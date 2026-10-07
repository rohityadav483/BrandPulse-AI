import type {InvestigationResponse} from '@/lib/api/client';
import {label} from '@/lib/format';

type Confidence = NonNullable<InvestigationResponse['report']>['confidence'];

const WEIGHTS: Record<string, number> = {
  independence: 30,
  agreement: 25,
  signal_strength: 20,
  recency: 15,
  consistency: 10,
};

const labelTone: Record<Confidence['label'], string> = {
  high: 'bg-emerald-50 text-emerald-700',
  medium: 'bg-amber-50 text-amber-700',
  low: 'bg-red-50 text-red-700',
};

export function ConfidenceBreakdown({confidence}: {confidence: Confidence}) {
  return (
    <div>
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">Overall confidence</div>
          <div className="mt-1 text-3xl font-bold text-navy">{confidence.score}%</div>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${labelTone[confidence.label]}`}>
          {confidence.label}
        </span>
      </div>
      <ul className="mt-5 space-y-3">
        {Object.entries(confidence.factors).map(([key, value]) => (
          <li key={key} data-factor={key}>
            <div className="flex justify-between text-sm">
              <span className="capitalize text-slate-600">
                {label(key)}
                {WEIGHTS[key] !== undefined && (
                  <span className="ml-1 text-xs text-slate-400">weight {WEIGHTS[key]}%</span>
                )}
              </span>
              <span className="font-semibold">{Math.round(value * 100)}%</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full bg-brand" style={{width: `${Math.round(value * 100)}%`}} />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-500">
        Computed by a fixed backend formula. The language model never sets this number.
      </p>
    </div>
  );
}
