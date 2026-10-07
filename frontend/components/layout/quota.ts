import type {UsageResponse} from '@/lib/api/client';

/** Remaining searches (above the reserve) at or below this level count as "low". */
export const QUOTA_LOW_THRESHOLD = 30;

export type QuotaState = 'ok' | 'low' | 'exhausted' | 'disabled';

export function quotaState(usage: UsageResponse): QuotaState {
  const available = usage.serpapi.remaining - usage.serpapi.reserve;
  if (available <= 0) return 'exhausted';
  if (available <= QUOTA_LOW_THRESHOLD) return 'low';
  return usage.serpapi.live_enabled ? 'ok' : 'disabled';
}
