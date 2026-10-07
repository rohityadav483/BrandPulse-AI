import type {DashboardResponse} from '@/lib/api/client';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';

type Sentiment = DashboardResponse['target']['sentiment'];

export function SentimentSummary({sentiment}: {sentiment: Sentiment}) {
  const rows = [
    {label: 'Positive', value: sentiment.positive, cls: 'bg-emerald-500'},
    {label: 'Neutral', value: sentiment.neutral, cls: 'bg-slate-300'},
    {label: 'Negative', value: sentiment.negative, cls: 'bg-red-500'},
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sentiment</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {rows.map((r) => (
            <div key={r.label}>
              <div className="mb-1 flex justify-between text-sm">
                <span>{r.label}</span>
                <span className="font-semibold">{r.value}%</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100">
                <div className={`h-2 rounded-full ${r.cls}`} style={{width: `${r.value}%`}} />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
