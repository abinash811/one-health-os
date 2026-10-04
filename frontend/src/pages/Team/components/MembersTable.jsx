import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Edit, XCircle, CheckCircle, Users, History, KeyRound, Building2, Stethoscope } from 'lucide-react';
import { AppButton, PaginationBar, TableSkeleton } from '@/components/shared';
import { formatDateTime } from '@/utils/dates';
import RoleBadge from './RoleBadge';

const ADMIN_ROLE = 'admin';

export default function MembersTable({ users, loading, currentUser, pagination, onEdit, onDeactivate, onActivate, onResetPassword, onStoreAccess, onClinicAccess }) {
  const navigate = useNavigate();
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Name</th>
              <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Email</th>
              <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Role</th>
              <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th scope="col" className="px-4 py-3 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">Last Active</th>
              <th scope="col" className="px-4 py-3 text-right text-[11px] font-medium text-gray-500 uppercase tracking-wider"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="p-0"><TableSkeleton rows={6} columns={6} /></td></tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-16 text-center">
                  <Users className="h-12 w-12 text-gray-300 mx-auto mb-3" strokeWidth={1.5} />
                  <p className="text-sm font-medium text-gray-900">No members found</p>
                  <p className="text-sm text-gray-500 mt-1">Invite your first user</p>
                </td>
              </tr>
            ) : users.map((u) => (
              <tr key={u.id} className="group h-10 border-b border-gray-100 last:border-0 hover:bg-brand-tint">
                <td className="px-4 py-2.5 text-sm font-medium text-gray-900">{u.name}</td>
                <td className="px-4 py-2.5 text-sm text-gray-500">{u.email}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <RoleBadge role={u.role} />
                    {u.is_admin && u.role !== 'admin' && <RoleBadge role={ADMIN_ROLE} />}
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  {u.is_active ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200">
                      <CheckCircle className="h-3 w-3" strokeWidth={1.5} /> Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200">
                      <XCircle className="h-3 w-3" strokeWidth={1.5} /> Inactive
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-sm text-gray-500">
                  {u.last_login_at ? formatDateTime(u.last_login_at) : 'Never'}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                    <AppButton variant="ghost" iconOnly icon={<History className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Login history for ${u.name}`}
                      onClick={() => navigate(`/audit-log?entity_type=auth&entity_id=${u.id}`)} />
                    <AppButton variant="ghost" iconOnly icon={<Edit className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Edit ${u.name}`}
                      onClick={() => onEdit(u)} />
                    <AppButton variant="ghost" iconOnly icon={<Building2 className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Store access for ${u.name}`}
                      onClick={() => onStoreAccess(u)} data-testid={`store-access-btn-${u.id}`} />
                    <AppButton variant="ghost" iconOnly icon={<Stethoscope className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Clinic access for ${u.name}`}
                      onClick={() => onClinicAccess(u)} data-testid={`clinic-access-btn-${u.id}`} />
                    {u.id !== currentUser.id && (
                      <AppButton variant="ghost" iconOnly icon={<KeyRound className="h-4 w-4" strokeWidth={1.5} />} aria-label={`Reset password for ${u.name}`}
                        onClick={() => onResetPassword(u)} />
                    )}
                    {u.id !== currentUser.id && (
                      u.is_active
                        ? <AppButton variant="ghost" iconOnly icon={<XCircle className="h-4 w-4 text-red-500" strokeWidth={1.5} />} aria-label={`Deactivate ${u.name}`} onClick={() => onDeactivate(u.id)} />
                        : <AppButton variant="ghost" iconOnly icon={<CheckCircle className="h-4 w-4 text-green-600" strokeWidth={1.5} />} aria-label={`Activate ${u.name}`} onClick={() => onActivate(u.id)} />
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <PaginationBar {...pagination} />
    </div>
  );
}
