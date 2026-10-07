import Link from 'next/link';
import {Badge} from '@/components/ui/badge';
import {AnalysisProgress} from '@/components/analyze/AnalysisProgress';

export default function AnalysisProgressPage({params}: {params: {id: string}}) {
  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <Link href="/analyze" className="text-sm font-medium text-brand">
        ← Back to analyze
      </Link>
      <Badge className="mt-5 block w-fit">Analysis progress</Badge>
      <h1 className="mt-4 text-3xl font-bold text-navy">Building your analysis</h1>
      <p className="mt-2 text-slate-600">
        Analysis <code className="rounded bg-slate-100 px-1.5 py-0.5 text-sm">{params.id}</code>
      </p>
      <AnalysisProgress id={params.id} />
    </main>
  );
}
