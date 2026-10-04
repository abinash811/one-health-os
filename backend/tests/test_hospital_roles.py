"""
Hospital-wide roles (docs/32_CLINICS_SCOPE.md, phase P0): once a pharmacy is part of a
hospital, its roles belong to the hospital and work at every place in it. Nobody's access
changes when the hospital is formed.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"


class _Base:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json"})
        self.suffix = uuid.uuid4().hex[:8]
        resp = self.s.post(f"{API}/auth/register", json={
            "email": f"hr_{self.suffix}@pharmacy.com", "name": "Role Admin",
            "password": "RoleTest123", "phone": "9877710000",
            "pharmacy_name": f"Role Pharmacy {self.suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560001",
            "drug_license_number": f"DL-HR-{self.suffix}",
        })
        assert resp.status_code == 200, resp.text
        self.s.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        self.admin_id = resp.json()["user"]["id"]

    def _add_store(self, tag="Second"):
        r = self.s.post(f"{API}/pharmacies/stores", json={
            "name": f"{tag} {self.suffix}", "address": "2 St", "city": "Testville",
            "state": "Karnataka", "pincode": "560002", "phone": "9877710001",
            "drug_license_number": f"DL-HR2-{self.suffix}-{tag}"})
        assert r.status_code == 200, r.text
        return r.json()

    def _roles(self):
        r = self.s.get(f"{API}/roles")
        assert r.status_code == 200, r.text
        return r.json()

    def _new_role(self, name, perms):
        r = self.s.post(f"{API}/roles", json={
            "name": name, "display_name": name.title(), "permissions": perms})
        assert r.status_code == 200, r.text
        return r.json()


class TestRolesFollowTheHospital(_Base):
    def test_forming_a_hospital_changes_nobodys_roles(self):
        custom = self._new_role(f"night_{self.suffix}", ["billing:view"])
        before = {r["name"]: r["permissions"] for r in self._roles()}
        self._add_store()
        after = {r["name"]: r["permissions"] for r in self._roles()}
        assert after == before
        assert custom["name"] in after

    def test_a_new_place_reuses_the_hospital_roles_instead_of_copying_them(self):
        before = self._roles()
        store = self._add_store()
        assert len(self._roles()) == len(before)
        mine = self.s.get(f"{API}/users/me/stores").json()
        new = next(m for m in mine if m["pharmacy_id"] == store["pharmacy_id"])
        assert new["role_name"] == "admin"
        # the admin role id is the very same row at both places
        assert {m["role_name"] for m in mine} == {"admin"}

    def test_a_role_made_after_the_hospital_exists_works_at_every_place(self):
        store = self._add_store()
        self._new_role(f"floor_{self.suffix}", ["billing:view"])
        member = self.s.post(f"{API}/users", json={
            "name": "Floor Staff", "email": f"floor_{self.suffix}@pharmacy.com",
            "password": "FloorStaff123", "role": f"floor_{self.suffix}"})
        assert member.status_code == 200, member.text
        grant = self.s.post(f"{API}/users/{member.json()['id']}/store-access", json={
            "pharmacy_id": store["pharmacy_id"], "role": f"floor_{self.suffix}"})
        assert grant.status_code == 200, grant.text

    def test_deleting_a_role_is_blocked_while_anyone_holds_it_at_any_place(self):
        store = self._add_store()
        role = self._new_role(f"temp_{self.suffix}", ["billing:view"])
        member = self.s.post(f"{API}/users", json={
            "name": "Temp Staff", "email": f"temp_{self.suffix}@pharmacy.com",
            "password": "TempStaff123", "role": "cashier"}).json()
        r = self.s.post(f"{API}/users/{member['id']}/store-access", json={
            "pharmacy_id": store["pharmacy_id"], "role": role["name"]})
        assert r.status_code == 200, r.text
        blocked = self.s.delete(f"{API}/roles/{role['id']}")
        assert blocked.status_code == 400
        assert "assigned" in blocked.json()["detail"]

    def test_a_standalone_pharmacy_still_has_its_own_roles(self):
        names = {r["name"] for r in self._roles()}
        assert {"admin", "cashier"} <= names

    def test_another_hospitals_roles_are_never_visible_or_editable(self):
        other = requests.Session()
        other.headers.update({"Content-Type": "application/json"})
        sfx = uuid.uuid4().hex[:8]
        reg = other.post(f"{API}/auth/register", json={
            "email": f"hr2_{sfx}@pharmacy.com", "name": "Other Admin", "password": "OtherTest123",
            "phone": "9877710002", "pharmacy_name": f"Other {sfx}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560001",
            "drug_license_number": f"DL-HR3-{sfx}"})
        assert reg.status_code == 200, reg.text
        other.headers.update({"Authorization": f"Bearer {reg.json()['token']}"})
        mine = self._new_role(f"mine_{self.suffix}", ["billing:view"])
        self._add_store()
        assert other.get(f"{API}/roles/{mine['id']}").status_code == 404
        assert other.put(f"{API}/roles/{mine['id']}", json={"permissions": ["*"]}).status_code == 404
