from dataclasses import dataclass


@dataclass(frozen=True)
class CompetitorComparisonResult:
    rows: list[dict]


def compare_aspect(
    target: dict, competitors: list[dict], aspect: str, brand_refs: dict
) -> CompetitorComparisonResult:
    rows = []
    for entry in [target, *competitors]:
        stats = next(
            (x for x in entry.get("aspects", []) if x["aspect"] == aspect), None
        )
        negative = (stats or {}).get("negative", 0)
        positive = (stats or {}).get("positive", 0)
        level = "high" if negative >= 50 else "medium" if negative >= 30 else "low"
        rows.append(
            {
                "brand": brand_refs[entry["brand_id"]],
                "positive_pct": positive,
                "negative_pct": negative,
                "aspect_negative_share": negative / 100.0,
                "level": level,
                "search_interest_change_pct": entry.get("search_interest_change_pct"),
            }
        )
    return CompetitorComparisonResult(rows)
