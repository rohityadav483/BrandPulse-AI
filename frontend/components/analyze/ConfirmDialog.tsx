'use client';
import {useState} from 'react';
import type {EstimateAnalysisResponse} from '@/lib/api/client';
import {Banner} from '@/components/common/Banner';
import {Button} from '@/components/ui/button';

const blockedMessage: Record<NonNullable<EstimateAnalysisResponse['blocked_reason']>, string> = {
  serpapi_quota_low: 'Monthly live-search quota is too low for a new live run. Cached runs still work.',
  live_data_disabled: 'Live data collection is switched off. Only cached runs are available.',
  daily_limit_reached: 'The daily analysis limit has been reached. Try again tomorrow.',
};

export function ConfirmDialog({
  estimate,
  busy,
  onConfirm,
  onCancel,
}: {
  estimate: EstimateAnalysisResponse;
  busy: boolean;
  onConfirm: (accessCode: string) => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState('');
  const free = estimate.estimated_new_calls === 0;
  const lowAfter = estimate.serpapi.remaining - estimate.estimated_new_calls <= estimate.serpapi.reserve;
  const needsCode = estimate.needs_access_code && !free;
  const blocked = !estimate.can_run;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-navy/30 p-4" role="dialog" aria-modal="true" aria-label="Confirm analysis">
      <div className="w-full max-w-md rounded-xl border border-border bg-white p-6 shadow-card">
        <h2 className="text-lg font-bold text-navy">Confirm analysis</h2>
        <dl className="mt-4 space-y-2 text-sm">
          <Row term="Planned searches" value={String(estimate.planned_calls)} />
          <Row term="Served from cache" value={String(estimate.cached_calls)} />
          <Row term="New live searches" value={String(estimate.estimated_new_calls)} strong />
          <Row term="Left this month" value={`${estimate.serpapi.remaining} of ${estimate.serpapi.limit}`} />
        </dl>
        {free && !blocked && (
          <Banner tone="success" className="mt-4">
            Served from cache. No search credits will be spent.
          </Banner>
        )}
        {!free && lowAfter && !blocked && (
          <Banner tone="warning" className="mt-4" title="Quota low">
            This run would leave you close to the reserve of {estimate.serpapi.reserve} searches.
          </Banner>
        )}
        {blocked && estimate.blocked_reason && (
          <Banner tone="error" className="mt-4">
            {blockedMessage[estimate.blocked_reason]}
          </Banner>
        )}
        {needsCode && !blocked && (
          <label className="mt-4 block text-sm font-medium text-slate-700">
            Access code
            <input
              className="input mt-1"
              type="password"
              autoComplete="off"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button onClick={onCancel} className="bg-white text-navy ring-1 ring-inset ring-border hover:bg-brand-soft">
            Cancel
          </Button>
          <Button disabled={busy || blocked || (needsCode && code.trim() === '')} onClick={() => onConfirm(code)}>
            {busy ? 'Starting…' : free ? 'Run from cache' : 'Run analysis'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Row({term, value, strong}: {term: string; value: string; strong?: boolean}) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-600">{term}</dt>
      <dd className={strong ? 'font-bold text-navy' : 'font-medium text-navy'}>{value}</dd>
    </div>
  );
}
