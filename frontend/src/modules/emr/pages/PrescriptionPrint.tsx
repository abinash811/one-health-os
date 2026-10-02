/**
 * EMR printable prescription — clean A4, no app chrome. Route:
 * /emr/prescriptions/:id/print (rendered outside <Layout>). "Print / Save as PDF"
 * uses the browser's own print dialog (docs/28_EMR_SCOPE.md Step 2).
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Printer } from 'lucide-react';
import { AppButton, ErrorState, PageSkeleton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { ROUTES } from '@/constants/routes';
import { PRESCRIPTION_STATUS } from '@/constants/domainConstants';
import { formatDate } from '@/utils/dates';
import type { EmrPrescription, EmrVitals } from '../types';

const VITAL_LABELS: [keyof EmrVitals, string, string][] = [
  ['pulse', 'Pulse', '/min'], ['temperature_c', 'Temp', '°C'], ['spo2', 'SpO₂', '%'], ['weight_kg', 'Weight', 'kg'],
];

const vitalsLine = (v: EmrVitals): string => {
  const parts: string[] = [];
  if (v.bp_systolic != null && v.bp_diastolic != null) parts.push(`BP ${v.bp_systolic}/${v.bp_diastolic} mmHg`);
  VITAL_LABELS.forEach(([k, label, unit]) => { if (v[k] != null) parts.push(`${label} ${v[k]} ${unit}`); });
  return parts.join('  ·  ');
};

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="mb-4">
    <h2 className="text-[11px] font-bold uppercase tracking-wider text-gray-500 mb-1">{title}</h2>
    <div className="text-sm text-gray-900 whitespace-pre-line">{children}</div>
  </section>
);

export default function PrescriptionPrint() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [rx, setRx] = useState<EmrPrescription | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(apiUrl.emrPrescription(id)).then((res: { data: EmrPrescription }) => setRx(res.data))
      .catch((err: Error) => setError(err.message));
  }, [id]);

  if (error) return <div className="p-8"><ErrorState message={error} /></div>;
  if (!rx) return <PageSkeleton />;

  const p = rx.patient;
  const isDraft = rx.status === PRESCRIPTION_STATUS.DRAFT;
  const vitals = vitalsLine(rx.vitals);
  return (
    <div className="min-h-screen bg-page print:bg-white py-6 print:py-0" data-testid="rx-print-page">
      <div className="max-w-[210mm] mx-auto mb-4 flex items-center justify-between print:hidden px-2">
        <AppButton variant="outline" icon={<ArrowLeft className="w-4 h-4" />}
          onClick={() => navigate(ROUTES.EMR.APPOINTMENTS)}>Back to queue</AppButton>
        <AppButton icon={<Printer className="w-4 h-4" />} onClick={() => window.print()} data-testid="print-btn">
          Print / Save as PDF
        </AppButton>
      </div>

      <article className="relative max-w-[210mm] min-h-[270mm] mx-auto bg-white shadow-sm border border-gray-200 print:shadow-none print:border-0 p-10">
        {rx.status !== PRESCRIPTION_STATUS.ISSUED && (
          <p className="absolute top-4 right-6 text-xs font-bold uppercase text-red-600" data-testid="rx-not-valid">
            {isDraft ? 'Draft — not issued' : 'Cancelled'}
          </p>
        )}
        <header className="border-b-2 border-gray-900 pb-3 mb-4">
          <h1 className="font-display text-2xl font-bold text-gray-900" data-testid="rx-clinic-name">{rx.clinic.name}</h1>
          <p className="text-xs text-gray-600">{[rx.clinic.address, rx.clinic.phone, rx.clinic.email].filter(Boolean).join(' · ')}</p>
          {rx.clinic.registration_no && <p className="text-xs text-gray-500" data-testid="rx-clinic-reg">Reg. no. {rx.clinic.registration_no}</p>}
        </header>

        <div className="flex justify-between text-sm mb-4">
          <div>
            <p className="font-semibold text-gray-900 text-base" data-testid="rx-patient-name">{rx.patient_name}</p>
            <p className="text-gray-600">{[rx.patient_uhid, p?.age ? `${p.age} yrs` : null, p?.gender, p?.phone].filter(Boolean).join(' · ')}</p>
            {p?.allergies && <p className="text-red-700 font-medium">Allergies: {p.allergies}</p>}
          </div>
          <div className="text-right">
            <p className="font-mono font-semibold">{rx.rx_number}</p>
            <p className="text-gray-600">{formatDate(rx.issued_at || rx.created_at)}</p>
          </div>
        </div>

        {vitals && <Section title="Vitals">{vitals}</Section>}
        {rx.complaints && <Section title="Complaints">{rx.complaints}</Section>}
        {rx.diagnosis && <Section title="Diagnosis">{rx.diagnosis}</Section>}

        <h2 className="font-display text-xl font-bold text-gray-900 mt-5 mb-2">℞</h2>
        <table className="w-full text-sm mb-4" data-testid="rx-items">
          <thead>
            <tr className="border-b border-gray-300 text-left text-[11px] uppercase text-gray-500">
              <th className="py-1 w-8">#</th><th className="py-1">Medicine</th><th className="py-1">Dose</th>
              <th className="py-1">Frequency</th><th className="py-1">Days</th>
            </tr>
          </thead>
          <tbody>
            {rx.items.map((i, n) => (
              <tr key={i.id || n} className="border-b border-gray-100 align-top">
                <td className="py-2 text-gray-500">{n + 1}</td>
                <td className="py-2 font-medium text-gray-900">
                  {i.medicine_name}
                  {i.instructions && <span className="block text-xs font-normal text-gray-600">{i.instructions}</span>}
                </td>
                <td className="py-2">{i.dosage || '—'}</td>
                <td className="py-2">{i.frequency || '—'}</td>
                <td className="py-2">{i.duration_days ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {rx.advice && <Section title="Advice">{rx.advice}</Section>}
        {rx.follow_up_date && <Section title="Follow-up">{`Please visit again on ${formatDate(rx.follow_up_date)}`}</Section>}

        <footer className="absolute bottom-16 right-10 text-right text-sm">
          <div className="w-48 border-b border-gray-400 mb-1" />
          <p className="font-semibold text-gray-900">{rx.doctor_name}</p>
          {(rx.doctor.qualification || rx.doctor.specialty) && (
            <p className="text-xs text-gray-600" data-testid="rx-doctor-quals">
              {[rx.doctor.qualification, rx.doctor.specialty].filter(Boolean).join(' · ')}</p>
          )}
          {rx.doctor.registration_no && <p className="text-xs text-gray-500">Reg. no. {rx.doctor.registration_no}</p>}
        </footer>
        {rx.clinic.footer && (
          <p className="absolute bottom-3 left-10 right-10 text-center text-[11px] text-gray-500 border-t pt-2" data-testid="rx-footer">
            {rx.clinic.footer}</p>
        )}
      </article>
    </div>
  );
}
