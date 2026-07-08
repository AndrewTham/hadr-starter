# CLAUDE.md

<!-- Fill in at least three conventions below before your first prompt.
     An empty conventions file is also a decision — just not one you made. -->

## Language & tooling

- Python 3 for all deterministic scripts (`scripts/`). Chosen for feed/JSON/geo
  handling and clean GitHub Actions execution.
- State persists in a single SQLite database (stdlib `sqlite3`) — tables:
  `situations`, `evidence` (append-only), `report_log`.
- Prefer the standard library; add a dependency only when it earns its place.

## Test command

    python3 -m unittest discover -s scripts -t scripts -p 'test_*.py'

Deterministic logic (normalize, correlate, classify, pipeline) is unit-tested
with offline fixtures under `scripts/tests/`. No network in tests.

## Conventions

## Deviations policy
