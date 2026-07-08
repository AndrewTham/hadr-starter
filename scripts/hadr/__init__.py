"""HADR monitor — first vertical slice.

Pipeline: fetch (USGS + GDACS) -> normalize into Evidence -> correlate onto
Situations (rungs 1 & 3) -> persist to SQLite -> classify material change
(WAKE / QUIET / FLAG). See implementation-notes.md for the design rationale.
"""
