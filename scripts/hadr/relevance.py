"""Singapore relevance lens.

The pipeline decides *what changed* globally (WAKE/QUIET/FLAG). This module
decides, for a Singapore-based duty officer, *how much a changed situation
matters to Singapore and the region* — and it does so only to **tier and
order** events, never to include or exclude them. Inclusion is gated upstream
by impact (see `Situation.reportable`): a distant but severe event (SCDF has
deployed as far as Türkiye) still surfaces — it just sorts below the regional
ones.

Distance alone is deliberately NOT the relevance score — that would repeat the
"magnitude != impact" category error. Region is a coarse, explainable lens on
top of the impact gate. Hazard-specific pathways (transboundary haze, tsunami)
are deferred until the feeds carry the data to support them — see
implementation-notes.md.
"""
from __future__ import annotations

from typing import List, Optional

from .models import Situation
from .util import haversine_km

# Singapore. Relevance is measured from here.
SINGAPORE = (1.3521, 103.8198)

# Within this radius, a situation can directly affect Singapore or its
# immediate neighbourhood (peninsular Malaysia, Riau, Batam, southern Thailand,
# the Singapore Strait). A deliberately generous "next door" ring.
DIRECT_RADIUS_KM = 500.0

# Southeast Asia / ASEAN operating region as a lat/lon box: Myanmar in the
# west through the Philippines in the east, southern China down through
# Indonesia. Used as the REGIONAL gate because it works even when a feed gives
# no country code (USGS situations have iso3 = None).
SEA_LAT_MIN, SEA_LAT_MAX = -11.0, 29.0
SEA_LON_MIN, SEA_LON_MAX = 90.0, 142.0

# ASEAN member states (ISO-3166 alpha-3). Enrichment only — a bonus signal when
# a country code is present; never the gate (see module docstring).
ASEAN_ISO3 = {
    "BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM", "TLS",
}

TIER_ORDER = {"DIRECT": 0, "REGIONAL": 1, "GLOBAL": 2}


def sg_distance_km(sit: Situation) -> Optional[float]:
    """Great-circle km from Singapore, or None if the situation has no coords."""
    if sit.lat is None or sit.lon is None:
        return None
    return haversine_km(SINGAPORE[0], SINGAPORE[1], sit.lat, sit.lon)


def _in_sea_box(sit: Situation) -> bool:
    if sit.lat is None or sit.lon is None:
        return False
    return (SEA_LAT_MIN <= sit.lat <= SEA_LAT_MAX) and (SEA_LON_MIN <= sit.lon <= SEA_LON_MAX)


def sg_tier(sit: Situation) -> str:
    """Classify a situation as DIRECT / REGIONAL / GLOBAL for Singapore.

    Coordinates drive the decision; iso3 is a fallback only when coords are
    missing (it can never promote a situation to DIRECT on its own).
    """
    d = sg_distance_km(sit)
    if d is not None:
        if d <= DIRECT_RADIUS_KM:
            return "DIRECT"
        if _in_sea_box(sit):
            return "REGIONAL"
        return "GLOBAL"
    # No coordinates: lean on the country code if we have one.
    if sit.iso3 and sit.iso3.upper() in ASEAN_ISO3:
        return "REGIONAL"
    return "GLOBAL"


def sg_reasons(sit: Situation) -> List[str]:
    """Human-readable justification for the tier — goes in the brief."""
    reasons: List[str] = []
    d = sg_distance_km(sit)
    if d is not None:
        reasons.append(f"{d:,.0f} km from Singapore")
        if d > DIRECT_RADIUS_KM and _in_sea_box(sit):
            reasons.append("inside the SE-Asia operating region")
    if sit.iso3:
        code = sit.iso3.upper()
        if code in ASEAN_ISO3:
            reasons.append(f"ASEAN member ({code})")
        else:
            reasons.append(f"country {code}")
    if not reasons:
        reasons.append("no location on record")
    return reasons


def rank_for_singapore(sits: List[Situation]) -> List[Situation]:
    """Order situations for a Singapore reader: tier, then impact, then nearness.

    Does NOT filter — every situation passed in is returned, reordered. Callers
    decide inclusion (by impact / material change) before ranking.
    """
    def key(s: Situation):
        d = sg_distance_km(s)
        return (
            TIER_ORDER.get(sg_tier(s), 9),
            -s.assessed_rank,
            d if d is not None else float("inf"),
        )

    return sorted(sits, key=key)
