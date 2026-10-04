"""
Doctors as their own records (docs/31_CORE_DOCTOR_SCOPE.md, phase 1): Settings → Organisation → Doctors.

A doctor is a profile owned by the hospital and mapped to clinics (fee per clinic, integer paise) — NOT a
login; a login can optionally be linked. HTTP integration tests against the isolated backend. Each test
registers its own brand-new pharmacy so chain/store state never leaks between tests.

P0 behaviours: permission per role, tenant isolation, clinic access from real grants, one login → one doctor,
soft delete, audit trail.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API = f"{BASE_URL}/api"


def _session(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def _register(tag):
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/auth/register", json={
        "email": f"{tag}_{suffix}@pharmacy.com", "name": f"{tag} Admin", "password": "DocTest123",
        "phone": "9877700001", "pharmacy_name": f"{tag} Pharmacy {suffix}", "address": "1 St",
        "city": "Pune", "state": "MH", "pincode": "411001"})
    assert r.status_code == 200, r.text
    s = _session(r.json()["token"])
    made = s.post(f"{API}/clinics", json={"name": f"{tag} Clinic {suffix}"})   # EMR belongs to a clinic
    assert made.status_code == 200, made.text
    return s


def _my_clinic(session):
    return next(c["clinic_id"] for c in session.get(f"{API}/users/me/clinics").json() if c["is_active"])


def _member(admin, role):
    email = f"{role}_{uuid.uuid4().hex[:8]}@pharmacy.com"
    r = admin.post(f"{API}/users", json={"email": email, "name": f"{role} member", "password": "DocTest123",
                                         "role": role})
    assert r.status_code == 200, r.text
    lg = requests.post(f"{API}/auth/login", json={"email": email, "password": "DocTest123"})
    assert lg.status_code == 200, lg.text
    return r.json()["id"], _session(lg.json()["token"])


@pytest.fixture()
def admin():
    return _register("doc")


def _create(admin, **body):
    body.setdefault("name", f"Dr Test {uuid.uuid4().hex[:5]}")
    r = admin.post(f"{API}/practitioners", json=body)
    assert r.status_code == 200, r.text
    return r.json()


class TestCreateAndRead:
    def test_minimal_doctor_is_mapped_to_my_clinic(self, admin):
        clinic = _my_clinic(admin)
        d = _create(admin, name="Dr Rao")
        assert d["name"] == "Dr Rao" and d["is_active"] is True and d["is_external"] is False
        assert d["user_id"] is None
        assert [c["clinic_id"] for c in d["clinics"]] == [clinic]
        assert d["clinics"][0]["consultation_fee_paise"] is None
        assert [x["id"] for x in admin.get(f"{API}/practitioners").json()] == [d["id"]]
        assert admin.get(f"{API}/practitioners/{d['id']}").json()["name"] == "Dr Rao"

    def test_full_profile_with_fee_in_paise_and_blank_text_is_cleaned(self, admin):
        clinic = _my_clinic(admin)
        d = _create(admin, name="  Dr Iyer  ", specialty="  Cardiology ", qualification="MD", registration_no="MH-123",
                    phone="9000000001", email="iyer@clinic.com", notes="   ",
                    clinics=[{"clinic_id": clinic, "consultation_fee_paise": 50000}])
        assert d["name"] == "Dr Iyer" and d["specialty"] == "Cardiology" and d["notes"] is None
        assert d["clinics"][0]["consultation_fee_paise"] == 50000

    def test_validation(self, admin):
        for bad in ({"name": "   "}, {"name": ""}, {"name": "X", "email": "nope"}, {"name": "X", "phone": "1" * 11},
                    {"name": "X", "clinics": [{"clinic_id": _my_clinic(admin), "consultation_fee_paise": -1}]}):
            assert admin.post(f"{API}/practitioners", json=bad).status_code == 422, bad

    def test_external_doctor_is_the_same_record_with_a_flag(self, admin):
        d = _create(admin, name="Dr Visiting", is_external=True, hospital="City Hospital")
        assert d["is_external"] is True and d["hospital"] == "City Hospital"


class TestUpdateDeactivateDelete:
    def test_update_profile_fee_and_clinics(self, admin):
        clinic = _my_clinic(admin)
        d = _create(admin, name="Dr A")
        r = admin.put(f"{API}/practitioners/{d['id']}", json={
            "specialty": "ENT", "clinics": [{"clinic_id": clinic, "consultation_fee_paise": 30000}]})
        assert r.status_code == 200, r.text
        assert r.json()["specialty"] == "ENT" and r.json()["clinics"][0]["consultation_fee_paise"] == 30000
        again = admin.put(f"{API}/practitioners/{d['id']}", json={"name": "Dr A Prime"}).json()
        assert again["name"] == "Dr A Prime" and again["clinics"][0]["consultation_fee_paise"] == 30000

    def test_name_cannot_be_blanked(self, admin):
        d = _create(admin, name="Dr B")
        assert admin.put(f"{API}/practitioners/{d['id']}", json={"name": "  "}).status_code == 422

    def test_deactivate_hides_from_default_list_but_not_from_include_inactive(self, admin):
        d = _create(admin, name="Dr C")
        assert admin.put(f"{API}/practitioners/{d['id']}", json={"is_active": False}).status_code == 200
        assert admin.get(f"{API}/practitioners").json() == []
        listed = admin.get(f"{API}/practitioners", params={"include_inactive": True}).json()
        assert [x["id"] for x in listed] == [d["id"]]

    def test_delete_is_soft_and_releases_the_login(self, admin):
        user_id, _ = _member(admin, "receptionist")
        d = _create(admin, name="Dr D", user_id=user_id)
        assert admin.delete(f"{API}/practitioners/{d['id']}").status_code == 200
        assert admin.get(f"{API}/practitioners/{d['id']}").status_code == 404
        assert admin.get(f"{API}/practitioners", params={"include_inactive": True}).json() == []
        # the login is free to be linked to a new doctor profile
        assert _create(admin, name="Dr D2", user_id=user_id)["user_id"] == user_id

    def test_unknown_or_malformed_id_is_404(self, admin):
        assert admin.get(f"{API}/practitioners/{uuid.uuid4()}").status_code == 404
        assert admin.get(f"{API}/practitioners/not-a-uuid").status_code == 404
        assert admin.put(f"{API}/practitioners/{uuid.uuid4()}", json={"name": "X"}).status_code == 404


class TestPermissions:
    def test_receptionist_can_view_but_not_change(self, admin):
        d = _create(admin, name="Dr E")
        _, rec = _member(admin, "receptionist")
        assert [x["id"] for x in rec.get(f"{API}/practitioners").json()] == [d["id"]]
        assert rec.get(f"{API}/practitioners/{d['id']}").status_code == 200
        assert rec.post(f"{API}/practitioners", json={"name": "Dr Nope"}).status_code == 403
        assert rec.put(f"{API}/practitioners/{d['id']}", json={"specialty": "x"}).status_code == 403
        assert rec.delete(f"{API}/practitioners/{d['id']}").status_code == 403
        assert rec.get(f"{API}/practitioners/linkable-users").status_code == 403

    def test_cashier_has_no_access_at_all(self, admin):
        _, cashier = _member(admin, "cashier")
        assert cashier.get(f"{API}/practitioners").status_code == 403

    def test_a_doctor_login_can_view_the_list(self, admin):
        d = _create(admin, name="Dr F")
        _, doc = _member(admin, "doctor")
        assert [x["id"] for x in doc.get(f"{API}/practitioners").json()] == [d["id"]]

    def test_login_permissions_list_carries_the_new_ticks(self, admin):
        _, rec = _member(admin, "receptionist")
        perms = rec.get(f"{API}/auth/me").json()["permissions"]
        assert "doctors:view" in perms and "doctors:edit" not in perms


class TestTenantIsolation:
    def test_another_pharmacy_cannot_see_or_touch_a_doctor(self, admin):
        d = _create(admin, name="Dr G")
        other = _register("other")
        assert other.get(f"{API}/practitioners").json() == []
        assert other.get(f"{API}/practitioners/{d['id']}").status_code == 404
        assert other.put(f"{API}/practitioners/{d['id']}", json={"name": "Hacked"}).status_code == 404
        assert other.delete(f"{API}/practitioners/{d['id']}").status_code == 404
        assert admin.get(f"{API}/practitioners/{d['id']}").json()["name"] == "Dr G"

    def test_cannot_map_a_doctor_to_someone_elses_clinic(self, admin):
        other_clinic = _my_clinic(_register("other"))
        r = admin.post(f"{API}/practitioners", json={"name": "Dr H", "clinics": [{"clinic_id": other_clinic}]})
        assert r.status_code == 403
        d = _create(admin, name="Dr H2")
        r = admin.put(f"{API}/practitioners/{d['id']}", json={"clinics": [{"clinic_id": other_clinic}]})
        assert r.status_code == 403
        assert admin.get(f"{API}/practitioners", params={"clinic_id": other_clinic}).status_code == 403

    def test_cannot_link_a_login_from_another_pharmacy(self, admin):
        other = _register("other")
        other_user = other.get(f"{API}/auth/me").json()["id"]
        r = admin.post(f"{API}/practitioners", json={"name": "Dr I", "user_id": other_user})
        assert r.status_code == 404


class TestLoginLink:
    def test_one_login_links_to_one_doctor(self, admin):
        user_id, _ = _member(admin, "doctor")
        first = _create(admin, name="Dr J", user_id=user_id)
        assert first["user_id"] == user_id and first["user_email"].startswith("doctor_")
        r = admin.post(f"{API}/practitioners", json={"name": "Dr J2", "user_id": user_id})
        assert r.status_code == 409 and "Dr J" in r.json()["detail"]

    def test_linkable_users_excludes_linked_and_unlink_with_null(self, admin):
        user_id, _ = _member(admin, "doctor")
        before = [u["id"] for u in admin.get(f"{API}/practitioners/linkable-users").json()]
        assert user_id in before
        d = _create(admin, name="Dr K", user_id=user_id)
        assert user_id not in [u["id"] for u in admin.get(f"{API}/practitioners/linkable-users").json()]
        r = admin.put(f"{API}/practitioners/{d['id']}", json={"user_id": None})
        assert r.status_code == 200 and r.json()["user_id"] is None
        assert user_id in [u["id"] for u in admin.get(f"{API}/practitioners/linkable-users").json()]

    def test_relinking_the_same_login_to_the_same_doctor_is_fine(self, admin):
        user_id, _ = _member(admin, "doctor")
        d = _create(admin, name="Dr L", user_id=user_id)
        assert admin.put(f"{API}/practitioners/{d['id']}", json={"user_id": user_id}).status_code == 200


class TestMultipleClinics:
    def _add_store(self, admin):
        r = admin.post(f"{API}/clinics", json={"name": f"Branch {uuid.uuid4().hex[:5]}", "city": "Mumbai"})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_one_doctor_at_two_clinics_with_a_fee_each(self, admin):
        home = _my_clinic(admin)
        branch = self._add_store(admin)
        d = _create(admin, name="Dr M", clinics=[
            {"clinic_id": home, "consultation_fee_paise": 40000},
            {"clinic_id": branch, "consultation_fee_paise": 60000}])
        fees = {c["clinic_id"]: c["consultation_fee_paise"] for c in d["clinics"]}
        assert fees == {home: 40000, branch: 60000}
        assert [x["id"] for x in admin.get(f"{API}/practitioners", params={"clinic_id": branch}).json()] == [d["id"]]
        assert [x["id"] for x in admin.get(f"{API}/practitioners", params={"clinic_id": home}).json()] == [d["id"]]

    def test_removing_a_clinic_unmaps_the_doctor_there_only(self, admin):
        home = _my_clinic(admin)
        branch = self._add_store(admin)
        d = _create(admin, name="Dr N", clinics=[{"clinic_id": home}, {"clinic_id": branch}])
        r = admin.put(f"{API}/practitioners/{d['id']}", json={"clinics": [{"clinic_id": home}]})
        assert [c["clinic_id"] for c in r.json()["clinics"]] == [home]
        assert admin.get(f"{API}/practitioners", params={"clinic_id": branch}).json() == []
        # and can be mapped back
        r = admin.put(f"{API}/practitioners/{d['id']}", json={"clinics": [
            {"clinic_id": home}, {"clinic_id": branch, "consultation_fee_paise": 1000}]})
        assert {c["clinic_id"] for c in r.json()["clinics"]} == {home, branch}

    def test_a_clinic_listed_twice_is_rejected(self, admin):
        home = _my_clinic(admin)
        r = admin.post(f"{API}/practitioners", json={"name": "Dr O", "clinics": [
            {"clinic_id": home}, {"clinic_id": home}]})
        assert r.status_code == 422


class TestAudit:
    def test_create_update_delete_leave_an_audit_trail(self, admin):
        d = _create(admin, name="Dr P")
        admin.put(f"{API}/practitioners/{d['id']}", json={"specialty": "Skin"})
        admin.delete(f"{API}/practitioners/{d['id']}")
        r = admin.get(f"{API}/audit-logs", params={"entity_type": "practitioner", "page_size": 50})
        assert r.status_code == 200, r.text
        rows = r.json().get("data", r.json())
        actions = sorted(x["action"] for x in rows if x.get("entity_id") == d["id"])
        assert actions == ["create", "delete", "update"]
