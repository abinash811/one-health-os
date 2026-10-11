import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';

export default function PurchaseReturnEditModal({ open, onClose, editType, editNote, onNoteChange, isSaving, onSave }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {editType === 'non_financial' ? 'Edit Return (Non-Financial)' : 'Edit Return (Financial)'}
          </DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-4">
          {editType === 'financial' && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
              Financial edits will recalculate stock and supplier outstanding. This action requires elevated permissions.
            </div>
          )}
          <div>
            <label htmlFor="fld-purchasereturneditmodaljsx-21" className="block text-sm font-medium text-gray-700 mb-1.5">Note</label>
            <textarea id="fld-purchasereturneditmodaljsx-21" value={editNote} onChange={(e) => onNoteChange(e.target.value.slice(0, 150))}
              placeholder="Add a note..."
              className="w-full h-24 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-1 focus:ring-brand" />
            <div className="text-right text-xs text-gray-400 mt-1">{editNote.length}/150</div>
          </div>
          {editType === 'financial' && (
            <div className="p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              To edit quantities or add/remove items, please create a new return for any differences.
            </div>
          )}
        </div>
        <DialogFooter>
          <AppButton variant="secondary" onClick={onClose}>Cancel</AppButton>
          <AppButton onClick={onSave} loading={isSaving}>Save Changes</AppButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
