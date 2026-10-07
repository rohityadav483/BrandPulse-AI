import {goldenFixture} from '@/lib/golden/fixture';
import {
  goldenEstimate,
  goldenMentionsFor,
  goldenStatus,
  goldenUsage,
  type AnalysisStatusResponse,
  type EstimateAnalysisResponse,
  type ListMentionsResponse,
  type UsageResponse,
} from '@/lib/golden/extras';
import type {components} from './types.generated';

type Schemas = components['schemas'];
export type DashboardResponse = Schemas['DashboardResponse'];
export type SignalDetail = Schemas['SignalDetail'];
export type InvestigationResponse = Schemas['InvestigationResponse'];
export type ListEvidenceResponse = Schemas['ListEvidenceResponse'];
export type CreateAnalysisRequest = Schemas['CreateAnalysisRequest'];
export type CreateAnalysisResponse = Schemas['CreateAnalysisResponse'];
export type EvidenceItem = Schemas['EvidenceItem'];
export type Recommendation = Schemas['Recommendation'];
export type CompetitorComparison = Schemas['CompetitorComparison'];
export type SignalSummary = Schemas['SignalSummary'];
export type SearchInterestPoint = Schemas['SearchInterestPoint'];
export type {AnalysisStatusResponse, EstimateAnalysisResponse, ListMentionsResponse, UsageResponse};

export const useGolden = process.env.NEXT_PUBLIC_USE_GOLDEN === 'true';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {'Content-Type': 'application/json', ...(init?.headers ?? {})},
    cache: 'no-store',
  });
  if (!response.ok) {
    let code: string | undefined;
    let message = `API request failed (${response.status})`;
    try {
      const body = (await response.json()) as Schemas['ErrorResponse'];
      code = body.error.code;
      message = body.error.message;
    } catch {
      // Non-JSON error body: keep the generic message.
    }
    throw new ApiError(message, response.status, code);
  }
  return (await response.json()) as T;
}

export async function getDashboard(id: string): Promise<DashboardResponse> {
  if (useGolden || id === 'demo') return goldenFixture.dashboard;
  return request<DashboardResponse>(`/analyses/${id}/dashboard`);
}

export async function getSignal(id: string): Promise<SignalDetail> {
  if (useGolden || id === 'demo-signal-battery') return goldenFixture.signal_detail;
  return request<SignalDetail>(`/signals/${id}`);
}

export async function getInvestigation(id: string): Promise<InvestigationResponse> {
  if (useGolden || id === 'demo-investigation') return goldenFixture.investigation;
  return request<InvestigationResponse>(`/investigations/${id}`);
}

export async function listInvestigationEvidence(id: string): Promise<ListEvidenceResponse> {
  if (useGolden || id === 'demo-investigation') return goldenFixture.evidence;
  return request<ListEvidenceResponse>(`/investigations/${id}/evidence`);
}

export async function createAnalysis(
  body: CreateAnalysisRequest,
  accessCode?: string,
): Promise<CreateAnalysisResponse> {
  if (useGolden) return {id: 'demo', status: 'queued', poll_url: '/api/v1/analyses/demo'};
  return request<CreateAnalysisResponse>('/analyses', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: accessCode ? {'X-Access-Code': accessCode} : undefined,
  });
}

export async function estimateAnalysis(
  body: CreateAnalysisRequest,
): Promise<EstimateAnalysisResponse> {
  if (useGolden) return goldenEstimate;
  return request<EstimateAnalysisResponse>('/analyses/estimate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getUsage(): Promise<UsageResponse> {
  if (useGolden) return goldenUsage;
  return request<UsageResponse>('/usage');
}

export async function getAnalysisStatus(id: string): Promise<AnalysisStatusResponse> {
  if (useGolden || id === 'demo') return goldenStatus(id, 'done', 100);
  return request<AnalysisStatusResponse>(`/analyses/${id}`);
}

export async function listMentions(
  analysisId: string,
  aspect: string,
): Promise<ListMentionsResponse> {
  if (useGolden || analysisId === 'demo') return goldenMentionsFor(aspect);
  return request<ListMentionsResponse>(
    `/analyses/${analysisId}/mentions?aspect=${encodeURIComponent(aspect)}`,
  );
}
