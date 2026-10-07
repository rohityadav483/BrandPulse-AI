import Link from 'next/link';
import type {Recommendation} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';

const tone = {
  high: 'bg-red-50 text-red-700',
  medium: 'bg-amber-50 text-amber-700',
  low: 'bg-emerald-50 text-emerald-700',
} as const;

export function RecommendationList({
  items,
  evidenceBase,
}: {
  items: Recommendation[];
  evidenceBase: string;
}) {
  if (items.length === 0) return <p className="text-sm text-slate-500">No recommendations.</p>;
  return (
    <ul className="space-y-4">
      {items.map((r) => (
        <li key={r.id} className="border-l-2 border-brand pl-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={tone[r.priority]}>{r.priority}</Badge>
            <span className="font-semibold text-navy">{r.title}</span>
            <span className="text-xs text-slate-500">{r.timeframe}</span>
          </div>
          <p className="mt-1 text-sm text-slate-700">{r.action}</p>
          <p className="mt-1 text-xs text-slate-500">{r.rationale}</p>
          {(r.evidence_ids ?? []).length > 0 && (
            <div className="mt-1 text-xs">
              Evidence:{' '}
              {(r.evidence_ids ?? []).map((id, i) => (
                <Link key={id} href={`${evidenceBase}#evidence-${id}`} className="mr-2 font-semibold text-brand">
                  [{i + 1}]
                </Link>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
