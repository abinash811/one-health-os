/**
 * Settings hub — one home for every setting, a tab per module (Organisation / EMR / Pharmacy) and
 * that module's sections down the left (layout B of docs/mockups/31_settings_hub_mock.html).
 * Routes: /settings, /settings/:module, /settings/:module/:section. Only the modules and sections
 * the user may open are shown; a module that is off simply has no entry in sections.tsx's list.
 */
import React, { useContext } from 'react';
import { Navigate, NavLink, useNavigate, useParams } from 'react-router-dom';
import { AlertCircle, History } from 'lucide-react';
import { AuthContext } from '@/App';
import { AppButton, PageHeader, PageTabs } from '@/components/shared';
import { HubUser, isAdmin, settingsPath, visibleModules } from './sections';

export default function SettingsHub() {
  const { user } = useContext(AuthContext) as unknown as { user: HubUser | null };
  const navigate = useNavigate();
  const { module, section } = useParams();
  const modules = visibleModules(user);

  if (!user || modules.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center py-32" data-testid="settings-denied">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-3" strokeWidth={1.5} />
          <h2 className="text-base font-semibold text-gray-900 mb-1">Access Denied</h2>
          <p className="text-sm text-gray-500">You do not have permission to open settings.</p>
        </div>
      </div>
    );
  }

  const current = modules.find((m) => m.key === module);
  if (!current) return <Navigate to={settingsPath(modules[0].key, modules[0].sections[0].key)} replace />;
  const active = current.sections.find((s) => s.key === section);
  if (!active) return <Navigate to={settingsPath(current.key, current.sections[0].key)} replace />;

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="settings-hub">
      <PageHeader
        title="Settings"
        actions={isAdmin(user) && (
          <AppButton variant="outline" icon={<History className="w-4 h-4" strokeWidth={1.5} />}
            onClick={() => navigate('/audit-log?entity_type=settings')} data-testid="settings-history-btn">
            Change History
          </AppButton>
        )}
      />
      <PageTabs
        tabs={modules.map((m) => ({ key: m.key, label: m.label }))}
        activeTab={current.key}
        onChange={(k) => navigate(settingsPath(k))}
      />

      <div className="flex gap-6 items-start">
        <nav className="w-56 shrink-0 bg-white rounded-xl border border-gray-200 p-2" aria-label={`${current.label} settings`}>
          {current.sections.map((s) => (
            <NavLink
              key={s.key}
              to={settingsPath(current.key, s.key)}
              data-testid={`settings-nav-${s.key}`}
              className={({ isActive }) => `block px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-brand-subtle text-brand font-semibold' : 'text-gray-700 hover:bg-gray-50'}`}
            >
              {s.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex-1 min-w-0" data-testid={`settings-content-${current.key}`}>
          {current.content(active.key, user)}
        </div>
      </div>
    </div>
  );
}
