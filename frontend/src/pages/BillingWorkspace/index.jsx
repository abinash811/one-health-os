/**
 * BillingWorkspace — orchestrator
 * Route: /billing/new · /billing/create · /billing/edit/:id (viewing a
 * completed/due/parked bill is BillDetail, /billing/:id)
 */
import React, { useState, useEffect, useRef, useCallback, useContext } from 'react';
import { useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AuthContext } from '@/App';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { useBillItems }       from './hooks/useBillItems';
import { useBillActions }     from './hooks/useBillActions';
import BillingHeader          from './components/BillingHeader';
import BillingSubbar          from './components/BillingSubbar';
import BillingTable           from './components/BillingTable';
import BillingFooter          from './components/BillingFooter';
import FinaliseModal          from './components/FinaliseModal';
import ScheduleHWarning       from './components/ScheduleHWarning';
import PatientSearchModal     from './components/PatientSearchModal';
import PrintReceipt           from './components/PrintReceipt';
import { PageSkeleton } from '@/components/shared';
import DrugLicenseRequiredState from './components/DrugLicenseRequiredState';
import { isDrugLicenseValid, isDrugLicenseExpired } from '@/utils/drugLicense';
import { buildPrintPharmacyInfo } from './utils/buildPrintPharmacyInfo';
import { getPaymentSplitsError } from './utils/validatePaymentSplits';
import { mapBillItemsToRows } from './utils/mapBillItemsToRows';
import { setDraftOwner, readBillDraft, writeBillDraft, clearBillDraft } from './utils/billDraft';
import ResumeDraftBanner from './components/ResumeDraftBanner';

export default function BillingWorkspace() {
  const navigate       = useNavigate();
  const [searchParams] = useSearchParams();
  const { id: billId } = useParams();
  const searchInputRef = useRef(null);
  const { user } = useContext(AuthContext);
  // The unfinished bill kept in this browser for THIS login at THIS pharmacy — offered, never auto-filled.
  setDraftOwner(user?.id, user?.pharmacy_id);
  const [pendingDraft, setPendingDraft] = useState(null);

  // ── Mode & loaded bill ───────────────────────────────────────────────────
  const [viewMode,       setViewMode]       = useState('new');
  const [loadedBill,     setLoadedBill]     = useState(null);
  const [editingDraftId, setEditingDraftId] = useState(null);

  // ── Header / customer fields ─────────────────────────────────────────────
  const [customerName,  setCustomerName]  = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerId,    setCustomerId]    = useState(null);
  const [doctorName,    setDoctorName]    = useState('');
  // Schedule H1 register (Drugs & Cosmetics Rules, Rule 65): patient name
  // AND address must be recorded at the time of supply, same standing as
  // the prescriber's own name/registration — captured here, not pulled
  // from a saved customer profile, since a one-off walk-in is exactly who
  // this rule is for.
  const [patientAddress, setPatientAddress] = useState('');
  const [patientAge,     setPatientAge]     = useState('');
  const [paymentType,   setPaymentType]   = useState('cash');
  // Split legs for a "Multi" payment (e.g. ₹300 cash + ₹200 UPI) — only
  // populated when paymentType === 'multiple'. Cleared whenever the payment
  // type changes away from 'multiple'.
  const [paymentSplits, setPaymentSplits] = useState([]);
  const [billDate,      setBillDate]      = useState(new Date());
  const [draftNumber,   setDraftNumber]   = useState(null);
  const [billDiscount,     setBillDiscount]     = useState(0);
  const [billDiscountType, setBillDiscountType] = useState('%');

  const [isInitialising, setIsInitialising] = useState(true);

  // ── Modal flags ──────────────────────────────────────────────────────────
  const [showFinalise,      setShowFinalise]      = useState(false);
  const [showScheduleH,     setShowScheduleH]     = useState(false);
  const [showPatientModal,  setShowPatientModal]  = useState(false);

  // ── Print ────────────────────────────────────────────────────────────────
  const [savedBillData,  setSavedBillData]  = useState(null);
  const [printFormat,    setPrintFormat]    = useState('80mm'); // default until settings load
  const [pharmacyGeneral, setPharmacyGeneral] = useState(null);
  const [printSettings,  setPrintSettings]  = useState(null); // full settings.print — toggles, header/footer text
  const [gstSettings,    setGstSettings]    = useState(null); // settings.gst — "Print GST summary on bill" lives here, not settings.print
  const [autoPrintInvoice, setAutoPrintInvoice] = useState(false); // Settings → Billing "Auto-print invoice after checkout"
  const [nearExpiryDays, setNearExpiryDays] = useState(90); // Settings → Inventory — matches isExpiringSoon's own default until settings load

  // ── Items + totals hook ──────────────────────────────────────────────────
  const {
    billItems, setItems,
    updateItem, removeItem, addItem,
    mrpTotal, subtotal, totalDiscount, totalGst, totalCess, grandTotal, margin,
  } = useBillItems(billDiscount, billDiscountType);

  // ── Draft helpers ─────────────────────────────────────────────────────────
  const saveDraft = useCallback(() => {
    if (viewMode !== 'new') return; // editing an existing bill must never become a "draft" of a new one
    const num = draftNumber || Math.floor(1000 + Math.random() * 9000);
    writeBillDraft({ customerName, customerPhone, doctorName, items: billItems, draftNumber: num });
    if (!draftNumber) setDraftNumber(num);
  }, [customerName, customerPhone, doctorName, billItems, draftNumber, viewMode]);

  const clearBill = useCallback(() => {
    setItems([]); setCustomerName(''); setCustomerPhone(''); setCustomerId(null);
    setDoctorName(''); setPaymentType('cash'); setPaymentSplits([]);
    setPatientAddress(''); setPatientAge('');
    clearBillDraft(); setDraftNumber(null); setPendingDraft(null);
  }, [setItems]);

  // ── Load helpers ──────────────────────────────────────────────────────────
  const loadExistingBill = useCallback(async (id) => {
    try {
      const bill = (await api.get(apiUrl.bill(id))).data;
      setLoadedBill(bill);
      const status = bill.status?.toLowerCase();
      // Same-day correction (paid/due) reuses edit mode too — see
      // docs/15_ROADMAP.md's Billing table, Sep 18 2026. The backend is the
      // real gate (return already exists / day already closed); this just
      // opens the fields for editing exactly like a draft would.
      if (status === 'parked' || status === 'draft' || status === 'paid' || status === 'due') {
        setViewMode('edit'); setEditingDraftId(bill.id);
      } else setViewMode('view');
      setCustomerName(bill.customer_name || 'Walk-in Customer');
      setCustomerPhone(bill.customer_mobile || bill.customer_phone || '');
      setCustomerId(bill.customer_id || null);
      setDoctorName(bill.doctor_name || '');
      setPaymentType(bill.payment_method || bill.payment_type || 'cash');
      setPaymentSplits((bill.payment_splits || []).map(s => ({ method: s.method, amount: String(s.amount) })));
      if (bill.bill_date || bill.created_at) setBillDate(new Date(bill.bill_date || bill.created_at));
      setItems(mapBillItemsToRows(bill.items));
    } catch { toast.error('Failed to load bill'); navigate('/billing'); }
  }, [setItems, navigate]);

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const sr = await api.get(apiUrl.settings());
        setPrintFormat(sr.data?.print?.paper_size || '80mm');
        setPharmacyGeneral(sr.data?.general || null);
        setPrintSettings(sr.data?.print || null);
        setGstSettings(sr.data?.gst || null);
        setAutoPrintInvoice(!!sr.data?.billing?.auto_print_invoice);
        if (sr.data?.inventory?.near_expiry_days) setNearExpiryDays(sr.data.inventory.near_expiry_days);
      } catch { /* silent */ } finally { setIsInitialising(false); }
    })();
    if (billId) { loadExistingBill(billId); return; }
    const draftId = searchParams.get('draft');
    if (draftId) { loadExistingBill(draftId); return; }
    // A fresh "Create Bill" starts BLANK (Oct 4, 2026 — previously-entered customer details were being poured
    // back in, even another person's). An unfinished bill of this login at this pharmacy is only offered.
    setPendingDraft(readBillDraft());
  }, [billId]); // eslint-disable-line react-hooks/exhaustive-deps

  const resumeDraft = () => {
    const d = pendingDraft;
    if (!d) return;
    setCustomerName(d.customerName || ''); setCustomerPhone(d.customerPhone || '');
    setDoctorName(d.doctorName || ''); setItems(d.items || []);
    // Payment type is intentionally NOT restored — "Create Bill" always defaults to Cash (Sep 19, 2026).
    setDraftNumber(d.draftNumber || Math.floor(1000 + Math.random() * 9000));
    setPendingDraft(null);
  };
  const discardDraft = () => { clearBillDraft(); setPendingDraft(null); };

  // Auto-focus the item search bar on a fresh "Create Bill" — Abinash, Sep
  // 19, 2026: nothing was focused before, forcing an extra click before the
  // user could start typing a medicine name.
  useEffect(() => {
    if (!isInitialising && viewMode === 'new' && !billId) {
      searchInputRef.current?.focus();
    }
  }, [isInitialising, viewMode, billId]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const h = (e) => {
      if (e.ctrlKey && e.key === 'f') { e.preventDefault(); searchInputRef.current?.focus(); }
      if (e.key === 'F8')  { e.preventDefault(); saveDraft(); toast.success('Bill held'); }
      if (e.key === 'F12') { e.preventDefault(); saveBill(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [saveDraft]);

  // ── Schedule H guard ──────────────────────────────────────────────────────
  const openFinaliseModal = useCallback(() => {
    if (!billItems.length)  { toast.error('Add items to bill first'); return; }
    if (!paymentType)       { toast.error('Select a payment method'); return; }
    if (paymentType === 'multiple') {
      const splitError = getPaymentSplitsError(paymentSplits, grandTotal);
      if (splitError) { toast.error(splitError); return; }
    }
    const hasH  = billItems.some(i => i.schedule === 'H' || i.schedule === 'H1' || i.scheduleH);
    const hasH1 = billItems.some(i => i.schedule === 'H1');
    if ((hasH && !doctorName?.trim()) || (hasH1 && !patientAddress?.trim())) {
      setShowScheduleH(true);
      return;
    }
    setShowFinalise(true);
  }, [billItems, paymentType, doctorName, patientAddress, paymentSplits, grandTotal]);

  const hasH1Item = billItems.some(i => i.schedule === 'H1');

  // ── Bill actions ──────────────────────────────────────────────────────────
  const billSnapshot = {
    billItems, customerName, customerPhone, customerId, doctorName, paymentType, paymentSplits,
    billDiscount, billDiscountType, mrpTotal, totalDiscount, totalGst, totalCess,
    grandTotal, subtotal, margin, draftNumber, editingDraftId,
    patientAddress, patientAge, billDate,
  };

  // Real pharmacy identity for the printed receipt — previously fetched but
  // never passed to print, so real receipts only showed a hardcoded fallback.
  const printPharmacyInfo = buildPrintPharmacyInfo(pharmacyGeneral, printSettings, gstSettings);

  const { saveBill, saveBillAndPrint, parkBill, confirmAndSaveBill, isSaving } =
    useBillActions(billSnapshot, clearBill, setSavedBillData, printPharmacyInfo, autoPrintInvoice);

  // Editing an already-finalized (paid/due) bill, not finalizing a new one —
  // changes header labels/actions (no Park Bill, "Save Changes" instead of
  // "Finalise Bill") per docs/15_ROADMAP.md's Billing table, Sep 18 2026.
  const isCorrection = viewMode === 'edit' && loadedBill
    && loadedBill.status !== 'draft' && loadedBill.status !== 'parked';

  // ── Render ────────────────────────────────────────────────────────────────
  if (isInitialising) return <PageSkeleton />;

  if (viewMode !== 'view' && !isDrugLicenseValid(pharmacyGeneral)) {
    return <DrugLicenseRequiredState expired={isDrugLicenseExpired(pharmacyGeneral)} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <BillingHeader
        viewMode={viewMode} loadedBill={loadedBill} draftNumber={draftNumber}
        isCorrection={isCorrection}
        isSaving={isSaving}
        printFormat={printFormat} onPrintFormatChange={setPrintFormat}
        onBack={() => navigate('/billing')}
        onParkBill={parkBill}
        onSavePrint={saveBillAndPrint}
        onFinalise={openFinaliseModal}
        onPrint={() => window.print()}
        onReturn={() => navigate(`/billing/returns/new?billId=${loadedBill?.id}`)}
        onHistory={() => toast.info('History coming soon')}
      />

      <main className="flex-grow p-4 lg:p-6 overflow-hidden flex flex-col gap-4">
        {pendingDraft && viewMode === 'new' && (
          <ResumeDraftBanner draft={pendingDraft} onResume={resumeDraft} onDiscard={discardDraft} />
        )}
        <BillingSubbar
          viewMode={viewMode} billDate={billDate} onBillDateChange={setBillDate}
          customerName={customerName} customerPhone={customerPhone}
          onPatientSelect={({ name, phone, id }) => { setCustomerName(name); setCustomerPhone(phone || ''); setCustomerId(id || null); saveDraft(); }}
          doctorName={doctorName} onDoctorChange={setDoctorName}
          paymentType={paymentType} onPaymentTypeChange={(v) => { setPaymentType(v); if (v !== 'multiple') setPaymentSplits([]); saveDraft(); }}
          paymentSplits={paymentSplits} onPaymentSplitsChange={setPaymentSplits}
          grandTotal={grandTotal}
        />

        <BillingTable
          viewMode={viewMode} billItems={billItems}
          onUpdateItem={updateItem} onRemoveItem={removeItem}
          onItemAdded={(p, b) => { addItem(p, b); saveDraft(); }}
          searchInputRef={searchInputRef}
          nearExpiryDays={nearExpiryDays}
        />

        <BillingFooter
          billItems={billItems}
          mrpTotal={mrpTotal} totalDiscount={totalDiscount}
          totalGst={totalGst} totalCess={totalCess}
          grandTotal={grandTotal} margin={margin}
        />
      </main>

      <ScheduleHWarning
        open={showScheduleH}
        requireAddress={hasH1Item}
        doctorName={doctorName} onDoctorNameChange={setDoctorName}
        patientAddress={patientAddress} onPatientAddressChange={setPatientAddress}
        patientAge={patientAge} onPatientAgeChange={setPatientAge}
        onCancel={() => setShowScheduleH(false)}
        onConfirm={() => { setShowScheduleH(false); setShowFinalise(true); }}
      />
      <FinaliseModal
        open={showFinalise} onClose={() => setShowFinalise(false)}
        customerName={customerName} paymentType={paymentType} paymentSplits={paymentSplits}
        mrpTotal={mrpTotal} totalDiscount={totalDiscount}
        billDiscount={billDiscount} billDiscountType={billDiscountType}
        totalGst={totalGst} totalCess={totalCess} grandTotal={grandTotal} margin={margin}
        isSaving={isSaving}
        isCorrection={isCorrection}
        onConfirm={(notes) => confirmAndSaveBill(notes).then(() => setShowFinalise(false))}
      />
      <PrintReceipt billData={savedBillData} format={printFormat} />
    </div>
  );
}
