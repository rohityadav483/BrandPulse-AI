def compute_confidence(
    *,
    independence: float,
    agreement: float,
    signal_strength: float,
    recency: float,
    consistency: float,
    independent_sources: int,
) -> dict:
    score = 100 * (
        0.30 * independence
        + 0.25 * agreement
        + 0.20 * signal_strength
        + 0.15 * recency
        + 0.10 * consistency
    )
    if independent_sources < 2:
        score = min(score, 49)
    score = round(max(0, min(95, score)))
    label = "low" if score < 50 else "medium" if score < 75 else "high"
    return {
        "score": score,
        "label": label,
        "factors": {
            "independence": round(independence, 4),
            "agreement": round(agreement, 4),
            "signal_strength": round(signal_strength, 4),
            "recency": round(recency, 4),
            "consistency": round(consistency, 4),
        },
    }
