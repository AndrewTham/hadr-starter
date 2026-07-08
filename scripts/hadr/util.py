"""Small pure helpers: time parsing and great-circle distance.

Kept dependency-free (stdlib only) so the deterministic core stays trivial to
test and to run in CI without an install step.
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Optional


def ms_to_iso(ms: Optional[int]) -> Optional[str]:
    """USGS epoch-milliseconds (UTC) -> ISO8601 'Z' string."""
    if ms is None:
        return None
    return _dt.datetime.fromtimestamp(ms / 1000, tz=_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def parse_epoch(ts: Optional[str]) -> Optional[float]:
    """Parse a timestamp to epoch seconds (UTC).

    Accepts ISO8601 with a 'Z' or offset, and naive 'YYYY-MM-DDTHH:MM:SS'
    (GDACS emits these without a timezone marker — the design assumes UTC).
    """
    if not ts:
        return None
    s = ts.strip().replace("Z", "+00:00")
    try:
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.timestamp()


def haversine_km(
    lat1: Optional[float],
    lon1: Optional[float],
    lat2: Optional[float],
    lon2: Optional[float],
) -> Optional[float]:
    """Great-circle distance in km, or None if any coordinate is missing."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))
