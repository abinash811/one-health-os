/**
 * Patient Billing desk — Pending · All bills · Receipts · Day closing.
 * Routes: /patient-billing/{pending,invoices,receipts,closing}. Each tab is its own route, so a
 * tab can be bookmarked and the browser's back button works.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader, PageTabs } from '@/components/shared';
import { BILLING_TABS, billingTabRoute } from '../patientBillingTabs';
import PendingTab from '../components/PendingTab';
import AllBillsTab from '../components/AllBillsTab';
import ReceiptsTab from '../components/ReceiptsTab';
import DayClosingTab from '../components/DayClosingTab';

export interface BillingDeskProps {
  tab: 'pending' | 'invoices' | 'receipts' | 'closing';
}

export default function BillingDesk({ tab }: BillingDeskProps) {
  const navigate = useNavigate();
  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="billing-desk-page">
      <PageHeader title="Billing" subtitle="Every patient's charges, bills and payments — across all counters" />
      <PageTabs tabs={BILLING_TABS} activeTab={tab} onChange={(k) => navigate(billingTabRoute(k))} />
      {tab === 'pending' && <PendingTab />}
      {tab === 'invoices' && <AllBillsTab />}
      {tab === 'receipts' && <ReceiptsTab />}
      {tab === 'closing' && <DayClosingTab />}
    </div>
  );
}
