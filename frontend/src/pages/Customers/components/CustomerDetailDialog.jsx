/**
 * CustomerDetailDialog — customer info + purchase stats.
 * Fetches stats and recent bills on open.
 * Props:
 *   open      {boolean}
 *   customer  {object|null}
 *   onClose   {() => void}
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { User } from 'lucide-react';
import { AppButton } from '@/components/shared';
import { formatCurrency } from '@/utils/currency';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';

function CustomerTypeBadge({ type }) {
  const safeType = type && typeof type === 'string' && type.trim() ? type.toLowerCase() : 'regular';
  const styles = { regular: 'bg-blue-50 text-blue-700', wholesale: 'bg-purple-50 text-purple-700', institution: 'bg-green-50 text-green-700' };
  return <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[safeType] || styles.regular}`}>{safeType.charAt(0).toUpperCase() + safeType.slice(1)}</span>;
}

export default function CustomerDetailDialog({ open, customer, onClose }) {
  const navigate = useNavigate();
  const [stats,     setStats]     = useState(null);
  const [purchases, setPurchases] = useState([]);

  useEffect(() => {
    if (!open || !customer) return;
    Promise.all([
      api.get(apiUrl.customerStats(customer.id)),
      api.get(apiUrl.bills({ customer_name: customer.name, limit: 10 })),
    ]).then(([sRes, bRes]) => {
      setStats(sRes.data);
      setPurchases(bRes.data || []);
    }).catch(() => {});
  }, [open, customer]);

  if (!customer) return null;

  const totalSpent = stats?.total_value
    ?? purchases.reduce((s, p) => s + (p.total_amount || 0), 0);
  const lastPurchase = stats?.last_purchase
    ?? (purchases[0] ? new Date(purchases[0].created_at).toLocaleDateString() : 'N/A');

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="w-5 h-5" />
            Customer Details
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Info grid */}
          <div className="grid grid-cols-2 gap-4">
            <div><span className="block text-xs text-gray-500 uppercase">Name</span><p className="font-medium">{customer.name}</p></div>
            <div><span className="block text-xs text-gray-500 uppercase">Type</span><p><CustomerTypeBadge type={customer.customer_type} /></p></div>
            {customer.phone && <div><span className="block text-xs text-gray-500 uppercase">Phone</span><p>{customer.phone}</p></div>}
            {customer.email && <div><span className="block text-xs text-gray-500 uppercase">Email</span><p>{customer.email}</p></div>}
            {customer.address && (
              <div className="col-span-2">
                <span className="block text-xs text-gray-500 uppercase">Address</span>
                <p className="text-sm">{customer.address}</p>
              </div>
            )}
            {customer.notes && (
              <div className="col-span-2">
                <span className="block text-xs text-gray-500 uppercase">Notes</span>
                <p className="text-sm whitespace-pre-wrap">{customer.notes}</p>
              </div>
            )}
          </div>

          {/* Stats */}
          <div className="border-t pt-4">
            <h3 className="font-semibold text-gray-800 mb-3">Purchase Summary</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-blue-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-blue-600">{stats?.total_purchases ?? purchases.length}</p>
                <p className="text-xs text-gray-600">Total Bills</p>
              </div>
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-green-600">₹{totalSpent.toLocaleString()}</p>
                <p className="text-xs text-gray-600">Total Spent</p>
              </div>
              <div className="bg-purple-50 rounded-lg p-3 text-center">
                <p className="text-sm font-bold text-purple-600">{lastPurchase}</p>
                <p className="text-xs text-gray-600">Last Purchase</p>
              </div>
            </div>
          </div>

          {/* Recent purchases */}
          <div className="border-t pt-4">
            <h3 className="font-semibold text-gray-800 mb-3">Recent Purchases</h3>
            {purchases.length > 0 ? (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {purchases.slice(0, 5).map(p => (
                  <div key={p.id} onClick={() => navigate(`/billing/${p.id}`)}
                    role="button" tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/billing/${p.id}`); } }}
                    className="flex justify-between items-center p-3 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
                    <div>
                      <p className="font-medium text-blue-600">{p.bill_number}</p>
                      <p className="text-xs text-gray-500">{new Date(p.created_at).toLocaleDateString()}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{formatCurrency(p.total_amount)}</p>
                      <p className="text-xs text-gray-500">{p.items?.length || 0} items</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-gray-400 py-4">No purchases yet</p>
            )}
          </div>

          <DialogFooter>
            <AppButton variant="outline" onClick={onClose}>Close</AppButton>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
