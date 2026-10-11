import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PurchaseItemsTable from '../PurchaseItemsTable';
import api from '@/lib/axios';

jest.mock('@/lib/axios', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

// The real modal is a full multi-field form (category, dosage form, GST%,
// opening stock...) already covered by its own tests elsewhere — here we
// only need to verify PurchaseItemsTable wires initialName in and the
// created product back out.
jest.mock('@/components/shared/AddMedicineModal', () => ({
  __esModule: true,
  default: ({ initialName, hideOpeningStock, onSuccess }:
    { initialName?: string; hideOpeningStock?: boolean; onSuccess: (p: unknown) => void }) => (
    <div data-testid="mock-add-medicine-modal">
      prefilled: {initialName}
      hideOpeningStock: {String(hideOpeningStock)}
      <div role="button" tabIndex={0} onKeyDown={() => undefined}
        onClick={() => onSuccess({ id: 'new-1', sku: 'SKU-NEW', name: initialName, gst_percent: 5 })}>
        mock-create-medicine
      </div>
    </div>
  ),
}));

const PRODUCT = {
  id: 'p1', sku: 'SKU-1', name: 'Paracetamol 500mg', manufacturer: 'Cipla',
  strength: '500mg', gst_percent: 12,
};

describe('PurchaseItemsTable — search, add-new-medicine', () => {
  beforeEach(() => jest.clearAllMocks());

  const baseProps = {
    items: [], onUpdateItem: jest.fn(), onSetItemFields: jest.fn(), onRemoveItem: jest.fn(), onAddItem: jest.fn(),
    withGST: true, searchInputRef: { current: null },
  };

  it('searches the server (not a preloaded catalog) and shows brand/strength in results', async () => {
    mockedGet.mockResolvedValueOnce({ data: [PRODUCT] });
    render(<PurchaseItemsTable {...baseProps} />);
    await userEvent.type(screen.getByTestId('product-search'), 'Para');

    await waitFor(() => expect(mockedGet).toHaveBeenCalledWith(expect.stringContaining('search=Para')));
    expect(await screen.findByText('Paracetamol 500mg')).toBeInTheDocument();
    expect(screen.getByText(/SKU: SKU-1 \| Cipla \| 500mg/)).toBeInTheDocument();
  });

  it('adds the clicked search result and clears the search box', async () => {
    mockedGet.mockResolvedValueOnce({ data: [PRODUCT] });
    const onAddItem = jest.fn();
    render(<PurchaseItemsTable {...baseProps} onAddItem={onAddItem} />);
    await userEvent.type(screen.getByTestId('product-search'), 'Para');
    fireEvent.click(await screen.findByText('Paracetamol 500mg'));

    expect(onAddItem).toHaveBeenCalledWith(PRODUCT);
    expect(screen.getByTestId('product-search')).toHaveValue('');
  });

  it('offers "add as new medicine" when the search finds nothing, prefilled with the typed name and opening stock hidden', async () => {
    mockedGet.mockResolvedValueOnce({ data: [] });
    render(<PurchaseItemsTable {...baseProps} />);
    await userEvent.type(screen.getByTestId('product-search'), 'Brand New Tablet');

    fireEvent.click(await screen.findByTestId('add-new-medicine-btn'));
    expect(await screen.findByText(/prefilled: Brand New Tablet/)).toBeInTheDocument();
    // Opening Stock would post a batch outside the purchase — the purchase's
    // own line-item batch entry is the single source of truth here instead.
    expect(screen.getByText(/hideOpeningStock: true/)).toBeInTheDocument();
  });

  it('adds the newly created medicine to the purchase and closes the modal', async () => {
    mockedGet.mockResolvedValueOnce({ data: [] });
    const onAddItem = jest.fn();
    render(<PurchaseItemsTable {...baseProps} onAddItem={onAddItem} />);
    await userEvent.type(screen.getByTestId('product-search'), 'Brand New Tablet');
    fireEvent.click(await screen.findByTestId('add-new-medicine-btn'));

    fireEvent.click(await screen.findByText('mock-create-medicine'));

    expect(onAddItem).toHaveBeenCalledWith(
      expect.objectContaining({ sku: 'SKU-NEW', name: 'Brand New Tablet' }),
    );
    expect(screen.queryByTestId('mock-add-medicine-modal')).not.toBeInTheDocument();
  });

  it('warns on a line item where PTR (cost) is higher than MRP — selling it would lose money', () => {
    const items = [{
      id: 'i1', product_sku: 'SKU-1', product_name: 'Combiflam', manufacturer: '', pack_size: '',
      batch_no: '', expiry_mmyy: '', qty_units: 1, free_qty_units: 0,
      ptr_per_unit: 300, mrp_per_unit: 100, gst_percent: 5, batch_priority: 'LIFA',
    }];
    render(<PurchaseItemsTable {...baseProps} items={items} />);
    expect(screen.getByTestId('ptr-0')).toHaveClass('border-amber-400');
    expect(screen.getByTestId('mrp-0')).toHaveClass('border-amber-400');
  });

  it('does not warn when PTR is below MRP', () => {
    const items = [{
      id: 'i1', product_sku: 'SKU-1', product_name: 'Combiflam', manufacturer: '', pack_size: '',
      batch_no: '', expiry_mmyy: '', qty_units: 1, free_qty_units: 0,
      ptr_per_unit: 50, mrp_per_unit: 100, gst_percent: 5, batch_priority: 'LIFA',
    }];
    render(<PurchaseItemsTable {...baseProps} items={items} />);
    expect(screen.getByTestId('ptr-0')).not.toHaveClass('border-amber-400');
    expect(screen.getByTestId('mrp-0')).not.toHaveClass('border-amber-400');
  });
});

describe('PurchaseItemsTable — Pack/Unit entry (Sep 24, 2026)', () => {
  beforeEach(() => jest.clearAllMocks());

  const baseProps = {
    items: [], onUpdateItem: jest.fn(), onSetItemFields: jest.fn(), onRemoveItem: jest.fn(), onAddItem: jest.fn(),
    withGST: true, searchInputRef: { current: null },
  };

  const packItem = {
    id: 'i1', product_sku: 'SKU-1', product_name: 'Paracetamol', manufacturer: '', pack_size: '10 Tablets',
    units_per_pack: 10, qty_mode: 'pack',
    batch_no: '', expiry_mmyy: '', qty_units: 10, free_qty_units: 0,
    ptr_per_unit: 30, mrp_per_unit: 50, gst_percent: 5, batch_priority: 'LIFA',
  };

  it('shows the Pack/Unit toggle for a product with a real pack size', () => {
    render(<PurchaseItemsTable {...baseProps} items={[packItem]} />);
    expect(screen.getByRole('button', { name: 'Pack' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unit' })).toBeInTheDocument();
  });

  it('hides the toggle for a product with no pack (units_per_pack=1)', () => {
    const singleUnitItem = { ...packItem, units_per_pack: 1, qty_mode: 'unit' };
    render(<PurchaseItemsTable {...baseProps} items={[singleUnitItem]} />);
    expect(screen.queryByRole('button', { name: 'Pack' })).not.toBeInTheDocument();
  });

  it('shows the real per-unit qty/cost/MRP under each field in Pack mode', () => {
    render(<PurchaseItemsTable {...baseProps} items={[packItem]} />);
    // 10 strips x 10 tablets/strip = 100 tablets; ₹30/strip = ₹3.00/tablet; ₹50/strip = ₹5.00/tablet
    expect(screen.getByTestId('qty-real-0')).toHaveTextContent('= 100 units');
    expect(screen.getByTestId('ptr-real-0')).toHaveTextContent('/unit');
    expect(screen.getByTestId('mrp-real-0')).toHaveTextContent('/unit');
  });

  it('hides the real-value subtext in Unit mode — the typed value is already real', () => {
    const unitItem = { ...packItem, qty_mode: 'unit' };
    render(<PurchaseItemsTable {...baseProps} items={[unitItem]} />);
    expect(screen.queryByTestId('qty-real-0')).not.toBeInTheDocument();
  });

  it('clicking Unit converts the pack-mode line to its real per-unit values', async () => {
    const onSetItemFields = jest.fn();
    render(<PurchaseItemsTable {...baseProps} items={[packItem]} onSetItemFields={onSetItemFields} />);
    await userEvent.click(screen.getByRole('button', { name: 'Unit' }));
    expect(onSetItemFields).toHaveBeenCalledWith('i1', expect.objectContaining({
      qty_mode: 'unit', qty_units: 100, ptr_per_unit: 3, mrp_per_unit: 5,
    }));
  });
});

describe('PurchaseItemsTable — short/excess supply (Sep 25, 2026)', () => {
  beforeEach(() => jest.clearAllMocks());

  const baseProps = {
    items: [], onUpdateItem: jest.fn(), onSetItemFields: jest.fn(), onRemoveItem: jest.fn(), onAddItem: jest.fn(),
    withGST: true, searchInputRef: { current: null },
  };

  const item = {
    id: 'i1', product_sku: 'SKU-1', product_name: 'Paracetamol', manufacturer: '', pack_size: '',
    units_per_pack: 1, qty_mode: 'unit',
    batch_no: '', expiry_mmyy: '', qty_units: 100, free_qty_units: 0,
    ptr_per_unit: 10, mrp_per_unit: 20, gst_percent: 5, batch_priority: 'LIFA',
  };

  it('shows a reveal link and no received-qty input by default (received_qty_units unset)', () => {
    render(<PurchaseItemsTable {...baseProps} items={[item]} />);
    expect(screen.getByTestId('reveal-received-0')).toBeInTheDocument();
    expect(screen.queryByTestId('received-0')).not.toBeInTheDocument();
  });

  it('clicking the reveal link seeds the received field with the current qty', async () => {
    const onUpdateItem = jest.fn();
    render(<PurchaseItemsTable {...baseProps} items={[item]} onUpdateItem={onUpdateItem} />);
    await userEvent.click(screen.getByTestId('reveal-received-0'));
    expect(onUpdateItem).toHaveBeenCalledWith('i1', 'received_qty_units', 100);
  });

  it('shows the received-qty input, not the reveal link, once a value is set', () => {
    const shortItem = { ...item, received_qty_units: 95 };
    render(<PurchaseItemsTable {...baseProps} items={[shortItem]} />);
    expect(screen.getByTestId('received-0')).toHaveValue(95);
    expect(screen.queryByTestId('reveal-received-0')).not.toBeInTheDocument();
  });

  it('shows "Short by N" when received is less than ordered', () => {
    const shortItem = { ...item, received_qty_units: 95 };
    render(<PurchaseItemsTable {...baseProps} items={[shortItem]} />);
    expect(screen.getByTestId('received-variance-0')).toHaveTextContent('Short by 5');
  });

  it('shows "Excess by N" when received is more than ordered', () => {
    const excessItem = { ...item, received_qty_units: 105 };
    render(<PurchaseItemsTable {...baseProps} items={[excessItem]} />);
    expect(screen.getByTestId('received-variance-0')).toHaveTextContent('Excess by 5');
  });

  it('shows no variance text when received equals ordered', () => {
    const evenItem = { ...item, received_qty_units: 100 };
    render(<PurchaseItemsTable {...baseProps} items={[evenItem]} />);
    expect(screen.queryByTestId('received-variance-0')).not.toBeInTheDocument();
  });

  it('clicking the clear button resets received_qty_units to null', async () => {
    const onUpdateItem = jest.fn();
    const shortItem = { ...item, received_qty_units: 95 };
    render(<PurchaseItemsTable {...baseProps} items={[shortItem]} onUpdateItem={onUpdateItem} />);
    await userEvent.click(screen.getByTestId('clear-received-0'));
    expect(onUpdateItem).toHaveBeenCalledWith('i1', 'received_qty_units', null);
  });
});

describe('PurchaseItemsTable — price-change warning (Sep 25, 2026)', () => {
  beforeEach(() => jest.clearAllMocks());

  const baseProps = {
    items: [], onUpdateItem: jest.fn(), onSetItemFields: jest.fn(), onRemoveItem: jest.fn(), onAddItem: jest.fn(),
    withGST: true, searchInputRef: { current: null },
  };

  const item = {
    id: 'i1', product_sku: 'SKU-1', product_name: 'Paracetamol', manufacturer: '', pack_size: '',
    units_per_pack: 1, qty_mode: 'unit',
    batch_no: '', expiry_mmyy: '', qty_units: 100, free_qty_units: 0,
    ptr_per_unit: 10, mrp_per_unit: 20, gst_percent: 5, batch_priority: 'LIFA',
  };

  it('shows no warning while last price is still loading (null)', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: null, last_mrp_per_unit: null }]} />);
    expect(screen.queryByTestId('ptr-increased-0')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mrp-changed-0')).not.toBeInTheDocument();
  });

  it('warns when cost is higher than the last recorded purchase', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: 8, last_mrp_per_unit: 20 }]} />);
    expect(screen.getByTestId('ptr-increased-0')).toHaveTextContent('Was ₹8.00 last time');
  });

  it('does not warn when cost is the same as last time', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: 10, last_mrp_per_unit: 20 }]} />);
    expect(screen.queryByTestId('ptr-increased-0')).not.toBeInTheDocument();
  });

  it('does not warn when cost is lower than last time', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: 12, last_mrp_per_unit: 20 }]} />);
    expect(screen.queryByTestId('ptr-increased-0')).not.toBeInTheDocument();
  });

  it('warns when MRP differs from last time, either direction', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: 10, last_mrp_per_unit: 18 }]} />);
    expect(screen.getByTestId('mrp-changed-0')).toHaveTextContent('MRP was ₹18.00');
  });

  it('does not warn when MRP is unchanged from last time', () => {
    render(<PurchaseItemsTable {...baseProps} items={[{ ...item, last_cost_per_unit: 10, last_mrp_per_unit: 20 }]} />);
    expect(screen.queryByTestId('mrp-changed-0')).not.toBeInTheDocument();
  });
});
