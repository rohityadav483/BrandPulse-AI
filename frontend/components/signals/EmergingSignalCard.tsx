import Link from 'next/link';
import type {SignalSummary} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {growth, pct} from '@/lib/format';

type Impact = SignalSummary['impact'];

const impactTone: Record<Impact, string> = {
  high: 'bg-red-50 text-red-700',
  medium: 'bg-amber-50 text-amber-700',
  low: 'bg-emerald-50 text-emerald-700',
};

export function EmergingSignalCard({
  signal,
  investigateHref,
}: {
  signal: SignalSummary;
  investigateHref: string;
}) {
  return (
    <section
      aria-label="Emerging signal"
      className="rounded-xl border border-blue-200 bg-white p-6 shadow-card ring-1 ring-brand/10"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-brand text-white">Emerging signal</Badge>
        <Badge className={impactTone[signal.impact]}>{signal.impact.toUpperCase()} IMPACT</Badge>
        {signal.trend_corroborated && <Badge>Search interest corroborates</Badge>}
      </div>
      <div className="mt-4 text-3xl font-bold capitalize text-navy sm:text-4xl">
        {signal.aspect} complaints ↑ {growth(signal.growth)}
      </div>
      <p className="mt-2 text-slate-600">
        Negative share moved from {Math.round(signal.baseline_share * 100)}% to{' '}
        {Math.round(signal.current_share * 100)}% of dated news and web mentions.
      </p>
      <dl className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Stat term="Confidence" value={pct(signal.confidence)} />
        <Stat term="Current sample" value={`n=${signal.current_n}`} />
        <Stat term="Baseline sample" value={`n=${signal.baseline_n}`} />
        <Stat term="Source types" value={String(signal.sources_count)} />
      </dl>
      <div className="mt-2 text-xs text-slate-500">
        Sources: {signal.source_types.join(', ')}
      </div>
      <div className="mt-5">
        <Link href={investigateHref}>
          <Button>Investigate signal</Button>
        </Link>
      </div>
    </section>
  );
}

function Stat({term, value}: {term: string; value: string}) {
  return (
    <div className="rounded-lg bg-brand-soft p-3">
      <dt className="text-xs text-slate-500">{term}</dt>
      <dd className="mt-0.5 text-lg font-bold text-navy">{value}</dd>
    </div>
  );
}
