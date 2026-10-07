import Link from 'next/link';
import {getDashboard} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Banner} from '@/components/common/Banner';
import {EmptyState} from '@/components/common/EmptyState';
import {QuotaBanner} from '@/components/layout/QuotaBanner';
import {BrandHealthCard} from '@/components/dashboard/BrandHealthCard';
import {SentimentSummary} from '@/components/dashboard/SentimentSummary';
import {AspectTable} from '@/components/dashboard/AspectTable';
import {TrendChart} from '@/components/dashboard/TrendChart';
import {EmergingSignalCard} from '@/components/signals/EmergingSignalCard';
import {signed} from '@/lib/format';

export default async function Dashboard({params}: {params: {id: string}}) {
  const d = await getDashboard(params.id);
  const signals = d.signals ?? [];
  const competitors = d.competitors ?? [];
  const warnings = d.analysis.warnings ?? [];
  const signal = signals[0];
  const interest = d.target.search_interest;

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Badge>{d.analysis.live_run ? 'Live run' : 'Golden data'}</Badge>
          <h1 className="mt-3 text-3xl font-bold text-navy">
            {d.target.brand.name}
            {d.analysis.product ? ` — ${d.analysis.product}` : ''}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            As of {d.analysis.as_of_date} • {d.analysis.period.current_start} to {d.analysis.period.current_end}
          </p>
        </div>
        <Link href={`/competitors/${params.id}`} className="text-sm font-semibold text-brand">
          Compare competitors →
        </Link>
      </div>

      <div className="mt-5 space-y-3">
        <QuotaBanner />
        {d.analysis.status === 'partial' && (
          <Banner tone="warning" title="Partial results">
            Some stages did not finish. Numbers below may be incomplete.
          </Banner>
        )}
        {warnings.map((w) => (
          <Banner key={w.code} tone="warning">
            {w.message}
          </Banner>
        ))}
        {d.target.low_data && (
          <Banner tone="warning" title="Low data">
            Only {d.target.sample_size} mentions were found. Scores and signals are less reliable.
          </Banner>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1fr]">
        <BrandHealthCard health={d.target.health} sampleSize={d.target.sample_size} lowData={d.target.low_data} />
        <SentimentSummary sentiment={d.target.sentiment} />
      </div>

      <div className="mt-6">
        {signal ? (
          <EmergingSignalCard signal={signal} investigateHref={`/investigate/${signal.id}`} />
        ) : (
          <EmptyState title="No emerging signal detected">
            Nothing is growing fast enough in this window to flag. Aspect health is still shown below.
          </EmptyState>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <AspectTable analysisId={params.id} aspects={d.target.aspects} topics={d.target.topics} />
        <Card>
          <CardHeader>
            <CardTitle>Search interest</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart series={interest?.series ?? []} changePct={interest?.change_pct} />
            <h3 className="mt-5 text-sm font-semibold text-navy">Source mix</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(d.target.source_mix).map(([k, v]) => (
                <Badge key={k}>
                  {k} · {String(v)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Competitor snapshot</CardTitle>
        </CardHeader>
        <CardContent>
          {competitors.length === 0 ? (
            <p className="text-sm text-slate-500">No competitors in this analysis.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {competitors.map((c) => {
                const battery = c.aspects[0];
                return (
                  <div key={c.brand.id} className="flex items-center justify-between rounded-lg bg-brand-soft p-3">
                    <span className="font-medium">{c.brand.name}</span>
                    <span className="text-sm text-slate-600">
                      {battery ? `${battery.aspect} ${signed(battery.net_score)}` : 'No aspect data'}
                      {c.low_data ? ' · low data' : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
