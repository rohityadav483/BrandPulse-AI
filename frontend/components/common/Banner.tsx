import * as React from 'react';
import {cn} from '@/lib/utils';

export type BannerTone = 'info' | 'warning' | 'error' | 'success';

const tones: Record<BannerTone, string> = {
  info: 'border-blue-200 bg-brand-soft text-navy',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-red-200 bg-red-50 text-red-800',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
};

export function Banner({
  tone = 'info',
  title,
  children,
  className,
}: {
  tone?: BannerTone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      data-tone={tone}
      className={cn('rounded-lg border px-4 py-3 text-sm', tones[tone], className)}
    >
      {title && <div className="font-semibold">{title}</div>}
      {children && <div className={title ? 'mt-1' : undefined}>{children}</div>}
    </div>
  );
}
