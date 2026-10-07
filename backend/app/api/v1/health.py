"""GET /api/v1/health (API.md §3.10)."""

from fastapi import APIRouter

from app import __version__
from app.api.v1.deps import SettingsDep
from app.db.session import check_database
from app.schemas.api import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, operation_id="getHealth", tags=["health"])
def get_health(settings: SettingsDep) -> HealthResponse:
    database = "ok" if check_database(settings.database_url) else "unavailable"
    # No NLP component exists yet (Phase 4). Report it honestly as unavailable.
    nlp = "unavailable"

    # Phase 0 rule: only the database drives `degraded`. API.md §3.10 also counts missing
    # required keys and NLP; those are added when SerpApi (P2), NLP (P4) and Groq (P7) land.
    status = "ok" if database == "ok" else "degraded"

    return HealthResponse(
        status=status,
        version=__version__,
        database=database,
        nlp=nlp,
        serpapi_configured=settings.serpapi_configured,
        live_serpapi_enabled=settings.allow_live_serpapi,
        groq_configured=settings.groq_configured,
        demo_mode=settings.demo_mode,
    )
