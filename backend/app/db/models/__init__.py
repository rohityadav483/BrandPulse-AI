"""Import every model here so `Base.metadata` is complete for Alembic."""

from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.base import Base
from app.db.models.brand import Brand
from app.db.models.serp import SerpCache, SerpUsage

__all__ = ["Analysis", "AnalysisBrand", "Base", "Brand", "SerpCache", "SerpUsage"]
