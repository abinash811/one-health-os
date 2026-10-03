// @ts-nocheck -- plain-JS component, same untyped-by-choice precedent as
// CorrectPurchaseModal.tsx/CreditStatusModal.tsx.
/**
 * TransferHistory — every stock transfer in/out of the active store, with
 * a Reverse action for one that hasn't been used yet at the destination.
 * Route: /inventory/transfers
 *
 * Built Sep 28, 2026 (docs/15_ROADMAP.md RULE MISSES LOG): POST
 * /stock-transfers/{id}/reverse (docs/26_MULTI_CHAIN_SCOPE.md Step 5) was
 * fully built and tested on the backend with zero frontend surface to
 * reach it — no history list, no detail, no Reverse button anywhere. This
 * page is that surface, using GET /stock-transfers, which already existed
 * and already scopes to the caller's own pharmacy on either side.
 */
import React, { useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowUpRight, ArrowDownLeft, RotateCcw } from 'lucide-react';
import { PageHeader, PageTabs, DataCard, TableSkeleton, AppButton } from '@/components/shared';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { formatDate, formatTime } from '@/utils/dates';
import { INVENTORY_TABS, inventoryTabRoute } from './inventoryTabs';

function DirectionBadge({ direction }) {
  const isOut = direction === 'out';
  const Icon = isOut ? ArrowUpRight : ArrowDownLeft;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
      isOut ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'
    }`}>
      <Icon className="w-3 h-3" />
      {isOut ? 'Sent' : 'Received'}
    </span>
  );
}

export default function TransferHistory() {
  const navigate = useNavigate();
  const { user } = useContext(AuthContext);
  const isAdmin = user?.role === 'admin' || !!user?.is_super_admin;

  const [transfers, setTransfers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reversingId, setReversingId] = useState(null);

  const fetchTransfers = async () => {
    setLoading(true);
    try {
      const res = await api.get(apiUrl.stockTransfers());
      setTransfers(res.data || []);
    } catch (err) {
      toast.error(err.message || 'Failed to load transfer history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTransfers(); }, []);

  const handleReverse = async (transferId) => {
    setReversingId(transferId);
    try {
      await api.post(apiUrl.reverseStockTransfer(transferId));
      toast.success('Transfer reversed');
      fetchTransfers();
    } catch (err) {
      toast.error(err.message || 'Failed to reverse transfer');
    } finally {
      setReversingId(null);
    }
  };

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="transfer-history-page">
      <PageHeader title="Inventory" />
      <PageTabs
        tabs={INVENTORY_TABS}
        activeTab="transfers"
        onChange={(key) => navigate(inventoryTabRoute(key))}
      />

      <DataCard>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="transfer-history-table">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Transfer #</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date & Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Direction</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Source</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Destination</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan="7" className="p-0">
                    <TableSkeleton rows={8} columns={7} />
                  </td>
                </tr>
              ) : transfers.length === 0 ? (
                <tr>
                  <td colSpan="7" className="py-16 text-center text-gray-400">
                    No stock transfers yet. Transfer stock between your stores from the
                    Inventory page's "Transfer Stock" action.
                  </td>
                </tr>
              ) : (
                transfers.map((t) => (
                  <tr key={t.id} className="hover:bg-brand-tint transition-colors" data-testid={`transfer-row-${t.id}`}>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{t.transfer_number}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="text-sm text-gray-700">{formatDate(t.transfer_date)}</div>
                      <div className="text-xs text-gray-400">{formatTime(t.transfer_date)}</div>
                    </td>
                    <td className="px-4 py-3"><DirectionBadge direction={t.direction} /></td>
                    <td className="px-4 py-3 text-gray-700">{t.source_pharmacy || '—'}</td>
                    <td className="px-4 py-3 text-gray-700">{t.destination_pharmacy || '—'}</td>
                    <td className="px-4 py-3 text-center">
                      {t.reversed ? (
                        <span className="text-xs font-medium text-gray-500">Reversed</span>
                      ) : (
                        <span className="text-xs font-medium text-green-600">Active</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {!t.reversed && isAdmin && (
                        <AppButton
                          variant="ghost" size="sm"
                          loading={reversingId === t.id}
                          onClick={() => handleReverse(t.id)}
                          icon={<RotateCcw className="w-3.5 h-3.5" />}
                          data-testid={`reverse-transfer-${t.id}`}
                        >
                          Reverse
                        </AppButton>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </DataCard>
    </div>
  );
}
