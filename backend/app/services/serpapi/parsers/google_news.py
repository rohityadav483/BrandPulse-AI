"""Google News (`engine=google_news`) -> RawItem. Source: `news_results` (+ nested `stories`)."""

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


def _source_name(source: Any) -> tuple[str | None, str | None]:
    """`source` is an object ({"name", "authors"}) on Google News, a plain string elsewhere."""
    if isinstance(source, dict):
        authors = source.get("authors")
        joined = ", ".join(a for a in authors if isinstance(a, str)) if authors else None
        return text(source.get("name")), text(joined)
    return text(source), None


def _item(row: Mapping[str, Any], position: int | None) -> RawItem | None:
    title, url = text(row.get("title")), text(row.get("link"))
    if not title or not url:
        return None
    outlet, authors = _source_name(row.get("source"))
    return RawItem(
        source_type=SourceType.news,
        engine=SerpEngine.google_news,
        title=title,
        url=url,
        snippet=text(row.get("snippet")),
        author=outlet,
        published_raw=text(row.get("date")),
        published_iso=text(row.get("iso_date")),
        position=position,
        metadata=compact(authors=authors),
    )


def parse_google_news(response: Mapping[str, Any]) -> ParsedResponse:
    found, skipped = rows(response, RESULT_LIST_KEYS[SerpEngine.google_news])
    items: list[RawItem] = []
    for index, row in enumerate(found, start=1):
        position = as_int(row.get("position")) or index
        stories = row.get("stories")
        has_stories = isinstance(stories, list) and bool(stories)
        parent = _item(row, position)
        if parent is not None:
            items.append(parent)
        elif not has_stories:
            skipped += 1
        # A story cluster carries its articles under `stories`; they are separate sources.
        for story in stories if has_stories else []:
            nested = _item(story, position) if isinstance(story, dict) else None
            if nested is None:
                skipped += 1
            else:
                items.append(nested)
    return ParsedResponse(engine=SerpEngine.google_news, items=items, skipped=skipped)
