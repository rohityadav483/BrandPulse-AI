'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {parseCompetitors} from '@/lib/competitors';
import {Banner} from '@/components/common/Banner';
import {ConfirmDialog} from '@/components/analyze/ConfirmDialog';
import {QuotaBanner} from '@/components/layout/QuotaBanner';
import {
  createAnalysis,
  estimateAnalysis,
  useGolden,
  type CreateAnalysisRequest,
  type EstimateAnalysisResponse,
} from '@/lib/api/client';

const PERIODS = [7, 14, 30] as const;

export default function Analyze() {
  const router = useRouter();
  const [brand, setBrand] = useState('Samsung');
  const [product, setProduct] = useState('Galaxy S25 Ultra');
  const [competitors, setCompetitors] = useState('Apple, OnePlus');
  const [category, setCategory] = useState<CreateAnalysisRequest['category']>('consumer_electronics');
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>(30);
  const [estimate, setEstimate] = useState<EstimateAnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const body: CreateAnalysisRequest = {
    brand: brand.trim(),
    product: product.trim() || null,
    competitors: parseCompetitors(competitors),
    category,
    period_days: period,
    as_of_date: '2026-08-10',
  };

  async function preview(e: React.FormEvent) {
    e.preventDefault();
    if (!body.brand) {
      setError('Enter a brand name.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      setEstimate(await estimateAnalysis(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to estimate this analysis');
    } finally {
      setBusy(false);
    }
  }

  async function confirm(accessCode: string) {
    setBusy(true);
    setError('');
    try {
      const result = await createAnalysis(body, accessCode || undefined);
      router.push(`/analyze/${result.id}`);
    } catch (err) {
      setEstimate(null);
      setError(err instanceof Error ? err.message : 'Unable to start analysis');
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <Badge>{useGolden ? 'Demo-safe' : 'Live'}</Badge>
      <h1 className="mt-4 text-3xl font-bold text-navy">Analyze a brand</h1>
      <p className="mt-2 text-slate-600">
        {useGolden
          ? 'Golden mode uses the pinned Samsung scenario and never spends search credits.'
          : 'Preview the cost first. Cached runs are free.'}
      </p>
      <div className="mt-4">
        <QuotaBanner />
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Analysis setup</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={preview} className="space-y-5">
            <Field label="Brand">
              <input className="input" maxLength={80} value={brand} onChange={(e) => setBrand(e.target.value)} />
            </Field>
            <Field label="Product (optional)">
              <input className="input" maxLength={80} value={product} onChange={(e) => setProduct(e.target.value)} />
            </Field>
            <Field label="Competitors (up to 2, comma separated)">
              <input className="input" value={competitors} onChange={(e) => setCompetitors(e.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Category">
                <select
                  className="input"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as CreateAnalysisRequest['category'])}
                >
                  <option value="consumer_electronics">Consumer electronics</option>
                  <option value="generic">Generic</option>
                </select>
              </Field>
              <Field label="Period">
                <select className="input" value={period} onChange={(e) => setPeriod(Number(e.target.value) as (typeof PERIODS)[number])}>
                  {PERIODS.map((p) => (
                    <option key={p} value={p}>
                      {p} days
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {error && <Banner tone="error">{error}</Banner>}
            <Button type="submit" disabled={busy}>
              {busy && !estimate ? 'Estimating…' : 'Preview analysis'}
            </Button>
          </form>
        </CardContent>
      </Card>
      {estimate && (
        <ConfirmDialog estimate={estimate} busy={busy} onConfirm={confirm} onCancel={() => setEstimate(null)} />
      )}
    </main>
  );
}

function Field({label, children}: {label: string; children: React.ReactNode}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}
