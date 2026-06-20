"""Probe backend API: enumerate routes from openapi.json, hit each GET, report status.

Run: python scripts/probe_api.py [base_url]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TOKEN = "devtoken"

# Sample values for common path params so we can probe parameterized GETs.
SAMPLE = {
    "id": "00000000-0000-0000-0000-000000000000",
    "kb_id": "00000000-0000-0000-0000-000000000000",
    "conversation_id": "00000000-0000-0000-0000-000000000000",
    "memory_id": "00000000-0000-0000-0000-000000000000",
    "user_id": "00000000-0000-0000-0000-000000000000",
    "org_id": "00000000-0000-0000-0000-000000000000",
    "team_id": "00000000-0000-0000-0000-000000000000",
    "trace_id": "00000000-0000-0000-0000-000000000000",
    "run_id": "00000000-0000-0000-0000-000000000000",
    "worker_id": "00000000-0000-0000-0000-000000000000",
    "instance_id": "00000000-0000-0000-0000-000000000000",
    "policy_id": "00000000-0000-0000-0000-000000000000",
    "key_id": "00000000-0000-0000-0000-000000000000",
    "webhook_id": "00000000-0000-0000-0000-000000000000",
    "document_id": "00000000-0000-0000-0000-000000000000",
    "doc_id": "00000000-0000-0000-0000-000000000000",
    "assistant_id": "00000000-0000-0000-0000-000000000000",
    "name": "sample",
    "provider": "openai",
}


def fill(path: str) -> str | None:
    out = path
    while "{" in out:
        s = out.index("{")
        e = out.index("}")
        key = out[s + 1 : e]
        val = SAMPLE.get(key)
        if val is None:
            return None  # unknown param, skip
        out = out[:s] + val + out[e + 1 :]
    return out


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:200]


def main() -> None:
    spec_raw = get_raw(f"{BASE}/openapi.json")
    spec = json.loads(spec_raw)
    paths = spec.get("paths", {})

    get_routes = []
    for path, methods in paths.items():
        if "get" in methods:
            get_routes.append(path)

    print(f"Total paths: {len(paths)}  |  GET routes: {len(get_routes)}\n")

    buckets: dict[str, list[tuple[str, int, str]]] = {}
    skipped = []
    for path in sorted(get_routes):
        filled = fill(path)
        if filled is None:
            skipped.append(path)
            continue
        status, body = get(f"{BASE}{filled}")
        # Bucket by first path segment (module-ish)
        seg = path.strip("/").split("/")
        key = seg[1] if seg and seg[0] in ("v1", "api") and len(seg) > 1 else (seg[0] or "root")
        buckets.setdefault(key, []).append((path, status, body))

    # Categorize
    ok, client_err, server_err, conn_err = [], [], [], []
    for key in sorted(buckets):
        for path, status, body in buckets[key]:
            line = (key, path, status, body)
            if status == -1:
                conn_err.append(line)
            elif 200 <= status < 300:
                ok.append(line)
            elif status in (401, 403, 404, 422, 405, 400, 503, 501):
                client_err.append(line)
            elif status >= 500:
                server_err.append(line)
            else:
                client_err.append(line)

    def show(title, rows):
        print(f"\n===== {title} ({len(rows)}) =====")
        for key, path, status, body in rows:
            extra = f"  {body}" if body and status >= 500 else ""
            print(f"  [{status}] {path}{extra}")

    show("2xx OK", sorted(ok, key=lambda r: r[1]))
    show("4xx / expected-no-data (401/403/404/422/503)", sorted(client_err, key=lambda r: r[1]))
    show("5xx SERVER ERRORS (BUGS)", sorted(server_err, key=lambda r: r[1]))
    show("CONNECTION ERRORS", sorted(conn_err, key=lambda r: r[1]))

    print(f"\nSKIPPED (unknown path params): {len(skipped)}")
    for p in skipped:
        print(f"  - {p}")

    print("\n========== SUMMARY ==========")
    print(f"  2xx OK         : {len(ok)}")
    print(f"  4xx/expected   : {len(client_err)}")
    print(f"  5xx SERVER ERR : {len(server_err)}")
    print(f"  conn errors    : {len(conn_err)}")
    print(f"  skipped        : {len(skipped)}")


def get_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


if __name__ == "__main__":
    main()
