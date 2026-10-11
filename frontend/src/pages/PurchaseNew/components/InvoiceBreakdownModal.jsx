/**
 * InvoiceBreakdownModal — review & adjust invoice breakdown before confirming.
 * Props:
 *   breakdown         {{ ptrTotal, totalDiscount, gst, cess, billAmount,
 *                        adjustedCN, tcs, extraCharges, adjustmentAmount, roundOff, netAmount }}
 *   onUpdateBreakdown {(field, value) => void}
 *   selectedSupplier  {object|null}
 *   supplierInvoiceNo {string}
 *   totals            {{ itemCount, totalQty, totalFree }}
 *   purchaseOn        {string}
 *   dueDate           {Date|null}
 *   internalNote      {string}
 *   onInternalNote    {(string) => void}
 *   loading           {boolean}
 *   onClose           {() => void}
 *   onConfirm         {() => void}
 */
import React from 'react';
import { format } from 'date-fns';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';

const NumberInput = ({ value, onChange }) => (
  <input type="number" step="0.01" value={value} onChange={(e) => onChange(e.target.value)}
    className="w-24 px-2 py-1 text-sm text-right bg-gray-50 border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-brand" />
);

const Row = ({ label, children }) => (
  <div className="flex justify-between items-center">
    <span className="text-sm text-gray-600">{label}</span>
    {children}
  </div>
);

export default function InvoiceBreakdownModal({
  breakdown, onUpdateBreakdown,
  selectedSupplier, supplierInvoiceNo,
  totals, purchaseOn, dueDate,
  internalNote, onInternalNote,
  loading, onClose, onConfirm,
}) {
  const fmt = (d) => d ? format(d, 'dd MMM yyyy') : 'Not set';

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Invoice Breakdown</DialogTitle>
        </DialogHeader>

        <div>
          {/* Header summary */}
          <div className="grid grid-cols-2 gap-4 mb-4 pb-4 border-b border-gray-100">
            <div>
              <span className="text-xs text-gray-400">Distributor</span>
              <div className="text-sm font-semibold">{selectedSupplier?.name || '—'}</div>
            </div>
            <div>
              <span className="text-xs text-gray-400">Invoice #</span>
              <div className="text-sm font-semibold">{supplierInvoiceNo || '—'}</div>
            </div>
            <div>
              <span className="text-xs text-gray-400">Items</span>
              <div className="text-sm font-semibold">{totals.itemCount}</div>
            </div>
            <div>
              <span className="text-xs text-gray-400">Total Qty</span>
              <div className="text-sm font-semibold">{totals.totalQty} + {totals.totalFree} free</div>
            </div>
          </div>

          {/* Breakdown rows */}
          <div className="space-y-3">
            <Row label="PTR Total">
              <span className="text-sm font-semibold">{formatCurrency(breakdown.ptrTotal)}</span>
            </Row>
            <Row label="Total Discount">
              <NumberInput value={breakdown.totalDiscount} onChange={(v) => onUpdateBreakdown('totalDiscount', v)} />
            </Row>
            <Row label="GST">
              <span className="text-sm font-semibold">{formatCurrency(breakdown.gst)}</span>
            </Row>
            <Row label="CESS">
              <NumberInput value={breakdown.cess} onChange={(v) => onUpdateBreakdown('cess', v)} />
            </Row>

            <hr className="border-gray-100" />

            <Row label="Bill Amount">
              <span className="text-sm font-semibold">{formatCurrency(breakdown.billAmount)}</span>
            </Row>
            <Row label="Adjusted CN/Voucher">
              <NumberInput value={breakdown.adjustedCN} onChange={(v) => onUpdateBreakdown('adjustedCN', v)} />
            </Row>
            <Row label="TCS">
              <NumberInput value={breakdown.tcs} onChange={(v) => onUpdateBreakdown('tcs', v)} />
            </Row>
            <Row label="Extra Charges">
              <NumberInput value={breakdown.extraCharges} onChange={(v) => onUpdateBreakdown('extraCharges', v)} />
            </Row>
            <Row label="Adjustment Amount">
              <NumberInput value={breakdown.adjustmentAmount} onChange={(v) => onUpdateBreakdown('adjustmentAmount', v)} />
            </Row>
            <Row label="Round Off">
              <span className={`text-sm font-semibold ${breakdown.roundOff >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {breakdown.roundOff >= 0 ? '+' : '-'}{formatCurrency(Math.abs(breakdown.roundOff))}
              </span>
            </Row>

            <hr className="border-gray-100" />

            <Row label={<span className="text-base font-bold text-gray-800">Net Amount</span>}>
              <span className="text-lg font-semibold tabular-nums text-brand">
                {formatCurrency(breakdown.netAmount)}
              </span>
            </Row>

            {purchaseOn === 'credit' && (
              <div className="flex justify-between items-center bg-amber-50 p-2 rounded-lg">
                <span className="text-sm text-amber-700">Due Date</span>
                <span className="text-sm font-semibold text-amber-800">{fmt(dueDate)}</span>
              </div>
            )}
          </div>

          {/* Internal note */}
          <div className="mt-4">
            <label htmlFor="fld-invoicebreakdownmodaljsx-129" className="block text-xs font-semibold text-gray-500 uppercase mb-2">Internal Note</label>
            <textarea id="fld-invoicebreakdownmodaljsx-129"
              value={internalNote}
              onChange={(e) => onInternalNote(e.target.value)}
              placeholder="Add a note (optional)"
              rows={2}
              className="w-full px-3 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand"
              data-testid="internal-note"
            />
          </div>
        </div>

        <DialogFooter>
          <AppButton variant="secondary" onClick={onClose}>Cancel</AppButton>
          <AppButton loading={loading} onClick={onConfirm} data-testid="confirm-save-btn">
            Confirm &amp; Save
          </AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
