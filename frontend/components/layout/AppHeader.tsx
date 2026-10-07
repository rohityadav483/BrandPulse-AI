import Link from 'next/link';
import {UsageIndicator} from '@/components/layout/UsageIndicator';

const links = [
  {href: '/', label: 'Overview'},
  {href: '/analyze', label: 'Analyze'},
  {href: '/dashboard/demo', label: 'Dashboard'},
  {href: '/competitors/demo', label: 'Competitors'},
  {href: '/evidence/demo-investigation', label: 'Evidence'},
];

export function AppHeader() {
  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 py-3">
        <Link href="/" className="text-lg font-bold text-navy">
          BrandPulse <span className="text-brand">AI</span>
        </Link>
        <nav aria-label="Main" className="order-3 flex w-full gap-4 overflow-x-auto text-sm text-slate-600 sm:order-none sm:w-auto">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="whitespace-nowrap hover:text-brand">
              {l.label}
            </Link>
          ))}
        </nav>
        <UsageIndicator />
      </div>
    </header>
  );
}
