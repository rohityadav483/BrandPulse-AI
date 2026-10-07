import type {DashboardResponse} from '@/lib/api/client';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';

type Health = DashboardResponse['target']['health'];

function tone(value: number): string {
  if (value >= 70) return 'text-emerald-600';
  if (value >= 50) return 'text-amber-600';
  return 'text-red-600';
}

export function BrandHealthCard({
  health,
  sampleSize,
  lowData,
}: {
  health: Health;
  sampleSize: number;
  lowData: boolean;
}) {
  const parts: Array<{key: string; label: string; value: number; proxy?: boolean}> = [
    {key: 'sentiment', label: 'Sentiment', value: health.sentiment},
    {key: 'engagement', label: 'Engagement', value: health.engagement, proxy: true},
    {key: 'risk', label: 'Risk (100 = none)', value: health.risk},
    {key: 'trend', label: 'Trend', value: health.trend},
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Brand Health</CardTitle>
        <p className="text-xs text-slate-500">
          Based on {sampleSize} mentions{lowData ? ' · low data, treat with caution' : ''}
        </p>
      </CardHeader>
      <CardContent>
        <div className={`text-5xl font-bold ${tone(health.overall)}`}>
          {health.overall}
          <span className="text-xl text-slate-400">/100</span>
        </div>
        <ul className="mt-4 grid grid-cols-2 gap-3 text-sm">
          {parts.map((p) => (
            <li key={p.key} className="rounded-lg bg-brand-soft p-3" data-part={p.key}>
              <div className="text-xs text-slate-500">{p.label}</div>
              <div className="mt-0.5 text-lg font-bold text-navy">{p.value}</div>
              {p.proxy && <Badge className="mt-1 bg-slate-100 text-slate-600">Proxy · lower confidence</Badge>}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
