"""Material-change classifier.

Given a Situation's state *before* this run and *after* folding in this run's
evidence, decide whether the change is worth waking the reporter for. This is
the deterministic gate the design puts in scripts/: the model only ever runs on
WAKE and FLAG. The materiality thresholds below *are* the definition of
"changed" -- change them here, not in a prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .models import Situation
from .util import haversine_km

# per-field materiality
MAG_MATERIAL_DELTA = 0.3  # smaller magnitude revisions are solution noise
LOC_MATERIAL_KM = 50.0  # smaller relocations are noise

WAKE = "WAKE"
QUIET = "QUIET"
FLAG = "FLAG"


@dataclass
class Change:
    situation_id: str
    verdict: str  # WAKE | QUIET | FLAG
    kind: str  # new | escalation | downgrade | retraction | update | noise | ambiguous
    detail: str
    from_level: Optional[str] = None
    to_level: Optional[str] = None


def _material_fields(before: Situation, after: Situation) -> List[str]:
    reasons = []
    if before.magnitude is not None and after.magnitude is not None:
        if abs(after.magnitude - before.magnitude) >= MAG_MATERIAL_DELTA:
            reasons.append(
                f"magnitude {before.magnitude}->{after.magnitude}"
            )
    dist = haversine_km(before.lat, before.lon, after.lat, after.lon)
    if dist is not None and dist >= LOC_MATERIAL_KM:
        reasons.append(f"relocated {dist:.0f}km")
    new_sources = [s for s in after.sources if s not in before.sources]
    if new_sources:
        reasons.append(f"new source: {','.join(new_sources)}")
    return reasons


def classify(
    before: Optional[Situation],
    after: Situation,
    flags: Optional[List[str]] = None,
) -> Change:
    sid = after.situation_id
    flags = flags or []

    # Ambiguity always wins: a low-confidence correlation or parse issue is not
    # something a deterministic gate should resolve on its own.
    if flags:
        return Change(sid, FLAG, "ambiguous", "; ".join(flags))

    # Retraction / deletion.
    if after.status == "retracted":
        # Fire once: re-seeing an already-retracted event is not news.
        if before is not None and before.status == "retracted":
            return Change(sid, QUIET, "retraction", "already retracted")
        was_reported = before is not None and (
            before.reportable or before.last_reported_at
        )
        if was_reported:
            return Change(
                sid,
                WAKE,
                "retraction",
                "previously reported event was deleted/retracted",
                from_level=before.assessed_level,
            )
        return Change(sid, QUIET, "retraction", "sub-threshold event retracted")

    # Brand-new situation.
    if before is None:
        if after.reportable:
            return Change(
                sid, WAKE, "new", "new reportable event", to_level=after.assessed_level
            )
        return Change(
            sid, QUIET, "new", "new sub-threshold event", to_level=after.assessed_level
        )

    # Existing situation: impact level change dominates.
    b, a = before.assessed_rank, after.assessed_rank
    if a > b and a >= after_threshold():
        return Change(
            sid,
            WAKE,
            "escalation",
            f"impact {before.assessed_level}->{after.assessed_level}",
            from_level=before.assessed_level,
            to_level=after.assessed_level,
        )
    if a < b and b >= after_threshold():
        return Change(
            sid,
            WAKE,
            "downgrade",
            f"impact {before.assessed_level}->{after.assessed_level}",
            from_level=before.assessed_level,
            to_level=after.assessed_level,
        )

    # Level unchanged. Only material for a situation that is (still) reportable.
    if after.reportable:
        reasons = _material_fields(before, after)
        if reasons:
            return Change(
                sid, WAKE, "update", "; ".join(reasons), to_level=after.assessed_level
            )

    return Change(sid, QUIET, "noise", "within-noise revision")


def after_threshold() -> int:
    # Imported lazily to keep the threshold defined in one place (models).
    from .models import REPORT_THRESHOLD

    return REPORT_THRESHOLD
