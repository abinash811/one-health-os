import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import type { PagedResponse } from './types';

/** Loads `url` (null = don't) and reloads when it — or `tick` — changes. Errors keep their real
 *  reason in `error` for the page to show. `loading` is true only until the first answer, so
 *  filtering doesn't flash the whole table back to a skeleton. */
export function useQuery<T>(url: string | null, tick = 0) {
  const [state, setState] = useState<{ data: T | null; error: string; status: number; loading: boolean }>(
    { data: null, error: '', status: 0, loading: true });

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(url);
        if (!cancelled) setState({ data: res.data as T, error: '', status: res.status ?? 200, loading: false });
      } catch (err) {
        if (!cancelled) {
          const status = (err as { response?: { status?: number } }).response?.status ?? 0;
          setState({ data: null, error: (err as Error).message, status, loading: false });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [url, tick]);

  return state;
}

/** Props for <PaginationBar> from a server page — page number lives in the caller's state. */
export function pageBarProps(page: number, setPage: (p: number) => void, p?: PagedResponse<unknown>['pagination']) {
  const totalItems = p?.total_items ?? 0;
  const totalPages = p?.total_pages ?? 1;
  const size = p?.page_size ?? 20;
  return {
    page, totalPages, totalItems, setPage,
    showingText: totalItems ? `Showing ${(page - 1) * size + 1}–${Math.min(page * size, totalItems)} of ${totalItems}` : '',
    prevPage: () => setPage(Math.max(1, page - 1)), nextPage: () => setPage(Math.min(totalPages, page + 1)),
    isFirstPage: page <= 1, isLastPage: page >= totalPages,
  };
}
