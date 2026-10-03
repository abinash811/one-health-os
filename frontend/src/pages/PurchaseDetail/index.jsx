import React, { useState, useEffect, useContext } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import api from '@/lib/axios';
import { toast } from 'sonner';
import { ArrowLeft, Printer, RotateCcw, FileText, Paperclip, PenLine } from 'lucide-react';
import { AuthContext } from '@/App';
import { InlineLoader, AppButton, PageBreadcrumb, MoreMenu, StatusBadge } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';
import { formatDate as formatDateShort, today } from '@/utils/dates';
import PurchaseItemsTable from './components/PurchaseItemsTable';
import PurchasePayModal from './components/PurchasePayModal';
import PaymentHistorySection from './components/PaymentHistorySection';
import CorrectPurchaseModal from './components/CorrectPurchaseModal';

export default function PurchaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useContext(AuthContext);
  const isAdmin = user?.role === 'admin' || !!user?.is_super_admin;
  const [purchase, setPurchase]   = useState(null);
  const [loading, setLoading]     = useState(true);
  const [showPayModal, setShowPayModal] = useState(false);
  const [paymentData, setPaymentData]   = useState({
    amount: 0, payment_method: 'cash', payment_date: today(), reference_no: '', notes: '',
  });
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [showCorrectModal, setShowCorrectModal] = useState(false);
  const [correctingLoading, setCorrectingLoading] = useState(false);

  useEffect(() => { fetchPurchase(); }, [id]); // eslint-disable-line

  useEffect(() => {
    if (!loading && purchase?.status === 'draft') navigate(`/purchases/edit/${id}?type=purchase`, { replace: true });
  }, [loading, purchase, id, navigate]);

  const fetchPurchase = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/purchases/${id}`);
      setPurchase(res.data);
    } catch { toast.error('Failed to load purchase'); navigate('/purchases'); }
    finally { setLoading(false); }
  };

  const handlePayment = async () => {
    setPaymentLoading(true);
    try {
      await api.post(`/purchases/${id}/pay`, paymentData);
      toast.success('Payment recorded successfully');
      setShowPayModal(false);
      fetchPurchase();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to record payment'); }
    finally { setPaymentLoading(false); }
  };

  const openPayModal = () => {
    const outstanding = (purchase.total_value || 0) - (purchase.amount_paid || 0);
    setPaymentData({ amount: outstanding, payment_method: 'cash', payment_date: today(), reference_no: '', notes: '' });
    setShowPayModal(true);
  };

  const handleCorrect = async (correction) => {
    setCorrectingLoading(true);
    try {
      await api.put(`/purchases/${id}/correct`, correction);
      toast.success('Purchase corrected');
      setShowCorrectModal(false);
      fetchPurchase();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to correct purchase'); }
    finally { setCorrectingLoading(false); }
  };

  const calculateTotals = () => {
    if (!purchase?.items) return { itemCount: 0, totalQty: 0, totalFree: 0, marginPercent: 0, gst: 0, netAmount: 0 };
    let totalQty = 0, totalFree = 0, totalPTR = 0, totalMRP = 0, totalGST = 0;
    purchase.items.forEach((item) => {
      const qty = parseInt(item.qty_units) || 0;
      const ptr = parseFloat(item.cost_price_per_unit) || 0;
      const mrp = parseFloat(item.mrp_per_unit) || 0;
      const gst = parseFloat(item.gst_percent) || 0;
      totalQty  += qty; totalFree += parseInt(item.free_qty_units) || 0;
      totalPTR  += qty * ptr; totalMRP += qty * mrp;
      totalGST  += qty * ptr * (gst / 100);
    });
    return {
      itemCount: purchase.items.length, totalQty, totalFree,
      marginPercent: totalMRP > 0 ? ((totalMRP - totalPTR) / totalMRP * 100).toFixed(1) : 0,
      gst: totalGST, netAmount: purchase.total_value || 0,
    };
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-page"><InlineLoader text="Loading purchase..." /></div>;
  if (!purchase) return <div className="min-h-screen flex items-center justify-center bg-page"><div className="text-gray-500">Purchase not found</div></div>;
  if (purchase.status === 'draft') return <div className="min-h-screen flex items-center justify-center bg-page"><InlineLoader text="Redirecting..." /></div>;

  const isDue      = purchase.payment_status !== 'paid' && (purchase.status === 'confirmed' || purchase.status === 'received');
  const isOverdue  = isDue && purchase.due_date && new Date(purchase.due_date) < new Date();
  const totals     = calculateTotals();

  return (
    <div className="h-screen flex flex-col bg-page">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <AppButton variant="ghost" iconOnly icon={<ArrowLeft className="w-5 h-5 text-gray-600" strokeWidth={1.5} />} aria-label="Back to purchases" onClick={() => navigate('/purchases')} data-testid="back-btn" />
            <div>
              <PageBreadcrumb crumbs={[
                { label: 'Purchases', to: '/purchases' },
                { label: purchase.purchase_number },
              ]} />
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold text-gray-900">{purchase.purchase_number}</h1>
                <StatusBadge status={purchase.status || 'confirmed'} label={(purchase.status || 'confirmed').toUpperCase()} />
                {isDue && <StatusBadge status={isOverdue ? 'overdue' : 'due'} label={isOverdue ? 'OVERDUE' : 'DUE'} />}
                {purchase.payment_status === 'paid' && <StatusBadge status="paid" label="PAID" />}
              </div>
            </div>
          </div>
          <MoreMenu
            testId="more-btn"
            items={[
              { icon: <Printer className="w-4 h-4" />, label: 'Print', action: () => window.print() },
              { icon: <RotateCcw className="w-4 h-4" />, label: 'Purchase Return', action: () => navigate(`/purchases/returns/create?purchase_id=${id}`) },
              { icon: <FileText className="w-4 h-4" />, label: 'Logs', action: () => toast.info('Logs coming soon') },
              ...(isAdmin ? [{ icon: <PenLine className="w-4 h-4" />, label: 'Correct Purchase', action: () => setShowCorrectModal(true) }] : []),
            ]}
          />
        </div>
      </header>

      {/* Read-only Subbar */}
      <section className="bg-white border-b border-gray-200 px-6 py-2 shrink-0">
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
            <span className="font-medium text-gray-700">{formatDateShort(purchase.purchase_date)}</span>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg" style={{ maxWidth: '220px' }}>
            <span className="font-medium text-gray-900 truncate" title={purchase.supplier_name}>{purchase.supplier_name}</span>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
            <span className="text-[10px] text-gray-500 uppercase font-medium">Inv#</span>
            <span className="font-medium text-gray-700">{purchase.supplier_invoice_no || '—'}</span>
          </div>
          {purchase.invoice_attachment_data && (
            <a
              href={purchase.invoice_attachment_data}
              target="_blank"
              rel="noopener noreferrer"
              download={purchase.invoice_attachment_name || 'invoice'}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-brand font-medium transition-colors"
              data-testid="view-invoice-attachment-link"
            >
              <Paperclip className="w-3.5 h-3.5" />
              <span className="truncate max-w-[100px]" title={purchase.invoice_attachment_name || 'Invoice'}>{purchase.invoice_attachment_name || 'Invoice'}</span>
            </a>
          )}
          {purchase.due_date && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${isOverdue ? 'bg-red-50 border border-red-200' : 'bg-amber-50 border border-amber-200'}`}>
              <span className={`text-[10px] uppercase font-medium ${isOverdue ? 'text-red-600' : 'text-amber-600'}`}>Due</span>
              <span className={`font-medium ${isOverdue ? 'text-red-700' : 'text-amber-700'}`}>{formatDateShort(purchase.due_date)}</span>
            </div>
          )}
          <div className={`px-2.5 py-1.5 rounded-lg ${purchase.purchase_on === 'cash' ? 'bg-green-50' : 'bg-amber-50'}`}>
            <span className={`font-medium ${purchase.purchase_on === 'cash' ? 'text-green-700' : 'text-amber-700'}`}>{purchase.purchase_on === 'cash' ? 'Cash' : 'Credit'}</span>
          </div>
        </div>
      </section>

      <PurchaseItemsTable items={purchase.items} withGst={purchase.with_gst} />

      {purchase.status === 'confirmed' && (
        <section className="bg-white border-t border-gray-200 px-6 py-4 shrink-0 max-h-52 overflow-y-auto">
          <PaymentHistorySection purchaseId={id} isAdmin={isAdmin} onReversed={fetchPurchase} />
        </section>
      )}

      {/* Sticky Footer */}
      <div className="bg-white border-t border-gray-200 shrink-0">
        <div className="px-6 py-2 border-b border-gray-100 flex items-center justify-between text-sm">
          <div className="flex items-center gap-4 text-gray-600">
            <span>Items <span className="font-bold text-gray-900">{totals.itemCount}</span></span>
            <span className="text-gray-300">·</span>
            <span>Total Qty <span className="font-bold text-gray-900">{totals.totalQty}</span></span>
            {totals.totalFree > 0 && <><span className="text-gray-300">·</span><span>Free Qty <span className="font-bold text-green-600">{totals.totalFree}</span></span></>}
            <span className="text-gray-300">·</span>
            <span>Margin% <span className="font-bold text-gray-900">{totals.marginPercent}%</span></span>
            <span className="text-gray-300">·</span>
            <span>GST <span className="font-bold text-gray-900">{formatCurrency(totals.gst)}</span></span>
          </div>
          <div className="text-gray-600">Net Amount <span className="font-bold text-brand text-base">{formatCurrency(totals.netAmount)}</span></div>
        </div>
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="text-sm">
            {isDue && (
              <span className="text-red-600">Due: <span className="font-bold">{formatCurrency((purchase.total_value || 0) - (purchase.amount_paid || 0))}</span>
                {purchase.due_date && <span className="text-gray-500 ml-2">· Due on {formatDateShort(purchase.due_date)}</span>}
                {purchase.last_payment_date && <span className="text-gray-500 ml-2">· Last paid on {formatDateShort(purchase.last_payment_date)}</span>}
              </span>
            )}
            {purchase.payment_status === 'paid' && (
              <span className="text-green-600 font-semibold">
                Payment complete
                {purchase.last_payment_date && <span className="text-gray-500 font-normal ml-2">· Paid on {formatDateShort(purchase.last_payment_date)}</span>}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {isDue && <AppButton variant="secondary" onClick={openPayModal} data-testid="mark-paid-btn">Mark as Paid</AppButton>}
            <AppButton variant="outline" icon={<Printer className="w-4 h-4" strokeWidth={1.5} />} onClick={() => window.print()} data-testid="print-btn">Print</AppButton>
          </div>
        </div>
      </div>

      <PurchasePayModal
        open={showPayModal}
        onClose={() => setShowPayModal(false)}
        purchase={purchase}
        paymentData={paymentData}
        onPaymentDataChange={setPaymentData}
        onConfirm={handlePayment}
        loading={paymentLoading}
      />

      {showCorrectModal && (
        <CorrectPurchaseModal
          purchase={purchase}
          onClose={() => setShowCorrectModal(false)}
          onConfirm={handleCorrect}
          isSaving={correctingLoading}
        />
      )}
    </div>
  );
}
