import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';

vi.mock('next/link', () => ({
  default: ({href, children}: {href: string; children: React.ReactNode}) => <a href={href}>{children}</a>,
}));

import {EmergingSignalCard} from '@/components/signals/EmergingSignalCard';
import {ConfidenceBreakdown} from '@/components/signals/ConfidenceBreakdown';
import {EvidenceList} from '@/components/evidence/EvidenceList';
import {Banner} from '@/components/common/Banner';
import {BrandHealthCard} from '@/components/dashboard/BrandHealthCard';
import {TrendChart} from '@/components/dashboard/TrendChart';
import {StepList} from '@/components/investigation/StepList';
import {CompetitorTable} from '@/components/investigation/CompetitorTable';
import {RecommendationList} from '@/components/investigation/RecommendationList';
import {ConfirmDialog} from '@/components/analyze/ConfirmDialog';
import {UsageBadge} from '@/components/layout/UsageIndicator';
import {QuotaNotice} from '@/components/layout/QuotaBanner';
import {quotaState} from '@/components/layout/quota';
import {StageList} from '@/components/analyze/AnalysisProgress';
import {goldenFixture} from '@/lib/golden/fixture';
import {goldenEstimate, goldenUsage} from '@/lib/golden/extras';
import {parseCompetitors} from '@/lib/competitors';

const signal = goldenFixture.dashboard.signals![0];
const report = goldenFixture.investigation.report!;
const evidence = goldenFixture.evidence.items;

describe('EmergingSignalCard', () => {
  it('shows growth, impact, samples and an investigate link', () => {
    const html = renderToStaticMarkup(<EmergingSignalCard signal={signal} investigateHref="/investigate/x" />);
    expect(html).toContain('battery complaints ↑ 3.3×');
    expect(html).toContain('HIGH IMPACT');
    expect(html).toContain('n=9');
    expect(html).toContain('n=2');
    expect(html).toContain('href="/investigate/x"');
    expect(html).toContain('Investigate signal');
  });
  it('omits corroboration badge when trend is not corroborated', () => {
    const html = renderToStaticMarkup(
      <EmergingSignalCard signal={{...signal, trend_corroborated: false}} investigateHref="/i" />,
    );
    expect(html).not.toContain('Search interest corroborates');
  });
});

describe('ConfidenceBreakdown', () => {
  it('renders score, label and every factor with weights', () => {
    const html = renderToStaticMarkup(<ConfidenceBreakdown confidence={report.confidence} />);
    expect(html).toContain('86%');
    expect(html).toContain('high');
    for (const key of Object.keys(report.confidence.factors)) expect(html).toContain(`data-factor="${key}"`);
    expect(html).toContain('weight 30%');
    expect(html).toContain('never sets this number');
  });
});

describe('EvidenceList', () => {
  it('renders every item with a source link and anchor id', () => {
    const html = renderToStaticMarkup(<EvidenceList items={evidence} />);
    for (const item of evidence) {
      expect(html).toContain(`id="evidence-${item.id}"`);
      expect(html).toContain(`href="${item.source.url}"`);
    }
    expect(html).toContain('Open source');
    expect(html).toContain('rel="noreferrer noopener"');
  });
  it('shows an empty message', () => {
    expect(renderToStaticMarkup(<EvidenceList items={[]} />)).toContain('No evidence items');
  });
});

describe('dashboard and investigation components', () => {
  it('marks engagement as a lower-confidence proxy', () => {
    const t = goldenFixture.dashboard.target;
    const html = renderToStaticMarkup(<BrandHealthCard health={t.health} sampleSize={t.sample_size} lowData={false} />);
    expect(html).toContain('>73<');
    expect(html).toContain('Proxy · lower confidence');
  });
  it('flags low data on the health card', () => {
    const t = goldenFixture.dashboard.target;
    expect(renderToStaticMarkup(<BrandHealthCard health={t.health} sampleSize={3} lowData />)).toContain('low data');
  });
  it('renders the trend chart or a fallback', () => {
    const si = goldenFixture.dashboard.target.search_interest!;
    expect(renderToStaticMarkup(<TrendChart series={si.series ?? []} changePct={si.change_pct} />)).toContain('<svg');
    expect(renderToStaticMarkup(<TrendChart series={[]} />)).toContain('not available');
  });
  it('renders investigation steps with states', () => {
    const html = renderToStaticMarkup(<StepList steps={goldenFixture.investigation.steps!} />);
    expect(html).toContain('data-state="done"');
  });
  it('renders the competitor comparison table', () => {
    const html = renderToStaticMarkup(<CompetitorTable comparison={report.competitor_comparison!} />);
    expect(html).toContain('Samsung');
    expect(html).toContain('Apple');
  });
  it('links recommendations to evidence anchors', () => {
    const html = renderToStaticMarkup(
      <RecommendationList items={report.recommendations!} evidenceBase="/evidence/inv" />,
    );
    expect(html).toContain('/evidence/inv#evidence-');
  });
  it('banner uses alert role for errors', () => {
    expect(renderToStaticMarkup(<Banner tone="error">x</Banner>)).toContain('role="alert"');
  });
  it('stage list marks earlier stages done', () => {
    const html = renderToStaticMarkup(<StageList stage="analyzing" />);
    expect(html.match(/data-state="done"/g)).toHaveLength(3);
    expect(html).toContain('data-state="active"');
  });
});

describe('ConfirmDialog', () => {
  const noop = () => undefined;
  it('says cached runs are free', () => {
    const html = renderToStaticMarkup(<ConfirmDialog estimate={goldenEstimate} busy={false} onConfirm={noop} onCancel={noop} />);
    expect(html).toContain('Served from cache');
    expect(html).toContain('Run from cache');
    expect(html).not.toContain('Access code');
  });
  it('asks for an access code on paid live runs', () => {
    const est = {...goldenEstimate, estimated_new_calls: 7, cached_calls: 4, needs_access_code: true, live_enabled: true};
    const html = renderToStaticMarkup(<ConfirmDialog estimate={est} busy={false} onConfirm={noop} onCancel={noop} />);
    expect(html).toContain('Access code');
    expect(html).toContain('Run analysis');
  });
  it('shows the blocked reason and disables confirm', () => {
    const est = {...goldenEstimate, estimated_new_calls: 7, can_run: false, blocked_reason: 'serpapi_quota_low' as const};
    const html = renderToStaticMarkup(<ConfirmDialog estimate={est} busy={false} onConfirm={noop} onCancel={noop} />);
    expect(html).toContain('quota is too low');
    expect(html).toContain('disabled');
  });
});

describe('quota states', () => {
  const withRemaining = (remaining: number, live = true) => ({
    ...goldenUsage,
    serpapi: {...goldenUsage.serpapi, remaining, live_enabled: live},
  });
  it('classifies quota', () => {
    expect(quotaState(withRemaining(167))).toBe('ok');
    expect(quotaState(withRemaining(167, false))).toBe('disabled');
    expect(quotaState(withRemaining(40))).toBe('low');
    expect(quotaState(withRemaining(20))).toBe('exhausted');
  });
  it('renders badge and notices', () => {
    expect(renderToStaticMarkup(<UsageBadge usage={withRemaining(167)} />)).toContain('167 live searches left');
    expect(renderToStaticMarkup(<QuotaNotice usage={withRemaining(40)} />)).toContain('quota is low');
    expect(renderToStaticMarkup(<QuotaNotice usage={withRemaining(10)} />)).toContain('quota reached');
    expect(renderToStaticMarkup(<QuotaNotice usage={withRemaining(167)} />)).toBe('');
  });
});

describe('parseCompetitors', () => {
  it('trims, drops blanks and caps at two', () => {
    expect(parseCompetitors(' Apple , , OnePlus, Google')).toEqual(['Apple', 'OnePlus']);
    expect(parseCompetitors('')).toEqual([]);
  });
});
