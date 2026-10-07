import type {CompetitorComparison} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';

const levelTone = {
  high: 'bg-red-50 text-red-700',
  medium: 'bg-amber-50 text-amber-700',
  low: 'bg-emerald-50 text-emerald-700',
} as const;

export function CompetitorTable({comparison}: {comparison: CompetitorComparison}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-left text-sm">
        <caption className="sr-only">Competitor comparison for {comparison.aspect}</caption>
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="py-2 pr-3">Brand</th>
            <th className="py-2 pr-3">Positive</th>
            <th className="py-2 pr-3">Negative</th>
            <th className="py-2 pr-3 capitalize">{comparison.aspect} negative share</th>
            <th className="py-2 pr-3">Level</th>
            <th className="py-2">Search interest</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {comparison.rows.map((r) => (
            <tr key={r.brand.id}>
              <td className="py-2 pr-3 font-medium">{r.brand.name}</td>
              <td className="py-2 pr-3">{r.positive_pct}%</td>
              <td className="py-2 pr-3">{r.negative_pct}%</td>
              <td className="py-2 pr-3">{Math.round(r.aspect_negative_share * 100)}%</td>
              <td className="py-2 pr-3">
                <Badge className={levelTone[r.level]}>{r.level}</Badge>
              </td>
              <td className="py-2">
                {r.search_interest_change_pct == null
                  ? '—'
                  : `${r.search_interest_change_pct > 0 ? '+' : ''}${r.search_interest_change_pct}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
