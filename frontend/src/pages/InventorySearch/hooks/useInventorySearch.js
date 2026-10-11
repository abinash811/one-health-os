/**
 * useInventorySearch
 *
 * Owns search query, active filters, inventory results, and pagination.
 * Wires debounced search → fetch. Always fetches (including on mount) —
 * with no search/filters yet, the page's default landing state shows the
 * 10 most recently added medicines instead of a blank "search to begin"
 * screen; search/filters are how a pharmacist reaches the rest of the
 * catalog.
 *
 * Returns:
 *   searchQuery, setSearchQuery
 *   activeFilters, applyFilters, removeFilter, clearAllFilters
 *   filterOptions
 *   inventory, loading, hasActiveQuery  — false = showing the default 10-recent view
 *   currentPage, totalPages, totalItems, setPage
 *   refetch  () — re-run current fetch (after add/edit/adjust)
 */
import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useDebounce } from '@/hooks/useDebounce';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

// Fallback only, used before GET /inventory/filters responds (or if it
// fails) — the real request now returns all of these for real (see the
// comment at its call site), including correcting a stray 28% GST option
// here that was never a valid slab (backend's VALID_GST_RATES = {0,5,12,18}).
const DEFAULT_FILTER_OPTIONS = {
  categories: [],
  dosage_types: ['Tablet','Capsule','Syrup','Injection','Cream','Drops','Powder','Gel','Ointment'],
  schedule_types: ['OTC','H1','H','X'],
  gst_rates: [0, 5, 12, 18],
  locations: ['Store A','Store B','Warehouse','Counter'],
};

// Simple in-memory cache (survives re-renders, lost on refresh)
let _filterCache = null;

export function useInventorySearch() {
  const [searchParams] = useSearchParams();
  const [searchQuery,   setSearchQuery]   = useState('');
  // Can arrive pre-set via URL (?stock_status=low_stock|near_expiry) so the
  // Dashboard's Low Stock/Expiring Soon "View All" buttons drill straight
  // into the same filtered list instead of landing on an unfiltered page.
  const [activeFilters, setActiveFilters] = useState(() => {
    const stockStatus = searchParams.get('stock_status');
    return stockStatus ? { stock_status: stockStatus } : {};
  });
  const [filterOptions, setFilterOptions] = useState(DEFAULT_FILTER_OPTIONS);

  const [inventory,   setInventory]   = useState([]);
  // Starts true: the page always fetches on mount now (default view = 10
  // most recently added), so there's no pre-fetch frame to render — see
  // Manifesto rule 16, no blank/flash screen while data loads.
  const [loading,     setLoading]     = useState(true);

  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages,  setTotalPages]  = useState(1);
  const [totalItems,  setTotalItems]  = useState(0);

  const debouncedSearch = useDebounce(searchQuery, 500);

  // ── Load filter options on mount ────────────────────────────────────────
  // Extracted so refetch() (called after add/edit/adjust) can force a real
  // re-fetch, not just null the cache for some future component mount that
  // may never happen in a single-page app — a newly added brand/category/
  // location used to never appear in FilterDrawer or BulkUpdateModal until
  // a hard page reload, found while live-testing the new Brand bulk-update
  // field this same fix ships with.
  const loadFilterOptions = useCallback(async (force = false) => {
    if (_filterCache && !force) { setFilterOptions(_filterCache); return; }
    try {
      const res = await api.get(apiUrl.inventoryFilters());
      // dosage_types/schedule_types/gst_rates/locations used to always
      // be the hardcoded defaults above regardless of what the backend
      // returned — these 4 filters looked real in the UI but never
      // actually filtered anything (see docs/15_ROADMAP.md RULE MISSES
      // LOG). Fixed August 22, 2026: GET /inventory/filters now returns
      // all of these for real, and they're used here instead.
      const opts = {
        categories:     res.data.categories     || [],
        brands:         res.data.brands          || [],
        dosage_types:   res.data.dosage_forms    || DEFAULT_FILTER_OPTIONS.dosage_types,
        schedule_types: res.data.schedules       || DEFAULT_FILTER_OPTIONS.schedule_types,
        gst_rates:      res.data.gst_rates       || DEFAULT_FILTER_OPTIONS.gst_rates,
        locations:      res.data.locations       || DEFAULT_FILTER_OPTIONS.locations,
        stock_statuses: res.data.statuses        || [],
      };
      _filterCache = opts;
      setFilterOptions(opts);
    } catch { /* use defaults */ }
  }, []);

  useEffect(() => {
    loadFilterOptions();
  }, [loadFilterOptions]);

  // ── Fetch when debounced search or filters change ───────────────────────
  const hasActiveQuery = debouncedSearch.length >= 2 || Object.keys(activeFilters).length > 0;

  const fetchInventory = useCallback(async (page = currentPage) => {
    setLoading(true);
    try {
      // No search/filters yet (the page's default landing state): show only
      // the 10 most recently added medicines — search/filters are how a
      // pharmacist reaches the rest of the catalog, not pagination.
      const params = { page, page_size: hasActiveQuery ? 20 : 10 };
      if (debouncedSearch.length >= 2) params.search        = debouncedSearch;
      if (activeFilters.stock_status) params.status_filter  = activeFilters.stock_status;
      if (activeFilters.category)     params.category_filter = activeFilters.category;
      if (activeFilters.requires_refrigeration) params.cold_chain_only = true;
      if (activeFilters.dosage_type)  params.dosage_form_filter = activeFilters.dosage_type;
      if (activeFilters.schedule)     params.schedule_filter = activeFilters.schedule;
      if (activeFilters.gst)          params.gst_filter = activeFilters.gst;
      if (activeFilters.location)     params.location_filter = activeFilters.location;

      const res = await api.get(apiUrl.inventory(params));
      setInventory(res.data.items || []);
      setTotalPages(res.data.pagination?.total_pages || 1);
      setTotalItems(res.data.pagination?.total_items || 0);
    } catch (err) {
      toast.error(err.message || 'Failed to load inventory');
      setInventory([]);
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately run only on these inputs; adding the missing ones would re-run it on every render
  }, [debouncedSearch, activeFilters, currentPage]);

  useEffect(() => {
    fetchInventory(currentPage);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately run only on these inputs; adding the missing ones would re-run it on every render
  }, [debouncedSearch, activeFilters, currentPage]);

  // ── Filter helpers ───────────────────────────────────────────────────────
  const applyFilters = useCallback((newFilters) => {
    const clean = Object.fromEntries(Object.entries(newFilters).filter(([, v]) => v && v !== ''));
    setActiveFilters(clean);
    setCurrentPage(1);
  }, []);

  const removeFilter = useCallback((key) => {
    setActiveFilters(prev => { const n = { ...prev }; delete n[key]; return n; });
  }, []);

  const clearAllFilters = useCallback(() => {
    setActiveFilters({}); setSearchQuery(''); setCurrentPage(1);
  }, []);

  const setPage = useCallback((p) => setCurrentPage(p), []);

  const refetch = useCallback(() => {
    fetchInventory(currentPage);
    loadFilterOptions(true); // real re-fetch, not just a cache null — see loadFilterOptions above
  }, [fetchInventory, currentPage, loadFilterOptions]);

  return {
    searchQuery, setSearchQuery,
    activeFilters, applyFilters, removeFilter, clearAllFilters,
    filterOptions,
    inventory, loading, hasActiveQuery,
    currentPage, totalPages, totalItems, setPage,
    refetch,
  };
}
