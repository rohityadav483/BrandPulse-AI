def scope_verdict(target_share: float | None, competitor_shares: list[float]) -> dict:
    if target_share is None or not competitor_shares:
        return {
            "verdict": "unknown",
            "ratio": None,
            "explanation": "Competitor data is unavailable for this aspect.",
        }
    median = (
        sorted(competitor_shares)[len(competitor_shares) // 2]
        if len(competitor_shares) % 2
        else sum(
            sorted(competitor_shares)[
                len(competitor_shares) // 2 - 1 : len(competitor_shares) // 2 + 1
            ]
        )
        / 2
    )
    if median <= 0:
        return {
            "verdict": "unknown",
            "ratio": None,
            "explanation": "Competitor negative-share data is too sparse to compare.",
        }
    ratio = target_share / median
    if ratio >= 1.5:
        verdict = "brand_specific"
    elif ratio <= 1.2:
        verdict = "industry_wide"
    else:
        verdict = "inconclusive"
    return {
        "verdict": verdict,
        "ratio": ratio,
        "explanation": f"Current negative {target_share:.0%} share is {ratio:.2f}× the median competitor share.",
    }
