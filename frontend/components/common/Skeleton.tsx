import {cn} from '@/lib/utils';

export function Skeleton({className}: {className?: string}) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-lg bg-slate-100', className)} />;
}

export function DashboardSkeleton() {
  return (
    <main className="mx-auto max-w-7xl px-5 py-8" aria-busy="true" aria-label="Loading dashboard">
      <Skeleton className="h-8 w-72" />
      <Skeleton className="mt-3 h-4 w-56" />
      <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="mt-6 h-56" />
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </main>
  );
}
