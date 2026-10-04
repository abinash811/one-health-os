/**
 * StoresTab — Settings → Organisation → Pharmacies. Add another pharmacy (turning a standalone pharmacy into a
 * chain, docs/26 Step 3), edit one's details, archive or restore it. Clinics are separate (docs/32).
 * Add follows `pharmacies:create`, edit / archive `pharmacies:edit`. An archived pharmacy is hidden everywhere
 * (switcher, pickers) but never deleted — its bills and stock stay for audits.
 */
import React, { useCallback, useContext, useEffect, useState } from 'react';
import { Plus, Building2, Pencil, Archive, ArchiveRestore } from 'lucide-react';
import { toast } from 'sonner';
import { AppButton, InlineLoader } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { AuthContext } from '@/App';
import { hasPermission } from '@/utils/clinicAccess';
import StoreFormModal, { type Store } from './StoreFormModal';

type Me = { role?: string; is_super_admin?: boolean; permissions?: string[] } | null | undefined;

export default function StoresTab() {
  const user: Me = (useContext(AuthContext) as unknown as { user?: Me } | null)?.user;
  const admin = !!user && (user.role === 'admin' || !!user.is_super_admin);
  const canCreate = admin || (!!user && hasPermission(user.permissions, 'pharmacies:create'));
  const canEdit = admin || (!!user && hasPermission(user.permissions, 'pharmacies:edit'));
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Store | null>(null);

  const fetchStores = useCallback(async () => {
    try {
      const res = await api.get(`${apiUrl.chainStores()}${showArchived ? '?include_archived=true' : ''}`);
      setStores(res.data || []);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [showArchived]);

  useEffect(() => { fetchStores(); }, [fetchStores]);

  const open = (s: Store | null) => { setEditing(s); setFormOpen(true); };

  const toggleArchive = async (s: Store) => {
    const archiving = s.is_active !== false;
    try {
      await api.put(apiUrl.chainStore(s.pharmacy_id), { is_active: !archiving });
      toast.success(archiving ? `${s.name} archived` : `${s.name} is active again`);
      fetchStores();
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold mb-1">Pharmacies</h3>
          <p className="text-sm text-gray-600">
            Add another pharmacy to turn this one into a chain. Once added, use the
            Users page to grant staff access to it. Clinics are managed separately.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer whitespace-nowrap" htmlFor="show-archived-stores">
            <input id="show-archived-stores" type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 accent-brand" data-testid="show-archived-stores" />
            Show archived
          </label>
          {canCreate && (
            <AppButton icon={<Plus className="w-4 h-4" strokeWidth={1.5} />} onClick={() => open(null)} data-testid="add-store-btn">
              Add Pharmacy
            </AppButton>
          )}
        </div>
      </div>

      {loading ? (
        <div className="py-8 flex justify-center"><InlineLoader text="Loading pharmacies..." /></div>
      ) : (
        <div className="space-y-2" data-testid="stores-list">
          {stores.map((store) => {
            const archived = store.is_active === false;
            return (
              <div key={store.pharmacy_id} data-testid={`store-row-${store.pharmacy_id}`}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg border border-gray-200 bg-white ${archived ? 'opacity-70' : ''}`}>
                <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center text-brand shrink-0">
                  <Building2 className="w-4 h-4" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    {store.name}{archived && <span className="ml-2 text-xs font-normal text-gray-500">Archived</span>}
                  </div>
                  <div className="text-xs text-gray-500">{store.city}, {store.state}</div>
                </div>
                {canEdit && (
                  <div className="flex gap-1">
                    {!archived && (
                      <AppButton variant="ghost" size="sm" iconOnly icon={<Pencil className="w-4 h-4" />}
                        aria-label={`Edit ${store.name}`} onClick={() => open(store)} data-testid={`edit-store-${store.pharmacy_id}`} />
                    )}
                    <AppButton variant="ghost" size="sm" iconOnly data-testid={`archive-store-${store.pharmacy_id}`}
                      icon={archived ? <ArchiveRestore className="w-4 h-4" /> : <Archive className="w-4 h-4" />}
                      aria-label={archived ? `Restore ${store.name}` : `Archive ${store.name}`} onClick={() => toggleArchive(store)} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <StoreFormModal open={formOpen} store={editing} onClose={() => setFormOpen(false)} onSaved={fetchStores} />
    </div>
  );
}
