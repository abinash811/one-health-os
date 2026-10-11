/**
 * PurchaseItemsTable — product search + editable line-items table.
 * Owns product catalog, search state. Parent owns items state.
 * Props:
 *   items          {Array}
 *   onUpdateItem   {(id, field, value) => void}
 *   onRemoveItem   {(id) => void}
 *   onAddItem      {(product) => void}
 *   withGST        {boolean}
 *   searchInputRef {React.Ref}
 *   pharmacyId     {string}  optional — the HQ-buyer picker's target store
 *                            (docs/26_MULTI_CHAIN_SCOPE.md Section 3 #3);
 *                            search must find THAT store's medicines, not
 *                            the caller's currently active one.
 */
import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import AddMedicineModal from '@/components/shared/AddMedicineModal';
import PurchaseItemRow from './PurchaseItemRow';

export default function PurchaseItemsTable({ items, onUpdateItem, onSetItemFields, onRemoveItem, onAddItem, withGST, searchInputRef, pharmacyId = null }) {
  const [searchQuery,       setSearchQuery]       = useState('');
  const [searchResults,     setSearchResults]     = useState([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [showAddMedicine,   setShowAddMedicine]   = useState(false);
  // Captured at click time — the Popover/panel can clear searchQuery before
  // the modal mounts, the same pitfall already fixed once in SupplierDropdown.
  const [newMedicineName,   setNewMedicineName]   = useState('');

  // Server-side search — matches name/SKU/brand/manufacturer/generic name/
  // strength (GET /products already covers all of these), so a distributor
  // bill line can be found by whichever of those the pharmacist recognizes.
  const runSearch = useDebouncedCallback(async (query) => {
    if (!query || query.length < 2) { setSearchResults([]); setShowSearchResults(false); return; }
    try {
      const res = await api.get(apiUrl.products({ search: query, page_size: 10, ...(pharmacyId ? { pharmacy_id: pharmacyId } : {}) }));
      setSearchResults(res.data.data || res.data || []);
      setShowSearchResults(true);
    } catch { /* search failing shouldn't block manual entry */ }
  }, 300);

  const handleSearchChange = (val) => { setSearchQuery(val); runSearch(val); };

  const handleAddProduct = (product) => {
    onAddItem(product);
    setSearchQuery('');
    setSearchResults([]);
    setShowSearchResults(false);
  };

  return (
    <>
      {showAddMedicine && (
        <AddMedicineModal
          initialName={newMedicineName}
          hideOpeningStock
          onClose={() => setShowAddMedicine(false)}
          onSuccess={(product) => { setShowAddMedicine(false); handleAddProduct(product); }}
        />
      )}

      {/* Items Table */}
      <div className="flex-1 overflow-auto px-6 py-4 min-h-0">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-left" style={{ tableLayout: 'fixed' }}>
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[['#','40px'],['Medicine','200px'],['Batch','90px'],['Expiry','70px'],
                  ['Qty','60px'],['Free','60px'],['PTR','70px'],['MRP','70px'],
                  ['GST%','55px'],['LIFA','55px'],['Amount','80px'],['','40px']].map(([h,w]) => (
                  <th key={h} className={`px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${['Qty','Free','PTR','MRP','Amount'].includes(h) ? (h === 'Qty' || h === 'Free' ? 'text-center' : 'text-right') : h === 'GST%' || h === 'LIFA' ? 'text-center' : ''}`} style={{ width: w }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100" data-testid="items-table">
              {/* ── Add-medicine search row (always first) ────────────────── */}
              <tr className="bg-brand-tint border-b border-brand/10">
                <td colSpan="12" className="px-3 py-2.5 relative">
                  <div className="flex items-center gap-2">
                    <Search className="w-4 h-4 text-brand shrink-0" />
                    <input
                      ref={searchInputRef}
                      type="text"
                      placeholder="Search by name, brand, generic, strength or SKU..."
                      value={searchQuery}
                      onChange={(e) => handleSearchChange(e.target.value)}
                      className="flex-1 bg-transparent border-none focus:outline-none text-sm text-gray-700 placeholder-gray-400"
                      data-testid="product-search"
                    />
                  </div>
                  {showSearchResults && (searchResults.length > 0 || searchQuery.trim().length >= 2) && (
                    <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-xl max-h-64 overflow-y-auto">
                      {searchResults.map(product => (
                        <div key={product.id} onClick={() => handleAddProduct(product)}
                          role="button" tabIndex={0}
                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleAddProduct(product); } }}
                          className="px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-inset">
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="text-sm font-semibold text-gray-800">{product.name}</div>
                              <div className="text-xs text-gray-400">
                                SKU: {product.sku} | {product.manufacturer || product.brand || 'N/A'}
                                {product.strength && ` | ${product.strength}`}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-xs text-gray-400">GST {product.gst_percent}%</div>
                            </div>
                          </div>
                        </div>
                      ))}
                      {searchResults.length === 0 && (
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => { setNewMedicineName(searchQuery.trim()); setShowAddMedicine(true); }}
                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setNewMedicineName(searchQuery.trim()); setShowAddMedicine(true); } }}
                          className="px-4 py-3 hover:bg-gray-50 cursor-pointer text-sm text-brand font-medium"
                          data-testid="add-new-medicine-btn"
                        >
                          + Add &quot;{searchQuery.trim()}&quot; as new medicine
                        </div>
                      )}
                    </div>
                  )}
                </td>
              </tr>

              {items.length === 0 ? (
                <tr>
                  <td colSpan="12" className="px-4 py-8 text-center text-gray-400">
                    No items added yet. Search above to get started.
                  </td>
                </tr>
              ) : (
                items.map((item, index) => (
                  <PurchaseItemRow
                    key={item.id} item={item} index={index}
                    onUpdateItem={onUpdateItem} onSetItemFields={onSetItemFields}
                    onRemoveItem={onRemoveItem} withGST={withGST}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
