import React, { useEffect, useState, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import '@/App.css';
import api from '@/lib/axios';
import { Toaster } from '@/components/ui/sonner';
import { toast } from 'sonner';
import { PageSkeleton } from '@/components/shared';

// AuthPage stays a static import — it's the first thing an unauthenticated
// visitor needs, and every other page below was previously bundled into
// that same initial chunk too, which is exactly why the login page loaded
// slower than it should have (Sep 22, 2026). Everything reachable only
// after login is lazy so the login bundle stops carrying it.
import AuthPage from '@/pages/AuthPage';
import ForgotPassword from '@/pages/ForgotPassword';
import ResetPassword from '@/pages/ResetPassword';
import Layout from '@/components/Layout';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ROUTES } from '@/constants/routes';
import { USER_ROLE } from '@/constants/domainConstants';

const Dashboard = lazy(() => import('@/pages/Dashboard'));
const BillingOperations = lazy(() => import('@/pages/BillingOperations'));
const BillingWorkspace = lazy(() => import('@/pages/BillingWorkspace'));
const BillDetail = lazy(() => import('@/pages/BillDetail'));
const SalesReturnsList = lazy(() => import('@/pages/SalesReturnsList'));
const SalesReturnCreate = lazy(() => import('@/pages/SalesReturnCreate'));
const SalesReturnDetail = lazy(() => import('@/pages/SalesReturnDetail'));
const InventorySearch = lazy(() => import('@/pages/InventorySearch'));
const MedicineDetail = lazy(() => import('@/pages/MedicineDetail'));
const PurchasesList = lazy(() => import('@/pages/PurchasesList'));
const PurchaseNew = lazy(() => import('@/pages/PurchaseNew'));
const PurchaseDetail = lazy(() => import('@/pages/PurchaseDetail'));
const PurchaseReturnCreate = lazy(() => import('@/pages/PurchaseReturnCreate'));
const PurchaseReturnDetail = lazy(() => import('@/pages/PurchaseReturnDetail'));
const PurchaseReturnsList = lazy(() => import('@/pages/PurchaseReturnsList'));
const Customers = lazy(() => import('@/pages/Customers'));
const Reports = lazy(() => import('@/pages/Reports'));
const Settings = lazy(() => import('@/pages/Settings'));
// Team page — merges Users + Roles into a single tabbed page
const Team = lazy(() => import('@/pages/Team'));
const Suppliers = lazy(() => import('@/pages/Suppliers'));
const GSTReport = lazy(() => import('@/pages/GSTReport'));
const DayEndClosing = lazy(() => import('@/pages/DayEndClosing'));
const ScheduleH1Register = lazy(() => import('@/pages/ScheduleH1Register'));
const AuditLog = lazy(() => import('@/pages/AuditLog'));
const StockMovementLog = lazy(() => import('@/pages/StockMovementLog'));
const ReorderList = lazy(() => import('@/pages/ReorderList'));
const TransferHistory = lazy(() => import('@/pages/TransferHistory'));
// EMR module (docs/28_EMR_SCOPE.md)
const EmrAppointments = lazy(() => import('@/modules/emr/pages/Appointments'));
const EmrPatients = lazy(() => import('@/modules/emr/pages/Patients'));
const EmrDoctorSchedules = lazy(() => import('@/modules/emr/pages/DoctorSchedules'));

// Clinic-only roles have no pharmacy permissions, so the pharmacy Dashboard
// would just 403 for them — land them on the clinic day view instead.
const CLINIC_ONLY_ROLES = [USER_ROLE.RECEPTIONIST, USER_ROLE.DOCTOR];
const homePathFor = (user) =>
  CLINIC_ONLY_ROLES.includes(user?.role) ? ROUTES.EMR.APPOINTMENTS : ROUTES.DASHBOARD;

// Auth Context
export const AuthContext = React.createContext(null);

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    if (!localStorage.getItem('token')) { setLoading(false); return; }
    try {
      const response = await api.get('/auth/me');
      setUser(response.data);
    } catch {
      localStorage.removeItem('token');
    }
    setLoading(false);
  };

  const login = (userData, token) => {
    setUser(userData);
    localStorage.setItem('token', token);
  };

  const logout = async () => {
    try { await api.post('/auth/logout'); } catch { /* silent */ }
    setUser(null);
    localStorage.removeItem('token');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, checkAuth }}>
      <BrowserRouter>
        <AppRoutes user={user} />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

function AppRoutes({ user }) {
  const location = useLocation();

  // Handle Emergent OAuth redirect
  useEffect(() => {
    const handleOAuthCallback = async () => {
      const hash = window.location.hash;
      if (hash && hash.includes('session_id=')) {
        const sessionId = hash.split('session_id=')[1].split('&')[0];
        
        try {
          const response = await api.post('/auth/session', {}, { headers: { 'X-Session-ID': sessionId } });
          
          const userData = response.data.user;
          const token = response.data.session_token || 'emergent-session';
          
          localStorage.setItem('token', token);
          window.location.href = '/dashboard';
        } catch (error) {
          console.error('OAuth callback error:', error);
          toast.error(error.message || 'Authentication failed');
          window.location.href = '/';
        }
      }
    };

    handleOAuthCallback();
  }, [location]);

  if (!user) {
    return (
      <Routes>
        <Route path="/" element={<AuthPage />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }

  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/" element={<ErrorBoundary><Layout /></ErrorBoundary>}>
          <Route index element={<Navigate to={homePathFor(user)} replace />} />
          <Route path="emr/appointments" element={<EmrAppointments />} />
          <Route path="emr/patients" element={<EmrPatients />} />
          <Route path="emr/schedules" element={<EmrDoctorSchedules />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="billing" element={<BillingOperations />} />
          <Route path="billing/new" element={<BillingWorkspace />} />
          <Route path="billing/create" element={<BillingWorkspace />} />
          <Route path="billing/edit/:id" element={<BillingWorkspace />} />
          <Route path="billing/returns" element={<SalesReturnsList />} />
          <Route path="billing/returns/new" element={<SalesReturnCreate />} />
          <Route path="billing/returns/edit/:id" element={<SalesReturnCreate />} />
          <Route path="billing/returns/:id" element={<SalesReturnDetail />} />
          <Route path="billing/:id" element={<BillDetail />} />
          <Route path="inventory" element={<InventorySearch />} />
          <Route path="inventory/product/:sku" element={<MedicineDetail />} />
          <Route path="inventory/edit/:sku" element={<MedicineDetail />} />
          <Route path="inventory/stock-movements" element={<StockMovementLog />} />
          <Route path="inventory/reorder" element={<ReorderList />} />
          <Route path="inventory/transfers" element={<TransferHistory />} />
          <Route path="purchases" element={<PurchasesList />} />
          <Route path="purchases/create" element={<PurchaseNew />} />
          <Route path="purchases/edit/:id" element={<PurchaseNew />} />
          <Route path="purchases/returns" element={<PurchaseReturnsList />} />
          <Route path="purchases/returns/create" element={<PurchaseReturnCreate />} />
          <Route path="purchases/returns/:id" element={<PurchaseReturnDetail />} />
          <Route path="purchases/:id" element={<PurchaseDetail />} />
          <Route path="customers" element={<Customers />} />
          <Route path="suppliers" element={<Suppliers />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/gst" element={<GSTReport />} />
          <Route path="reports/day-end" element={<DayEndClosing />} />
          <Route path="compliance/schedule-h1" element={<ScheduleH1Register />} />
          <Route path="audit-log" element={<AuditLog />} />
          <Route path="settings" element={<Settings />} />
          <Route path="team" element={<Team />} />
        </Route>
        <Route path="*" element={<Navigate to={homePathFor(user)} replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
