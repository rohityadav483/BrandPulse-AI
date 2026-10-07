'use client';
import {Banner} from '@/components/common/Banner';
import {Button} from '@/components/ui/button';

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <Banner tone="error" title="Something went wrong">
        {message}
      </Banner>
      {onRetry && (
        <Button className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </main>
  );
}
