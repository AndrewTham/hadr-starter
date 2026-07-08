"""Orchestration: normalize -> correlate -> persist -> classify.

Returns the classified changeset for the run. The model (elsewhere) only ever
looks at WAKE and FLAG items; QUIET items are persisted and otherwise ignored.
"""
from __future__ import annotations

from typing import Dict, List

from . import store
from .classify import Change, classify
from .correlate import CorrelationIndex, Match
from .models import Evidence, Situation, new_situation_from
from .normalize import normalize

# USGS is the authoritative source for earthquakes, so process it first: the
# USGS situation then exists when the GDACS duplicate arrives and rung 3 can
# fold it in (rather than minting a second situation we'd have to reconcile).
_SOURCE_ORDER = {"usgs": 0, "gdacs": 1, "reliefweb": 2}


def _order_key(ev: Evidence):
    return (_SOURCE_ORDER.get(ev.source, 9), ev.onset_time or "", ev.source_event_id)


def run(
    conn,
    raw_by_source: Dict[str, List[dict]],
    observed_at: str,
) -> List[Change]:
    situations: Dict[str, Situation] = store.load_situations(conn)

    # Rebuild the correlation index over everything we already know.
    index = CorrelationIndex()
    prior_evidence = store.load_evidence_by_situation(conn)
    for sid, evs in prior_evidence.items():
        sit = situations.get(sid)
        if sit:
            for ev in evs:
                index.add(ev, sit)

    # Normalize all incoming features.
    incoming: List[Evidence] = []
    for source, feats in raw_by_source.items():
        incoming.extend(normalize(source, feats, observed_at))
    incoming.sort(key=_order_key)

    before_snap: Dict[str, Situation] = {}  # pre-run state per touched situation
    flags_by_sid: Dict[str, List[str]] = {}
    touched: List[str] = []

    for ev in incoming:
        match: Match = index.match(ev)
        flags: List[str] = []

        if match.auto_merge:
            sid = match.situation_id
        else:
            # New situation (either genuinely new, or a fuzzy near-match we
            # refuse to auto-merge -- flag it for review instead).
            sid = f"sit-{ev.source}-{ev.source_event_id}"
            if match.confidence == "fuzzy":
                flags.append(match.reason)

        if sid not in situations:
            situations[sid] = new_situation_from(ev, sid, observed_at)
            before_snap.setdefault(sid, None)  # genuinely new this run
        else:
            if sid not in before_snap:
                before_snap[sid] = situations[sid].snapshot()
            situations[sid].apply_evidence(ev)

        index.add(ev, situations[sid])
        ev.situation_id = sid
        store.insert_evidence(conn, ev)

        if sid not in touched:
            touched.append(sid)
        flags_by_sid.setdefault(sid, []).extend(flags)

    changes: List[Change] = []
    for sid in touched:
        after = situations[sid]
        before = before_snap.get(sid)
        change = classify(before, after, flags=flags_by_sid.get(sid))
        if change.verdict == "WAKE":
            after.last_material_change = observed_at
        store.upsert_situation(conn, after)
        changes.append(change)

    conn.commit()
    return changes
