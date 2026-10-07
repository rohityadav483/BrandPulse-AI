import './globals.css';
import type {Metadata, Viewport} from 'next';
import {AppHeader} from '@/components/layout/AppHeader';

export const metadata: Metadata = {
  title: 'BrandPulse AI',
  description: 'Detect emerging brand signals and investigate them with cited evidence.',
};

export const viewport: Viewport = {width: 'device-width', initialScale: 1};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en">
      <body>
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
