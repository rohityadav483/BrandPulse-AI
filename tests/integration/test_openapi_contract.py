"""OpenAPI contract: operations, status codes, error envelope, and committed-file drift."""

import importlib.util
import json
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONTRACT_PATH = BACKEND_DIR.parent / "contracts" / "openapi.json"
P = "/api/v1"

# API.md section 3 table: operationId -> (method, path)
OPERATIONS = {
    "estimateAnalysis": ("post", f"{P}/analyses/estimate"),
    "createAnalysis": ("post", f"{P}/analyses"),
    "listAnalyses": ("get", f"{P}/analyses"),
    "getAnalysis": ("get", f"{P}/analyses/{{id}}"),
    "getDashboard": ("get", f"{P}/analyses/{{id}}/dashboard"),
    "listMentions": ("get", f"{P}/analyses/{{id}}/mentions"),
    "getSignal": ("get", f"{P}/signals/{{id}}"),
    "investigateSignal": ("post", f"{P}/signals/{{id}}/investigate"),
    "getInvestigation": ("get", f"{P}/investigations/{{id}}"),
    "listInvestigationEvidence": ("get", f"{P}/investigations/{{id}}/evidence"),
    "getUsage": ("get", f"{P}/usage"),
    "getHealth": ("get", f"{P}/health"),
}

# operationId -> response schema name for the main success status
RESPONSE_MODELS = {
    "estimateAnalysis": ("200", "EstimateAnalysisResponse"),
    "createAnalysis": ("202", "CreateAnalysisResponse"),
    "listAnalyses": ("200", "ListAnalysesResponse"),
    "getAnalysis": ("200", "AnalysisStatusResponse"),
    "getDashboard": ("200", "DashboardResponse"),
    "listMentions": ("200", "ListMentionsResponse"),
    "getSignal": ("200", "SignalDetail"),
    "investigateSignal": ("202", "InvestigateSignalResponse"),
    "getInvestigation": ("200", "InvestigationResponse"),
    "listInvestigationEvidence": ("200", "ListEvidenceResponse"),
    "getUsage": ("200", "UsageResponse"),
    "getHealth": ("200", "HealthResponse"),
}


@pytest.fixture
def spec(make_client):
    return make_client().app.openapi()


def _operations(spec):
    found = {}
    for path, item in spec["paths"].items():
        for method, op in item.items():
            found[op["operationId"]] = (method, path, op)
    return found


def test_exactly_the_documented_operations_exist(spec):
    ops = _operations(spec)
    assert {k: (v[0], v[1]) for k, v in ops.items()} == OPERATIONS


def test_operation_ids_are_unique_camel_case(spec):
    ids = [op["operationId"] for item in spec["paths"].values() for op in item.values()]
    assert len(ids) == len(set(ids)) == len(OPERATIONS)
    assert all(i[0].islower() and "_" not in i for i in ids)


@pytest.mark.parametrize("op_id", sorted(RESPONSE_MODELS))
def test_success_response_uses_documented_schema(spec, op_id):
    status, schema = RESPONSE_MODELS[op_id]
    op = _operations(spec)[op_id][2]
    ref = op["responses"][status]["content"]["application/json"]["schema"]["$ref"]
    assert ref == f"#/components/schemas/{schema}"


def test_investigate_documents_200_reuse_and_202_create(spec):
    op = _operations(spec)["investigateSignal"][2]
    assert {"200", "202"} <= set(op["responses"])
    ref200 = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref200.endswith("/InvestigateSignalResponse")
    force = next(p for p in op["parameters"] if p["name"] == "force")
    assert force["in"] == "query" and force["schema"]["default"] is False


def test_access_code_header_only_on_live_capable_operations(spec):
    with_header = set()
    for op_id, (_, _, op) in _operations(spec).items():
        for param in op.get("parameters", []):
            if param["in"] == "header":
                assert param["name"] == "X-Access-Code"
                with_header.add(op_id)
    assert with_header == {"createAnalysis", "investigateSignal"}


def test_create_and_estimate_share_one_request_schema(spec):
    for op_id in ("createAnalysis", "estimateAnalysis"):
        body = _operations(spec)[op_id][2]["requestBody"]["content"]["application/json"]["schema"]
        assert body["$ref"] == "#/components/schemas/CreateAnalysisRequest"


def test_request_schema_constraints_are_in_the_contract(spec):
    props = spec["components"]["schemas"]["CreateAnalysisRequest"]["properties"]
    assert props["brand"]["minLength"] == 1 and props["brand"]["maxLength"] == 80
    assert props["competitors"]["maxItems"] == 2
    assert props["competitors"]["items"]["maxLength"] == 80
    assert props["period_days"]["enum"] == [7, 14, 30]
    assert props["period_days"]["default"] == 30
    assert spec["components"]["schemas"]["CreateAnalysisRequest"]["required"] == ["brand"]


def test_query_parameters_match_the_contract(spec):
    ops = _operations(spec)

    def params(op_id):
        return {p["name"]: p for p in ops[op_id][2].get("parameters", []) if p["in"] == "query"}

    limit = params("listAnalyses")["limit"]["schema"]
    assert (limit["default"], limit["minimum"], limit["maximum"]) == (10, 1, 50)
    assert set(params("listMentions")) == {
        "brand_id",
        "aspect",
        "sentiment",
        "source_type",
        "window",
        "page",
        "page_size",
    }
    page_size = params("listMentions")["page_size"]["schema"]
    assert (page_size["default"], page_size["maximum"]) == (20, 100)
    assert set(params("listInvestigationEvidence")) == {
        "stance",
        "source_type",
        "page",
        "page_size",
    }


def test_errors_use_the_envelope_and_not_fastapi_defaults(spec):
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas and "ValidationError" not in schemas
    assert "ErrorResponse" in schemas
    for op_id, (_, _, op) in _operations(spec).items():
        for status, response in op["responses"].items():
            if status.startswith(("4", "5")):
                ref = response["content"]["application/json"]["schema"]["$ref"]
                assert ref == "#/components/schemas/ErrorResponse", (op_id, status)


def test_operations_with_input_document_422(spec):
    ops = _operations(spec)
    for op_id in ("estimateAnalysis", "createAnalysis", "listAnalyses", "listMentions"):
        assert "422" in ops[op_id][2]["responses"], op_id


def test_all_refs_resolve(spec):
    schemas = spec["components"]["schemas"]

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref:
                assert ref.startswith("#/components/schemas/"), ref
                assert ref.rsplit("/", 1)[1] in schemas, ref
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)


def test_contract_enums_are_lowercase_snake_case(spec):
    for name, schema in spec["components"]["schemas"].items():
        for value in schema.get("enum", []):
            if isinstance(value, str):
                assert value == value.lower() and " " not in value, (name, value)


# --- stub routes behave per the envelope ---------------------------------------------------------


def test_stub_routes_answer_501_in_the_error_envelope(make_client):
    client = make_client()
    res = client.get(f"{P}/usage")
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "not_implemented"
    res = client.get(f"{P}/analyses/some-id")
    assert res.status_code == 501
    res = client.post(f"{P}/analyses", json={"brand": "Samsung"})
    assert res.status_code == 501


def test_request_validation_runs_before_the_stub(make_client):
    client = make_client()
    res = client.post(f"{P}/analyses", json={"brand": "A", "competitors": ["B", "C", "D"]})
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "validation_error"
    assert any(f["field"].startswith("competitors") for f in body["details"]["fields"])
    assert client.post(f"{P}/analyses/estimate", json={"brand": ""}).status_code == 422
    assert client.get(f"{P}/analyses?limit=0").status_code == 422
    assert client.get(f"{P}/analyses?limit=51").status_code == 422
    assert client.get(f"{P}/analyses/x/mentions?sentiment=bogus").status_code == 422
    assert client.get(f"{P}/investigations/x/evidence?page_size=101").status_code == 422


# --- committed contracts/openapi.json -------------------------------------------------------------


def _export_module():
    path = BACKEND_DIR / "scripts" / "export_openapi.py"
    module_spec = importlib.util.spec_from_file_location("export_openapi", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_export_script_writes_and_checks(tmp_path):
    export = _export_module()
    out = tmp_path / "openapi.json"
    assert export.main(["--output", str(out), "--check"]) == 1  # missing file = drift
    assert export.main(["--output", str(out)]) == 0
    assert export.main(["--output", str(out), "--check"]) == 0
    first = out.read_text(encoding="utf-8")
    assert first.endswith("\n") and json.loads(first)["info"]["title"] == "BrandPulse AI"
    export.main(["--output", str(out)])
    assert out.read_text(encoding="utf-8") == first  # deterministic
    out.write_text(first.replace("BrandPulse AI", "Other"), encoding="utf-8")
    assert export.main(["--output", str(out), "--check"]) == 1


def test_committed_contract_is_up_to_date():
    """Fails when schemas/routes changed without re-running scripts/export_openapi.py."""
    export = _export_module()
    assert CONTRACT_PATH.exists() and CONTRACT_PATH.stat().st_size > 0, (
        "contracts/openapi.json is empty. Run: python scripts/export_openapi.py"
    )
    assert export.main(["--output", str(CONTRACT_PATH), "--check"]) == 0
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed["openapi"].startswith("3.")
    ids = {op["operationId"] for item in committed["paths"].values() for op in item.values()}
    assert ids == set(OPERATIONS)
