"""
Regression tests for the Sep 14, 2026 "Data Export & Backup" feature.

GET /backup/export, the AuditLog model, and even an apiUrl.backupExport()
frontend constant all already existed — but no Settings screen ever called
it, so admins had no way to actually download a backup. Built the missing
UI (Settings > Data & Backup tab) and, since a full pharmacy-data export is
a sensitive action, added an audit-log entry for it (entity_type=
"data_export") the same way the Sep 13 Settings/Login history batch did
for those actions.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class _FreshPharmacyTestBase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        suffix = uuid.uuid4().hex[:8]
        resp = self.session.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"backup_{suffix}@pharmacy.com", "name": "Backup Test Admin",
            "password": "BackupTest123", "phone": "9855555551",
            "pharmacy_name": f"Backup Test Pharmacy {suffix}", "address": "1 St",
            "city": "Testville", "state": "Karnataka", "pincode": "560001",
            "drug_license_number": f"DL-BACKUP-{suffix}",
        })
        assert resp.status_code == 200, resp.text
        self.session.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
        self.admin_user_id = resp.json()["user"]["id"]
        self.suffix = suffix

    def _create_product(self):
        sku = f"BACKUP-{uuid.uuid4().hex[:8]}"
        resp = self.session.post(f"{BASE_URL}/api/products", json={
            "sku": sku, "name": "Backup Test Product",
            "category": "medicine", "gst_percent": 5, "units_per_pack": 1,
        })
        assert resp.status_code == 200, resp.text
        return resp.json()


class TestBackupExportAccess(_FreshPharmacyTestBase):
    def test_requires_authentication(self):
        resp = requests.get(f"{BASE_URL}/api/backup/export")
        assert resp.status_code == 401, resp.text

    def test_non_admin_is_rejected(self):
        cashier_email = f"backup_cashier_{self.suffix}@pharmacy.com"
        create_resp = self.session.post(f"{BASE_URL}/api/users", json={
            "email": cashier_email, "name": "Backup Test Cashier",
            "password": "CashierTest123", "role": "cashier",
        })
        assert create_resp.status_code == 200, create_resp.text

        cashier_session = requests.Session()
        login_resp = cashier_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": cashier_email, "password": "CashierTest123",
        })
        assert login_resp.status_code == 200, login_resp.text
        cashier_session.headers.update({"Authorization": f"Bearer {login_resp.json()['token']}"})

        resp = cashier_session.get(f"{BASE_URL}/api/backup/export")
        assert resp.status_code == 403, resp.text

    def test_admin_can_export(self):
        resp = self.session.get(f"{BASE_URL}/api/backup/export")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for key in ["export_date", "medicines", "bills", "purchases", "customers", "doctors", "suppliers"]:
            assert key in data, f"missing '{key}' in export response"


class TestBackupExportContentAndAudit(_FreshPharmacyTestBase):
    def _audit_entries(self):
        resp = self.session.get(f"{BASE_URL}/api/audit-logs", params={"entity_type": "data_export"})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def test_exported_medicines_reflect_real_data(self):
        product = self._create_product()
        resp = self.session.get(f"{BASE_URL}/api/backup/export")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert any(m["id"] == product["id"] for m in data["medicines"])

    def test_export_is_logged_to_the_audit_trail(self):
        assert self._audit_entries() == []
        self._create_product()

        resp = self.session.get(f"{BASE_URL}/api/backup/export")
        assert resp.status_code == 200, resp.text

        entries = self._audit_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["action"] == "export"
        assert entry["performed_by_name"] == "Backup Test Admin"
        # New value counts must reflect real row counts, not a placeholder.
        assert entry["new_value"]["medicines"] == 1

    def test_two_exports_are_logged_separately(self):
        self.session.get(f"{BASE_URL}/api/backup/export")
        self.session.get(f"{BASE_URL}/api/backup/export")
        assert len(self._audit_entries()) == 2


class TestBackupExportClinicData(_FreshPharmacyTestBase):
    """Oct 11, 2026: the export also carries the active clinic's EMR and patient-billing rows."""

    def _clinic_and_patient(self, name):
        cid = self.session.post(f"{BASE_URL}/api/clinics", json={"name": f"{name} {self.suffix}"}).json()["id"]
        assert self.session.post(f"{BASE_URL}/api/users/me/switch-clinic", json={"clinic_id": cid}).status_code == 200
        pat = self.session.post(f"{BASE_URL}/api/emr/patients", json={"name": f"{name} Pat", "phone": "9000000001"})
        assert pat.status_code in (200, 201), pat.text
        return pat.json()["id"]

    def test_export_carries_the_active_clinics_patients_only(self):
        a = self._clinic_and_patient("Alpha")
        b = self._clinic_and_patient("Beta")  # active clinic is now Beta
        data = self.session.get(f"{BASE_URL}/api/backup/export").json()
        ids = [p["id"] for p in data["emr_patients"]]
        assert ids == [b] and a not in ids
        for key in ["emr_appointments", "emr_prescriptions", "emr_prescription_items", "emr_doctor_schedules",
                    "emr_settings", "patient_invoices", "patient_charge_items", "patient_payments"]:
            assert key in data

    def test_without_an_active_clinic_the_clinic_lists_are_empty(self):
        data = self.session.get(f"{BASE_URL}/api/backup/export").json()
        assert data["emr_patients"] == [] and data["patient_invoices"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
