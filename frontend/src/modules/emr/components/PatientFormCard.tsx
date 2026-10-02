import React from 'react';
import { DataCard, FilterPills } from '@/components/shared';
import type { FieldState, PatientFormField } from '../types';

export const FORM_FIELDS: { key: PatientFormField; label: string }[] = [
  { key: 'phone', label: 'Mobile' },
  { key: 'alternate_phone', label: 'Alternate mobile' },
  { key: 'age', label: 'Age' },
  { key: 'date_of_birth', label: 'Date of birth' },
  { key: 'gender', label: 'Gender' },
  { key: 'blood_group', label: 'Blood group' },
  { key: 'city', label: 'City' },
  { key: 'allergies', label: 'Allergies' },
  { key: 'notes', label: 'Notes' },
];

const STATES = [
  { key: 'hidden', label: 'Hidden' },
  { key: 'optional', label: 'Optional' },
  { key: 'required', label: 'Required' },
];

export interface PatientFormCardProps {
  value: Record<PatientFormField, FieldState>;
  readOnly: boolean;
  onChange: (next: Record<PatientFormField, FieldState>) => void;
}

/** Which fields the registration form shows, and which of them must be filled. */
export default function PatientFormCard({ value, readOnly, onChange }: PatientFormCardProps) {
  return (
    <DataCard noPadding={false}>
      <h2 className="text-sm font-semibold text-gray-900 mb-1">Patient registration form</h2>
      <p className="text-xs text-gray-500 mb-4">Choose what your front desk collects. A required field blocks registration until it is filled.</p>
      <ul className="divide-y" data-testid="patient-form-config">
        <li className="flex items-center justify-between py-2">
          <span className="text-sm font-medium text-gray-900">Patient name</span>
          <span className="text-xs text-gray-500">Always required</span>
        </li>
        {FORM_FIELDS.map((f) => (
          <li key={f.key} className="flex items-center justify-between py-2" data-testid={`form-field-${f.key}`}>
            <span className="text-sm text-gray-900">{f.label}</span>
            {readOnly ? <span className="text-xs text-gray-500 capitalize">{value[f.key]}</span> : (
              <FilterPills options={STATES} active={value[f.key]} onChange={(k) => onChange({ ...value, [f.key]: k as FieldState })} />
            )}
          </li>
        ))}
      </ul>
    </DataCard>
  );
}
