/**
 * InventorySearch — orchestrator
 * Route: /inventory
 */
import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Upload } from 'lucide-react';
import { TableSkeleton, PageHeader, PageTabs, AppButton } from '@/components/shared';
import ExcelBulkUploadWizard from '@/components/ExcelBulkUploadWizard';
import { INVENTORY_TABS, inventoryTabRoute } from '../inventoryTabs';

import { useInventorySearch }  from './hooks/useInventorySearch';
import InventorySearchBar      from './components/InventorySearchBar';
import InventoryEmptyState     from './components/InventoryEmptyState';
import InventoryTable          from './components/InventoryTable';
import BulkUpdateModal         from './components/BulkUpdateModal';
import TransferStockModal      from './components/TransferStockModal';
import { AddMedicineModal }    from '@/components/shared';
import AdjustStockModal        from './components/AdjustStockModal';
import EditProductModal        from './components/EditProductModal';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

export default function InventorySearch() {
  const navigate       = useNavigate();
  const searchInputRef = useRef(null);

  const {
    searchQuery, setSearchQuery,
    activeFilters, applyFilters, removeFilter, clearAllFilters,
    filterOptions,
    inventory, loading, hasActiveQuery,
    currentPage, totalPages, totalItems, setPage,
    refetch,
  } = useInventorySearch();

  // True only for a genuinely empty pharmacy (no medicines added yet) —
  // otherwise the default view shows the 10 most recently added.
  const isEmptyPharmacy = !hasActiveQuery && totalItems === 0;

  // ── Selection state ───────────────────────────────────────────────────────
  const [selectedItems, setSelectedItems] = useState(new Set());

  const handleSelectItem = (sku, checked) => {
    setSelectedItems(prev => { const s = new Set(prev); checked ? s.add(sku) : s.delete(sku); return s; });
  };
  const handleSelectAll = (checked) => {
    setSelectedItems(checked ? new Set(inventory.map(i => i.product.sku)) : new Set());
  };

  // ── Modal state ───────────────────────────────────────────────────────────
  const [showBulkModal,      setShowBulkModal]      = useState(false);
  const [showTransferModal,  setShowTransferModal]  = useState(false);
  const [showAddModal,       setShowAddModal]       = useState(false);
  const [showExcelWizard,    setShowExcelWizard]    = useState(false);
  const [adjustProduct,      setAdjustProduct]      = useState(null);
  const [editProduct,        setEditProduct]        = useState(null);

  // ── Bulk update ───────────────────────────────────────────────────────────
  const handleBulkConfirm = async (field, value) => {
    try {
      await api.post(apiUrl.productsBulkUpdate(), { skus: Array.from(selectedItems), field, value });
      toast.success(`Updated ${selectedItems.size} products successfully`);
      setShowBulkModal(false);
      setSelectedItems(new Set());
      refetch();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bulk update failed');
    }
  };

  const hasActiveFilters = Object.keys(activeFilters).length > 0;

  return (
    <div className="px-8 py-6 min-h-screen bg-page">
      <PageHeader
        title="Inventory"
        actions={
          <>
            <AppButton
              variant="secondary"
              icon={<Upload className="w-4 h-4" />}
              onClick={() => setShowExcelWizard(true)}
              data-testid="bulk-upload-btn"
            >
              Bulk Upload
            </AppButton>
            <AppButton
              icon={<Plus className="w-4 h-4" />}
              onClick={() => setShowAddModal(true)}
              data-testid="add-medicine-btn"
            >
              Add Medicine
            </AppButton>
          </>
        }
      />
      <PageTabs
        tabs={INVENTORY_TABS}
        activeTab="products"
        onChange={(key) => navigate(inventoryTabRoute(key))}
      />

      <div>
        <InventorySearchBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          filterOptions={filterOptions}
          activeFilters={activeFilters}
          onApplyFilters={applyFilters}
          onRemoveFilter={removeFilter}
          onClearAll={clearAllFilters}
          searchInputRef={searchInputRef}
        />

        {/* Results area */}
        {loading ? (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <TableSkeleton rows={8} columns={6} />
          </div>
        ) : isEmptyPharmacy ? (
          <InventoryEmptyState onAddMedicine={() => setShowAddModal(true)} />
        ) : inventory.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center text-gray-500">
            No medicines found for your search.{hasActiveFilters && ' Try clearing some filters.'}
          </div>
        ) : (
          <InventoryTable
            inventory={inventory}
            selectedItems={selectedItems}
            onSelectItem={handleSelectItem}
            onSelectAll={handleSelectAll}
            onRowClick={(item) => navigate(`/inventory/product/${item.product.sku}`)}
            onEdit={(item, e) => { e.stopPropagation(); setEditProduct(item.product); }}
            onAdjust={(item, e) => { e.stopPropagation(); setAdjustProduct(item); }}
            onBulkUpdate={() => setShowBulkModal(true)}
            onTransferStock={() => setShowTransferModal(true)}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalItems}
            onPageChange={setPage}
          />
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────────────────────── */}
      {showBulkModal && (
        <BulkUpdateModal
          selectedCount={selectedItems.size}
          filterOptions={filterOptions}
          onConfirm={handleBulkConfirm}
          onClose={() => setShowBulkModal(false)}
        />
      )}

      {showTransferModal && (
        <TransferStockModal
          selectedSkus={Array.from(selectedItems)}
          onClose={() => setShowTransferModal(false)}
          onSuccess={() => { setShowTransferModal(false); setSelectedItems(new Set()); refetch(); }}
        />
      )}

      {showAddModal && (
        <AddMedicineModal onClose={() => setShowAddModal(false)} onSuccess={() => { setShowAddModal(false); refetch(); }} />
      )}

      {editProduct && (
        <EditProductModal
          product={editProduct}
          onClose={() => setEditProduct(null)}
          onSuccess={() => { setEditProduct(null); refetch(); }}
        />
      )}

      {adjustProduct && (
        <AdjustStockModal
          product={adjustProduct}
          onClose={() => setAdjustProduct(null)}
          onSuccess={() => { setAdjustProduct(null); refetch(); }}
        />
      )}

      <ExcelBulkUploadWizard
        isOpen={showExcelWizard}
        onClose={() => setShowExcelWizard(false)}
        onImportComplete={() => { setShowExcelWizard(false); refetch(); }}
      />
    </div>
  );
}
