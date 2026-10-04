/**
 * StoresTab — Settings → Organisation → Pharmacies. Add another pharmacy, turning a standalone
 * pharmacy into a chain (docs/26_MULTI_CHAIN_SCOPE.md Step 3). Clinics are separate (docs/32).
 * Adding follows the `pharmacies:create` tick. No persisted settings — self-contained action, same
 * pattern as DataBackupTab (no generic "Save Settings" button shown for this tab).
 */
import React, { useContext, useEffect, useState } from 'react';
import { Plus, Building2 } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton, InlineLoader } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { AuthContext } from '@/App';
import { hasPermission } from '@/utils/clinicAccess';

const inputCls = 'w-full h-10 px-3 rounded-lg border border-gray-300 text-sm focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none placeholder:text-gray-400';

const BLANK_STORE = {
  name: '', address: '', city: '', state: '', pincode: '', phone: '', email: '',
  gstin: '', drug_license_number: '',
};

interface Store { pharmacy_id: string; name: string; city: string; state: string; }

export default function StoresTab() {
  const user = (useContext(AuthContext) as unknown as { user?: { role?: string; is_super_admin?: boolean; permissions?: string[] } | null } | null)?.user;
  const canCreate = !!user && (user.role === 'admin' || !!user.is_super_admin || hasPermission(user.permissions, 'pharmacies:create'));
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(BLANK_STORE);

  const fetchStores = async () => {
    try {
      const res = await api.get(apiUrl.chainStores());
      setStores(res.data || []);
    } catch (error: any) {
      toast.error(error.message || 'Could not load pharmacies');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStores(); }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(apiUrl.chainStores(), form);
      toast.success('Pharmacy added');
      setShowAdd(false);
      setForm(BLANK_STORE);
      fetchStores();
    } catch (error: any) {
      toast.error(error.message || 'Could not add the pharmacy');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold mb-1">Pharmacies</h3>
          <p className="text-sm text-gray-600">
            Add another pharmacy to turn this one into a chain. Once added, use the
            Users page to grant staff access to it. Clinics are managed separately.
          </p>
        </div>
        {canCreate && (
          <AppButton icon={<Plus className="w-4 h-4" strokeWidth={1.5} />} onClick={() => setShowAdd(true)} data-testid="add-store-btn">
            Add Pharmacy
          </AppButton>
        )}
      </div>

      {loading ? (
        <div className="py-8 flex justify-center"><InlineLoader text="Loading pharmacies..." /></div>
      ) : (
        <div className="space-y-2" data-testid="stores-list">
          {stores.map(store => (
            <div key={store.pharmacy_id} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-gray-200 bg-white">
              <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center text-brand shrink-0">
                <Building2 className="w-4 h-4" strokeWidth={1.5} />
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900">{store.name}</div>
                <div className="text-xs text-gray-500">{store.city}, {store.state}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Pharmacy</DialogTitle></DialogHeader>
          <p className="text-xs text-gray-500 -mt-2">
            This pharmacy's branding, GST defaults, and thresholds will be copied to the new
            one — invoice and return numbering always starts fresh there, as GST requires.
          </p>
          <form onSubmit={handleAdd} className="space-y-4 mt-2">
            <div><label htmlFor="store-name" className="block text-xs font-medium text-gray-700 mb-1">Store Name *</label>
              <input id="store-name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={inputCls} required /></div>
            <div><label htmlFor="store-phone" className="block text-xs font-medium text-gray-700 mb-1">Phone *</label>
              <input id="store-phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={inputCls} maxLength={10} required /></div>
            <div><label htmlFor="store-address" className="block text-xs font-medium text-gray-700 mb-1">Address *</label>
              <input id="store-address" value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} className={inputCls} required /></div>
            <div className="grid grid-cols-3 gap-3">
              <div><label htmlFor="store-city" className="block text-xs font-medium text-gray-700 mb-1">City *</label>
                <input id="store-city" value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} className={inputCls} required /></div>
              <div><label htmlFor="store-state" className="block text-xs font-medium text-gray-700 mb-1">State *</label>
                <input id="store-state" value={form.state} onChange={e => setForm({ ...form, state: e.target.value })} className={inputCls} required /></div>
              <div><label htmlFor="store-pincode" className="block text-xs font-medium text-gray-700 mb-1">Pincode *</label>
                <input id="store-pincode" value={form.pincode} onChange={e => setForm({ ...form, pincode: e.target.value })} className={inputCls} maxLength={6} required /></div>
            </div>
            <div><label htmlFor="store-gstin" className="block text-xs font-medium text-gray-700 mb-1">GSTIN</label>
              <input id="store-gstin" value={form.gstin} onChange={e => setForm({ ...form, gstin: e.target.value.toUpperCase() })} className={inputCls} maxLength={15} placeholder="This store's own GST registration" /></div>
            <div><label htmlFor="store-dl" className="block text-xs font-medium text-gray-700 mb-1">Drug License Number</label>
              <input id="store-dl" value={form.drug_license_number} onChange={e => setForm({ ...form, drug_license_number: e.target.value })} className={inputCls} /></div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowAdd(false)}>Cancel</AppButton>
              <AppButton type="submit" loading={saving}>Add Pharmacy</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
