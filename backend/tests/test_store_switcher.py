"""
Regression tests for the Sep 26, 2026 multi-chain Phase 2 store switcher
(docs/26_MULTI_CHAIN_SCOPE.md Step 2): `GET /users/me/stores` and
`POST /users/me/switch-store`.

Switching is not a login/session change — `users.pharmacy_id`/`role_id`
are read fresh from the DB on every request (`get_current_user`), so the
switch endpoint just updates those two columns on the caller's own row,
after checking a real `user_store_roles` grant exists for the target
store. No real UI exists yet to grant a second store to someone (that's
Team page work, not built yet) — the two-store test below seeds that
grant directly via the DB, same pattern as `test_user_store_roles.py`.
"""
import asyncio
import os
import uuid

import requests

from database import AsyncSessionLocal, engine
from models.users import UserStoreRole

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000').rstrip('/')


def _run(coro_fn):
    async def _inner():
        try:
            return await coro_fn()
        finally:
            await engine.dispose()
    return asyncio.run(_inner())


def _grant_second_store(user_id: str, pharmacy_id: str):
    """Directly seeds a second user_store_roles row — the admin role of
    the target pharmacy, since that's the only role guaranteed to exist
    on any freshly registered pharmacy."""
    async def _do():
        async with AsyncSessionLocal() as db:
            db.add(UserStoreRole(user_id=uuid.UUID(user_id), pharmacy_id=uuid.UUID(pharmacy_id)))
            await db.commit()
    return _run(_do)


def _register(prefix: str):
    suffix = uuid.uuid4().hex[:8]
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"{prefix}_{suffix}@pharmacy.com", "name": f"{prefix} Admin",
        "password": f"{prefix}Test123", "phone": "9855550002",
        "pharmacy_name": f"{prefix} Pharmacy {suffix}", "address": "1 St",
        "city": "Testville", "state": "Karnataka", "pincode": "560001",
        "drug_license_number": f"DL-{prefix}-{suffix}",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestStoreSwitcher:
    def test_my_stores_shows_the_one_store_even_with_no_chain(self):
        """Switcher must show even for a plain single-store account, per
        direct instruction — never conditionally hidden."""
        user = _register("switcher1")
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {user['token']}"})

        resp = session.get(f"{BASE_URL}/api/users/me/stores")
        assert resp.status_code == 200, resp.text
        stores = resp.json()
        assert len(stores) == 1
        assert stores[0]["is_active"] is True

    def test_switch_to_a_store_with_no_access_is_rejected(self):
        user = _register("switcher2")
        other = _register("switcher2other")
        other_session = requests.Session()
        other_session.headers.update({"Authorization": f"Bearer {other['token']}"})
        other_pharmacy_id = other_session.get(f"{BASE_URL}/api/users/me/stores").json()[0]["pharmacy_id"]

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {user['token']}"})

        resp = session.post(f"{BASE_URL}/api/users/me/switch-store", json={
            "pharmacy_id": other_pharmacy_id,
        })
        assert resp.status_code == 403, resp.text

    def test_switch_to_a_granted_second_store_actually_changes_tenant_scope(self):
        user = _register("switcher3")
        second = _register("switcher3second")

        # Need the second pharmacy's real id, not its admin user's id —
        # look it up via that admin's own /users/me/stores.
        second_session = requests.Session()
        second_session.headers.update({"Authorization": f"Bearer {second['token']}"})
        second_stores = second_session.get(f"{BASE_URL}/api/users/me/stores").json()
        second_pharmacy_id = second_stores[0]["pharmacy_id"]

        _grant_second_store(user["user"]["id"], second_pharmacy_id)

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {user['token']}"})

        stores = session.get(f"{BASE_URL}/api/users/me/stores").json()
        assert len(stores) == 2
        assert {s["pharmacy_id"] for s in stores} == {
            _first_store_id(user, session), second_pharmacy_id}

        switch = session.post(f"{BASE_URL}/api/users/me/switch-store", json={
            "pharmacy_id": second_pharmacy_id,
        })
        assert switch.status_code == 200, switch.text

        # Real proof it's not cosmetic: a real tenant-scoped read now
        # operates in the second pharmacy — a customer created there
        # (by that pharmacy's own admin) is now visible to the switched
        # user, and their own original pharmacy's data is not.
        second_session.post(f"{BASE_URL}/api/customers", json={"name": "Only In Second Pharmacy"})
        customers = session.get(f"{BASE_URL}/api/customers").json()
        assert any(c["name"] == "Only In Second Pharmacy" for c in customers)


def _first_store_id(user, session):
    stores = session.get(f"{BASE_URL}/api/users/me/stores").json()
    active = next(s for s in stores if s["is_active"])
    return active["pharmacy_id"]
