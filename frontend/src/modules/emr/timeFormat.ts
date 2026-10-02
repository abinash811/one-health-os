/** '09:30' (24h, as the API sends it) → '9:30 AM'. Falls back to '—' for walk-ins. */
export function to12h(value: string | null | undefined): string {
  if (!value) return '—';
  const [h, m] = value.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return value;
  const suffix = h >= 12 ? 'PM' : 'AM';
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${suffix}`;
}
