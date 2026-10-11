/**
 * InventoryTab — inventory management settings.
 * Props:
 *   inventory      {object}  settings.inventory slice
 *   onUpdate       {(key, value) => void}
 */
import React from 'react';

export default function InventoryTab({ inventory, onUpdate }) {
  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold mb-4">Inventory Management Rules</h3>

      <div className="space-y-4">
        <div>
          <label htmlFor="fld-inventorytabjsx-16" className="block text-sm font-medium text-gray-700 mb-2">
            Near Expiry Alert (Days before expiry)
          </label>
          <input id="fld-inventorytabjsx-16"
            type="number"
            value={inventory.near_expiry_days}
            onChange={(e) => onUpdate('near_expiry_days', parseInt(e.target.value))}
            className="w-full md:w-64 px-3 py-2 border border-gray-300 rounded"
            min="1"
            max="365"
          />
          <p className="text-xs text-gray-500 mt-1">
            Products expiring within this period will be flagged as "Near Expiry"
          </p>
        </div>

        {[
          { id: 'block_expired_stock',      key: 'block_expired_stock',      label: 'Block expired stock from billing' },
          { id: 'allow_near_expiry',        key: 'allow_near_expiry_sale',   label: 'Allow selling near-expiry products (with warning)' },
          { id: 'low_stock_alert_enabled',  key: 'low_stock_alert_enabled',  label: 'Enable low stock alerts on dashboard' },
        ].map(({ id, key, label }) => (
          <div key={id} className="flex items-center gap-3">
            <input
              type="checkbox"
              id={id}
              checked={inventory[key]}
              onChange={(e) => onUpdate(key, e.target.checked)}
              className="w-4 h-4 text-blue-600"
            />
            <label htmlFor={id} className="text-sm font-medium text-gray-700">{label}</label>
          </div>
        ))}
      </div>
    </div>
  );
}
