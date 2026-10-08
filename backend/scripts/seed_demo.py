"""Seed the deterministic Samsung demo scenario into PostgreSQL.

This creates a small DB-backed copy of the golden scenario using fixed IDs, so the
normal dashboard/signal/investigation routes can be exercised without SerpApi or Groq.
Usage: python backend/scripts/seed_demo.py [--fixture contracts/golden/samsung_battery.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import date, datetime
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.content_item import ContentItemRow
from app.db.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    BrandRole,
    ContentPurpose,
    DateConfidence,
    ImpactLevel,
    SignalKind,
    SignalStatus,
    SourceType,
    WindowKind,
)
from app.db.models.investigation import Evidence, Investigation
from app.db.models.phase5 import BrandSnapshot, Signal, TrendPoint
from app.db.models.recommendation import Recommendation
from app.db.session import get_engine

DEFAULT_FIXTURE = ROOT / "contracts" / "golden" / "samsung_battery.json"

AID = uuid.UUID("00000000-0000-4000-8000-000000000001")
SAMSUNG = uuid.UUID("00000000-0000-4000-8000-000000000010")
APPLE = uuid.UUID("00000000-0000-4000-8000-000000000011")
ONEPLUS = uuid.UUID("00000000-0000-4000-8000-000000000012")
SID = uuid.UUID("00000000-0000-4000-8000-000000000020")
IID = uuid.UUID("00000000-0000-4000-8000-000000000030")


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-4000-8000-{n:012d}")


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def content_row(aid, bid, cid, source_type, engine, title, url, window, query, published_at, purpose=ContentPurpose.collection):
    return ContentItemRow(
        id=cid, analysis_id=aid, brand_id=bid, purpose=purpose, window=window,
        source_type=source_type, engine=engine, url=url, url_hash=sha(url),
        domain=url.split('/')[2], title=title, snippet=title, author=None,
        published_at=published_at, date_confidence=DateConfidence.exact,
        query=query, item_metadata={}, content_hash=sha(title + url),
        dup_group=None, serp_cache_key=None, collected_at=datetime(2026, 8, 10, 10, 0),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    args = parser.parse_args()
    settings = Settings()
    url = settings.database_url or settings.database_url_direct
    if not url:
        raise SystemExit("DATABASE_URL or DATABASE_URL_DIRECT is required")
    data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    dashboard = data["dashboard"]
    signal = data["signal_detail"]
    investigation = data["investigation"]
    evidence = data["evidence"]
    period = dashboard["analysis"]["period"]
    engine = get_engine(url)

    with Session(engine) as s, s.begin():
        # Fixed IDs make the script repeatable. CASCADE removes dependent analysis rows.
        s.execute(delete(Analysis).where(Analysis.id == AID))
        for bid, name in ((SAMSUNG, "Samsung"), (APPLE, "Apple"), (ONEPLUS, "OnePlus")):
            if s.get(Brand, bid) is None:
                s.add(Brand(id=bid, name=name, normalized_name=name.casefold()))
        s.flush()

        s.add(Analysis(
            id=AID, brand_id=SAMSUNG, product=dashboard["analysis"]["product"],
            category="consumer_electronics", period_days=30,
            as_of_date=date.fromisoformat(dashboard["analysis"]["as_of_date"]),
            current_start=date.fromisoformat(period["current_start"]), current_end=date.fromisoformat(period["current_end"]),
            baseline_start=date.fromisoformat(period["baseline_start"]), baseline_end=date.fromisoformat(period["baseline_end"]),
            status=AnalysisStatus.completed, stage=AnalysisStage.done, progress=100,
            warnings=dashboard["analysis"]["warnings"], serp_calls_used=0, serp_calls_budget=12, live_run=False,
        ))
        s.add_all([
            AnalysisBrand(analysis_id=AID, brand_id=SAMSUNG, role=BrandRole.target),
            AnalysisBrand(analysis_id=AID, brand_id=APPLE, role=BrandRole.competitor),
            AnalysisBrand(analysis_id=AID, brand_id=ONEPLUS, role=BrandRole.competitor),
        ])

        for idx, window in enumerate((WindowKind.current, WindowKind.baseline)):
            count = dashboard["target"]["growth_sample_size"]["current" if window is WindowKind.current else "baseline"]
            day = date.fromisoformat(period["current_end" if window is WindowKind.current else "baseline_end"])
            for n in range(count):
                cid = uid(1000 + idx * 100 + n)
                url2 = f"https://demo.example/samsung/{idx}/{n}"
                s.add(content_row(AID, SAMSUNG, cid, SourceType.web, "google", f"Samsung demo mention {idx}-{n}", url2, window, "Samsung Galaxy S25 Ultra", datetime.combine(day, datetime.min.time())))
        for bid, name, count in ((APPLE, "Apple", 18), (ONEPLUS, "OnePlus", 15)):
            for n in range(count):
                cid = uid((20 if bid == APPLE else 40) * 100 + n)
                url2 = f"https://demo.example/{name.casefold()}/{n}"
                s.add(content_row(AID, bid, cid, SourceType.web, "google", f"{name} demo mention {n}", url2, WindowKind.current, name, datetime(2026, 8, 10, 10, 0)))

        for idx, item in enumerate(evidence["items"], 40):
            src = item["source"]
            cid = uid(100 + idx)
            url2 = src["url"]
            s.add(content_row(AID, SAMSUNG, cid, SourceType(src["source_type"]), {
                "forum": "google_forums", "web": "google", "news": "google_news", "youtube": "youtube"
            }[src["source_type"]], src["title"], url2, None, "Samsung battery", datetime.fromisoformat(src["published_at"]), ContentPurpose.investigation))

        for bid, block in ((SAMSUNG, dashboard["target"]), (APPLE, dashboard["competitors"][0]), (ONEPLUS, dashboard["competitors"][1])):
            s.add(BrandSnapshot(
                analysis_id=AID, brand_id=bid, sample_size=block["sample_size"],
                baseline_sample_size=dashboard["target"]["baseline_sample_size"] if bid == SAMSUNG else 0,
                sentiment_dist=block["sentiment"], aspect_scores=block["aspects"], topic_counts=dashboard["target"]["topics"] if bid == SAMSUNG else [],
                source_mix=dashboard["target"]["source_mix"] if bid == SAMSUNG else {}, health=dashboard["target"]["health"] if bid == SAMSUNG else {"overall":70,"sentiment":80,"engagement":70,"risk":80,"trend":70,"formula_version":"v1"},
                interest_change_pct=block.get("search_interest", {}).get("change_pct"), low_data=block["low_data"],
            ))
        for tp in dashboard["target"]["search_interest"]["series"]:
            s.add(TrendPoint(analysis_id=AID, brand_id=SAMSUNG, keyword="Samsung", date=date.fromisoformat(tp["date"]), value=tp["value"]))
        s.add(Signal(
            id=SID, analysis_id=AID, brand_id=SAMSUNG, kind=SignalKind(signal["kind"]), aspect=signal["aspect"],
            baseline_n=signal["baseline_n"], baseline_total=signal["baseline_n"] + 25, current_n=signal["current_n"], current_total=31,
            baseline_share=signal["baseline_share"], current_share=signal["current_share"], growth=signal["growth"], components=signal["score_components"],
            signal_score=signal["score"], impact=ImpactLevel(signal["impact"]), signal_confidence=signal["confidence"], sources_count=signal["sources_count"],
            source_types=signal["source_types"], trend_corroborated=signal["trend_corroborated"], status=SignalStatus.investigated,
        ))
        s.add(Investigation(id=IID, signal_id=SID, analysis_id=AID, status="completed", step="done", steps=investigation["steps"], report=investigation["report"], error=None))
        for item in evidence["items"]:
            eid = uuid.UUID(item["id"])
            cid = uid(100 + int(eid.int % 100))
            s.add(Evidence(id=eid, investigation_id=IID, content_id=cid, stance=item["stance"], relevance=item["relevance"], note=item["note"], rank=item["rank"]))
        for rec in investigation["report"]["recommendations"]:
            s.add(Recommendation(id=uuid.UUID(rec["id"]), investigation_id=IID, priority=rec["priority"], title=rec["title"], action=rec["action"], rationale=rec["rationale"], evidence_ids=rec["evidence_ids"], timeframe=rec["timeframe"]))

    print(f"Seeded demo analysis {AID}, signal {SID}, investigation {IID}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
