"""
Patient Billing B2 (docs/29_BILLING_SCOPE.md): the doctor's consultation fee is posted to the
patient's account at check-in, once per visit, and withdrawn if the visit is cancelled before
it is billed. P0: no double charge, no silent loss of a billed charge, clinic isolation.
"""
import uuid
from datetime import date

import requests

from test_emr_appointments import BASE_URL
from test_patient_billing import API, _Billing


class _Fee(_Billing):
    def _doctor(self, fee_paise=50000):
        return super()._doctor(fee_paise=fee_paise)

    def _walk_in(self, doctor_id):
        patient = self._patient()
        appt = self._book(patient["id"], doctor_id, date.today())
        assert appt.status_code == 200, appt.text
        return patient, appt.json()

    def _move(self, appt, status, **extra):
        return self.session.post(f"{BASE_URL}/api/emr/appointments/{appt['id']}/status",
                                 json={"status": status, **extra})

    def _account(self, patient_id):
        return self.session.get(f"{API}/accounts/{patient_id}")


class TestConsultationFee(_Fee):
    def test_fee_belongs_to_the_clinic_and_is_set_from_the_clinic_doctors_list(self):
        doctor_id = self._doctor(fee_paise=45000)
        listed = self.session.get(f"{BASE_URL}/api/emr/clinic-doctors").json()
        assert next(d for d in listed if d["id"] == doctor_id)["consultation_fee_paise"] == 45000
        url = f"{BASE_URL}/api/emr/clinic-doctors/{doctor_id}"
        assert self.session.put(url, json={"consultation_fee_paise": 60000}).json()["consultation_fee_paise"] == 60000
        assert self.session.put(url, json={"consultation_fee_paise": -1}).status_code == 422
        assert self.session.put(url, json={"consultation_fee_paise": None}).json()["consultation_fee_paise"] is None
        _, rec = self._user("receptionist")
        assert rec.put(url, json={"consultation_fee_paise": 1}).status_code == 403
        assert self.session.put(f"{BASE_URL}/api/emr/clinic-doctors/{uuid.uuid4()}",
                                json={"consultation_fee_paise": 1}).status_code == 404

    def test_check_in_posts_the_fee_once(self):
        doctor_id = self._doctor(50000)
        patient, appt = self._walk_in(doctor_id)
        assert self._account(patient["id"]).status_code == 404          # nothing owed before check-in
        assert self._move(appt, "checked_in").status_code == 200
        acct = self._account(patient["id"]).json()
        assert len(acct["charges"]) == 1
        c = acct["charges"][0]
        assert (c["total_paise"], c["status"], c["source_module"]) == (50000, "unbilled", "emr")
        assert c["description"].startswith("Consultation — ") and c["encounter_ref"] == appt["id"]
        assert c["patient_name"] == patient["name"] and c["patient_uhid"] == patient["uhid"]
        assert self._move(appt, "checked_in").status_code == 409         # can't check in twice
        assert len(self._account(patient["id"]).json()["charges"]) == 1
        pending = self.session.get(f"{API}/accounts").json()
        assert [a["patient_id"] for a in pending["data"]] == [patient["id"]]
        assert pending["data"][0]["balance_paise"] == 50000 and pending["data"][0]["sources"] == ["emr"]

    def test_no_fee_set_means_no_charge(self):
        for fee in (None, 0):
            patient, appt = self._walk_in(self._doctor(fee_paise=fee))
            assert self._move(appt, "checked_in").status_code == 200
            assert self._account(patient["id"]).status_code == 404

    def test_later_fee_change_does_not_touch_posted_charge(self):
        doctor_id = self._doctor(50000)
        patient, appt = self._walk_in(doctor_id)
        self._move(appt, "checked_in")
        self.session.put(f"{BASE_URL}/api/emr/clinic-doctors/{doctor_id}", json={"consultation_fee_paise": 90000})
        assert self._account(patient["id"]).json()["charges"][0]["total_paise"] == 50000

    def test_cancel_before_billing_withdraws_the_fee(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        r = self._move(appt, "cancelled", cancel_reason="Patient left")
        assert r.status_code == 200
        c = self._account(patient["id"]).json()["charges"][0]
        assert c["status"] == "void" and "cancelled" in c["void_reason"].lower()
        assert self.session.get(f"{API}/accounts").json()["totals"]["patients"] == 0

    def test_cancel_after_invoicing_leaves_the_billed_charge_alone(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        charge = self._account(patient["id"]).json()["charges"][0]
        assert self._invoice(patient["id"], [charge["id"]], counter="front_desk").status_code == 200
        assert self._move(appt, "cancelled", cancel_reason="Changed mind").status_code == 200
        acct = self._account(patient["id"]).json()
        assert acct["charges"][0]["status"] == "invoiced"                # billing desk decides; no silent loss
        assert acct["totals"]["balance_paise"] == 50000

    def test_booked_no_show_has_no_charge(self):
        patient, appt = self._walk_in(self._doctor(50000))
        assert self._move(appt, "no_show").status_code == 200
        assert self._account(patient["id"]).status_code == 404

    def test_fee_charges_stay_inside_the_clinic(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"fee_o_{self.suffix}@pharmacy.com", "name": "Other", "password": "OtherFee12345",
            "phone": "9855555587", "pharmacy_name": f"Fee Other {self.suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560007",
            "drug_license_number": f"DL-FEEO-{self.suffix}"})
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        assert requests.get(f"{API}/accounts/{patient['id']}", headers=h).status_code == 404
        assert requests.get(f"{API}/accounts", headers=h).json()["totals"]["patients"] == 0

    def test_fee_posting_is_in_the_audit_trail(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        charge_id = self._account(patient["id"]).json()["charges"][0]["id"]
        logs = self.session.get(f"{BASE_URL}/api/audit-logs", params={"entity_type": "pb_charge_item"})
        assert logs.status_code == 200, logs.text
        body = logs.json()
        rows = body["data"] if isinstance(body, dict) and "data" in body else body
        assert any(r.get("entity_id") == charge_id and r.get("action") == "create" for r in rows)


class TestFeeOnTheQueue(_Fee):
    """B3: the appointment list tells the front desk where each visit's fee stands."""

    def _row(self, appt):
        rows = self.session.get(f"{BASE_URL}/api/emr/appointments",
                                params={"date": date.today().isoformat()}).json()
        return next(r for r in rows if r["id"] == appt["id"])

    def test_fee_state_follows_the_money(self):
        patient, appt = self._walk_in(self._doctor(50000))
        assert self._row(appt)["fee"] is None                           # booked: nothing owed yet
        self._move(appt, "checked_in")
        fee = self._row(appt)["fee"]
        assert (fee["status"], fee["amount_paise"], fee["balance_paise"]) == ("unpaid", 50000, 50000)
        assert fee["mode"] is None and fee["invoice_id"] is None

        part = self.session.post(f"{API}/accounts/{patient['id']}/collect", json={
            "charge_item_ids": [fee["charge_id"]], "amount_paise": 20000, "mode": "upi", "counter": "front_desk"})
        assert part.status_code == 200
        fee = self._row(appt)["fee"]
        assert (fee["status"], fee["paid_paise"], fee["balance_paise"], fee["mode"]) == (
            "part_paid", 20000, 30000, "upi")
        assert fee["invoice_id"] == part.json()["invoice"]["id"]

        rest = self.session.post(f"{API}/invoices/{fee['invoice_id']}/payments",
                                 json={"amount_paise": 30000, "mode": "cash"})
        assert rest.status_code == 200
        fee = self._row(appt)["fee"]
        assert (fee["status"], fee["balance_paise"], fee["mode"]) == ("paid", 0, "cash")
        assert fee["invoice_number"].startswith("INV-")

    def test_withdrawn_or_absent_fee_is_not_shown(self):
        _, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        self._move(appt, "cancelled", cancel_reason="Left")
        assert self._row(appt)["fee"] is None                           # voided fee disappears from the queue
        _, no_fee = self._walk_in(self._doctor(fee_paise=None))
        self._move(no_fee, "checked_in")
        assert self._row(no_fee)["fee"] is None


class TestPatientWithMoneyOwed(_Fee):
    """B5 audit: a patient who owes money can't be deleted — their bill would be orphaned."""

    def test_delete_is_refused_until_the_bill_is_settled(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")                                   # ₹500 fee now unbilled
        r = self.session.delete(f"{BASE_URL}/api/emr/patients/{patient['id']}")
        assert r.status_code == 409 and "₹500.00" in r.json()["detail"] and patient["name"] in r.json()["detail"]
        charge = self._account(patient["id"]).json()["charges"][0]
        self.session.post(f"{API}/accounts/{patient['id']}/collect",
                          json={"charge_item_ids": [charge["id"]], "amount_paise": 20000, "mode": "cash"})
        part_paid = self.session.delete(f"{BASE_URL}/api/emr/patients/{patient['id']}")
        assert part_paid.status_code == 409                                  # part-paid still owes
        invoice_id = self._account(patient["id"]).json()["invoices"][0]["id"]
        assert self._pay(invoice_id, 30000).status_code == 200
        assert self.session.delete(f"{BASE_URL}/api/emr/patients/{patient['id']}").status_code == 200  # settled
        assert self.session.get(f"{API}/accounts/{patient['id']}").status_code == 200  # bill history is kept

    def test_voided_fee_does_not_block_delete(self):
        patient, appt = self._walk_in(self._doctor(50000))
        self._move(appt, "checked_in")
        self._move(appt, "cancelled", cancel_reason="Left")
        assert self.session.delete(f"{BASE_URL}/api/emr/patients/{patient['id']}").status_code == 200
