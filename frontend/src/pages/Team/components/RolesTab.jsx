import React, { useState, useEffect } from 'react';
import { Plus, Edit, Trash2, Shield, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { InlineLoader, DeleteConfirmDialog, AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import PermissionsMatrix from './PermissionsMatrix';

const inputCls = 'w-full h-10 px-3 rounded-lg border border-gray-300 text-sm focus:border-brand focus:ring-1 focus:ring-brand focus:outline-none placeholder:text-gray-400';

function RoleTypeBadge({ role }) {
  if (role.is_super_admin) return <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200"><Shield className="h-3 w-3" strokeWidth={1.5} />Super Admin</span>;
  if (role.is_default)     return <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">Default</span>;
  return <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200">Custom</span>;
}

export default function RolesTab() {
  const [roles, setRoles]         = useState([]);
  const [permissions, setPermissions] = useState({});
  const [loading, setLoading]     = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog]     = useState(false);
  const [selectedRole, setSelectedRole]         = useState(null);
  const [deleteDialog, setDeleteDialog]         = useState({ open: false, roleId: null, roleName: '', loading: false });
  const [formData, setFormData]   = useState({ name: '', display_name: '', selectedPermissions: [] });

  useEffect(() => { fetchRoles(); fetchPermissions(); }, []);

  const fetchRoles = async () => {
    try { const res = await api.get(apiUrl.roles()); setRoles(res.data); }
    catch { toast.error('Failed to load roles'); }
    finally { setLoading(false); }
  };

  const fetchPermissions = async () => {
    try { const res = await api.get(apiUrl.permissions()); setPermissions(res.data); }
    catch { toast.error('Failed to load permissions'); }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (formData.selectedPermissions.length === 0) { toast.error('Select at least one permission'); return; }
    try {
      await api.post(apiUrl.roles(), { name: formData.name.toLowerCase().replace(/\s+/g, '_'), display_name: formData.display_name, permissions: formData.selectedPermissions });
      toast.success('Role created successfully');
      setShowCreateDialog(false);
      setFormData({ name: '', display_name: '', selectedPermissions: [] });
      fetchRoles();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to create role'); }
  };

  const handleClone = (role) => {
    setFormData({
      name: `${role.name}_copy`,
      display_name: `${role.display_name} (Copy)`,
      selectedPermissions: [...role.permissions],
    });
    setShowCreateDialog(true);
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    if (formData.selectedPermissions.length === 0) { toast.error('Select at least one permission'); return; }
    try {
      await api.put(apiUrl.role(selectedRole.id), { display_name: formData.display_name, permissions: formData.selectedPermissions });
      toast.success('Role updated successfully');
      setShowEditDialog(false); setSelectedRole(null); fetchRoles();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to update role'); }
  };

  const confirmDelete = async () => {
    setDeleteDialog((p) => ({ ...p, loading: true }));
    try {
      await api.delete(apiUrl.role(deleteDialog.roleId));
      toast.success('Role deleted');
      setDeleteDialog({ open: false, roleId: null, roleName: '', loading: false });
      fetchRoles();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete role');
      setDeleteDialog((p) => ({ ...p, loading: false }));
    }
  };

  const togglePermission = (permId) => setFormData((p) => ({ ...p, selectedPermissions: p.selectedPermissions.includes(permId) ? p.selectedPermissions.filter((x) => x !== permId) : [...p.selectedPermissions, permId] }));
  const toggleModule = (moduleKey) => {
    const ids = permissions[moduleKey].permissions.map((p) => p.id);
    const allOn = ids.every((id) => formData.selectedPermissions.includes(id));
    setFormData((p) => ({ ...p, selectedPermissions: allOn ? p.selectedPermissions.filter((x) => !ids.includes(x)) : [...new Set([...p.selectedPermissions, ...ids])] }));
  };
  const toggleAllPermissions = () => {
    const allIds = Object.values(permissions).flatMap((mod) => mod.permissions.map((p) => p.id));
    const allOn = allIds.length > 0 && allIds.every((id) => formData.selectedPermissions.includes(id));
    setFormData((p) => ({ ...p, selectedPermissions: allOn ? [] : allIds }));
  };

  return (
    <>
      <div className="flex items-center justify-end mb-4">
        <AppButton icon={<Plus className="h-4 w-4" strokeWidth={1.5} />} onClick={() => { setFormData({ name: '', display_name: '', selectedPermissions: [] }); setShowCreateDialog(true); }}>Create Role</AppButton>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? <div className="py-16 flex items-center justify-center"><InlineLoader text="Loading roles..." /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Role</th>
                  <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Permissions</th>
                  <th scope="col" className="px-4 py-3 text-right text-[11px] font-medium text-gray-500 uppercase tracking-wider"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {roles.length === 0 ? (
                  <tr><td colSpan={4} className="py-16 text-center"><Shield className="h-12 w-12 text-gray-300 mx-auto mb-3" strokeWidth={1.5} /><p className="text-sm font-medium text-gray-900">No roles found</p><p className="text-sm text-gray-500 mt-1">Create your first custom role</p></td></tr>
                ) : roles.map((role) => (
                  <tr key={role.id} className="group h-10 border-b border-gray-100 last:border-0 hover:bg-brand-tint">
                    <td className="px-4 py-2.5"><div className="text-sm font-medium text-gray-900">{role.display_name}</div><div className="text-xs text-gray-500 font-mono">{role.name}</div></td>
                    <td className="px-4 py-2.5"><RoleTypeBadge role={role} /></td>
                    <td className="px-4 py-2.5 text-sm text-gray-500">{role.permissions.includes('*') || role.is_super_admin ? <span className="text-purple-700 font-medium">All permissions</span> : `${role.permissions.length} permissions`}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                        <AppButton variant="ghost" iconOnly icon={<Copy className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Clone ${role.display_name}`}
                          onClick={() => handleClone(role)} />
                        {!role.is_default ? (
                          <>
                            <AppButton variant="ghost" iconOnly icon={<Edit className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Edit ${role.display_name}`}
                              onClick={() => { setSelectedRole(role); setFormData({ name: role.name, display_name: role.display_name, selectedPermissions: role.permissions }); setShowEditDialog(true); }} />
                            <AppButton variant="ghost" iconOnly icon={<Trash2 className="h-4 w-4 text-red-500" strokeWidth={1.5} />} aria-label={`Delete ${role.display_name}`}
                              onClick={() => setDeleteDialog({ open: true, roleId: role.id, roleName: role.display_name, loading: false })} />
                          </>
                        ) : <span className="text-xs text-gray-400 italic pr-2">Protected</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Create Custom Role</DialogTitle></DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div><label htmlFor="fld-rolestabjsx-151" className="block text-xs font-medium text-gray-700 mb-1">Role Key *</label><input id="fld-rolestabjsx-151" type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className={inputCls} placeholder="e.g., store_manager" required /><p className="text-xs text-gray-500 mt-1">Lowercase, underscores only</p></div>
              <div><label htmlFor="fld-rolestabjsx-152" className="block text-xs font-medium text-gray-700 mb-1">Display Name *</label><input id="fld-rolestabjsx-152" type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className={inputCls} placeholder="e.g., Store Manager" required /></div>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-700 mb-2">Permissions *</p>
              <PermissionsMatrix permissions={permissions} selectedPermissions={formData.selectedPermissions} onTogglePermission={togglePermission} onToggleModule={toggleModule} onToggleAll={toggleAllPermissions} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowCreateDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Create Role</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Role</DialogTitle></DialogHeader>
          <form onSubmit={handleEdit} className="space-y-4 mt-2">
            <div><label htmlFor="fld-rolestabjsx-171" className="block text-xs font-medium text-gray-700 mb-1">Display Name *</label><input id="fld-rolestabjsx-171" type="text" value={formData.display_name} onChange={(e) => setFormData({ ...formData, display_name: e.target.value })} className={inputCls} required /></div>
            <div>
              <p className="text-xs font-medium text-gray-700 mb-2">Permissions *</p>
              <PermissionsMatrix permissions={permissions} selectedPermissions={formData.selectedPermissions} onTogglePermission={togglePermission} onToggleModule={toggleModule} onToggleAll={toggleAllPermissions} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <AppButton type="button" variant="secondary" onClick={() => setShowEditDialog(false)}>Cancel</AppButton>
              <AppButton type="submit">Update Role</AppButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog open={deleteDialog.open} onClose={() => setDeleteDialog({ open: false, roleId: null, roleName: '', loading: false })}
        onConfirm={confirmDelete} itemName={deleteDialog.roleName ? `role "${deleteDialog.roleName}"` : 'this role'} isLoading={deleteDialog.loading} />
    </>
  );
}
