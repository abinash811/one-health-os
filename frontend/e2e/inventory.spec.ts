import { test, expect, Page } from '@playwright/test';

// Medicine names must come from the catalog (AddMedicineModal's strict SuggestField, Sep 19, 2026) —
// type a few letters and pick the first suggestion, like a user does. Returns the chosen name.
async function pickCatalogMedicine(page: Page): Promise<string> {
  const input = page.getByTestId('medicine-name-input');
  await input.fill('Dolo');
  await page.getByRole('button', { name: /dolo/i }).first().dispatchEvent('mousedown');
  await expect(input).not.toHaveValue('Dolo');
  return input.inputValue();
}


// Authenticate before inventory tests
test.beforeEach(async ({ page }) => {
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('login-email-input').fill(process.env.E2E_EMAIL || 'admin@pharmacy.com');
  await page.getByTestId('login-password-input').fill(process.env.E2E_PASSWORD || 'admin123');
  await page.getByTestId('login-submit-btn').click();
  await page.waitForURL(/dashboard/, { waitUntil: 'domcontentloaded' });
});

test.describe('Inventory', () => {
  test('navigates to inventory page', async ({ page }) => {
    await page.goto('/inventory', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('add-medicine-btn')).toBeVisible();
  });

  test('adding a medicine makes it appear in the inventory list', async ({ page }) => {

    await page.goto('/inventory', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('add-medicine-btn').click();

    const medicineName = await pickCatalogMedicine(page);
    await page.getByTestId('medicine-category-select').selectOption({ index: 1 });
    await page.getByTestId('medicine-dosageform-select').selectOption({ index: 1 });

    const expiry = new Date();
    expiry.setDate(expiry.getDate() + 400);
    await page.getByTestId('medicine-batchno-input').fill(`E2E-BATCH-${Date.now()}`);
    await page.getByTestId('medicine-expiry-input').fill(expiry.toISOString().slice(0, 10));
    await page.getByTestId('medicine-quantity-input').fill('25');
    await page.getByTestId('medicine-mrp-input').fill('50');

    await page.getByTestId('add-medicine-submit-btn').click();

    // The results table only renders after a search or filter is applied
    // (useInventorySearch.js's `hasSearched` gate) — the list page shows an
    // empty "Start searching..." state by default, even right after adding
    // a product. Search for the new medicine by name to bring it up.
    await page.getByTestId('inventory-search-input').fill(medicineName);
    await expect(page.getByTestId('inventory-results-table')).toContainText(medicineName, { timeout: 10000 });
  });

  // Regression test for the August 22, 2026 bug where GET /reports/dashboard
  // and GET /analytics/summary silently returned all-zero data for every
  // pharmacy (a func.case(..., else_=...) misuse swallowed by a broad
  // except Exception). Checked at the API level, not through a page: as of
  // this writing neither endpoint is called by any frontend page (verified
  // by grep — apiUrl.analyticsSummary is defined but never invoked, and
  // 'reports/dashboard' has no call site either; the Dashboard page's real
  // stat cards come from the separate, unaffected /analytics/dashboard).
  // Kept here as a live-server API check — not a UI assertion, since there
  // is currently no UI to assert against — so a future regression in
  // either endpoint is still caught even before something starts rendering
  // them.
  test('reports/dashboard and analytics/summary APIs return real data, not silent zeros', async ({ page, request }) => {
    await page.goto('/inventory', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('add-medicine-btn').click();
    const medicineName = await pickCatalogMedicine(page);
    await page.getByTestId('medicine-category-select').selectOption({ index: 1 });
    await page.getByTestId('medicine-dosageform-select').selectOption({ index: 1 });
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + 400);
    await page.getByTestId('medicine-batchno-input').fill(`E2E-BATCH-${Date.now()}`);
    await page.getByTestId('medicine-expiry-input').fill(expiry.toISOString().slice(0, 10));
    await page.getByTestId('medicine-quantity-input').fill('3');
    await page.getByTestId('medicine-mrp-input').fill('40');
    await page.getByTestId('add-medicine-submit-btn').click();
    // See the comment in the previous test — the results table needs an
    // explicit search before it renders anything.
    await page.getByTestId('inventory-search-input').fill(medicineName);
    await expect(page.getByTestId('inventory-results-table')).toContainText(medicineName, { timeout: 10000 });

    const authHeader = { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('token'))}` };

    const dashboardRes = await request.get('/api/reports/dashboard', { headers: authHeader });
    expect(dashboardRes.ok()).toBeTruthy();
    const dashboard = await dashboardRes.json();
    expect(dashboard.total_medicines).toBeGreaterThanOrEqual(1);

    const summaryRes = await request.get('/api/analytics/summary', { headers: authHeader });
    expect(summaryRes.ok()).toBeTruthy();
    // Just confirms the endpoint doesn't error and returns the expected
    // shape — this test doesn't create a bill, so gross_sales isn't
    // asserted beyond being a number (the backend pytest regression test
    // covers the with-a-real-sale case).
    const summary = await summaryRes.json();
    expect(typeof summary.gross_sales).toBe('number');
  });
});
