/**
 * SupplierPaymentModal — record a payment against a supplier.
 * Props:
 *   supplier   {object}
 *   onClose    {() => void}
 *   onConfirm  {(amount, note) => void}
 */
import React, { useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';

export default function SupplierPaymentModal({ supplier, onClose, onConfirm }) {
  const [amount, setAmount] = useState('');
  const [note,   setNote]   = useState('');

  const cls = 'w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand';

  const handleSubmit = () => {
    if (!amount || parseFloat(amount) <= 0) { toast.error('Please enter a valid amount'); return; }
    onConfirm(amount, note);
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Record Payment</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-xs text-gray-500">Current Outstanding</div>
            <div className="text-xl font-bold font-mono text-red-600">
              {formatCurrency(supplier?.outstanding || 0)}
            </div>
          </div>

          <div>
            <label htmlFor="fld-supplierpaymentmodaljsx-41" className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Payment Amount *</label>
            <input id="fld-supplierpaymentmodaljsx-41" type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
              max={supplier?.outstanding || 0}
              className={`${cls} font-mono`} placeholder="0.00"
              data-testid="payment-amount-input" />
          </div>

          <div>
            <label htmlFor="fld-supplierpaymentmodaljsx-49" className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Note</label>
            <textarea id="fld-supplierpaymentmodaljsx-49" value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              className={`${cls} resize-none`} placeholder="Optional note..." />
          </div>
        </div>

        <DialogFooter>
          <AppButton variant="secondary" onClick={onClose}>Cancel</AppButton>
          <AppButton onClick={handleSubmit} data-testid="confirm-payment-btn">Record Payment</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
