/**
 * FinaliseModal — invoice breakdown + notes + confirm-save.
 * Props:
 *   open              {boolean}
 *   onClose           {() => void}
 *   customerName      {string}
 *   paymentType       {string}
 *   paymentSplits     {Array<{method, amount}>} — split legs when paymentType === 'multiple'
 *   mrpTotal          {number}
 *   totalDiscount     {number}
 *   billDiscount      {number}
 *   billDiscountType  {'%'|'₹'}
 *   totalGst          {number}
 *   totalCess         {number}
 *   grandTotal        {number}
 *   margin            {{ amount: number, percent: number }}
 *   isSaving          {boolean}
 *   isCorrection      {boolean} — editing an already-finalized bill; the
 *     actual payment amount/method is preserved server-side and can't be
 *     changed here (see docs/15_ROADMAP.md's Billing table) — only items/
 *     pricing shown below are what's actually being saved
 *   onConfirm         {(notes: { internalNote }) => void}
 */
import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';

export default function FinaliseModal({
  open,
  onClose,
  customerName   = '',
  paymentType    = '',
  paymentSplits  = /** @type {Array<{method: string, amount: string}>} */ ([]),
  mrpTotal       = 0,
  totalDiscount  = 0,
  billDiscount   = 0,
  billDiscountType = '%',
  totalGst       = 0,
  totalCess      = 0,
  grandTotal     = 0,
  margin         = { amount: 0, percent: 0 },
  isSaving       = false,
  isCorrection   = false,
  onConfirm,
}) {
  const [internalNote, setInternalNote] = useState('');

  // Clear the note each time the modal opens. Adjusted during render (not an
  // effect) per React's own guidance on resetting state from a prop change —
  // this component stays mounted while `open` toggles, so an effect here
  // would fire a second render every time (react-hooks/set-state-in-effect).
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setInternalNote('');
  }

  const billDiscAmt = billDiscountType === '%'
    ? mrpTotal * (billDiscount / 100)
    : billDiscount;
  const itemDiscAmt = totalDiscount - billDiscAmt;
  // grandTotal (prop) is already rounded to the nearest rupee, matching
  // create_bill's own rounding — Round off is the exact delta from the raw,
  // pre-round total, same pattern as SalesReturnFinaliseModal.
  const rawTotal = mrpTotal - totalDiscount + totalGst + totalCess;
  const roundOff = grandTotal - rawTotal;

  const handleConfirm = () => onConfirm({ internalNote });

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl p-0 gap-0 max-h-[90vh] overflow-y-auto">
        <DialogHeader className="px-6 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle className="text-lg">{isCorrection ? 'Save Bill Changes' : 'Finalise Bill'}</DialogTitle>
              <p className="text-sm text-gray-500 mt-0.5">{customerName || 'Counter Sale'}</p>
            </div>
          </div>
        </DialogHeader>

        <div className="p-6">
          <div className="grid grid-cols-2 gap-8">

            {/* ── Left: Invoice breakdown ──────────────────────────── */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-4">Invoice Breakdown</h4>

              {[
                { label: 'MRP Total',       value: formatCurrency(mrpTotal),                  cls: '' },
                { label: 'Item Discounts',  value: formatCurrency(-itemDiscAmt),               cls: 'text-red-500' },
                { label: 'Bill Discount',   value: formatCurrency(-billDiscAmt),               cls: 'text-red-500' },
                { label: 'GST',             value: formatCurrency(totalGst),                  cls: '' },
                { label: 'CESS',            value: formatCurrency(totalCess),                 cls: '' },
                { label: 'Round off',       value: formatCurrency(roundOff),                  cls: '' },
              ].map(({ label, value, cls }) => (
                <div key={label} className="flex justify-between py-2 border-b border-gray-100">
                  <span className="text-sm text-gray-600">{label}</span>
                  <span className={`text-sm font-semibold ${cls}`}>{value}</span>
                </div>
              ))}

              {/* Net Payable highlight */}
              <div className="flex justify-between py-4 mt-4 bg-brand-subtle rounded-lg px-4 -mx-4">
                <span className="text-base font-bold text-gray-900">Net Payable</span>
                <span className="text-2xl font-semibold tabular-nums text-gray-900">{formatCurrency(grandTotal)}</span>
              </div>

              <div className="flex justify-between py-2 mt-2">
                <span className="text-sm text-gray-400">Margin</span>
                <span className="text-sm font-semibold text-green-600">{formatCurrency(margin.amount)}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-sm text-gray-400">Margin %</span>
                <span className="text-sm font-semibold text-green-600">{margin.percent.toFixed(1)}%</span>
              </div>
            </div>

            {/* ── Right: Notes + confirm ───────────────────────────── */}
            <div className="space-y-4">
              <div>
                <label htmlFor="fld-finalisemodaljsx-123" className="block text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Internal Note</label>
                <textarea id="fld-finalisemodaljsx-123"
                  value={internalNote}
                  onChange={(e) => setInternalNote(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand resize-none"
                  rows="4"
                  placeholder="Internal notes (not visible to customer)"
                  data-testid="internal-note"
                />
              </div>

              {isCorrection ? (
                <div className="p-3 bg-blue-50 rounded-lg" data-testid="correction-payment-note">
                  <p className="text-sm text-blue-800">
                    This saves your item/pricing correction only. The payment
                    already collected stays as-is — use Collect Payment on the
                    bill to change what's been paid.
                  </p>
                </div>
              ) : (
                <div className="p-3 bg-gray-50 rounded-lg">
                  <span className="text-xs text-gray-400 block mb-1">Payment Method</span>
                  <span className="font-semibold text-gray-700 capitalize">
                    {paymentType === 'multiple' ? 'Multi' : (paymentType || 'Not selected')}
                  </span>
                </div>
              )}

              {!isCorrection && paymentType === 'multiple' && paymentSplits.length > 0 && (
                <div className="p-3 bg-gray-50 rounded-lg space-y-1" data-testid="multi-split-summary">
                  {paymentSplits.map((s, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-gray-600 capitalize">{s.method}</span>
                      <span className="font-semibold text-gray-800">{formatCurrency(Number(s.amount) || 0)}</span>
                    </div>
                  ))}
                </div>
              )}

              <AppButton
                onClick={handleConfirm}
                loading={isSaving}
                size="lg"
                className="w-full mt-4"
                icon={<span className="material-symbols-outlined">check_circle</span>}
                data-testid="confirm-save-btn"
              >
                {isCorrection ? 'Save Changes' : 'Confirm & Save Bill'}
              </AppButton>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
