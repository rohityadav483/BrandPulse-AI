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

describe('live API client', () => {
  it('uses an absolute API origin for server-side requests', async () => {
    vi.stubEnv('NEXT_PUBLIC_USE_GOLDEN', 'false');
    vi.stubEnv('API_ORIGIN', 'http://127.0.0.1:8000/');
    vi.resetModules();
    const {getDashboard} = await import('@/lib/api/client');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), {status: 200, headers: {'content-type': 'application/json'}}),
    );
    await getDashboard('00000000-0000-4000-8000-000000000001');
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/analyses/00000000-0000-4000-8000-000000000001/dashboard',
      expect.objectContaining({cache: 'no-store'}),
    );
    fetchSpy.mockRestore();
  });

  it('starts a live investigation with the access-code header', async () => {
    vi.stubEnv('NEXT_PUBLIC_USE_GOLDEN', 'false');
    vi.resetModules();
    const {investigateSignal} = await import('@/lib/api/client');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        investigation_id: '00000000-0000-4000-8000-000000000030',
        status: 'queued',
        reused: false,
        poll_url: '/api/v1/investigations/00000000-0000-4000-8000-000000000030',
      }), {status: 202, headers: {'content-type': 'application/json'}}),
    );
    const result = await investigateSignal('00000000-0000-4000-8000-000000000020', 'secret');
    expect(result.status).toBe('queued');
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/signals/00000000-0000-4000-8000-000000000020/investigate'),
      expect.objectContaining({headers: {'Content-Type': 'application/json', 'X-Access-Code': 'secret'}}),
    );
    fetchSpy.mockRestore();
  });
});
