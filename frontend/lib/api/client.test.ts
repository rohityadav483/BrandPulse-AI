import { describe, expect, it, vi } from 'vitest';
import { goldenFixture } from '@/lib/golden/fixture';

describe('golden contract', () => {
  it('contains the pinned Samsung scenario', () => {
    expect(goldenFixture.dashboard.target.brand.name).toBe('Samsung');
    expect(goldenFixture.dashboard.target.health.overall).toBe(73);

    const signals = goldenFixture.dashboard.signals ?? [];
    expect(signals.length).toBeGreaterThan(0);
    expect(signals[0].growth).toBe(3.3);

    expect(goldenFixture.investigation.report?.confidence.score).toBe(86);
  });
});

describe('golden client mode', () => {
  it('serves estimate, usage, status and mentions without network', async () => {
    vi.stubEnv('NEXT_PUBLIC_USE_GOLDEN', 'true');
    vi.resetModules();
    const {estimateAnalysis, getUsage, getAnalysisStatus, listMentions} = await import('@/lib/api/client');
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    expect((await estimateAnalysis({brand: 'Samsung'})).estimated_new_calls).toBe(0);
    expect((await getUsage()).serpapi.limit).toBe(250);
    expect((await getAnalysisStatus('demo')).status).toBe('completed');
    const mentions = await listMentions('demo', 'battery');
    expect(mentions.total).toBeGreaterThan(0);
    expect(mentions.items.every((m) => (m.aspects ?? []).some((a) => a.aspect === 'battery'))).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
