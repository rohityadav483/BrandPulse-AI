from app.schemas.api import GeneratedBy


def fallback_report(signal, evidence, confidence):
    aspect = signal.aspect
    if not evidence:
        summary = f"The investigation is inconclusive because no usable evidence was collected for the {aspect} signal."
        return {
            "generated_by": GeneratedBy.fallback.value,
            "summary": summary,
            "findings": [],
            "scope": {
                "verdict": "unknown",
                "ratio": None,
                "explanation": "No usable evidence was available.",
            },
            "confidence": confidence,
            "source_coverage": [],
            "search_interest": None,
            "competitor_comparison": None,
            "recommendations": [],
            "disclaimer": "This report uses deterministic fallback logic because the LLM was unavailable or produced invalid output.",
        }
    supports = sum(e.stance == "supports" for e in evidence)
    contradicts = sum(e.stance == "contradicts" for e in evidence)
    summary = f"Evidence shows an emerging {aspect} issue associated with the detected signal: {supports} supporting source(s) and {contradicts} contradicting source(s) were found."
    ids = [str(e.id) for e in evidence[:5]]
    return {
        "generated_by": GeneratedBy.fallback.value,
        "summary": summary,
        "findings": [
            {
                "text": f"The collected evidence supports an association between the {aspect} issue and the signal.",
                "evidence_ids": ids,
            }
        ],
        "scope": {
            "verdict": "inconclusive",
            "ratio": None,
            "explanation": "Competitor scope comparison is not available in Phase 7 without competitor evidence.",
        },
        "confidence": confidence,
        "source_coverage": [],
        "search_interest": None,
        "competitor_comparison": None,
        "recommendations": [],
        "disclaimer": "This report describes association, not causation. It uses deterministic fallback logic because the LLM was unavailable or produced invalid output.",
    }
