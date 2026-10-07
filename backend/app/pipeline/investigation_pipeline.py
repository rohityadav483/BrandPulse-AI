from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.investigation import Investigation
from app.db.models.phase5 import Signal
from app.db.repositories.investigation import EvidenceRepository
from app.services.competitors.comparison import compare_aspect
from app.services.competitors.scope import scope_verdict
from app.services.competitors.snapshot import build_competitor_snapshot
from app.services.investigation.confidence import compute_confidence
from app.services.investigation.evidence_collector import collect_existing
from app.services.investigation.query_gen import generate_queries
from app.services.investigation.synthesizer import synthesize
from app.services.llm.provider_groq import GroqProvider
from app.services.llm.service import LLMService
from app.services.recommendations.generator import generate_recommendations


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
    return [
        {
            "key": k,
            "label": labels[k],
            "state": "completed"
            if keys.index(k) < keys.index(state)
            else "running"
            if k == state
            else "pending",
        }
        for k in keys
    ]


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
        s.commit()
    try:
        generate_queries(brand.name, analysis.product, sig.aspect)
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.step = "collecting_evidence"
            inv.steps = _steps("collecting_evidence")
            s.commit()
        scored = collect_existing(engine, analysis.id, brand.id, sig.aspect, limit=20)
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.step = "scoring_evidence"
            inv.steps = _steps("scoring_evidence")
            s.commit()
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
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.step = "comparing_competitors"
            inv.steps = _steps("comparing_competitors")
            s.commit()
        # Phase 8 competitor context is current-window and cache-safe: reuse stored snapshots/content.
        competitor_entries = []
        brand_refs = {}
        with Session(engine) as s:
            links = s.scalars(
                select(AnalysisBrand).where(AnalysisBrand.analysis_id == analysis.id)
            ).all()
            brands = {
                b.id: b
                for b in s.scalars(
                    select(Brand).where(Brand.id.in_([x.brand_id for x in links]))
                ).all()
            }
        for link in links:
            snap = build_competitor_snapshot(engine, analysis.id, link.brand_id)
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
                    "role": "competitor" if bid != brand.id else "target",
                }
                for bid, name in brand_refs.items()
            }
            comparison = compare_aspect(
                target_entry, competitor_data, sig.aspect, refs
            ).rows
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.step = "synthesizing"
            inv.steps = _steps("synthesizing")
            s.commit()
        with Session(engine) as s:
            evidence = (
                s.query(
                    __import__(
                        "app.db.models.investigation", fromlist=["Evidence"]
                    ).Evidence
                )
                .filter_by(investigation_id=investigation_id)
                .order_by(
                    __import__(
                        "app.db.models.investigation", fromlist=["Evidence"]
                    ).Evidence.rank
                )
                .all()
            )
        # Compute independence from evidence source domains.
        from app.db.models.content_item import ContentItemRow

        with Session(engine) as s:
            content = (
                s.query(ContentItemRow)
                .filter(ContentItemRow.id.in_([e.content_id for e in evidence]))
                .all()
                if evidence
                else []
            )
        domains = {c.domain for c in content}
        supporting = sum(e.stance == "supports" for e in evidence)
        contradicting = sum(e.stance == "contradicts" for e in evidence)
        agreement = supporting / max(1, supporting + contradicting)
        conf = compute_confidence(
            independence=min(1, len(domains) / 4),
            agreement=agreement,
            signal_strength=float(sig.signal_score),
            recency=0.8,
            consistency=agreement,
            independent_sources=len(domains),
        )
        provider = (
            GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model)
            if settings.groq_configured
            else None
        )
        report = synthesize(
            sig,
            evidence,
            conf,
            LLMService(provider, settings.llm_max_calls_per_investigation),
        )
        # Deterministic Phase 8 recommendations are always evidence-linked.
        drafts = generate_recommendations(sig, evidence, scope, comparison)
        from app.db.repositories.recommendation import RecommendationRepository

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
                "priority": r.priority.value,
                "title": r.title,
                "action": r.action,
                "rationale": r.rationale,
                "evidence_ids": [UUID(x) for x in r.evidence_ids],
                "timeframe": r.timeframe,
            }
            for r in stored
        ]
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            inv.report = report
            inv.status = "completed"
            inv.step = "done"
            inv.steps = _steps("done")
            inv.finished_at = datetime.now(UTC)
            s.commit()
    except Exception:  # noqa: BLE001 - background pipeline job catches unexpected errors to record failure state
        with Session(engine) as s:
            inv = s.get(Investigation, investigation_id)
            if inv:
                inv.status = "failed"
                inv.error = "Investigation failed. Please try again."
                inv.finished_at = datetime.now(UTC)
                s.commit()
