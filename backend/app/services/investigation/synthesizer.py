from app.services.llm.fallback import fallback_report
from app.services.llm.service import LLMService


def synthesize(signal, evidence, confidence, llm: LLMService):
    base = f"Signal: {signal.aspect}; score={signal.signal_score:.2f}; evidence IDs are authoritative."
    prompt = (
        base
        + " Return JSON with summary, findings (text,evidence_ids), scope, recommendations. Cite only supplied evidence IDs."
    )
    try:
        data = llm.complete_json(
            prompt,
            system="You are a cautious brand intelligence analyst. Never invent evidence IDs or facts. Use association language, not causation.",
        )
        valid = {str(e.id) for e in evidence}
        data["generated_by"] = "llm"
        data["findings"] = [
            f
            for f in data.get("findings", [])
            if all(str(x) in valid for x in f.get("evidence_ids", []))
        ]
        data["recommendations"] = [
            r
            for r in data.get("recommendations", [])
            if all(str(x) in valid for x in r.get("evidence_ids", []))
        ]
        data["confidence"] = confidence
        data.setdefault("source_coverage", [])
        data.setdefault("search_interest", None)
        data.setdefault("competitor_comparison", None)
        data.setdefault(
            "disclaimer", "This report describes association, not causation."
        )
        return data
    except Exception:  # noqa: BLE001 - fallback report handles any LLM failure (network, parsing, bad output)
        return fallback_report(signal, evidence, confidence)
