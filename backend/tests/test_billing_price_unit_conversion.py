"""
Regression tests for the Sep 11, 2026 billing pricing P0 found during a live
end-to-end walkthrough (Supplier -> Customer -> Inventory -> Billing):

`_batch_for_billing()` (backend/routers/inventory.py) divided a batch's
mrp_per_unit by the product's units_per_pack a second time. mrp_paise is
already stored as a per-UNIT price (confirmed by batches.py's own batch
response, which returns mrp_paise/100 with no conversion) — units_per_pack
only converts a pack-based quantity into loose units, it never applies to
price. The result: searching for a medicine during billing showed and
actually charged MRP / units_per_pack instead of the real MRP — a 90%
undercharge for a standard 10-tablet strip, on every sale, silently,
because create_bill only rejects a submitted price that EXCEEDS the real
batch MRP, never one that's suspiciously low.

Covers GET /products/search-with-batches (typed search), which feeds the
billing medicine-search UI via the buggy helper (`_get_active_batches` ->
`_batch_for_billing`). A second test proves the whole chain end-to-end:
the price the search endpoint returns is the exact price a real finalized
bill charges.

See docs/15_ROADMAP.md's RULE MISSES LOG for the full writeup.
"""
import pytest
import requests
import os
import uuid
from datetime import date, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class _AuthedTestBase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@pharmacy.com",
            "password": "admin123",
        })
        if login_response.status_code == 200:
            token = login_response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping billing price conversion tests")

    def _create_product(self, sku, name, units_per_pack):
        payload = {
            "sku": sku, "name": name, "category": "medicine", "gst_percent": 5,
            "units_per_pack": units_per_pack,
        }
        resp = self.session.post(f"{BASE_URL}/api/products", json=payload)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _create_batch(self, sku, qty, mrp_per_unit, cost_per_unit):
        expiry = (date.today() + timedelta(days=365)).isoformat()
        resp = self.session.post(f"{BASE_URL}/api/stock/batches", json={
            "product_sku": sku, "batch_no": f"PRICE-{uuid.uuid4().hex[:6]}",
            "expiry_date": expiry, "qty_on_hand": qty,
            "cost_price_per_unit": cost_per_unit, "mrp_per_unit": mrp_per_unit,
        })
        assert resp.status_code == 200, resp.text
        return resp.json()


class TestBatchPriceNotDividedByPackSize(_AuthedTestBase):
    """units_per_pack must convert quantity, never price."""

    def test_search_with_batches_returns_real_per_unit_mrp(self):
        sku = f"PRICE-SRCH-{uuid.uuid4().hex[:8]}"
        name = f"PriceSearchTest_{uuid.uuid4().hex[:8]}"
        self._create_product(sku, name, units_per_pack=10)
        self._create_batch(sku, qty=100, mrp_per_unit=2.50, cost_per_unit=1.80)

        resp = self.session.get(f"{BASE_URL}/api/products/search-with-batches", params={"q": name})
        assert resp.status_code == 200, resp.text
        results = resp.json()
        assert len(results) == 1, f"Expected exactly 1 product match, got {results}"
        batches = results[0]["batches"]
        assert len(batches) == 1
        batch = batches[0]

        # The bug divided this by units_per_pack (10), returning 0.25.
        assert batch["mrp_per_unit"] == pytest.approx(2.50), (
            f"mrp_per_unit was divided by units_per_pack again — got "
            f"{batch['mrp_per_unit']}, expected 2.50 (the real per-unit MRP)")
        assert batch["mrp"] == pytest.approx(2.50)
        # qty_on_hand is stored in real units (migration a343c922f896) —
        # total_units is a plain alias, never multiplied by units_per_pack.
        assert batch["total_units"] == 100

    def test_a_real_finalized_bill_charges_the_real_mrp_not_a_fraction_of_it(self):
        """End-to-end: the price the search endpoint hands the billing UI is
        the exact price a real finalized bill charges — not a units_per_pack
        fraction of it. Uses the real POST /bills contract (BillCreate):
        status="paid" to finalize (not a draft), items as a raw dict list
        resolved by batch_id, mrp/unit_price returned in rupees (not paise)
        per _bill_item_response."""
        sku = f"PRICE-BILL-{uuid.uuid4().hex[:8]}"
        name = f"PriceBillTest_{uuid.uuid4().hex[:8]}"
        self._create_product(sku, name, units_per_pack=10)
        batch = self._create_batch(sku, qty=100, mrp_per_unit=2.50, cost_per_unit=1.80)

        search = self.session.get(f"{BASE_URL}/api/products/search-with-batches",
                                  params={"q": name}).json()
        unit_price = search[0]["batches"][0]["mrp_per_unit"]
        assert unit_price == pytest.approx(2.50)

        bill_resp = self.session.post(f"{BASE_URL}/api/bills", json={
            "customer_name": "Price Regression Walk-in",
            "payment_method": "cash",
            "status": "paid",
            "tax_rate": 5,
            "items": [{
                "product_sku": sku,
                "batch_id": batch["id"],
                "quantity": 4,
                "unit_price": unit_price,
                "disc_percent": 0,
                "gst_percent": 5,
            }],
        })
        assert bill_resp.status_code == 200, bill_resp.text
        bill = bill_resp.json()
        item = bill["items"][0]

        # The bugged endpoint would have handed the UI 0.25 as "the MRP",
        # and the bill would have silently charged that instead of 2.50 —
        # a real, finalized, stock-deducting sale at 10% of the true price.
        assert item["mrp"] == pytest.approx(2.50), (
            f"Bill item's MRP was charged as {item['mrp']}, expected the real "
            f"2.50/unit — units_per_pack must never divide price")
        assert item["unit_price"] == pytest.approx(2.50)
        assert item["quantity"] == 4
