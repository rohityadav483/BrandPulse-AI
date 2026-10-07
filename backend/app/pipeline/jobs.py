"""BackgroundTasks orchestration and lightweight concurrency/stale-job helpers."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis
from app.db.session import get_engine
from app.pipeline.analysis_pipeline import run_analysis

_semaphore = threading.BoundedSemaphore(1)


def start_analysis_job(analysis_id: UUID, settings: Settings) -> None:
    if not _semaphore.acquire(blocking=False):
        return
    try:
        run_analysis(analysis_id, settings)
    finally:
        _semaphore.release()


def reap_stale_jobs(settings: Settings, max_age_minutes: int = 60) -> int:
    engine = get_engine(settings.database_url or settings.database_url_direct)
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(Analysis).where(
                Analysis.status == "running", Analysis.started_at < cutoff
            )
        ).all()
        for row in rows:
            row.status = "partial"
            row.error = "Analysis stopped after becoming stale."
            row.finished_at = datetime.now(UTC)
        return len(rows)
