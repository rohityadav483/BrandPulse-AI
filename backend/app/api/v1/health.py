from fastapi import APIRouter

from app import __version__
from app.api.v1.deps import SettingsDep
from app.db.session import check_database
from app.schemas.api import HealthResponse
from app.services.nlp.readiness import nlp_status

router = APIRouter()


@router.get(
    "/health", response_model=HealthResponse, operation_id="getHealth", tags=["health"]
)
def get_health(settings: SettingsDep) -> HealthResponse:
    db = (
        "ok"
        if check_database(settings.database_url or settings.database_url_direct)
        else "unavailable"
    )
    nlp = nlp_status(settings.sentiment_model, settings.hf_home)
    status = "ok" if db == "ok" and nlp != "unavailable" else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        database=db,
        nlp=nlp,
        serpapi_configured=settings.serpapi_configured,
        live_serpapi_enabled=settings.allow_live_serpapi,
        groq_configured=settings.groq_configured,
        demo_mode=settings.demo_mode,
    )
