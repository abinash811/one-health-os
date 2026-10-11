import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import api from '@/lib/axios';
import { toast } from 'sonner';
import { ArrowLeft, ChevronDown, Calendar as CalendarIcon, Printer, Trash2, Package } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { AppButton, EmptyState, InlineLoader } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';
import { format } from 'date-fns';
import { PURCHASE_RETURN_REASON, PURCHASE_RETURN_REASON_LABELS } from '@/constants/domainConstants';
import PurchaseReturnFinaliseModal from './components/PurchaseReturnFinaliseModal';

export default function PurchaseReturnCreate() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const purchaseId = searchParams.get('purchase_id');

  const [returnDate, setReturnDate]   = useState(new Date());
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [supplier, setSupplier]       = useState({ id: null, name: '' });
  const [invoiceNo, setInvoiceNo]     = useState('');
  const [paymentType, setPaymentType] = useState('credit');
  const [reason, setReason]           = useState(PURCHASE_RETURN_REASON.DAMAGED);
  const [note, setNote]               = useState('');
  const [items, setItems]             = useState([]);
  const [loading, setLoading]         = useState(true);
  const [showFinaliseModal, setShowFinaliseModal] = useState(false);
  const [isSaving, setIsSaving]       = useState(false);
  const [totals, setTotals]           = useState({ ptrTotal: 0, gstAmount: 0, netAmount: 0 });

  useEffect(() => {
    if (purchaseId) { fetchPurchaseForReturn(purchaseId); }
    else { toast.error('No purchase ID provided'); navigate('/purchases'); }
  }, [purchaseId]); // eslint-disable-line
  useEffect(() => { calculateTotals(); }, [items]); // eslint-disable-line

  const fetchPurchaseForReturn = async (id) => {
    try {
      const res = await api.get(`/purchases/${id}/items-for-return`);
      const data = res.data;
      setSupplier({ id: data.supplier_id, name: data.supplier_name });
      setInvoiceNo(data.invoice_no || '');
      setItems(data.items.filter((i) => i.max_returnable_qty > 0).map((item) => ({
        id: crypto.randomUUID(),
        // GET /purchases/{id}/items-for-return returns product_id/product_name
        // (not medicine_id/medicine_name) — found Sep 13, 2026, Purchases
        // product-review, live-testing the create-return flow: reading the
        // wrong field names here silently left every item's name blank and
        // the create payload's required product_name missing, so a real
        // Save always 422'd. Kept as medicine_id/medicine_name locally since
        // the rest of this component (and the create payload) already
        // reads those names.
        medicine_id: item.product_id, medicine_name: item.product_name,
        product_sku: item.product_sku, batch_id: item.batch_id, batch_no: item.batch_no,
        expiry_date: item.expiry_date, mrp: item.mrp || 0, ptr: item.ptr || 0,
        gst_percent: item.gst_percent || 5, original_qty: item.original_qty,
        return_qty: 0, max_returnable_qty: item.max_returnable_qty, error: null,
      })));
      setLoading(false);
    } catch (err) { toast.error(err.message || 'Failed to load purchase'); navigate('/purchases'); }
  };

  const calculateTotals = () => {
    let ptrTotal = 0, gstAmount = 0;
    items.forEach((item) => {
      if (item.return_qty > 0) {
        const line = item.return_qty * item.ptr;
        ptrTotal  += line;
        gstAmount += line * (item.gst_percent / 100);
      }
    });
    setTotals({ ptrTotal, gstAmount, netAmount: Math.round(ptrTotal + gstAmount) });
  };

  const updateItemQty = (index, newQty) => {
    setItems((prev) => prev.map((item, i) => {
      if (i !== index) return item;
      const qty = parseInt(newQty) || 0;
      const error = qty > item.max_returnable_qty ? `Max: ${item.max_returnable_qty}` : qty < 0 ? 'Invalid qty' : null;
      return { ...item, return_qty: qty, error };
    }));
  };

  const hasErrors    = () => items.some((i) => i.error);
  const hasReturnItems = () => items.some((i) => i.return_qty > 0);

  const handleSave = async (andPrint = false) => {
    if (hasErrors()) { toast.error('Please fix validation errors before saving'); return; }
    if (!hasReturnItems()) { toast.error('Please enter return quantity for at least one item'); return; }
    setIsSaving(true);
    try {
      const res = await api.post(`/purchase-returns`, {
        supplier_id: supplier.id, purchase_id: purchaseId,
        return_date: format(returnDate, 'yyyy-MM-dd'),
        payment_type: paymentType, reason, note,
        items: items.filter((i) => i.return_qty > 0).map((item) => ({
          product_sku: item.product_sku, product_name: item.medicine_name,
          batch_id: item.batch_id, batch_no: item.batch_no,
          expiry_date: item.expiry_date, mrp: item.mrp, ptr: item.ptr,
          gst_percent: item.gst_percent, return_qty_units: item.return_qty,
          cost_price_per_unit: item.ptr,
        })),
      });
      toast.success(`Return ${res.data.return_number} created successfully`);
      if (andPrint) toast.info('Print functionality coming soon');
      setShowFinaliseModal(false);
      navigate('/purchases/returns');
    } catch (err) { toast.error(err.message || 'Failed to create return'); }
    finally { setIsSaving(false); }
  };

  const formatExpiry = (exp) => {
    if (!exp) return '—';
    if (exp.includes('/') && exp.length <= 5) return exp;
    if (exp.length >= 7) { const p = exp.split('-'); if (p.length >= 2) return `${p[1]}/${p[0].slice(-2)}`; }
    return exp;
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-page"><InlineLoader text="Loading purchase..." /></div>;

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <header className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
        <div className="flex items-center gap-4">
          <AppButton variant="ghost" iconOnly icon={<ArrowLeft className="w-5 h-5 text-gray-600" strokeWidth={1.5} />} aria-label="Back" onClick={() => navigate('/purchases')} data-testid="back-btn" />
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-0.5">
              <Link to="/purchases" className="hover:text-brand">Purchases</Link><span>/</span>
              <span>Returns</span><span>/</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900">New Purchase Return</h1>
          </div>
        </div>
      </header>

      <main className="flex-grow p-4 lg:p-6 overflow-hidden flex flex-col gap-4">
        {/* Subbar */}
        <section className="bg-white rounded-xl border border-gray-200 px-3 py-2 shadow-sm">
          <div className="flex items-center gap-2 flex-wrap">
            <Popover open={showDatePicker} onOpenChange={setShowDatePicker}>
              <PopoverTrigger asChild>
                <AppButton variant="ghost" className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-green-50 border border-green-200 hover:bg-green-50" data-testid="date-picker-btn">
                  <CalendarIcon className="w-4 h-4 text-brand" strokeWidth={1.5} />
                  <span className="text-sm font-medium text-brand">{format(returnDate, 'dd MMM yyyy')}</span>
                  <ChevronDown className="w-3 h-3 text-brand" strokeWidth={1.5} />
                </AppButton>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar mode="single" selected={returnDate} onSelect={(d) => { setReturnDate(d || new Date()); setShowDatePicker(false); }} disabled={(d) => d > new Date()} initialFocus />
              </PopoverContent>
            </Popover>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg" style={{ maxWidth: '220px' }} title={supplier.name}>
              <span className="text-sm font-medium text-gray-900 truncate" title={supplier.name}>{supplier.name}</span>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-100 rounded-lg">
              <span className="text-[10px] text-gray-500 uppercase font-medium">Inv#</span>
              <span className="text-sm font-medium text-gray-700">{invoiceNo || '—'}</span>
            </div>
            <div className="flex-grow" />
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-50 border border-gray-200 rounded-lg">
              <select value={reason} onChange={(e) => setReason(e.target.value)} className="text-sm font-medium text-gray-700 bg-transparent border-none focus:outline-none cursor-pointer pr-1" data-testid="return-reason">
                {Object.values(PURCHASE_RETURN_REASON).map((r) => (
                  <option key={r} value={r}>{PURCHASE_RETURN_REASON_LABELS[r]}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-50 border border-gray-200 rounded-lg">
              <select value={paymentType} onChange={(e) => setPaymentType(e.target.value)} className="text-sm font-medium text-gray-700 bg-transparent border-none focus:outline-none cursor-pointer pr-1" data-testid="payment-type">
                <option value="cash">Cash</option>
                <option value="upi">UPI</option>
                <option value="credit">Credit</option>
                <option value="adjust_outstanding">Adjust Against Outstanding</option>
              </select>
            </div>
          </div>
        </section>

        {/* Items Table */}
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm flex-grow overflow-hidden flex flex-col">
          <div className="overflow-auto flex-grow">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  {['#', 'Medicine', 'Batch', 'Expiry', 'MRP', 'Original Qty', 'Return Qty', 'PTR', 'GST%', 'Amount', ''].map((h, i) => (
                    <th key={i} className={`px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${i >= 4 ? 'text-right' : 'text-left'} ${i === 5 || i === 6 ? 'text-center' : ''}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((item, index) => {
                  const lineAmount = item.return_qty * item.ptr;
                  return (
                    <tr key={item.id} className="hover:bg-brand-tint transition-colors">
                      <td className="px-4 py-3 text-gray-500">{index + 1}</td>
                      <td className="px-4 py-3"><div className="font-medium text-gray-900">{item.medicine_name}</div><div className="text-xs text-gray-400">{item.product_sku}</div></td>
                      <td className="px-4 py-3 font-mono text-gray-700">{item.batch_no}</td>
                      <td className="px-4 py-3 text-gray-700">{formatExpiry(item.expiry_date)}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-700">{formatCurrency(item.mrp || 0)}</td>
                      <td className="px-4 py-3 text-center font-semibold text-gray-700">{item.original_qty}</td>
                      <td className="px-4 py-3">
                        <div className="relative">
                          <input type="number" min="0" max={item.max_returnable_qty} value={item.return_qty || ''}
                            onChange={(e) => updateItemQty(index, e.target.value)}
                            className={`w-full px-2 py-1.5 text-center border rounded-lg focus:outline-none focus:ring-1 focus:ring-brand font-semibold ${item.error ? 'border-red-400 bg-red-50' : 'border-gray-200'}`}
                            placeholder="0" data-testid={`return-qty-${index}`} />
                          {item.error && <div className="absolute -bottom-4 left-0 right-0 text-[10px] text-red-500 text-center">{item.error}</div>}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-gray-700">{formatCurrency(item.ptr || 0)}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{item.gst_percent}%</td>
                      <td className={`px-4 py-3 text-right font-mono font-semibold ${item.return_qty > 0 ? 'text-red-600' : 'text-gray-400'}`}>{formatCurrency(lineAmount)}</td>
                      <td className="px-4 py-3 text-center">
                        <AppButton variant="ghost" iconOnly icon={<Trash2 className="h-4 w-4 text-gray-400" strokeWidth={1.5} />} aria-label="Remove item" onClick={() => setItems(items.filter((_, i) => i !== index))} />
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && (
                  <tr><td colSpan={11} className="p-0">
                    <EmptyState icon={Package} title="No items available for return" description="Every item on this purchase has already been fully returned." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Footer */}
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm shrink-0">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between bg-gray-50">
            <div className="flex items-center gap-6 text-sm">
              {[
                { label: 'Items',     value: items.filter((i) => i.return_qty > 0).length },
                { label: 'Total Qty', value: items.reduce((s, i) => s + (i.return_qty || 0), 0) },
                { label: 'PTR Total', value: formatCurrency(totals.ptrTotal) },
                { label: 'GST',       value: formatCurrency(totals.gstAmount) },
              ].map((f) => (
                <div key={f.label}>
                  <span className="text-[10px] text-gray-500 uppercase font-semibold block">{f.label}</span>
                  <span className="font-bold text-gray-700">{f.value}</span>
                </div>
              ))}
            </div>
            <div className="text-right">
              <span className="text-[10px] text-gray-500 uppercase font-semibold block">Net Return Amount</span>
              <span className="text-2xl font-semibold tabular-nums text-red-600">{formatCurrency(totals.netAmount)}</span>
            </div>
          </div>
          <div className="px-4 py-3 flex items-center justify-end gap-3">
            <AppButton variant="secondary" onClick={() => navigate('/purchases')}>Cancel</AppButton>
            <AppButton variant="outline" icon={<Printer className="w-4 h-4" strokeWidth={1.5} />} onClick={() => toast.info('Print functionality coming soon')}>Print</AppButton>
            <AppButton disabled={hasErrors() || !hasReturnItems()} onClick={() => setShowFinaliseModal(true)} data-testid="save-return-btn">Save Return</AppButton>
          </div>
        </section>
      </main>

      <PurchaseReturnFinaliseModal
        open={showFinaliseModal} onClose={() => setShowFinaliseModal(false)}
        totals={totals} note={note} onNoteChange={setNote}
        supplierName={supplier.name} onSave={handleSave} isSaving={isSaving}
      />
    </div>
  );
}
