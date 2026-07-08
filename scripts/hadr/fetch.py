"""Feed I/O. Live fetch via stdlib urllib (no dependency), plus fixture load
so the whole slice runs offline in CI and in tests.
"""
from __future__ import annotations

import json
import urllib.request
from typing import List

USGS_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

_UA = {"User-Agent": "hadr-monitor/0.1 (course project)"}


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (known hosts)
        return json.loads(resp.read().decode("utf-8"))


def load_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def features(payload: dict) -> List[dict]:
    """Both feeds return a GeoJSON FeatureCollection."""
    return payload.get("features") or []


def load_feeds(usgs_path=None, gdacs_path=None, do_fetch=False) -> dict:
    """Assemble the {source: [features]} dict from live feeds or fixture files.

    Shared by the CLI entrypoints (run_slice, sg_brief) so feed handling lives
    in one place. Callers validate that at least one input was given.
    """
    raw = {}
    if do_fetch:
        raw["usgs"] = features(fetch_json(USGS_URL))
        raw["gdacs"] = features(fetch_json(GDACS_URL))
    else:
        if usgs_path:
            raw["usgs"] = features(load_json_file(usgs_path))
        if gdacs_path:
            raw["gdacs"] = features(load_json_file(gdacs_path))
    return raw
