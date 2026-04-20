# server/api/scripts/check_types_align.py
"""Fail the build if Python and TS ItemKind literals diverge."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY_FILE = REPO / "server/api/src/ai_portal/chat/item_kinds.py"
TS_FILE = REPO / "apps/frontend/src/lib/chat-types.ts"


def py_kinds() -> set[str]:
    text = PY_FILE.read_text(encoding="utf-8")
    m = re.search(r"class ItemKind\(str, Enum\):(.+?)(?=\nclass |\Z)", text, re.S)
    assert m, "could not locate ItemKind in Python"
    return {v for _, v in re.findall(r'(\w+)\s*=\s*"([^"]+)"', m.group(1))}


def ts_kinds() -> set[str]:
    text = TS_FILE.read_text(encoding="utf-8")
    m = re.search(r"export type ItemKind\s*=([^;]+);", text)
    assert m, "could not locate ItemKind in TS"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def main() -> int:
    py = py_kinds()
    ts = ts_kinds()
    only_py = py - ts
    only_ts = ts - py
    if only_py or only_ts:
        print(f"Python-only kinds: {sorted(only_py)}", file=sys.stderr)
        print(f"TS-only kinds:     {sorted(only_ts)}", file=sys.stderr)
        return 1
    print(f"OK — {len(py)} ItemKind literals aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
