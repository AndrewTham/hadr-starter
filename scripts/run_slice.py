#!/usr/bin/env python3
"""Run one pass of the monitor and print the classified changeset.

    # offline (fixtures) -- deterministic, no network:
    python scripts/run_slice.py --db /tmp/hadr.db \
        --usgs scripts/tests/fixtures/usgs_run1.json \
        --gdacs scripts/tests/fixtures/gdacs_run1.json --observed-at 2026-07-08T00:00:00Z

    # live:
    python scripts/run_slice.py --db data/hadr.db --fetch

The model that writes the morning report only ever consumes the WAKE and FLAG
rows below. QUIET rows are persisted and summarized, not surfaced.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow "import hadr" when run directly as scripts/run_slice.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hadr import fetch, store, util  # noqa: E402
from hadr.pipeline import run  # noqa: E402

_ICON = {"WAKE": "🔴", "FLAG": "🟡", "QUIET": "·"}
_ORDER = {"WAKE": 0, "FLAG": 1, "QUIET": 2}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run one HADR monitor pass.")
    p.add_argument("--db", default="data/hadr.db", help="SQLite state file")
    p.add_argument("--usgs", help="USGS GeoJSON fixture file (offline)")
    p.add_argument("--gdacs", help="GDACS GeoJSON fixture file (offline)")
    p.add_argument("--fetch", action="store_true", help="fetch feeds live")
    p.add_argument("--observed-at", default=None, help="override observation time")
    args = p.parse_args(argv)

    observed_at = args.observed_at or util.now_iso()

    if not (args.fetch or args.usgs or args.gdacs):
        p.error("provide --usgs/--gdacs fixtures, or --fetch for live feeds")
    raw = fetch.load_feeds(args.usgs, args.gdacs, args.fetch)
    conn = store.open_db(args.db)

    changes = run(conn, raw, observed_at)
    changes.sort(key=lambda c: (_ORDER[c.verdict], c.situation_id))

    counts = {"WAKE": 0, "FLAG": 0, "QUIET": 0}
    for c in changes:
        counts[c.verdict] += 1

    print(f"\nHADR pass @ {observed_at}")
    print(f"  {counts['WAKE']} WAKE · {counts['FLAG']} FLAG · {counts['QUIET']} QUIET\n")
    for c in changes:
        if c.verdict == "QUIET":
            continue  # persisted, not surfaced
        level = c.to_level or c.from_level or "-"
        print(
            f"  {_ICON[c.verdict]} {c.verdict:5} {c.kind:11} "
            f"[{level:6}] {c.situation_id}  — {c.detail}"
        )
    if counts["QUIET"]:
        print(f"\n  ({counts['QUIET']} sub-threshold/noise changes stored, not reported)")

    # WAKE or FLAG present -> the morning routine would run the model.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
