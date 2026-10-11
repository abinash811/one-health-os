import { test, expect } from '@playwright/test';

// Authenticate before purchases tests
test.beforeEach(async ({ page }) => {
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('login-email-input').fill(process.env.E2E_EMAIL || 'admin@pharmacy.com');
  await page.getByTestId('login-password-input').fill(process.env.E2E_PASSWORD || 'admin123');
  await page.getByTestId('login-submit-btn').click();
  await page.waitForURL(/dashboard/, { waitUntil: 'domcontentloaded' });
});

test.describe('Purchases', () => {
  test('navigates to purchases page', async ({ page }) => {
    await page.goto('/purchases', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('purchases-page')).toBeVisible();
  });

  // Drives the real create-purchase flow end to end (supplier select, product
  // search, line-item entry, invoice-breakdown confirm) and then checks the
  // real inventory API — not just that a success toast appeared — that
  // confirming a purchase actually creates stock. This is the same class of
  // check that caught the silent /reports/dashboard and /analytics/summary
  // bug on Aug 22, 2026: a passing UI flow with wrong (or missing) downstream
  // data is exactly what "it looked done" bugs look like.
  test('creating and confirming a purchase adds real stock', async ({ page, request }) => {
    const authHeader = { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('token'))}` };
    const unique = Date.now();
    const supplierName = `E2E Supplier ${unique}`;
    const medicineName = `E2E Purchase Medicine ${unique}`;

    // Seed a supplier and a product via the real API — this test is about
    // the purchase-confirm flow itself, not supplier/product creation
    // (already covered by the Suppliers page and inventory.spec.ts).
    const supplierRes = await request.post('/api/suppliers', { headers: authHeader, data: { name: supplierName } });
    expect(supplierRes.ok()).toBeTruthy();
    const supplier = await supplierRes.json();

    const productRes = await request.post('/api/products', { headers: authHeader, data: { name: medicineName } });
    expect(productRes.ok()).toBeTruthy();

    await page.goto('/purchases', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('new-purchase-btn').click();
    await page.waitForURL(/purchases\/create/, { waitUntil: 'domcontentloaded' });
    // The page is still loading its lists right after the URL changes; a click on the Distributor menu in that
    // window is lost when the page re-renders. Wait for it to settle, as a user would.
    await page.waitForLoadState('networkidle');

    await page.getByTestId('supplier-selector').click();
    await page.getByTestId('supplier-search-input').fill(supplierName);
    await page.getByTestId(`supplier-option-${supplier.id}`).click();

    await page.getByTestId('product-search').fill(medicineName);
    await page.getByText(medicineName).first().click();

    await page.getByTestId('batch-0').fill('E2EBATCH1');
    await page.getByTestId('expiry-0').fill('12/27');
    await page.getByTestId('qty-0').fill('10');
    await page.getByTestId('ptr-0').fill('20');
    await page.getByTestId('mrp-0').fill('30');

    await page.getByTestId('confirm-btn').click();
    await page.getByTestId('confirm-save-btn').click();

    await page.waitForURL(/\/purchases$/, { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('purchases-table')).toContainText(supplierName);

    // The real check: stock actually landed, in the right quantity — not
    // just that the purchase row exists.
    const inventoryRes = await request.get(
      `/api/inventory?search=${encodeURIComponent(medicineName)}`,
      { headers: authHeader },
    );
    expect(inventoryRes.ok()).toBeTruthy();
    const inventory = await inventoryRes.json();
    expect(inventory.items.length).toBeGreaterThanOrEqual(1);
    expect(inventory.items[0].total_qty_units).toBeGreaterThanOrEqual(10);
  });
});
