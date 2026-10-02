"""
EMR clinic settings (docs/28_EMR_SCOPE.md → Settings): clinic profile, UHID
format, patient-form layout, Rx prefix, doctor profiles. P0 behaviours:
permission split (anyone reads, only admin edits), UHIDs unique and never reused,
required patient fields enforced server-side, per-clinic isolation.

Each test runs in its own freshly registered pharmacy so changed settings
(e.g. a required field) can never leak into other tests.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from test_emr_appointments import BASE_URL, _EmrBase, _next_weekday_date


class _Clinic(_EmrBase):
    @pytest.fixture(autouse=True)
    def own_clinic(self, setup):
        sfx = uuid.uuid4().hex[:8]
        reg = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_set_{sfx}@pharmacy.com", "name": "Clinic Admin", "password": "SettingsTest123",
            "phone": "9855555583", "pharmacy_name": f"Settings Clinic {sfx}", "address": "9 Clinic Rd",
            "city": "Testville", "state": "Karnataka", "pincode": "560003",
            "drug_license_number": f"DL-EMRSET-{sfx}"})
        assert reg.status_code == 200, reg.text
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json",
                                     "Authorization": f"Bearer {reg.json()['token']}"})
        self.name = f"Settings Clinic {sfx}"

    def _put(self, body, session=None):
        return (session or self.session).put(f"{BASE_URL}/api/emr/settings", json=body)


class TestSettings(_Clinic):
    def test_defaults_are_created_on_first_read(self):
        s = self.session.get(f"{BASE_URL}/api/emr/settings").json()
        assert s["rx_prefix"] == "RX-" and s["uhid_prefix"] == "UH-" and s["uhid_digits"] == 6
        assert s["uhid_next"] == 1 and s["default_slot_minutes"] == 15
        assert s["patient_form"]["allergies"] == "optional"
        assert s["fallback"]["clinic_name"] == self.name

    def test_anyone_reads_only_admin_edits(self):
        _, rec = self._user("receptionist")
        _, doc = self._user("doctor")
        assert rec.get(f"{BASE_URL}/api/emr/settings").status_code == 200
        assert self._put({"clinic_name": "Hack"}, rec).status_code == 403
        assert self._put({"clinic_name": "Hack"}, doc).status_code == 403
        assert self._put({"clinic_name": "Sunrise Clinic"}).json()["clinic_name"] == "Sunrise Clinic"

    def test_validation(self):
        for body in ({"uhid_prefix": "bad prefix!"}, {"rx_prefix": ""}, {"uhid_digits": 2},
                     {"default_slot_minutes": 1}, {"patient_form": {"name": "hidden"}},
                     {"patient_form": {"allergies": "sometimes"}}):
            assert self._put(body).status_code == 422, body

    def test_settings_are_per_clinic(self):
        self._put({"uhid_prefix": "MINE-"})
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_set_o_{self.suffix}@pharmacy.com", "name": "Other", "password": "OtherSet12345",
            "phone": "9855555584", "pharmacy_name": f"Other Set {self.suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560004",
            "drug_license_number": f"DL-EMRSETO-{self.suffix}"})
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        assert requests.get(f"{BASE_URL}/api/emr/settings", headers=h).json()["uhid_prefix"] == "UH-"


class TestUhid(_Clinic):
    def test_sequential_uhids_with_clinic_prefix_and_no_reuse(self):
        a = self._patient()
        b = self._patient()
        assert (a["uhid"], b["uhid"]) == ("UH-000001", "UH-000002")
        self._put({"uhid_prefix": "SUN-", "uhid_digits": 4})
        c = self._patient()
        assert c["uhid"] == "SUN-0003"                      # numbering continues, new format
        assert self.session.get(f"{BASE_URL}/api/emr/patients/{a['id']}").json()["uhid"] == "UH-000001"
        self.session.delete(f"{BASE_URL}/api/emr/patients/{c['id']}")
        assert self._patient()["uhid"] == "SUN-0004"        # a deleted patient's UHID is never reused

    def test_simultaneous_registrations_get_distinct_uhids(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            res = list(pool.map(lambda _: self.session.post(
                f"{BASE_URL}/api/emr/patients", json={"name": "Race Patient"}), range(5)))
        assert all(r.status_code == 200 for r in res), [r.text for r in res]
        assert len({r.json()["uhid"] for r in res}) == 5

    def test_search_by_uhid(self):
        p = self._patient()
        found = self.session.get(f"{BASE_URL}/api/emr/patients", params={"search": p["uhid"]}).json()
        assert [x["id"] for x in found["data"]] == [p["id"]]


class TestPatientFormRules(_Clinic):
    def test_required_field_is_enforced_on_create_and_edit(self):
        self._put({"patient_form": {"allergies": "required", "blood_group": "hidden"}})
        r = self.session.post(f"{BASE_URL}/api/emr/patients", json={"name": "No Allergy Info"})
        assert r.status_code == 422 and "Allergies" in r.json()["detail"]
        ok = self.session.post(f"{BASE_URL}/api/emr/patients", json={"name": "Has Info", "allergies": "None known"})
        assert ok.status_code == 200
        blank = self.session.put(f"{BASE_URL}/api/emr/patients/{ok.json()['id']}", json={"allergies": ""})
        assert blank.status_code == 422
        # editing a different field doesn't trip on the required one
        url = f"{BASE_URL}/api/emr/patients/{ok.json()['id']}"
        assert self.session.put(url, json={"city": "Pune"}).status_code == 200

    def test_changing_form_keeps_unmentioned_fields(self):
        self._put({"patient_form": {"allergies": "required"}})
        form = self._put({"patient_form": {"city": "hidden"}}).json()["patient_form"]
        assert form["allergies"] == "required" and form["city"] == "hidden"


class TestPrescriptionIdentity(_Clinic):
    def _issued_rx(self):
        doctor_id = self._doctor_with_schedule(1)
        patient = self._patient()
        appt = self._book(patient["id"], doctor_id, _next_weekday_date(1), start="09:00").json()
        r = self.session.post(f"{BASE_URL}/api/emr/prescriptions", json={"appointment_id": appt["id"]})
        assert r.status_code == 200, r.text
        return doctor_id, r.json()

    def test_print_identity_uses_settings_and_falls_back_to_pharmacy(self):
        doctor_id, rx = self._issued_rx()
        assert rx["clinic"]["name"] == self.name                      # blank settings → pharmacy record
        self._put({"clinic_name": "Sunrise Family Clinic", "registration_no": "KMC-123", "rx_footer": "Get well soon"})
        prof = self.session.put(f"{BASE_URL}/api/emr/doctor-profiles/{doctor_id}", json={
            "specialty": "Paediatrics", "qualification": "MBBS, MD", "registration_no": "KMC-9981"})
        assert prof.status_code == 200 and prof.json()["specialty"] == "Paediatrics"
        got = self.session.get(f"{BASE_URL}/api/emr/prescriptions/{rx['id']}").json()
        assert got["clinic"]["name"] == "Sunrise Family Clinic" and got["clinic"]["footer"] == "Get well soon"
        assert got["doctor"]["registration_no"] == "KMC-9981" and got["doctor"]["specialty"] == "Paediatrics"
        assert got["patient_uhid"]

    def test_rx_prefix_change_keeps_numbering(self):
        _, first = self._issued_rx()
        assert first["rx_number"] == "RX-000001"
        self._put({"rx_prefix": "SUN-RX-"})
        day = _next_weekday_date(1)
        doctor_id = self._doctor_with_schedule(1)
        appt = self._book(self._patient()["id"], doctor_id, day, start="09:00").json()
        second = self.session.post(f"{BASE_URL}/api/emr/prescriptions", json={"appointment_id": appt["id"]}).json()
        assert second["rx_number"] == "SUN-RX-000002"


class TestDoctorProfiles(_Clinic):
    def test_list_update_and_permissions(self):
        doctor_id, _ = self._user("doctor")
        listed = self.session.get(f"{BASE_URL}/api/emr/doctor-profiles").json()
        row = next(d for d in listed if d["user_id"] == doctor_id)
        assert row["specialty"] is None
        _, doc = self._user("doctor")
        assert doc.put(f"{BASE_URL}/api/emr/doctor-profiles/{doctor_id}", json={"specialty": "X"}).status_code == 403
        url = f"{BASE_URL}/api/emr/doctor-profiles/{doctor_id}"
        r = self.session.put(url, json={"specialty": "ENT", "registration_no": "  "})
        assert r.json()["specialty"] == "ENT" and r.json()["registration_no"] is None
        again = self.session.put(f"{BASE_URL}/api/emr/doctor-profiles/{doctor_id}", json={"qualification": "MS"}).json()
        assert again["specialty"] == "ENT" and again["qualification"] == "MS"   # update keeps other fields

    def test_cannot_edit_another_clinics_doctor(self):
        doctor_id, _ = self._user("doctor")
        other = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"emr_dp_o_{self.suffix}@pharmacy.com", "name": "Other", "password": "OtherDoc12345",
            "phone": "9855555585", "pharmacy_name": f"Other Doc {self.suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560005",
            "drug_license_number": f"DL-EMRDP-{self.suffix}"})
        h = {"Authorization": f"Bearer {other.json()['token']}"}
        r = requests.put(f"{BASE_URL}/api/emr/doctor-profiles/{doctor_id}", json={"specialty": "Hacked"}, headers=h)
        assert r.status_code == 404
