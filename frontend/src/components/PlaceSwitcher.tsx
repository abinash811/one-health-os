/**
 * PlaceSwitcher — top bar. Shows where you are working right now and lets you move between every clinic and
 * pharmacy you can open (docs/32_CLINICS_SCOPE.md P2). One list, two groups: Clinics (EMR) and Pharmacies.
 * The trigger shows the place that belongs to the module you are in (a clinic on EMR pages, a pharmacy on
 * pharmacy pages). Switching updates the account's active place server-side, then reloads the page: many
 * pages cache place-scoped data, and a hard reload guarantees none of it survives stale.
 */
import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Building2, Check, ChevronDown, Pill, Stethoscope } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { AppButton } from '@/components/shared';
import { moduleForPath } from '@/components/navConfig';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';

interface Clinic { clinic_id: string; clinic_name: string; role_name: string; is_active: boolean }
interface Store { pharmacy_id: string; pharmacy_name: string; role_name: string; is_active: boolean }

export default function PlaceSwitcher() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);

  // Fetched once on mount: the trigger needs the active names before the list is ever opened.
  useEffect(() => {
    Promise.all([
      api.get(apiUrl.myClinics()).then((r: { data: Clinic[] }) => r.data || []).catch(() => [] as Clinic[]),
      api.get(apiUrl.myStores()).then((r: { data: Store[] }) => r.data || []).catch(() => [] as Store[]),
    ]).then(([c, s]) => { setClinics(c); setStores(s); }).finally(() => setLoading(false));
  }, []);

  const activeClinic = clinics.find((c) => c.is_active);
  const activeStore = stores.find((s) => s.is_active);
  const inEmr = moduleForPath(location.pathname) === 'emr';
  const label = inEmr
    ? (activeClinic?.clinic_name || 'Select a clinic')
    : (activeStore?.pharmacy_name || activeClinic?.clinic_name || (loading ? 'Loading…' : 'Select a place'));
  const Icon = inEmr ? Stethoscope : Building2;

  const run = async (url: string, body: object) => {
    if (switching) return;
    setSwitching(true);
    try {
      await api.post(url, body);
      window.location.reload();
    } catch (error) {
      toast.error((error as Error).message);
      setSwitching(false);
    }
  };

  const pickClinic = (c: Clinic) => { if (!c.is_active) run(apiUrl.switchClinic(), { clinic_id: c.clinic_id }); };
  const pickStore = (s: Store) => { if (!s.is_active) run(apiUrl.switchStore(), { pharmacy_id: s.pharmacy_id }); };

  const Check_ = ({ on }: { on: boolean }) => <span className="w-4 h-4 flex-shrink-0">{on && <Check className="w-4 h-4 text-brand" />}</span>;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <AppButton variant="secondary" size="sm" data-testid="place-switcher-trigger" aria-label="Switch clinic or pharmacy"
          className="max-w-[260px] gap-2" icon={<Icon className="w-4 h-4 flex-shrink-0" />}>
          <span className="truncate" title={label}>{label}</span>
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
        </AppButton>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-1 overflow-hidden" align="start" sideOffset={6}>
        <p className="px-2.5 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 flex items-center gap-1.5">
          <Stethoscope className="w-3 h-3" /> Clinics
        </p>
        {clinics.length === 0 && (
          <p className="px-2.5 py-2 text-xs text-gray-500" data-testid="place-switcher-no-clinics">
            No clinic yet — add one in Settings → Organisation → Clinics.
          </p>
        )}
        {clinics.map((c) => (
          <AppButton key={c.clinic_id} variant="ghost" onClick={() => pickClinic(c)} disabled={switching}
            className="w-full justify-start px-2.5 py-2 text-sm rounded-md" data-testid={`place-option-clinic-${c.clinic_id}`}>
            <Check_ on={c.is_active} />
            <div className="min-w-0 text-left">
              <div className="truncate text-gray-900 font-normal">{c.clinic_name}</div>
              <div className="truncate text-xs text-gray-500 capitalize font-normal">{c.role_name}</div>
            </div>
          </AppButton>
        ))}
        <div className="my-1 border-t border-gray-100" />
        <p className="px-2.5 pt-1 pb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 flex items-center gap-1.5">
          <Pill className="w-3 h-3" /> Pharmacies
        </p>
        {stores.map((s) => (
          <AppButton key={s.pharmacy_id} variant="ghost" onClick={() => pickStore(s)} disabled={switching}
            className="w-full justify-start px-2.5 py-2 text-sm rounded-md" data-testid={`place-option-pharmacy-${s.pharmacy_id}`}>
            <Check_ on={s.is_active} />
            <div className="min-w-0 text-left">
              <div className="truncate text-gray-900 font-normal">{s.pharmacy_name}</div>
              <div className="truncate text-xs text-gray-500 capitalize font-normal">{s.role_name}</div>
            </div>
          </AppButton>
        ))}
      </PopoverContent>
    </Popover>
  );
}
