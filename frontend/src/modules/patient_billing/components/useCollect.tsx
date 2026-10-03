/**
 * useCollect — "Collect" for a patient, wherever the button lives (billing desk row, patient bill).
 * Looks at the patient's account and collects what is owed: their unbilled charges first (one new
 * invoice), otherwise the balance of their oldest unpaid invoice. Anything left shows up again
 * as a pending row, so a second click collects the next part.
 */
import React, { useCallback, useState } from 'react';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { CHARGE_SOURCE, CHARGE_STATUS, INVOICE_STATUS } from '@/constants/domainConstants';
import CollectPaymentDialog, { CollectCharge } from './CollectPaymentDialog';
import type { AccountDetail } from '../types';

interface Target {
  patientId: string;
  patientName: string;
  charges: CollectCharge[];
  existingInvoice: { id: string; invoice_number: string; balance_paise: number } | null;
}

export function useCollect(onDone: () => void) {
  const [target, setTarget] = useState<Target | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const start = useCallback(async (patientId: string, patientName: string) => {
    setBusyId(patientId);
    try {
      const { data } = await api.get(apiUrl.pbAccount(patientId)) as { data: AccountDetail };
      // Medicines are billed by the pharmacy, never here.
      const unbilled = data.charges.filter((c) => c.status === CHARGE_STATUS.UNBILLED && c.source_module !== CHARGE_SOURCE.PHARMACY);
      const open = data.invoices.find((i) => (i.status === INVOICE_STATUS.ISSUED || i.status === INVOICE_STATUS.PART_PAID)
        && i.balance_paise > 0);
      if (unbilled.length) {
        setTarget({ patientId, patientName, existingInvoice: null,
          charges: unbilled.map((c) => ({ id: c.id, description: c.description, total_paise: c.total_paise })) });
      } else if (open) {
        setTarget({ patientId, patientName, charges: [],
          existingInvoice: { id: open.id, invoice_number: open.invoice_number, balance_paise: open.balance_paise } });
      } else {
        toast.info(`Nothing to collect for ${patientName}`);
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }, []);

  const dialog = target ? (
    <CollectPaymentDialog open patientId={target.patientId} patientName={target.patientName}
      charges={target.charges} existingInvoice={target.existingInvoice}
      onClose={() => setTarget(null)} onCollected={onDone} />
  ) : null;

  return { start, dialog, busyId };
}
