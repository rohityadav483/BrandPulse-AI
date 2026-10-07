import Link from 'next/link';
import {getInvestigation, listInvestigationEvidence} from '@/lib/api/client';
import {Badge} from '@/components/ui/badge';
import {EvidenceList} from '@/components/evidence/EvidenceList';

export default async function Evidence({params}: {params: {id: string}}) {
  const [data, inv] = await Promise.all([
    listInvestigationEvidence(params.id),
    getInvestigation(params.id),
  ]);
  const counts = data.counts;
  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <Link href={`/investigate/${inv.signal_id}`} className="text-sm font-medium text-brand">
        ← Back to investigation
      </Link>
      <h1 className="mt-5 text-3xl font-bold text-navy">Evidence explorer</h1>
      <p className="mt-2 text-slate-600">{data.total} cited items. Every citation links to its original source.</p>
      {counts && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge className="bg-emerald-50 text-emerald-700">{counts.supports} supporting</Badge>
          <Badge className="bg-red-50 text-red-700">{counts.contradicts} contradicting</Badge>
          <Badge className="bg-slate-100 text-slate-600">{counts.neutral} neutral</Badge>
        </div>
      )}
      <div className="mt-7">
        <EvidenceList items={data.items} />
      </div>
    </main>
  );
}
