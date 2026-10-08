"""FastAPI application factory."""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import analyses, health, investigations, signals, usage
from app.api.v1.errors import register_exception_handlers
from app.config.settings import Settings, get_settings
from app.db.session import dispose_engines
from app.pipeline.jobs import reap_stale_jobs_safe
from app.utils.logging_config import configure_logging, request_id_var

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "startup", extra={"version": __version__, "demo_mode": settings.demo_mode}
        )
        # Recover analyses orphaned by a restart (no-op without a database).
        reap_stale_jobs_safe(settings)
        yield
        dispose_engines()
        logger.info("shutdown")

    app = FastAPI(title="BrandPulse AI", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                },
            )
            raise
        else:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)

    register_exception_handlers(app)
    for router in (
        analyses.router,
        signals.router,
        investigations.router,
        usage.router,
        health.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
