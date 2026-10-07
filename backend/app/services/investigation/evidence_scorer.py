def score_evidence(items, aspect: str):
    out = []
    seen = set()
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        text = ((item.title or "") + " " + (item.snippet or "")).casefold()
        if aspect.casefold() not in text:
            relevance = 0.35
        else:
            relevance = 0.85
        neg = any(
            w in text
            for w in (
                "problem",
                "issue",
                "drain",
                "bad",
                "poor",
                "complaint",
                "terrible",
                "overheat",
            )
        )
        pos = any(
            w in text for w in ("good", "great", "improved", "excellent", "fixed")
        )
        stance = (
            "supports"
            if neg and not pos
            else "contradicts"
            if pos and not neg
            else "neutral"
        )
        out.append((item, relevance, stance))
    return sorted(out, key=lambda x: (-x[1], x[0].id.hex))
