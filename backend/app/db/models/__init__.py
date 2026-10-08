"""Import every model here so `Base.metadata` is complete for Alembic."""

from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.base import Base
from app.db.models.brand import Brand
from app.db.models.content_analysis import ContentAnalysisRow
from app.db.models.content_item import ContentItemRow
from app.db.models.investigation import Evidence, Investigation
from app.db.models.item_aspect import ItemAspectRow
from app.db.models.llm_call import LLMCall
from app.db.models.phase5 import BrandSnapshot, Signal, TrendPoint
from app.db.models.raw_item import RawItemRow
from app.db.models.recommendation import Recommendation
from app.db.models.serp import SerpCache, SerpUsage

__all__ = [
    "Analysis",
    "AnalysisBrand",
    "Base",
    "Brand",
    "BrandSnapshot",
    "ContentAnalysisRow",
    "ContentItemRow",
    "Evidence",
    "Investigation",
    "ItemAspectRow",
    "LLMCall",
    "RawItemRow",
    "Recommendation",
    "SerpCache",
    "SerpUsage",
    "Signal",
    "TrendPoint",
]
