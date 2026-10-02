import React from 'react';
import type { EmrVitals } from '../types';

export type VitalsForm = Record<keyof EmrVitals, string>;

export const EMPTY_VITALS: VitalsForm = {
  bp_systolic: '', bp_diastolic: '', pulse: '', temperature_c: '', spo2: '', weight_kg: '',
};

const FIELDS: { key: keyof EmrVitals; label: string; unit: string; step?: string }[] = [
  { key: 'bp_systolic', label: 'BP (sys)', unit: 'mmHg' },
  { key: 'bp_diastolic', label: 'BP (dia)', unit: 'mmHg' },
  { key: 'pulse', label: 'Pulse', unit: '/min' },
  { key: 'temperature_c', label: 'Temp', unit: '°C', step: '0.1' },
  { key: 'spo2', label: 'SpO₂', unit: '%' },
  { key: 'weight_kg', label: 'Weight', unit: 'kg', step: '0.1' },
];

export const toVitalsForm = (v: EmrVitals | undefined): VitalsForm => ({
  ...EMPTY_VITALS,
  ...Object.fromEntries(Object.entries(v || {}).map(([k, n]) => [k, String(n)])),
});

/** Empty boxes are dropped so the backend only stores what was actually measured. */
export const fromVitalsForm = (f: VitalsForm): EmrVitals =>
  Object.fromEntries(Object.entries(f).filter(([, s]) => s !== '').map(([k, s]) => [k, Number(s)]));

export interface VitalsFieldsProps {
  value: VitalsForm;
  onChange: (next: VitalsForm) => void;
  readOnly?: boolean;
}

export default function VitalsFields({ value, onChange, readOnly }: VitalsFieldsProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="vitals-fields">
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label htmlFor={`vital-${f.key}`} className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">
            {f.label}
          </label>
          <div className="relative">
            <input id={`vital-${f.key}`} type="number" min="0" step={f.step || '1'} value={value[f.key]}
              disabled={readOnly} onChange={(e) => onChange({ ...value, [f.key]: e.target.value })}
              data-testid={`vital-${f.key}`}
              className="w-full pl-3 pr-12 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm disabled:bg-gray-50" />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">{f.unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
