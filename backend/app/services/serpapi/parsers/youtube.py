"""YouTube search (`engine=youtube`) -> RawItem. Source: `video_results`."""

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


def parse_youtube(response: Mapping[str, Any]) -> ParsedResponse:
    found, skipped = rows(response, RESULT_LIST_KEYS[SerpEngine.youtube])
    items: list[RawItem] = []
    for index, row in enumerate(found, start=1):
        title, url = text(row.get("title")), text(row.get("link"))
        if not title or not url:
            skipped += 1
            continue
        channel = row.get("channel")
        channel = channel if isinstance(channel, dict) else {}
        items.append(
            RawItem(
                source_type=SourceType.youtube,
                engine=SerpEngine.youtube,
                title=title,
                url=url,
                snippet=text(row.get("description")),
                author=text(channel.get("name")),
                # Relative ("3 weeks ago") or missing; Phase 3 `dates.py` interprets it.
                published_raw=text(row.get("published_date")),
                position=as_int(row.get("position_on_page")) or index,
                metadata=compact(
                    views=as_int(row.get("views")),
                    length=text(row.get("length")),
                    channel_link=text(channel.get("link")),
                ),
            )
        )
    return ParsedResponse(engine=SerpEngine.youtube, items=items, skipped=skipped)
