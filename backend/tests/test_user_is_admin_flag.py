"""Admin is a checkbox on the user (users.is_admin), separate from the clinical role: a Doctor can also be an
admin and gets every permission. Added Oct 3, 2026."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture()
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "testadmin@pharmacy.com", "password": "admin123"})
    if r.status_code != 200:
        pytest.skip("Authentication failed")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s, r.json()["user"]


def _create(admin, role, is_admin):
    email = f"isadmin_{uuid.uuid4().hex[:8]}@pharmacy.com"
    r = admin.post(f"{BASE_URL}/api/users", json={
        "email": email, "name": "Flag Test", "password": "FlagTest123", "role": role, "is_admin": is_admin})
    assert r.status_code == 200, r.text
    return r.json(), email


def test_existing_admin_role_user_is_flagged(admin):
    assert admin.get(f"{BASE_URL}/api/auth/me").json()["is_admin"] is True


def test_doctor_without_flag_is_not_admin(admin):
    user, email = _create(admin, "doctor", False)
    assert user["is_admin"] is False
    s, _ = _login(email, "FlagTest123")
    assert s.get(f"{BASE_URL}/api/users").status_code == 403


def test_doctor_with_flag_gets_admin_access_and_keeps_role(admin):
    user, email = _create(admin, "doctor", True)
    assert user["is_admin"] is True and user["role"] == "doctor"
    s, login_user = _login(email, "FlagTest123")
    assert login_user["role"] == "doctor" and login_user["is_admin"] is True
    assert s.get(f"{BASE_URL}/api/users").status_code == 200
    assert s.get(f"{BASE_URL}/api/auth/me").json()["is_super_admin"] is True


def test_toggle_flag_on_and_off(admin):
    user, email = _create(admin, "receptionist", False)
    r = admin.put(f"{BASE_URL}/api/users/{user['id']}", json={"is_admin": True})
    assert r.status_code == 200 and r.json()["is_admin"] is True
    r = admin.put(f"{BASE_URL}/api/users/{user['id']}", json={"is_admin": False})
    assert r.json()["is_admin"] is False
    s, _ = _login(email, "FlagTest123")
    assert s.get(f"{BASE_URL}/api/users").status_code == 403


def test_cannot_remove_own_admin(admin):
    me = admin.get(f"{BASE_URL}/api/auth/me").json()
    r = admin.put(f"{BASE_URL}/api/users/{me['id']}", json={"is_admin": False})
    assert r.status_code == 400
    assert "own admin" in r.json()["detail"]


def test_me_and_login_return_the_real_permission_list(admin):
    me = admin.get(f"{BASE_URL}/api/auth/me").json()
    assert me["permissions"] == ["*"]  # admin = everything

    user, email = _create(admin, "receptionist", False)
    s, login_user = _login(email, "FlagTest123")
    perms = login_user["permissions"]
    assert "patient_billing:collect" in perms and "patient_billing:void" not in perms
    assert perms == s.get(f"{BASE_URL}/api/auth/me").json()["permissions"]


def test_ticking_a_permission_shows_up_in_me(admin):
    role = admin.post(f"{BASE_URL}/api/roles", json={
        "name": f"billtest_{uuid.uuid4().hex[:6]}", "display_name": "Bill test",
        "permissions": ["patient_billing:view", "patient_billing:collect"]}).json()
    _, email = _create(admin, role["name"], False)
    s, _ = _login(email, "FlagTest123")
    assert s.get(f"{BASE_URL}/api/auth/me").json()["permissions"] == ["patient_billing:collect", "patient_billing:view"]


def test_same_email_at_two_pharmacies_can_still_log_in(admin):
    """The same email can exist at two pharmacies; login used to 500 ("Multiple rows were found")."""
    email = f"dup_{uuid.uuid4().hex[:8]}@pharmacy.com"
    first = admin.post(f"{BASE_URL}/api/users", json={
        "email": email, "name": "Dup One", "password": "DupOne1234", "role": "cashier"})
    assert first.status_code == 200, first.text

    # a second, separate pharmacy registers its own admin, then adds the same email there
    other_email = f"other_{uuid.uuid4().hex[:8]}@pharmacy.com"
    reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": other_email, "name": "Other Admin", "password": "OtherAdmin1", "phone": "9000000002",
        "pharmacy_name": "Other Pharmacy", "address": "1 Test Road", "city": "Pune", "state": "MH",
        "pincode": "411001"})
    assert reg.status_code == 200, reg.text
    other = requests.Session()
    other.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {reg.json()['token']}"})
    second = other.post(f"{BASE_URL}/api/users", json={
        "email": email, "name": "Dup Two", "password": "DupTwo5678", "role": "cashier"})
    assert second.status_code == 200, second.text

    for pw, name in (("DupOne1234", "Dup One"), ("DupTwo5678", "Dup Two")):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["name"] == name
    bad = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401
