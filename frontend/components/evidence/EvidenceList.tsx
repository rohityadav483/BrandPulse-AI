import type {EvidenceItem} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {shortDate} from '@/lib/format';

const stanceTone: Record<EvidenceItem['stance'], string> = {
  supports: 'bg-emerald-50 text-emerald-700',
  contradicts: 'bg-red-50 text-red-700',
  neutral: 'bg-slate-100 text-slate-600',
};

export function EvidenceList({
  items,
  highlightId,
}: {
  items: EvidenceItem[];
  highlightId?: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">No evidence items to show.</p>;
  }
  return (
    <ul className="space-y-4">
      {items.map((item) => (
        <li key={item.id} id={`evidence-${item.id}`}>
          <Card className={item.id === highlightId ? 'ring-2 ring-brand' : undefined}>
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={stanceTone[item.stance]}>{item.stance}</Badge>
                <Badge>{item.source.source_type}</Badge>
                <Badge>Relevance {Math.round(item.relevance * 100)}%</Badge>
                <span className="text-xs text-slate-500">Rank {item.rank}</span>
              </div>
              <CardTitle className="mt-3">{item.source.title}</CardTitle>
            </CardHeader>
            <CardContent>
              {item.source.snippet && (
                <p className="text-sm leading-6 text-slate-600">{item.source.snippet}</p>
              )}
              {item.note && <p className="mt-2 text-sm italic text-slate-500">{item.note}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span>{item.source.domain}</span>
                <span>
                  {shortDate(item.source.published_at)} ({item.source.date_confidence} date)
                </span>
                <a
                  className="font-semibold text-brand"
                  href={item.source.url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  Open source ↗
                </a>
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
