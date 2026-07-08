#!/usr/bin/env python3
"""Singapore morning brief — the deterministic gate for the 08:30 SGT routine.

Runs one monitor pass, keeps only what materially changed (the pipeline's WAKE
items), tiers them by relevance to Singapore, and prints a brief. The exit code
is the branch signal the scheduled workflow needs (see
`.github/workflows/sitrep.yml.disabled`, TODO 1):

    exit 0  — something to report (a model / operator should publish)
    exit 1  — quiet; nothing material this pass

This script never calls a model. Authoring the human report and republishing
dashboard.html is TODO 2 — for now, the operator "plays the loop".

    python3 scripts/sg_brief.py --usgs scripts/tests/fixtures/usgs_run1.json \
        --gdacs scripts/tests/fixtures/gdacs_run1.json --observed-at 2026-07-08T00:00:00Z
    python3 scripts/sg_brief.py --db data/hadr.db --fetch
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hadr import fetch, store  # noqa: E402
from hadr.pipeline import run  # noqa: E402
from hadr.relevance import rank_for_singapore, sg_reasons, sg_tier  # noqa: E402

HAZARD_LABEL = {
    "earthquake": "earthquake", "tropical_cyclone": "cyclone", "flood": "flood",
    "wildfire": "wildfire", "volcano": "volcano", "drought": "drought", "tsunami": "tsunami",
}
TIERS = ["DIRECT", "REGIONAL", "GLOBAL"]
TIER_BLURB = {
    "DIRECT": "may affect Singapore or its immediate neighbourhood",
    "REGIONAL": "within the SE-Asia operating region",
    "GLOBAL": "elsewhere — significant enough to note",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sgt(observed_at: str) -> dt.datetime:
    """Convert an observation timestamp to Singapore time (UTC+8, no DST)."""
    base = dt.datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return base.astimezone(ZoneInfo("Asia/Singapore"))
    except Exception:
        # Singapore has had no DST since 1982 — a fixed +8 is always correct.
        return base.astimezone(dt.timezone(dt.timedelta(hours=8)))


def render(situations_by_tier, observed_at: str) -> str:
    sgt = _sgt(observed_at)
    total = sum(len(v) for v in situations_by_tier.values())
    lines = []
    lines.append("=" * 62)
    lines.append(" SINGAPORE HADR BRIEF")
    lines.append(f" {sgt.strftime('%d %b %Y · %H:%M SGT')} ({observed_at})")
    lines.append("=" * 62)
    lines.append(f" {total} situation(s) changed materially this pass.")
    for tier in TIERS:
        group = situations_by_tier.get(tier, [])
        if not group:
            continue
        lines.append("")
        lines.append(f" {tier} ({len(group)}) — {TIER_BLURB[tier]}")
        for sit, change in group:
            haz = HAZARD_LABEL.get(sit.hazard_type, sit.hazard_type)
            level = sit.assessed_level.upper()
            title = sit.title or sit.place or sit.situation_id
            feeds = "+".join(s.upper() for s in sit.sources)
            lines.append(f"  ● {level:6} {haz:10} {title}")
            lines.append(f"           {change.kind} · {'; '.join(sg_reasons(sit))} · via {feeds}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Singapore HADR morning brief + change gate.")
    p.add_argument("--db", default="data/hadr.db")
    p.add_argument("--usgs")
    p.add_argument("--gdacs")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--observed-at", default=None)
    args = p.parse_args(argv)

    observed_at = args.observed_at or _now_iso()

    raw = {}
    if args.fetch:
        raw["usgs"] = fetch.features(fetch.fetch_json(fetch.USGS_URL))
        raw["gdacs"] = fetch.features(fetch.fetch_json(fetch.GDACS_URL))
    else:
        if not (args.usgs or args.gdacs):
            p.error("provide --usgs/--gdacs fixtures, or --fetch for live feeds")
        if args.usgs:
            raw["usgs"] = fetch.features(fetch.load_json_file(args.usgs))
        if args.gdacs:
            raw["gdacs"] = fetch.features(fetch.load_json_file(args.gdacs))

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    conn = store.connect(args.db)
    store.init_schema(conn)

    changes = run(conn, raw, observed_at)
    wake = {c.situation_id: c for c in changes if c.verdict == "WAKE"}

    if not wake:
        print(render({}, observed_at))
        print("\n GATE: quiet — nothing material for Singapore this pass.")
        return 1

    sits = store.load_situations(conn)
    pairs = [(sits[sid], c) for sid, c in wake.items() if sid in sits]
    ordered = rank_for_singapore([s for s, _ in pairs])
    by_change = {s.situation_id: c for s, c in pairs}
    grouped = {t: [] for t in TIERS}
    for sit in ordered:
        grouped[sg_tier(sit)].append((sit, by_change[sit.situation_id]))

    print(render(grouped, observed_at))
    print("\n GATE: report — publish the Singapore brief.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
