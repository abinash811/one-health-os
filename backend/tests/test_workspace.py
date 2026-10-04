"""
Workspace (docs/33_WORKSPACE_SCOPE.md, W1+W2): every pharmacy lives in a workspace (the hospital); every
login, role and clinic belongs to one. Places added later join the same workspace.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"


def _register(tag):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    sfx = uuid.uuid4().hex[:8]
    r = s.post(f"{API}/auth/register", json={
        "email": f"{tag}_{sfx}@pharmacy.com", "name": f"{tag} Admin", "password": "Workspace123",
        "phone": "9877730000", "pharmacy_name": f"{tag} Pharmacy {sfx}", "address": "1 St",
        "city": "Testville", "state": "Karnataka", "pincode": "560001",
        "drug_license_number": f"DL-{tag}-{sfx}"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s, sfx


def _me(s):
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 200, r.text
    return r.json()


class TestWorkspace:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s, self.sfx = _register("ws")

    def _add_pharmacy(self):
        r = self.s.post(f"{API}/pharmacies/stores", json={
            "name": f"Second {self.sfx}", "address": "2 St", "city": "T", "state": "K", "pincode": "560002",
            "phone": "9877730001", "drug_license_number": f"DL-WS2-{self.sfx}"})
        assert r.status_code == 200, r.text
        return r.json()

    def test_signing_up_forms_a_workspace_named_after_the_pharmacy(self):
        ws = _me(self.s)["workspace"]
        assert ws and ws["id"] and ws["name"].startswith("ws Pharmacy")

    def test_two_signups_are_two_separate_workspaces(self):
        other, _ = _register("ws2")
        assert _me(other)["workspace"]["id"] != _me(self.s)["workspace"]["id"]

    def test_adding_a_pharmacy_joins_the_same_workspace(self):
        before = _me(self.s)["workspace"]["id"]
        store = self._add_pharmacy()
        assert store["chain_id"] == before
        assert _me(self.s)["workspace"]["id"] == before

    def test_a_clinic_joins_the_same_workspace_without_forming_a_new_one(self):
        before = _me(self.s)["workspace"]["id"]
        assert self.s.post(f"{API}/clinics", json={"name": "WS Clinic"}).status_code == 200
        assert _me(self.s)["workspace"]["id"] == before

    def test_team_members_belong_to_the_creators_workspace(self):
        email = f"mem_{self.sfx}@pharmacy.com"
        r = self.s.post(f"{API}/users", json={"name": "Member", "email": email, "password": "Member12345",
                                              "role": "cashier"})
        assert r.status_code == 200, r.text
        m = requests.Session()
        m.headers.update({"Content-Type": "application/json"})
        login = m.post(f"{API}/auth/login", json={"email": email, "password": "Member12345"})
        m.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        assert _me(m)["workspace"]["id"] == _me(self.s)["workspace"]["id"]

    def test_the_first_pharmacy_and_its_roles_are_in_the_workspace(self):
        stores = self.s.get(f"{API}/pharmacies/stores").json()
        assert len(stores) == 1
        names = {r["name"] for r in self.s.get(f"{API}/roles").json()}
        assert {"admin", "cashier"} <= names
        self._add_pharmacy()
        assert {r["name"] for r in self.s.get(f"{API}/roles").json()} == names

    def test_another_workspace_never_sees_my_people_or_roles(self):
        other, _ = _register("ws3")
        mine = {u["email"] for u in self.s.get(f"{API}/users").json()}
        theirs = {u["email"] for u in other.get(f"{API}/users").json()}
        assert mine and theirs and not (mine & theirs)
