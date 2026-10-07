"""Export a verified analysis/investigation into the Phase 10 demo bundle.

Usage:
  python scripts/export_demo_bundle.py --analysis-id <uuid> --signal-id <uuid> \
      --investigation-id <uuid> --api-base http://127.0.0.1:8000

The script pins every SerpApi cache entry that was used by the analysis/investigation,
then writes the API-shaped responses plus those cache entries to contracts/demo/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.settings import Settings
from app.db.models.serp import SerpCache, SerpUsage
from app.db.session import get_engine


def fetch(base: str, path: str) -> dict:
    try:
        with urlopen(
            Request(base.rstrip("/") + path, headers={"Accept": "application/json"}),
            timeout=20,
        ) as response:
            return json.load(response)
    except (HTTPError, URLError) as exc:
        raise SystemExit(f"API request failed for {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output", default=str(ROOT / "contracts" / "demo" / "samsung_s25_ultra.json")
    )
    args = parser.parse_args()

    settings = Settings()
    if not (settings.database_url or settings.database_url_direct):
        raise SystemExit("DATABASE_URL or DATABASE_URL_DIRECT is required")
    engine = get_engine(settings.database_url or settings.database_url_direct)

    dashboard = fetch(args.api_base, f"/api/v1/analyses/{args.analysis_id}/dashboard")
    signal = fetch(args.api_base, f"/api/v1/signals/{args.signal_id}")
    investigation = fetch(
        args.api_base, f"/api/v1/investigations/{args.investigation_id}"
    )
    evidence = fetch(
        args.api_base,
        f"/api/v1/investigations/{args.investigation_id}/evidence?page=1&page_size=100",
    )

    with Session(engine) as session, session.begin():
        usages = session.scalars(
            select(SerpUsage).where(
                (SerpUsage.analysis_id == args.analysis_id)
                | (SerpUsage.investigation_id == args.investigation_id)
            )
        ).all()
        keys = sorted({u.cache_key for u in usages})
        if keys:
            session.query(SerpCache).filter(SerpCache.cache_key.in_(keys)).update(
                {SerpCache.pinned: True}, synchronize_session=False
            )
        cache_rows = (
            session.scalars(
                select(SerpCache).where(SerpCache.cache_key.in_(keys))
            ).all()
            if keys
            else []
        )
        cache_entries = [
            {
                "cache_key": r.cache_key,
                "engine": r.engine,
                "params": r.params,
                "response": r.response,
                "http_status": r.http_status,
                "fetched_at": r.fetched_at.isoformat(),
                "expires_at": r.expires_at.isoformat(),
                "pinned": True,
            }
            for r in cache_rows
        ]

    bundle = {
        "meta": {
            "fixture_version": "2",
            "scenario": "Samsung Galaxy S25 Ultra",
            "as_of_date": dashboard["analysis"]["as_of_date"],
            "period_days": 30,
            "mode": "verified_live_export",
            "notes": "Exported from a verified local run. Cache entries are pinned for demo replay.",
        },
        "dashboard": dashboard,
        "signal_detail": signal,
        "investigation": investigation,
        "evidence": evidence,
        "cache_entries": cache_entries,
        "source_ids": {
            "analysis_id": args.analysis_id,
            "signal_id": args.signal_id,
            "investigation_id": args.investigation_id,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Exported {output}")
    print(f"Pinned/exported cache entries: {len(cache_entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
