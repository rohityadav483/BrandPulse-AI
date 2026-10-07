"""API DTOs, one-to-one with docs/API.md (v2). The exported OpenAPI is the machine contract.

Conventions (API.md section 1): snake_case, lowercase enums, UUID ids, ISO 8601 UTC timestamps,
percentages 0-100 (fractions 0-1 only when the field name ends in `_share`).
Change a shape here -> update docs/API.md, regenerate contracts/openapi.json (+ TS types) and the
golden fixture in the same change.
"""

import datetime as dt
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.domain import (
    MAX_COMPETITORS,
    MAX_NAME_LENGTH,
    AnalysisStage,
    AnalysisStatus,
    BlockedReason,
    BrandRole,
    Category,
    ConfidenceLabel,
    ConfidenceSource,
    CoverageSourceType,
    DateConfidence,
    GeneratedBy,
    ImpactLevel,
    InvestigationStatus,
    InvestigationStep,
    Priority,
    ScopeVerdict,
    Sentiment,
    SignalKind,
    SignalStatus,
    SourceType,
    Stance,
    StepState,
    confidence_label,
)

# Reusable constrained types
Percent = Annotated[int, Field(ge=0, le=100)]  # 0-100
SignedPercent = Annotated[int, Field(ge=-100, le=100)]  # net_score
Fraction = Annotated[
    float, Field(ge=0, le=1)
]  # 0-1 (`*_share`, relevance, factors, scores)
Count = Annotated[int, Field(ge=0)]
BrandName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]


# --- Error envelope (API.md section 1) -----------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- Shared types (API.md section 2) -------------------------------------------------------------


class Warning(BaseModel):  # name fixed by API.md section 2
    code: str
    message: str
    stage: AnalysisStage | None = None


class BrandRef(BaseModel):
    id: UUID
    name: str
    role: BrandRole


class Period(BaseModel):
    current_start: date
    current_end: date
    baseline_start: date
    baseline_end: date


class Source(BaseModel):
    source_type: SourceType
    domain: str
    url: str
    title: str
    snippet: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    date_confidence: DateConfidence
    collected_at: datetime


# --- Analyses: create / estimate (API.md section 3.1, 3.11) --------------------------------------


class CreateAnalysisRequest(BaseModel):
    """Body of `createAnalysis` and `estimateAnalysis`."""

    brand: BrandName
    product: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, max_length=MAX_NAME_LENGTH)
        ]
        | None
    ) = None
    competitors: list[BrandName] = Field(
        default_factory=list, max_length=MAX_COMPETITORS
    )
    category: Category = Category.consumer_electronics
    period_days: Literal[7, 14, 30] = 30
    as_of_date: date | None = None

    @field_validator("product")
    @classmethod
    def _blank_product_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _drop_target_and_duplicate_competitors(self) -> Self:
        """Case-insensitive duplicates and the target brand are removed (API.md section 3.1).

        The `max_length=2` check runs on the raw input first, so 3 names -> 422 even if two of
        them would later collapse into one.
        """
        seen = {self.brand.casefold()}
        kept: list[str] = []
        for name in self.competitors:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                kept.append(name)
        self.competitors = kept
        return self


class CreateAnalysisResponse(BaseModel):
    id: UUID
    status: AnalysisStatus
    poll_url: str


class SerpapiQuota(BaseModel):
    limit: Count
    used: Count
    remaining: Count
    reserve: Count


class EstimateAnalysisResponse(BaseModel):
    planned_calls: Count
    cached_calls: Count
    estimated_new_calls: Count
    as_of_date: date
    period: Period
    serpapi: SerpapiQuota
    live_enabled: bool
    needs_access_code: bool
    can_run: bool
    blocked_reason: BlockedReason | None = None


# --- Analyses: list / status (API.md section 3.2, 3.3) -------------------------------------------


class TopSignal(BaseModel):
    aspect: str
    impact: ImpactLevel


class AnalysisListItem(BaseModel):
    id: UUID
    brand: str
    product: str | None = None
    status: AnalysisStatus
    created_at: datetime
    top_signal: TopSignal | None = None


class ListAnalysesResponse(BaseModel):
    items: list[AnalysisListItem]


class AnalysisStatusResponse(BaseModel):
    """`getAnalysis`: lightweight status, polled every 2 s. Terminal: completed, partial, failed."""

    id: UUID
    status: AnalysisStatus
    stage: AnalysisStage | None = None
    progress: Percent
    brands: list[BrandRef]
    product: str | None = None
    period: Period
    warnings: list[Warning] = Field(default_factory=list)
    serp_calls_used: Count
    serp_calls_budget: Count
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


# --- Dashboard (API.md section 3.4) --------------------------------------------------------------


class DashboardAnalysis(BaseModel):
    id: UUID
    status: AnalysisStatus
    product: str | None = None
    as_of_date: date
    live_run: bool
    period: Period
    warnings: list[Warning] = Field(default_factory=list)


class GrowthSampleSize(BaseModel):
    """Growth sources only (news and web with reliable dates)."""

    current: Count
    baseline: Count


class HealthScores(BaseModel):
    overall: Percent
    sentiment: Percent
    engagement: Percent  # proxy; the UI marks it lower confidence
    risk: Percent  # inverted: 100 = no risk
    trend: Percent
    formula_version: str


class SentimentDistribution(BaseModel):
    positive: Percent
    neutral: Percent
    negative: Percent


class AspectStat(BaseModel):
    aspect: str
    net_score: SignedPercent  # positive% - negative%
    mentions: Count
    positive: Percent
    neutral: Percent
    negative: Percent


class TopicCount(BaseModel):
    topic: str
    count: Count


class SearchInterestPoint(BaseModel):
    date: dt.date
    value: float


class SearchInterest(BaseModel):
    """`change_pct` and `series` may be empty/null when Trends data is missing."""

    change_pct: float | None = None
    series: list[SearchInterestPoint] = Field(default_factory=list)


class TargetBlock(BaseModel):
    brand: BrandRef
    sample_size: Count
    baseline_sample_size: Count
    growth_sample_size: GrowthSampleSize
    low_data: bool
    health: HealthScores
    sentiment: SentimentDistribution
    aspects: list[AspectStat]
    topics: list[TopicCount]
    source_mix: dict[SourceType, Count]
    search_interest: SearchInterest | None = None


class CompetitorBlock(BaseModel):
    """Current-window snapshot only. No `health`, no `topics` in the MVP."""

    brand: BrandRef
    sample_size: Count
    low_data: bool
    sentiment: SentimentDistribution
    aspects: list[AspectStat]
    search_interest: SearchInterest | None = None


class SignalBase(BaseModel):
    """Fields shared by the dashboard `signals[]` entry and `getSignal`."""

    id: UUID
    kind: SignalKind
    aspect: str
    growth: float
    impact: ImpactLevel
    confidence: Percent
    confidence_source: ConfidenceSource
    sources_count: Count
    source_types: list[SourceType]
    current_share: Fraction
    baseline_share: Fraction
    current_n: Count
    baseline_n: Count
    trend_corroborated: bool
    status: SignalStatus


class SignalSummary(SignalBase):
    """One entry of dashboard `signals[]`, sorted by score descending."""

    brand_id: UUID
    investigation_id: UUID | None = None


class DashboardResponse(BaseModel):
    analysis: DashboardAnalysis
    target: TargetBlock
    competitors: list[CompetitorBlock] = Field(default_factory=list)
    signals: list[SignalSummary] = Field(default_factory=list)


# --- Mentions (API.md section 3.5) ---------------------------------------------------------------


class MentionAspect(BaseModel):
    aspect: str
    sentiment: Sentiment
    clause: str  # the analyzed text that produced the sentiment


class MentionItem(BaseModel):
    id: UUID
    source: Source
    sentiment: Sentiment
    aspects: list[MentionAspect] = Field(default_factory=list)


class ListMentionsResponse(BaseModel):
    items: list[MentionItem]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1, le=100)]
    total: Count


# --- Signals (API.md section 3.6) ----------------------------------------------------------------


class ScoreComponents(BaseModel):
    growth: Fraction
    frequency: Fraction
    cross_source: Fraction
    sentiment_impact: Fraction


class InvestigationRef(BaseModel):
    id: UUID
    status: InvestigationStatus


class SignalDetail(SignalBase):
    """`getSignal`. Follows the API.md 3.6 example: `brand` (not `brand_id`) and
    `latest_investigation` (not `investigation_id`)."""

    analysis_id: UUID
    brand: BrandRef
    score: Fraction
    score_components: ScoreComponents
    latest_investigation: InvestigationRef | None = None


# --- Investigations (API.md section 3.7-3.9) ------------------------------------------------------


class InvestigateSignalResponse(BaseModel):
    investigation_id: UUID
    status: InvestigationStatus
    reused: bool
    poll_url: str


class InvestigationStepInfo(BaseModel):
    key: InvestigationStep
    label: str
    state: StepState


class Finding(BaseModel):
    text: str
    evidence_ids: list[UUID] = Field(default_factory=list)


class Scope(BaseModel):
    verdict: ScopeVerdict
    ratio: float | None = (
        None  # brand share / median competitor share; null when `unknown`
    )
    explanation: str


class ConfidenceFactors(BaseModel):
    independence: Fraction
    agreement: Fraction
    signal_strength: Fraction
    recency: Fraction
    consistency: Fraction


class InvestigationConfidence(BaseModel):
    score: Percent
    label: ConfidenceLabel
    factors: ConfidenceFactors

    @model_validator(mode="after")
    def _label_matches_score(self) -> Self:
        expected = confidence_label(self.score)
        if self.label != expected:
            raise ValueError(f"label must be '{expected.value}' for score {self.score}")
        return self


class SourceCoverage(BaseModel):
    source_type: (
        CoverageSourceType  # includes `trends` only with search-interest corroboration
    )
    supporting: Count


class ReportSearchInterest(BaseModel):
    keyword: str
    change_pct: float | None = None


class ComparisonRow(BaseModel):
    brand: BrandRef
    positive_pct: Percent
    negative_pct: Percent
    aspect_negative_share: Fraction
    level: ImpactLevel
    search_interest_change_pct: float | None = None


class CompetitorComparison(BaseModel):
    aspect: str
    rows: list[ComparisonRow]


class Recommendation(BaseModel):
    id: UUID
    priority: Priority
    title: str
    action: str
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    timeframe: str


class InvestigationReport(BaseModel):
    generated_by: GeneratedBy
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    scope: Scope
    confidence: InvestigationConfidence
    source_coverage: list[SourceCoverage] = Field(default_factory=list)
    search_interest: ReportSearchInterest | None = None
    competitor_comparison: CompetitorComparison | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    disclaimer: str


class InvestigationResponse(BaseModel):
    """`getInvestigation`. `report` is null until `completed`; `error` is user-safe on `failed`."""

    id: UUID
    signal_id: UUID
    analysis_id: UUID
    status: InvestigationStatus
    step: InvestigationStep
    steps: list[InvestigationStepInfo] = Field(default_factory=list)
    report: InvestigationReport | None = None
    error: str | None = None


class EvidenceItem(BaseModel):
    id: UUID
    stance: Stance
    relevance: Fraction
    note: str | None = None
    rank: Annotated[int, Field(ge=1)]
    source: Source


class EvidenceCounts(BaseModel):
    supports: Count
    contradicts: Count
    neutral: Count


class ListEvidenceResponse(BaseModel):
    items: list[EvidenceItem]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1, le=100)]
    total: Count
    counts: EvidenceCounts


# --- Usage (API.md section 3.12) -----------------------------------------------------------------


class UsageSerpapi(SerpapiQuota):
    live_enabled: bool


class UsageGroq(BaseModel):
    configured: bool
    calls_today: Count
    model: str | None = None


class AnalysesToday(BaseModel):
    used: Count
    limit: Count


class UsageResponse(BaseModel):
    month: Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    serpapi: UsageSerpapi
    groq: UsageGroq
    analyses_today: AnalysesToday


# --- Health (API.md section 3.10) ----------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "unavailable"]
    nlp: Literal["ok", "loading", "unavailable"]
    serpapi_configured: bool
    live_serpapi_enabled: bool
    groq_configured: bool
    demo_mode: bool
