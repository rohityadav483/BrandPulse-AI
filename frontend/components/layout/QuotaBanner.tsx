'use client';
import {useEffect, useState} from 'react';
import {getUsage, type UsageResponse} from '@/lib/api/client';
import {Banner} from '@/components/common/Banner';
import {quotaState} from '@/components/layout/quota';

export function QuotaNotice({usage}: {usage: UsageResponse}) {
  const state = quotaState(usage);
  if (state === 'low') {
    return (
      <Banner tone="warning" title="Live search quota is low">
        {usage.serpapi.remaining} searches remain this month (reserve {usage.serpapi.reserve}). Cached
        analyses are still free.
      </Banner>
    );
  }
  if (state === 'exhausted') {
    return (
      <Banner tone="error" title="Live search quota reached">
        New live runs are blocked until the monthly allowance resets. Cached analyses still work.
      </Banner>
    );
  }
  return null;
}

export function QuotaBanner() {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  useEffect(() => {
    let active = true;
    getUsage()
      .then((u) => active && setUsage(u))
      .catch(() => active && setUsage(null));
    return () => {
      active = false;
    };
  }, []);
  return usage ? <QuotaNotice usage={usage} /> : null;
}
