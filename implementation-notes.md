# Implementation notes

Kept by the agent, reviewed by you. One entry per working block.

## Decisions

### 2026-07-08 — Data model & change-detection design

- **Core model: `Situation`, not `Event`.** One `Situation` per physical
  disaster; we mint its `situation_id` (never key off a feed id). Raw feed
  records become append-only `Evidence` attached to it. Rationale: the three
  feeds are different epistemic layers — USGS *measures* the hazard, GDACS
  *models* impact, ReliefWeb *reports* the human situation — not three copies
  of one event. Field groups `measured` / `modeled` / `narrative` never blend.
- **Runtime: Python 3. State store: SQLite** (`situations`, `evidence`
  append-only, `report_log` with content hash). "Gone from a feed" resolves as
  *deleted* (absent from a full-window fetch **and** source delete signal →
  retract) vs *aged-out* (merely absent → closed, no correction).
- **Impact filter is impact-based, not magnitude.** Keep `usgs_pager`
  (fatality/economic-loss model) and `gdacs` (national coping-capacity model)
  separate — they disagree by design. `assessed` level is a deterministic
  rollup (`max`) that records which source it came from.
- **Correlation ladder** (auto-merge only rungs 1–3): (1) same source +
  `source_event_id`; (2) matching non-empty GLIDE; (3) GDACS NEIC id ∈ USGS
  `ids`; (4) fuzzy spatial+temporal+type → **FLAG for review, never
  auto-merge.**
- **Aftershocks: one `Situation` per mainshock**, aftershocks as child
  evidence; promote any aftershock that itself crosses an impact threshold.
  Cascades (EQ→tsunami→landslide) linked via `related_to`, not force-merged.
- **Material-change classifier** lives in `scripts/`, unit-tested, emits a
  classified changeset → **WAKE / QUIET / FLAG**. The model runs only on WAKE
  and FLAG. Per-field materiality: impact level = any boundary crossing;
  magnitude |Δ|≥0.3; location Δ≥50 km; depth only if shallow↔deep flips;
  auto→reviewed only if paired with a field change; deletion/retraction always;
  new narrative source always. This config *is* the definition of "changed."

### 2026-07-08 — First vertical slice built (`scripts/hadr/`)

Implemented fetch (USGS `all_day` + GDACS `EVENTS4APP`) → normalize → correlate
(rungs 1, 3a, 3b; rung 4 surfaces as FLAG) → SQLite → classify → changeset.
21 unit tests (offline fixtures) pass. **Validated live**: one real pass ingested
235 USGS + 100 GDACS records → 318 situations, correctly suppressing 315
sub-threshold events and surfacing 3 reportable ones. **Cross-source dedup fired
on real data**: 17 earthquakes reported by both feeds were fused into single
situations (would otherwise be 34 double-counts). Re-running identical input is
silent (0 WAKE/FLAG), satisfying "stay quiet when nothing changed."

### 2026-07-08 — Singapore relevance gate + brief (`relevance.py`, `sg_brief.py`)

First decision layer on top of the pipeline, for the 08:30 SGT reader.
- **Relevance only tiers/orders; impact gates inclusion.** `sg_tier()` →
  DIRECT / REGIONAL / GLOBAL from distance-to-Singapore + an explicit SE-Asia
  lat/lon box; `iso3` is enrichment only (USGS situations have `iso3=None`, so
  it can't be the gate). Distance is deliberately *not* the score — that would
  repeat "magnitude ≠ impact". A distant severe event (e.g. Türkiye) still
  surfaces as GLOBAL because impact, not proximity, decides inclusion.
- **`sg_brief.py` is the deterministic gate for `sitrep.yml` TODO 1.** It runs
  one pass, keeps the pipeline's WAKE items, tiers them for Singapore, prints a
  brief, and **exits 0 (report) / 1 (quiet)** — no model. SGT stamp derives from
  `observed_at` via `zoneinfo("Asia/Singapore")` (fixed +8 fallback; no DST), so
  re-runs stay byte-identical. Cron for the workflow is `30 0 * * *` UTC.
- **Validated live**: real pass tiered a RED cyclone and a China flood as
  REGIONAL and correctly dropped "Forest fires in France" to GLOBAL; identical
  re-run gated quiet (exit 1). 9 new unit tests (30 total) pass.

Deferred to later slices (need data we don't yet carry):
- **Transboundary haze** pathway — GDACS `iso3` is country-level (can't tell a
  Sumatran peat fire from a Papuan one) and GDACS barely detects peat fires; the
  real signal is ASMC hotspots / PSI. Needs sub-national + seasonal data.
- **Tsunami** pathway — first surface the USGS `tsunami` flag (currently dropped
  in `normalize.py`) rather than inferring from magnitude/depth.
- Narrative + `dashboard.html` via a `/sitrep` skill (TODO 2) — the operator
  plays that loop for now.

### 2026-07-08 — Self-review of PR #3 (fixes applied)

Multi-angle review of the first-slice diff before merge. Fixed:
- `util.haversine_km` clamps the term to ≤1 — a quake near Singapore's SE-Pacific
  antipode no longer risks a math-domain crash in the relevance distance calc.
- `correlate` earthquake index is now per-situation with a sources set + a
  magnitude gate: a merged USGS+GDACS situation can't absorb a distinct
  same-feed quake, and co-located quakes >0.5 M apart aren't fused.
- `models.apply_evidence` compares timestamps by parsed epoch, not raw strings
  (USGS 'Z' vs GDACS naive no longer mis-order "newest wins").
- GDACS `evidence_id` includes `datemodified` so a same-episode update stays
  append-only instead of REPLACE-ing the prior row.
- Extracted shared CLI helpers (`fetch.load_feeds`, `store.open_db`,
  `util.now_iso`) — `run_slice` and `sg_brief` no longer duplicate feed/db setup.
- Strengthened the SGT test to assert the real 08:00 conversion. 37 tests pass.

Deferred: retraction of a *previously-reported-then-decayed* event stays silent
because it keys on the unwired `report_log` / `last_reported_at` (see Deviations);
resolved when report_log lands.

## Open questions

- Fuzzy-correlation thresholds (~100 km / ~1 h) are guesses — tune against real
  dual-sourced (USGS+GDACS) events before trusting rung 4.
- Report-entry threshold (PAGER yellow+ vs orange+; GDACS Orange+) needs
  calibration against actual daily volume.
- "Feed down at 08:30" behaviour: report the outage explicitly (never imply
  all-clear); still need a staleness threshold for treating cached state as
  usable.
- ReliefWeb `appname` approval pending (form + email, required since
  2025-11-01). Build against the RSS feed now behind an interface; swap to the
  API once approved.
- How often is GLIDE actually populated across the three feeds? Quantify before
  relying on rung 2.

## Deviations

<!-- Anything built that departs from the PRD or CLAUDE.md is recorded here,
     with the reason. An undocumented deviation is a bug. -->

- **Deletion is driven by a `_deleted` marker, not USGS's real delete feed.**
  The summary GeoJSON simply drops deleted events; the slice models the
  retraction *path* correctly but does not yet subscribe to the delete signal.
  Next: wire the USGS delete feed (or window reconciliation) so real deletions
  are detected. Until then, live runs never emit retractions.
- **Aged-out reconciliation not implemented.** A situation that falls out of
  the rolling window is not yet transitioned to `closed`; only explicitly-seen
  events are updated. Needs a window-horizon sweep.
- **`report_log` table exists but is not written yet.** "Was this reported?"
  currently uses `reportable` as a proxy. Wiring the content-hash log is the
  next step for the morning routine's true idempotency (and drives the
  "publish nothing" decision).
- **rung 3a (explicit upstream id) implemented but unused on live data** — the
  `EVENTS4APP` list payload doesn't expose the USGS id under the field names we
  probe, so the 17 live merges came via rung 3b (spatial+temporal coincidence,
  justified by shared NEIC provenance). Fetching the GDACS event detail would
  restore the explicit-id path.
