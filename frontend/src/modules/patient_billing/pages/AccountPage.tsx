/** One patient's complete bill, opened from the billing desk. Route: /patient-billing/accounts/:patientId */
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { PageHeader, AppButton } from '@/components/shared';
import { ROUTES } from '@/constants/routes';
import AccountBill from '../components/AccountBill';

export default function AccountPage() {
  const { patientId = '' } = useParams();
  const navigate = useNavigate();
  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="account-page">
      <PageHeader title="Patient bill"
        breadcrumb={<AppButton variant="chip" icon={<ChevronLeft className="w-4 h-4" />}
          onClick={() => navigate(ROUTES.PATIENT_BILLING.PENDING)}>Billing</AppButton>} />
      <AccountBill patientId={patientId} />
    </div>
  );
}
