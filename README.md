# ATOM V9 Thin

Quant research pipeline only.

## Speed Gate 2 evidence causality

Live COIN evidence is captured into immutable, bounded envelopes and delivered
asynchronously to the evidence ledger. Raw forecast `created_epoch` remains the
quote capture time; it is **not** a database-availability timestamp. Therefore
this release does not claim exact historical V2 replay causality for delayed raw
forecast/outcome delivery. Such a claim requires a separate evidence-contract
compatibility change adding immutable availability timestamps. Missing live
envelopes are never backfilled from later quotes.

```
COIN snapshot → Unified Quant → exact-six ledger → truthful status
```

## Laws
See FREEZE.md. `SIMULATION_FREEZE.md` is controlling law for simulator work.
Phase-specific freezes and amendments live in `docs/`.

## Layout
```
FREEZE.md                 architecture law
SIMULATION_FREEZE.md      paper-simulator law
PHASES.md                 phase ledger
docs/                     freeze amendments, audits, spike write-ups
migrations/               numbered SQL migrations (001–028)
supabase/migrations/      timestamped SQL migrations (historical replay)
quant/                    runtime package
  web.py                  thin web surface (atom-v9-thin)
  live_market.py          market pollers and live state
  evidence*.py            evidence ledger and outbox
  v9_*.py                 V9 production, V1–V4D, SIM-1..4
  historical_*.py         historical replay and H2-D canaries
  q1_*.py … q12_*.py      the twelve fixed-equation families
  v4_state_worker.py      derived-state worker (ATOM-matrix V4)
  v9_sim4_worker.py       isolated SIM-4 entry worker (atom-v9-sim4-worker)
spikes/                   feasibility scripts, not runtime
tests/                    pytest suite
```

## Run tests
```
PYTHONPATH=. python -m pytest -q
```
CI (`.github/workflows/ci.yml`) runs the same command against a PostgreSQL 16
service with `H2C_TEST_DATABASE_URL` set.

## Database migrations

Apply `migrations/001` … `028` in numeric order, then `supabase/migrations/` in
timestamp order. Two files use `CREATE INDEX CONCURRENTLY` and must run outside
a transaction (Supabase SQL Editor or psql, not the MCP migration tools):
`migrations/023_index_v2_external_rebuild_pagination.sql` and
`migrations/025_index_historical_replay_scoring.sql`. Verify `pg_index.indisvalid`
afterwards.

## Live Q1-Q3 runtime

Install `requirements.txt`, apply the migrations above, and
set `DATABASE_URL`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY`. Then start the single-process
standard-library HTTPS polling runtime (Render supplies `PORT`):

```
python -m quant.web --host 0.0.0.0 --port "$PORT"
```

The optional derived-state background process uses the same `DATABASE_URL`:

```
python -m quant.v4_state_worker
```

Keep the web-hosted builder enabled until that process is provisioned. Then set
`ATOM_V4_STATE_BUILDER_EXTERNAL=1` on the web service, verify that deployment,
and finally set `ATOM_V4_STATE_WORKER_ENABLED=1` on the background process.

## Not included
Charts, Research OS, Scout/Shadow, Direction Brain, broker, fat migration branch.
