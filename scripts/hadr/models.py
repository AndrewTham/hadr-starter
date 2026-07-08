"""Domain types.

A `Situation` is one physical disaster; we mint its id and never key off a
feed's id. Raw feed records become append-only `Evidence` attached to it.

The three feeds are different epistemic layers -- USGS *measures* the hazard,
GDACS *models* impact -- so each source owns its own severity slot and we only
roll them up deterministically (`assessed_*`). Measured / modeled fields are
kept apart and never blended.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List, Optional

# Normalized impact levels, ordered so we can detect boundary crossings.
# GDACS has no "yellow"; its Green/Orange/Red map onto 0/2/3.
_IMPACT_RANK = {"none": 0, "green": 0, "yellow": 1, "orange": 2, "red": 3}
_RANK_NAME = {0: "green", 1: "yellow", 2: "orange", 3: "red"}

# Below this rank a situation is noise and never enters a report.
# yellow(1) == "PAGER yellow+, GDACS Orange+".
REPORT_THRESHOLD = 1


def impact_rank(level: Optional[str]) -> int:
    if not level:
        return 0
    return _IMPACT_RANK.get(level.lower(), 0)


@dataclass
class Evidence:
    """One observation of one source at one fetch. Append-only; never mutated."""

    evidence_id: str
    source: str  # "usgs" | "gdacs" | "reliefweb"
    source_event_id: str
    hazard_type: str
    observed_at: str  # our clock (ISO8601 Z)
    source_updated_at: Optional[str] = None
    source_episode_id: Optional[str] = None
    source_status: Optional[str] = None  # e.g. USGS automatic|reviewed
    origin_agency: Optional[str] = None  # e.g. GDACS EQ carries "NEIC" (== USGS)
    deleted: bool = False

    # physical location / time
    lat: Optional[float] = None
    lon: Optional[float] = None
    depth_km: Optional[float] = None
    place: Optional[str] = None
    iso3: Optional[str] = None
    onset_time: Optional[str] = None
    glide: Optional[str] = None

    # measured (instrument truth)
    magnitude: Optional[float] = None
    mag_type: Optional[str] = None

    # modeled impact (per source — never blended)
    pager_level: Optional[str] = None  # USGS PAGER colour
    gdacs_level: Optional[str] = None  # GDACS colour
    gdacs_score: Optional[float] = None

    # cross-source identity hints (rung 3): USGS `ids` tokens, or a GDACS
    # record's explicit upstream id.
    external_ids: List[str] = field(default_factory=list)

    title: Optional[str] = None
    raw: dict = field(default_factory=dict)
    situation_id: Optional[str] = None


@dataclass
class Situation:
    """Derived state for one physical disaster. Recomputed by folding Evidence."""

    situation_id: str
    hazard_type: str
    title: Optional[str] = None
    onset_time: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    place: Optional[str] = None
    iso3: Optional[str] = None
    glide: Optional[str] = None
    status: str = "active"  # active|escalated|downgraded|retracted|closed|superseded

    # measured
    magnitude: Optional[float] = None
    mag_type: Optional[str] = None
    depth_km: Optional[float] = None

    # per-source impact (kept separate; they disagree by design)
    pager_level: Optional[str] = None
    gdacs_level: Optional[str] = None
    gdacs_score: Optional[float] = None

    # which sources have contributed (drives "new source arrived" materiality)
    sources: List[str] = field(default_factory=list)

    first_seen: Optional[str] = None
    last_material_change: Optional[str] = None
    last_reported_at: Optional[str] = None
    last_reported_hash: Optional[str] = None

    # internal: newest evidence timestamp applied to the shared descriptive fields
    last_ev_ts: Optional[str] = None

    @property
    def assessed_rank(self) -> int:
        return max(impact_rank(self.pager_level), impact_rank(self.gdacs_level))

    @property
    def assessed_level(self) -> str:
        return _RANK_NAME[self.assessed_rank]

    @property
    def reportable(self) -> bool:
        return self.assessed_rank >= REPORT_THRESHOLD

    def snapshot(self) -> "Situation":
        """Deep copy for before/after diffing within a run."""
        return copy.deepcopy(self)

    def apply_evidence(self, ev: Evidence) -> None:
        """Fold one Evidence into this Situation.

        Each source owns its own severity slot. Shared descriptive/measured
        fields follow newest-evidence-wins. USGS is authoritative for magnitude
        (GDACS list payloads don't carry it), so GDACS never overwrites it.
        """
        if ev.source not in self.sources:
            self.sources.append(ev.source)

        # per-source severity
        if ev.source == "usgs" and ev.pager_level is not None:
            self.pager_level = ev.pager_level
        if ev.source == "gdacs":
            if ev.gdacs_level is not None:
                self.gdacs_level = ev.gdacs_level
            if ev.gdacs_score is not None:
                self.gdacs_score = ev.gdacs_score

        ts = ev.source_updated_at or ev.observed_at
        newer = self.last_ev_ts is None or (ts or "") >= self.last_ev_ts
        if newer:
            for f in (
                "mag_type",
                "depth_km",
                "lat",
                "lon",
                "place",
                "iso3",
                "onset_time",
                "title",
            ):
                v = getattr(ev, f)
                if v is not None:
                    setattr(self, f, v)
            # magnitude: USGS wins; only accept GDACS magnitude if we have none
            if ev.magnitude is not None and (
                ev.source == "usgs" or self.magnitude is None
            ):
                self.magnitude = ev.magnitude
            if ev.glide:
                self.glide = ev.glide
            self.last_ev_ts = ts

        if ev.deleted:
            self.status = "retracted"


def new_situation_from(ev: Evidence, situation_id: str, observed_at: str) -> Situation:
    sit = Situation(
        situation_id=situation_id,
        hazard_type=ev.hazard_type,
        first_seen=observed_at,
        last_material_change=observed_at,
    )
    sit.apply_evidence(ev)
    return sit
