/**
 * SidebarNav — the main sidebar, one folding section per module (EMR / Pharmacy / Admin).
 * The module you are in is open; click another module's heading to fold that one open instead.
 * Collapsed (icons only): a flat icon list with a thin divider between modules, tooltip = item name
 * (Sep 21, 2026 request). Modules: docs/27_PLATFORM_MODULE_MAP.md.
 */
import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { moduleForPath } from '@/components/navConfig';
import { AppButton } from '@/components/shared';

// tooltip.jsx is untyped plain JS — same cast BackdatedBadge.tsx uses.
const TooltipContentAny = TooltipContent as unknown as React.FC<{ children?: React.ReactNode; side?: string }>;

interface NavItem {
  name: string;
  path: string;
  testId?: string;
  icon: React.ComponentType<{ className?: string }>;
}
interface NavModule {
  id: string;
  label: string;
  dot: string;
  items: NavItem[];
}

interface Props {
  modules: NavModule[];
  collapsed: boolean;
}

export default function SidebarNav({ modules, collapsed }: Props) {
  const { pathname } = useLocation();
  // A manual fold/unfold only lasts until the next page change; then the module you are in opens.
  const [picked, setPicked] = useState<{ id: string | null; path: string } | null>(null);
  const routeModule = moduleForPath(pathname);
  const openId = picked && picked.path === pathname ? picked.id : routeModule;

  const linkFor = (item: NavItem) => (
    <NavLink
      to={item.path}
      data-testid={item.testId ?? `nav-${item.name.toLowerCase().replace(/\s+/g, '-')}`}
      className={({ isActive }) =>
        `flex items-center gap-2.5 h-9 [@media(pointer:coarse)]:h-11 rounded-lg transition-colors text-[13px] font-medium mb-0.5 ${
          collapsed ? 'justify-center px-0' : 'px-3'
        } ${isActive ? 'bg-blue-600/20 text-white' : 'text-gray-300 hover:bg-white/5 hover:text-white'}`
      }
    >
      {({ isActive }) => (
        <>
          <item.icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-gray-400'}`} />
          {!collapsed && <span>{item.name}</span>}
        </>
      )}
    </NavLink>
  );

  if (collapsed) {
    return (
      <nav className="flex-1 overflow-y-auto py-2 px-2" aria-label="Main">
        <TooltipProvider>
          {modules.map((m, idx) => (
            <div key={m.id} className={idx > 0 ? 'mt-2 pt-2 border-t border-white/10' : ''}>
              {m.items.map((item) => (
                <Tooltip key={item.path}>
                  {/* A plain div is a safer asChild ref target than NavLink (see BackdatedBadge.tsx). */}
                  <TooltipTrigger asChild><div>{linkFor(item)}</div></TooltipTrigger>
                  <TooltipContentAny side="right">{item.name}</TooltipContentAny>
                </Tooltip>
              ))}
            </div>
          ))}
        </TooltipProvider>
      </nav>
    );
  }

  return (
    <nav className="flex-1 overflow-y-auto py-2 px-2" aria-label="Main">
      {modules.map((m) => {
        const open = openId === m.id;
        return (
          <div key={m.id} className="mb-1" data-testid={`nav-module-${m.id}`}>
            <AppButton
              variant="ghost"
              aria-expanded={open}
              onClick={() => setPicked({ id: open ? null : m.id, path: pathname })}
              className="w-full justify-start gap-2.5 h-9 [@media(pointer:coarse)]:h-11 px-2 text-[13px] font-semibold text-gray-200 hover:bg-white/5 hover:text-white"
            >
              <span className={`w-[22px] h-[22px] rounded-md grid place-items-center text-[11px] font-bold text-white flex-shrink-0 ${m.dot}`}>
                {m.label[0]}
              </span>
              {m.label}
              <ChevronRight className={`w-3.5 h-3.5 ml-auto text-gray-400 transition-transform ${open ? 'rotate-90' : ''}`} strokeWidth={1.5} />
            </AppButton>
            {open && (
              <div className="ml-[19px] mt-0.5 mb-1 pl-2.5 border-l border-white/10">
                {m.items.map((item) => <div key={item.path}>{linkFor(item)}</div>)}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
