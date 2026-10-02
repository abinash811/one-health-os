// @ts-nocheck -- plain-JS constants/component extracted from AuditLog.jsx
// to keep that file under the 300-line limit; no real typing needed.
import React from 'react';

export function ActionBadge({ action }) {
  const styles = {
    create: 'bg-green-50 text-green-700',
    update: 'bg-blue-50 text-blue-700',
    delete: 'bg-red-50 text-red-700',
    login:  'bg-purple-50 text-purple-700',
    login_failed: 'bg-red-50 text-red-700',
    login_blocked: 'bg-red-50 text-red-700',
    logout: 'bg-gray-100 text-gray-600',
    bill_finalized:    'bg-green-50 text-green-700',
    bill_parked:       'bg-amber-50 text-amber-700',
    stock_adjusted:    'bg-orange-50 text-orange-700',
    payment_recorded:  'bg-green-50 text-green-700',
    return_processed:  'bg-pink-50 text-pink-700',
    issue:             'bg-green-50 text-green-700',
    cancel:            'bg-red-50 text-red-700',
    status_change:     'bg-blue-50 text-blue-700',
  };
  const label = action?.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Unknown';
  const cls   = styles[action?.toLowerCase()] || 'bg-gray-100 text-gray-600';
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

// Entity type display labels
export const ENTITY_LABELS = {
  bill:             'Bill',
  purchase:         'Purchase',
  purchase_return:  'Purchase Return',
  sales_return:     'Sales Return',
  product:          'Product',
  stock_batch:      'Stock Batch',
  stock_movement:   'Stock Adjustment',
  user:             'User',
  role:             'Role',
  supplier:         'Supplier',
  customer:         'Customer',
  settings:         'Settings',
  auth:             'Login',
  data_export:      'Data Export',
  emr_patient:      'Patient (EMR)',
  emr_appointment:  'Appointment (EMR)',
  emr_schedule:     'Doctor Schedule (EMR)',
  emr_prescription: 'Prescription (EMR)',
  emr_settings:     'Clinic Settings (EMR)',
  emr_doctor_profile: 'Doctor Profile (EMR)',
};

export const ENTITY_TYPES = [
  { key: 'all',             label: 'All'             },
  { key: 'bill',            label: 'Bill'            },
  { key: 'purchase',        label: 'Purchase'        },
  { key: 'purchase_return', label: 'Purchase Return' },
  { key: 'sales_return',    label: 'Sales Return'    },
  { key: 'product',         label: 'Product'         },
  { key: 'stock_batch',     label: 'Stock Batch'     },
  { key: 'user',            label: 'User'            },
  { key: 'settings',        label: 'Settings'        },
  { key: 'auth',            label: 'Login'           },
  { key: 'data_export',     label: 'Data Export'     },
  { key: 'emr_patient',      label: 'Patient (EMR)'      },
  { key: 'emr_appointment',  label: 'Appointment (EMR)'  },
  { key: 'emr_prescription', label: 'Prescription (EMR)' },
  { key: 'emr_settings',     label: 'Clinic Settings (EMR)' },
];
