/**
 * StoreFormModal — add a pharmacy, or edit one (Settings → Organisation → Pharmacies). Same fields both ways;
 * a new pharmacy copies the creator's settings (the note below), an edit changes only these details.
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

const inputCls = 'w-full h-10 px-3 rounded-lg border border-gray-300 text-sm focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none placeholder:text-gray-400';

export interface Store {
  pharmacy_id: string; name: string; city: string; state: string; address?: string; pincode?: string;
  phone?: string; gstin?: string | null; drug_license_number?: string | null; is_active?: boolean;
}

const BLANK = { name: '', address: '', city: '', state: '', pincode: '', phone: '', gstin: '', drug_license_number: '' };

interface Props { open: boolean; store: Store | null; onClose: () => void; onSaved: () => void }

export default function StoreFormModal({ open, store, onClose, onSaved }: Props) {
  const [form, setForm] = useState(BLANK);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(store ? {
      name: store.name || '', address: store.address || '', city: store.city || '', state: store.state || '',
      pincode: store.pincode || '', phone: store.phone || '', gstin: store.gstin || '',
      drug_license_number: store.drug_license_number || '',
    } : BLANK);
  }, [open, store]);

  const set = (k: keyof typeof BLANK, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (store) await api.put(apiUrl.chainStore(store.pharmacy_id), form);
      else await api.post(apiUrl.chainStores(), form);
      toast.success(store ? 'Pharmacy saved' : 'Pharmacy added');
      onSaved();
      onClose();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const label = 'block text-xs font-medium text-gray-700 mb-1';
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>{store ? 'Edit Pharmacy' : 'Add Pharmacy'}</DialogTitle></DialogHeader>
        {!store && (
          <p className="text-xs text-gray-500 -mt-2">
            This pharmacy's branding, GST defaults, and thresholds will be copied to the new
            one — invoice and return numbering always starts fresh there, as GST requires.
          </p>
        )}
        <form onSubmit={submit} className="space-y-4 mt-2" data-testid="store-form">
          <div><label htmlFor="store-name" className={label}>Store Name *</label>
            <input id="store-name" value={form.name} onChange={(e) => set('name', e.target.value)} className={inputCls} required /></div>
          <div><label htmlFor="store-phone" className={label}>Phone *</label>
            <input id="store-phone" value={form.phone} onChange={(e) => set('phone', e.target.value)} className={inputCls} maxLength={10} required /></div>
          <div><label htmlFor="store-address" className={label}>Address *</label>
            <input id="store-address" value={form.address} onChange={(e) => set('address', e.target.value)} className={inputCls} required /></div>
          <div className="grid grid-cols-3 gap-3">
            <div><label htmlFor="store-city" className={label}>City *</label>
              <input id="store-city" value={form.city} onChange={(e) => set('city', e.target.value)} className={inputCls} required /></div>
            <div><label htmlFor="store-state" className={label}>State *</label>
              <input id="store-state" value={form.state} onChange={(e) => set('state', e.target.value)} className={inputCls} required /></div>
            <div><label htmlFor="store-pincode" className={label}>Pincode *</label>
              <input id="store-pincode" value={form.pincode} onChange={(e) => set('pincode', e.target.value)} className={inputCls} maxLength={6} required /></div>
          </div>
          <div><label htmlFor="store-gstin" className={label}>GSTIN</label>
            <input id="store-gstin" value={form.gstin} onChange={(e) => set('gstin', e.target.value.toUpperCase())} className={inputCls} maxLength={15} placeholder="This store's own GST registration" /></div>
          <div><label htmlFor="store-dl" className={label}>Drug License Number</label>
            <input id="store-dl" value={form.drug_license_number} onChange={(e) => set('drug_license_number', e.target.value)} className={inputCls} /></div>
          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <AppButton type="button" variant="secondary" onClick={onClose}>Cancel</AppButton>
            <AppButton type="submit" loading={saving} data-testid="store-save-btn">{store ? 'Save' : 'Add Pharmacy'}</AppButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
