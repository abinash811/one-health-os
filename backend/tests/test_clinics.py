"""
Clinics (docs/32_CLINICS_SCOPE.md, phase P1): EMR places are their own records, separate from pharmacies,
created and managed by whoever holds the clinics ticks (administrators always).
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
        "email": f"{tag}_{sfx}@pharmacy.com", "name": f"{tag} Admin", "password": "ClinicTest123",
        "phone": "9877720000", "pharmacy_name": f"{tag} Pharmacy {sfx}", "address": "1 St",
        "city": "Testville", "state": "Karnataka", "pincode": "560001",
        "drug_license_number": f"DL-{tag}-{sfx}"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s, sfx


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


class _Base:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s, self.sfx = _register("clinic")

    def _create(self, name=None, **extra):
        return self.s.post(f"{API}/clinics", json={"name": name or f"Clinic {uuid.uuid4().hex[:6]}", **extra})

    def _member(self, perms, tag="m"):
        role_name = f"r_{tag}_{uuid.uuid4().hex[:6]}"
        role = self.s.post(f"{API}/roles", json={"name": role_name, "display_name": role_name, "permissions": perms})
        assert role.status_code == 200, role.text
        email = f"{tag}_{uuid.uuid4().hex[:8]}@pharmacy.com"
        u = self.s.post(f"{API}/users", json={"name": "Member", "email": email, "password": "Member12345",
                                              "role": role_name})
        assert u.status_code == 200, u.text
        return _login(email, "Member12345")


class TestClinics(_Base):
    def test_create_list_edit_and_deactivate(self):
        assert self.s.get(f"{API}/clinics").json() == []
        c = self._create("Sunrise Clinic", city="Pune", pincode="411001", phone="9876543210")
        assert c.status_code == 200, c.text
        cid = c.json()["id"]
        assert c.json()["has_pharmacy"] is False
        assert [x["name"] for x in self.s.get(f"{API}/clinics").json()] == ["Sunrise Clinic"]

        up = self.s.put(f"{API}/clinics/{cid}", json={"city": "Mumbai", "email": ""})
        assert up.status_code == 200 and up.json()["city"] == "Mumbai" and up.json()["email"] is None

        off = self.s.put(f"{API}/clinics/{cid}", json={"is_active": False})
        assert off.json()["is_active"] is False
        assert self.s.get(f"{API}/clinics").json() == []
        assert len(self.s.get(f"{API}/clinics?include_inactive=true").json()) == 1
        assert self.s.get(f"{API}/clinics/{cid}").status_code == 200  # still readable, never deleted

    def test_creating_a_clinic_does_not_create_a_pharmacy(self):
        before = self.s.get(f"{API}/pharmacies/stores").json()
        self._create()
        assert self.s.get(f"{API}/pharmacies/stores").json() == before

    def test_clinics_of_one_hospital_see_each_other_through_a_second_pharmacy(self):
        self._create("First Clinic")
        store = self.s.post(f"{API}/pharmacies/stores", json={
            "name": f"Second {self.sfx}", "address": "2 St", "city": "T", "state": "K", "pincode": "560002",
            "phone": "9877720001", "drug_license_number": f"DL-C2-{self.sfx}"})
        assert store.status_code == 200, store.text
        assert [c["name"] for c in self.s.get(f"{API}/clinics").json()] == ["First Clinic"]

    def test_duplicate_name_in_the_same_hospital_is_refused_with_a_reason(self):
        self._create("Twin Clinic")
        dup = self._create("twin clinic")
        assert dup.status_code == 409 and "already exists" in dup.json()["detail"]
        other = self._create("Other Clinic").json()["id"]
        clash = self.s.put(f"{API}/clinics/{other}", json={"name": "TWIN CLINIC"})
        assert clash.status_code == 409

    def test_bad_input_says_why(self):
        r = self._create("Bad Pin", pincode="12")
        assert r.status_code == 422 and "6 digits" in r.text
        assert self._create("   ").status_code == 422

    def test_another_hospital_never_sees_or_edits_my_clinics(self):
        cid = self._create("Private Clinic").json()["id"]
        other, _ = _register("outsider")
        assert other.get(f"{API}/clinics").json() == []
        assert other.get(f"{API}/clinics/{cid}").status_code == 404
        assert other.put(f"{API}/clinics/{cid}", json={"name": "Hacked"}).status_code == 404

    def test_every_change_is_in_the_audit_log(self):
        cid = self._create("Audited Clinic").json()["id"]
        self.s.put(f"{API}/clinics/{cid}", json={"city": "Delhi"})
        logs = self.s.get(f"{API}/audit-logs", params={"entity_type": "clinic", "entity_id": cid})
        assert logs.status_code == 200, logs.text
        assert {"create", "update"} <= {r["action"] for r in logs.json()["data"]}


class TestClinicAccess(_Base):
    def test_a_role_without_the_ticks_cannot_see_create_or_edit(self):
        cid = self._create("Guarded Clinic").json()["id"]
        m = self._member(["billing:view"])
        assert m.get(f"{API}/clinics").status_code == 403
        assert m.post(f"{API}/clinics", json={"name": "Nope"}).status_code == 403
        assert m.put(f"{API}/clinics/{cid}", json={"city": "X"}).status_code == 403

    def test_view_tick_reads_but_cannot_change(self):
        cid = self._create("Readable Clinic").json()["id"]
        m = self._member(["clinics:view"])
        assert [c["name"] for c in m.get(f"{API}/clinics").json()] == ["Readable Clinic"]
        assert m.post(f"{API}/clinics", json={"name": "Nope"}).status_code == 403
        assert m.put(f"{API}/clinics/{cid}", json={"city": "X"}).status_code == 403

    def test_a_non_administrator_with_the_create_tick_can_create(self):
        m = self._member(["clinics:view", "clinics:create"])
        r = m.post(f"{API}/clinics", json={"name": "Made By Manager"})
        assert r.status_code == 200, r.text
        assert m.put(f"{API}/clinics/{r.json()['id']}", json={"city": "X"}).status_code == 403

    def test_adding_a_pharmacy_needs_its_own_tick_and_never_makes_the_creator_admin(self):
        body = {"name": f"Third {self.sfx}", "address": "3 St", "city": "T", "state": "K", "pincode": "560003",
                "phone": "9877720003", "drug_license_number": f"DL-C3-{self.sfx}"}
        denied = self._member(["clinics:create"]).post(f"{API}/pharmacies/stores", json=body)
        assert denied.status_code == 403
        m = self._member(["pharmacies:create", "billing:view"], tag="pm")
        ok = m.post(f"{API}/pharmacies/stores", json=body)
        assert ok.status_code == 200, ok.text
        mine = m.get(f"{API}/users/me/stores").json()
        new = next(x for x in mine if x["pharmacy_id"] == ok.json()["pharmacy_id"])
        assert new["role_name"] != "admin"

    def test_clinics_permissions_are_listed_for_the_roles_screen(self):
        perms = self.s.get(f"{API}/permissions").json()
        ids = {p["id"] for g in perms.values() for p in g["permissions"]}
        assert {"clinics:view", "clinics:create", "clinics:edit",
                "pharmacies:view", "pharmacies:create", "pharmacies:edit"} <= ids
