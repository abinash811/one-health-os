/**
 * DataBackupTab — one-click full data export/backup.
 * No persisted settings — self-contained action, same pattern as
 * BillSequenceTab (no generic "Save Settings" button shown for this tab).
 */
import React, { useState } from 'react';
import { Download, DatabaseBackup, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { AppButton } from '@/components/shared';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import { today } from '@/utils/dates';

export default function DataBackupTab() {
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await api.get(apiUrl.backupExport());
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), {
        href: url, download: `pharmacare-backup-${today()}.json`,
      });
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success('Backup downloaded');
    } catch (err: any) {
      toast.error(err.message || 'Failed to download backup');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-2">Data Export & Backup</h3>
        <p className="text-sm text-gray-600 mb-6">
          Download a complete copy of your pharmacy's data — medicines, bills, purchases, customers,
          doctors, and suppliers — as a single JSON file. Keep it somewhere safe for your own records.
        </p>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 flex items-start gap-4">
          <DatabaseBackup className="w-8 h-8 text-blue-600 flex-shrink-0" strokeWidth={1.5} />
          <div className="flex-1">
            <h4 className="font-medium text-gray-800 mb-1">Full data backup</h4>
            <p className="text-sm text-gray-600 mb-4">
              Includes every active record for this pharmacy as of the moment you download it.
            </p>
            <AppButton
              onClick={handleDownload}
              loading={downloading}
              icon={<Download className="w-4 h-4" strokeWidth={1.5} />}
              data-testid="download-backup-btn"
            >
              {downloading ? 'Preparing…' : 'Download Backup'}
            </AppButton>
          </div>
        </div>

        <div className="mt-6 bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" strokeWidth={1.5} />
          <div className="text-sm text-amber-800">
            <p className="font-medium mb-1">Good to know:</p>
            <ul className="list-disc list-inside space-y-1 text-amber-700">
              <li>Only administrators can download a backup</li>
              <li>Every download is recorded in the Audit Log, with who and when</li>
              <li>Clinic data (patients, appointments, prescriptions, patient bills) comes from the clinic you are working at — switch clinic and download again for each one</li>
              <li>This is a point-in-time snapshot — it doesn't update itself later</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
