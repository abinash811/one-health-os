import React from 'react';
import { renderHook } from '@testing-library/react';
import { AuthContext } from '@/App';
import { hasPermission, useClinicAccess } from '../clinicAccess';

const wrap = (user: unknown) => ({ children }: { children: React.ReactNode }) => (
  <AuthContext.Provider value={{ user } as never}>{children}</AuthContext.Provider>);

describe('hasPermission', () => {
  it('allows everything for "*" and only listed ids otherwise', () => {
    expect(hasPermission(['*'], 'patient_billing:collect')).toBe(true);
    expect(hasPermission(['patient_billing:collect'], 'patient_billing:collect')).toBe(true);
    expect(hasPermission(['patient_billing:view'], 'patient_billing:collect')).toBe(false);
  });
  it('does not hide anything for an old session with no list (the backend still enforces)', () => {
    expect(hasPermission(undefined, 'patient_billing:collect')).toBe(true);
  });
});

describe('useClinicAccess — ticks decide, never the role name', () => {
  it('a doctor with Collect ticked can collect', () => {
    const { result } = renderHook(() => useClinicAccess(), {
      wrapper: wrap({ role: 'doctor', permissions: ['patient_billing:view', 'patient_billing:collect'] }) });
    expect(result.current.canCollect).toBe(true);
    expect(result.current.canCancelInvoice).toBe(false);
  });

  it('a receptionist with Collect unticked cannot', () => {
    const { result } = renderHook(() => useClinicAccess(), {
      wrapper: wrap({ role: 'receptionist', permissions: ['patient_billing:view'] }) });
    expect(result.current.canCollect).toBe(false);
  });

  it('an admin (["*"]) can do everything even with a clinical role', () => {
    const { result } = renderHook(() => useClinicAccess(), { wrapper: wrap({ role: 'doctor', permissions: ['*'] }) });
    expect(result.current).toEqual({ canCollect: true, canCancelInvoice: true, canWriteRx: true });
  });

  it('Write Rx follows the prescriptions tick', () => {
    const off = renderHook(() => useClinicAccess(), { wrapper: wrap({ role: 'doctor', permissions: ['prescriptions:view'] }) });
    expect(off.result.current.canWriteRx).toBe(false);
    const on = renderHook(() => useClinicAccess(), { wrapper: wrap({ role: 'cashier', permissions: ['prescriptions:create'] }) });
    expect(on.result.current.canWriteRx).toBe(true);
  });
});
