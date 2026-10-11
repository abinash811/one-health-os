/**
 * QuickStatCard — compact stat tile with optional nav click.
 * Props:
 *   title   {string}
 *   value   {string|number}
 *   icon    {ReactNode}
 *   color   {'yellow'|'gray'|'red'|'indigo'}
 *   onClick {(() => void)|undefined}
 */
import React from 'react';
import { ArrowUpRight } from 'lucide-react';

const COLOR_CLASSES = {
  yellow: 'bg-yellow-50 border-yellow-200 text-yellow-700',
  gray:   'bg-gray-50 border-gray-200 text-gray-700',
  red:    'bg-red-50 border-red-200 text-red-700',
  indigo: 'bg-blue-50 border-blue-200 text-blue-700',
};

export default function QuickStatCard({ title, value, icon, color, onClick }) {
  const handleKeyDown = (e) => {
    if (!onClick) return;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
  };

  return (
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- role and tabIndex are applied only when onClick is given
    <div
      className={`p-4 rounded-xl border ${COLOR_CLASSES[color]} ${onClick ? 'cursor-pointer hover:shadow-md' : ''} transition-all`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={handleKeyDown}
      data-testid={`quick-stat-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs font-medium">{title}</span>
        {onClick && <ArrowUpRight className="w-3 h-3 ml-auto opacity-50" />}
      </div>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}
