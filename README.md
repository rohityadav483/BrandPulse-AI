# BrandPulse AI

Brand-intelligence MVP: public web signals, local NLP, emerging-signal detection, cited investigations.
Local run only (hackathon MVP).

- Rules for contributors and coding agents: [`AGENTS.md`](AGENTS.md)
- Current state: [`docs/PROGRESS.md`](docs/PROGRESS.md)
- Design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/DATABASE.md`](docs/DATABASE.md), [`docs/API.md`](docs/API.md), [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md), [`docs/SCORING.md`](docs/SCORING.md)
- Plan: [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)

Layout: `backend/` (FastAPI), `frontend/` (Next.js), `contracts/` (OpenAPI + golden fixtures), `docs/`.

## Phase 0 status

Foundations and contracts are implemented. The golden Samsung scenario can be rendered locally without SerpApi or Groq. External account creation/keys are intentionally not committed and must be supplied through `.env` for later live phases.

## Backend

From `backend/`:

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
pytest                      # migration tests skip without TEST_DATABASE_URL
ruff check .
ruff format --check .
python backend/scripts/export_openapi.py --check
python backend/scripts/validate_golden.py
alembic upgrade head       # needs DATABASE_URL_DIRECT in .env
uvicorn app.main:app --reload
```

Health endpoint: `http://localhost:8000/api/v1/health`.

Migration tests need a PostgreSQL role that can create databases:

```bash
export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/postgres
pytest tests/integration/test_migrations.py
```

## Frontend

From `frontend/`:

```bash
npm install
npm run generate:types
npm run typecheck
npm run lint
npm test
npm run build
npm run dev
```

For the Phase 0 golden demo, copy `.env.example` to `.env.local` and keep:

```text
NEXT_PUBLIC_USE_GOLDEN=true
API_ORIGIN=http://127.0.0.1:8000
```

Then open `http://localhost:3000`. Golden mode does not call SerpApi or Groq.
