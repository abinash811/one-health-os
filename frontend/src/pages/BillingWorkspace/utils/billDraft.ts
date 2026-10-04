/**
 * The unfinished-bill draft kept in this browser so a closed tab or a held bill (F8) is not lost.
 *
 * It belongs to ONE login at ONE pharmacy: another person on the same computer, or the same person after
 * switching pharmacy, never sees it. It is never poured into a new bill automatically — "Create Bill" starts
 * blank and offers to resume (ResumeDraftBanner). Drafts older than a day are dropped. The old single
 * `billing_draft` key (shared by everyone, with customer names and phones in it) is deleted on sight.
 */
const LEGACY_KEY = 'billing_draft';
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface BillDraft {
  customerName: string;
  customerPhone: string;
  doctorName: string;
  items: unknown[];
  draftNumber: number | null;
  savedAt: number;
}

let owner = '';

/** Who the draft belongs to — set once by the billing screen from the signed-in user and active pharmacy. */
export function setDraftOwner(userId?: string, pharmacyId?: string): void {
  owner = userId && pharmacyId ? `${userId}:${pharmacyId}` : '';
}

const key = (): string | null => (owner ? `${LEGACY_KEY}:${owner}` : null);

const safe = <T,>(fn: () => T, fallback: T): T => {
  try { return fn(); } catch { return fallback; }   // storage can be blocked or full — drafts are a convenience only
};

export function readBillDraft(): BillDraft | null {
  return safe(() => {
    localStorage.removeItem(LEGACY_KEY);
    const k = key();
    const raw = k && localStorage.getItem(k);
    if (!raw) return null;
    const d = JSON.parse(raw) as BillDraft;
    if (!d.savedAt || Date.now() - d.savedAt > MAX_AGE_MS || !Array.isArray(d.items) || d.items.length === 0) {
      localStorage.removeItem(k);
      return null;
    }
    return d;
  }, null);
}

export function writeBillDraft(draft: Omit<BillDraft, 'savedAt'>): void {
  safe(() => {
    const k = key();
    if (k) localStorage.setItem(k, JSON.stringify({ ...draft, savedAt: Date.now() }));
  }, undefined);
}

export function clearBillDraft(): void {
  safe(() => {
    localStorage.removeItem(LEGACY_KEY);
    const k = key();
    if (k) localStorage.removeItem(k);
  }, undefined);
}
