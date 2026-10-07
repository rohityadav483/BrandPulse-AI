import Link from 'next/link';
import {getSignal} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {growth, label, pct, score} from '@/lib/format';

const WEIGHTS: Record<string, number> = {growth: 35, frequency: 20, cross_source: 25, sentiment_impact: 20};

export default async function SignalDetailPage({params}: {params: {id: string}}) {
  const s = await getSignal(params.id);
  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <Link href={`/dashboard/${s.analysis_id}`} className="text-sm font-medium text-brand">
        ← Back to dashboard
      </Link>
      <div className="mt-5 flex flex-wrap gap-2">
        <Badge>Signal detail</Badge>
        <Badge className="bg-red-50 text-red-700">{s.impact.toUpperCase()} IMPACT</Badge>
      </div>
      <h1 className="mt-3 text-3xl font-bold capitalize text-navy">
        {s.brand.name} {s.aspect} complaints ↑ {growth(s.growth)}
      </h1>
      <p className="mt-2 text-slate-600">
        Signal score {score(s.score)} · confidence {pct(s.confidence)} · {s.sources_count} source types
      </p>
      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Score components</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {Object.entries(s.score_components).map(([k, v]) => (
              <li key={k}>
                <div className="flex justify-between text-sm">
                  <span className="capitalize text-slate-600">
                    {label(k)} <span className="text-xs text-slate-400">weight {WEIGHTS[k]}%</span>
                  </span>
                  <span className="font-semibold">{Math.round(v * 100)}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                  <div className="h-1.5 rounded-full bg-brand" style={{width: `${Math.round(v * 100)}%`}} />
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-slate-600">
            Negative share {Math.round(s.baseline_share * 100)}% → {Math.round(s.current_share * 100)}% (baseline n=
            {s.baseline_n}, current n={s.current_n}).
          </p>
          <div className="mt-5">
            <Link href={`/investigate/${s.id}`}>
              <Button>Investigate signal</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
