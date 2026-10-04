/**
 * ResumeDraftBanner — "You have an unfinished bill" on a fresh Create Bill. The bill itself starts blank; the
 * person chooses to bring the old one back or throw it away. One line, two buttons, never a modal.
 */
import React from 'react';
import { FileClock } from 'lucide-react';
import { AppButton } from '@/components/shared';
import type { BillDraft } from '../utils/billDraft';

interface Props { draft: BillDraft; onResume: () => void; onDiscard: () => void }

export default function ResumeDraftBanner({ draft, onResume, onDiscard }: Props) {
  const n = draft.items.length;
  const who = draft.customerName && draft.customerName !== 'Walk-in Customer' ? ` for ${draft.customerName}` : '';
  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900"
      data-testid="resume-draft-banner" role="status">
      <FileClock className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1">You have an unfinished bill{who} · {n} item{n !== 1 ? 's' : ''}</span>
      <AppButton size="sm" variant="secondary" onClick={onResume} data-testid="resume-draft-btn">Resume</AppButton>
      <AppButton size="sm" variant="ghost" onClick={onDiscard} data-testid="discard-draft-btn">Discard</AppButton>
    </div>
  );
}
