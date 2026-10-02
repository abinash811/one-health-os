/**
 * EMR Consultation — the visit's ONE prescription record: vitals, complaints,
 * diagnosis, medicines, advice, follow-up. Route: /emr/consult/:appointmentId.
 * Draft is editable; "Issue & print" locks it (docs/28_EMR_SCOPE.md).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Ban, Printer, Save } from 'lucide-react';
import {
  PageHeader, DataCard, AppButton, StatusBadge, ErrorState, TableSkeleton, MoreMenu,
} from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { ROUTES } from '@/constants/routes';
import { PRESCRIPTION_STATUS } from '@/constants/domainConstants';
import { formatDate } from '@/utils/dates';
import MedicineRows, { newRow, type RxRow } from '../components/MedicineRows';
import VitalsFields, { EMPTY_VITALS, fromVitalsForm, toVitalsForm, type VitalsForm } from '../components/VitalsFields';
import CancelPrescriptionDialog from '../components/CancelPrescriptionDialog';
import type { EmrPrescription } from '../types';

const areaCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm resize-none disabled:bg-gray-50';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';
const num = (s: string) => (s === '' ? null : Number(s));

const rowsFrom = (rx: EmrPrescription): RxRow[] =>
  rx.items.length
    ? rx.items.map((i) => newRow({
      medicine_name: i.medicine_name, dosage: i.dosage || '', frequency: i.frequency || '',
      duration_days: i.duration_days ? String(i.duration_days) : '', instructions: i.instructions || '',
      quantity: i.quantity ? String(i.quantity) : '',
    }))
    : [newRow()];

export default function Consultation() {
  const { appointmentId = '' } = useParams();
  const navigate = useNavigate();
  const [rx, setRx] = useState<EmrPrescription | null>(null);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<EmrPrescription[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [vitals, setVitals] = useState<VitalsForm>(EMPTY_VITALS);
  const [complaints, setComplaints] = useState('');
  const [diagnosis, setDiagnosis] = useState('');
  const [advice, setAdvice] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [rows, setRows] = useState<RxRow[]>([newRow()]);
  const [busy, setBusy] = useState<'save' | 'issue' | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);

  const hydrate = useCallback((r: EmrPrescription) => {
    setRx(r);
    setVitals(toVitalsForm(r.vitals));
    setComplaints(r.complaints || ''); setDiagnosis(r.diagnosis || ''); setAdvice(r.advice || '');
    setFollowUp(r.follow_up_date || ''); setRows(rowsFrom(r));
  }, []);

  const load = useCallback(async () => {
    setError('');
    try {
      const res = await api.post(apiUrl.emrPrescriptions(), { appointment_id: appointmentId });
      hydrate(res.data);
      const [hist, sug] = await Promise.all([
        api.get(apiUrl.emrPatientPrescriptions(res.data.patient_id)),
        api.get(apiUrl.emrPrescriptionSuggestions()),
      ]);
      setHistory((hist.data || []).filter((h: EmrPrescription) => h.id !== res.data.id && h.status === PRESCRIPTION_STATUS.ISSUED));
      setSuggestions(sug.data || []);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [appointmentId, hydrate]);

  useEffect(() => { load(); }, [load]);

  const save = async (): Promise<EmrPrescription | null> => {
    if (!rx) return null;
    const res = await api.put(apiUrl.emrPrescription(rx.id), {
      vitals: fromVitalsForm(vitals), complaints: complaints || null, diagnosis: diagnosis || null,
      advice: advice || null, follow_up_date: followUp || null,
      items: rows.filter((r) => r.medicine_name.trim()).map((r) => ({
        medicine_name: r.medicine_name, dosage: r.dosage || null, frequency: r.frequency || null,
        duration_days: num(r.duration_days), instructions: r.instructions || null, quantity: num(r.quantity),
      })),
    });
    hydrate(res.data);
    return res.data;
  };

  const saveDraft = async () => {
    setBusy('save');
    try { await save(); toast.success('Draft saved'); } catch (err) { toast.error((err as Error).message); } finally { setBusy(null); }
  };

  const issue = async () => {
    if (!rx) return;
    setBusy('issue');
    try {
      await save();
      await api.post(apiUrl.emrPrescriptionIssue(rx.id));
      navigate(ROUTES.EMR.RX_PRINT(rx.id));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (error) {
    return (
      <div className="px-8 py-6 min-h-screen bg-page">
        <PageHeader title="Consultation" />
        <DataCard><ErrorState message={error} onRetry={load} /></DataCard>
      </div>
    );
  }
  if (!rx) {
    return (
      <div className="px-8 py-6 min-h-screen bg-page"><PageHeader title="Consultation" />
        <DataCard noPadding><TableSkeleton rows={6} columns={4} /></DataCard></div>
    );
  }

  const isDraft = rx.status === PRESCRIPTION_STATUS.DRAFT;
  const p = rx.patient;
  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="emr-consult-page">
      <PageHeader
        title="Consultation"
        subtitle={`${rx.rx_number} · ${rx.doctor_name || ''}`}
        actions={isDraft ? (
          <>
            <AppButton variant="outline" icon={<Save className="w-4 h-4" />} loading={busy === 'save'}
              disabled={busy !== null} onClick={saveDraft} data-testid="save-draft-btn">Save draft</AppButton>
            <AppButton icon={<Printer className="w-4 h-4" />} loading={busy === 'issue'} disabled={busy !== null}
              onClick={issue} data-testid="issue-rx-btn">Issue &amp; print</AppButton>
          </>
        ) : (
          <>
            <AppButton icon={<Printer className="w-4 h-4" />} onClick={() => navigate(ROUTES.EMR.RX_PRINT(rx.id))}
              data-testid="print-rx-btn">Print</AppButton>
            <MoreMenu testId="rx-more" items={[
              { icon: <Ban className="w-4 h-4" />, label: 'Cancel prescription', action: () => setCancelOpen(true) },
            ]} />
          </>
        )}
      />

      <DataCard noPadding={false} className="mb-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
          <span className="font-semibold text-gray-900 text-base" data-testid="consult-patient">{rx.patient_name}</span>
          <span className="text-gray-600">{[rx.patient_uhid, p?.age ? `${p.age} yrs` : null, p?.gender, p?.phone].filter(Boolean).join(' · ')}</span>
          <StatusBadge status={rx.status} />
          {p?.allergies && (
            <span className="px-2 py-0.5 rounded bg-red-50 text-red-700 text-xs font-medium" data-testid="allergy-banner">
              Allergies: {p.allergies}
            </span>
          )}
        </div>
      </DataCard>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4">
          <DataCard noPadding={false}>
            <span className={labelCls}>Vitals</span>
            <VitalsFields value={vitals} onChange={setVitals} readOnly={!isDraft} />
          </DataCard>
          <DataCard noPadding={false}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="rx-complaints" className={labelCls}>Complaints</label>
                <textarea id="rx-complaints" rows={3} value={complaints} disabled={!isDraft} className={areaCls}
                  onChange={(e) => setComplaints(e.target.value)} data-testid="rx-complaints" />
              </div>
              <div>
                <label htmlFor="rx-diagnosis" className={labelCls}>Diagnosis</label>
                <textarea id="rx-diagnosis" rows={3} value={diagnosis} disabled={!isDraft} className={areaCls}
                  onChange={(e) => setDiagnosis(e.target.value)} data-testid="rx-diagnosis" />
              </div>
            </div>
          </DataCard>
          <DataCard noPadding={false}>
            <span className={labelCls}>Medicines</span>
            <MedicineRows rows={rows} onChange={setRows} suggestions={suggestions} readOnly={!isDraft} />
          </DataCard>
          <DataCard noPadding={false}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <label htmlFor="rx-advice" className={labelCls}>Advice / notes</label>
                <textarea id="rx-advice" rows={2} value={advice} disabled={!isDraft} className={areaCls}
                  onChange={(e) => setAdvice(e.target.value)} data-testid="rx-advice" />
              </div>
              <div>
                <label htmlFor="rx-followup" className={labelCls}>Follow-up on</label>
                <input id="rx-followup" type="date" value={followUp} disabled={!isDraft}
                  onChange={(e) => setFollowUp(e.target.value)} data-testid="rx-followup"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm disabled:bg-gray-50" />
              </div>
            </div>
          </DataCard>
        </div>

        <DataCard noPadding={false}>
          <span className={labelCls}>Previous visits</span>
          {history.length === 0 ? <p className="text-sm text-gray-400" data-testid="no-history">No earlier prescriptions.</p> : (
            <ul className="divide-y" data-testid="rx-history">
              {history.slice(0, 5).map((h) => (
                <li key={h.id} className="py-2 text-sm">
                  <p className="font-medium text-gray-900">{formatDate(h.issued_at || h.created_at)} · {h.rx_number}</p>
                  <p className="text-gray-600">{h.diagnosis || 'No diagnosis noted'}</p>
                  <p className="text-xs text-gray-400">{h.items.map((i) => i.medicine_name).join(', ')}</p>
                </li>
              ))}
            </ul>
          )}
        </DataCard>
      </div>

      <CancelPrescriptionDialog open={cancelOpen} prescriptionId={rx.id} rxNumber={rx.rx_number}
        onClose={() => setCancelOpen(false)} onCancelled={() => navigate(ROUTES.EMR.APPOINTMENTS)} />
    </div>
  );
}
