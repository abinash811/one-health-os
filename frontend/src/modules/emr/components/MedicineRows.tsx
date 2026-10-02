import React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { AppButton, SuggestField } from '@/components/shared';

export interface RxRow {
  key: string;
  medicine_name: string;
  dosage: string;
  frequency: string;
  duration_days: string;
  instructions: string;
  quantity: string;
}

let rowSeq = 0;
export const newRow = (over: Partial<RxRow> = {}): RxRow => ({
  key: `row-${++rowSeq}`, medicine_name: '', dosage: '', frequency: '',
  duration_days: '', instructions: '', quantity: '', ...over,
});

const fieldCls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand text-sm disabled:bg-gray-50';
const labelCls = 'block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1';

export interface MedicineRowsProps {
  rows: RxRow[];
  onChange: (rows: RxRow[]) => void;
  /** The clinic's own prescribing history, most-used first. */
  suggestions: string[];
  readOnly?: boolean;
}

export default function MedicineRows({ rows, onChange, suggestions, readOnly }: MedicineRowsProps) {
  const patch = (key: string, field: keyof RxRow, value: string) =>
    onChange(rows.map((r) => (r.key === key ? { ...r, [field]: value } : r)));

  return (
    <div className="space-y-3" data-testid="medicine-rows">
      {rows.map((r, i) => (
        <div key={r.key} className="grid grid-cols-12 gap-3 items-end p-3 rounded-lg border border-gray-200" data-testid={`rx-row-${i}`}>
          <div className="col-span-12 lg:col-span-3">
            {readOnly ? (
              <><span className={labelCls}>Medicine</span><p className="text-sm font-medium text-gray-900 py-2">{r.medicine_name}</p></>
            ) : (
              <SuggestField label="Medicine" value={r.medicine_name} options={suggestions}
                onChange={(v: string) => patch(r.key, 'medicine_name', v)}
                placeholder="Type a name — e.g. Paracetamol 650" testId={`rx-name-${i}`} />
            )}
          </div>
          <div className="col-span-6 lg:col-span-2">
            <label className={labelCls} htmlFor={`rx-dose-${i}`}>Dose</label>
            <input id={`rx-dose-${i}`} value={r.dosage} disabled={readOnly} placeholder="1 tab" className={fieldCls}
              onChange={(e) => patch(r.key, 'dosage', e.target.value)} data-testid={`rx-dose-${i}`} />
          </div>
          <div className="col-span-6 lg:col-span-3">
            <label className={labelCls} htmlFor={`rx-freq-${i}`}>Frequency</label>
            <input id={`rx-freq-${i}`} value={r.frequency} disabled={readOnly} placeholder="1-0-1" className={fieldCls}
              onChange={(e) => patch(r.key, 'frequency', e.target.value)} data-testid={`rx-freq-${i}`} />
          </div>
          <div className="col-span-4 lg:col-span-1">
            <label className={labelCls} htmlFor={`rx-days-${i}`}>Days</label>
            <input id={`rx-days-${i}`} type="number" min="1" value={r.duration_days} disabled={readOnly} className={fieldCls}
              onChange={(e) => patch(r.key, 'duration_days', e.target.value)} data-testid={`rx-days-${i}`} />
          </div>
          <div className="col-span-4 lg:col-span-1">
            <label className={labelCls} htmlFor={`rx-qty-${i}`}>Qty</label>
            <input id={`rx-qty-${i}`} type="number" min="1" value={r.quantity} disabled={readOnly} className={fieldCls}
              onChange={(e) => patch(r.key, 'quantity', e.target.value)} data-testid={`rx-qty-${i}`} />
          </div>
          <div className="col-span-4 lg:col-span-1 flex justify-end">
            {!readOnly && (
              <AppButton variant="ghost" size="sm" iconOnly icon={<Trash2 className="w-4 h-4" />}
                aria-label={`Remove medicine ${i + 1}`} onClick={() => onChange(rows.filter((x) => x.key !== r.key))}
                data-testid={`rx-remove-${i}`} />
            )}
          </div>
          <div className="col-span-12">
            <input value={r.instructions} disabled={readOnly} placeholder="Instructions — e.g. after food"
              aria-label="Instructions" className={fieldCls}
              onChange={(e) => patch(r.key, 'instructions', e.target.value)} data-testid={`rx-instr-${i}`} />
          </div>
        </div>
      ))}
      {!readOnly && (
        <AppButton variant="outline" size="sm" icon={<Plus className="w-4 h-4" />}
          onClick={() => onChange([...rows, newRow()])} data-testid="add-medicine-btn">
          Add medicine
        </AppButton>
      )}
    </div>
  );
}
