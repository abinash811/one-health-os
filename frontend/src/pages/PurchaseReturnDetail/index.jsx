import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '@/lib/axios';
import { toast } from 'sonner';
import { ArrowLeft, Printer, Edit, FileText, Package } from 'lucide-react';
import { AppButton, InlineLoader, PageBreadcrumb, MoreMenu, StatusBadge, EmptyState } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';
import { formatDate } from '@/utils/dates';
import { PURCHASE_RETURN_REASON_LABELS, PURCHASE_RETURN_PAYMENT_TYPE_LABELS } from '@/constants/domainConstants';
import PurchaseReturnEditModal from './components/PurchaseReturnEditModal';
import CreditStatusModal from './components/CreditStatusModal';

export default function PurchaseReturnDetail() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [purchaseReturn, setPurchaseReturn] = useState(null);
  const [loading, setLoading]               = useState(true);
  const [showEditModal, setShowEditModal]   = useState(false);
  const [editType, setEditType]             = useState(null);
  const [editNote, setEditNote]             = useState('');
  const [isSaving, setIsSaving]             = useState(false);
  const [showCreditModal, setShowCreditModal] = useState(false);
  const [isSavingCredit, setIsSavingCredit]   = useState(false);

  useEffect(() => { fetchPurchaseReturn(); }, [id]); // eslint-disable-line

  const fetchPurchaseReturn = async () => {
    try {
      const res = await api.get(`/purchase-returns/${id}`);
      setPurchaseReturn(res.data);
      setEditNote(res.data.note || '');
    } catch (err) { toast.error(err.message || 'Failed to load purchase return'); navigate('/purchases'); }
    finally { setLoading(false); }
  };

  const handleEditSave = async () => {
    setIsSaving(true);
    try {
      await api.put(`/purchase-returns/${id}`, { edit_type: editType, note: editNote });
      toast.success('Return updated successfully');
      setShowEditModal(false);
      fetchPurchaseReturn();
    } catch (err) { toast.error(err.message || 'Failed to update return'); }
    finally { setIsSaving(false); }
  };

  const handleCreditStatusSave = async (creditReceived, rejected) => {
    setIsSavingCredit(true);
    try {
      await api.put(`/purchase-returns/${id}/credit-status`, { credit_received: creditReceived, rejected });
      toast.success('Credit status updated');
      setShowCreditModal(false);
      fetchPurchaseReturn();
    } catch (err) { toast.error(err.message || 'Failed to update credit status'); }
    finally { setIsSavingCredit(false); }
  };

  const formatExpiry = (exp) => {
    if (!exp) return '—';
    if (exp.includes('/') && exp.length <= 5) return exp;
    if (exp.length >= 7) { const p = exp.split('-'); if (p.length >= 2) return `${p[1]}/${p[0].slice(-2)}`; }
    return exp;
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-page"><InlineLoader text="Loading return..." /></div>;
  if (!purchaseReturn) return <div className="min-h-screen flex items-center justify-center bg-page"><div className="text-gray-500">Purchase return not found</div></div>;

  const items     = purchaseReturn.items || [];
  const ptrTotal  = purchaseReturn.ptr_total || purchaseReturn.total_value || 0;
  const gstAmount = purchaseReturn.gst_amount || 0;
  const netAmount = purchaseReturn.total_value || 0;

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <header className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <AppButton variant="ghost" iconOnly icon={<ArrowLeft className="w-5 h-5 text-gray-600" strokeWidth={1.5} />} aria-label="Back" onClick={() => navigate('/purchases')} data-testid="back-btn" />
            <div>
              <PageBreadcrumb crumbs={[
                { label: 'Purchases', to: '/purchases' },
                { label: 'Returns', to: '/purchases/returns' },
                { label: purchaseReturn.return_number },
              ]} />
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold font-mono text-brand">{purchaseReturn.return_number}</h1>
                <StatusBadge status={purchaseReturn.status || 'confirmed'} label={(purchaseReturn.status || 'confirmed').toUpperCase()} />
              </div>
            </div>
          </div>
          <MoreMenu
            testId="more-menu-btn"
            items={[
              { icon: <Edit className="w-4 h-4" />, label: 'Edit (Non-Financial)', action: () => { setEditType('non_financial'); setShowEditModal(true); } },
              { icon: <Edit className="w-4 h-4" />, label: 'Edit (Financial)',      action: () => { setEditType('financial'); setShowEditModal(true); } },
              { icon: <Printer className="w-4 h-4" />, label: 'Print',             action: () => window.print() },
              { icon: <FileText className="w-4 h-4" />, label: 'Logs',             action: () => toast.info('Logs coming soon') },
            ]}
          />
        </div>
      </header>

      <main className="flex-grow p-4 lg:p-6 overflow-hidden flex flex-col gap-4">
        {/* Subbar */}
        <section className="bg-white rounded-xl border border-gray-200 px-3 py-2 shadow-sm">
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg"><span className="font-medium text-gray-700">{formatDate(purchaseReturn.return_date, '—')}</span></div>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg" style={{ maxWidth: '220px' }}><span className="font-medium text-gray-900 truncate" title={purchaseReturn.supplier_name}>{purchaseReturn.supplier_name}</span></div>
            {purchaseReturn.purchase_number && (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
                <span className="text-[10px] text-gray-500 uppercase font-medium">Orig#</span>
                <span className="font-medium font-mono text-brand">{purchaseReturn.purchase_number}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
              <span className="text-[10px] text-gray-500 uppercase font-medium">Reason</span>
              <span className="font-medium text-gray-700">{PURCHASE_RETURN_REASON_LABELS[purchaseReturn.reason] || purchaseReturn.reason || '—'}</span>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
              <span className="text-[10px] text-gray-500 uppercase font-medium">Settlement</span>
              <span className="font-medium text-gray-700">{PURCHASE_RETURN_PAYMENT_TYPE_LABELS[purchaseReturn.payment_type] || purchaseReturn.payment_type || '—'}</span>
            </div>
          </div>
        </section>

        {/* Items Table */}
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm flex-grow overflow-hidden flex flex-col">
          <div className="overflow-auto flex-grow">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  {['#', 'Medicine', 'Batch', 'Expiry', 'MRP', 'Return Qty', 'PTR', 'GST%', 'Amount'].map((h, i) => (
                    <th key={h} className={`px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${i >= 4 ? 'text-right' : 'text-left'} ${i === 5 ? 'text-center' : ''}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((item, index) => {
                  const lineAmount = item.line_total || (item.qty_units * (item.ptr || item.cost_price_per_unit || 0));
                  return (
                    <tr key={item.id || index} className="hover:bg-brand-tint transition-colors">
                      <td className="px-4 py-3 text-gray-500">{index + 1}</td>
                      <td className="px-4 py-3"><div className="font-medium text-gray-900">{item.product_name}</div><div className="text-xs text-gray-400">{item.product_sku}</div></td>
                      <td className="px-4 py-3 font-mono text-gray-700">{item.batch_no}</td>
                      <td className="px-4 py-3 text-gray-700">{formatExpiry(item.expiry_date)}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-700">{formatCurrency(item.mrp || 0)}</td>
                      <td className="px-4 py-3 text-center font-semibold text-brand">{item.qty_units}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-700">{formatCurrency(item.ptr || item.cost_price_per_unit || 0)}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{item.gst_percent || 5}%</td>
                      <td className="px-4 py-3 text-right font-mono font-semibold text-red-600">{formatCurrency(lineAmount)}</td>
                    </tr>
                  );
                })}
                {items.length === 0 && (
                  <tr><td colSpan={9} className="p-0">
                    <EmptyState icon={Package} title="No items in this return" description="This return has no line items." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Footer Totals */}
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm shrink-0">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between bg-gray-50">
            <div className="flex items-center gap-6 text-sm">
              {[
                { label: 'Items',     value: items.length },
                { label: 'Total Qty', value: items.reduce((s, i) => s + (i.qty_units || 0), 0) },
                { label: 'PTR Total', value: formatCurrency(ptrTotal) },
                { label: 'GST',       value: formatCurrency(gstAmount) },
              ].map((f) => (
                <div key={f.label}>
                  <span className="text-[10px] text-gray-500 uppercase font-semibold block">{f.label}</span>
                  <span className="font-bold text-gray-700">{f.value}</span>
                </div>
              ))}
            </div>
            <div className="text-right">
              <span className="text-[10px] text-gray-500 uppercase font-semibold block">Net Return Amount</span>
              <span className="text-2xl font-semibold tabular-nums text-red-600">{formatCurrency(netAmount)}</span>
            </div>
          </div>
          <div className="px-4 py-3 flex items-center justify-end gap-3">
            <AppButton variant="outline" icon={<Printer className="w-4 h-4" strokeWidth={1.5} />} onClick={() => window.print()}>Print</AppButton>
          </div>
        </section>

        {/* Credit Status — tracks what the distributor has actually credited
            back, separate from the return record's own "confirmed" status. */}
        <section className="bg-white rounded-xl border border-gray-200 px-4 py-3 shadow-sm flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div>
              <div className="text-[10px] text-gray-500 uppercase font-semibold mb-1">Credit Status</div>
              <StatusBadge status={purchaseReturn.credit_status || 'pending'} />
            </div>
            <div>
              <div className="text-[10px] text-gray-500 uppercase font-semibold">Credited So Far</div>
              <div className="font-semibold text-gray-800">{formatCurrency(purchaseReturn.credit_received || 0)}</div>
            </div>
            {purchaseReturn.credit_status !== 'rejected' && (purchaseReturn.credit_owed || 0) > 0 && (
              <div>
                <div className="text-[10px] text-gray-500 uppercase font-semibold">Still Owed</div>
                <div className="font-semibold text-amber-700">{formatCurrency(purchaseReturn.credit_owed)}</div>
              </div>
            )}
          </div>
          <AppButton variant="outline" onClick={() => setShowCreditModal(true)} data-testid="update-credit-status-btn">
            Update Credit Status
          </AppButton>
        </section>

        {purchaseReturn.note && (
          <section className="bg-white rounded-xl border border-gray-200 px-4 py-3 shadow-sm">
            <div className="text-xs text-gray-400 uppercase font-semibold mb-1">Note</div>
            <div className="text-sm text-gray-700">{purchaseReturn.note}</div>
          </section>
        )}
      </main>

      <PurchaseReturnEditModal
        open={showEditModal}
        onClose={() => setShowEditModal(false)}
        editType={editType}
        editNote={editNote}
        onNoteChange={setEditNote}
        isSaving={isSaving}
        onSave={handleEditSave}
      />

      {showCreditModal && (
        <CreditStatusModal
          purchaseReturn={purchaseReturn}
          onClose={() => setShowCreditModal(false)}
          onConfirm={handleCreditStatusSave}
          isSaving={isSavingCredit}
        />
      )}
    </div>
  );
}
