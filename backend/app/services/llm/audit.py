"""Audit trail: one `llm_calls` row per LLM provider call (docs/DATABASE.md)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.llm_call import LLMCall

logger = logging.getLogger(__name__)

MAX_ERROR_CHARS = 500


class LLMCallRecorder:
    """Writes call records for one task. Never raises: auditing must not break a report."""

    def __init__(
        self,
        engine,
        *,
        task: str,
        prompt_version: str,
        analysis_id: UUID | None = None,
        investigation_id: UUID | None = None,
        provider: str = "groq",
    ):
        self.engine = engine
        self.task = task
        self.prompt_version = prompt_version
        self.analysis_id = analysis_id
        self.investigation_id = investigation_id
        self.provider = provider

    def record(
        self,
        *,
        model: str,
        status: str,
        attempt: int = 1,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        try:
            with Session(self.engine) as s:
                s.add(
                    LLMCall(
                        analysis_id=self.analysis_id,
                        investigation_id=self.investigation_id,
                        task=self.task,
                        provider=self.provider,
                        model=model,
                        prompt_version=self.prompt_version,
                        attempt=attempt,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=latency_ms,
                        status=status,
                        error=error[:MAX_ERROR_CHARS] if error else None,
                    )
                )
                s.commit()
        except Exception:  # noqa: BLE001 - audit failures are logged, never raised
            logger.exception("Could not record %s LLM call", self.task)
