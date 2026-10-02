import React from 'react';
import { DataCard } from '@/components/shared';
import { fieldCls, labelCls } from './settingsShared';
import type { SettingsDraft } from '../settingsDraft';

export interface ClinicProfileCardProps {
  draft: SettingsDraft;
  fallback: { clinic_name: string; clinic_address: string; clinic_phone: string };
  readOnly: boolean;
  onChange: (patch: Partial<SettingsDraft>) => void;
}

/** The identity printed at the top of every prescription. Blank fields use the pharmacy record. */
export default function ClinicProfileCard({ draft, fallback, readOnly, onChange }: ClinicProfileCardProps) {
  const input = (key: keyof SettingsDraft, label: string, placeholder?: string) => (
    <div>
      <label htmlFor={`set-${key}`} className={labelCls}>{label}</label>
      <input id={`set-${key}`} value={draft[key] as string} disabled={readOnly} placeholder={placeholder}
        onChange={(e) => onChange({ [key]: e.target.value })} className={fieldCls} data-testid={`set-${key}`} />
    </div>
  );
  return (
    <DataCard noPadding={false}>
      <h2 className="text-sm font-semibold text-gray-900 mb-1">Clinic profile</h2>
      <p className="text-xs text-gray-500 mb-4">Printed on every prescription. Leave a field blank to use your pharmacy&apos;s own details.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {input('clinic_name', 'Clinic name', fallback.clinic_name)}
        {input('registration_no', 'Registration no.', 'e.g. KMC clinic registration')}
        <div className="md:col-span-2">
          <label htmlFor="set-clinic_address" className={labelCls}>Address</label>
          <textarea id="set-clinic_address" rows={2} value={draft.clinic_address} disabled={readOnly}
            placeholder={fallback.clinic_address} onChange={(e) => onChange({ clinic_address: e.target.value })}
            className={`${fieldCls} resize-none`} data-testid="set-clinic_address" />
        </div>
        {input('clinic_phone', 'Phone', fallback.clinic_phone)}
        {input('clinic_email', 'Email')}
        <div className="md:col-span-2">
          <label htmlFor="set-rx_footer" className={labelCls}>Prescription footer</label>
          <textarea id="set-rx_footer" rows={2} value={draft.rx_footer} disabled={readOnly}
            placeholder="e.g. Timings 9–1, 5–8 · Closed Sundays" onChange={(e) => onChange({ rx_footer: e.target.value })}
            className={`${fieldCls} resize-none`} data-testid="set-rx_footer" />
        </div>
      </div>
    </DataCard>
  );
}
