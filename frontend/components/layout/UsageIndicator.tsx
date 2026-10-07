'use client';
import {useEffect, useState} from 'react';
import {getUsage, type UsageResponse} from '@/lib/api/client';
import {quotaState, type QuotaState} from '@/components/layout/quota';
import {cn} from '@/lib/utils';

const dot: Record<QuotaState, string> = {
  ok: 'bg-emerald-500',
  disabled: 'bg-slate-400',
  low: 'bg-amber-500',
  exhausted: 'bg-red-500',
};

export function UsageBadge({usage}: {usage: UsageResponse}) {
  const state = quotaState(usage);
  const text =
    state === 'disabled'
      ? 'Live searches off · cached'
      : `${usage.serpapi.remaining} live searches left`;
  return (
    <span
      data-quota={state}
      title={`SerpApi ${usage.month}: ${usage.serpapi.used}/${usage.serpapi.limit} used`}
      className="inline-flex items-center gap-2 rounded-full border border-border bg-white px-3 py-1 text-xs text-slate-600"
    >
      <span className={cn('h-2 w-2 rounded-full', dot[state])} aria-hidden="true" />
      {text}
    </span>
  );
}

export function UsageIndicator() {
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
  if (!usage) return null;
  return <UsageBadge usage={usage} />;
}
