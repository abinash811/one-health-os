/**
 * PlaceSwitcher — sits in the page header, right next to the page title ("Appointments | Sunrise Clinic ▾").
 * EMR pages list clinics only; pharmacy pages list pharmacies only; workspace-wide pages show none.
 * `PlaceProvider` (mounted once in the Layout) loads the lists a single time; every page header then renders
 * the switcher from that shared data. Shows where you are working right now and lets you move between every clinic and
 * pharmacy you can open (docs/32_CLINICS_SCOPE.md P2). One list per module: clinics on EMR pages, pharmacies on pharmacy pages.
 * The trigger shows the place that belongs to the module you are in (a clinic on EMR pages, a pharmacy on
 * pharmacy pages). Switching updates the account's active place server-side, then reloads the page: many
 * pages cache place-scoped data, and a hard reload guarantees none of it survives stale.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Building2, Check, ChevronDown, Stethoscope } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import AppButton from '@/components/shared/AppButton';
import { moduleForPath } from '@/components/navConfig';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';

interface Clinic { clinic_id: string; clinic_name: string; role_name: string; is_active: boolean }
interface Store { pharmacy_id: string; pharmacy_name: string; role_name: string; is_active: boolean }

interface PlaceData { clinics: Clinic[]; stores: Store[]; loading: boolean }
const PlaceContext = createContext<PlaceData | null>(null);

/** Loads the clinics and pharmacies this login can open — once, for the whole app shell. */
export function PlaceProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<PlaceData>({ clinics: [], stores: [], loading: true });
  // Fetched once on mount: the trigger needs the active names before the list is ever opened.
  useEffect(() => {
    Promise.all([
      api.get(apiUrl.myClinics()).then((r: { data: Clinic[] }) => r.data || []).catch(() => [] as Clinic[]),
      api.get(apiUrl.myStores()).then((r: { data: Store[] }) => r.data || []).catch(() => [] as Store[]),
    ]).then(([clinics, stores]) => setData({ clinics, stores, loading: false }));
  }, []);
  return <PlaceContext.Provider value={data}>{children}</PlaceContext.Provider>;
}

/** Renders nothing outside a PlaceProvider (e.g. a page rendered on its own in a test). */
export default function PlaceSwitcher({ withDivider = false }: { withDivider?: boolean }) {
  const ctx = useContext(PlaceContext);
  if (!ctx) return null;
  return (
    <>
      {withDivider && <span className="h-6 w-px bg-gray-200" aria-hidden="true" />}
      <PlaceSwitcherInner {...ctx} />
    </>
  );
}

function PlaceSwitcherInner({ clinics, stores, loading }: PlaceData) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  // One list per module: EMR pages choose between clinics, pharmacy pages between pharmacies. Workspace-wide
  // pages (Users, Audit Log, Organisation settings) belong to neither, so they show no switcher at all.
  const module = moduleForPath(location.pathname);
  const kind: 'clinic' | 'pharmacy' | null = module === 'emr' ? 'clinic' : module === 'admin' ? null : 'pharmacy';
  const activeClinic = clinics.find((c) => c.is_active);
  const activeStore = stores.find((s) => s.is_active);
  const label = kind === 'clinic'
    ? (activeClinic?.clinic_name || 'Select a clinic')
    : (activeStore?.pharmacy_name || (loading ? 'Loading…' : 'Select a pharmacy'));
  const Icon = kind === 'clinic' ? Stethoscope : Building2;

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

  if (kind === null) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <AppButton variant="secondary" size="sm" data-testid="place-switcher-trigger" className="max-w-[260px] gap-2"
          aria-label={kind === 'clinic' ? 'Switch clinic' : 'Switch pharmacy'} icon={<Icon className="w-4 h-4 flex-shrink-0" />}>
          <span className="truncate" title={label}>{label}</span>
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
        </AppButton>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-1 overflow-hidden" align="start" sideOffset={6}>
        {kind === 'clinic' && (
          <>
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
          </>
        )}
        {kind === 'pharmacy' && stores.map((s) => (
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
