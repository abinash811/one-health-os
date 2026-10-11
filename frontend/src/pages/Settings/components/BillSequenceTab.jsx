/**
 * BillSequenceTab — bill number sequence configuration.
 * Props:
 *   billSequences    {Array}
 *   sequenceLoading  {boolean}
 *   onSave           {(form) => Promise<boolean>}
 *   onRefresh        {() => void}
 */
import React, { useState, useEffect } from 'react';
import { Save, Hash, AlertCircle, CheckCircle } from 'lucide-react';
import { InlineLoader, AppButton } from '@/components/shared';
import { SEQUENCE_DOCUMENT_TYPE } from '@/constants/domainConstants';

const SEQ_INIT = { document_type: SEQUENCE_DOCUMENT_TYPE.SALES_INVOICE, prefix: 'INV', starting_number: 1, sequence_length: 6, allow_prefix_change: true };

const DOCUMENT_TYPE_LABELS = {
  [SEQUENCE_DOCUMENT_TYPE.SALES_INVOICE]: 'Sales Invoice',
  [SEQUENCE_DOCUMENT_TYPE.SALES_RETURN]:  'Sales Return',
};

export default function BillSequenceTab({ billSequences, sequenceLoading, onSave, onRefresh }) {
  const [editingSequence, setEditingSequence] = useState(null);
  const [form,            setForm]            = useState(SEQ_INIT);
  const [previewNumber,   setPreviewNumber]   = useState('');

  useEffect(() => {
    const preview = `${form.prefix.toUpperCase()}-${String(form.starting_number).padStart(form.sequence_length, '0')}`;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resets form/list state when the input changes; moving it out of the effect is a separate refactor
    setPreviewNumber(preview);
  }, [form]);

  const handleConfigure = (seq) => {
    setEditingSequence(seq.document_type);
    setForm({
      document_type: seq.document_type,
      prefix: seq.prefix,
      starting_number: seq.next_number,
      sequence_length: seq.sequence_length || 6,
      allow_prefix_change: seq.allow_prefix_change !== false,
    });
  };

  const handleCancel = () => { setEditingSequence(null); setForm(SEQ_INIT); };

  const handleSave = async () => {
    const ok = await onSave(form);
    if (ok) { onRefresh(); handleCancel(); }
  };

  if (sequenceLoading) {
    return <div className="py-8 text-center"><InlineLoader text="Loading sequences..." /></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-2">Bill Number Sequence Configuration</h3>
        <p className="text-sm text-gray-600 mb-6">
          Sales bills and sales returns each get their own number series — required for GST filing,
          since returns shouldn't create gaps in your bill numbers. Numbers are sequential and never reused.
        </p>

        {/* Sequences Table */}
        <div className="mb-8">
          <h4 className="font-medium text-gray-800 mb-3">Current Sequences</h4>
          <div className="bg-gray-50 rounded-lg border overflow-hidden">
            <table className="w-full" data-testid="bill-sequences-table">
              <thead className="bg-gray-100">
                <tr>
                  {['Document Type','Prefix','Last Used','Next Number','Format','Actions'].map(h => (
                    <th key={h} className={`px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${h==='Actions'?'text-center':'text-left'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {billSequences.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="px-4 py-8 text-center text-gray-500">
                      No sequences configured. Default sequences will be created automatically.
                    </td>
                  </tr>
                ) : (
                  billSequences.map((seq, idx) => (
                    <tr key={idx} className="hover:bg-brand-tint transition-colors">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{seq.label || seq.document_type}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex px-2.5 py-1 bg-blue-50 text-blue-800 text-sm font-mono rounded">{seq.prefix}</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {seq.current_sequence > 0 ? seq.current_sequence : 'Not used yet'}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-mono text-green-600">
                          {seq.prefix}-{String(seq.next_number).padStart(seq.sequence_length || 6, '0')}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {seq.prefix}-{'0'.repeat(seq.sequence_length || 6)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <AppButton
                          variant="ghost"
                          size="sm"
                          onClick={() => handleConfigure(seq)}
                          className="text-blue-600 hover:text-blue-800"
                          data-testid={`edit-sequence-${seq.document_type}`}
                        >
                          Configure
                        </AppButton>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Form */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h4 className="font-medium text-gray-800 mb-4 flex items-center gap-2">
            <Hash className="w-5 h-5 text-blue-600" />
            {editingSequence ? `Configure ${DOCUMENT_TYPE_LABELS[editingSequence] || editingSequence} Sequence` : 'Create New Sequence'}
          </h4>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label htmlFor="fld-billsequencetabjsx-127" className="block text-sm font-medium text-gray-700 mb-2">Prefix <span className="text-red-500">*</span></label>
              <input id="fld-billsequencetabjsx-127" type="text" value={form.prefix}
                onChange={(e) => setForm(p => ({ ...p, prefix: e.target.value.toUpperCase() }))}
                className="w-full px-3 py-2 border border-gray-300 rounded font-mono uppercase"
                placeholder="INV" maxLength={10} data-testid="sequence-prefix-input" />
              <p className="text-xs text-gray-500 mt-1">1-10 alphanumeric characters</p>
            </div>

            <div>
              <label htmlFor="fld-billsequencetabjsx-136" className="block text-sm font-medium text-gray-700 mb-2">Starting Number <span className="text-red-500">*</span></label>
              <input id="fld-billsequencetabjsx-136" type="number" value={form.starting_number}
                onChange={(e) => setForm(p => ({ ...p, starting_number: Math.max(1, parseInt(e.target.value) || 1) }))}
                className="w-full px-3 py-2 border border-gray-300 rounded"
                min="1" data-testid="sequence-starting-number" />
              <p className="text-xs text-gray-500 mt-1">Must be ≥ 1 and greater than last used</p>
            </div>

            <div>
              <label htmlFor="fld-billsequencetabjsx-145" className="block text-sm font-medium text-gray-700 mb-2">Sequence Length</label>
              <select id="fld-billsequencetabjsx-145" value={form.sequence_length}
                onChange={(e) => setForm(p => ({ ...p, sequence_length: parseInt(e.target.value) }))}
                className="w-full px-3 py-2 border border-gray-300 rounded"
                data-testid="sequence-length-select">
                {[3,4,5,6,7,8].map(n => <option key={n} value={n}>{n} digits (e.g., {'0'.repeat(n-1)}1)</option>)}
              </select>
            </div>

            <div>
              <span className="block text-sm font-medium text-gray-700 mb-2">Preview</span>
              <div className="w-full px-4 py-3 bg-white border-2 border-green-200 rounded font-mono text-lg text-green-700 flex items-center gap-2">
                <CheckCircle className="w-5 h-5" />
                {previewNumber}
              </div>
              <p className="text-xs text-gray-500 mt-1">This is how your next bill number will look</p>
            </div>
          </div>

          <div className="flex items-center gap-3 mt-6 pt-4 border-t border-blue-200">
            <AppButton onClick={handleSave} icon={<Save className="w-4 h-4" />} data-testid="save-sequence-btn">
              Save Sequence Settings
            </AppButton>
            {editingSequence && (
              <AppButton variant="ghost" onClick={handleCancel}>Cancel</AppButton>
            )}
          </div>
        </div>

        {/* Info Box */}
        <div className="mt-6 bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-amber-800">
            <p className="font-medium mb-1">Important Notes:</p>
            <ul className="list-disc list-inside space-y-1 text-amber-700">
              <li>Bill numbers are generated <strong>only when bills are settled/saved</strong>, not for drafts</li>
              <li>Numbers are <strong>never reused</strong>, even if a bill is cancelled</li>
              <li>Concurrent settlements are handled safely — no duplicate numbers possible</li>
              <li>Starting number must be greater than the last used number</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
