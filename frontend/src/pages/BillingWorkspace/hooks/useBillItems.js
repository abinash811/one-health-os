/**
 * useBillItems
 *
 * Owns billItems array + all derived totals.
 * Returns mutations (updateItem, removeItem, addItem) and computed totals.
 */
import { useState, useEffect, useCallback } from 'react';

const calcItemTotal = (item) => {
  const base  = item.qty * item.unit_price;
  const after = base - base * (item.discount_percent / 100);
  return after + after * (item.gst_percent / 100);
};

export function useBillItems(billDiscount = 0, billDiscountType = '%') {
  const [billItems, setBillItems] = useState([]);

  // ── Derived totals ──────────────────────────────────────────────────────
  const [mrpTotal,      setMrpTotal]      = useState(0);
  const [subtotal,      setSubtotal]      = useState(0);
  const [totalDiscount, setTotalDiscount] = useState(0);
  const [totalGst,      setTotalGst]      = useState(0);
  const [totalCess,     setTotalCess]     = useState(0);
  const [grandTotal,    setGrandTotal]    = useState(0);
  const [margin,        setMargin]        = useState({ amount: 0, percent: 0 });

  useEffect(() => {
    let mrp = 0, itemDisc = 0, gst = 0, cess = 0, cost = 0;
    billItems.forEach((item) => {
      const base  = item.qty * item.unit_price;
      const disc  = base * (item.discount_percent / 100);
      const after = base - disc;
      mrp      += base;
      itemDisc += disc;
      gst      += after * (item.gst_percent / 100);
      cess     += after * ((item.cess_percent || 0) / 100);
      cost     += item.qty * (item.cost_price || item.unit_price * 0.7);
    });
    let billDiscAmt = 0;
    if (billDiscount > 0) {
      billDiscAmt = billDiscountType === '%' ? (mrp - itemDisc) * (billDiscount / 100) : billDiscount;
    }
    const sub   = mrp - itemDisc - billDiscAmt;
    const grand = sub + gst + cess;
    const mAmt  = sub - cost;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resets form/list state when the input changes; moving it out of the effect is a separate refactor
    setMrpTotal(mrp);
    setSubtotal(sub);
    setTotalDiscount(itemDisc + billDiscAmt);
    setTotalGst(gst);
    setTotalCess(cess);
    // Rounded to the nearest rupee, matching create_bill's own rounding
    // (backend/routers/billing.py) and Sales Return's netAmount pattern —
    // the single source of truth shown everywhere (footer, finalise modal,
    // print) must be the figure that's actually charged, not a raw float
    // the backend then silently rounds differently.
    setGrandTotal(Math.round(grand));
    setMargin({ amount: mAmt, percent: cost > 0 ? (mAmt / cost) * 100 : 0 });
  }, [billItems, billDiscount, billDiscountType]);

  // ── Mutations ────────────────────────────────────────────────────────────
  const updateItem = useCallback((index, field, value) => {
    setBillItems((prev) => {
      const items = [...prev];
      items[index] = { ...items[index], [field]: value };
      items[index].net_amount = calcItemTotal(items[index]);
      return items;
    });
  }, []);

  const removeItem = useCallback((index) => {
    setBillItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const addItem = useCallback((product, batch) => {
    setBillItems((prev) => {
      const idx = prev.findIndex(i => i.product_sku === product.sku && i.batch_no === batch.batch_no);
      if (idx >= 0) {
        const items = [...prev];
        items[idx] = { ...items[idx], qty: items[idx].qty + 1 };
        items[idx].net_amount = calcItemTotal(items[idx]);
        return items;
      }
      const ni = {
        id:               Date.now(),
        product_sku:      product.sku,
        product_name:     product.name,
        manufacturer:     product.manufacturer || '',
        composition:      product.composition || product.generic_name || '',
        batch_no:         batch.batch_no,
        batch_id:         batch.id,
        // batch.expiry_date from search-with-batches is a pre-formatted
        // "DD-MM-YYYY" display string (see _batch_for_billing,
        // backend/routers/inventory.py) — date-fns' parseISO can't read
        // that, so every isExpired/isExpiringSoon/formatExpiry call on it
        // silently failed and showed "–". expiry_iso is the real ISO date
        // meant for exactly this. Other batch sources (stock/batches) only
        // ever send an already-ISO expiry_date, so the fallback is safe.
        expiry_date:      batch.expiry_iso || batch.expiry_date,
        qty:              1,
        unit_price:       batch.mrp_per_unit || product.default_mrp || 0,
        cost_price:       batch.cost_price_per_unit || (batch.mrp_per_unit || 0) * 0.7,
        discount_percent: batch.discount_percent || 0,
        gst_percent:      product.gst_percent || 5,
        cess_percent:     product.cess_percent || 0,
        available_qty:    batch.qty_on_hand || 0,
        schedule:         product.schedule || null,
        scheduleH:        product.scheduleH || product.schedule === 'H' || product.schedule === 'H1',
        net_amount:       0,
      };
      ni.net_amount = calcItemTotal(ni);
      return [...prev, ni];
    });
  }, []);

  const setItems = setBillItems; // expose for loading existing bill

  return {
    billItems, setItems,
    updateItem, removeItem, addItem,
    mrpTotal, subtotal, totalDiscount, totalGst, totalCess, grandTotal, margin,
  };
}
