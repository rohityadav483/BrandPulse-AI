"""Google web search (`engine=google`) -> RawItem. Source: `organic_results`."""

from collections.abc import Mapping
from typing import Any

from app.schemas.domain import SourceType
from app.schemas.serp import ParsedResponse, RawItem, SerpEngine
from app.services.serpapi.parsers.common import (
    RESULT_LIST_KEYS,
    as_int,
    compact,
    rows,
    text,
)


def parse_google_web(response: Mapping[str, Any]) -> ParsedResponse:
    found, skipped = rows(response, RESULT_LIST_KEYS[SerpEngine.google])
    items: list[RawItem] = []
    for index, row in enumerate(found, start=1):
        title, url = text(row.get("title")), text(row.get("link"))
        if not title or not url:
            skipped += 1
            continue
        items.append(
            RawItem(
                source_type=SourceType.web,
                engine=SerpEngine.google,
                title=title,
                url=url,
                snippet=text(row.get("snippet")),
                author=text(row.get("source")),
                published_raw=text(row.get("date")),
                position=as_int(row.get("position")) or index,
                metadata=compact(displayed_link=text(row.get("displayed_link"))),
            )
        )
    return ParsedResponse(engine=SerpEngine.google, items=items, skipped=skipped)
