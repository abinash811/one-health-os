import React from 'react';
import { DataCard, FilterPills } from '@/components/shared';
import { fieldCls, labelCls } from './settingsShared';
import type { SettingsDraft } from '../settingsDraft';

const DIGITS = [4, 5, 6, 8].map((n) => ({ key: String(n), label: `${n} digits` }));
const SLOTS = [10, 15, 20, 30].map((n) => ({ key: String(n), label: `${n} min` }));

export interface IdFormatsCardProps {
  draft: SettingsDraft;
  /** Next patient number the clinic will hand out (read-only — it only moves forward). */
  uhidNext: number;
  readOnly: boolean;
  onChange: (patch: Partial<SettingsDraft>) => void;
}

export default function IdFormatsCard({ draft, uhidNext, readOnly, onChange }: IdFormatsCardProps) {
  const preview = `${draft.uhid_prefix}${String(uhidNext).padStart(Number(draft.uhid_digits), '0')}`;
  return (
    <DataCard noPadding={false}>
      <h2 className="text-sm font-semibold text-gray-900 mb-1">IDs and defaults</h2>
      <p className="text-xs text-gray-500 mb-4">Changing a format only affects new records — existing patient IDs and prescription numbers stay as they are.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor="set-uhid_prefix" className={labelCls}>Patient ID (UHID) prefix</label>
          <input id="set-uhid_prefix" value={draft.uhid_prefix} disabled={readOnly} maxLength={10}
            onChange={(e) => onChange({ uhid_prefix: e.target.value })} className={fieldCls} data-testid="set-uhid_prefix" />
          <p className="text-xs text-gray-500 mt-1">Next patient ID: <span className="font-mono font-semibold" data-testid="uhid-preview">{preview}</span></p>
        </div>
        <div>
          <span className={labelCls}>UHID length</span>
          {readOnly ? <p className="text-sm py-2">{draft.uhid_digits} digits</p> : (
            <FilterPills options={DIGITS} active={String(draft.uhid_digits)} onChange={(k) => onChange({ uhid_digits: Number(k) })} />
          )}
        </div>
        <div>
          <label htmlFor="set-rx_prefix" className={labelCls}>Prescription number prefix</label>
          <input id="set-rx_prefix" value={draft.rx_prefix} disabled={readOnly} maxLength={10}
            onChange={(e) => onChange({ rx_prefix: e.target.value })} className={fieldCls} data-testid="set-rx_prefix" />
        </div>
        <div>
          <span className={labelCls}>Default appointment length</span>
          {readOnly ? <p className="text-sm py-2">{draft.default_slot_minutes} min</p> : (
            <FilterPills options={SLOTS} active={String(draft.default_slot_minutes)}
              onChange={(k) => onChange({ default_slot_minutes: Number(k) })} />
          )}
        </div>
      </div>
    </DataCard>
  );
}
