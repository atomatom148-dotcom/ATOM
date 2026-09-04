# ATOM TRUE V9 — SIM-5W Read-Only Simulation Web Card Freeze

**Decision ID:** `ATOM-SIM5W-READ-ONLY-SIM-WEB-CARD-FREEZE-1`  
**Status:** ADOPTED BY AUTHOR OF RECORD — controlling upon Owner-approved merge  
**Author of record:** ChatGPT Pro  
**Drafted by:** Claude at Owner request; adopted with the author-of-record decisions below  
**Change class:** documentation only  
**Implementation base observed:** `c622296e7f9e020cf772b5f32c04073a61984cdb`  
**Phase opened on merge:** SIM-5W only, alongside SIM-5  
**Mode:** `PAPER_ONLY` — display only  
**Symbol/instrument:** `COIN` / one `COIN_SHARE`

## 0. Objective and boundary

SIM-5W makes already-durable SIM-5 terminal-resolution data visible. It adds exactly one compact, read-only card to the existing `quant/web.py` UI showing, per horizon, how many simulated positions have reached a durable terminal resolution and how those split between resolved and unresolved.

SIM-5W computes no simulator performance truth. It defines no new metric, performance measure, or evidence. It reads committed resolution rows, counts them, and renders them.

This freeze does not authorize SIM-6, E-2, E-3, E-4, Level-II mathematical use, V9 changes, family changes, broker actions, account actions, order submission, live positions, or any simulator mutation.

## 1. Dedicated read-only boundary

The existing web simulator publisher role must not be widened and no worker role may be reused. SIM-5W creates one dedicated least-privilege login role used only by the web card.

## 2. Exact new role

Migration `032_authorize_sim_web_reader.sql` creates exactly one role:

```text
atom_v9_sim_web_reader
```

with exactly:

```text
LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
```

No password appears in the migration. The Owner sets the password out of band.

The role receives exactly:

```text
GRANT USAGE  ON SCHEMA public TO atom_v9_sim_web_reader;
GRANT SELECT ON TABLE public.atom_v9_sim_resolutions TO atom_v9_sim_web_reader;
```

plus one minimum `FOR SELECT ... USING (true)` RLS policy on `public.atom_v9_sim_resolutions` scoped to `atom_v9_sim_web_reader`.

The role receives **no privilege and no policy on `public.atom_v9_sim_entries`**. It must not receive any `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, sequence privilege, function `EXECUTE`, schema `CREATE`, ownership, role membership, `BYPASSRLS`, or production-project privilege.

Migration 032 must not widen or alter `atom_v9_sim_runtime`, `atom_v9_sim_entry_runtime`, `atom_v9_sim_owner`, any existing grant, existing policy, existing table definition, or existing function.

## 3. Exact new credential

One new environment variable exists on the existing ATOM web service only:

```text
ATOM_V9_SIM_WEB_READONLY_DATABASE_URL
```

It is a role-bound session DSN for `atom_v9_sim_web_reader` on the existing isolated simulator project and must pass the existing simulator-DSN validation with `required_role="atom_v9_sim_web_reader"` and the existing project-ref proof.

No new service, Supabase project, database, data source, WebSocket, broker credential, or production credential is authorized.

## 4. Exact card contents

One card headed:

```text
SIM — PAPER ONLY
```

with exactly one status token: `LIVE`, `STALE`, or `NO DATA`.

Reuse the existing canonical six-horizon constant and existing `_table(...)` helper. Horizons render as columns in canonical order; metrics render as exactly three rows:

- `CLOSED` — count of durable terminal resolution rows for the horizon.
- `RESOLVED` — count with `resolution_status = 'RESOLVED'`.
- `UNRESOLVED` — count with `resolution_status IN ('UNRESOLVED_WINDOW_EXPIRED','UNRESOLVED_OBSERVATION_GAP')`.

No other number may be displayed. Explicitly forbidden: win rate, hit rate, accuracy, P&L, `return_bps`, averages, medians, drawdown, Sharpe or other ratios, expectancy, cumulative curves, per-trade rows, trade history, exit prices, quote data, charts, sparklines, filters, sorting controls, date pickers, drill-through, pagination, or any new page/route.

## 5. Exact status semantics

`STATUS` is presentational freshness only and is never persisted or treated as evidence.

```text
NO DATA — reader DSN absent/invalid, read failure, or zero resolution rows
LIVE    — rows exist and (now() - max(created_at)) <= 90 minutes
STALE   — rows exist and (now() - max(created_at)) > 90 minutes
```

`SIM5W_LIVE_WINDOW = 90 minutes` is frozen.

Any missing credential, validation failure, connection failure, timeout, or query error renders `NO DATA` and an empty count grid. The card must never raise into the page, degrade another card, or retry in a loop.

## 6. Exact read path

Per page render, at most one bounded read-only transaction may run, containing exactly:

```sql
SET LOCAL statement_timeout = '2000ms';

SELECT horizon, resolution_status, count(*) AS n
FROM public.atom_v9_sim_resolutions
GROUP BY horizon, resolution_status;

SELECT max(created_at) FROM public.atom_v9_sim_resolutions;
```

The transaction is read-only, closes or rolls back without commit, and takes no advisory lock. Horizons outside the canonical six are discarded rather than rendered.

SIM-5W must not query `atom_v9_sim_entries` at all. It must not access raw quotes, intents, publications, `record_json`, hashes, return calculations, exit prices, or any simulator write path. It must not re-derive or reinterpret simulator truth.

## 7. Visual footprint

Reuse the existing `_table(...)` helper and the same `<h2>` + table shape as V9 Directional Accuracy, with `section='sim_paper_only'`. No new CSS, layout primitive, template engine, rendering helper, page, or route. Horizons remain columns and `CLOSED`, `RESOLVED`, `UNRESOLVED` remain rows.

## 8. Exact implementation surface

Only these paths may change:

- `migrations/032_authorize_sim_web_reader.sql` — new. If ordinal 032 is occupied at implementation time, stop `BLOCKED` before editing.
- `quant/web.py` — reader connection factory, bounded read, count assembly, and one card block only.
- `tests/test_web_sim_card.py` — new focused tests.
- `tests/test_web.py` — only if an existing assertion is unavoidably invalidated, and only minimally.

If any other file is required, stop `BLOCKED` and return to ChatGPT Pro. No SIM worker, SIM entry/resolution contract, migration 031, isolation test, V9 mathematics, family, broker, or unrelated file is authorized.

## 9. Required tests

Before merge prove at minimum:

- absent, empty, malformed, wrong-role, wrong-project, and wrong-port DSNs yield `NO DATA` and zero I/O;
- a valid DSN bound to any role other than `atom_v9_sim_web_reader` is rejected before I/O;
- existing worker-credential presence rejection remains unchanged;
- exactly the statements in §6 run, in a read-only transaction, with no commit and no advisory lock;
- zero resolution rows renders `NO DATA` with blank counts, not zeros presented as evidence;
- fresh rows render `LIVE`, old rows render `STALE`, and the exact 90-minute boundary is tested;
- counts group correctly and `CLOSED = RESOLVED + UNRESOLVED` for each horizon;
- a canonical horizon absent from returned rows renders zero counts while rows exist elsewhere;
- connection failure, timeout, and query error each render `NO DATA` without affecting another card;
- no forbidden percentage, ratio, currency, `return_bps`, exit price, or per-trade value renders;
- six horizons render in canonical order;
- migration 032 grants exactly schema USAGE plus resolution-table SELECT, creates exactly the one resolution-table SELECT policy, creates no membership, grants no privilege on `atom_v9_sim_entries`, and leaves every pre-existing role/grant/policy unchanged;
- existing web and SIM isolation suites remain green.

## 10. Merge, provisioning, and deployment gate

1. Merge this documentation freeze and the minimum active-pointer authorization as documentation only.
2. One implementation PR on the §8 surface only.
3. Independent final-head review; every required check green; zero unresolved material threads.
4. ChatGPT Pro final architecture/freeze audit.
5. Owner merge.
6. Apply migration 032 exactly once to the isolated simulator Supabase project only.
7. Owner sets the `atom_v9_sim_web_reader` password and provisions `ATOM_V9_SIM_WEB_READONLY_DATABASE_URL` on the existing web service only.
8. Verify the exact privilege set, zero role membership, no entries-table privilege, and no pre-existing grant change.
9. Deploy the existing ATOM web service at the exact merged SHA.
10. Capture deployment proof and one rendered-card proof.

No step may be reordered or combined.

## 11. Acceptance proof

The SIM-5W receipt identifies the merged/deployed SHA, isolated simulator project identity, migration-032 application, exact reader privileges and zero membership, proof of no entries-table privilege and no pre-existing grant/policy change, exact read statements, rendered status/count grid, and confirmation that no write, lock, broker, account, order, production-V9, or simulator-mutation path is reachable from the card.

Any privilege beyond §2, statement beyond §6, forbidden display value, write capability, or production influence is `FAIL`/`INVALID`.

## 12. Frozen conclusion

> SIM-5W adds one passive card that counts committed SIM-5 terminal resolutions per horizon and says whether the data is fresh. It reads only `public.atom_v9_sim_resolutions` through one dedicated least-privilege role, computes no simulator performance metric, writes nothing, and changes no simulator behavior. Every performance question it might invite belongs to SIM-6.
