import React from 'react';
import { Printer } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';

export default function SalesReturnFinaliseModal({ open, onClose, totals, note, onNoteChange, onSave, isSaving }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>Invoice Breakdown</DialogTitle></DialogHeader>
        <div className="p-6 grid grid-cols-2 gap-8">
          {/* Amounts */}
          <div className="space-y-2">
            {[
              { label: 'MRP Total',       value: formatCurrency(totals.mrpTotal) },
              { label: 'Total Discount',  value: formatCurrency(-totals.totalDiscount), cls: 'text-red-500' },
              { label: 'Bill Amount',     value: formatCurrency(totals.mrpTotal - totals.totalDiscount) },
              { label: 'Round off',       value: formatCurrency(totals.netAmount - (totals.mrpTotal - totals.totalDiscount + totals.gstAmount)) },
              { label: 'Net Amount',      value: formatCurrency(totals.netAmount) },
              { label: 'GST',             value: formatCurrency(totals.gstAmount) },
            ].map((row) => (
              <div key={row.label} className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">{row.label}</span>
                <span className={`text-sm font-semibold ${row.cls || ''}`}>{row.value}</span>
              </div>
            ))}
            <div className="pt-4 mt-4 border-t border-gray-200 flex justify-between items-center">
              <span className="text-base font-bold text-gray-900">Net Refund</span>
              <span className="text-xl font-semibold tabular-nums text-red-600">{formatCurrency(totals.netAmount)}</span>
            </div>
          </div>
          {/* Note */}
          <div>
            <label htmlFor="fld-salesreturnfinalisemodaljsx-35" className="block text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Note</label>
            <textarea id="fld-salesreturnfinalisemodaljsx-35" value={note} onChange={(e) => onNoteChange(e.target.value.slice(0, 150))}
              placeholder="Add a note for this return..."
              className="w-full h-40 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-1 focus:ring-brand"
              data-testid="note-input" />
            <div className="text-right text-xs text-gray-400 mt-1">{note.length}/150</div>
          </div>
        </div>
        <DialogFooter>
          <AppButton variant="secondary" onClick={onClose}>Cancel</AppButton>
          <AppButton variant="outline" icon={<Printer className="w-4 h-4" strokeWidth={1.5} />} onClick={() => onSave(true)} loading={isSaving}>Save & Print</AppButton>
          <AppButton onClick={() => onSave(false)} loading={isSaving} data-testid="submit-btn">Submit</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
