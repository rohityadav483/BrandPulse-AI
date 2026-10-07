"""Collection plan: which (engine, query, window) calls one analysis makes.

Implements the lean plan in ARCHITECTURE.md section 6 (11 calls for target + 2 competitors):

| Calls | Engine        | Detail                                             |
|-------|---------------|----------------------------------------------------|
| 2     | Google News   | target, current + baseline                         |
| 2     | Google web    | target "brand product review problems", cur + base |
| 1     | Google Forums | target, current only (cannot be date-filtered)     |
| 1     | YouTube       | target, current only (cannot be date-filtered)     |
| 1     | Google Trends | all brands in one multi-term call, both windows    |
| 4     | News + web    | each competitor, current only (2 each, max 2)      |

The list is ordered by priority. If the call cap is below the plan size the tail is dropped
(competitors first) and reported in `SerpPlan.dropped`. Pure and deterministic: windows come
from `as_of_date`, never from today, and every date is absolute (stable cache keys).

Date encoding per engine is an assumption until the first live session verifies it
(docs/SERPAPI_FINDINGS.md): Google web `tbs=cdr:1,cd_min,cd_max` (M/D/YYYY), Google News
`after:`/`before:` operators inside `q`, Trends `date="YYYY-MM-DD YYYY-MM-DD"`.
"""

from datetime import date, timedelta

from app.schemas.domain import (
    MAX_COMPETITORS,
    PERIOD_DAYS_CHOICES,
    BrandRole,
    WindowKind,
)
from app.schemas.serp import PlannedCall, QuerySpec, SerpEngine, SerpPlan, WindowSet

HL = "en"
GL = "us"
TRENDS_MAX_TERMS = 5


def compute_windows(as_of_date: date, period_days: int) -> WindowSet:
    """Current = `period_days` ending at `as_of_date`; baseline = the preceding equal span.

    Both ends are inclusive: as_of 2026-08-10 and 30 days give current 2026-07-12..2026-08-10 and
    baseline 2026-06-12..2026-07-11 (API.md section 3.11 example).
    """
    if period_days not in PERIOD_DAYS_CHOICES:
        raise ValueError(f"period_days must be one of {PERIOD_DAYS_CHOICES}")
    span = timedelta(days=period_days - 1)
    current_start = as_of_date - span
    baseline_end = current_start - timedelta(days=1)
    return WindowSet(
        as_of_date=as_of_date,
        period_days=period_days,
        current_start=current_start,
        current_end=as_of_date,
        baseline_start=baseline_end - span,
        baseline_end=baseline_end,
    )


def subject_for(brand: str, product: str | None) -> str:
    """Search subject: "Samsung" + "Galaxy S25 Ultra" -> "Samsung Galaxy S25 Ultra"."""
    brand = " ".join(brand.split())
    product = " ".join((product or "").split())
    if not product:
        return brand
    if product.casefold().startswith(brand.casefold()):
        return product
    return f"{brand} {product}"


def _google_range(start: date, end: date) -> str:
    """Google custom date range; `tbs` takes US-style M/D/YYYY dates, both ends inclusive."""
    low = f"{start.month}/{start.day}/{start.year}"
    high = f"{end.month}/{end.day}/{end.year}"
    return f"cdr:1,cd_min:{low},cd_max:{high}"


def web_spec(query: str, start: date, end: date) -> QuerySpec:
    params = {"q": query, "tbs": _google_range(start, end), "hl": HL, "gl": GL}
    return QuerySpec(engine=SerpEngine.google, params=params)


def news_spec(query: str, start: date, end: date) -> QuerySpec:
    # `before:` is exclusive, so the inclusive window end becomes end + 1 day.
    dated = f"{query} after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}"
    return QuerySpec(
        engine=SerpEngine.google_news, params={"q": dated, "hl": HL, "gl": GL}
    )


def forums_spec(query: str) -> QuerySpec:
    return QuerySpec(
        engine=SerpEngine.google_forums, params={"q": query, "hl": HL, "gl": GL}
    )


def youtube_spec(query: str) -> QuerySpec:
    params = {"search_query": query, "hl": HL, "gl": GL}
    return QuerySpec(engine=SerpEngine.youtube, params=params)


def trends_spec(terms: list[str], windows: WindowSet) -> QuerySpec:
    params = {
        "q": ",".join(terms),
        "data_type": "TIMESERIES",
        "date": f"{windows.baseline_start.isoformat()} {windows.current_end.isoformat()}",
        "hl": HL,
    }
    return QuerySpec(engine=SerpEngine.google_trends, params=params)


def build_plan(
    *,
    brand: str,
    product: str | None,
    competitors: list[str],
    as_of_date: date,
    period_days: int,
    max_calls: int,
) -> SerpPlan:
    """Plan for one analysis. Raises ValueError on more than 2 or duplicate competitors."""
    if len(competitors) > MAX_COMPETITORS:
        raise ValueError(f"at most {MAX_COMPETITORS} competitors are supported")
    names = [" ".join(name.split()) for name in [brand, *competitors]]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("brand and competitor names must be distinct")
    if max_calls < 0:
        raise ValueError("max_calls must be >= 0")

    windows = compute_windows(as_of_date, period_days)
    subject = subject_for(brand, product)
    review_query = f"{subject} review problems"
    target = names[0]
    current, baseline = WindowKind.current, WindowKind.baseline

    def call(
        spec: QuerySpec, name: str, role: BrandRole, window: WindowKind | None
    ) -> PlannedCall:
        return PlannedCall(spec=spec, brand=name, role=role, window=window)

    cur_range = (windows.current_start, windows.current_end)
    base_range = (windows.baseline_start, windows.baseline_end)
    calls = [
        call(news_spec(subject, *cur_range), target, BrandRole.target, current),
        call(news_spec(subject, *base_range), target, BrandRole.target, baseline),
        call(web_spec(review_query, *cur_range), target, BrandRole.target, current),
        call(web_spec(review_query, *base_range), target, BrandRole.target, baseline),
        call(forums_spec(subject), target, BrandRole.target, current),
        call(youtube_spec(subject), target, BrandRole.target, current),
        call(
            trends_spec(names[:TRENDS_MAX_TERMS], windows),
            target,
            BrandRole.target,
            None,
        ),
    ]
    for rival in names[1:]:
        rival_web = web_spec(f"{rival} review problems", *cur_range)
        calls.append(
            call(news_spec(rival, *cur_range), rival, BrandRole.competitor, current)
        )
        calls.append(call(rival_web, rival, BrandRole.competitor, current))

    return SerpPlan(windows=windows, calls=calls[:max_calls], dropped=calls[max_calls:])
