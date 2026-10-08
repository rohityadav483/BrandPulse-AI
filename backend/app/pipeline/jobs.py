"""BackgroundTasks orchestration and lightweight concurrency/stale-job helpers.

Concurrency: at most `Settings.max_concurrent_analyses` analyses run at once. A job that
finds every slot busy WAITS (it is not dropped). If it cannot get a slot within
`QUEUE_WAIT_SECONDS` its row is marked `failed` with a reason, so a row never stays
`queued` forever. `reap_stale_jobs` recovers rows orphaned by a restart.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis
from app.db.models.enums import AnalysisStatus
from app.db.models.investigation import Investigation
from app.db.session import get_engine
from app.pipeline.analysis_pipeline import run_analysis
from app.pipeline.investigation_pipeline import run_investigation, settle_signal_status

logger = logging.getLogger(__name__)

# Must stay below the reaper's default `max_age_minutes` so the job fails itself first.
QUEUE_WAIT_SECONDS = 30 * 60
STALE_AFTER_MINUTES = 60


class _Gate:
    """Counting gate whose limit is read on every call (so settings are honored)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._running = 0

    def acquire(self, limit: int, timeout: float) -> bool:
        deadline = datetime.now(UTC) + timedelta(seconds=timeout)
        with self._cond:
            while self._running >= max(1, limit):
                remaining = (deadline - datetime.now(UTC)).total_seconds()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            self._running += 1
            return True

    def release(self) -> None:
        with self._cond:
            self._running = max(0, self._running - 1)
            self._cond.notify()

    @property
    def running(self) -> int:
        with self._cond:
            return self._running


_gate = _Gate()
_investigation_gate = _Gate()


def _mark_failed(analysis_id: UUID, settings: Settings, reason: str) -> None:
    """Fail a row that never got to run. Only touches rows still `queued`."""
    try:
        engine = get_engine(settings.database_url or settings.database_url_direct)
        with Session(engine) as session, session.begin():
            row = session.get(Analysis, analysis_id)
            if row is not None and row.status == AnalysisStatus.queued:
                row.status = AnalysisStatus.failed
                row.error = reason
                row.finished_at = datetime.now(UTC)
    except Exception:
        logger.exception("could not mark analysis %s failed", analysis_id)


def start_analysis_job(
    analysis_id: UUID,
    settings: Settings,
    queue_wait_seconds: float | None = None,
) -> None:
    wait = QUEUE_WAIT_SECONDS if queue_wait_seconds is None else queue_wait_seconds
    if not _gate.acquire(settings.max_concurrent_analyses, wait):
        logger.warning("analysis %s timed out waiting for a free slot", analysis_id)
        _mark_failed(
            analysis_id,
            settings,
            "Analysis could not start: the server stayed busy with other analyses.",
        )
        return
    try:
        run_analysis(analysis_id, settings)
    except Exception:
        # run_analysis records its own failures; this covers anything that escapes it.
        logger.exception("analysis_job_crashed", extra={"analysis_id": str(analysis_id)})
        _mark_failed_any(analysis_id, settings)
    finally:
        _gate.release()


def _mark_failed_any(analysis_id: UUID, settings: Settings) -> None:
    """Fail a row left `queued`/`running` after an unexpected crash."""
    try:
        engine = get_engine(settings.database_url or settings.database_url_direct)
        with Session(engine) as session, session.begin():
            row = session.get(Analysis, analysis_id)
            if row is not None and row.status in (
                AnalysisStatus.queued,
                AnalysisStatus.running,
            ):
                row.status = AnalysisStatus.failed
                row.error = "Analysis failed. Check server logs for details."
                row.finished_at = datetime.now(UTC)
    except Exception:
        logger.exception("could not mark analysis %s failed", analysis_id)


def _fail_investigation(
    investigation_id: UUID, settings: Settings, reason: str, only_queued: bool = False
) -> None:
    try:
        engine = get_engine(settings.database_url or settings.database_url_direct)
        signal_id = None
        with Session(engine) as session, session.begin():
            row = session.get(Investigation, investigation_id)
            allowed = {"queued"} if only_queued else {"queued", "running"}
            if row is not None and row.status in allowed:
                row.status = "failed"
                row.error = reason
                row.finished_at = datetime.now(UTC)
                signal_id = row.signal_id
        if signal_id is not None:
            settle_signal_status(engine, signal_id)
    except Exception:
        logger.exception("could not mark investigation %s failed", investigation_id)


def start_investigation_job(
    investigation_id: UUID,
    settings: Settings,
    queue_wait_seconds: float | None = None,
) -> None:
    """Run one investigation in the background, bounded like analyses (never dropped)."""
    wait = QUEUE_WAIT_SECONDS if queue_wait_seconds is None else queue_wait_seconds
    if not _investigation_gate.acquire(settings.max_concurrent_analyses, wait):
        _fail_investigation(
            investigation_id,
            settings,
            "Investigation could not start: the server stayed busy.",
            only_queued=True,
        )
        return
    try:
        run_investigation(investigation_id, settings)
    except Exception:
        logger.exception(
            "investigation_job_crashed", extra={"investigation_id": str(investigation_id)}
        )
        _fail_investigation(
            investigation_id, settings, "Investigation failed. Please try again."
        )
    finally:
        _investigation_gate.release()


def reap_stale_jobs(
    settings: Settings, max_age_minutes: int = STALE_AFTER_MINUTES
) -> int:
    """Recover rows orphaned by a restart or crash.

    * `running` and started more than `max_age_minutes` ago -> `partial`.
    * `queued` and created more than `max_age_minutes` ago -> `failed` (it never ran).
    * Investigations `queued`/`running` for longer than that -> `failed`, and their signal's
      status is recomputed (a stuck row would otherwise block every later investigation).
    Returns how many rows changed.
    """
    engine = get_engine(settings.database_url or settings.database_url_direct)
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=max_age_minutes)
    with Session(engine) as session, session.begin():
        running = session.scalars(
            select(Analysis).where(
                Analysis.status == AnalysisStatus.running,
                Analysis.started_at < cutoff,
            )
        ).all()
        for row in running:
            row.status = AnalysisStatus.partial
            row.error = "Analysis stopped after becoming stale."
            row.finished_at = now
        queued = session.scalars(
            select(Analysis).where(
                Analysis.status == AnalysisStatus.queued,
                Analysis.created_at < cutoff,
            )
        ).all()
        for row in queued:
            row.status = AnalysisStatus.failed
            row.error = "Analysis never started and was stopped after becoming stale."
            row.finished_at = now
        stuck = session.scalars(
            select(Investigation).where(
                Investigation.status.in_(("queued", "running")),
                Investigation.created_at < cutoff,
            )
        ).all()
        signal_ids = {row.signal_id for row in stuck}
        for row in stuck:
            row.status = "failed"
            row.error = "Investigation stopped after becoming stale."
            row.finished_at = now
        count = len(running) + len(queued) + len(stuck)
    for signal_id in signal_ids:
        settle_signal_status(engine, signal_id)
    return count


def reap_stale_jobs_safe(settings: Settings) -> int:
    """Startup/request hook: never raises, no-op without a database."""
    if not (settings.database_url or settings.database_url_direct):
        return 0
    try:
        count = reap_stale_jobs(settings)
    except Exception:
        logger.exception("reap_stale_jobs_failed")
        return 0
    if count:
        logger.warning("reaped %s stale analyses", count)
    return count
