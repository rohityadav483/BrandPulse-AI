'use client';
import {useEffect, useState} from 'react';
import {listMentions, type DashboardResponse, type ListMentionsResponse} from '@/lib/api/client';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Banner} from '@/components/common/Banner';
import {signed} from '@/lib/format';

type Aspect = DashboardResponse['target']['aspects'][number];

const sentimentTone = {
  positive: 'bg-emerald-50 text-emerald-700',
  neutral: 'bg-slate-100 text-slate-600',
  negative: 'bg-red-50 text-red-700',
} as const;

export function AspectTable({
  analysisId,
  aspects,
  topics,
}: {
  analysisId: string;
  aspects: Aspect[];
  topics: DashboardResponse['target']['topics'];
}) {
  const [selected, setSelected] = useState<Aspect | null>(null);
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Aspect health</CardTitle>
          <p className="text-xs text-slate-500">Select an aspect to see the analyzed clauses.</p>
        </CardHeader>
        <CardContent>
          {aspects.length === 0 ? (
            <p className="text-sm text-slate-500">No aspects detected yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {aspects.map((a) => (
                <li key={a.aspect}>
                  <button
                    type="button"
                    onClick={() => setSelected(a)}
                    className="flex w-full items-center justify-between py-3 text-left hover:bg-brand-soft"
                    aria-label={`Open ${a.aspect} details`}
                  >
                    <span>
                      <span className="block font-medium capitalize">{a.aspect}</span>
                      <span className="text-xs text-slate-500">{a.mentions} mentions</span>
                    </span>
                    <span className={a.net_score < 0 ? 'font-semibold text-red-600' : 'font-semibold text-emerald-600'}>
                      {signed(a.net_score)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {selected && (
        <AspectDrawer
          analysisId={analysisId}
          aspect={selected}
          topics={topics}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

export function AspectDrawer({
  analysisId,
  aspect,
  topics,
  onClose,
}: {
  analysisId: string;
  aspect: Aspect;
  topics: DashboardResponse['target']['topics'];
  onClose: () => void;
}) {
  const [data, setData] = useState<ListMentionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    listMentions(analysisId, aspect.aspect)
      .then((r) => active && setData(r))
      .catch((e: unknown) => active && setError(e instanceof Error ? e.message : 'Unable to load mentions'));
    return () => {
      active = false;
    };
  }, [analysisId, aspect.aspect]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-navy/30" role="dialog" aria-modal="true" aria-label={`${aspect.aspect} details`}>
      <aside className="h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-card">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-xl font-bold capitalize text-navy">{aspect.aspect}</h3>
            <p className="text-sm text-slate-500">
              Net {signed(aspect.net_score)} · {aspect.mentions} mentions
            </p>
          </div>
          <Button onClick={onClose} className="bg-white text-navy ring-1 ring-inset ring-border hover:bg-brand-soft">
            Close
          </Button>
        </div>
        <div className="mt-4 flex gap-2 text-xs">
          <Badge className={sentimentTone.positive}>{aspect.positive}% positive</Badge>
          <Badge className={sentimentTone.neutral}>{aspect.neutral}% neutral</Badge>
          <Badge className={sentimentTone.negative}>{aspect.negative}% negative</Badge>
        </div>
        <h4 className="mt-6 text-sm font-semibold text-navy">Related topics</h4>
        <div className="mt-2 flex flex-wrap gap-2">
          {topics.map((t) => (
            <Badge key={t.topic}>
              {t.topic} · {t.count}
            </Badge>
          ))}
        </div>
        <h4 className="mt-6 text-sm font-semibold text-navy">Analyzed clauses</h4>
        {error && <Banner tone="error" className="mt-2">{error}</Banner>}
        {!data && !error && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {data && data.items.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">No mentions recorded for this aspect.</p>
        )}
        <ul className="mt-2 space-y-3">
          {data?.items.map((m) => (
            <li key={m.id} className="rounded-lg border border-border p-3">
              {(m.aspects ?? [])
                .filter((a) => a.aspect === aspect.aspect)
                .map((a) => (
                  <p key={a.clause} className="text-sm text-navy">
                    <Badge className={`mr-2 ${sentimentTone[a.sentiment]}`}>{a.sentiment}</Badge>“{a.clause}”
                  </p>
                ))}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{m.source.source_type}</span>
                <span>{m.source.domain}</span>
                <a className="font-semibold text-brand" href={m.source.url} target="_blank" rel="noreferrer noopener">
                  Source ↗
                </a>
              </div>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
