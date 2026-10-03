import React from 'react';
import { Pencil } from 'lucide-react';
import { DataCard, AppButton, EmptyState, TableSkeleton } from '@/components/shared';
import { formatCurrency, toRupees } from '@/utils/currency';
import type { EmrClinicDoctor } from '../types';

export interface DoctorsCardProps {
  doctors: EmrClinicDoctor[];
  loading: boolean;
  readOnly: boolean;
  onEdit: (d: EmrClinicDoctor) => void;
}

export default function DoctorsCard({ doctors, loading, readOnly, onEdit }: DoctorsCardProps) {
  return (
    <DataCard noPadding>
      <div className="px-4 pt-4 pb-3">
        <h2 className="text-sm font-semibold text-gray-900">Doctors</h2>
        <p className="text-xs text-gray-500">The doctors who practise at this clinic. Add doctors and edit their details under Settings → Organisation → Doctors; set this clinic's consultation fee here.</p>
      </div>
      {loading ? <TableSkeleton rows={3} columns={4} /> : doctors.length === 0 ? (
        <EmptyState title="No doctors yet" description="Add a doctor under Settings → Organisation → Doctors and tick this clinic." />
      ) : (
        <table className="w-full text-sm" data-testid="doctors-table">
          <thead className="bg-gray-50 border-y">
            <tr>{['Doctor', 'Specialty', 'Qualification', 'Registration no.', 'Fee at this clinic', ''].map((h) => (
              <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>))}</tr>
          </thead>
          <tbody className="divide-y">
            {doctors.map((d) => (
              <tr key={d.id} data-testid={`doctor-row-${d.id}`}>
                <td className="px-4 py-3 font-medium text-gray-900">{d.name}</td>
                <td className="px-4 py-3 text-gray-700">{d.specialty || '—'}</td>
                <td className="px-4 py-3 text-gray-700">{d.qualification || '—'}</td>
                <td className="px-4 py-3 text-gray-700">{d.registration_no || '—'}</td>
                <td className="px-4 py-3 text-gray-700" data-testid={`fee-${d.id}`}>
                  {d.consultation_fee_paise ? formatCurrency(toRupees(d.consultation_fee_paise)) : 'No fee'}</td>
                <td className="px-4 py-3 text-right">
                  {!readOnly && (
                    <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                      aria-label={`Edit fee for ${d.name}`} onClick={() => onEdit(d)} data-testid={`edit-doctor-${d.id}`} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DataCard>
  );
}
