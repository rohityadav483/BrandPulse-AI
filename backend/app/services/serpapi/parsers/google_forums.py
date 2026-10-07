"""Google Forums (`engine=google_forums`) -> RawItem.

Result key names are not yet verified against a live response, so `organic_results`,
`forum_results` and `discussions_and_forums` are all accepted (see SERPAPI_FINDINGS.md).
"""

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


def parse_google_forums(response: Mapping[str, Any]) -> ParsedResponse:
    found, skipped = rows(response, RESULT_LIST_KEYS[SerpEngine.google_forums])
    items: list[RawItem] = []
    for index, row in enumerate(found, start=1):
        title, url = text(row.get("title")), text(row.get("link"))
        if not title or not url:
            skipped += 1
            continue
        items.append(
            RawItem(
                source_type=SourceType.forum,
                engine=SerpEngine.google_forums,
                title=title,
                url=url,
                snippet=text(row.get("snippet")),
                author=text(row.get("author")) or text(row.get("source")),
                published_raw=text(row.get("date")),
                position=as_int(row.get("position")) or index,
                metadata=compact(
                    community=text(row.get("community")),
                    answers=as_int(row.get("answers")),
                    comments=as_int(row.get("comments")),
                ),
            )
        )
    return ParsedResponse(engine=SerpEngine.google_forums, items=items, skipped=skipped)
