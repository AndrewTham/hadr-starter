"""Turn raw feed features into normalized `Evidence`.

Pure functions (no I/O) so the trickiest parsing is unit-tested directly.
Both feeds are GeoJSON FeatureCollections; coordinates are [lon, lat, depth].
"""
from __future__ import annotations

from typing import List

from .models import Evidence
from .util import ms_to_iso

# GDACS eventtype code -> normalized hazard.
GDACS_HAZARD = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
    "TS": "tsunami",
}


def _coords(feature: dict):
    geom = feature.get("geometry") or {}
    c = geom.get("coordinates") or []
    lon = c[0] if len(c) > 0 else None
    lat = c[1] if len(c) > 1 else None
    depth = c[2] if len(c) > 2 else None
    return lon, lat, depth


def usgs_feature_to_evidence(feature: dict, observed_at: str) -> Evidence:
    props = feature.get("properties") or {}
    lon, lat, depth = _coords(feature)
    eid = str(feature.get("id"))
    # `ids` is a comma-wrapped list like ",ci41287863,us6000tafd," -- these are
    # the identity tokens a GDACS record's upstream id can match against.
    ids = [t for t in (props.get("ids") or "").split(",") if t]
    return Evidence(
        evidence_id=f"ev-usgs-{eid}-{props.get('updated')}",
        source="usgs",
        source_event_id=eid,
        hazard_type="earthquake",
        observed_at=observed_at,
        source_updated_at=ms_to_iso(props.get("updated")),
        source_status=props.get("status"),
        deleted=bool(props.get("_deleted")),  # delete-feed / fixture marker
        lat=lat,
        lon=lon,
        depth_km=depth,
        place=props.get("place"),
        onset_time=ms_to_iso(props.get("time")),
        magnitude=props.get("mag"),
        mag_type=props.get("magType"),
        pager_level=props.get("alert"),  # PAGER: green/yellow/orange/red or null
        external_ids=ids,
        title=props.get("title"),
        raw=feature,
    )


def gdacs_feature_to_evidence(feature: dict, observed_at: str) -> Evidence:
    props = feature.get("properties") or {}
    lon, lat, _ = _coords(feature)
    etype = props.get("eventtype")
    eid = str(props.get("eventid"))
    episode = props.get("episodeid")
    # rung-3 hint: capture any explicit upstream id GDACS exposes. Field names
    # vary across GDACS payloads, so we probe a few and keep whatever is there.
    external = []
    for key in ("usgsid", "sourceid", "originalid", "eventsource"):
        v = props.get(key)
        if v:
            external.append(str(v))
    return Evidence(
        evidence_id=f"ev-gdacs-{eid}-{episode}",
        source="gdacs",
        source_event_id=eid,
        source_episode_id=str(episode) if episode is not None else None,
        hazard_type=GDACS_HAZARD.get(etype, "other"),
        observed_at=observed_at,
        source_updated_at=props.get("datemodified"),
        origin_agency=props.get("source"),  # e.g. "NEIC" == USGS, for EQ
        deleted=bool(props.get("_deleted")),
        lat=lat,
        lon=lon,
        place=props.get("name"),
        iso3=props.get("iso3"),
        onset_time=props.get("fromdate"),
        glide=(props.get("glide") or None),
        gdacs_level=props.get("alertlevel"),
        gdacs_score=props.get("alertscore"),
        external_ids=external,
        title=props.get("name"),
        raw=feature,
    )


def normalize(source: str, features: List[dict], observed_at: str) -> List[Evidence]:
    fn = {
        "usgs": usgs_feature_to_evidence,
        "gdacs": gdacs_feature_to_evidence,
    }[source]
    return [fn(f, observed_at) for f in features]
