"""Check that checked-in TS types cover the OpenAPI schemas used by the frontend."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
types = (ROOT / "frontend/lib/api/types.generated.ts").read_text(encoding="utf-8")
missing = [name for name in spec["components"]["schemas"] if not re.search(rf"\b{name}\b", types)]
if missing:
    raise SystemExit("Missing generated TS schemas: " + ", ".join(missing))
required = {"DashboardResponse", "SignalDetail", "InvestigationResponse", "ListEvidenceResponse", "CreateAnalysisRequest", "CreateAnalysisResponse"}
missing_used = [name for name in required if not re.search(rf"\b{name}\b", types)]
if missing_used:
    raise SystemExit("Missing frontend DTOs: " + ", ".join(missing_used))
print(f"Type contract covers all {len(spec['components']['schemas'])} OpenAPI schemas and required frontend DTOs.")
