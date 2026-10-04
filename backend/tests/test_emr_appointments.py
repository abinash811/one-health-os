"""
EMR step 1 (docs/28_EMR_SCOPE.md): patients, doctor schedules, appointments
and the live queue. HTTP integration tests against the isolated backend
(backend/run_isolated_tests.sh), same style as the rest of this suite.

P0 behaviours covered: tenant isolation of patient/appointment records,
permission enforcement per role, no double-booking, per-doctor/day token
numbering, the appointment status machine, and soft deletes.
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


def _clinic_for_token(token: str, name="Other Clinic"):
    """Give a freshly registered admin (identified by token) a clinic of their own."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return _ensure_clinic(s, name)


def _next_weekday_date(weekday: int) -> date:
    """The first date at least 7 days ahead that falls on `weekday` (Mon=0)."""
    d = date.today() + timedelta(days=7)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def _ensure_clinic(session, name="Test Clinic"):
    """The id of the clinic this login is working at — created (and made active) if they have none yet.
    EMR belongs to a clinic (docs/32 P2b), so every EMR test needs one."""
    mine = session.get(f"{BASE_URL}/api/users/me/clinics").json()
    active = [c["clinic_id"] for c in mine if c["is_active"]]
    if active:
        return active[0]
    r = session.post(f"{BASE_URL}/api/clinics", json={"name": f"{name} {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


class _EmrBase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testadmin@pharmacy.com", "password": "admin123"})
        if login.status_code != 200:
            pytest.skip("Authentication failed - skipping EMR tests")
        self.session.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        _ensure_clinic(self.session)

    # ── helpers ──
    def _user(self, role):
        email = f"emr_{role}_{uuid.uuid4().hex[:8]}@pharmacy.com"
        resp = self.session.post(f"{BASE_URL}/api/users", json={
            "email": email, "name": f"EMR {role} {self.suffix}", "password": "EmrTest123", "role": role})
        assert resp.status_code == 200, resp.text
        grant = self.session.post(f"{BASE_URL}/api/users/{resp.json()['id']}/clinic-access", json={
            "clinic_id": self._clinic_id(), "role": role})
        assert grant.status_code == 200, grant.text
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        lg = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "EmrTest123"})
        assert lg.status_code == 200, lg.text
        s.headers.update({"Authorization": f"Bearer {lg.json()['token']}"})
        return resp.json()["id"], s

    def _patient(self, session=None, **extra):
        body = {"name": f"EMRTEST Patient {uuid.uuid4().hex[:6]}", "phone": "9000000001", **extra}
        resp = (session or self.session).post(f"{BASE_URL}/api/emr/patients", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _clinic_id(self):
        return _ensure_clinic(self.session)

    def _doctor(self, fee_paise=None, session=None, clinic_id=None, **extra):
        """A doctor profile (not a login) mapped to this clinic — docs/31_CORE_DOCTOR_SCOPE.md."""
        s = session or self.session
        clinic = clinic_id or self._clinic_id()
        r = s.post(f"{BASE_URL}/api/practitioners", json={
            "name": f"Dr Test {uuid.uuid4().hex[:6]}",
            "clinics": [{"clinic_id": clinic, "consultation_fee_paise": fee_paise}], **extra})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def _doctor_with_schedule(self, weekday, start="09:00", end="10:00", slot=30):
        doctor_id = self._doctor()
        resp = self.session.post(f"{BASE_URL}/api/emr/schedules", json={
            "doctor_id": doctor_id, "weekday": weekday,
            "start_time": start, "end_time": end, "slot_minutes": slot})
        assert resp.status_code == 200, resp.text
        return doctor_id

    def _book(self, patient_id, doctor_id, day, start=None, session=None):
        body = {"patient_id": patient_id, "doctor_id": doctor_id,
                "appointment_date": day.isoformat()}
        if start:
            body["start_time"] = start
        return (session or self.session).post(f"{BASE_URL}/api/emr/appointments", json=body)


class TestPatients(_EmrBase):
    def test_create_get_search_update_delete(self):
        p = self._patient(allergies="Penicillin")
        assert p["source"] == "emr" and p["allergies"] == "Penicillin"
        assert self.session.get(f"{BASE_URL}/api/emr/patients/{p['id']}").json()["name"] == p["name"]

        found = self.session.get(f"{BASE_URL}/api/emr/patients", params={"search": p["name"]}).json()
        assert any(x["id"] == p["id"] for x in found["data"])

        upd = self.session.put(f"{BASE_URL}/api/emr/patients/{p['id']}", json={"city": "Pune", "age": 41})
        assert upd.status_code == 200 and upd.json()["city"] == "Pune"

        assert self.session.delete(f"{BASE_URL}/api/emr/patients/{p['id']}").status_code == 200
        assert self.session.get(f"{BASE_URL}/api/emr/patients/{p['id']}").status_code == 404
        listed = self.session.get(f"{BASE_URL}/api/emr/patients", params={"search": p["name"]}).json()
        assert not any(x["id"] == p["id"] for x in listed["data"])  # soft-deleted rows are hidden

    def test_validation(self):
        r = self.session.post(f"{BASE_URL}/api/emr/patients", json={"name": "   "})
        assert r.status_code == 422
        r = self.session.post(f"{BASE_URL}/api/emr/patients", json={"name": "X", "phone": "12345678901"})
        assert r.status_code == 422
        p = self._patient()
        r = self.session.put(f"{BASE_URL}/api/emr/patients/{p['id']}", json={"name": ""})
        assert r.status_code == 422

    def test_other_pharmacy_cannot_see_patient(self):
        p = self._patient()
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_other_{self.suffix}@pharmacy.com", "name": "Other Admin",
            "password": "OtherPharmTest123", "phone": "9855555581",
            "pharmacy_name": f"EMR Other {self.suffix}", "address": "2 St", "city": "Testville",
            "state": "Karnataka", "pincode": "560002",
            "drug_license_number": f"DL-EMROTHER-{self.suffix}"})
        assert other.status_code == 200, other.text
        _clinic_for_token(other.json()["token"])
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        assert requests.get(f"{BASE_URL}/api/emr/patients/{p['id']}", headers=h).status_code == 404
        assert requests.put(f"{BASE_URL}/api/emr/patients/{p['id']}", json={"city": "X"},
                            headers=h).status_code == 404
        assert requests.delete(f"{BASE_URL}/api/emr/patients/{p['id']}", headers=h).status_code == 404
        mine = requests.get(f"{BASE_URL}/api/emr/patients", headers=h).json()
        assert not any(x["id"] == p["id"] for x in mine["data"])


class TestPermissions(_EmrBase):
    def test_cashier_has_no_emr_access(self):
        _, cashier = self._user("cashier")
        assert cashier.get(f"{BASE_URL}/api/emr/patients").status_code == 403
        assert cashier.post(f"{BASE_URL}/api/emr/patients", json={"name": "N"}).status_code == 403

    def test_receptionist_can_register_and_book_but_not_edit_schedules(self):
        _, rec = self._user("receptionist")
        assert self._patient(session=rec)["id"]
        r = rec.post(f"{BASE_URL}/api/emr/schedules", json={
            "doctor_id": str(uuid.uuid4()), "weekday": 0,
            "start_time": "09:00", "end_time": "10:00"})
        assert r.status_code == 403
        assert rec.delete(f"{BASE_URL}/api/emr/patients/{uuid.uuid4()}").status_code == 403

    def test_doctor_login_can_edit_schedules(self):
        doctor_id = self._doctor()
        _, doc = self._user("doctor")
        r = doc.post(f"{BASE_URL}/api/emr/schedules", json={
            "doctor_id": doctor_id, "weekday": 2, "start_time": "10:00", "end_time": "12:00"})
        assert r.status_code == 200, r.text


class TestSchedulesAndSlots(_EmrBase):
    def test_doctor_list_and_schedule_validation(self):
        doctor_id = self._doctor_with_schedule(0)
        docs = self.session.get(f"{BASE_URL}/api/emr/doctors").json()
        assert any(d["id"] == doctor_id for d in docs)

        base = {"doctor_id": doctor_id, "weekday": 0, "start_time": "09:30", "end_time": "10:30"}
        assert self.session.post(f"{BASE_URL}/api/emr/schedules", json=base).status_code == 409  # overlap
        assert self.session.post(f"{BASE_URL}/api/emr/schedules",
                                 json={**base, "weekday": 7}).status_code == 422
        assert self.session.post(f"{BASE_URL}/api/emr/schedules",
                                 json={**base, "start_time": "11:00", "end_time": "10:00"}).status_code == 422
        assert self.session.post(f"{BASE_URL}/api/emr/schedules",
                                 json={**base, "slot_minutes": 1}).status_code == 422
        assert self.session.post(f"{BASE_URL}/api/emr/schedules",
                                 json={**base, "start_time": "14:00", "end_time": "15:00"}).status_code == 200

    def test_schedule_update_and_soft_delete(self):
        doctor_id = self._doctor_with_schedule(1)
        block = self.session.get(f"{BASE_URL}/api/emr/schedules",
                                 params={"doctor_id": doctor_id}).json()[0]
        r = self.session.put(f"{BASE_URL}/api/emr/schedules/{block['id']}", json={"end_time": "11:00"})
        assert r.status_code == 200 and r.json()["end_time"] == "11:00"
        assert self.session.delete(f"{BASE_URL}/api/emr/schedules/{block['id']}").status_code == 200
        assert self.session.get(f"{BASE_URL}/api/emr/schedules",
                                params={"doctor_id": doctor_id}).json() == []

    def test_slots_generated_and_marked_taken(self):
        day = _next_weekday_date(3)
        doctor_id = self._doctor_with_schedule(3, "09:00", "10:00", 30)
        patient = self._patient()
        slots = self.session.get(f"{BASE_URL}/api/emr/slots",
                                 params={"doctor_id": doctor_id, "date": day.isoformat()}).json()
        assert [s["start_time"] for s in slots] == ["09:00", "09:30"]
        assert all(s["available"] for s in slots)

        assert self._book(patient["id"], doctor_id, day, "09:00").status_code == 200
        slots = self.session.get(f"{BASE_URL}/api/emr/slots",
                                 params={"doctor_id": doctor_id, "date": day.isoformat()}).json()
        assert [s["available"] for s in slots] == [False, True]


class TestAppointments(_EmrBase):
    def test_no_double_booking_and_off_schedule_rejected(self):
        day = _next_weekday_date(4)
        doctor_id = self._doctor_with_schedule(4)
        a, b = self._patient(), self._patient()
        first = self._book(a["id"], doctor_id, day, "09:00")
        assert first.status_code == 200, first.text
        assert first.json()["end_time"] == "09:30" and first.json()["appointment_type"] == "scheduled"
        assert self._book(b["id"], doctor_id, day, "09:00").status_code == 409     # same slot
        assert self._book(b["id"], doctor_id, day, "09:10").status_code == 422     # off the grid
        assert self._book(b["id"], doctor_id, day, "15:00").status_code == 422     # outside hours
        assert self._book(b["id"], doctor_id, day - timedelta(days=30), "09:00").status_code == 422  # past

    def test_walk_in_tokens_per_doctor(self):
        doctor_a, doctor_b = self._doctor_with_schedule(5), self._doctor_with_schedule(5)
        p = self._patient()
        t1 = self._book(p["id"], doctor_a, date.today())
        t2 = self._book(p["id"], doctor_a, date.today())
        other = self._book(p["id"], doctor_b, date.today())
        assert [t1.json()["token_number"], t2.json()["token_number"]] == [1, 2]
        assert other.json()["token_number"] == 1                      # tokens are per doctor
        assert t1.json()["appointment_type"] == "walk_in" and t1.json()["start_time"] is None
        # a walk-in can only be for today
        future = self._book(p["id"], doctor_a, date.today() + timedelta(days=2))
        assert future.status_code == 422

    def test_status_machine_and_queue(self):
        doctor_id = self._doctor_with_schedule(6)
        p = self._patient()
        appt = self._book(p["id"], doctor_id, date.today()).json()
        url = f"{BASE_URL}/api/emr/appointments/{appt['id']}/status"

        assert self.session.post(url, json={"status": "completed"}).status_code == 409  # can't skip
        for nxt in ("checked_in", "in_consult", "completed"):
            r = self.session.post(url, json={"status": nxt})
            assert r.status_code == 200 and r.json()["status"] == nxt, r.text
        done = r.json()
        assert done["checked_in_at"] and done["started_at"] and done["completed_at"]
        assert self.session.post(url, json={"status": "cancelled", "cancel_reason": "x"}).status_code == 409

        queue = self.session.get(f"{BASE_URL}/api/emr/appointments",
                                 params={"doctor_id": doctor_id}).json()
        assert [q["id"] for q in queue] == [appt["id"]] and queue[0]["patient_name"] == p["name"]

    def test_cancel_needs_reason_and_frees_slot(self):
        day = _next_weekday_date(0)
        doctor_id = self._doctor_with_schedule(0)
        p, q = self._patient(), self._patient()
        appt = self._book(p["id"], doctor_id, day, "09:00").json()
        url = f"{BASE_URL}/api/emr/appointments/{appt['id']}/status"
        assert self.session.post(url, json={"status": "cancelled"}).status_code == 422
        r = self.session.post(url, json={"status": "cancelled", "cancel_reason": "Patient called"})
        assert r.status_code == 200 and r.json()["cancel_reason"] == "Patient called"
        assert self._book(q["id"], doctor_id, day, "09:00").status_code == 200   # slot is free again

    def test_reschedule_only_while_booked(self):
        day = _next_weekday_date(1)
        doctor_id = self._doctor_with_schedule(1)
        p = self._patient()
        appt = self._book(p["id"], doctor_id, day, "09:00").json()
        url = f"{BASE_URL}/api/emr/appointments/{appt['id']}"
        r = self.session.put(url, json={"start_time": "09:30"})
        assert r.status_code == 200 and r.json()["start_time"] == "09:30"
        assert self.session.put(url, json={"start_time": "11:00"}).status_code == 422
        self.session.post(url + "/status", json={"status": "checked_in"})
        assert self.session.put(url, json={"start_time": "09:00"}).status_code == 409

    def test_other_pharmacy_cannot_touch_appointment(self):
        doctor_id = self._doctor_with_schedule(2)
        appt = self._book(self._patient()["id"], doctor_id, date.today()).json()
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_other2_{self.suffix}@pharmacy.com", "name": "Other Admin",
            "password": "OtherPharmTest123", "phone": "9855555582",
            "pharmacy_name": f"EMR Other2 {self.suffix}", "address": "2 St", "city": "Testville",
            "state": "Karnataka", "pincode": "560002",
            "drug_license_number": f"DL-EMROTHER2-{self.suffix}"})
        _clinic_for_token(other.json()["token"])
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        assert requests.get(f"{BASE_URL}/api/emr/appointments/{appt['id']}", headers=h).status_code == 404
        r = requests.post(f"{BASE_URL}/api/emr/appointments/{appt['id']}/status",
                          json={"status": "checked_in"}, headers=h)
        assert r.status_code == 404

    def test_booking_needs_real_patient_and_doctor(self):
        doctor_id = self._doctor_with_schedule(3)
        assert self._book(str(uuid.uuid4()), doctor_id, date.today()).status_code == 404
        assert self._book(self._patient()["id"], str(uuid.uuid4()), date.today()).status_code == 404


class TestCalendarRange(_EmrBase):
    """The calendar's week view: one call returns a whole date range."""

    def test_range_returns_each_day_and_respects_doctor_filter(self):
        d1 = _next_weekday_date(0)
        d2 = d1 + timedelta(days=2)
        doctor_id = self._doctor_with_schedule(0, "09:00", "10:00", 30)
        other_id = self._doctor_with_schedule(0, "09:00", "10:00", 30)
        p = self._patient()
        assert self._book(p["id"], doctor_id, d1, "09:00").status_code == 200
        assert self._book(p["id"], other_id, d1, "09:00").status_code == 200
        url = f"{BASE_URL}/api/emr/appointments"
        rng = {"date_from": d1.isoformat(), "date_to": d2.isoformat()}
        both = self.session.get(url, params=rng).json()
        assert {a["doctor_id"] for a in both} >= {doctor_id, other_id}
        only = self.session.get(url, params={**rng, "doctor_id": doctor_id}).json()
        assert [a["doctor_id"] for a in only] == [doctor_id]
        later = self.session.get(url, params={
            "date_from": (d1 + timedelta(days=1)).isoformat(), "date_to": d2.isoformat(),
            "doctor_id": doctor_id}).json()
        assert later == []

    def test_range_validation(self):
        url = f"{BASE_URL}/api/emr/appointments"
        today = date.today()
        assert self.session.get(url, params={"date_from": today.isoformat()}).status_code == 422
        assert self.session.get(url, params={
            "date_from": today.isoformat(), "date_to": (today - timedelta(days=1)).isoformat()}).status_code == 422
        assert self.session.get(url, params={
            "date_from": today.isoformat(), "date_to": (today + timedelta(days=31)).isoformat()}).status_code == 422
        assert self.session.get(url, params={
            "date_from": today.isoformat(), "date_to": (today + timedelta(days=30)).isoformat()}).status_code == 200


class TestDoctorRecords(_EmrBase):
    """EMR works with doctor PROFILES mapped to this clinic (docs/31_CORE_DOCTOR_SCOPE.md), not with logins."""

    def _other_pharmacy(self):
        suffix = uuid.uuid4().hex[:8]
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_other_{suffix}@pharmacy.com", "name": "Other Admin", "password": "OtherAdmin1",
            "phone": "9877700003", "pharmacy_name": f"Other Clinic {suffix}", "address": "1 St", "city": "Pune",
            "state": "MH", "pincode": "411001"})
        assert r.status_code == 200, r.text
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {r.json()['token']}"})
        _ensure_clinic(s)
        return s

    def test_a_doctor_with_no_login_can_be_scheduled_and_booked(self):
        doctor_id = self._doctor_with_schedule(2)           # a profile only — no user behind it
        patient = self._patient()
        r = self._book(patient["id"], doctor_id, _next_weekday_date(2), "09:00")
        assert r.status_code == 200, r.text
        assert r.json()["doctor_id"] == doctor_id and r.json()["doctor_name"].startswith("Dr Test")

    def test_doctor_list_has_only_this_clinics_active_doctors(self):
        mine = self._doctor()
        elsewhere_clinic = self._other_pharmacy()
        theirs = self._doctor(session=elsewhere_clinic, clinic_id=_ensure_clinic(elsewhere_clinic))
        listed = {d["id"] for d in self.session.get(f"{BASE_URL}/api/emr/doctors").json()}
        assert mine in listed and theirs not in listed
        assert self.session.put(f"{BASE_URL}/api/practitioners/{mine}", json={"is_active": False}).status_code == 200
        assert mine not in {d["id"] for d in self.session.get(f"{BASE_URL}/api/emr/doctors").json()}

    def test_cannot_schedule_or_book_a_doctor_not_mapped_to_this_clinic(self):
        other = self._other_pharmacy()
        their_clinic = _ensure_clinic(other)
        foreign = self._doctor(session=other, clinic_id=their_clinic)
        r = self.session.post(f"{BASE_URL}/api/emr/schedules", json={
            "doctor_id": foreign, "weekday": 0, "start_time": "09:00", "end_time": "10:00"})
        assert r.status_code == 404
        assert self._book(self._patient()["id"], foreign, date.today()).status_code == 404

    def test_a_deactivated_doctor_cannot_take_new_bookings_but_history_keeps_the_name(self):
        doctor_id = self._doctor_with_schedule(4)
        patient = self._patient()
        appt = self._book(patient["id"], doctor_id, _next_weekday_date(4), "09:00").json()
        name = appt["doctor_name"]
        self.session.put(f"{BASE_URL}/api/practitioners/{doctor_id}", json={"is_active": False})
        assert self._book(patient["id"], doctor_id, _next_weekday_date(4), "09:30").status_code == 404
        again = self.session.get(f"{BASE_URL}/api/emr/appointments/{appt['id']}").json()
        assert again["doctor_name"] == name and again["doctor_id"] == doctor_id

    def test_unmapping_a_doctor_from_this_clinic_removes_them_from_booking(self):
        doctor_id = self._doctor_with_schedule(5)
        self.session.put(f"{BASE_URL}/api/practitioners/{doctor_id}", json={"clinics": []})
        assert doctor_id not in {d["id"] for d in self.session.get(f"{BASE_URL}/api/emr/doctors").json()}
        assert self._book(self._patient()["id"], doctor_id, _next_weekday_date(5), "09:00").status_code == 404
