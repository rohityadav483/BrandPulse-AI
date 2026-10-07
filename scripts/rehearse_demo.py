"""Run the no-network demo fallback rehearsal against the local API."""
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def get(base: str, path: str) -> dict:
    with urlopen(Request(base.rstrip('/') + path, headers={'Accept':'application/json'}), timeout=10) as r:
        return json.load(r)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--api-base', default='http://127.0.0.1:8000')
    args = p.parse_args()
    checks = [
        '/api/v1/analyses/00000000-0000-4000-8000-000000000001/dashboard',
        '/api/v1/signals/00000000-0000-4000-8000-000000000020',
        '/api/v1/investigations/00000000-0000-4000-8000-000000000030',
        '/api/v1/investigations/00000000-0000-4000-8000-000000000030/evidence',
    ]
    for path in checks:
        body = get(args.api_base, path)
        print(f'OK {path} ({len(json.dumps(body))} bytes)')
    print('Demo fallback rehearsal passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
