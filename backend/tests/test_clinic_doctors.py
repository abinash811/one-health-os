"""
Doctors at a clinic (docs/32_CLINICS_SCOPE.md P2c): the clinic-side view of the doctor↔clinic mapping.
Tick a doctor to practise here (fee for this clinic), untick to remove; nothing is deleted.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"


def _session(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


def _register(tag):
    sfx = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/auth/register", json={
        "email": f"{tag}_{sfx}@pharmacy.com", "name": f"{tag} Admin", "password": "ClinicDoc123",
        "phone": "9877750000", "pharmacy_name": f"{tag} Pharmacy {sfx}", "address": "1 St", "city": "T",
        "state": "K", "pincode": "560001", "drug_license_number": f"DL-{tag}-{sfx}"})
    assert r.status_code == 200, r.text
    return _session(r.json()["token"])


class TestClinicDoctors:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = _register("cd")
        self.c1 = self.s.post(f"{API}/clinics", json={"name": "Clinic One"}).json()["id"]
        self.c2 = self.s.post(f"{API}/clinics", json={"name": "Clinic Two"}).json()["id"]
        self.doc = self.s.post(f"{API}/practitioners", json={"name": "Dr Rao", "clinics": []}).json()["id"]

    def _rows(self, clinic):
        r = self.s.get(f"{API}/clinics/{clinic}/doctors")
        assert r.status_code == 200, r.text
        return {d["id"]: d for d in r.json()}

    def test_a_new_doctor_is_listed_but_not_ticked(self):
        row = self._rows(self.c1)[self.doc]
        assert row["mapped"] is False and row["consultation_fee_paise"] is None

    def test_ticking_maps_the_doctor_with_this_clinics_fee_only(self):
        r = self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": 50000})
        assert r.status_code == 200, r.text
        assert self._rows(self.c1)[self.doc]["mapped"] is True
        assert self._rows(self.c1)[self.doc]["consultation_fee_paise"] == 50000
        assert self._rows(self.c2)[self.doc]["mapped"] is False
        # the doctor's own screen shows the same mapping
        mine = self.s.get(f"{API}/practitioners/{self.doc}").json()["clinics"]
        assert [(c["clinic_id"], c["consultation_fee_paise"]) for c in mine] == [(self.c1, 50000)]
        # and EMR at that clinic now lists the doctor
        assert self.doc in {d["id"] for d in self.s.get(f"{API}/practitioners", params={"clinic_id": self.c1}).json()}

    def test_changing_the_fee_updates_in_place(self):
        self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": 50000})
        self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": 70000})
        assert self._rows(self.c1)[self.doc]["consultation_fee_paise"] == 70000

    def test_unticking_removes_softly_and_re_ticking_revives(self):
        self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": 50000})
        assert self.s.delete(f"{API}/clinics/{self.c1}/doctors/{self.doc}").status_code == 200
        assert self._rows(self.c1)[self.doc]["mapped"] is False
        assert self.s.delete(f"{API}/clinics/{self.c1}/doctors/{self.doc}").status_code == 404
        self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={})
        assert self._rows(self.c1)[self.doc]["mapped"] is True

    def test_negative_fee_is_refused(self):
        r = self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": -5})
        assert r.status_code == 422

    def test_other_workspaces_never_reach_my_clinic_or_doctors(self):
        other = _register("cdo")
        assert other.get(f"{API}/clinics/{self.c1}/doctors").status_code == 404
        assert other.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={}).status_code == 404
        mine = other.post(f"{API}/clinics", json={"name": "Theirs"}).json()["id"]
        assert other.put(f"{API}/clinics/{mine}/doctors/{self.doc}", json={}).status_code == 404

    def test_permissions_split_view_and_edit(self):
        role = f"cdv_{uuid.uuid4().hex[:6]}"
        self.s.post(f"{API}/roles", json={"name": role, "display_name": role,
                                          "permissions": ["clinics:view", "doctors:view"]})
        email = f"{role}@pharmacy.com"
        uid = self.s.post(f"{API}/users", json={"name": "Viewer", "email": email, "password": "Viewer12345",
                                                "role": role}).json()["id"]
        self.s.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": self.c1, "role": role})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Viewer12345"}).json()["token"]
        viewer = _session(tok)
        assert viewer.get(f"{API}/clinics/{self.c1}/doctors").status_code == 200
        assert viewer.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={}).status_code == 403
        assert viewer.delete(f"{API}/clinics/{self.c1}/doctors/{self.doc}").status_code == 403
        # a clinic they cannot open is refused even for reading
        assert viewer.get(f"{API}/clinics/{self.c2}/doctors").status_code == 403

    def test_changes_are_audited(self):
        self.s.put(f"{API}/clinics/{self.c1}/doctors/{self.doc}", json={"consultation_fee_paise": 100})
        self.s.delete(f"{API}/clinics/{self.c1}/doctors/{self.doc}")
        logs = self.s.get(f"{API}/audit-logs", params={"entity_type": "practitioner_clinic"}).json()["data"]
        assert {"create", "delete"} <= {x["action"] for x in logs}
