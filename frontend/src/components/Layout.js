/**
 * Layout — App shell with design-system-compliant sidebar
 *
 * Spec (SKILL.md):
 *   bg: #1a2332 · width: 200px · inactive: text-gray-300 · hover: bg-white/5
 *   active: bg-blue-600/20 text-white · font: 13px font-medium · item h: 36px
 *   groups: DAILY OPS / RELATIONSHIPS / REPORTS / COMPLIANCE / ADMIN
 */
import React, { useContext, useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AuthContext } from '@/App';
import { AppButton } from '@/components/shared';
import SidebarNav from '@/components/SidebarNav';
import PlaceSwitcher from '@/components/PlaceSwitcher';
import { visibleNavModules, ROLE_BADGE, ROLE_LABEL } from '@/components/navConfig';
import {
  LogOut,
  Menu,
  X,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';

const SIDEBAR_COLLAPSED_KEY = 'pharmacare_sidebar_collapsed';

const BRAND_ICON_PATH = 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z';

// Hoisted out of Layout() — a component defined inside a parent's render
// body gets recreated (and thus remounted) on every render, which was
// silently resetting this sidebar's own state each time (react-hooks/
// static-components). Takes everything it needs as props instead of
// closing over Layout()'s locals.
function SidebarShell({ collapsed, visibleGroups, user, roleBadge, roleLabel, onToggleCollapsed, onCloseMobile, onLogout }) {
  return (
    <div className="flex flex-col h-full">

      {/* Logo strip */}
      <div className={`flex items-center gap-2 h-14 border-b border-white/10 flex-shrink-0 ${collapsed ? 'px-2 justify-center' : 'px-3'}`}>
        <div className="w-7 h-7 bg-brand rounded-md flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={BRAND_ICON_PATH} />
          </svg>
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white leading-tight">PharmaCare</p>
            <p className="text-[10px] text-gray-400 leading-tight">v1.0</p>
          </div>
        )}
        {/* Collapse toggle — desktop only, mobile drawer always stays expanded */}
        <AppButton
          variant="ghost"
          iconOnly
          className="hidden md:inline-flex h-auto p-1 text-gray-400 hover:text-white hover:bg-white/5"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          data-testid="sidebar-collapse-toggle"
          icon={collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        />
        {/* Mobile close */}
        <AppButton
          variant="ghost"
          iconOnly
          className="md:hidden h-auto p-0 text-gray-400 hover:text-white hover:bg-transparent"
          onClick={onCloseMobile}
          aria-label="Close menu"
          icon={<X className="w-4 h-4" />}
        />
      </div>

      <SidebarNav modules={visibleGroups} collapsed={collapsed} />

      {/* User footer */}
      <div className="flex-shrink-0 border-t border-white/10 px-3 py-3">
        <div className={`flex items-center gap-2 mb-2 ${collapsed ? 'justify-center' : ''}`}>
          <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center flex-shrink-0">
            <span className="text-[11px] font-semibold text-gray-300">
              {user?.name?.charAt(0)?.toUpperCase() ?? '?'}
            </span>
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-white truncate leading-tight" data-testid="user-name">
                {user?.name}
              </p>
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${roleBadge}`} data-testid="user-role">
                {roleLabel}
              </span>
            </div>
          )}
        </div>
        <AppButton
          variant="ghost"
          onClick={onLogout}
          data-testid="logout-btn"
          aria-label="Logout"
          className={`w-full h-8 [@media(pointer:coarse)]:h-11 rounded-lg text-[13px] font-medium text-gray-400 hover:text-white hover:bg-white/5 ${collapsed ? 'justify-center px-0' : 'justify-start gap-2 px-3'}`}
          icon={<LogOut className="w-4 h-4 flex-shrink-0" />}
        >
          {!collapsed && 'Logout'}
        </AppButton>
      </div>
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useContext(AuthContext);
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'; } catch { return false; }
  });

  const toggleSidebarCollapsed = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? '1' : '0'); } catch { /* per-viewer convenience only */ }
      return next;
    });
  };

  // Close the mobile drawer on navigation. Adjusted during render (not an
  // effect) — same pattern MoreFiltersDrawer.tsx uses for its own
  // open-triggered reset — avoids the extra render an effect-based
  // setState would cause, and satisfies react-hooks/set-state-in-effect.
  const [prevPathname, setPrevPathname] = useState(location.pathname);
  if (location.pathname !== prevPathname) {
    setPrevPathname(location.pathname);
    setSidebarOpen(false);
  }

  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') setSidebarOpen(false); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const roleBadge = ROLE_BADGE[user?.role] ?? 'bg-gray-100 text-gray-600';
  const roleLabel = ROLE_LABEL[user?.role] ?? (user?.role ?? '');

  // Filter each group's items by role (admins see all), drop groups with no visible items
  const visibleGroups = visibleNavModules(user);

  return (
    <div className="app-shell flex h-screen bg-page overflow-hidden">

      {/* ── Desktop sidebar ────────────────────────────────────────────── */}
      <aside
        className={`hidden md:flex ${sidebarCollapsed ? 'w-[64px]' : 'w-[200px]'} bg-sidebar flex-col flex-shrink-0 transition-[width] duration-200`}
        data-testid="sidebar"
      >
        <SidebarShell
          collapsed={sidebarCollapsed}
          visibleGroups={visibleGroups}
          user={user}
          roleBadge={roleBadge}
          roleLabel={roleLabel}
          onToggleCollapsed={toggleSidebarCollapsed}
          onCloseMobile={() => setSidebarOpen(false)}
          onLogout={logout}
        />
      </aside>

      {/* ── Mobile overlay ─────────────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Mobile drawer ──────────────────────────────────────────────── */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-[200px] bg-sidebar flex flex-col flex-shrink-0
          transform transition-transform duration-200 ease-in-out md:hidden
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        data-testid="mobile-sidebar"
        aria-label="Mobile navigation"
      >
        <SidebarShell
          collapsed={false}
          visibleGroups={visibleGroups}
          user={user}
          roleBadge={roleBadge}
          roleLabel={roleLabel}
          onToggleCollapsed={toggleSidebarCollapsed}
          onCloseMobile={() => setSidebarOpen(false)}
          onLogout={logout}
        />
      </aside>

      {/* ── Main area ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Desktop top bar — where you are working (clinic / pharmacy) */}
        <header className="hidden md:flex items-center gap-3 px-6 h-12 bg-white border-b border-gray-200 flex-shrink-0" data-testid="top-bar">
          <PlaceSwitcher />
        </header>

        {/* Mobile top bar */}
        <header className="md:hidden flex items-center gap-3 px-4 h-14 bg-sidebar border-b border-white/10 flex-shrink-0">
          <AppButton
            variant="ghost"
            iconOnly
            onClick={() => setSidebarOpen(true)}
            className="h-auto p-0 text-gray-400 hover:text-white hover:bg-transparent"
            aria-label="Open menu"
            data-testid="hamburger-btn"
            icon={<Menu className="w-5 h-5" />}
          />
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-brand rounded flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-white">PharmaCare</span>
          </div>
          <div className="flex-1" />
          <PlaceSwitcher />
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${roleBadge}`}>{roleLabel}</span>
        </header>

        <main className="app-main flex-1 overflow-auto" data-testid="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
