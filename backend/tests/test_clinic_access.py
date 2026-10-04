"""
Clinic access (docs/32_CLINICS_SCOPE.md P2a): which clinics a login can open, the clinic they are working at,
and the admin endpoints to grant / revoke. The creator of a clinic can open it straight away.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"


def _session(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


class TestClinicAccess:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json"})
        self.sfx = uuid.uuid4().hex[:8]
        r = self.s.post(f"{API}/auth/register", json={
            "email": f"ca_{self.sfx}@pharmacy.com", "name": "CA Admin", "password": "ClinicAcc123",
            "phone": "9877740000", "pharmacy_name": f"CA Pharmacy {self.sfx}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560001",
            "drug_license_number": f"DL-CA-{self.sfx}"})
        assert r.status_code == 200, r.text
        self.s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})

    def _clinic(self, name):
        r = self.s.post(f"{API}/clinics", json={"name": name})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def _member(self, tag, role="receptionist"):
        email = f"{tag}_{self.sfx}@pharmacy.com"
        r = self.s.post(f"{API}/users", json={"name": tag, "email": email, "password": "Member12345", "role": role})
        assert r.status_code == 200, r.text
        return r.json()["id"], email

    def test_a_clinic_creator_can_open_it_and_it_becomes_their_active_clinic(self):
        cid = self._clinic("First Clinic")
        mine = self.s.get(f"{API}/users/me/clinics").json()
        assert [(c["clinic_id"], c["is_active"]) for c in mine] == [(cid, True)]

    def test_a_second_clinic_does_not_steal_the_active_one(self):
        first = self._clinic("First Clinic")
        second = self._clinic("Second Clinic")
        active = {c["clinic_id"]: c["is_active"] for c in self.s.get(f"{API}/users/me/clinics").json()}
        assert active == {first: True, second: False}

    def test_switching_makes_another_clinic_active(self):
        self._clinic("First Clinic")
        second = self._clinic("Second Clinic")
        r = self.s.post(f"{API}/users/me/switch-clinic", json={"clinic_id": second})
        assert r.status_code == 200, r.text
        active = [c["clinic_id"] for c in self.s.get(f"{API}/users/me/clinics").json() if c["is_active"]]
        assert active == [second]

    def test_cannot_switch_to_a_clinic_without_access(self):
        cid = self._clinic("Private Clinic")
        _, email = self._member("nope")
        m = _session(email, "Member12345")
        denied = m.post(f"{API}/users/me/switch-clinic", json={"clinic_id": cid})
        assert denied.status_code == 403
        assert m.get(f"{API}/users/me/clinics").json() == []

    def test_admin_grants_access_with_a_role_and_the_first_grant_activates(self):
        cid = self._clinic("Granted Clinic")
        uid, email = self._member("grantee")
        g = self.s.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": cid, "role": "receptionist"})
        assert g.status_code == 200, g.text
        listed = self.s.get(f"{API}/users/{uid}/clinic-access").json()
        assert [(x["clinic_id"], x["role_name"]) for x in listed] == [(cid, "receptionist")]
        m = _session(email, "Member12345")
        assert [c["is_active"] for c in m.get(f"{API}/users/me/clinics").json()] == [True]

    def test_revoking_moves_the_active_clinic_or_clears_it(self):
        c1 = self._clinic("Clinic One")
        uid, email = self._member("revokee")
        self.s.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": c1, "role": "receptionist"})
        assert self.s.delete(f"{API}/users/{uid}/clinic-access/{c1}").status_code == 200
        m = _session(email, "Member12345")
        assert m.get(f"{API}/users/me/clinics").json() == []
        assert self.s.delete(f"{API}/users/{uid}/clinic-access/{c1}").status_code == 404

    def test_only_administrators_grant_and_only_inside_the_workspace(self):
        cid = self._clinic("Workspace Clinic")
        uid, email = self._member("plain", role="cashier")
        m = _session(email, "Member12345")
        denied = m.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": cid, "role": "cashier"})
        assert denied.status_code == 403
        other = requests.Session()
        other.headers.update({"Content-Type": "application/json"})
        sfx = uuid.uuid4().hex[:8]
        reg = other.post(f"{API}/auth/register", json={
            "email": f"cb_{sfx}@pharmacy.com", "name": "Other", "password": "OtherAdmin123", "phone": "9877740001",
            "pharmacy_name": f"Other {sfx}", "address": "1 St", "city": "T", "state": "K", "pincode": "560001",
            "drug_license_number": f"DL-CB-{sfx}"})
        other.headers.update({"Authorization": f"Bearer {reg.json()['token']}"})
        cross = other.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": cid, "role": "admin"})
        assert cross.status_code == 404
        mine = other.post(f"{API}/clinics", json={"name": "Theirs"}).json()["id"]
        back = self.s.post(f"{API}/users/{uid}/clinic-access", json={"clinic_id": mine, "role": "cashier"})
        assert back.status_code == 404

    def test_a_deactivated_clinic_disappears_from_the_switcher(self):
        cid = self._clinic("Closing Clinic")
        self.s.put(f"{API}/clinics/{cid}", json={"is_active": False})
        assert self.s.get(f"{API}/users/me/clinics").json() == []
