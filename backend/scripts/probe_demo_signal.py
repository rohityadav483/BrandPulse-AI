"""Check the deterministic demo signal against the public API.

Usage: python backend/scripts/probe_demo_signal.py [--api-base http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def get(base: str, path: str) -> dict:
    with urlopen(Request(base.rstrip("/") + path, headers={"Accept": "application/json"}), timeout=10) as r:
        return json.load(r)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-base", default="http://127.0.0.1:8000")
    args = p.parse_args()
    signal = get(args.api_base, "/api/v1/signals/demo-signal-battery")
    if signal["aspect"] != "battery" or signal["growth"] <= 0 or not signal["trend_corroborated"]:
        raise SystemExit("Demo signal probe failed: expected a positive battery spike with trend corroboration.")
    print(f"OK demo signal: {signal['aspect']} growth={signal['growth']}x trend_corroborated=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
