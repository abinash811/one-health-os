import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';

export default function SalesReturnEditModal({ open, onClose, editForm, onFormChange, onSaveNonFinancial, onFinancialEdit, isSaving, allowFinancialEdit }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Edit Sales Return</DialogTitle></DialogHeader>
        <div className="p-6 space-y-4">
          {/* Non-Financial */}
          <div className="p-4 bg-gray-50 rounded-lg space-y-3">
            <h3 className="text-sm font-semibold text-gray-700">Non-Financial Edit</h3>
            <p className="text-xs text-gray-500">Edit doctor or note without changing amounts.</p>
            <div>
              <label htmlFor="fld-salesreturneditmodaljsx-16" className="block text-xs font-medium text-gray-600 mb-1">Doctor</label>
              <input id="fld-salesreturneditmodaljsx-16" type="text" value={editForm.doctor} onChange={(e) => onFormChange({ ...editForm, doctor: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-brand" placeholder="Doctor name" />
            </div>
            <div>
              <label htmlFor="fld-salesreturneditmodaljsx-21" className="block text-xs font-medium text-gray-600 mb-1">Note</label>
              <textarea id="fld-salesreturneditmodaljsx-21" value={editForm.note} onChange={(e) => onFormChange({ ...editForm, note: e.target.value.slice(0, 150) })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none h-20 focus:outline-none focus:ring-1 focus:ring-brand"
                placeholder="Add a note..." />
            </div>
            <AppButton onClick={onSaveNonFinancial} loading={isSaving} className="w-full">Save Changes</AppButton>
          </div>

          {/* Financial */}
          <div className="p-4 bg-gray-50 rounded-lg">
            <h3 className="text-sm font-semibold text-gray-700 mb-1">Financial Edit</h3>
            <p className="text-xs text-gray-500 mb-3">Edit items, quantities, and amounts. Requires permission.</p>
            <AppButton
              variant={allowFinancialEdit ? 'secondary' : 'ghost'}
              disabled={!allowFinancialEdit}
              onClick={onFinancialEdit}
              className="w-full"
            >
              {allowFinancialEdit ? 'Open Financial Edit' : 'Permission Required'}
            </AppButton>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
