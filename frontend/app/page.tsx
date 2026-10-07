import Link from 'next/link';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {goldenFixture} from '@/lib/golden/fixture';
import {growth, pct, signed} from '@/lib/format';

export default function Home() {
  const {target, signals} = goldenFixture.dashboard;
  const signal = signals?.[0];
  const battery = target.aspects.find((a) => a.aspect === 'battery');
  return (
    <main className="mx-auto max-w-7xl px-5 py-12">
      <div className="grid gap-10 lg:grid-cols-[1.25fr_.75fr] lg:items-center">
        <section>
          <Badge>Golden demo data</Badge>
          <h1 className="mt-4 text-4xl font-bold tracking-tight text-navy sm:text-5xl">
            See what is changing in your brand before it becomes obvious.
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-600">
            BrandPulse turns public signals into measurable trends, emerging issues, evidence-backed
            investigations, and actionable recommendations.
          </p>
          <ol className="mt-6 grid max-w-2xl gap-2 text-sm text-slate-600 sm:grid-cols-2">
            <li>1. Analyze a brand and its competitors</li>
            <li>2. Read Brand Health and aspect sentiment</li>
            <li>3. Spot the emerging signal</li>
            <li>4. Investigate with cited evidence</li>
          </ol>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/analyze">
              <Button>Analyze a brand</Button>
            </Link>
            <Link href="/dashboard/demo">
              <Button className="bg-white text-brand ring-1 ring-inset ring-blue-200 hover:bg-brand-soft">
                Open Samsung demo
              </Button>
            </Link>
          </div>
        </section>
        <Card>
          <CardHeader>
            <CardTitle>Samsung Galaxy S25 Ultra</CardTitle>
            <p className="text-sm text-slate-500">Pinned demo • 30-day window</p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Brand health" value={String(target.health.overall)} />
              <Metric label="Signal growth" value={signal ? growth(signal.growth) : '—'} />
              <Metric label="Confidence" value={signal ? pct(signal.confidence) : '—'} />
              <Metric label="Battery net" value={battery ? signed(battery.net_score) : '—'} />
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function Metric({label, value}: {label: string; value: string}) {
  return (
    <div className="rounded-lg bg-brand-soft p-4">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy">{value}</div>
    </div>
  );
}
