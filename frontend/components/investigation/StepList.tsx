import type {InvestigationResponse} from '@/lib/api/client';

type Step = NonNullable<InvestigationResponse['steps']>[number];

const marker: Record<Step['state'], string> = {
  done: 'bg-emerald-500 text-white',
  active: 'bg-brand text-white',
  pending: 'bg-slate-200 text-slate-500',
};

export function StepList({steps}: {steps: Step[]}) {
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-2" aria-label="Investigation steps">
      {steps.map((s, i) => (
        <li key={s.key} data-state={s.state} className="flex items-center gap-2 text-sm text-slate-600">
          <span className={`flex h-5 w-5 items-center justify-center rounded-full text-xs ${marker[s.state]}`}>
            {s.state === 'done' ? '✓' : i + 1}
          </span>
          {s.label}
        </li>
      ))}
    </ol>
  );
}
