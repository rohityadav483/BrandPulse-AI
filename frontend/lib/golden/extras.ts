import type {components} from '@/lib/api/types.generated';
import {goldenFixture} from '@/lib/golden/fixture';

type Schemas = components['schemas'];
export type EstimateAnalysisResponse = Schemas['EstimateAnalysisResponse'];
export type UsageResponse = Schemas['UsageResponse'];
export type AnalysisStatusResponse = Schemas['AnalysisStatusResponse'];
export type ListMentionsResponse = Schemas['ListMentionsResponse'];
export type MentionItem = Schemas['MentionItem'];

/**
 * Frontend-only golden extras. These endpoints are not part of the golden JSON contract
 * (contracts/golden/samsung_battery.json is intentionally untouched). They are typed with
 * the generated OpenAPI schemas so they stay contract-compatible, and are only used when
 * NEXT_PUBLIC_USE_GOLDEN=true or for demo alias ids. No network calls are made.
 */
const period = goldenFixture.dashboard.analysis.period;

export const goldenEstimate: EstimateAnalysisResponse = {
  planned_calls: 11,
  cached_calls: 11,
  estimated_new_calls: 0,
  as_of_date: '2026-08-10',
  period,
  serpapi: {limit: 250, used: 83, remaining: 167, reserve: 20},
  live_enabled: false,
  needs_access_code: false,
  can_run: true,
  blocked_reason: null,
};

export const goldenUsage: UsageResponse = {
  month: '2026-08',
  serpapi: {limit: 250, used: 83, remaining: 167, reserve: 20, live_enabled: false},
  groq: {configured: false, calls_today: 0, model: null},
  analyses_today: {used: 0, limit: 3},
};

/** Simulated progress stages shown on the progress page (golden mode only). */
export const simulatedStages: ReadonlyArray<{
  stage: NonNullable<AnalysisStatusResponse['stage']>;
  label: string;
}> = [
  {stage: 'planning', label: 'Planning searches'},
  {stage: 'collecting', label: 'Collecting public sources'},
  {stage: 'processing', label: 'Cleaning and deduplicating'},
  {stage: 'analyzing', label: 'Analyzing sentiment and aspects'},
  {stage: 'detecting', label: 'Detecting emerging signals'},
  {stage: 'snapshotting', label: 'Building brand snapshots'},
];

export function goldenStatus(
  id: string,
  stage: AnalysisStatusResponse['stage'],
  progress: number,
): AnalysisStatusResponse {
  const done = stage === 'done';
  return {
    id,
    status: done ? 'completed' : 'running',
    stage,
    progress,
    brands: [
      goldenFixture.dashboard.target.brand,
      ...(goldenFixture.dashboard.competitors ?? []).map((c) => c.brand),
    ],
    product: goldenFixture.dashboard.analysis.product ?? null,
    period,
    warnings: [],
    serp_calls_used: 0,
    serp_calls_budget: 12,
    error: null,
    created_at: '2026-08-10T10:00:00Z',
    finished_at: done ? '2026-08-10T10:00:12Z' : null,
  };
}

const base = goldenFixture.evidence.items[0].source;

/** Mentions behind an aspect: clause-level text that produced the sentiment. */
export const goldenMentions: Record<string, MentionItem[]> = {
  battery: [
    {
      id: '00000000-0000-4000-8000-000000000101',
      source: {...base, source_type: 'forum', domain: 'reddit.com', title: 'Galaxy S25 Ultra battery discussion', snippet: 'Battery drains much faster since the latest update.'},
      sentiment: 'negative',
      aspects: [{aspect: 'battery', sentiment: 'negative', clause: 'battery drains much faster since the latest update'}],
    },
    {
      id: '00000000-0000-4000-8000-000000000102',
      source: {...base, source_type: 'news', domain: 'example-news.com', title: 'Users report battery drain after update', snippet: 'Owners report faster battery drain and warmer devices.', date_confidence: 'exact'},
      sentiment: 'negative',
      aspects: [{aspect: 'battery', sentiment: 'negative', clause: 'owners report faster battery drain and warmer devices'}],
    },
    {
      id: '00000000-0000-4000-8000-000000000103',
      source: {...base, source_type: 'youtube', domain: 'youtube.com', title: 'S25 Ultra long-term review', snippet: 'Camera is amazing but battery is disappointing.', date_confidence: 'approximate'},
      sentiment: 'negative',
      aspects: [
        {aspect: 'camera', sentiment: 'positive', clause: 'camera is amazing'},
        {aspect: 'battery', sentiment: 'negative', clause: 'battery is disappointing'},
      ],
    },
  ],
  camera: [
    {
      id: '00000000-0000-4000-8000-000000000104',
      source: {...base, source_type: 'youtube', domain: 'youtube.com', title: 'S25 Ultra camera test', snippet: 'The camera is excellent in low light.', date_confidence: 'approximate'},
      sentiment: 'positive',
      aspects: [{aspect: 'camera', sentiment: 'positive', clause: 'the camera is excellent in low light'}],
    },
  ],
};

export function goldenMentionsFor(aspect: string): ListMentionsResponse {
  const items = goldenMentions[aspect] ?? [];
  return {items, page: 1, page_size: 20, total: items.length};
}
