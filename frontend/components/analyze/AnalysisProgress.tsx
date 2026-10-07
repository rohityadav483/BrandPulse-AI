'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {getAnalysisStatus, useGolden, type AnalysisStatusResponse} from '@/lib/api/client';
import {goldenStatus, simulatedStages} from '@/lib/golden/extras';
import {Banner} from '@/components/common/Banner';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';

const POLL_MS = 2000;
const SIMULATED_TICK_MS = 1000;

export function StageList({
  stage,
  failed,
}: {
  stage: AnalysisStatusResponse['stage'];
  failed?: boolean;
}) {
  const activeIndex = stage === 'done' ? simulatedStages.length : simulatedStages.findIndex((s) => s.stage === stage);
  return (
    <ol className="space-y-3" aria-label="Analysis stages">
      {simulatedStages.map((s, i) => {
        const state = i < activeIndex ? 'done' : i === activeIndex ? (failed ? 'failed' : 'active') : 'pending';
        return (
          <li key={s.stage} data-state={state} className="flex items-center gap-3 text-sm">
            <span
              className={
                'flex h-6 w-6 items-center justify-center rounded-full text-xs ' +
                (state === 'done'
                  ? 'bg-emerald-500 text-white'
                  : state === 'active'
                    ? 'bg-brand text-white'
                    : state === 'failed'
                      ? 'bg-red-500 text-white'
                      : 'bg-slate-200 text-slate-500')
              }
            >
              {state === 'done' ? '✓' : state === 'failed' ? '!' : i + 1}
            </span>
            <span className={state === 'pending' ? 'text-slate-400' : 'text-navy'}>{s.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AnalysisProgress({id}: {id: string}) {
  const router = useRouter();
  const [status, setStatus] = useState<AnalysisStatusResponse>(goldenStatus(id, 'planning', 5));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let tick = 0;
    const run = async () => {
      if (useGolden) {
        tick += 1;
        if (tick >= simulatedStages.length) {
          if (active) setStatus(goldenStatus(id, 'done', 100));
          return true;
        }
        const progress = Math.round((tick / simulatedStages.length) * 100);
        if (active) setStatus(goldenStatus(id, simulatedStages[tick].stage, progress));
        return false;
      }
      try {
        const next = await getAnalysisStatus(id);
        if (active) setStatus(next);
        return next.status === 'completed' || next.status === 'partial' || next.status === 'failed';
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Unable to read analysis status');
        return true;
      }
    };
    const interval = setInterval(
      () => {
        void run().then((finished) => {
          if (finished) clearInterval(interval);
        });
      },
      useGolden ? SIMULATED_TICK_MS : POLL_MS,
    );
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [id]);

  const finished = status.status === 'completed' || status.status === 'partial';
  const failed = status.status === 'failed';

  return (
    <Card className="mt-8">
      <CardHeader>
        <CardTitle>{finished ? 'Analysis ready' : failed ? 'Analysis failed' : 'Analysis in progress'}</CardTitle>
        <p className="text-xs text-slate-500">
          {status.serp_calls_used} of {status.serp_calls_budget} searches used ·{' '}
          {useGolden ? 'simulated progress on golden data' : 'live status'}
        </p>
      </CardHeader>
      <CardContent>
        <div className="mb-5 h-2 rounded-full bg-slate-100" role="progressbar" aria-valuenow={status.progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-2 rounded-full bg-brand transition-all" style={{width: `${status.progress}%`}} />
        </div>
        <StageList stage={status.stage} failed={failed} />
        {error && <Banner tone="error" className="mt-5">{error}</Banner>}
        {failed && !error && (
          <Banner tone="error" className="mt-5" title="The analysis could not finish">
            {status.error ?? 'Unknown error.'}
          </Banner>
        )}
        {status.status === 'partial' && (
          <Banner tone="warning" className="mt-5" title="Partial results">
            {(status.warnings ?? []).map((w) => w.message).join(' ') || 'Some stages did not complete.'}
          </Banner>
        )}
        {finished && (
          <div className="mt-6">
            <Button onClick={() => router.push(`/dashboard/${id}`)}>View dashboard</Button>
          </div>
        )}
        {failed && (
          <div className="mt-6">
            <Link href="/analyze" className="font-semibold text-brand">← Start a new analysis</Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
