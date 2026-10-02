import React from 'react';
import {
  Select as SelectRoot, SelectContent as SelectContentRaw, SelectItem as SelectItemRaw,
  SelectTrigger as SelectTriggerRaw, SelectValue as SelectValueRaw,
} from '@/components/ui/select';
import type { EmrDoctor } from '../types';

// select.jsx is untyped plain JS — same cast BackdatedBadge.tsx uses for tooltip.jsx.
type AnyProps = React.FC<Record<string, unknown> & { children?: React.ReactNode }>;
const Select = SelectRoot as unknown as AnyProps;
const SelectContent = SelectContentRaw as unknown as AnyProps;
const SelectItem = SelectItemRaw as unknown as AnyProps;
const SelectTrigger = SelectTriggerRaw as unknown as AnyProps;
const SelectValue = SelectValueRaw as unknown as AnyProps;

export const ALL_DOCTORS = 'all';

export interface DoctorSelectProps {
  doctors: EmrDoctor[];
  /** Doctor id, or ALL_DOCTORS when `allowAll` is set. */
  value: string;
  onChange: (value: string) => void;
  allowAll?: boolean;
  id?: string;
  testId?: string;
  className?: string;
}

/** The one doctor picker used by the day view, the booking dialog and the schedule page. */
export default function DoctorSelect({ doctors, value, onChange, allowAll = false, id, testId, className = 'w-56' }: DoctorSelectProps) {
  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger id={id} className={className} data-testid={testId}>
        <SelectValue placeholder={doctors.length ? 'Select doctor' : 'No doctors yet'} />
      </SelectTrigger>
      <SelectContent>
        {allowAll && <SelectItem value={ALL_DOCTORS}>All doctors</SelectItem>}
        {doctors.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
