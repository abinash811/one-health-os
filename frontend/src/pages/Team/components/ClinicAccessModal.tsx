/**
 * ClinicAccessModal — grant / revoke a team member's access to the workspace's clinics, with the role they
 * hold at each (docs/32_CLINICS_SCOPE.md P2). The clinic twin of StoreAccessModal. Roles are workspace-wide.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AppButton, InlineLoader } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import RoleBadge from './RoleBadge';

const selectCls = 'h-8 px-2 rounded-lg border border-gray-300 text-xs focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none';

interface Clinic { id: string; name: string; city: string | null }
interface Grant { clinic_id: string; clinic_name: string; role_name: string }
interface Role { name: string; display_name: string }
interface Member { id: string; name: string }

export default function ClinicAccessModal({ member, open, onClose }: { member: Member | null; open: boolean; onClose: () => void }) {
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingRole, setPendingRole] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!member) return;
    setLoading(true);
    try {
      const [c, g, r] = await Promise.all([
        api.get(apiUrl.clinics()), api.get(apiUrl.userClinicAccess(member.id)), api.get(apiUrl.roles()),
      ]);
      setClinics(c.data || []);
      setGrants(g.data || []);
      setRoles(r.data || []);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [member]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const defaultRole = roles.find((r) => r.name === 'receptionist')?.name || roles[0]?.name || '';

  const act = async (clinicId: string, run: () => Promise<unknown>, done: string) => {
    setBusyId(clinicId);
    try {
      await run();
      toast.success(done);
      await load();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Clinic access{member ? ` — ${member.name}` : ''}</DialogTitle></DialogHeader>
        {loading ? (
          <div className="py-8 flex justify-center"><InlineLoader text="Loading clinics..." /></div>
        ) : (
          <div className="space-y-2 mt-2" data-testid="clinic-access-list">
            {clinics.map((c) => {
              const grant = grants.find((g) => g.clinic_id === c.id);
              const busy = busyId === c.id;
              const role = pendingRole[c.id] || defaultRole;
              return (
                <div key={c.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{c.name}</div>
                    <div className="text-xs text-gray-500">{c.city || '—'}</div>
                  </div>
                  {grant ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <RoleBadge role={grant.role_name} />
                      <AppButton variant="ghost" size="sm" disabled={busy} data-testid={`revoke-clinic-${c.id}`}
                        onClick={() => act(c.id, () => api.delete(apiUrl.revokeClinicAccess(member!.id, c.id)), 'Clinic access revoked')}>
                        Revoke
                      </AppButton>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 shrink-0">
                      <select className={selectCls} value={role} data-testid={`clinic-role-${c.id}`}
                        onChange={(e) => setPendingRole((p) => ({ ...p, [c.id]: e.target.value }))}>
                        {roles.map((r) => <option key={r.name} value={r.name}>{r.display_name || r.name}</option>)}
                      </select>
                      <AppButton variant="secondary" size="sm" disabled={busy || !role} data-testid={`grant-clinic-${c.id}`}
                        onClick={() => act(c.id, () => api.post(apiUrl.userClinicAccess(member!.id), { clinic_id: c.id, role }), 'Clinic access granted')}>
                        Grant
                      </AppButton>
                    </div>
                  )}
                </div>
              );
            })}
            {clinics.length === 0 && (
              <p className="text-xs text-gray-500 py-2">Add a clinic under Settings → Organisation → Clinics first.</p>
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
