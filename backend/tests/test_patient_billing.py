"""
Patient Billing B1 (docs/29_BILLING_SCOPE.md): charges -> invoices -> payments, the
billing desk's Pending list, and the day summary. HTTP integration tests (P0): money
integrity (no overpay, no double-invoicing even under simultaneous requests), idempotent
charge posting, numbers never reused, per-role permissions, per-clinic isolation.
Each test runs in its own freshly registered pharmacy.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

from test_emr_appointments import BASE_URL
from test_emr_settings import _Clinic

API = f"{BASE_URL}/api/patient-billing"


class _Billing(_Clinic):
    def _post(self, patient=None, name="Asha Menon", price=50000, qty=1, key=None, source="emr",
              desc="Consultation", session=None, **extra):
        pid = patient or str(uuid.uuid4())
        body = {"patient_id": pid, "patient_name": name, "patient_uhid": "UH-000001", "source_module": source,
                "description": desc, "unit_price_paise": price, "quantity": qty, **extra}
        if key:
            body["idempotency_key"] = key
        return (session or self.session).post(f"{API}/charges", json=body)

    def _charge(self, patient, **kw):
        r = self._post(patient=patient, **kw)
        assert r.status_code == 200, r.text
        return r.json()

    def _invoice(self, patient, ids, discount=0, session=None, counter="billing_desk"):
        return (session or self.session).post(f"{API}/invoices", json={
            "patient_id": patient, "charge_item_ids": ids, "discount_paise": discount, "counter": counter})

    def _pay(self, invoice_id, amount, mode="cash", session=None):
        return (session or self.session).post(f"{API}/invoices/{invoice_id}/payments",
                                              json={"amount_paise": amount, "mode": mode})

    def _owed(self, patient):
        """Fresh patient with two charges (₹500 + ₹300) and an invoice for the first."""
        a = self._charge(patient, price=50000)
        b = self._charge(patient, price=30000, desc="Lab")
        return a, b


class TestCharges(_Billing):
    def test_post_is_idempotent_and_correct(self):
        p = str(uuid.uuid4())
        first = self._charge(p, price=25000, qty=2, key=f"k-{self.suffix}")
        again = self._charge(p, price=25000, qty=2, key=f"k-{self.suffix}")
        assert first["id"] == again["id"]
        assert first["total_paise"] == 50000 and first["status"] == "unbilled"
        acct = self.session.get(f"{API}/accounts/{p}").json()
        assert len(acct["charges"]) == 1 and acct["totals"]["balance_paise"] == 50000

    def test_validation(self):
        p = str(uuid.uuid4())
        assert self._post(patient=p, price=0).status_code == 422
        assert self._post(patient=p, qty=0).status_code == 422
        assert self._post(patient=p, source="alien").status_code == 422
        r = self._post(patient=p, source="pharmacy")           # pharmacy bills only from the pharmacy
        assert r.status_code == 422 and "pharmacy" in r.json()["detail"].lower()
        assert self._post(patient=p, desc="   ").status_code == 422

    def test_void_rules(self):
        p = str(uuid.uuid4())
        a, b = self._owed(p)
        assert self.session.post(f"{API}/charges/{a['id']}/void", json={"reason": ""}).status_code == 422
        v = self.session.post(f"{API}/charges/{a['id']}/void", json={"reason": "Entered twice"})
        assert v.status_code == 200 and v.json()["status"] == "void"
        assert self.session.post(f"{API}/charges/{a['id']}/void", json={"reason": "again"}).status_code == 409
        self._invoice(p, [b["id"]])
        r = self.session.post(f"{API}/charges/{b['id']}/void", json={"reason": "oops"})
        assert r.status_code == 409 and "invoice" in r.json()["detail"]
        assert self.session.get(f"{API}/accounts/{p}").json()["totals"]["total_charges_paise"] == 30000

    def test_permissions(self):
        p = str(uuid.uuid4())
        _, rec = self._user("receptionist")
        _, doc = self._user("doctor")
        _, cashier = self._user("cashier")                        # a pharmacy role: no clinic billing
        assert self._post(patient=p, session=rec).status_code == 200
        assert doc.get(f"{API}/accounts").status_code == 200
        assert self._post(patient=p, session=doc).status_code == 403
        assert self._post(patient=p, session=cashier).status_code == 403
        assert cashier.get(f"{API}/accounts").status_code == 403
        assert rec.post(f"{API}/charges/{uuid.uuid4()}/void", json={"reason": "x"}).status_code == 403

    def test_other_clinic_cannot_touch_my_charge(self):
        p = str(uuid.uuid4())
        a, _ = self._owed(p)
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"pb_other_{self.suffix}@pharmacy.com", "name": "Other", "password": "OtherBill12345",
            "phone": "9855555586", "pharmacy_name": f"PB Other {self.suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560006",
            "drug_license_number": f"DL-PBO-{self.suffix}"})
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        assert requests.post(f"{API}/charges/{a['id']}/void", json={"reason": "x"}, headers=h).status_code == 404
        r = requests.post(f"{API}/invoices", json={"patient_id": p, "charge_item_ids": [a["id"]]}, headers=h)
        assert r.status_code == 404
        assert requests.get(f"{API}/accounts/{p}", headers=h).status_code == 404
        assert requests.get(f"{API}/accounts", headers=h).json()["totals"]["patients"] == 0


class TestInvoicesAndPayments(_Billing):
    def test_invoice_freezes_lines_and_marks_charges(self):
        p = str(uuid.uuid4())
        a, b = self._owed(p)
        inv = self._invoice(p, [a["id"], b["id"]], discount=5000).json()
        assert inv["invoice_number"] == "INV-000001" and inv["status"] == "issued"
        assert (inv["gross_paise"], inv["discount_paise"], inv["net_paise"]) == (80000, 5000, 75000)
        assert {line["description"] for line in inv["lines"]} == {"Consultation", "Lab"}
        acct = self.session.get(f"{API}/accounts/{p}").json()
        assert {c["status"] for c in acct["charges"]} == {"invoiced"}
        assert acct["totals"]["invoiced_unpaid_paise"] == 75000 and acct["totals"]["not_invoiced_paise"] == 0

    def test_invoice_validation(self):
        p, q = str(uuid.uuid4()), str(uuid.uuid4())
        a, b = self._owed(p)
        other_patients_charge = self._charge(q)
        assert self._invoice(p, []).status_code == 422
        assert self._invoice(p, [a["id"]], discount=999999).status_code == 422
        assert self._invoice(p, [other_patients_charge["id"]]).status_code == 404
        assert self._invoice(p, [str(uuid.uuid4())]).status_code == 404
        assert self._invoice(p, [a["id"]], counter="mars").status_code == 422
        assert self._invoice(p, [a["id"]]).status_code == 200
        assert self._invoice(p, [a["id"]]).status_code == 409        # already billed

    def test_part_payment_then_full_and_receipts(self):
        p = str(uuid.uuid4())
        a, _ = self._owed(p)
        inv = self._invoice(p, [a["id"]]).json()
        r1 = self._pay(inv["id"], 20000, "upi")
        assert r1.status_code == 200
        assert r1.json()["payment"]["receipt_number"] == "RCT-000001"
        assert r1.json()["invoice"]["status"] == "part_paid" and r1.json()["invoice"]["balance_paise"] == 30000
        assert self._pay(inv["id"], 30001).status_code == 422          # more than the balance
        assert self._pay(inv["id"], 100, "bitcoin").status_code == 422
        r2 = self._pay(inv["id"], 30000, "cash")
        assert r2.json()["payment"]["receipt_number"] == "RCT-000002" and r2.json()["invoice"]["status"] == "paid"
        assert self._pay(inv["id"], 100).status_code == 409            # already fully paid
        acct = self.session.get(f"{API}/accounts/{p}").json()
        assert acct["totals"]["paid_paise"] == 50000
        assert next(c for c in acct["charges"] if c["id"] == a["id"])["status"] == "paid"

    def test_cancel_rules_and_numbers_never_reused(self):
        p = str(uuid.uuid4())
        a, b = self._owed(p)
        inv = self._invoice(p, [a["id"]]).json()
        assert self.session.post(f"{API}/invoices/{inv['id']}/cancel", json={"reason": ""}).status_code == 422
        cancel = self.session.post(f"{API}/invoices/{inv['id']}/cancel", json={"reason": "Wrong patient"})
        assert cancel.status_code == 200
        assert self._pay(inv["id"], 100).status_code == 409             # cancelled can't be paid
        acct = self.session.get(f"{API}/accounts/{p}").json()
        assert all(c["status"] == "unbilled" for c in acct["charges"]) and acct["invoices"] == []
        again = self._invoice(p, [a["id"]]).json()
        assert again["invoice_number"] == "INV-000002"                  # cancelled number is not reused
        self._pay(again["id"], 1000)
        r = self.session.post(f"{API}/invoices/{again['id']}/cancel", json={"reason": "Refund?"})
        assert r.status_code == 409 and "refund" in r.json()["detail"].lower()

    def test_full_discount_settles_immediately(self):
        p = str(uuid.uuid4())
        a = self._charge(p, price=10000)
        inv = self._invoice(p, [a["id"]], discount=10000).json()
        assert inv["status"] == "paid" and inv["net_paise"] == 0
        acct = self.session.get(f"{API}/accounts/{p}").json()
        assert acct["totals"]["balance_paise"] == 0

    def test_collect_in_one_step(self):
        p = str(uuid.uuid4())
        a, b = self._owed(p)
        r = self.session.post(f"{API}/accounts/{p}/collect", json={
            "charge_item_ids": [a["id"]], "mode": "cash", "counter": "front_desk"})
        assert r.status_code == 200
        assert r.json()["invoice"]["status"] == "paid" and r.json()["payment"]["amount_paise"] == 50000
        part = self.session.post(f"{API}/accounts/{p}/collect", json={
            "charge_item_ids": [b["id"]], "amount_paise": 10000, "mode": "upi", "reference": "ab12"})
        assert part.json()["invoice"]["status"] == "part_paid" and part.json()["payment"]["reference"] == "ab12"
        _, doc = self._user("doctor")
        assert doc.post(f"{API}/accounts/{p}/collect", json={"charge_item_ids": [], "mode": "cash"}).status_code == 403

    def test_simultaneous_payments_never_overpay(self):
        p = str(uuid.uuid4())
        inv = self._invoice(p, [self._charge(p, price=10000)["id"]]).json()
        with ThreadPoolExecutor(max_workers=5) as pool:
            res = list(pool.map(lambda _: self._pay(inv["id"], 10000), range(5)))
        assert sorted(r.status_code for r in res).count(200) == 1, [r.text for r in res]
        got = self.session.get(f"{API}/invoices/{inv['id']}").json()
        assert got["paid_paise"] == 10000 and len(got["payments"]) == 1

    def test_simultaneous_invoicing_of_one_charge_makes_one_invoice(self):
        p = str(uuid.uuid4())
        a = self._charge(p)
        with ThreadPoolExecutor(max_workers=4) as pool:
            res = list(pool.map(lambda _: self._invoice(p, [a["id"]]), range(4)))
        assert sorted(r.status_code for r in res).count(200) == 1, [r.text for r in res]
        assert len(self.session.get(f"{API}/accounts/{p}").json()["invoices"]) == 1


class TestAccountsAndSummary(_Billing):
    def _scenario(self):
        """A: unbilled ₹300 + part-paid invoice (₹500, ₹200 paid). B: all paid. C: lab charge unbilled."""
        a, b, c = (str(uuid.uuid4()) for _ in range(3))
        self._charge(a, name="Asha Menon", price=30000, desc="Dressing")
        inv = self._invoice(a, [self._charge(a, name="Asha Menon", price=50000)["id"]]).json()
        self._pay(inv["id"], 20000, "upi")
        self.session.post(f"{API}/accounts/{b}/collect", json={
            "charge_item_ids": [self._charge(b, name="Ravi Kumar", price=70000)["id"]], "mode": "cash",
            "counter": "front_desk"})
        self._charge(c, name="Sunita Rao", price=35000, source="lab", desc="CBC")
        return a, b, c

    def test_pending_list_and_filters(self):
        a, b, c = self._scenario()
        r = self.session.get(f"{API}/accounts").json()
        by = {x["patient_id"]: x for x in r["data"]}
        assert b not in by                                           # fully paid → not pending
        assert by[a]["not_invoiced_paise"] == 30000 and by[a]["invoiced_unpaid_paise"] == 30000
        assert by[a]["balance_paise"] == 60000 and by[a]["has_part_paid"] is True
        assert r["totals"] == {"balance_paise": 95000, "not_invoiced_paise": 65000,
                               "invoiced_unpaid_paise": 30000, "patients": 2}
        assert [x["patient_id"] for x in r["data"]] == [a, c]        # biggest balance first
        ni = self.session.get(f"{API}/accounts", params={"status": "not_invoiced"}).json()
        assert {x["patient_id"] for x in ni["data"]} == {a, c}
        iu = self.session.get(f"{API}/accounts", params={"status": "invoiced_unpaid"}).json()
        assert [x["patient_id"] for x in iu["data"]] == [a]

        def ids(**params):
            return [x["patient_id"] for x in self.session.get(f"{API}/accounts", params=params).json()["data"]]

        assert ids(status="part_paid") == [a]
        assert ids(source="lab") == [c]
        assert ids(search="sunita") == [c]
        allr = self.session.get(f"{API}/accounts", params={"status": "all"}).json()
        assert {x["patient_id"] for x in allr["data"]} == {a, c}     # 'all' lists accounts that owe or are being billed
        assert self.session.get(f"{API}/accounts", params={"status": "weird"}).status_code == 422

    def test_account_detail(self):
        a, _, _ = self._scenario()
        acct = self.session.get(f"{API}/accounts/{a}").json()
        assert acct["patient"]["name"] == "Asha Menon"
        assert acct["totals"] == {"total_charges_paise": 80000, "paid_paise": 20000,
                                  "not_invoiced_paise": 30000, "invoiced_unpaid_paise": 30000,
                                  "balance_paise": 60000}
        assert len(acct["charges"]) == 2 and len(acct["invoices"]) == 1 and len(acct["payments"]) == 1
        assert self.session.get(f"{API}/accounts/{uuid.uuid4()}").status_code == 404

    def test_summary_and_receipts(self):
        self._scenario()
        s = self.session.get(f"{API}/summary/today").json()
        assert s["collected_paise"] == 90000 and s["receipts"] == 2
        assert s["by_mode"] == {"upi": 20000, "cash": 70000}
        assert s["by_counter"] == {"billing_desk": 20000, "front_desk": 70000}
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert self.session.get(f"{API}/summary/today", params={"date": yesterday}).json()["collected_paise"] == 0
        pays = self.session.get(f"{API}/payments", params={"date": date.today().isoformat()}).json()
        assert pays["pagination"]["total_items"] == 2
        assert {p["receipt_number"] for p in pays["data"]} == {"RCT-000001", "RCT-000002"}
