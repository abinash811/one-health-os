import React, { useState, useEffect } from 'react';
import { User, Stethoscope, Plus, FileSpreadsheet } from 'lucide-react';
import { SearchInput, DeleteConfirmDialog, PaginationBar, PageTabs, PageHeader, AppButton } from '@/components/shared';
import usePagination from '@/hooks/usePagination';
import { toast } from 'sonner';
import { exportCustomersToExcel, exportDoctorsToExcel } from '@/utils/excelExport';
import { useDebounce } from '@/hooks/useDebounce';

import { useCustomers }          from './hooks/useCustomers';
import CustomersTable            from './components/CustomersTable';
import DoctorsTable              from './components/DoctorsTable';
import CustomerFormDialog        from './components/CustomerFormDialog';
import DoctorFormDialog          from './components/DoctorFormDialog';
import CustomerDetailDialog      from './components/CustomerDetailDialog';

const CUSTOMER_TABS = [
  { key: 'customers', label: 'Customers', icon: User        },
  { key: 'doctors',   label: 'Doctors',   icon: Stethoscope },
];

export default function Customers() {
  const { customers, doctors, loading, fetchData, saveCustomer, deleteCustomer, saveDoctor, deleteDoctor } = useCustomers();

  const [activeSection, setActiveSection] = useState('customers');

  const [searchQuery,    setSearchQuery]    = useState('');
  const debouncedSearch = useDebounce(searchQuery, 300);

  const [showCustomerDialog,  setShowCustomerDialog]  = useState(false);
  const [editingCustomer,     setEditingCustomer]     = useState(null);
  const [showDoctorDialog,    setShowDoctorDialog]    = useState(false);
  const [editingDoctor,       setEditingDoctor]       = useState(null);
  const [detailCustomer,      setDetailCustomer]      = useState(null);
  const [delCustomer, setDelCustomer] = useState({ open: false, item: null, loading: false });
  const [delDoctor,   setDelDoctor]   = useState({ open: false, item: null, loading: false });

  const custPg = usePagination({ pageSize: 20 });
  const docPg  = usePagination({ pageSize: 20 });

  useEffect(() => { fetchData(); }, []); // eslint-disable-line
  // eslint-disable-next-line react-hooks/set-state-in-effect -- resets form/list state when the input changes; moving it out of the effect is a separate refactor
  useEffect(() => { setSearchQuery(''); }, [activeSection]);

  const q = debouncedSearch.toLowerCase();
  const filteredCustomers = customers.filter(c =>
    c.name?.toLowerCase().includes(q) || c.phone?.includes(q) || c.email?.toLowerCase().includes(q)
  );
  const filteredDoctors = doctors.filter(d =>
    d.name?.toLowerCase().includes(q) || d.contact?.includes(q) || d.specialization?.toLowerCase().includes(q)
  );

  useEffect(() => {
    custPg.resetPage(); custPg.setTotal(filteredCustomers.length);
  }, [debouncedSearch, customers.length]); // eslint-disable-line

  useEffect(() => {
    docPg.resetPage(); docPg.setTotal(filteredDoctors.length);
  }, [debouncedSearch, doctors.length]); // eslint-disable-line

  const pageCustomers = custPg.slice(filteredCustomers);
  const pageDoctors   = docPg.slice(filteredDoctors);

  const handleEditCustomer = (c) => { setEditingCustomer(c); setShowCustomerDialog(true); };
  const handleAddCustomer  = ()  => { setEditingCustomer(null); setShowCustomerDialog(true); };
  const handleCloseCustomerDialog = () => { setShowCustomerDialog(false); setEditingCustomer(null); };

  const handleEditDoctor   = (d) => { setEditingDoctor(d); setShowDoctorDialog(true); };
  const handleAddDoctor    = ()  => { setEditingDoctor(null); setShowDoctorDialog(true); };
  const handleCloseDoctorDialog = () => { setShowDoctorDialog(false); setEditingDoctor(null); };

  const confirmDeleteCustomer = async () => {
    setDelCustomer(p => ({ ...p, loading: true }));
    const ok = await deleteCustomer(delCustomer.item.id);
    setDelCustomer({ open: !ok, item: ok ? null : delCustomer.item, loading: false });
  };
  const confirmDeleteDoctor = async () => {
    setDelDoctor(p => ({ ...p, loading: true }));
    const ok = await deleteDoctor(delDoctor.item.id);
    setDelDoctor({ open: !ok, item: ok ? null : delDoctor.item, loading: false });
  };
  const handleExport = () => {
    if (isCustomers) {
      if (customers.length === 0) { toast.error('No customers to export'); return; }
      exportCustomersToExcel(customers);
    } else {
      if (doctors.length === 0) { toast.error('No doctors to export'); return; }
      exportDoctorsToExcel(doctors);
    }
    toast.success('Exported to Excel');
  };

  const isCustomers = activeSection === 'customers';

  return (
    <div className="px-8 py-6 min-h-screen bg-page" data-testid="customers-page">

      <PageHeader
        title="Customers & Doctors"
        actions={
          <div className="flex items-center gap-2">
            <AppButton
              variant="outline"
              icon={<FileSpreadsheet className="w-4 h-4" strokeWidth={1.5} />}
              onClick={handleExport}
              data-testid={isCustomers ? 'export-customers-btn' : 'export-doctors-btn'}
            >
              Export Excel
            </AppButton>
            <AppButton
              icon={<Plus className="w-4 h-4" strokeWidth={1.5} />}
              onClick={isCustomers ? handleAddCustomer : handleAddDoctor}
              data-testid={isCustomers ? 'add-customer-btn' : 'add-doctor-btn'}
            >
              {isCustomers ? 'Add Customer' : 'Add Doctor'}
            </AppButton>
          </div>
        }
      />

      <PageTabs tabs={CUSTOMER_TABS} activeTab={activeSection} onChange={setActiveSection} />

      <div className="flex items-center gap-4 mb-4">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder={isCustomers ? 'Search customers…' : 'Search doctors…'}
          className="w-64"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        {isCustomers ? (
          <>
            <CustomersTable
              customers={pageCustomers}
              loading={loading}
              searchQuery={searchQuery}
              onEdit={handleEditCustomer}
              onDelete={(c) => setDelCustomer({ open: true, item: c, loading: false })}
              onView={(c) => setDetailCustomer(c)}
              onAdd={handleAddCustomer}
            />
            <div className="px-6 py-4 border-t border-gray-100">
              <PaginationBar {...custPg} />
            </div>
          </>
        ) : (
          <>
            <DoctorsTable
              doctors={pageDoctors}
              loading={loading}
              searchQuery={searchQuery}
              onEdit={handleEditDoctor}
              onDelete={(d) => setDelDoctor({ open: true, item: d, loading: false })}
              onAdd={handleAddDoctor}
            />
            <div className="px-6 py-4 border-t border-gray-100">
              <PaginationBar {...docPg} />
            </div>
          </>
        )}
      </div>

      <CustomerFormDialog
        open={showCustomerDialog}
        editingCustomer={editingCustomer}
        onClose={handleCloseCustomerDialog}
        onSave={saveCustomer}
      />
      <DoctorFormDialog
        open={showDoctorDialog}
        editingDoctor={editingDoctor}
        onClose={handleCloseDoctorDialog}
        onSave={saveDoctor}
      />
      <CustomerDetailDialog
        open={!!detailCustomer}
        customer={detailCustomer}
        onClose={() => setDetailCustomer(null)}
      />
      <DeleteConfirmDialog
        open={delCustomer.open}
        onClose={() => setDelCustomer({ open: false, item: null, loading: false })}
        onConfirm={confirmDeleteCustomer}
        itemName={delCustomer.item?.name ? `customer "${delCustomer.item.name}"` : 'this customer'}
        isLoading={delCustomer.loading}
      />
      <DeleteConfirmDialog
        open={delDoctor.open}
        onClose={() => setDelDoctor({ open: false, item: null, loading: false })}
        onConfirm={confirmDeleteDoctor}
        itemName={delDoctor.item?.name ? `doctor "${delDoctor.item.name}"` : 'this doctor'}
        isLoading={delDoctor.loading}
      />
    </div>
  );
}
