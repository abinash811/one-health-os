import React from 'react';

interface Props { checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }

export default function AdminCheckbox({ checked, onChange, disabled = false }: Props) {
  return (
    <div className={`flex items-start gap-2 ${disabled ? 'opacity-60' : ''}`}>
      <input id="member-is-admin" type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-gray-300 accent-brand" data-testid="is-admin-checkbox" />
      <div>
        <label htmlFor="member-is-admin" className={`block text-sm font-medium text-gray-900 ${disabled ? '' : 'cursor-pointer'}`}>Administrator</label>
        <p className="text-xs text-gray-500">
          {disabled ? 'You can’t remove your own admin access. ' : ''}
          Full access to everything, plus managing team, roles and settings. Keeps the role above.
        </p>
      </div>
    </div>
  );
}
