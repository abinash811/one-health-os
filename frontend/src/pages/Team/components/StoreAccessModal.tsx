/**
 * StoreAccessModal — grant/revoke a team member's access to other stores
 * in the same chain (docs/26_MULTI_CHAIN_SCOPE.md Step 3). Only shows
 * chain stores beyond the admin's own — a plain standalone pharmacy has
 * exactly one store, so this modal has nothing to offer there yet
 * (MembersTable only shows the row action once a chain exists).
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton, InlineLoader } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

interface Store { pharmacy_id: string; name: string; city: string; }
interface Grant { pharmacy_id: string; pharmacy_name: string; }
interface Member { id: string; name: string; }

export default function StoreAccessModal({ member, open, onClose }: { member: Member | null; open: boolean; onClose: () => void }) {
  const [stores, setStores] = useState<Store[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyStoreId, setBusyStoreId] = useState<string | null>(null);

  const load = async () => {
    if (!member) return;
    setLoading(true);
    try {
      const [storesRes, grantsRes] = await Promise.all([
        api.get(apiUrl.chainStores()),
        api.get(apiUrl.userStoreAccess(member.id)),
      ]);
      setStores(storesRes.data || []);
      setGrants(grantsRes.data || []);
    } catch (error: any) {
      toast.error(error.message || 'Failed to load store access');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (open) load(); }, [open, member?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGrant = async (pharmacyId: string) => {
    setBusyStoreId(pharmacyId);
    try {
      await api.post(apiUrl.userStoreAccess(member!.id), { pharmacy_id: pharmacyId });
      toast.success('Store access granted');
      await load();
    } catch (error: any) {
      toast.error(error.message || 'Failed to grant store access');
    } finally {
      setBusyStoreId(null);
    }
  };

  const handleRevoke = async (pharmacyId: string) => {
    setBusyStoreId(pharmacyId);
    try {
      await api.delete(apiUrl.revokeStoreAccess(member!.id, pharmacyId));
      toast.success('Store access revoked');
      await load();
    } catch (error: any) {
      toast.error(error.message || 'Failed to revoke store access');
    } finally {
      setBusyStoreId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Store Access{member ? ` — ${member.name}` : ''}</DialogTitle></DialogHeader>
        {loading ? (
          <div className="py-8 flex justify-center"><InlineLoader text="Loading stores..." /></div>
        ) : (
          <div className="space-y-2 mt-2" data-testid="store-access-list">
            {stores.map(store => {
              const grant = grants.find(g => g.pharmacy_id === store.pharmacy_id);
              const busy = busyStoreId === store.pharmacy_id;
              return (
                <div key={store.pharmacy_id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{store.name}</div>
                    <div className="text-xs text-gray-500">{store.city}</div>
                  </div>
                  {grant ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-gray-500">Has access</span>
                      <AppButton
                        variant="ghost" size="sm" disabled={busy}
                        onClick={() => handleRevoke(store.pharmacy_id)}
                        data-testid={`revoke-store-${store.pharmacy_id}`}
                      >
                        Revoke
                      </AppButton>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 shrink-0">
                      <AppButton
                        variant="secondary" size="sm" disabled={busy}
                        onClick={() => handleGrant(store.pharmacy_id)}
                        data-testid={`grant-store-${store.pharmacy_id}`}
                      >
                        Grant
                      </AppButton>
                    </div>
                  )}
                </div>
              );
            })}
            {stores.length <= 1 && (
              <p className="text-xs text-gray-500 py-2">
                Add another store under Settings → Stores first to grant access here.
              </p>
            )}
          </div>
        )}
        <div className="flex justify-end pt-2 border-t border-gray-100 mt-2">
          <AppButton variant="secondary" onClick={onClose}>Close</AppButton>
        </div>
      </DialogContent>
    </Dialog>
  );
}
