import * as React from 'react';

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-white px-6 py-10 text-center">
      <div className="text-base font-semibold text-navy">{title}</div>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
