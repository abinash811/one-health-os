import React from 'react';
import { Printer } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';

export default function PurchaseReturnFinaliseModal({ open, onClose, totals, note, onNoteChange, supplierName, onSave, isSaving }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>Invoice Breakdown</DialogTitle></DialogHeader>
        <div className="p-6 grid grid-cols-2 gap-8">
          {/* Note + Supplier */}
          <div>
            <div className="mb-4 p-3 bg-gray-50 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Supplier</div>
              <div className="font-semibold text-gray-800">{supplierName}</div>
            </div>
            <label htmlFor="fld-purchasereturnfinalisemodaljsx-19" className="block text-sm font-medium text-gray-700 mb-1.5">Note</label>
            <textarea id="fld-purchasereturnfinalisemodaljsx-19" value={note} onChange={(e) => onNoteChange(e.target.value.slice(0, 150))}
              placeholder="Add a note for this return..."
              className="w-full h-32 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-1 focus:ring-brand"
              data-testid="note-input" />
            <div className="text-right text-xs text-gray-400 mt-1">{note.length}/150</div>
          </div>
          {/* Breakdown */}
          <div className="space-y-2">
            {[
              { label: 'PTR Total',   value: formatCurrency(totals.ptrTotal) },
              { label: 'GST',         value: formatCurrency(totals.gstAmount) },
              { label: 'Bill Amount', value: formatCurrency(totals.ptrTotal + totals.gstAmount) },
              { label: 'Round off',   value: formatCurrency(totals.netAmount - (totals.ptrTotal + totals.gstAmount)) },
            ].map((row) => (
              <div key={row.label} className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">{row.label}</span>
                <span className="text-sm font-semibold font-mono">{row.value}</span>
              </div>
            ))}
            <div className="pt-4 mt-4 border-t border-gray-200 flex justify-between items-center">
              <span className="text-base font-bold text-gray-900">Net Return</span>
              <span className="text-xl font-semibold tabular-nums text-red-600">{formatCurrency(totals.netAmount)}</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <AppButton variant="secondary" onClick={onClose}>Cancel</AppButton>
          <AppButton variant="outline" icon={<Printer className="w-4 h-4" strokeWidth={1.5} />} onClick={() => onSave(true)} loading={isSaving}>Save & Print</AppButton>
          <AppButton onClick={() => onSave(false)} loading={isSaving} data-testid="confirm-btn">Confirm & Save</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
