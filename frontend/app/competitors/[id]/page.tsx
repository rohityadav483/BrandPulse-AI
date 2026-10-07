import Link from 'next/link';
import {getDashboard} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {EmptyState} from '@/components/common/EmptyState';
import {signed} from '@/lib/format';

export default async function Competitors({params}: {params: {id: string}}) {
  const d = await getDashboard(params.id);
  const brands = [
    {brand: d.target.brand, sentiment: d.target.sentiment, aspects: d.target.aspects, lowData: d.target.low_data, n: d.target.sample_size},
    ...(d.competitors ?? []).map((c) => ({brand: c.brand, sentiment: c.sentiment, aspects: c.aspects, lowData: c.low_data, n: c.sample_size})),
  ];
  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <Link href={`/dashboard/${params.id}`} className="text-sm font-medium text-brand">
        ← Back to dashboard
      </Link>
      <Badge className="mt-5 block w-fit">Competitor analysis</Badge>
      <h1 className="mt-4 text-3xl font-bold text-navy">Competitor comparison</h1>
      <p className="mt-2 text-slate-600">Current window only. Competitors have no baseline, so no growth is computed for them.</p>
      {brands.length < 2 ? (
        <div className="mt-8">
          <EmptyState title="No competitors in this analysis">Add up to two competitors when you start an analysis.</EmptyState>
        </div>
      ) : (
        <Card className="mt-8">
          <CardHeader>
            <CardTitle>Sentiment and aspects</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-2 pr-3">Brand</th>
                    <th className="py-2 pr-3">Sample</th>
                    <th className="py-2 pr-3">Positive</th>
                    <th className="py-2 pr-3">Negative</th>
                    <th className="py-2">Aspects (net)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {brands.map((b) => (
                    <tr key={b.brand.id}>
                      <td className="py-3 pr-3 font-medium">
                        {b.brand.name} {b.brand.role === 'target' && <Badge className="ml-1">target</Badge>}
                      </td>
                      <td className="py-3 pr-3">
                        n={b.n}
                        {b.lowData && <span className="ml-1 text-xs text-amber-700">low data</span>}
                      </td>
                      <td className="py-3 pr-3">{b.sentiment.positive}%</td>
                      <td className="py-3 pr-3">{b.sentiment.negative}%</td>
                      <td className="py-3">
                        {b.aspects.map((a) => `${a.aspect} ${signed(a.net_score)}`).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
