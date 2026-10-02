import { useCallback, useEffect, useState } from 'react';
import api from '@/lib/axios';
import { apiUrl } from '@/constants/api';
import type { EmrSettings } from './types';

/** The clinic's EMR settings (patient-form layout, ID formats, default slot length).
 *  `null` until loaded — callers fall back to the built-in defaults, so a slow or
 *  failed load never blocks registering a patient. */
export function useEmrSettings(enabled = true) {
  const [settings, setSettings] = useState<EmrSettings | null>(null);

  const reload = useCallback(() => {
    api.get(apiUrl.emrSettings())
      .then((res: { data: EmrSettings }) => setSettings(res.data))
      .catch(() => setSettings(null));
  }, []);

  useEffect(() => { if (enabled) reload(); }, [enabled, reload]);

  return { settings, reload };
}
