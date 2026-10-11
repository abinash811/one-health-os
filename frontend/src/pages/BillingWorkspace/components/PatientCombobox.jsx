/**
 * PatientCombobox — inline typeahead for patient selection in billing.
 *
 * Replaces the modal-based PatientSearchModal + chip button.
 * Behaviour:
 *   - Click field → opens dropdown, shows recent / walk-in option
 *   - Type → debounced search against /customers
 *   - Select existing → fills name + phone
 *   - "+ Add [name]" → compact mini-form (name + phone) → creates customer → selects
 *   - Walk-in → clears to counter sale
 *   - Click outside / Escape → closes
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { UserPlus, Search, User } from 'lucide-react';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { useDebounce } from '@/hooks/useDebounce';
import { toast } from 'sonner';
import { AppButton } from '@/components/shared';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import AddPersonMiniForm from './AddPersonMiniForm';

export default function PatientCombobox({ value, onSelect, readOnly }) {
  const [open,    setOpen]    = useState(false);
  const [query,   setQuery]   = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', phone: '' });
  const [saving,  setSaving]  = useState(false);

  const wrapperRef  = useRef(null);
  const contentRef  = useRef(null);
  const inputRef    = useRef(null);
  const addNameRef  = useRef(null);
  const debouncedQ  = useDebounce(query, 250);

  // Focus the mini add-form's name field when it opens — a plain JSX
  // `autoFocus` prop trips the jsx-a11y/no-autofocus lint rule.
  useEffect(() => {
    if (showAdd) addNameRef.current?.focus();
  }, [showAdd]);

  // Search patients when query changes
  useEffect(() => {
    if (!open) return;
    if (!debouncedQ.trim()) { setResults([]); return; }
    let cancelled = false;
    setLoading(true);
    // No /patients endpoint exists — /customers is the correct source
    api.get(apiUrl.customers({ search: debouncedQ, page_size: 8 }))
      .then(res => { if (!cancelled) setResults(res.data.data || res.data || []); })
      .catch(() => { if (!cancelled) setResults([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [debouncedQ, open]);

  // Close on outside click. Content renders via a Radix Portal (see below),
  // so it's no longer a DOM descendant of wrapperRef — must also exempt
  // clicks inside contentRef, or picking a result/the "Add new" button/the
  // mini-form's own buttons always misfired this as an "outside" click
  // first (same bug class fixed the same day in DoctorDropdown.jsx).
  useEffect(() => {
    const handler = (e) => {
      const inWrapper = wrapperRef.current && wrapperRef.current.contains(e.target);
      const inContent = contentRef.current && contentRef.current.contains(e.target);
      if (!inWrapper && !inContent) {
        setOpen(false);
        setShowAdd(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const openDropdown = () => {
    if (readOnly) return;
    setOpen(true);
    setQuery('');
    setResults([]);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const select = useCallback((patient) => {
    if (patient === 'walkin') {
      onSelect({ name: 'Counter Sale', phone: '', id: null });
    } else {
      onSelect({ name: patient.name, phone: patient.phone || patient.mobile || '', id: patient.id });
    }
    setOpen(false);
    setQuery('');
    setShowAdd(false);
  }, [onSelect]);

  const handleKey = (e) => {
    if (e.key === 'Escape') { setOpen(false); setShowAdd(false); setQuery(''); }
  };

  const handleAddSave = async () => {
    if (!addForm.name.trim()) { toast.error('Name is required'); return; }
    setSaving(true);
    try {
      const res = await api.post(apiUrl.customers(), {
        name: addForm.name.trim(),
        phone: addForm.phone.trim(),
        customer_type: 'regular',
      });
      const created = res.data;
      toast.success(`${created.name} added`);
      select(created);
    } catch {
      toast.error('Failed to add customer');
    } finally {
      setSaving(false);
    }
  };

  const displayValue = value || 'Walk-in patient';
  const noResults    = !loading && query.trim().length > 0 && results.length === 0;

  // Content renders via Radix Popover (portals to document.body) instead
  // of a plain `absolute` div — found Sep 13, 2026 (Billing product-review):
  // BillingSubbar's toolbar row has `overflow-x-auto`, which per the CSS
  // overflow spec forces `overflow-y` to also clip ("auto"), silently
  // hiding any plain-absolute dropdown nested inside it, no matter its
  // z-index. Same fix as DoctorDropdown.jsx, same day.
  return (
    <Popover open={open}>
      <PopoverAnchor asChild>
        <div ref={wrapperRef} className="relative">
          {!open ? (
            <AppButton
              variant="chip"
              onClick={openDropdown}
              className="w-40 h-9 px-2.5 justify-between gap-1 text-sm border border-gray-200 rounded-lg bg-white hover:bg-gray-50"
              title={displayValue}
              data-testid="patient-chip"
            >
              <span className={`truncate ${!value ? 'text-gray-400' : ''}`}>{displayValue}</span>
              <svg className="w-3 h-3 text-gray-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </AppButton>
          ) : (
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKey}
              placeholder={value || 'Search patient...'}
              className="w-40 h-9 px-2.5 text-sm font-medium text-gray-900 border border-brand rounded-lg outline-none bg-white focus:ring-2 focus:ring-brand placeholder:text-gray-400 placeholder:font-normal"
              data-testid="patient-search-input"
            />
          )}
        </div>
      </PopoverAnchor>

      <PopoverContent
        ref={contentRef}
        className="w-64 p-0 overflow-hidden"
        align="start"
        sideOffset={4}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onCloseAutoFocus={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        {!showAdd ? (
          <>
            {/* Walk-in always first */}
            <AppButton
              variant="ghost"
              onClick={() => select('walkin')}
              className="w-full justify-start px-3 py-2 text-sm text-gray-600 border-b border-gray-100 rounded-none"
              icon={<User className="w-3.5 h-3.5 text-gray-400" />}
            >
              Counter / Walk-in
            </AppButton>

            {/* Loading */}
            {loading && (
              <div className="px-3 py-3 text-xs text-gray-400 flex items-center gap-2">
                <div className="w-3 h-3 border border-gray-300 border-t-brand rounded-full animate-spin" />
                Searching...
              </div>
            )}

            {/* Results */}
            {results.map(p => (
              <div
                key={p.id}
                role="button"
                tabIndex={0}
                onClick={() => select(p)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(p); } }}
                className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-brand/5 transition-colors cursor-pointer"
                data-testid={`patient-result-${p.id}`}
              >
                <User className="w-3.5 h-3.5 text-gray-400 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm font-medium text-gray-900">{p.name}</div>
                  {p.phone && <div className="text-xs text-gray-500">{p.phone}</div>}
                </div>
              </div>
            ))}

            {/* Add new */}
            {(noResults || (query.trim() && results.length < 8)) && query.trim() && (
              <AppButton
                variant="ghost"
                onClick={() => { setShowAdd(true); setAddForm({ name: query.trim(), phone: '' }); }}
                className="w-full justify-start px-3 py-2.5 text-sm text-brand hover:bg-brand/5 hover:text-brand border-t border-gray-100 rounded-none"
                icon={<UserPlus className="w-3.5 h-3.5" />}
                data-testid="patient-add-new"
              >
                Add "{query.trim()}" as new customer
              </AppButton>
            )}

            {/* Empty state — found Sep 19, 2026 (Abinash, testing zero-data):
                showed a "type to search" hint but no button, unlike other
                empty states in the app (Billing/Purchases lists) which all
                show a centered CTA. A genuinely new pharmacy with zero
                customers had no visible way to add its first one here. */}
            {!loading && !query.trim() && (
              <div className="px-3 py-4 flex flex-col items-center gap-2 text-center">
                <Search className="w-4 h-4 text-gray-300" />
                <p className="text-xs text-gray-400">Type to search, or add a new customer</p>
                <AppButton
                  variant="outline"
                  size="sm"
                  onClick={() => { setShowAdd(true); setAddForm({ name: '', phone: '' }); }}
                  icon={<UserPlus className="w-3.5 h-3.5" />}
                  data-testid="patient-add-new-empty"
                >
                  Add Customer
                </AppButton>
              </div>
            )}
          </>
        ) : (
          <AddPersonMiniForm
            title="New Customer"
            namePlaceholder="Full name *"
            nameRef={addNameRef}
            name={addForm.name}
            onNameChange={(v) => setAddForm(f => ({ ...f, name: v }))}
            secondPlaceholder="Phone (optional)"
            secondValue={addForm.phone}
            onSecondChange={(v) => setAddForm(f => ({ ...f, phone: v }))}
            secondMaxLength={10}
            saving={saving}
            onBack={() => setShowAdd(false)}
            onSave={handleAddSave}
          />
        )}
      </PopoverContent>
    </Popover>
  );
}
