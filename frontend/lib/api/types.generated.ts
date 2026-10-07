/** Generated from contracts/openapi.json. Do not edit manually. */

export interface AnalysesToday {
  "used": number;
  "limit": number;
}

export interface AnalysisListItem {
  "id": string;
  "brand": string;
  "product"?: string | null;
  "status": AnalysisStatus;
  "created_at": string;
  "top_signal"?: TopSignal | null;
}

export type AnalysisStage = "planning" | "collecting" | "processing" | "analyzing" | "detecting" | "snapshotting" | "done";

export type AnalysisStatus = "queued" | "running" | "completed" | "partial" | "failed";

export interface AnalysisStatusResponse {
  "id": string;
  "status": AnalysisStatus;
  "stage"?: AnalysisStage | null;
  "progress": number;
  "brands": Array<BrandRef>;
  "product"?: string | null;
  "period": Period;
  "warnings"?: Array<Warning>;
  "serp_calls_used": number;
  "serp_calls_budget": number;
  "error"?: string | null;
  "created_at": string;
  "finished_at"?: string | null;
}

export interface AspectStat {
  "aspect": string;
  "net_score": number;
  "mentions": number;
  "positive": number;
  "neutral": number;
  "negative": number;
}

export type BlockedReason = "serpapi_quota_low" | "live_data_disabled" | "daily_limit_reached";

export interface BrandRef {
  "id": string;
  "name": string;
  "role": BrandRole;
}

export type BrandRole = "target" | "competitor" | "suggested";

export type Category = "consumer_electronics" | "generic";

export interface ComparisonRow {
  "brand": BrandRef;
  "positive_pct": number;
  "negative_pct": number;
  "aspect_negative_share": number;
  "level": ImpactLevel;
  "search_interest_change_pct"?: number | null;
}

export interface CompetitorBlock {
  "brand": BrandRef;
  "sample_size": number;
  "low_data": boolean;
  "sentiment": SentimentDistribution;
  "aspects": Array<AspectStat>;
  "search_interest"?: SearchInterest | null;
}

export interface CompetitorComparison {
  "aspect": string;
  "rows": Array<ComparisonRow>;
}

export interface ConfidenceFactors {
  "independence": number;
  "agreement": number;
  "signal_strength": number;
  "recency": number;
  "consistency": number;
}

export type ConfidenceLabel = "low" | "medium" | "high";

export type ConfidenceSource = "signal" | "investigation";

export type CoverageSourceType = "web" | "news" | "youtube" | "forum" | "shopping" | "trends";

export interface CreateAnalysisRequest {
  "brand": string;
  "product"?: string | null;
  "competitors"?: Array<string>;
  "category"?: Category;
  "period_days"?: 7 | 14 | 30;
  "as_of_date"?: string | null;
}

export interface CreateAnalysisResponse {
  "id": string;
  "status": AnalysisStatus;
  "poll_url": string;
}

export interface DashboardAnalysis {
  "id": string;
  "status": AnalysisStatus;
  "product"?: string | null;
  "as_of_date": string;
  "live_run": boolean;
  "period": Period;
  "warnings"?: Array<Warning>;
}

export interface DashboardResponse {
  "analysis": DashboardAnalysis;
  "target": TargetBlock;
  "competitors"?: Array<CompetitorBlock>;
  "signals"?: Array<SignalSummary>;
}

export type DateConfidence = "exact" | "approximate" | "unknown";

export interface ErrorBody {
  "code": string;
  "message": string;
  "details"?: { [key: string]: unknown };
}

export interface ErrorResponse {
  "error": ErrorBody;
}

export interface EstimateAnalysisResponse {
  "planned_calls": number;
  "cached_calls": number;
  "estimated_new_calls": number;
  "as_of_date": string;
  "period": Period;
  "serpapi": SerpapiQuota;
  "live_enabled": boolean;
  "needs_access_code": boolean;
  "can_run": boolean;
  "blocked_reason"?: BlockedReason | null;
}

export interface EvidenceCounts {
  "supports": number;
  "contradicts": number;
  "neutral": number;
}

export interface EvidenceItem {
  "id": string;
  "stance": Stance;
  "relevance": number;
  "note"?: string | null;
  "rank": number;
  "source": Source;
}

export interface Finding {
  "text": string;
  "evidence_ids"?: Array<string>;
}

export type GeneratedBy = "llm" | "fallback";

export interface GrowthSampleSize {
  "current": number;
  "baseline": number;
}

export interface HealthResponse {
  "status": "ok" | "degraded";
  "version": string;
  "database": "ok" | "unavailable";
  "nlp": "ok" | "loading" | "unavailable";
  "serpapi_configured": boolean;
  "live_serpapi_enabled": boolean;
  "groq_configured": boolean;
  "demo_mode": boolean;
}

export interface HealthScores {
  "overall": number;
  "sentiment": number;
  "engagement": number;
  "risk": number;
  "trend": number;
  "formula_version": string;
}

export type ImpactLevel = "low" | "medium" | "high";

export interface InvestigateSignalResponse {
  "investigation_id": string;
  "status": InvestigationStatus;
  "reused": boolean;
  "poll_url": string;
}

export interface InvestigationConfidence {
  "score": number;
  "label": ConfidenceLabel;
  "factors": ConfidenceFactors;
}

export interface InvestigationRef {
  "id": string;
  "status": InvestigationStatus;
}

export interface InvestigationReport {
  "generated_by": GeneratedBy;
  "summary": string;
  "findings"?: Array<Finding>;
  "scope": Scope;
  "confidence": InvestigationConfidence;
  "source_coverage"?: Array<SourceCoverage>;
  "search_interest"?: ReportSearchInterest | null;
  "competitor_comparison"?: CompetitorComparison | null;
  "recommendations"?: Array<Recommendation>;
  "disclaimer": string;
}

export interface InvestigationResponse {
  "id": string;
  "signal_id": string;
  "analysis_id": string;
  "status": InvestigationStatus;
  "step": InvestigationStep;
  "steps"?: Array<InvestigationStepInfo>;
  "report"?: InvestigationReport | null;
  "error"?: string | null;
}

export type InvestigationStatus = "queued" | "running" | "completed" | "failed";

export type InvestigationStep = "generating_queries" | "collecting_evidence" | "scoring_evidence" | "comparing_competitors" | "synthesizing" | "recommending" | "done";

export interface InvestigationStepInfo {
  "key": InvestigationStep;
  "label": string;
  "state": StepState;
}

export interface ListAnalysesResponse {
  "items": Array<AnalysisListItem>;
}

export interface ListEvidenceResponse {
  "items": Array<EvidenceItem>;
  "page": number;
  "page_size": number;
  "total": number;
  "counts": EvidenceCounts;
}

export interface ListMentionsResponse {
  "items": Array<MentionItem>;
  "page": number;
  "page_size": number;
  "total": number;
}

export interface MentionAspect {
  "aspect": string;
  "sentiment": Sentiment;
  "clause": string;
}

export interface MentionItem {
  "id": string;
  "source": Source;
  "sentiment": Sentiment;
  "aspects"?: Array<MentionAspect>;
}

export interface Period {
  "current_start": string;
  "current_end": string;
  "baseline_start": string;
  "baseline_end": string;
}

export type Priority = "low" | "medium" | "high";

export interface Recommendation {
  "id": string;
  "priority": Priority;
  "title": string;
  "action": string;
  "rationale": string;
  "evidence_ids"?: Array<string>;
  "timeframe": string;
}

export interface ReportSearchInterest {
  "keyword": string;
  "change_pct"?: number | null;
}

export interface Scope {
  "verdict": ScopeVerdict;
  "ratio"?: number | null;
  "explanation": string;
}

export type ScopeVerdict = "brand_specific" | "industry_wide" | "inconclusive" | "unknown";

export interface ScoreComponents {
  "growth": number;
  "frequency": number;
  "cross_source": number;
  "sentiment_impact": number;
}

export interface SearchInterest {
  "change_pct"?: number | null;
  "series"?: Array<SearchInterestPoint>;
}

export interface SearchInterestPoint {
  "date": string;
  "value": number;
}

export type Sentiment = "positive" | "neutral" | "negative";

export interface SentimentDistribution {
  "positive": number;
  "neutral": number;
  "negative": number;
}

export interface SerpapiQuota {
  "limit": number;
  "used": number;
  "remaining": number;
  "reserve": number;
}

export interface SignalDetail {
  "id": string;
  "kind": SignalKind;
  "aspect": string;
  "growth": number;
  "impact": ImpactLevel;
  "confidence": number;
  "confidence_source": ConfidenceSource;
  "sources_count": number;
  "source_types": Array<SourceType>;
  "current_share": number;
  "baseline_share": number;
  "current_n": number;
  "baseline_n": number;
  "trend_corroborated": boolean;
  "status": SignalStatus;
  "analysis_id": string;
  "brand": BrandRef;
  "score": number;
  "score_components": ScoreComponents;
  "latest_investigation"?: InvestigationRef | null;
}

export type SignalKind = "aspect_negative_spike";

export type SignalStatus = "detected" | "investigating" | "investigated";

export interface SignalSummary {
  "id": string;
  "kind": SignalKind;
  "aspect": string;
  "growth": number;
  "impact": ImpactLevel;
  "confidence": number;
  "confidence_source": ConfidenceSource;
  "sources_count": number;
  "source_types": Array<SourceType>;
  "current_share": number;
  "baseline_share": number;
  "current_n": number;
  "baseline_n": number;
  "trend_corroborated": boolean;
  "status": SignalStatus;
  "brand_id": string;
  "investigation_id"?: string | null;
}

export interface Source {
  "source_type": SourceType;
  "domain": string;
  "url": string;
  "title": string;
  "snippet"?: string | null;
  "author"?: string | null;
  "published_at"?: string | null;
  "date_confidence": DateConfidence;
  "collected_at": string;
}

export interface SourceCoverage {
  "source_type": CoverageSourceType;
  "supporting": number;
}

export type SourceType = "web" | "news" | "youtube" | "forum" | "shopping";

export type Stance = "supports" | "contradicts" | "neutral";

export type StepState = "done" | "active" | "pending";

export interface TargetBlock {
  "brand": BrandRef;
  "sample_size": number;
  "baseline_sample_size": number;
  "growth_sample_size": GrowthSampleSize;
  "low_data": boolean;
  "health": HealthScores;
  "sentiment": SentimentDistribution;
  "aspects": Array<AspectStat>;
  "topics": Array<TopicCount>;
  "source_mix": Record<string, number>;
  "search_interest"?: SearchInterest | null;
}

export interface TopSignal {
  "aspect": string;
  "impact": ImpactLevel;
}

export interface TopicCount {
  "topic": string;
  "count": number;
}

export interface UsageGroq {
  "configured": boolean;
  "calls_today": number;
  "model"?: string | null;
}

export interface UsageResponse {
  "month": string;
  "serpapi": UsageSerpapi;
  "groq": UsageGroq;
  "analyses_today": AnalysesToday;
}

export interface UsageSerpapi {
  "limit": number;
  "used": number;
  "remaining": number;
  "reserve": number;
  "live_enabled": boolean;
}

export interface Warning {
  "code": string;
  "message": string;
  "stage"?: AnalysisStage | null;
}

export type WindowKind = "baseline" | "current";



export interface components {

  schemas: {

    AnalysesToday: AnalysesToday;

    AnalysisListItem: AnalysisListItem;

    AnalysisStage: AnalysisStage;

    AnalysisStatus: AnalysisStatus;

    AnalysisStatusResponse: AnalysisStatusResponse;

    AspectStat: AspectStat;

    BlockedReason: BlockedReason;

    BrandRef: BrandRef;

    BrandRole: BrandRole;

    Category: Category;

    ComparisonRow: ComparisonRow;

    CompetitorBlock: CompetitorBlock;

    CompetitorComparison: CompetitorComparison;

    ConfidenceFactors: ConfidenceFactors;

    ConfidenceLabel: ConfidenceLabel;

    ConfidenceSource: ConfidenceSource;

    CoverageSourceType: CoverageSourceType;

    CreateAnalysisRequest: CreateAnalysisRequest;

    CreateAnalysisResponse: CreateAnalysisResponse;

    DashboardAnalysis: DashboardAnalysis;

    DashboardResponse: DashboardResponse;

    DateConfidence: DateConfidence;

    ErrorBody: ErrorBody;

    ErrorResponse: ErrorResponse;

    EstimateAnalysisResponse: EstimateAnalysisResponse;

    EvidenceCounts: EvidenceCounts;

    EvidenceItem: EvidenceItem;

    Finding: Finding;

    GeneratedBy: GeneratedBy;

    GrowthSampleSize: GrowthSampleSize;

    HealthResponse: HealthResponse;

    HealthScores: HealthScores;

    ImpactLevel: ImpactLevel;

    InvestigateSignalResponse: InvestigateSignalResponse;

    InvestigationConfidence: InvestigationConfidence;

    InvestigationRef: InvestigationRef;

    InvestigationReport: InvestigationReport;

    InvestigationResponse: InvestigationResponse;

    InvestigationStatus: InvestigationStatus;

    InvestigationStep: InvestigationStep;

    InvestigationStepInfo: InvestigationStepInfo;

    ListAnalysesResponse: ListAnalysesResponse;

    ListEvidenceResponse: ListEvidenceResponse;

    ListMentionsResponse: ListMentionsResponse;

    MentionAspect: MentionAspect;

    MentionItem: MentionItem;

    Period: Period;

    Priority: Priority;

    Recommendation: Recommendation;

    ReportSearchInterest: ReportSearchInterest;

    Scope: Scope;

    ScopeVerdict: ScopeVerdict;

    ScoreComponents: ScoreComponents;

    SearchInterest: SearchInterest;

    SearchInterestPoint: SearchInterestPoint;

    Sentiment: Sentiment;

    SentimentDistribution: SentimentDistribution;

    SerpapiQuota: SerpapiQuota;

    SignalDetail: SignalDetail;

    SignalKind: SignalKind;

    SignalStatus: SignalStatus;

    SignalSummary: SignalSummary;

    Source: Source;

    SourceCoverage: SourceCoverage;

    SourceType: SourceType;

    Stance: Stance;

    StepState: StepState;

    TargetBlock: TargetBlock;

    TopSignal: TopSignal;

    TopicCount: TopicCount;

    UsageGroq: UsageGroq;

    UsageResponse: UsageResponse;

    UsageSerpapi: UsageSerpapi;

    Warning: Warning;

    WindowKind: WindowKind;

  };

}
