/**
 * useBillActions
 *
 * All async bill operations: save, save-and-print, park,
 * confirm (finalise), and print-current.
 *
 * Returns { saveBill, saveBillAndPrint, parkBill,
 *           confirmAndSaveBill, handlePrintCurrentBill, isSaving }
 *
 * The hook does NOT own bill state — it only reads the snapshot values
 * passed in via `billSnapshot` and fires callbacks on success/failure.
 * Payload-building and pre-save guards live in ../utils/buildBillPayload.js
 * (split out Sep 18, 2026 to keep this file under the 300-line rule).
 */
import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { buildBillBase, guardBillForSave } from '../utils/buildBillPayload';
import { clearBillDraft } from '../utils/billDraft';

/**
 * @param {object} billSnapshot  — read-only snapshot of current bill state
 *   .billItems, .customerName, .customerPhone, .doctorName,
 *   .paymentType, .billDiscount, .billDiscountType,
 *   .mrpTotal, .totalDiscount, .totalGst, .totalCess,
 *   .grandTotal, .subtotal, .margin, .draftNumber, .editingDraftId,
 *   .patientAddress, .patientAge — Schedule H1 register fields, only
 *   required when the bill contains an H1 item (see ScheduleHWarning)
 * @param {Function} onSaveSuccess   — called after any successful save
 * @param {Function} onPrintReady    — called with billData to trigger window.print()
 * @param {object}   printPharmacyInfo — pharmacy_name/address/phone/gstin/
 *   drug_license/fssai/pan/bill_header/bill_footer/print_signature/
 *   print_patient_name, already filtered by the Show-on-Bill toggles
 * @param {boolean}  autoPrintInvoice — Settings → Billing "Auto-print
 *   invoice after checkout": when true, confirmAndSaveBill (the normal
 *   Finalize action) prints automatically, same as the explicit
 *   saveBillAndPrint action always does.
 */
export function useBillActions(billSnapshot, onSaveSuccess, onPrintReady, printPharmacyInfo = {}, autoPrintInvoice = false) {
  const navigate  = useNavigate();
  const [isSaving, setIsSaving] = useState(false);

  const guard = (opts) => {
    const err = guardBillForSave(billSnapshot, opts);
    if (err) toast.error(err);
    return !err;
  };

  // Editing an existing bill (a resumed draft, or a same-day correction to
  // an already-finalized bill — docs/15_ROADMAP.md's Billing table, Sep 18
  // 2026) must PUT to the real row, not POST a brand-new one. Found while
  // wiring this: every save path here always POSTed, even in edit mode —
  // resuming and finalizing a parked draft silently left the original
  // DRAFT-xxxx row behind as an orphan instead of updating it. Routing
  // through PUT when editingDraftId is set fixes that same-shaped bug too.
  const isEditingExisting = () => !!billSnapshot.editingDraftId;
  const submitBill = (payload) => isEditingExisting()
    ? api.put(apiUrl.bill(billSnapshot.editingDraftId), payload)
    : api.post(apiUrl.bills(), payload);
  const savedMsg = (res, created) => isEditingExisting()
    ? `Bill #${res.data.bill_number} updated!`
    : `Bill #${res.data.bill_number} ${created}!`;

  const afterSuccess = () => {
    clearBillDraft();
    onSaveSuccess?.();
    navigate('/billing');
  };

  // ── saveBill ─────────────────────────────────────────────────────────────
  const saveBill = useCallback(async () => {
    if (!guard()) return;
    try {
      const res = await submitBill(buildBillBase(billSnapshot, 'paid'));
      toast.success(savedMsg(res, 'created successfully'));
      afterSuccess();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save bill');
    }
  }, [billSnapshot]);

  // ── saveBillAndPrint ──────────────────────────────────────────────────────
  const saveBillAndPrint = useCallback(async () => {
    if (!guard()) return;
    const { paymentType, billItems, customerName, customerPhone, doctorName, subtotal, totalDiscount, totalGst, grandTotal } = billSnapshot;
    try {
      const res = await submitBill(buildBillBase(billSnapshot, 'paid'));
      toast.success(savedMsg(res, 'created'));
      onPrintReady?.({
        ...printPharmacyInfo,
        bill_number:    res.data.bill_number,
        items:          billItems,
        customer_name:  customerName || 'Walk-in Customer',
        customer_phone: customerPhone,
        doctor_name:    doctorName,
        payment_method: paymentType,
        payment_splits: paymentType === 'multiple' ? billSnapshot.paymentSplits : undefined,
        subtotal,
        total_discount: totalDiscount,
        total_gst:      totalGst,
        grand_total:    grandTotal,
      });
      clearBillDraft();
      setTimeout(() => { window.print(); afterSuccess(); }, 200);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save bill');
    }
    // Every callback in this hook intentionally tracks only billSnapshot (and
    // now printPharmacyInfo) — helpers/onPrintReady are stable closures, not state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billSnapshot, printPharmacyInfo]);

  // ── parkBill ─────────────────────────────────────────────────────────────
  const parkBill = useCallback(async () => {
    if (!guard({ requirePayment: false })) return;
    try {
      await submitBill(buildBillBase(billSnapshot, 'draft'));
      toast.success('Bill parked! Can be resumed later.');
      afterSuccess();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to park bill');
    }
  }, [billSnapshot]);

  // ── confirmAndSaveBill (finalise) ─────────────────────────────────────────
  const confirmAndSaveBill = useCallback(async ({ internalNote }) => {
    if (!guard()) return;
    setIsSaving(true);
    const {
      paymentType, mrpTotal, totalDiscount, totalGst, totalCess,
      grandTotal, margin, billDiscount, billDiscountType,
      billItems, customerName, customerPhone, doctorName, subtotal,
    } = billSnapshot;

    let billDiscAmt = 0;
    if (billDiscount > 0) {
      billDiscAmt = billDiscountType === '%'
        ? mrpTotal * (billDiscount / 100)
        : billDiscount;
    }

    const payload = {
      ...buildBillBase(billSnapshot, 'paid'),
      mrp_total:      mrpTotal,
      item_discount:  totalDiscount - billDiscAmt,
      bill_discount:  billDiscAmt,
      discount:       totalDiscount,
      gst_amount:     totalGst,
      cgst_amount:    totalGst / 2,
      sgst_amount:    totalGst / 2,
      cess_amount:    totalCess,
      margin_amount:  margin.amount,
      margin_percent: margin.percent,
      total_amount:   grandTotal,
      grand_total:    grandTotal,
      round_off:      0,
      internal_note:  internalNote,
    };

    try {
      const res = await submitBill(payload);
      toast.success(savedMsg(res, 'created successfully'));
      if (autoPrintInvoice) {
        // Settings → Billing "Auto-print invoice after checkout" — found
        // Sep 13, 2026 (Settings product-review): this toggle saved but
        // was never read anywhere in the frontend, so it had no effect
        // regardless of what a pharmacy configured.
        onPrintReady?.({
          ...printPharmacyInfo,
          bill_number:    res.data.bill_number,
          items:          billItems,
          customer_name:  customerName || 'Walk-in Customer',
          customer_phone: customerPhone,
          doctor_name:    doctorName,
          payment_method: paymentType,
          payment_splits: paymentType === 'multiple' ? billSnapshot.paymentSplits : undefined,
          subtotal,
          total_discount: totalDiscount,
          total_gst:      totalGst,
          grand_total:    grandTotal,
        });
        setTimeout(() => { window.print(); afterSuccess(); }, 200);
      } else {
        afterSuccess();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save bill. Transaction rolled back.');
    } finally {
      setIsSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see saveBillAndPrint above
  }, [billSnapshot, printPharmacyInfo, autoPrintInvoice]);

  // ── handlePrintCurrentBill ────────────────────────────────────────────────
  const handlePrintCurrentBill = useCallback(() => {
    const { billItems, customerName, customerPhone, doctorName, paymentType, paymentSplits, draftNumber, subtotal, totalDiscount, totalGst, grandTotal } = billSnapshot;
    if (billItems.length === 0) { toast.error('Add items to bill first'); return; }
    onPrintReady?.({
      ...printPharmacyInfo,
      bill_number:    draftNumber ? `DRAFT-${draftNumber}` : 'PREVIEW',
      items:          billItems,
      customer_name:  customerName || 'Walk-in Customer',
      customer_phone: customerPhone,
      doctor_name:    doctorName,
      payment_method: paymentType,
      payment_splits: paymentType === 'multiple' ? paymentSplits : undefined,
      subtotal,
      total_discount: totalDiscount,
      total_gst:      totalGst,
      grand_total:    grandTotal,
    });
    setTimeout(() => window.print(), 100);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see saveBillAndPrint above
  }, [billSnapshot, printPharmacyInfo]);

  return { saveBill, saveBillAndPrint, parkBill, confirmAndSaveBill, handlePrintCurrentBill, isSaving };
}
