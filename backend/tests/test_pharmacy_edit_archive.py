"""
Pharmacies under Settings → Organisation: edit details, archive and restore (Oct 4, 2026). Archiving is soft;
an archived pharmacy drops out of every picker, nobody is left working in it, and unfinished work blocks it.
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
        "email": f"{tag}_{sfx}@pharmacy.com", "name": f"{tag} Admin", "password": "PharmEdit123",
        "phone": "9877760000", "pharmacy_name": f"{tag} Pharmacy {sfx}", "address": "1 St", "city": "T",
        "state": "K", "pincode": "560001", "drug_license_number": f"DL-{tag}-{sfx}"})
    assert r.status_code == 200, r.text
    return _session(r.json()["token"]), sfx


class TestPharmacyEditArchive:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.s, self.sfx = _register("pe")
        stores = self.s.get(f"{API}/pharmacies/stores").json()
        self.a = stores[0]["pharmacy_id"]
        r = self.s.post(f"{API}/pharmacies/stores", json={
            "name": f"Branch {self.sfx}", "address": "2 St", "city": "Mumbai", "state": "MH", "pincode": "400001",
            "phone": "9877760001", "drug_license_number": f"DL-PEB-{self.sfx}"})
        assert r.status_code == 200, r.text
        self.b = r.json()["pharmacy_id"]

    def _put(self, pid, body, session=None):
        return (session or self.s).put(f"{API}/pharmacies/stores/{pid}", json=body)

    def test_list_carries_the_details_needed_to_edit(self):
        row = next(x for x in self.s.get(f"{API}/pharmacies/stores").json() if x["pharmacy_id"] == self.b)
        assert row["address"] == "2 St" and row["is_active"] is True and row["gstin"] is None

    def test_edit_details(self):
        r = self._put(self.b, {"name": "Branch Renamed", "city": "Pune", "gstin": "29abcde1234f1z5", "email": ""})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Branch Renamed" and r.json()["gstin"] == "29ABCDE1234F1Z5"
        assert r.json()["email"] == ""
        listed = {x["pharmacy_id"]: x for x in self.s.get(f"{API}/pharmacies/stores").json()}
        assert listed[self.b]["city"] == "Pune"

    def test_bad_input_says_why(self):
        assert "6 digits" in self._put(self.b, {"pincode": "12"}).text
        assert self._put(self.b, {"name": "  "}).status_code == 422

    def test_archive_hides_it_everywhere_and_restore_brings_it_back(self):
        assert self._put(self.b, {"is_active": False}).status_code == 200
        assert self.b not in {x["pharmacy_id"] for x in self.s.get(f"{API}/pharmacies/stores").json()}
        assert self.b not in {x["pharmacy_id"] for x in self.s.get(f"{API}/users/me/stores").json()}
        shown = self.s.get(f"{API}/pharmacies/stores", params={"include_archived": "true"}).json()
        assert next(x for x in shown if x["pharmacy_id"] == self.b)["is_active"] is False
        assert self._put(self.b, {"is_active": True}).status_code == 200
        assert self.b in {x["pharmacy_id"] for x in self.s.get(f"{API}/pharmacies/stores").json()}

    def test_cannot_switch_to_or_transfer_to_an_archived_pharmacy(self):
        self._put(self.b, {"is_active": False})
        sw = self.s.post(f"{API}/users/me/switch-store", json={"pharmacy_id": self.b})
        assert sw.status_code == 409 and "archived" in sw.json()["detail"]
        tr = self.s.post(f"{API}/stock-transfers", json={"destination_pharmacy_id": self.b, "items": [
            {"product_sku": "NOPE", "batch_number": "B1", "quantity": 1}]})
        assert tr.status_code == 409 and "archived" in tr.json()["detail"]

    def test_the_last_active_pharmacy_cannot_be_archived(self):
        assert self._put(self.b, {"is_active": False}).status_code == 200
        r = self._put(self.a, {"is_active": False})
        assert r.status_code == 409 and "only active pharmacy" in r.json()["detail"]

    def test_people_working_there_are_moved_to_another_pharmacy(self):
        self.s.post(f"{API}/users/me/switch-store", json={"pharmacy_id": self.b})
        assert self._put(self.b, {"is_active": False}).status_code == 200
        active = [x["pharmacy_id"] for x in self.s.get(f"{API}/users/me/stores").json() if x["is_active"]]
        assert active == [self.a]

    def test_someone_who_can_open_no_other_pharmacy_blocks_it(self):
        email = f"only_{self.sfx}@pharmacy.com"
        uid = self.s.post(f"{API}/users", json={"name": "Only", "email": email, "password": "Member12345",
                                                "role": "cashier"}).json()["id"]
        # grant at B, then move their home to B by revoking A is not possible; simply grant B and make B their home
        self.s.post(f"{API}/users/{uid}/store-access", json={"pharmacy_id": self.b, "role": "cashier"})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Member12345"}).json()["token"]
        m = _session(tok)
        m.post(f"{API}/users/me/switch-store", json={"pharmacy_id": self.b})
        self.s.delete(f"{API}/users/{uid}/store-access/{self.a}")
        r = self._put(self.b, {"is_active": False})
        assert r.status_code == 409 and "can open no other pharmacy" in r.json()["detail"]

    def test_permissions_and_isolation(self):
        role = f"pv_{uuid.uuid4().hex[:6]}"
        self.s.post(f"{API}/roles", json={"name": role, "display_name": role, "permissions": ["pharmacies:view"]})
        email = f"{role}@pharmacy.com"
        self.s.post(f"{API}/users", json={"name": "V", "email": email, "password": "Viewer12345", "role": role})
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "Viewer12345"}).json()["token"]
        assert self._put(self.b, {"city": "X"}, _session(tok)).status_code == 403
        other, _ = _register("peo")
        assert self._put(self.b, {"city": "Hacked"}, other).status_code == 404

    def test_changes_are_audited(self):
        self._put(self.b, {"city": "Nashik"})
        self._put(self.b, {"is_active": False})
        logs = self.s.get(f"{API}/audit-logs", params={"entity_type": "store", "entity_id": self.b}).json()["data"]
        assert {"update", "archive"} <= {x["action"] for x in logs}
