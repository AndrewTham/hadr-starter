"""SQLite persistence.

Three tables, per the design:
  situations  -- current derived state (one row per physical disaster)
  evidence    -- append-only observations (never UPDATEd)
  report_log  -- what we published and when (content hash -> "stay quiet")

Holding this state between runs is what lets us tell "revised" from "new" and,
later, "aged out of the rolling window" from "deleted".
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, List

from .models import Evidence, Situation

_SITUATION_COLS = [
    "situation_id", "hazard_type", "title", "onset_time", "lat", "lon", "place",
    "iso3", "glide", "status", "magnitude", "mag_type", "depth_km", "pager_level",
    "gdacs_level", "gdacs_score", "sources", "first_seen", "last_material_change",
    "last_reported_at", "last_reported_hash", "last_ev_ts",
]

_EVIDENCE_COLS = [
    "evidence_id", "situation_id", "source", "source_event_id", "source_episode_id",
    "source_status", "origin_agency", "deleted", "hazard_type", "lat", "lon",
    "depth_km", "place", "iso3", "onset_time", "glide", "magnitude", "mag_type",
    "pager_level", "gdacs_level", "gdacs_score", "external_ids", "observed_at",
    "source_updated_at", "title", "raw",
]

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS situations (
    {', '.join(c + (' TEXT PRIMARY KEY' if c == 'situation_id' else '') for c in _SITUATION_COLS)}
);
CREATE TABLE IF NOT EXISTS evidence (
    {', '.join(c + (' TEXT PRIMARY KEY' if c == 'evidence_id' else '') for c in _EVIDENCE_COLS)}
);
CREATE INDEX IF NOT EXISTS idx_evidence_situation ON evidence(situation_id);
CREATE TABLE IF NOT EXISTS report_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reported_at TEXT,
    content_hash TEXT,
    situation_ids TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def open_db(path: str) -> sqlite3.Connection:
    """Create the parent dir, connect, and ensure the schema exists.

    The one-liner both CLI entrypoints need to reach a ready-to-use connection.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = connect(path)
    init_schema(conn)
    return conn


def _situation_to_row(s: Situation) -> dict:
    row = {c: getattr(s, c) for c in _SITUATION_COLS if c != "sources"}
    row["sources"] = json.dumps(s.sources)
    return row


def _row_to_situation(row: sqlite3.Row) -> Situation:
    d = dict(row)
    d["sources"] = json.loads(d.get("sources") or "[]")
    return Situation(**d)


def _evidence_to_row(e: Evidence) -> dict:
    row = {}
    for c in _EVIDENCE_COLS:
        if c == "external_ids":
            row[c] = json.dumps(e.external_ids)
        elif c == "raw":
            row[c] = json.dumps(e.raw)
        elif c == "deleted":
            row[c] = 1 if e.deleted else 0
        else:
            row[c] = getattr(e, c)
    return row


def _row_to_evidence(row: sqlite3.Row) -> Evidence:
    d = dict(row)
    d["external_ids"] = json.loads(d.get("external_ids") or "[]")
    d["raw"] = json.loads(d.get("raw") or "{}")
    d["deleted"] = bool(d.get("deleted"))
    return Evidence(**d)


def upsert_situation(conn: sqlite3.Connection, s: Situation) -> None:
    row = _situation_to_row(s)
    cols = ", ".join(row)
    ph = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO situations ({cols}) VALUES ({ph})",
        list(row.values()),
    )


def insert_evidence(conn: sqlite3.Connection, e: Evidence) -> None:
    row = _evidence_to_row(e)
    cols = ", ".join(row)
    ph = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO evidence ({cols}) VALUES ({ph})",
        list(row.values()),
    )


def load_situations(conn: sqlite3.Connection) -> Dict[str, Situation]:
    rows = conn.execute("SELECT * FROM situations").fetchall()
    return {r["situation_id"]: _row_to_situation(r) for r in rows}


def load_evidence_by_situation(conn: sqlite3.Connection) -> Dict[str, List[Evidence]]:
    out: Dict[str, List[Evidence]] = {}
    for r in conn.execute("SELECT * FROM evidence").fetchall():
        out.setdefault(r["situation_id"], []).append(_row_to_evidence(r))
    return out
