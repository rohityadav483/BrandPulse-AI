'use client';
import {ErrorState} from '@/components/common/ErrorState';

export default function DashboardError({error, reset}: {error: Error; reset: () => void}) {
  return <ErrorState message={error.message || 'Unable to load the dashboard.'} onRetry={reset} />;
}
