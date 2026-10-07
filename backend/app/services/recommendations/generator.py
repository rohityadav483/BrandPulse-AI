from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationDraft:
    priority: str
    title: str
    action: str
    rationale: str
    evidence_ids: list
    timeframe: str


def generate_recommendations(
    signal, evidence, scope: dict, comparison=None
) -> list[RecommendationDraft]:
    valid = [e.id for e in evidence]
    if not valid:
        return []
    high = str(getattr(signal, "impact", "low")) in {"high", "ImpactLevel.high"}
    priority = (
        "high"
        if high or getattr(signal, "signal_confidence", 0) >= 70
        else "medium"
        if getattr(signal, "signal_confidence", 0) >= 40
        else "low"
    )
    aspect = signal.aspect.replace("_", " ")
    verdict = scope.get("verdict", "unknown")
    if verdict == "brand_specific":
        action = f"Investigate and address the {aspect} issue in the next product/support review, prioritizing the recurring evidence above competitor levels."
        title = f"Address {aspect} complaints"
    elif verdict == "industry_wide":
        action = f"Benchmark the {aspect} issue against competitors and prepare a category-level response rather than treating it as a brand-only problem."
        title = f"Benchmark {aspect} across the category"
    else:
        action = f"Validate the {aspect} signal with additional customer feedback and monitor whether the spike persists before committing to a major intervention."
        title = f"Validate {aspect} signal"
    return [
        RecommendationDraft(
            priority,
            title,
            action,
            f"The signal is {getattr(signal, 'signal_score', 0):.2f} with {getattr(signal, 'signal_confidence', 0)}% confidence; competitor scope is {verdict}.",
            valid[:3],
            "next 2–4 weeks",
        )
    ]
