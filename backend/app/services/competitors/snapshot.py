from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.content_analysis import ContentAnalysisRow
from app.db.models.content_item import ContentItemRow
from app.db.models.item_aspect import ItemAspectRow


def build_competitor_snapshot(engine, analysis_id, brand_id):
    with Session(engine) as s:
        items = s.scalars(
            select(ContentItemRow).where(
                ContentItemRow.analysis_id == analysis_id,
                ContentItemRow.brand_id == brand_id,
                ContentItemRow.window == "current",
                ContentItemRow.purpose == "collection",
            )
        ).all()
        ids = [x.id for x in items]
        analyses = (
            s.scalars(
                select(ContentAnalysisRow).where(
                    ContentAnalysisRow.content_id.in_(ids),
                    ContentAnalysisRow.is_about_brand.is_(True),
                )
            ).all()
            if ids
            else []
        )
        amap = {x.content_id: x for x in analyses}
        aspects = (
            s.scalars(
                select(ItemAspectRow).where(ItemAspectRow.content_id.in_(ids))
            ).all()
            if ids
            else []
        )
    relevant = [x for x in items if x.id in amap]
    n = len(relevant)
    sentiment = Counter(amap[x.id].sentiment.value for x in relevant)
    dist = {
        k: round(100 * sentiment.get(k, 0) / n) if n else 0
        for k in ("positive", "neutral", "negative")
    }
    grouped = defaultdict(list)
    for a in aspects:
        if a.content_id in amap:
            grouped[a.aspect].append(a)
    aspect_rows = []
    for name, rows in sorted(grouped.items()):
        counts = Counter(r.sentiment.value for r in rows)
        total = len(rows)
        aspect_rows.append(
            {
                "aspect": name,
                "net_score": round(
                    100
                    * (counts.get("positive", 0) - counts.get("negative", 0))
                    / total
                )
                if total
                else 0,
                "mentions": total,
                "positive": round(100 * counts.get("positive", 0) / total)
                if total
                else 0,
                "neutral": round(100 * counts.get("neutral", 0) / total)
                if total
                else 0,
                "negative": round(100 * counts.get("negative", 0) / total)
                if total
                else 0,
            }
        )
    return {
        "sample_size": n,
        "sentiment": dist,
        "aspects": aspect_rows,
        "low_data": n < 3,
    }
