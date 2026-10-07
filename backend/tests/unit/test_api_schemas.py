"""API schemas vs docs/API.md: every documented example validates and round-trips unchanged."""

import pytest
from pydantic import ValidationError

from app.schemas import api


def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


PERIOD = {
    "current_start": "2026-09-06",
    "current_end": "2026-10-05",
    "baseline_start": "2026-08-07",
    "baseline_end": "2026-09-05",
}
SAMSUNG = {"id": uid(1), "name": "Samsung", "role": "target"}
APPLE = {"id": uid(2), "name": "Apple", "role": "competitor"}


def source(**over):
    base = {
        "source_type": "forum",
        "domain": "reddit.com",
        "url": "https://example.com/a",
        "title": "Battery drain after update",
        "snippet": "Battery drops fast.",
        "author": "someone",
        "published_at": "2026-10-01T08:00:00Z",
        "date_confidence": "exact",
        "collected_at": "2026-10-06T09:12:00Z",
    }
    return {**base, **over}


SIGNAL_COMMON = {
    "kind": "aspect_negative_spike",
    "aspect": "battery",
    "growth": 3.3,
    "impact": "high",
    "confidence": 87,
    "confidence_source": "signal",
    "sources_count": 4,
    "source_types": ["youtube", "forum", "web", "news"],
    "current_share": 0.29,
    "baseline_share": 0.07,
    "current_n": 9,
    "baseline_n": 2,
    "trend_corroborated": True,
    "status": "detected",
}

EXAMPLES: dict[str, tuple[type, dict]] = {
    "create_response": (
        api.CreateAnalysisResponse,
        {"id": uid(3), "status": "queued", "poll_url": f"/api/v1/analyses/{uid(3)}"},
    ),
    "list_analyses": (
        api.ListAnalysesResponse,
        {
            "items": [
                {
                    "id": uid(3),
                    "brand": "Samsung",
                    "product": "Galaxy S25 Ultra",
                    "status": "completed",
                    "created_at": "2026-10-06T09:10:00Z",
                    "top_signal": {"aspect": "battery", "impact": "high"},
                },
                {
                    "id": uid(4),
                    "brand": "Apple",
                    "product": None,
                    "status": "failed",
                    "created_at": "2026-10-05T09:10:00Z",
                    "top_signal": None,
                },
            ]
        },
    ),
    "analysis_status": (
        api.AnalysisStatusResponse,
        {
            "id": uid(3),
            "status": "running",
            "stage": "analyzing",
            "progress": 62,
            "brands": [SAMSUNG, APPLE],
            "product": "Galaxy S25 Ultra",
            "period": PERIOD,
            "warnings": [
                {
                    "code": "serpapi_engine_failed",
                    "message": "Google Forums returned no usable results.",
                    "stage": "collecting",
                }
            ],
            "serp_calls_used": 7,
            "serp_calls_budget": 12,
            "error": None,
            "created_at": "2026-10-06T09:10:00Z",
            "finished_at": None,
        },
    ),
    "dashboard": (
        api.DashboardResponse,
        {
            "analysis": {
                "id": uid(3),
                "status": "completed",
                "product": "Galaxy S25 Ultra",
                "as_of_date": "2026-08-10",
                "live_run": False,
                "period": PERIOD,
                "warnings": [],
            },
            "target": {
                "brand": SAMSUNG,
                "sample_size": 64,
                "baseline_sample_size": 41,
                "growth_sample_size": {"current": 31, "baseline": 27},
                "low_data": False,
                "health": {
                    "overall": 73,
                    "sentiment": 72,
                    "engagement": 81,
                    "risk": 64,
                    "trend": 76,
                    "formula_version": "v1",
                },
                "sentiment": {"positive": 62, "neutral": 21, "negative": 17},
                "aspects": [
                    {
                        "aspect": "battery",
                        "net_score": -48,
                        "mentions": 14,
                        "positive": 12,
                        "neutral": 28,
                        "negative": 60,
                    }
                ],
                "topics": [{"topic": "battery", "count": 14}],
                "source_mix": {"web": 18, "news": 16, "youtube": 20, "forum": 10},
                "search_interest": {
                    "change_pct": 31,
                    "series": [{"date": "2026-09-06", "value": 52}],
                },
            },
            "competitors": [
                {
                    "brand": APPLE,
                    "sample_size": 38,
                    "low_data": False,
                    "sentiment": {"positive": 74, "neutral": 15, "negative": 11},
                    "aspects": [
                        {
                            "aspect": "battery",
                            "net_score": 20,
                            "mentions": 18,
                            "positive": 40,
                            "neutral": 40,
                            "negative": 20,
                        }
                    ],
                    "search_interest": {"change_pct": 8, "series": []},
                }
            ],
            "signals": [
                {
                    **SIGNAL_COMMON,
                    "id": uid(5),
                    "brand_id": uid(1),
                    "investigation_id": None,
                }
            ],
        },
    ),
    "mentions": (
        api.ListMentionsResponse,
        {
            "items": [
                {
                    "id": uid(6),
                    "source": source(
                        source_type="youtube", date_confidence="approximate"
                    ),
                    "sentiment": "negative",
                    "aspects": [
                        {
                            "aspect": "battery",
                            "sentiment": "negative",
                            "clause": "battery life is terrible since the update",
                        }
                    ],
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 14,
        },
    ),
    "signal_detail": (
        api.SignalDetail,
        {
            **SIGNAL_COMMON,
            "id": uid(5),
            "analysis_id": uid(3),
            "brand": SAMSUNG,
            "score": 0.79,
            "score_components": {
                "growth": 0.74,
                "frequency": 0.8,
                "cross_source": 1.0,
                "sentiment_impact": 0.6,
            },
            "latest_investigation": {"id": uid(7), "status": "completed"},
        },
    ),
    "investigate_response": (
        api.InvestigateSignalResponse,
        {
            "investigation_id": uid(7),
            "status": "queued",
            "reused": False,
            "poll_url": f"/api/v1/investigations/{uid(7)}",
        },
    ),
    "investigation_running": (
        api.InvestigationResponse,
        {
            "id": uid(7),
            "signal_id": uid(5),
            "analysis_id": uid(3),
            "status": "running",
            "step": "collecting_evidence",
            "steps": [
                {
                    "key": "generating_queries",
                    "label": "Generating investigation queries",
                    "state": "done",
                },
                {
                    "key": "collecting_evidence",
                    "label": "Collecting independent evidence",
                    "state": "active",
                },
                {
                    "key": "scoring_evidence",
                    "label": "Cross-checking sources",
                    "state": "pending",
                },
            ],
            "report": None,
            "error": None,
        },
    ),
    "investigation_completed": (
        api.InvestigationResponse,
        {
            "id": uid(7),
            "signal_id": uid(5),
            "analysis_id": uid(3),
            "status": "completed",
            "step": "done",
            "steps": [],
            "report": {
                "generated_by": "llm",
                "summary": "The rise in battery complaints appears to be associated with updates.",
                "findings": [
                    {
                        "text": "Forum threads report drain.",
                        "evidence_ids": [uid(8), uid(9)],
                    },
                ],
                "scope": {
                    "verdict": "brand_specific",
                    "ratio": 2.4,
                    "explanation": "Battery-negative share is 2.4x the competitor median.",
                },
                "confidence": {
                    "score": 86,
                    "label": "high",
                    "factors": {
                        "independence": 0.9,
                        "agreement": 0.85,
                        "signal_strength": 0.79,
                        "recency": 0.9,
                        "consistency": 0.8,
                    },
                },
                "source_coverage": [
                    {"source_type": "youtube", "supporting": 5},
                    {"source_type": "trends", "supporting": 1},
                ],
                "search_interest": {"keyword": "Samsung battery", "change_pct": 31},
                "competitor_comparison": {
                    "aspect": "battery",
                    "rows": [
                        {
                            "brand": SAMSUNG,
                            "positive_pct": 62,
                            "negative_pct": 17,
                            "aspect_negative_share": 0.28,
                            "level": "high",
                            "search_interest_change_pct": 31,
                        },
                        {
                            "brand": APPLE,
                            "positive_pct": 74,
                            "negative_pct": 11,
                            "aspect_negative_share": 0.06,
                            "level": "low",
                            "search_interest_change_pct": 8,
                        },
                    ],
                },
                "recommendations": [
                    {
                        "id": uid(10),
                        "priority": "high",
                        "title": "Investigate battery performance after the latest update",
                        "action": "Review the update changelog.",
                        "rationale": "Complaints cluster after the update.",
                        "evidence_ids": [uid(8)],
                        "timeframe": "next 7 days",
                    }
                ],
                "disclaimer": "Findings show association, not proven causation.",
            },
            "error": None,
        },
    ),
    "evidence": (
        api.ListEvidenceResponse,
        {
            "items": [
                {
                    "id": uid(8),
                    "stance": "supports",
                    "relevance": 0.91,
                    "note": "Reports battery drain after the update.",
                    "rank": 1,
                    "source": source(),
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 18,
            "counts": {"supports": 14, "contradicts": 2, "neutral": 2},
        },
    ),
    "estimate": (
        api.EstimateAnalysisResponse,
        {
            "planned_calls": 11,
            "cached_calls": 4,
            "estimated_new_calls": 7,
            "as_of_date": "2026-08-10",
            "period": PERIOD,
            "serpapi": {"limit": 250, "used": 83, "remaining": 167, "reserve": 20},
            "live_enabled": True,
            "needs_access_code": True,
            "can_run": True,
            "blocked_reason": None,
        },
    ),
    "usage": (
        api.UsageResponse,
        {
            "month": "2026-10",
            "serpapi": {
                "limit": 250,
                "used": 83,
                "remaining": 167,
                "reserve": 20,
                "live_enabled": True,
            },
            "groq": {
                "configured": True,
                "calls_today": 6,
                "model": "configured-model-id",
            },
            "analyses_today": {"used": 1, "limit": 3},
        },
    ),
    "health": (
        api.HealthResponse,
        {
            "status": "ok",
            "version": "0.1.0",
            "database": "ok",
            "nlp": "ok",
            "serpapi_configured": True,
            "live_serpapi_enabled": False,
            "groq_configured": True,
            "demo_mode": False,
        },
    ),
    "error": (
        api.ErrorResponse,
        {
            "error": {
                "code": "analysis_not_ready",
                "message": "Analysis is still running.",
                "details": {"status": "running", "stage": "analyzing"},
            }
        },
    ),
}


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_documented_example_validates_and_round_trips(name):
    model, example = EXAMPLES[name]
    parsed = model.model_validate(example)
    assert parsed.model_dump(mode="json") == example


# --- createAnalysis / estimateAnalysis request rules (API.md section 3.1) -----------------------


def test_request_defaults():
    req = api.CreateAnalysisRequest(brand="Samsung")
    assert req.product is None
    assert req.competitors == []
    assert req.category == "consumer_electronics"
    assert req.period_days == 30
    assert req.as_of_date is None


def test_request_full_example():
    req = api.CreateAnalysisRequest.model_validate(
        {
            "brand": "Samsung",
            "product": "Galaxy S25 Ultra",
            "competitors": ["Apple", "OnePlus"],
            "category": "consumer_electronics",
            "period_days": 30,
            "as_of_date": "2026-08-10",
        }
    )
    assert req.competitors == ["Apple", "OnePlus"]
    assert str(req.as_of_date) == "2026-08-10"


def test_request_trims_text():
    req = api.CreateAnalysisRequest(
        brand="  Samsung  ", product="  S25  ", competitors=[" Apple "]
    )
    assert (req.brand, req.product, req.competitors) == ("Samsung", "S25", ["Apple"])


def test_blank_product_becomes_none():
    assert api.CreateAnalysisRequest(brand="Samsung", product="   ").product is None


@pytest.mark.parametrize("brand", ["", "   ", "x" * 81])
def test_brand_must_be_1_to_80_chars_after_trim(brand):
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand=brand)


def test_brand_80_chars_ok():
    assert api.CreateAnalysisRequest(brand="x" * 80).brand == "x" * 80


def test_product_max_80():
    api.CreateAnalysisRequest(brand="A", product="p" * 80)
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", product="p" * 81)


def test_more_than_two_competitors_rejected():
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", competitors=["B", "C", "D"])


def test_three_competitors_rejected_even_if_duplicates_would_collapse():
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", competitors=["B", "b", "C"])


@pytest.mark.parametrize("bad", [[""], ["  "], ["x" * 81]])
def test_competitor_names_must_be_1_to_80_chars(bad):
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", competitors=bad)


def test_competitors_dedupe_case_insensitive_and_drop_target():
    req = api.CreateAnalysisRequest(brand="Samsung", competitors=["samsung", "Apple"])
    assert req.competitors == ["Apple"]
    req = api.CreateAnalysisRequest(brand="Samsung", competitors=["Apple", "APPLE"])
    assert req.competitors == ["Apple"]


@pytest.mark.parametrize("days", [7, 14, 30])
def test_period_days_allowed(days):
    assert api.CreateAnalysisRequest(brand="A", period_days=days).period_days == days


@pytest.mark.parametrize("days", [0, 1, 10, 31, 60])
def test_period_days_rejected(days):
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", period_days=days)


def test_category_values():
    assert (
        api.CreateAnalysisRequest(brand="A", category="generic").category == "generic"
    )
    with pytest.raises(ValidationError):
        api.CreateAnalysisRequest(brand="A", category="fashion")


# --- strictness of response shapes ---------------------------------------------------------------


def test_confidence_label_must_match_score():
    names = ("independence", "agreement", "signal_strength", "recency", "consistency")
    factors = dict.fromkeys(names, 0.5)
    api.InvestigationConfidence(score=39, label="low", factors=factors)
    api.InvestigationConfidence(score=40, label="medium", factors=factors)
    api.InvestigationConfidence(score=70, label="high", factors=factors)
    with pytest.raises(ValidationError):
        api.InvestigationConfidence(score=86, label="low", factors=factors)


@pytest.mark.parametrize(
    ("model", "patch"),
    [
        (api.AnalysisStatusResponse, {"progress": 101}),
        (api.AnalysisStatusResponse, {"status": "done"}),
        (api.AnalysisStatusResponse, {"stage": "finished"}),
        (api.UsageResponse, {"month": "2026-13"}),
        (api.UsageResponse, {"month": "Oct 2026"}),
        (api.ListMentionsResponse, {"page": 0}),
        (api.ListMentionsResponse, {"page_size": 101}),
        (api.EstimateAnalysisResponse, {"blocked_reason": "no_money"}),
        (api.HealthResponse, {"nlp": "maybe"}),
    ],
)
def test_out_of_contract_values_rejected(model, patch):
    key = {
        api.AnalysisStatusResponse: "analysis_status",
        api.UsageResponse: "usage",
        api.ListMentionsResponse: "mentions",
        api.EstimateAnalysisResponse: "estimate",
        api.HealthResponse: "health",
    }[model]
    with pytest.raises(ValidationError):
        model.model_validate({**EXAMPLES[key][1], **patch})


def test_percent_fields_are_bounded():
    base = EXAMPLES["dashboard"][1]["target"]["sentiment"]
    with pytest.raises(ValidationError):
        api.SentimentDistribution.model_validate({**base, "positive": 101})
    with pytest.raises(ValidationError):
        api.AspectStat(
            aspect="a", net_score=-101, mentions=1, positive=0, neutral=0, negative=0
        )


def test_share_fields_are_fractions():
    with pytest.raises(ValidationError):
        api.SignalSummary.model_validate(
            {**SIGNAL_COMMON, "id": uid(5), "brand_id": uid(1), "current_share": 29}
        )


def test_source_type_rejects_trends_but_coverage_accepts_it():
    with pytest.raises(ValidationError):
        api.Source.model_validate(source(source_type="trends"))
    assert api.SourceCoverage(source_type="trends", supporting=1).supporting == 1


def test_source_dates_can_be_unknown():
    src = api.Source.model_validate(
        source(published_at=None, date_confidence="unknown")
    )
    assert src.published_at is None


def test_source_mix_keys_are_source_types():
    base = EXAMPLES["dashboard"][1]["target"]
    api.TargetBlock.model_validate({**base, "source_mix": {"web": 1}})
    with pytest.raises(ValidationError):
        api.TargetBlock.model_validate({**base, "source_mix": {"twitter": 1}})


def test_competitor_block_has_no_health_or_topics():
    assert "health" not in api.CompetitorBlock.model_fields
    assert "topics" not in api.CompetitorBlock.model_fields


def test_report_may_be_inconclusive_with_no_findings():
    report = EXAMPLES["investigation_completed"][1]["report"]
    slim = {
        **report,
        "findings": [],
        "recommendations": [],
        "source_coverage": [],
        "search_interest": None,
        "competitor_comparison": None,
        "scope": {
            "verdict": "unknown",
            "ratio": None,
            "explanation": "No competitor data.",
        },
        "confidence": {**report["confidence"], "score": 20, "label": "low"},
    }
    parsed = api.InvestigationReport.model_validate(slim)
    assert parsed.confidence.label == "low"
    assert parsed.scope.ratio is None
