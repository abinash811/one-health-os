"""
EMR step 2 (docs/28_EMR_SCOPE.md): ONE prescription per visit carrying the
consultation record + medicine lines. HTTP integration tests (P0): tenant
isolation, doctor-only editing, draft/issued/cancelled lifecycle, one live Rx
per appointment, history suggestions.
"""
import uuid

import requests

from test_emr_appointments import BASE_URL, _EmrBase, _next_weekday_date


class TestPrescriptions(_EmrBase):
    def _visit(self):
        day = _next_weekday_date(1)
        doctor_id = self._doctor_with_schedule(1)
        patient = self._patient()
        appt = self._book(patient["id"], doctor_id, day, start="09:00").json()
        return patient, appt

    def _start(self, appt, session=None):
        return (session or self.session).post(
            f"{BASE_URL}/api/emr/prescriptions", json={"appointment_id": appt["id"]})

    def test_full_lifecycle_in_one_record(self):
        patient, appt = self._visit()
        rx = self._start(appt).json()
        assert rx["status"] == "draft" and rx["rx_number"].startswith("RX-")
        assert rx["patient_name"] == patient["name"] and rx["clinic"]["name"]
        again = self._start(appt).json()
        assert again["id"] == rx["id"]  # idempotent: one live Rx per visit

        body = {"vitals": {"bp_systolic": 120, "bp_diastolic": 80, "pulse": 72, "junk": 1},
                "complaints": "Fever 2 days", "diagnosis": "Viral fever", "advice": "Rest",
                "follow_up_date": "2030-01-10",
                "items": [{"medicine_name": "Paracetamol 650", "dosage": "1 tab",
                           "frequency": "TDS", "duration_days": 3, "quantity": 9},
                          {"medicine_name": "ORS", "instructions": "After each stool"}]}
        put = self.session.put(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}", json=body)
        assert put.status_code == 200, put.text
        got = put.json()
        assert got["vitals"] == {"bp_systolic": 120, "bp_diastolic": 80, "pulse": 72}
        assert [i["medicine_name"] for i in got["items"]] == ["Paracetamol 650", "ORS"]

        issued = self.session.post(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}/issue")
        assert issued.status_code == 200 and issued.json()["status"] == "issued"
        assert issued.json()["issued_at"]
        locked = self.session.put(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}", json=body)
        assert locked.status_code == 409

        hist = self.session.get(f"{BASE_URL}/api/emr/patients/{patient['id']}/prescriptions").json()
        assert [h["id"] for h in hist] == [rx["id"]]

    def test_cannot_issue_empty_and_cancel_frees_the_visit(self):
        _, appt = self._visit()
        rx = self._start(appt).json()
        assert self.session.post(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}/issue").status_code == 422
        assert self.session.post(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}/cancel",
                                 json={"reason": ""}).status_code == 422
        c = self.session.post(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}/cancel",
                              json={"reason": "Wrong patient"})
        assert c.status_code == 200 and c.json()["status"] == "cancelled"
        new = self._start(appt).json()
        assert new["id"] != rx["id"] and new["rx_number"] != rx["rx_number"]

    def test_vitals_validation(self):
        _, appt = self._visit()
        rx = self._start(appt).json()
        r = self.session.put(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}",
                             json={"vitals": {"pulse": -5}, "items": []})
        assert r.status_code == 422

    def test_suggestions_from_own_history(self):
        _, appt = self._visit()
        rx = self._start(appt).json()
        name = f"Zyloxa{self.suffix}"
        self.session.put(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}",
                         json={"items": [{"medicine_name": name}]})
        s = self.session.get(f"{BASE_URL}/api/emr/prescriptions/suggestions", params={"q": "zylox"})
        assert name in s.json()

    def test_permissions_receptionist_views_but_cannot_write(self):
        _, appt = self._visit()
        rx = self._start(appt).json()
        _, rec = self._user("receptionist")
        assert rec.get(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}").status_code == 200
        assert self._start(appt, rec).status_code == 403
        assert rec.put(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}", json={"items": []}).status_code == 403
        assert rec.post(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}/issue").status_code == 403
        _, cashier = self._user("cashier")
        assert cashier.get(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}").status_code == 403

    def test_other_pharmacy_cannot_touch_prescription(self):
        _, appt = self._visit()
        rx = self._start(appt).json()
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_rx_other_{self.suffix}@pharmacy.com", "name": "Other Admin",
            "password": "OtherPharmTest123", "phone": "9855555582",
            "pharmacy_name": f"EMR RX Other {self.suffix}", "address": "2 St", "city": "Testville",
            "state": "Karnataka", "pincode": "560002",
            "drug_license_number": f"DL-EMRRX-{self.suffix}"})
        assert other.status_code == 200, other.text
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        u = f"{BASE_URL}/api/emr/prescriptions/{rx['id']}"
        assert requests.get(u, headers=h).status_code == 404
        assert requests.put(u, json={"items": []}, headers=h).status_code == 404
        assert requests.post(f"{u}/issue", headers=h).status_code == 404
        assert requests.post(f"{u}/cancel", json={"reason": "x"}, headers=h).status_code == 404
        assert requests.post(f"{BASE_URL}/api/emr/prescriptions",
                             json={"appointment_id": appt["id"]}, headers=h).status_code == 404

    def test_unknown_appointment_404(self):
        r = self.session.post(f"{BASE_URL}/api/emr/prescriptions",
                              json={"appointment_id": str(uuid.uuid4())})
        assert r.status_code == 404

    def test_simultaneous_opens_return_the_same_prescription(self):
        from concurrent.futures import ThreadPoolExecutor
        _, appt = self._visit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self._start(appt), range(4)))
        assert all(r.status_code == 200 for r in results), [r.text for r in results]
        assert len({r.json()["id"] for r in results}) == 1
