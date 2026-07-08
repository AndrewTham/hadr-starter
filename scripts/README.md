Deterministic checks live here — anything that must give the same answer twice does not belong in a prompt.

## First slice: feed pipeline

`hadr/` is the deterministic core; `run_slice.py` runs one pass and prints the
classified changeset (WAKE / QUIET / FLAG). The model only ever consumes WAKE
and FLAG — QUIET changes are persisted and never surfaced.

    fetch (USGS + GDACS) → normalize → correlate → SQLite → classify change

Modules:

| File | Role |
| --- | --- |
| `hadr/models.py` | `Situation` / `Evidence` types, impact ranking, report threshold |
| `hadr/normalize.py` | raw GeoJSON feature → `Evidence` (pure) |
| `hadr/correlate.py` | correlation ladder; only high-confidence rungs auto-merge |
| `hadr/classify.py` | material-change classifier; the thresholds *are* the definition of "changed" |
| `hadr/store.py` | SQLite: `situations`, append-only `evidence`, `report_log` |
| `hadr/pipeline.py` | orchestration → classified changeset |
| `hadr/fetch.py` | live fetch (stdlib urllib) + fixture load |

Run it:

    # offline, deterministic (fixtures under tests/):
    python3 scripts/run_slice.py --db /tmp/hadr.db \
        --usgs scripts/tests/fixtures/usgs_run1.json \
        --gdacs scripts/tests/fixtures/gdacs_run1.json \
        --observed-at 2026-07-07T12:00:00Z

    # live:
    python3 scripts/run_slice.py --db data/hadr.db --fetch

    # tests:
    python3 -m unittest discover -s scripts -t scripts -p 'test_*.py'

The SQLite file is the state that lets a second run tell "revised" from "new".
It is gitignored — delete it to start clean.
