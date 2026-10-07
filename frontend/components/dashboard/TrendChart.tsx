import type {SearchInterestPoint} from '@/lib/api/client';

type Point = {date: string; value: number};

/** Dependency-free SVG line chart for search-interest series. */
export function TrendChart({
  series,
  changePct,
}: {
  series: Point[];
  changePct?: number | null;
}) {
  if (series.length < 2) {
    return <p className="text-sm text-slate-500">Search-interest data is not available.</p>;
  }
  const w = 320;
  const h = 100;
  const pad = 6;
  const values = series.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = series.map((p, i) => {
    const x = pad + (i / (series.length - 1)) * (w - pad * 2);
    const y = h - pad - ((p.value - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <figure>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={`Search interest from ${series[0].date} to ${series[series.length - 1].date}`}
        className="h-28 w-full"
      >
        <polyline points={coords.join(' ')} fill="none" stroke="#2563eb" strokeWidth="2" />
        {coords.map((c, i) => (
          <circle key={series[i].date} cx={c.split(',')[0]} cy={c.split(',')[1]} r="2.5" fill="#2563eb" />
        ))}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-slate-500">
        <span>{series[0].date}</span>
        {changePct != null && (
          <span className="font-semibold text-navy">
            {changePct > 0 ? '+' : ''}
            {changePct}% vs prior period
          </span>
        )}
        <span>{series[series.length - 1].date}</span>
      </figcaption>
    </figure>
  );
}

export type {SearchInterestPoint};
