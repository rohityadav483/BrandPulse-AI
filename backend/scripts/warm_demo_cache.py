"""Load pinned cache entries embedded in the demo bundle into PostgreSQL.

The current verified bundle may contain no cache entries; in that case this is a safe no-op.
Usage: python backend/scripts/warm_demo_cache.py
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.serp import SerpCache
from app.db.session import get_engine

BUNDLE = ROOT / "contracts" / "demo" / "samsung_s25_ultra.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", default=str(BUNDLE))
    args = parser.parse_args()
    settings = Settings()
    url = settings.database_url or settings.database_url_direct
    if not url:
        raise SystemExit("DATABASE_URL or DATABASE_URL_DIRECT is required")
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    entries = bundle.get("cache_entries", [])
    if not entries:
        print("No cache entries in demo bundle; nothing to warm.")
        return 0
    engine = get_engine(url)
    with Session(engine) as session, session.begin():
        for item in entries:
            row = session.get(SerpCache, item["cache_key"])
            values = {
                "cache_key": item["cache_key"],
                "engine": item["engine"],
                "params": item["params"],
                "response": item["response"],
                "http_status": item.get("http_status"),
                "fetched_at": datetime.fromisoformat(item["fetched_at"]),
                "expires_at": datetime.fromisoformat(item["expires_at"]),
                "pinned": True,
            }
            if row is None:
                session.add(SerpCache(**values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
    print(f"Warmed {len(entries)} pinned SerpApi cache entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
