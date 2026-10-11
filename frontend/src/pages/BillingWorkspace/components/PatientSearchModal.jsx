/**
 * PatientSearchModal
 *
 * Typeahead patient lookup. Owns its own search state — the parent only
 * needs to handle what happens after a patient is selected.
 *
 * Props:
 *   open      {boolean}              — whether the modal is visible
 *   onClose   {() => void}           — close without selecting
 *   onSelect  {(patient | 'counter') => void}
 *               'counter' → Counter / Walk-in Sale
 *               patient   → { id, name, phone, mobile, age, gender }
 */

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

export default function PatientSearchModal({ open, onClose, onSelect }) {
  const [query,   setQuery]   = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  // Clear state when modal is opened fresh
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
    }
  }, [open]);

  const searchPatients = useDebouncedCallback(async (q) => {
    if (q.length < 1) { setResults([]); return; }
    setLoading(true);
    try {
      const res = await api.get(apiUrl.patients({ search: q, page_size: 20 }));
      setResults(res.data.data || res.data || []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, 300);

  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    searchPatients(val);
  };

  const handleSelect = (patient) => {
    onSelect(patient);
    onClose();
  };

  const activateOnKey = (handler) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="max-w-md p-0 gap-0 overflow-hidden max-h-[80vh] flex flex-col">
        <DialogHeader className="px-4 py-3 border-b border-gray-200 shrink-0">
          <DialogTitle className="text-base">Select Patient</DialogTitle>
        </DialogHeader>

        {/* Search input */}
        <div className="px-4 py-3 border-b border-gray-200 shrink-0">
          <div className="relative">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg">
              search
            </span>
            <input
              type="text"
              placeholder="Search by name or phone…"
              value={query}
              onChange={handleQueryChange}
              // eslint-disable-next-line jsx-a11y/no-autofocus -- the search box is the only thing in this modal; focus belongs there
              autoFocus
              className="w-full pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              data-testid="patient-search-input"
            />
          </div>
        </div>

        {/* Patient list */}
        <div className="flex-1 overflow-y-auto">

          {/* Counter Sale — always first */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => handleSelect('counter')}
            onKeyDown={activateOnKey(() => handleSelect('counter'))}
            className="w-full px-4 py-3 text-left hover:bg-brand-subtle flex items-center gap-3 border-b border-gray-100 cursor-pointer"
            data-testid="counter-sale-option"
          >
            <div className="w-10 h-10 rounded-full bg-brand/20 flex items-center justify-center shrink-0">
              <span className="material-symbols-outlined text-brand text-lg">storefront</span>
            </div>
            <div>
              <div className="font-semibold text-gray-900 text-sm">Counter Sale</div>
              <div className="text-xs text-gray-400">Walk-in customer without registration</div>
            </div>
          </div>

          {/* Loading */}
          {loading && (
            <div className="px-4 py-6 text-center text-gray-400">
              <span className="material-symbols-outlined animate-spin text-2xl">progress_activity</span>
              <p className="mt-2 text-sm">Searching patients…</p>
            </div>
          )}

          {/* Results */}
          {!loading && results.map((patient) => (
            <div
              key={patient.id}
              role="button"
              tabIndex={0}
              onClick={() => handleSelect(patient)}
              onKeyDown={activateOnKey(() => handleSelect(patient))}
              className="w-full px-4 py-3 text-left hover:bg-gray-50 flex items-center gap-3 border-b border-gray-100 cursor-pointer"
              data-testid={`patient-${patient.id}`}
            >
              <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-gray-400 text-lg">person</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-gray-900 text-sm truncate" title={patient.name}>{patient.name}</div>
                <div className="text-xs text-gray-400">
                  {patient.phone || patient.mobile || 'No phone'}
                  {patient.age    && ` · ${patient.age} yrs`}
                  {patient.gender && ` · ${patient.gender}`}
                </div>
              </div>
            </div>
          ))}

          {/* Empty state */}
          {!loading && query.length > 0 && results.length === 0 && (
            <div className="px-4 py-6 text-center text-gray-400">
              <span className="material-symbols-outlined text-3xl mb-2">person_search</span>
              <p className="text-sm">No patients found for &ldquo;{query}&rdquo;</p>
              <p className="text-xs mt-1">Select &ldquo;Counter Sale&rdquo; for walk-in customers</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
