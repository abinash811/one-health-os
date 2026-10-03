/**
 * Settings → Pharmacy: the nine pharmacy setting pages (profile, receipt, GST, …) rendered one at a
 * time. One load + one Save for the whole settings object, exactly as the old tabbed page did, so
 * switching sections keeps unsaved edits (see useSettings.js on why that matters).
 */
import React, { useEffect } from 'react';
import { Save } from 'lucide-react';
import { AppButton, InlineLoader } from '@/components/shared';
import { useSettings } from '@/pages/Settings/hooks/useSettings';
import InventoryTab from '@/pages/Settings/components/InventoryTab';
import BillingTab from '@/pages/Settings/components/BillingTab';
import ReturnsTab from '@/pages/Settings/components/ReturnsTab';
import BillSequenceTab from '@/pages/Settings/components/BillSequenceTab';
import PharmacyProfileTab from '@/pages/Settings/components/PharmacyProfileTab';
import ReceiptTab from '@/pages/Settings/components/ReceiptTab';
import GSTTab from '@/pages/Settings/components/GSTTab';
import NotificationsTab from '@/pages/Settings/components/NotificationsTab';
import DataBackupTab from '@/pages/Settings/components/DataBackupTab';

export type PharmacySection =
  'profile' | 'receipt' | 'gst' | 'notifications' | 'inventory' | 'billing' | 'bill-sequence' | 'returns' | 'backup';

/** Sections that are their own action (not part of the one Save). */
const NO_SAVE: PharmacySection[] = ['bill-sequence', 'backup'];

export default function PharmacyPanel({ section }: { section: PharmacySection }) {
  const {
    settings, loading, saving, billSequences, sequenceLoading,
    fetchSettings, saveSettings, fetchBillSequences, saveBillSequence, updateSetting,
  } = useSettings();

  useEffect(() => { fetchSettings(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (section === 'bill-sequence') fetchBillSequences(); }, [section]); // eslint-disable-line react-hooks/exhaustive-deps

  // useSettings.js is untyped; its defaults object omits `digital`, so read it loosely.
  const s = settings as unknown as Record<string, any>;
  const up = (name: string) => (key: string, value: unknown) => updateSetting(name, key, value);

  if (loading) return <div className="text-center py-12"><InlineLoader text="Loading settings…" /></div>;

  return (
    <div data-testid="pharmacy-settings">
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-6">
          {section === 'profile' && <PharmacyProfileTab general={s.general || {}} onUpdate={up('general')} />}
          {section === 'receipt' && (
            <ReceiptTab print={s.print || {}} digital={s.digital || {}} general={s.general || {}}
              onUpdate={up('print')} onUpdateDigital={up('digital')} onUpdateGeneral={up('general')} />
          )}
          {section === 'gst' && <GSTTab gst={s.gst || {}} onUpdate={up('gst')} />}
          {section === 'notifications' && <NotificationsTab notifications={s.notifications || {}} onUpdate={up('notifications')} />}
          {section === 'inventory' && <InventoryTab inventory={s.inventory} onUpdate={up('inventory')} />}
          {section === 'billing' && <BillingTab billing={s.billing} onUpdate={up('billing')} />}
          {section === 'returns' && <ReturnsTab returns={s.returns} onUpdate={up('returns')} />}
          {section === 'bill-sequence' && (
            <BillSequenceTab billSequences={billSequences} sequenceLoading={sequenceLoading}
              onSave={saveBillSequence} onRefresh={fetchBillSequences} />
          )}
          {section === 'backup' && <DataBackupTab />}
        </div>
        {!NO_SAVE.includes(section) && (
          <div className="border-t border-gray-100 px-6 py-4 flex justify-end">
            <AppButton onClick={() => saveSettings(settings)} loading={saving} icon={<Save className="w-4 h-4" />}
              data-testid="save-settings-btn">
              {saving ? 'Saving…' : 'Save Settings'}
            </AppButton>
          </div>
        )}
      </div>
    </div>
  );
}
