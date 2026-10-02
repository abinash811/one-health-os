import React from 'react';
import { Pencil } from 'lucide-react';
import { DataCard, AppButton, EmptyState, TableSkeleton } from '@/components/shared';
import type { EmrDoctorProfile } from '../types';

export interface DoctorsCardProps {
  doctors: EmrDoctorProfile[];
  loading: boolean;
  readOnly: boolean;
  onEdit: (d: EmrDoctorProfile) => void;
}

export default function DoctorsCard({ doctors, loading, readOnly, onEdit }: DoctorsCardProps) {
  return (
    <DataCard noPadding>
      <div className="px-4 pt-4 pb-3">
        <h2 className="text-sm font-semibold text-gray-900">Doctors</h2>
        <p className="text-xs text-gray-500">Add a doctor from Team (role: Doctor), then fill in their details here. These print on their prescriptions.</p>
      </div>
      {loading ? <TableSkeleton rows={3} columns={4} /> : doctors.length === 0 ? (
        <EmptyState title="No doctors yet" description="Add a team member with the Doctor role to see them here." />
      ) : (
        <table className="w-full text-sm" data-testid="doctors-table">
          <thead className="bg-gray-50 border-y">
            <tr>{['Doctor', 'Specialty', 'Qualification', 'Registration no.', ''].map((h) => (
              <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>))}</tr>
          </thead>
          <tbody className="divide-y">
            {doctors.map((d) => (
              <tr key={d.user_id} data-testid={`doctor-row-${d.user_id}`}>
                <td className="px-4 py-3 font-medium text-gray-900">{d.name}</td>
                <td className="px-4 py-3 text-gray-700">{d.specialty || '—'}</td>
                <td className="px-4 py-3 text-gray-700">{d.qualification || '—'}</td>
                <td className="px-4 py-3 text-gray-700">{d.registration_no || '—'}</td>
                <td className="px-4 py-3 text-right">
                  {!readOnly && (
                    <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                      aria-label={`Edit ${d.name}`} onClick={() => onEdit(d)} data-testid={`edit-doctor-${d.user_id}`} />
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
