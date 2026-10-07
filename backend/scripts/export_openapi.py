"""Export the FastAPI OpenAPI document to contracts/openapi.json (API.md section 6).

Usage (from backend/):
    python scripts/export_openapi.py            # write contracts/openapi.json
    python scripts/export_openapi.py --check    # exit 1 if the committed file is out of date
    python scripts/export_openapi.py --output path/to/file.json

No database, no network, no API keys needed. Output is deterministic.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BACKEND_DIR.parent / "contracts" / "openapi.json"

sys.path.insert(0, str(BACKEND_DIR))


def build_openapi() -> dict:
    from app.config.settings import Settings
    from app.main import create_app

    # Ignore any developer .env: the contract must not depend on local configuration.
    return create_app(Settings(_env_file=None)).openapi()


def render(spec: dict) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="fail if the file would change"
    )
    args = parser.parse_args(argv)

    text = render(build_openapi())

    if args.check:
        current = (
            args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        )
        if current != text:
            print(
                f"{args.output} is out of date. Run: python scripts/export_openapi.py"
            )
            return 1
        print(f"{args.output} is up to date.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
