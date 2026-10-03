import React, { useState, useEffect } from 'react';
import { Plus, Key } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { InlineLoader, ConfirmDialog, SearchInput, AppButton } from '@/components/shared';
import { useDebounce } from '@/hooks/useDebounce';
import usePagination from '@/hooks/usePagination';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import MembersTable from './MembersTable';
import StoreAccessModal from './StoreAccessModal';
import AdminCheckbox from './AdminCheckbox';

const inputCls = 'w-full h-10 px-3 rounded-lg border border-gray-300 text-sm focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none placeholder:text-gray-400';

export default function MembersTab({ currentUser }) {
  const [users, setUsers]           = useState([]);
  const [loading, setLoading]       = useState(true);
  const [availableRoles, setAvailableRoles] = useState([]);

  const [showAddDialog, setShowAddDialog]         = useState(false);
  const [showEditDialog, setShowEditDialog]       = useState(false);
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [showResetDialog, setShowResetDialog]     = useState(false);
  const [resetTarget, setResetTarget]             = useState(null);
  const [selectedUser, setSelectedUser]           = useState(null);
  const [deactivateDialog, setDeactivateDialog]   = useState({ open: false, userId: null, loading: false });
  const [storeAccessMember, setStoreAccessMember] = useState(null);

  const [formData, setFormData]     = useState({ name: '', email: '', password: '', role: '', is_admin: false });
  const [passwordData, setPasswordData] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [resetData, setResetData] = useState({ new_password: '', confirm_password: '' });
  const [searchQuery, setSearchQuery] = useState('');
  // Admin is a checkbox now, not a role — only offered as a role when the member being edited already has it.
  const memberRoles = availableRoles.filter((r) => r.name !== 'admin' || (showEditDialog && r.name === selectedUser?.role));
  const debouncedSearch = useDebounce(searchQuery, 300);
  const pg = usePagination({ pageSize: 15 });

  useEffect(() => { fetchUsers(); fetchRoles(); }, []);

  const fetchUsers = async () => {
    try { const res = await api.get(apiUrl.users()); setUsers(res.data); }
    catch { toast.error('Failed to load users'); }
    finally { setLoading(false); }
  };

  const fetchRoles = async () => {
    try { const res = await api.get(apiUrl.roles()); setAvailableRoles(res.data); }
    catch { /* silent */ }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    try {
      await api.post(apiUrl.users(), formData);
      toast.success('User created successfully');
      setShowAddDialog(false);
      setFormData({ name: '', email: '', password: '', role: '', is_admin: false });
      fetchUsers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to create user'); }
  };

  const handleEditUser = async (e) => {
    e.preventDefault();
    try {
      await api.put(apiUrl.user(selectedUser.id), { name: formData.name, email: formData.email, role: formData.role, is_admin: formData.is_admin });
      toast.success('User updated successfully');
      setShowEditDialog(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to update user'); }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (passwordData.new_password !== passwordData.confirm_password) { toast.error('Passwords do not match'); return; }
    if (passwordData.new_password.length < 6) { toast.error('Minimum 6 characters'); return; }
    try {
      await api.put(apiUrl.changePassword(), { current_password: passwordData.current_password, new_password: passwordData.new_password });
      toast.success('Password changed successfully');
      setShowPasswordDialog(false);
      setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to change password'); }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (resetData.new_password !== resetData.confirm_password) { toast.error('Passwords do not match'); return; }
    if (resetData.new_password.length < 6) { toast.error('Minimum 6 characters'); return; }
    try {
      await api.put(apiUrl.resetUserPassword(resetTarget.id), { new_password: resetData.new_password });
      toast.success(`Password reset for ${resetTarget.name}. Share the new password with them directly.`);
      setShowResetDialog(false);
      setResetTarget(null);
      setResetData({ new_password: '', confirm_password: '' });
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to reset password'); }
  };

  const confirmDeactivate = async () => {
    setDeactivateDialog((p) => ({ ...p, loading: true }));
    try {
      await api.delete(apiUrl.user(deactivateDialog.userId));
      toast.success('User deactivated');
      setDeactivateDialog({ open: false, userId: null, loading: false });
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to deactivate user');
      setDeactivateDialog((p) => ({ ...p, loading: false }));
    }
  };

  const filteredUsers = users.filter((u) => {
    if (!debouncedSearch) return true;
    const q = debouncedSearch.toLowerCase();
    return u.name?.toLowerCase().includes(q) || u.email?.toLowerCase().includes(q);
  });

  useEffect(() => {
    pg.resetPage(); pg.setTotal(filteredUsers.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, users.length]);

  const handleEditClick = (u) => { setSelectedUser(u); setFormData({ name: u.name, email: u.email, role: u.role, is_admin: !!u.is_admin, password: '' }); setShowEditDialog(true); };

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <SearchInput value={searchQuery} onChange={setSearchQuery} placeholder="Search members..." className="w-60" />
        <div className="flex items-center gap-2">
          <AppButton variant="outline" icon={<Key className="h-4 w-4" strokeWidth={1.5} />} onClick={() => setShowPasswordDialog(true)}>Change Password</AppButton>
          <AppButton icon={<Plus className="h-4 w-4" strokeWidth={1.5} />} onClick={() => { setFormData({ name: '', email: '', password: '', role: '', is_admin: false }); setShowAddDialog(true); }}>Invite Member</AppButton>
        </div>
      </div>

      {loading ? (
        <div className="py-16 flex items-center justify-center bg-white rounded-xl border border-gray-200">
          <InlineLoader text="Loading members..." />
        </div>
      ) : (
        <MembersTable users={pg.slice(filteredUsers)} loading={loading} currentUser={currentUser} pagination={pg}
          onEdit={handleEditClick} onDeactivate={(id) => setDeactivateDialog({ open: true, userId: id, loading: false })}
          onActivate={async (id) => { try { await api.put(apiUrl.user(id), { is_active: true }); toast.success('User activated'); fetchUsers(); } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); } }}
          onResetPassword={(u) => { setResetTarget(u); setResetData({ new_password: '', confirm_password: '' }); setShowResetDialog(true); }}
          onStoreAccess={(u) => setStoreAccessMember(u)} />
      )}

      <StoreAccessModal
        member={storeAccessMember}
        open={!!storeAccessMember}
        onClose={() => setStoreAccessMember(null)}
      />

      {/* Invite Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Invite Member</DialogTitle></DialogHeader>
          <form onSubmit={handleAddUser} className="space-y-4 mt-2">
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Name *</label><input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className={inputCls} required /></div>
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Email *</label><input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className={inputCls} required /></div>
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Password *</label><input type="password" value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} className={inputCls} required minLength={6} /><p className="text-xs text-gray-500 mt-1">Minimum 6 characters</p></div>
            <div><label htmlFor="member-role" className="block text-xs font-medium text-gray-700 mb-1">Role *</label><select id="member-role" value={formData.role} onChange={(e) => setFormData({ ...formData, role: e.target.value })} className={inputCls} required><option value="">Select a role…</option>{memberRoles.map((r) => <option key={r.id} value={r.name}>{r.display_name}</option>)}</select></div>
            <AdminCheckbox checked={formData.is_admin} onChange={(v) => setFormData({ ...formData, is_admin: v })} />
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowAddDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Create Member</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Member</DialogTitle></DialogHeader>
          <form onSubmit={handleEditUser} className="space-y-4 mt-2">
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Name *</label><input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className={inputCls} required /></div>
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Email *</label><input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} className={inputCls} required /></div>
            <div><label htmlFor="member-role" className="block text-xs font-medium text-gray-700 mb-1">Role *</label><select id="member-role" value={formData.role} onChange={(e) => setFormData({ ...formData, role: e.target.value })} className={inputCls} required><option value="">Select a role…</option>{memberRoles.map((r) => <option key={r.id} value={r.name}>{r.display_name}</option>)}</select></div>
            <AdminCheckbox checked={formData.is_admin} disabled={selectedUser?.id === currentUser.id} onChange={(v) => setFormData({ ...formData, is_admin: v })} />
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowEditDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Update Member</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Change Password Dialog */}
      <Dialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Change My Password</DialogTitle></DialogHeader>
          <form onSubmit={handleChangePassword} className="space-y-4 mt-2">
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Current Password *</label><input type="password" value={passwordData.current_password} onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })} className={inputCls} required /></div>
            <div><label className="block text-xs font-medium text-gray-700 mb-1">New Password *</label><input type="password" value={passwordData.new_password} onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })} className={inputCls} required minLength={6} /></div>
            <div><label className="block text-xs font-medium text-gray-700 mb-1">Confirm New Password *</label><input type="password" value={passwordData.confirm_password} onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })} className={inputCls} required minLength={6} /></div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowPasswordDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Change Password</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog — admin sets a new password directly for
          another member, no email/token infra needed (unlike a future
          self-service "forgot password" flow) */}
      <Dialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reset Password{resetTarget ? ` for ${resetTarget.name}` : ''}</DialogTitle></DialogHeader>
          <form onSubmit={handleResetPassword} className="space-y-4 mt-2">
            <p className="text-xs text-gray-500">
              Set a new password for this member. Share it with them directly — there is no email notification.
            </p>
            <div><label htmlFor="reset-new-password" className="block text-xs font-medium text-gray-700 mb-1">New Password *</label><input id="reset-new-password" type="password" value={resetData.new_password} onChange={(e) => setResetData({ ...resetData, new_password: e.target.value })} className={inputCls} required minLength={6} /></div>
            <div><label htmlFor="reset-confirm-password" className="block text-xs font-medium text-gray-700 mb-1">Confirm New Password *</label><input id="reset-confirm-password" type="password" value={resetData.confirm_password} onChange={(e) => setResetData({ ...resetData, confirm_password: e.target.value })} className={inputCls} required minLength={6} /></div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowResetDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Reset Password</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={deactivateDialog.open} onClose={() => setDeactivateDialog({ open: false, userId: null, loading: false })} onConfirm={confirmDeactivate}
        title="Deactivate Member?" description="They will no longer be able to sign in." confirmLabel="Deactivate" isDestructive isLoading={deactivateDialog.loading} />
    </>
  );
}
