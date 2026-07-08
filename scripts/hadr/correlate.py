"""Correlation ladder: decide which Situation a piece of Evidence belongs to.

Only high-confidence rungs auto-merge. Loose spatial/temporal guesses are
returned as ``fuzzy`` so the caller can FLAG them for review instead of
silently fusing two records (the failure mode that turns one flood into two,
or two distinct quakes into one).

    rung 1  same source + same source_event_id      -> exact       (an update)
    rung 2  matching non-empty GLIDE                 -> cross_source
    rung 3a GDACS upstream id in USGS `ids` tokens   -> cross_source
    rung 3b cross-source EQ coincidence (NEIC==USGS) -> cross_source
    rung 4  same hazard, near in space+time          -> fuzzy (FLAG, no merge)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import Evidence, Situation
from .util import haversine_km, parse_epoch

# rung 3b / 4 tolerances. NEIC-sourced GDACS shares the USGS origin solution,
# so a cross-source EQ this close is the same event, not a coincidence.
EQ_TIME_TOL_S = 120
EQ_DIST_TOL_KM = 100.0
EQ_MAG_TOL = 0.5
# rung 4 (fuzzy, non-identity) is deliberately looser and never auto-merges.
FUZZY_TIME_TOL_S = 3600
FUZZY_DIST_TOL_KM = 150.0


@dataclass
class Match:
    situation_id: Optional[str]
    confidence: Optional[str]  # "exact" | "cross_source" | "fuzzy" | None
    rung: Optional[str] = None
    reason: str = ""

    @property
    def auto_merge(self) -> bool:
        return self.confidence in ("exact", "cross_source")


class CorrelationIndex:
    """Lookup structures over the current situations, rebuilt as they change."""

    def __init__(self):
        self._exact: Dict[tuple, str] = {}  # (source, source_event_id) -> sid
        self._tokens: Dict[str, str] = {}  # identity token -> sid
        self._glide: Dict[str, str] = {}  # glide -> sid
        # earthquakes, for the coincidence rungs: (sid, source, lat, lon, epoch)
        self._eq: List[tuple] = []

    def add(self, ev: Evidence, sit: Situation) -> None:
        sid = sit.situation_id
        self._exact[(ev.source, ev.source_event_id)] = sid
        # a situation is findable by any id token it has been seen under
        self._tokens[ev.source_event_id] = sid
        for tok in ev.external_ids:
            self._tokens[tok] = sid
        if ev.glide:
            self._glide[ev.glide] = sid
        if sit.hazard_type == "earthquake":
            self._eq.append(
                (sid, ev.source, sit.lat, sit.lon, parse_epoch(sit.onset_time))
            )

    def match(self, ev: Evidence) -> Match:
        # rung 1 -- same source, same id: this is an update to a known event.
        sid = self._exact.get((ev.source, ev.source_event_id))
        if sid:
            return Match(sid, "exact", "1", "same source + source_event_id")

        # rung 2 -- GLIDE, the intended cross-feed key (rarely populated).
        if ev.glide and ev.glide in self._glide:
            return Match(self._glide[ev.glide], "cross_source", "2", f"GLIDE {ev.glide}")

        # rung 3a -- explicit upstream id (GDACS -> USGS) matches a known token.
        for tok in [ev.source_event_id, *ev.external_ids]:
            other = self._tokens.get(tok)
            if other and other != self._exact.get((ev.source, ev.source_event_id)):
                return Match(other, "cross_source", "3a", f"shared id token {tok}")

        # rung 3b -- cross-source earthquake coincidence. Only fires across
        # different sources (never USGS<->USGS, which would merge aftershocks).
        if ev.hazard_type == "earthquake":
            t = parse_epoch(ev.onset_time)
            for sid2, src2, lat2, lon2, t2 in self._eq:
                if src2 == ev.source:
                    continue  # cross-source only
                if t is None or t2 is None or abs(t - t2) > EQ_TIME_TOL_S:
                    continue
                dist = haversine_km(ev.lat, ev.lon, lat2, lon2)
                if dist is None or dist > EQ_DIST_TOL_KM:
                    continue
                return Match(
                    sid2,
                    "cross_source",
                    "3b",
                    f"cross-source EQ within {dist:.0f}km / {abs(t - t2):.0f}s",
                )

        # rung 4 -- loose same-hazard proximity. Surfaced, never auto-merged.
        # (This slice only fuzzy-matches earthquakes; other hazards fall through.)
        if ev.hazard_type == "earthquake":
            t = parse_epoch(ev.onset_time)
            for sid2, src2, lat2, lon2, t2 in self._eq:
                if src2 == ev.source:
                    continue  # cross-source only
                if t is None or t2 is None or abs(t - t2) > FUZZY_TIME_TOL_S:
                    continue
                dist = haversine_km(ev.lat, ev.lon, lat2, lon2)
                if dist is not None and dist <= FUZZY_DIST_TOL_KM:
                    return Match(
                        sid2,
                        "fuzzy",
                        "4",
                        f"possible duplicate of {sid2} (~{dist:.0f}km apart)",
                    )

        return Match(None, None)
