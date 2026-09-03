# ATOM TRUE V9 — SIM-4A Exact SIM-5 Six-Horizon Causal Resolution Freeze

**Decision ID:** `ATOM-SIM-4A-EXACT-SIM5-RESOLUTION-FREEZE-1`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** This text grants no implementation authority before its Owner-approved merge.  
**Author:** ChatGPT Pro  
**Phase opened on merge:** SIM-5 only  
**Mode:** `PAPER_ONLY`  
**Symbol/instrument:** `COIN` / one `COIN_SHARE`

## 0. Objective and sequence

SIM-5 closes only the positions successfully opened by SIM-4. It adds one immutable terminal resolution for each durable SIM-4 entry whose `entry_status` is exactly `ENTERED`, then releases that horizon for later SIM-4 entries only after the terminal resolution is durable.

This freeze does not authorize SIM-6, E-2, E-3, E-4, Level-II mathematical use, V9 changes, family changes, broker actions, account actions, live positions, or order submission.

The official E-1 scorecard receipt is preserved at `docs/e-1-official-scorecard-receipt-2026-09-03.json`. Its `INSUFFICIENT` cells are not loosened, rescored, or rerun by SIM-5.

The already-authorized Level-II durable capture remains an independent observer-only sink. It may continue collecting data, but it is not a SIM-5 source, signal, consumer, prerequisite, or blocker.

## 1. Existing boundaries preserved

All merged SIM-1 through SIM-4 contracts remain unchanged except where this freeze explicitly adds the SIM-5 terminal-resolution layer.

SIM-5 uses:

- the existing isolated simulator Supabase project only;
- the existing dedicated Render background worker whose command remains `python -m quant.v9_sim4_worker`;
- the existing `atom_v9_sim_entry_runtime` database role;
- the existing SIM-4 Alpaca SIP data-only WebSocket and `SimulationExecutableQuote` contract;
- the existing six horizons, in order: `30S`, `1M`, `5M`, `15M`, `30M`, `1H`;
- the existing per-horizon advisory-lock keys and single-worker ownership fence; and
- the existing V4A canonicalization functions without modification.

No new Render service, Supabase project, database role, market-data credential, WebSocket connection, broker credential, or production credential is authorized.

## 2. Exact terminal statuses

Every SIM-5 resolution has exactly one of these terminal statuses:

- `RESOLVED`
- `UNRESOLVED_WINDOW_EXPIRED`
- `UNRESOLVED_OBSERVATION_GAP`

No other SIM-5 status is valid.

Only a SIM-4 entry with `entry_status = ENTERED` receives a SIM-5 resolution. Skipped SIM-4 entries never receive one.

Exactly one terminal resolution may exist per `entry_id`. A second different terminal resolution is a conflict and fails closed. An exact replay of the same canonical record is idempotent.

## 3. Exact endpoint and closed observation window

For an `ENTERED` record:

```text
resolution_target_at   = cutoff_at + horizon_seconds
resolution_deadline_at = resolution_target_at + 2 seconds
```

The exit observation window is the closed interval:

```text
[resolution_target_at, resolution_deadline_at]
```

**Both bounds are inclusive.**

The target remains based on the original V9 `cutoff_at`, never entry time.

A candidate exit quote must satisfy all existing SIM-4 quote validation and source-identity rules and must also satisfy both of these closed-window tests:

```text
resolution_target_at <= quote provider-event time <= resolution_deadline_at
resolution_target_at <= quote accepted_at          <= resolution_deadline_at
```

The quote must also be strictly causal to the actual entry quote:

```text
exit provider-event time > entry provider-event time
exit accepted_at          > entry accepted_at
```

That strict entry floor is never relaxed, even when an endpoint equals an entry timestamp after normalization.

Among valid exit quotes, select the first deterministic tuple in the existing SIM-4 ordering:

```text
(accepted_at, provider_event_ns, quote_id)
```

No interpolation, backfill, nearest-neighbor substitution, midpoint substitution, reconstructed quote, later quote outside the window, or pre-entry quote is allowed.

## 4. Exact executable exit side

For `LONG`:

- use the selected quote's `bid` as `exit_price`;
- require `bid_size >= 1.0`.

For `SHORT`:

- use the selected quote's `ask` as `exit_price`;
- require `ask_size >= 1.0`.

All existing finite/positive/ordering checks of `SimulationExecutableQuote` remain mandatory.

## 5. Exact unresolved classification

When the closed observation window ends without a valid exit quote:

- emit `UNRESOLVED_WINDOW_EXPIRED` only when the worker can prove continuous authorized SIP observation for the entire closed interval `[resolution_target_at, resolution_deadline_at]` and no valid exit quote existed;
- emit `UNRESOLVED_OBSERVATION_GAP` when any part of that closed interval lacks continuous observation because of worker startup after the interval began, restart, ownership loss, WebSocket disconnect/reconnect gap, or another provable observation discontinuity.

Unknown coverage is a gap, never a clean expiry.

An existing SIM-4 `ENTERED` position whose resolution window partially or fully elapsed before SIM-5 activation cannot be reconstructed from absent quotes. After its deadline passes it therefore resolves as `UNRESOLVED_OBSERVATION_GAP` unless the worker already possesses complete causal quote coverage for that exact closed interval.

These statuses are evidence, not failures to be retried. Once durably written they are terminal and immutable.

## 6. Exact immutable resolution record

Create one frozen/slotted `SimulationResolutionRecord` with fields in this exact order:

1. `contract_version: str`
2. `canonicalization_version: str`
3. `simulator_version: str`
4. `resolution_id: str`
5. `resolution_hash: str`
6. `mode: str`
7. `symbol: str`
8. `instrument: str`
9. `entry_id: str`
10. `entry_hash: str`
11. `source_cycle_id: str`
12. `cutoff_at: timezone-aware datetime`
13. `horizon: str`
14. `horizon_seconds: int`
15. `decision: str`
16. `entry_quote_id: str`
17. `entry_quote_hash: str`
18. `entry_price: float`
19. `resolution_target_at: timezone-aware datetime`
20. `resolution_deadline_at: timezone-aware datetime`
21. `resolution_status: str`
22. `exit_quote: SimulationExecutableQuote | None`
23. `exit_price: float | None`
24. `return_bps: float | None`

Exact constants:

```text
SIM_RESOLUTION_CONTRACT_VERSION = ATOM_TRUE_V9_SIM5_RESOLUTION_1
SIM_RESOLUTION_SCHEMA_VERSION = ATOM_TRUE_V9_SIM5_SCHEMA_1
SIM_RESOLUTION_STORE_VERSION = ATOM_TRUE_V9_SIM5_STORE_1
SIM_RESOLUTION_RUNTIME_VERSION = ATOM_TRUE_V9_SIM5_RUNTIME_1
SIM_CANONICALIZATION_VERSION = ATOM_TRUE_V9_SIM_CANONICAL_V4A_1
SIMULATOR_VERSION = ATOM_TRUE_V9_SIM_1
SIMULATION_MODE = PAPER_ONLY
RESOLUTION_ID_PREFIX = v9simresolution:
SIM_RESOLUTION_TABLE = public.atom_v9_sim_resolutions
```

For `RESOLVED`, `exit_quote`, `exit_price`, and `return_bps` are mandatory. For either unresolved status, all three are exactly `None`.

The entry identity, entry quote identity, entry price, cutoff, horizon, and direction must exactly match the referenced immutable SIM-4 `ENTERED` record.

## 7. Return mathematics and hash integrity

For `LONG`:

```text
return_bps = 10^4 * ln(exit_bid / entry_ask)
```

For `SHORT`:

```text
return_bps = 10^4 * ln(entry_bid / exit_ask)
```

Equivalently, because SIM-4 already freezes `entry_price` to the correct side and SIM-5 freezes `exit_price` to the correct side:

```text
LONG  = 10^4 * ln(exit_price / entry_price)
SHORT = 10^4 * ln(entry_price / exit_price)
```

The implementation must calculate this once with ordinary finite binary64 mathematics. NaN and infinity are invalid.

`resolution_hash` is the frozen V4A `canonical_sha256` over every resolution field except `resolution_id` and `resolution_hash`. **`return_bps` is inside the hash.**

```text
resolution_id = "v9simresolution:" + resolution_hash
```

Deserialization and durable-row reads independently recompute:

- the referenced entry identity;
- the exit quote identity when present;
- `exit_price` from the frozen direction/quote side;
- `return_bps` from immutable entry and exit prices;
- `resolution_hash`; and
- `resolution_id`.

Any mismatch is invalid and fails closed.

## 8. Persistence — migration 031 only

SIM-5 migration is exactly:

```text
migrations/031_create_v9_sim_resolutions.sql
```

If migration number `031` is occupied on the implementation base, stop `BLOCKED` before editing.

Migration 031 runs only on the already-installed isolated simulator Supabase project. It creates exactly one new append-only table `public.atom_v9_sim_resolutions` plus only the minimum index, immutable trigger/function, RLS policy, ownership, grants, and assertions required for this contract.

The table must enforce:

- `resolution_id` primary key;
- `resolution_hash` unique;
- `entry_id` unique and `NOT NULL`;
- a foreign key from `entry_id` to `public.atom_v9_sim_entries(entry_id)` with `ON DELETE RESTRICT`;
- exact status domain;
- exact six-horizon domain;
- resolved-vs-unresolved nullability consistency;
- canonical `record_json` storage;
- append-only mutation rejection.

The existing `atom_v9_sim_entry_runtime` receives only the minimum additional authority:

- `SELECT` on the resolution table;
- `INSERT` on the resolution table.

It receives no `UPDATE`, `DELETE`, `TRUNCATE`, schema mutation, role creation, RLS bypass, or new database access.

The existing simulator owner remains owner. No production role or production table may appear in this migration.

`UPDATE`, `DELETE`, and `TRUNCATE` must fail at the database boundary.

## 9. Runtime and horizon release

SIM-5 is disabled by default behind exactly:

```text
ATOM_V9_SIM5_ENABLED=true
```

Only lowercase `true` enables it. Missing or any other value disables SIM-5 without disabling SIM-4.

The existing SIM-4 worker remains the sole runtime. It consumes the same accepted SIP quote once and may offer that immutable quote to both the SIM-4 entry selector and the SIM-5 resolver. It must not open another market-data connection.

At startup/recovery the worker reads only unresolved `ENTERED` positions. Because SIM-4 permits at most one open position per horizon, recovery must remain bounded to at most six open entries. No historical full-table polling loop is authorized.

A horizon remains open from the durable SIM-4 `ENTERED` record until its SIM-5 terminal resolution is durably inserted. Only after that durable insert may later SIM-4 intents on the same horizon become eligible to enter.

Resolution and horizon-release decisions for a horizon use the existing per-horizon advisory lock. No process-local state may release a horizon before the database has the terminal resolution.

## 10. Exact implementation surface

After this documentation freeze merges, Codex is implementation owner.

Codex may change only:

- `migrations/031_create_v9_sim_resolutions.sql` — new;
- `quant/v9_sim5_resolution.py` — new immutable contract/store/resolver helpers;
- `tests/test_v9_sim5_resolution.py` — new;
- `quant/v9_sim4_worker.py` — minimum integration only;
- `quant/v9_sim4_entry.py` — minimum query/locking change needed so a durably resolved entry no longer blocks its horizon;
- `tests/test_v9_sim4_entry.py` — only tests for that narrow horizon-release interaction;
- `tests/test_v9_sim4_isolation.py` — only isolation/authority assertions required by migration 031/SIM-5;
- `tests/test_v9_sim4_void_return.py` only if the existing advisory-lock void-return compatibility path is directly exercised by the SIM-5 integration.

If another file is required, stop `BLOCKED` and return to ChatGPT Pro. No refactor, cleanup, dependency update, service split, new role, new credential, new data source, UI work, SIM-6 scaffold, or production change is authorized.

## 11. Required tests

Before merge prove at minimum:

- exact resolution dataclass field order, frozen/slotted behavior, constants, six horizons, and status domain;
- target is `cutoff_at + horizon_seconds`, never entry time;
- both observation-window bounds inclusive;
- strict post-entry causal floor;
- deterministic first-quote ordering;
- LONG bid and SHORT ask exit side with size >= 1;
- exact return formulas and finite-binary64 rejection;
- `return_bps` hash sensitivity and independent recomputation/tamper rejection;
- one resolution per `ENTERED` entry, exact replay idempotent, different replay conflict;
- skipped entries cannot resolve;
- `UNRESOLVED_WINDOW_EXPIRED` requires complete continuous observation;
- any unknown/restart/disconnect/startup coverage gap yields `UNRESOLVED_OBSERVATION_GAP`;
- pre-SIM-5 expired open positions cannot be reconstructed;
- terminal durable resolution releases only that horizon;
- no release before commit;
- restart recovery bounded to at most six unresolved open entries;
- migration FK points resolutions to entries and uses `ON DELETE RESTRICT`;
- `UPDATE`, `DELETE`, `TRUNCATE` fail;
- runtime role has only required SELECT/INSERT authority;
- SIM-5 disabled preserves SIM-4 behavior;
- no second WebSocket/source/service/role/project is introduced;
- no V9, family, E-1, Level-II, broker, account, position, or order path is reachable;
- full existing suite remains green.

## 12. Merge, migration, activation, and deployment gate

Implementation order after this freeze merges:

1. Codex implements migration/tests/runtime on one PR.
2. Independent final-head review.
3. Every required check green and zero unresolved material threads.
4. Owner merge.
5. Apply migration 031 once to the isolated simulator Supabase project only.
6. Verify installation identity, FK, append-only protections, and exact runtime grants.
7. Set `ATOM_V9_SIM5_ENABLED=true` only on the existing SIM-4 Render worker.
8. Deploy that existing worker at the exact merged implementation SHA.
9. Capture deterministic deployment/health evidence.
10. During the next available causal quote window, capture the live SIM-5 resolution acceptance proof.

A deployment outside regular market hours is allowed. Lack of a live market quote does not fabricate a PASS; the live resolution portion remains pending until causal evidence exists.

## 13. Acceptance proof

The SIM-5 receipt must identify:

- exact merged/deployed SHA;
- isolated simulator project identity;
- existing worker identity and single-owner fence;
- migration 031 applied exactly once;
- SIM-5 gate state;
- no new service/role/credential/source;
- counts of open `ENTERED` positions and terminal resolutions by horizon/status;
- at least one terminal-resolution record validated end-to-end when live causal evidence is available;
- for `RESOLVED`, the entry identity, endpoint, chosen exit quote identity, side, price, recomputed `return_bps`, record hash, and durable row identity;
- for unresolved records, the exact terminal reason and observation-coverage proof;
- horizon release only after durable terminal resolution;
- append-only enforcement; and
- `PAPER_ONLY`, no broker/account/order authority.

Any causal ambiguity, hash mismatch, duplicate different resolution, unexplained observation gap, wrong project/role/source, mutation authority, or production influence is `FAIL`/`INVALID`, never PASS.

## 14. Frozen conclusion

> SIM-5 does one thing: close each immutable SIM-4 `ENTERED` paper position from the first valid causal executable quote inside the closed two-second endpoint window, or immutably record why that window could not be resolved. Persist exactly one terminal record, release the horizon only after commit, and change nothing in V9 or live trading.

**END — ATOM-SIM-4A-EXACT-SIM5-RESOLUTION-FREEZE-1**
