/**
 * SupplierDropdown — chip button + searchable dropdown for distributor selection.
 * Props:
 *   suppliers         {Array}
 *   value             {object|null}  selected supplier
 *   onChange          {(supplier) => void}
 *   allowCreate       {boolean}  show "+ Add '<search>' as new distributor"
 *                                when nothing matches. Off by default —
 *                                e.g. PurchasesList uses this component as
 *                                a read-only filter, where creating a new
 *                                supplier makes no sense.
 *   onSupplierCreated {(supplier) => void}  called after a successful
 *                                create, so the parent can add it to its
 *                                own suppliers list without a refetch.
 *   pharmacyId        {string}   optional — the HQ-buyer picker's target
 *                                store (docs/26_MULTI_CHAIN_SCOPE.md
 *                                Section 3 #3); a newly-created supplier
 *                                must belong to THAT store, not the
 *                                caller's currently active one.
 */
import React, { useState } from 'react';
import { ChevronDown, Building2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { AppButton, SupplierFormModal } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { formatCurrency } from '@/utils/currency';

export default function SupplierDropdown({ suppliers = [], value, onChange, allowCreate = false, onSupplierCreated, pharmacyId = null }) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [supplierSearch, setSupplierSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  // Captured at the moment "Add new" is clicked — the popover closing (the
  // Dialog opening steals focus) clears supplierSearch via onOpenChange
  // below, so the modal can't read that state directly by the time it renders.
  const [newSupplierName, setNewSupplierName] = useState('');

  const filtered = suppliers.filter(s =>
    s.name.toLowerCase().includes(supplierSearch.toLowerCase())
  );

  const handleCreateSupplier = async (formData) => {
    try {
      const res = await api.post(apiUrl.suppliers(), pharmacyId ? { ...formData, pharmacy_id: pharmacyId } : formData);
      const newSupplier = res.data;
      toast.success('Distributor added');
      onSupplierCreated?.(newSupplier);
      onChange(newSupplier);
      setShowDropdown(false);
      setSupplierSearch('');
      return true;
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add distributor');
      return false;
    }
  };

  return (
    <div className="relative group">
      {/* Uses the shared Popover (portals to document.body) rather than a
          hand-rolled absolute panel — this row scrolls horizontally
          (PurchaseSubbar's overflow-x-auto), and per the CSS spec that
          implicitly clips overflow-y too, so a plain `absolute top-full`
          panel here rendered in the DOM but was invisible. */}
      <Popover
        open={showDropdown}
        onOpenChange={(open) => { setShowDropdown(open); if (!open) setSupplierSearch(''); }}
      >
        <PopoverTrigger asChild>
          <AppButton
            variant="secondary"
            size="sm"
            className="gap-1.5"
            style={{ maxWidth: '220px' }}
            data-testid="supplier-selector"
            title={value ? (value.outstanding > 0
              ? `${value.name} — owes ${formatCurrency(value.outstanding)}`
              : value.name) : 'Select Distributor'}
          >
            <Building2 className="w-4 h-4 text-gray-400 shrink-0" strokeWidth={1.5} />
            <span className={`text-sm font-medium truncate ${value ? 'text-gray-900' : 'text-gray-400'}`}>
              {value?.name || 'Distributor'}
            </span>
            {value?.outstanding > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" aria-hidden="true" />
            )}
            <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" />
          </AppButton>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <input
              type="text"
              placeholder="Search distributors..."
              value={supplierSearch}
              onChange={(e) => setSupplierSearch(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand"
              data-testid="supplier-search-input"
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-xs text-gray-400 text-center">No distributors found</div>
            ) : (
              filtered.map(supplier => (
                <div
                  key={supplier.id}
                  role="option"
                  aria-selected={false}
                  tabIndex={0}
                  onClick={() => { onChange(supplier); setShowDropdown(false); setSupplierSearch(''); }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChange(supplier); setShowDropdown(false); setSupplierSearch(''); } }}
                  className="px-3 py-2 hover:bg-gray-50 cursor-pointer"
                  data-testid={`supplier-option-${supplier.id}`}
                >
                  <div className="text-xs font-semibold text-gray-700">{supplier.name}</div>
                  {supplier.gstin && (
                    <div className="text-[10px] text-gray-500">GSTIN: {supplier.gstin}</div>
                  )}
                  {supplier.outstanding > 0 && (
                    <div className="text-[10px] text-red-600 font-medium">
                      Owes {formatCurrency(supplier.outstanding)}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {allowCreate && supplierSearch.trim() && (
            <div className="p-1.5 border-t border-gray-100">
              <AppButton
                variant="ghost"
                size="sm"
                icon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => { setNewSupplierName(supplierSearch.trim()); setShowCreateModal(true); }}
                className="w-full justify-start text-brand"
                data-testid="add-new-supplier-btn"
              >
                Add "{supplierSearch.trim()}" as new distributor
              </AppButton>
            </div>
          )}
        </PopoverContent>
      </Popover>

      {/* Tooltip for long names */}
      {value && value.name.length > 20 && (
        <div className="absolute z-50 bottom-full left-0 mb-1 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
          {value.name}
        </div>
      )}

      {showCreateModal && (
        <SupplierFormModal
          open
          editingSupplier={null}
          initialName={newSupplierName}
          onClose={() => setShowCreateModal(false)}
          onSave={handleCreateSupplier}
        />
      )}
    </div>
  );
}
