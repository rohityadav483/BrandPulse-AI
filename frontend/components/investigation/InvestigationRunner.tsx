'use client';

import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {ApiError, getInvestigation, investigateSignal} from '@/lib/api/client';
import {Button} from '@/components/ui/button';
import {Banner} from '@/components/common/Banner';

export function InvestigationRunner({signalId}: {signalId: string}) {
  const router = useRouter();
  const [accessCode, setAccessCode] = useState('');
  const [running, setRunning] = useState(false);
  const [investigationId, setInvestigationId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!running || !investigationId || status === 'completed' || status === 'failed') return;
    const timer = window.setInterval(async () => {
      try {
        const investigation = await getInvestigation(investigationId);
        setStatus(investigation.status);
        if (investigation.status === 'completed' || investigation.status === 'failed') {
          window.clearInterval(timer);
          router.refresh();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Polling failed.');
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [running, investigationId, status, router]);

  async function start() {
    setRunning(true);
    setError(null);
    try {
      const result = await investigateSignal(signalId, accessCode || undefined);
      setInvestigationId(result.investigation_id);
      const first = await getInvestigation(result.investigation_id);
      setStatus(first.status);
      if (first.status === 'completed' || first.status === 'failed') router.refresh();
    } catch (err) {
      setRunning(false);
      setError(err instanceof ApiError ? `${err.message} (${err.status})` : err instanceof Error ? err.message : 'Could not start investigation.');
    }
  }

  const waiting = running && status && status !== 'completed' && status !== 'failed';
  return (
    <div className="mt-6 space-y-3 rounded-xl border border-slate-200 bg-white p-5">
      <div>
        <p className="font-semibold text-navy">Investigate this signal</p>
        <p className="mt-1 text-sm text-slate-500">Collect evidence, compare competitors, and generate an evidence-backed report.</p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={accessCode}
          onChange={(e) => setAccessCode(e.target.value)}
          placeholder="Live access code (if required)"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          type="password"
        />
        <Button onClick={start} disabled={Boolean(waiting)}>
          {waiting ? `Investigation ${status}…` : 'Start investigation'}
        </Button>
      </div>
      {waiting && <p className="text-sm text-slate-500">Running in the background. This page checks every 2 seconds.</p>}
      {error && <Banner tone="error" title="Investigation could not start">{error}</Banner>}
    </div>
  );
}
