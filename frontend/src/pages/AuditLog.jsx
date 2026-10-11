/**
 * AuditLog — system activity log viewer.
 * Route: /audit-log
 *
 * Accessible by admin only.
 * Shows all system actions: bill created, stock adjusted, user changed, etc.
 */
import React, { useState, useEffect, useContext } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertCircle, RefreshCw, X } from 'lucide-react';
import {
  PageHeader, DataCard, SearchInput,
  TableSkeleton, PaginationBar,
  FilterPills, AppButton,
} from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { useDebounce } from '@/hooks/useDebounce';
import { formatDateShort, formatTime } from '@/utils/dates';
import usePagination from '@/hooks/usePagination';
import { ActionBadge, ENTITY_LABELS, ENTITY_TYPES } from './AuditLogBadges';

export default function AuditLog() {
  const { user: currentUser } = useContext(AuthContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [logs, setLogs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);

  // Filters — entity_type/entity_id can arrive pre-set via URL (e.g. a
  // "View Change History" link from Settings, or "Login History" from a
  // Team member row), so other pages can deep-link straight to a
  // filtered view instead of duplicating this table elsewhere.
  const [entityTypeFilter, setEntityTypeFilter] = useState(searchParams.get('entity_type') || 'all');
  const entityIdFilter                          = searchParams.get('entity_id') || null;
  const [searchQuery, setSearchQuery]           = useState('');
  const debouncedSearch                         = useDebounce(searchQuery, 300);

  // Pagination (server-side)
  const pg = usePagination({ pageSize: 25 });

  const fetchData = async (pageOverride) => {
    setLoading(true);
    try {
      const params = {
        page:      pageOverride ?? pg.page,
        page_size: pg.pageSize,
      };
      if (entityTypeFilter !== 'all') params.entity_type = entityTypeFilter;
      if (entityIdFilter) params.entity_id = entityIdFilter;

      const res = await api.get(apiUrl.auditLogs(params));
      setLogs(res.data.data || []);
      pg.setFromResponse(res.data.pagination);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  };

  const clearEntityIdFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('entity_id');
    setSearchParams(next);
  };

  useEffect(() => {
    pg.resetPage();
    fetchData(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityTypeFilter, entityIdFilter]);

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pg.page]);

  // Client-side search on loaded page
  const displayLogs = debouncedSearch
    ? logs.filter((l) => {
        const q = debouncedSearch.toLowerCase();
        return (
          l.entity_type?.toLowerCase().includes(q) ||
          l.action?.toLowerCase().includes(q) ||
          l.entity_id?.toLowerCase().includes(q)
        );
      })
    : logs;

  const toggleExpand = (id) => setExpandedRow((prev) => (prev === id ? null : id));

  // See Team/index.jsx and Settings/index.jsx's identical comment — a
  // wildcard-permission custom role ("Super Admin") must not be blocked
  // here just because its name isn't literally "admin". Found via the
  // same grep that surfaced the Team/Settings bug (Sep 15, 2026).
  if (currentUser?.role !== 'admin' && !currentUser?.is_super_admin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-gray-800 mb-2">Access Denied</h1>
          <p className="text-gray-600">Audit logs are accessible to admins only.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="audit-log-page">
      <PageHeader
        title="Audit Log"
        actions={
          <AppButton variant="outline" onClick={() => fetchData(1)} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </AppButton>
        }
      />

      {/* Filters */}
      <div className="flex items-center gap-4 mb-4">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search by action, entity..."
          className="w-64"
        />

        <FilterPills
          options={ENTITY_TYPES}
          active={entityTypeFilter}
          onChange={setEntityTypeFilter}
          className="flex-wrap"
        />

        {entityIdFilter && (
          <span className="flex items-center gap-1 pl-2.5 pr-1 py-1 bg-brand-tint text-brand text-xs font-medium rounded-lg">
            One record only
            <AppButton
              variant="ghost"
              iconOnly
              icon={<X className="w-3.5 h-3.5" />}
              aria-label="Clear record filter"
              onClick={clearEntityIdFilter}
            />
          </span>
        )}
      </div>

      {/* Table */}
      <DataCard>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="audit-log-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Entity</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Entity ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Performed By</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan="6" className="p-0">
                    <TableSkeleton rows={8} columns={5} />
                  </td>
                </tr>
              ) : displayLogs.length === 0 ? (
                <tr>
                  <td colSpan="6" className="py-16 text-center text-gray-400">
                    {debouncedSearch ? 'No entries match your search.' : 'No audit log entries found.'}
                  </td>
                </tr>
              ) : (
                displayLogs.map((log) => (
                  <React.Fragment key={log.id}>
                    <tr
                      className="hover:bg-brand-tint transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-inset"
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleExpand(log.id)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(log.id); } }}
                      data-testid={`audit-row-${log.id}`}
                    >
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="text-sm text-gray-700">{formatDateShort(log.created_at)}</div>
                        <div className="text-xs text-gray-400">{formatTime(log.created_at)}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs font-medium text-gray-600 bg-gray-100 px-2 py-1 rounded">
                          {ENTITY_LABELS[log.entity_type] || log.entity_type || '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <ActionBadge action={log.action} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs font-mono text-gray-500">
                          {log.entity_id ? log.entity_id.slice(0, 8) + '…' : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {log.performed_by_name || (log.performed_by ? log.performed_by.slice(0, 8) + '…' : '—')}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {(log.old_value || log.new_value) && (
                          <AppButton
                            variant="ghost"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); toggleExpand(log.id); }}
                          >
                            {expandedRow === log.id ? 'Hide' : 'Show'}
                          </AppButton>
                        )}
                      </td>
                    </tr>

                    {/* Expanded diff view */}
                    {expandedRow === log.id && (log.old_value || log.new_value) && (
                      <tr className="bg-gray-50">
                        <td colSpan="6" className="px-6 py-3">
                          <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                            {log.old_value && (
                              <div>
                                <div className="text-gray-500 font-sans font-semibold mb-1">Before</div>
                                <pre className="bg-red-50 border border-red-100 rounded p-2 overflow-auto max-h-48 text-red-700">
                                  {JSON.stringify(log.old_value, null, 2)}
                                </pre>
                              </div>
                            )}
                            {log.new_value && (
                              <div>
                                <div className="text-gray-500 font-sans font-semibold mb-1">After</div>
                                <pre className="bg-green-50 border border-green-100 rounded p-2 overflow-auto max-h-48 text-green-700">
                                  {JSON.stringify(log.new_value, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <PaginationBar {...pg} />
      </DataCard>
    </div>
  );
}
