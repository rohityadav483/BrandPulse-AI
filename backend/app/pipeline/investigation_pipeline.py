import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.content_item import ContentItemRow
from app.db.models.enums import SignalStatus
from app.db.models.investigation import Evidence, Investigation
from app.db.models.phase5 import Signal
from app.db.repositories.investigation import EvidenceRepository
from app.db.repositories.recommendation import RecommendationRepository
from app.services.competitors.comparison import compare_aspect
from app.services.competitors.scope import scope_verdict
from app.services.competitors.snapshot import build_competitor_snapshot
from app.services.investigation.confidence import compute_confidence, derive_confidence_inputs
from app.services.investigation.evidence_collector import collect_existing
from app.services.investigation.query_gen import generate_queries
from app.services.investigation.synthesizer import PROMPT_VERSION, TASK, synthesize
from app.services.llm.audit import LLMCallRecorder
from app.services.llm.limiter import shared_limiter
from app.services.llm.provider_groq import GroqProvider
from app.services.llm.service import LLMService
from app.services.recommendations.generator import generate_recommendations

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SignalCtx:
    """Plain copy of the Signal columns the pipeline needs.

    ORM instances expire on commit and detach when their Session closes, so nothing
    downstream may read attributes from them. Services only use these four fields.
    """

    aspect: str
    signal_score: float
    signal_confidence: int
    impact: Any



def settle_signal_status(engine, signal_id: UUID) -> None:
    """Derive `Signal.status` from its investigations.

    active (queued/running) -> investigating; else any completed -> investigated;
    else detected. Called when an investigation starts, completes or fails. Never raises:
    a status-sync problem must not turn a finished investigation into a failed one.
    """
    try:
        with Session(engine) as s:
            sig = s.get(Signal, signal_id)
            if sig is None:
                return
            statuses = set(
                s.scalars(
                    select(Investigation.status).where(
                        Investigation.signal_id == signal_id
                    )
                ).all()
            )
            if statuses & {"queued", "running"}:
                sig.status = SignalStatus.investigating
            elif "completed" in statuses:
                sig.status = SignalStatus.investigated
            else:
                sig.status = SignalStatus.detected
            s.commit()
    except Exception:
        logger.exception("Could not update status of signal %s", signal_id)


def _steps(state):
    labels = {
        "generating_queries": "Generating investigation queries",
        "collecting_evidence": "Collecting evidence",
        "scoring_evidence": "Scoring evidence",
        "comparing_competitors": "Comparing competitors",
        "synthesizing": "Synthesizing report",
        "recommending": "Preparing recommendations",
        "done": "Done",
    }
    keys = list(labels)
    # `StepState` (API.md 3.8) is done / active / pending. The terminal `done` step is
    # itself complete, so once the pipeline reaches it nothing stays active.
    finished = state == "done"
    return [
        {
            "key": k,
            "label": labels[k],
            "state": "done"
            if finished or keys.index(k) < keys.index(state)
            else "active"
            if k == state
            else "pending",
        }
        for k in keys
    ]


def _set_step(engine, investigation_id: UUID, step: str) -> None:
    with Session(engine) as s:
        inv = s.get(Investigation, investigation_id)
        inv.step = step
        inv.steps = _steps(step)
        s.commit()


def run_investigation(investigation_id: UUID, settings: Settings):
    engine = __import__("app.db.session", fromlist=["get_engine"]).get_engine(
        settings.database_url or settings.database_url_direct
    )
    with Session(engine) as s:
        inv = s.get(Investigation, investigation_id)
        if not inv:
            return
        sig = s.get(Signal, inv.signal_id)
        analysis = s.get(Analysis, inv.analysis_id)
        brand = s.get(Brand, sig.brand_id) if sig else None
        if not sig or not analysis or not brand:
            return
        inv.status = "running"
        inv.step = "generating_queries"
        inv.steps = _steps("generating_queries")
        # Copy everything needed later while the instances are still live: commit()
        # expires them and leaving the `with` block detaches them.
        signal_id = sig.id
        analysis_id = analysis.id
        product = analysis.product
        as_of_date = analysis.as_of_date
        brand_id = brand.id
        brand_name = brand.name
        sig = _SignalCtx(
            aspect=sig.aspect,
            signal_score=float(sig.signal_score),
            signal_confidence=int(sig.signal_confidence),
            impact=sig.impact,
        )
        s.commit()
    settle_signal_status(engine, signal_id)
    try:
        generate_queries(brand_name, product, sig.aspect)
        _set_step(engine, investigation_id, "collecting_evidence")
        scored = collect_existing(engine, analysis_id, brand_id, sig.aspect, limit=20)
        _set_step(engine, investigation_id, "scoring_evidence")
        # Persist evidence only for existing content; this is cache-safe and spends zero SerpApi credits.
        repo = EvidenceRepository(engine)
        rows = []
        for rank, (item, relevance, stance) in enumerate(scored, 1):
            rows.append(
                {
                    "investigation_id": investigation_id,
                    "content_id": item.id,
                    "stance": stance,
                    "relevance": relevance,
                    "note": (item.snippet or item.title)[:500],
                    "rank": rank,
                }
            )
        repo.add_many(rows)
        _set_step(engine, investigation_id, "comparing_competitors")
        # Phase 8 competitor context is current-window and cache-safe: reuse stored snapshots/content.
        competitor_entries = []
        brand_refs = {}
        with Session(engine) as s:
            links = s.scalars(
                select(AnalysisBrand).where(AnalysisBrand.analysis_id == analysis_id)
            ).all()
            brands = {
                b.id: b
                for b in s.scalars(
                    select(Brand).where(Brand.id.in_([x.brand_id for x in links]))
                ).all()
            }
        for link in links:
            snap = build_competitor_snapshot(engine, analysis_id, link.brand_id)
            snap["brand_id"] = link.brand_id
            competitor_entries.append((link.role.value, snap))
            brand_refs[link.brand_id] = brands[link.brand_id].name
        target_entry = next(
            (x for role, x in competitor_entries if role == "target"), None
        )
        competitor_data = [x for role, x in competitor_entries if role != "target"][:2]
        scope = {
            "verdict": "unknown",
            "ratio": None,
            "explanation": "No competitor data available.",
        }
        comparison = None
        if target_entry and competitor_data:
            aspect_rows = [
                x for x in target_entry.get("aspects", []) if x["aspect"] == sig.aspect
            ]
            target_share = (aspect_rows[0]["negative"] / 100) if aspect_rows else None
            shares = []
            for x in competitor_data:
                row = next(
                    (a for a in x.get("aspects", []) if a["aspect"] == sig.aspect), None
                )
                if row:
                    shares.append(row["negative"] / 100)
            scope = scope_verdict(target_share, shares)
            refs = {
                bid: {
                    "id": bid,
                    "name": name,
                    "role": "competitor" if bid != brand_id else "target",
                }
                for bid, name in brand_refs.items()
            }
            comparison = compare_aspect(
                target_entry, competitor_data, sig.aspect, refs
            ).rows
        _set_step(engine, investigation_id, "synthesizing")
        with Session(engine) as s:
            evidence = list(
                s.scalars(
                    select(Evidence)
                    .where(Evidence.investigation_id == investigation_id)
                    .order_by(Evidence.rank)
                ).all()
            )
        # Compute independence from evidence source domains.
        with Session(engine) as s:
            content = (
                s.scalars(
                    select(ContentItemRow).where(
                        ContentItemRow.id.in_([e.content_id for e in evidence])
                    )
                ).all()
                if evidence
                else []
            )
        inputs = derive_confidence_inputs(evidence, {c.id: c for c in content}, as_of_date)
        conf = compute_confidence(signal_strength=sig.signal_score, **inputs)
        provider = (
            GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model)
            if settings.groq_configured
            else None
        )
        report = synthesize(
            sig,
            evidence,
            conf,
            LLMService(
                provider,
                settings.llm_max_calls_per_investigation,
                limiter=shared_limiter(settings.llm_max_concurrency),
                recorder=LLMCallRecorder(
                    engine,
                    task=TASK,
                    prompt_version=PROMPT_VERSION,
                    analysis_id=analysis_id,
                    investigation_id=investigation_id,
                ),
            ),
        )
        _set_step(engine, investigation_id, "recommending")
        # Deterministic Phase 8 recommendations are always evidence-linked.
        drafts = generate_recommendations(sig, evidence, scope, comparison)
        rec_rows = [
            {
                "investigation_id": investigation_id,
                "priority": d.priority,
                "title": d.title,
                "action": d.action,
                "rationale": d.rationale,
                "evidence_ids": [str(x) for x in d.evidence_ids],
                "timeframe": d.timeframe,
            }
            for d in drafts
        ]
        stored = RecommendationRepository(engine).add_many(rec_rows)
        report["scope"] = scope
        report["competitor_comparison"] = (
            {"aspect": sig.aspect, "rows": comparison} if comparison else None
        )
        report["recommendations"] = [
            {
                "id": r.id,
                # Recommendation.priority is a Text column: already a plain str.
                "priority": r.priority,
                "title": r.title,
                "action": r.action,
                "rationale": r.rationale,
                "evidence_ids": list(r.evidence_ids),
                "timeframe": r.timeframe,
            }
            for r in stored
        ]
        # The report lands in a JSONB column: UUIDs, enums and datetimes become JSON types.
        report = to_jsonable_python(report)
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.report = report
            inv.status = "completed"
            inv.step = "done"
            inv.steps = _steps("done")
            inv.finished_at = datetime.now(UTC)
            s.commit()
        settle_signal_status(engine, signal_id)
    except Exception:  # noqa: BLE001 - background pipeline job catches unexpected errors to record failure state
        logger.exception("Investigation %s failed", investigation_id)
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            if inv:
                inv.status = "failed"
                inv.error = "Investigation failed. Please try again."
                inv.finished_at = datetime.now(UTC)
                s.commit()
        settle_signal_status(engine, signal_id)
