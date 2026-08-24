# ATOM TRUE V9 — Paper Simulation Architecture Freeze

**Status:** LAW
**Freeze amendment:** SIM-0A
**Simulator version:** `ATOM_TRUE_V9_SIM_1`
**Mode:** `PAPER_ONLY`
**Symbol:** `COIN`
**Initial instrument:** COIN shares
**Position size:** One simulated share

This document is controlling law for simulator work. SIM-0A authorizes architecture only and does not implement the simulator. After SIM-0A is merged, only SIM-1 is authorized; no later simulation phase may be implemented early.

## Authority and isolation

The production pipeline remains unchanged:

```
snapshot
  → Q1–Q12
  → V1
  → immutable V2
  → V3
  → V4D
  → website
```

One isolated downstream research path is authorized:

```
immutable completed V4D output
  → paper simulator
  → immutable simulation evidence
  → compact simulation state
  → read-only simulation page
```

The simulator is not part of V9 forecasting mathematics. It has no authority over production, forecasting, broker activity, or truth credit. Simulator failure, delay, overload, missing data, or complete unavailability must not affect production.

## Six independent horizon books

One simulator contains six independent horizon books, in this exact order:

1. `30S`
2. `1M`
3. `5M`
4. `15M`
5. `30M`
6. `1H`

At most one position may be open per horizon, for a maximum of six open positions in total.

## Direction rule

Direction is determined only from `final_bps`:

| Condition | Direction |
| --- | --- |
| `final_bps > 0` | `LONG` |
| `final_bps < 0` | `SHORT` |
| `final_bps = 0` | `NO_TRADE` |
| `final_bps` unavailable or nonfinite | `NO_TRADE` |

`PROVISIONAL` forecasts may be simulated, but must remain separately identified.

## Causal execution rule

The simulator consumes only a completed, immutable V4D output.

Entry is the first valid executable COIN quote after forecast publication and no more than two seconds after publication:

- `LONG` entry uses the ask.
- `SHORT` entry uses the bid.

The exit endpoint is the original V9 cutoff plus the applicable horizon:

- `LONG` exit uses the first valid bid crossing the endpoint.
- `SHORT` exit uses the first valid ask crossing the endpoint.

A missing or invalid entry produces `SKIPPED`. A missing causal exit bracket produces `UNRESOLVED`. Reconstruction, interpolation, backdating, and fabricated quotes are forbidden.

## Return mathematics

For `LONG` positions:

```
R_bps = 10^4 * ln(exit_bid / entry_ask)
```

For `SHORT` positions:

```
R_bps = 10^4 * ln(entry_bid / exit_ask)
```

## Hard security boundary

The following values are frozen:

```
SIMULATION_MODE = PAPER_ONLY
BROKER_AUTHORITY = NONE
ORDER_SUBMISSION = IMPOSSIBLE
```

The simulator must never possess:

- broker credentials;
- an order-submission client;
- buying-power authority;
- live position authority; or
- broker mutation capability.

The simulator must never execute:

- under a COIN or BTC ingestion lock;
- inside Q1–Q12;
- inside V1, V2, V3, or V4D;
- inside a web request;
- inside production forecast persistence;
- inside production target resolution; or
- before V4D publication completes.

## Database security

Persistence is not implemented or migrated in SIM-0A. A future persistence phase may create the dedicated role `atom_v9_sim_runtime`. Its maximum authority is:

- `SELECT` on explicitly required immutable production evidence;
- `SELECT` on simulator evidence; and
- `INSERT` on simulator evidence.

It must not receive:

- `UPDATE`;
- `DELETE`;
- `TRUNCATE`;
- production `INSERT`;
- schema mutation;
- role creation;
- superuser;
- inheritance; or
- RLS bypass.

## Immutability and identity

Future simulator persistence shall use separate, append-only:

- trade-intent evidence;
- trade-resolution evidence; and
- compact simulator states.

The original trade intent may not be rewritten after its result is known. Every mathematical object requires deterministic canonical serialization, SHA-256 hashing, and a simulator-specific identity namespace.

Simulator evidence must never enter or contaminate V1–V4 production evidence, truth credit, calibration, `RANGE`, probability, or forecast ledgers.

## Website boundary

A future `/simulation` page shall be:

- read-only;
- compact-state only;
- incapable of starting or modifying simulation;
- free of historical scans;
- free of outcome resolution; and
- free of broker authority.

It must display:

> **PAPER SIMULATION — NO BROKER AUTHORITY**

## Options deferred

Options simulation is explicitly deferred. No `CALL`/`PUT`, strike, expiration, Greeks, contract sizing, or option execution logic belongs to `ATOM_TRUE_V9_SIM_1`.

## Phase gate

SIM-0A freezes this architecture. The phase sequence is defined in `PHASES.md`. Only SIM-1 becomes authorized after SIM-0A is merged. No later phase may be implemented early.

## SIM-0B — Exact SIM-1 contract freeze

SIM-0B resolves the SIM-1 contract architecture only. It is documentation-only and does not implement SIM-1.

### Exact SIM-1 scope

SIM-1 defines exactly one immutable mathematical object: `SimulationTradeIntent`. It represents one simulator decision for one V9 horizon after a completed, immutable, and successfully persisted V4D forecast becomes available to the simulator.

SIM-1 does not define entry records, resolution records, P&L, compact simulator states, persistence, database schemas, runtime capture, or web integration. Those remain assigned to later phases.

### Frozen identities and constants

The exact SIM-1 identities and constants are:

```
SIM_INTENT_CONTRACT_VERSION = ATOM_TRUE_V9_SIM1_INTENT_1
SIMULATOR_VERSION = ATOM_TRUE_V9_SIM_1
SIM_CANONICALIZATION_VERSION = ATOM_TRUE_V9_SIM_CANONICAL_V4A_1
SIMULATION_MODE = PAPER_ONLY
IDENTITY_PREFIX = v9simintent:
SYMBOL = COIN
INSTRUMENT = COIN_SHARE
```

### Exact contract fields

`SimulationTradeIntent` contains fields in exactly this order and with exactly these types:

1. `contract_version: str`
2. `canonicalization_version: str`
3. `simulator_version: str`
4. `intent_id: str`
5. `intent_hash: str`
6. `mode: str`
7. `symbol: str`
8. `instrument: str`
9. `source_cycle_id: str`
10. `source_forecast_record_id: str`
11. `source_forecast_record_hash: str`
12. `source_v2_state_id: str`
13. `source_v2_state_hash: str`
14. `source_v3_contract_version: str`
15. `source_v3_model_version: str`
16. `cutoff_at: timezone-aware datetime`
17. `eligible_at: timezone-aware datetime`
18. `horizon: str`
19. `horizon_seconds: int`
20. `final_bps: Optional[float]`
21. `source_v3_status: str`
22. `decision: str`
23. `status: str`
24. `quantity_shares: int`

The implementation shall use `@dataclass(frozen=True, slots=True)`. No lists, mappings, or mutable nested values are permitted.

### Source identity and eligibility

`source_forecast_record_id` and `source_forecast_record_hash` identify the exact immutable V4A forecast record used by V4D. A simulator intent is eligible only after that source forecast has been successfully persisted. The simulator must not use an unpersisted or reconstructed forecast.

`source_v2_state_id` and `source_v2_state_hash` preserve the exact immutable V2 evidence identity. `source_v3_contract_version` and `source_v3_model_version` preserve the exact V3 identity. `source_cycle_id` and `cutoff_at` preserve the original V9 cycle identity. SIM-1 does not modify V3, V4A, or V4D to add another production identity.

`eligible_at` is the UTC timestamp captured by the future SIM-3 consumer immediately after all of the following:

1. The complete immutable V4D cycle output exists.
2. The referenced V4A forecast persistence succeeded.
3. The simulator receives that completed result.

`eligible_at` is a causal simulator boundary and is included in the mathematical intent hash. It must satisfy `eligible_at >= cutoff_at`. SIM-1 accepts `eligible_at` as supplied data and performs no clock access.

### Exact horizon domain

The horizon mapping and order are exactly:

```
30S = 30
1M  = 60
5M  = 300
15M = 900
30M = 1800
1H  = 3600
```

No other horizon or seconds value is valid.

### Source status, decision, and intent status

`source_v3_status` has no default and must be exactly one of `AVAILABLE`, `PROVISIONAL`, or `UNAVAILABLE`.

`decision` must be exactly one of `LONG`, `SHORT`, or `NO_TRADE`. `status` must be exactly one of `ACTIONABLE`, `NO_TRADE`, or `UNAVAILABLE`. Their deterministic mapping is:

| Input | `decision` | `status` | `quantity_shares` |
| --- | --- | --- | --- |
| finite `final_bps > 0` | `LONG` | `ACTIONABLE` | `1` |
| finite `final_bps < 0` | `SHORT` | `ACTIONABLE` | `1` |
| finite `final_bps == 0`, including negative zero | `NO_TRADE` | `NO_TRADE` | `0` |
| `final_bps is None` | `NO_TRADE` | `UNAVAILABLE` | `0` |

NaN and positive or negative infinity are invalid and rejected. If `source_v3_status` is `UNAVAILABLE`, `final_bps` must be `None`. `PROVISIONAL` remains `source_v3_status = PROVISIONAL` and receives no confidence discount or mathematical alteration. Boolean values are invalid for `final_bps`, `horizon_seconds`, and `quantity_shares`.

### Normative canonicalization

SIM-1 shall reuse, without modification, the behavior of:

- `quant.v9_v4a_evidence._canonical`
- `quant.v9_v4a_evidence._decanonical`
- `quant.v9_v4a_evidence.canonical_sha256`

The existing V4A canonical numerical procedure is normative for SIM-1:

- Timezone-aware datetimes normalize to UTC.
- UTC timestamps use microsecond precision and a `Z` suffix.
- The datetime wrapper is `$timestamp_utc`.
- Finite binary64 floats use `float.hex()`.
- The float wrapper is `$float64`.
- Positive and negative zero canonicalize identically.
- NaN and infinity are rejected.
- Tuples serialize as ordered arrays.
- Mapping keys are strings and sorted deterministically.
- JSON uses sorted keys, compact separators, and ASCII encoding.
- SHA-256 output is lowercase hexadecimal.

SIM-1 must not modify the existing V4A canonicalization implementation.

### Exact mathematical hash boundary

`intent_hash` is SHA-256 over exactly these fields:

1. `contract_version`
2. `canonicalization_version`
3. `simulator_version`
4. `mode`
5. `symbol`
6. `instrument`
7. `source_cycle_id`
8. `source_forecast_record_id`
9. `source_forecast_record_hash`
10. `source_v2_state_id`
11. `source_v2_state_hash`
12. `source_v3_contract_version`
13. `source_v3_model_version`
14. `cutoff_at`
15. `eligible_at`
16. `horizon`
17. `horizon_seconds`
18. `final_bps`
19. `source_v3_status`
20. `decision`
21. `status`
22. `quantity_shares`

The hash excludes exactly `intent_id` and `intent_hash`. SIM-1 contains no operational creation timestamp or persistence result.

### Exact intent identity

The identity is exactly:

```
intent_id = "v9simintent:" + intent_hash
```

Hash values must match `^[0-9a-f]{64}$`. Deserialization must independently recalculate and verify both `intent_hash` and `intent_id`; any mismatch is rejected.

### Exact validation boundary

SIM-1 requires:

- Exact version constants and exact mode, symbol, and instrument.
- A nonempty `source_cycle_id`.
- Valid source IDs and lowercase 64-character source hashes.
- Timezone-aware `cutoff_at` and `eligible_at`.
- `eligible_at >= cutoff_at`.
- Exact horizon/seconds pairing.
- A valid source status.
- The deterministic decision/status/quantity mapping above.
- `final_bps` finite or `None`.
- Deep immutability.
- No unknown fields and no missing fields.

Timezone-equivalent instants must produce identical canonical values and hashes.

### Deferred contracts

SIM-4 defines the immutable entry record and entry statuses. SIM-5 defines the immutable resolution record, successful-resolution status, `SKIPPED`/`UNRESOLVED` lifecycle, quote identities, return values, and supplement semantics. SIM-6 defines the compact simulator state and all aggregate mathematics. These objects must not be scaffolded during SIM-1.

### Exact SIM-1 implementation surface

After SIM-0B merges, SIM-1 may create exactly:

- `quant/v9_sim1_contract.py`
- `tests/test_v9_sim1_contract.py`

SIM-1 may not modify any existing production module. It may import and reuse the frozen V4A canonicalization functions without changing them.

### Required SIM-1 tests

SIM-1 must test:

- Exact field declaration order.
- Frozen and slotted dataclass behavior and deep immutability.
- Exact constants and exact horizon mapping.
- Positive `LONG`, negative `SHORT`, positive-zero and negative-zero `NO_TRADE`, and `None`/`UNAVAILABLE` mappings.
- `PROVISIONAL` preservation.
- NaN, infinity, boolean numerical fields, naive datetimes, and `eligible_at` before `cutoff_at` rejection.
- Timezone-equivalent canonicalization, binary64 golden vectors, and negative-zero normalization.
- Deterministic hashing, hash sensitivity for every included field, and exclusion of `intent_id` and `intent_hash`.
- The exact identity prefix.
- Serialization/deserialization round trip and missing or unknown field rejection.
- Stored hash and stored ID tamper rejection.
- No I/O or clock access.
- No persistence, broker, web, V3 synthesis, or V4D invocation.
- No changes to Q1–Q12 or V1–V4 files.
- The full existing suite remains green.

### SIM-0B and SIM-1 hard boundaries

SIM-0B adds no Python implementation, tests, migration, database change, Render change, web change, broker integration, Q1–Q12 change, V1–V4 change, entry selection, resolution, P&L, compact state, or unrelated documentation rewrite.

## SIM-1A — Exact SIM-2 Intent Persistence Freeze

SIM-1A freezes the following SIM-2 persistence decisions exactly. It is documentation-only and does not implement SIM-2.

### Identities

```
SIM_INTENT_STORE_VERSION = ATOM_TRUE_V9_SIM2_STORE_1
SIM_INTENT_SCHEMA_VERSION = ATOM_TRUE_V9_SIM2_SCHEMA_1
SIM_INTENT_TABLE = public.atom_v9_sim_intents
SIM_RUNTIME_ROLE = atom_v9_sim_runtime
MIGRATION_FILE = migrations/010_create_v9_sim_intents.sql
```

If migration number `010` is already occupied, stop without editing and report the conflict.

### Database placement

Use the existing PostgreSQL database and `public` schema, but use an isolated simulator table and isolated simulator role.

No simulator foreign key may reference a production table.

### Table — exact column order

1. `intent_id text PRIMARY KEY`
2. `intent_hash text UNIQUE NOT NULL`
3. `contract_version text NOT NULL`
4. `canonicalization_version text NOT NULL`
5. `simulator_version text NOT NULL`
6. `symbol text NOT NULL`
7. `horizon text NOT NULL`
8. `horizon_seconds integer NOT NULL`
9. `cutoff_at timestamptz NOT NULL`
10. `eligible_at timestamptz NOT NULL`
11. `source_v3_status text NOT NULL`
12. `decision text NOT NULL`
13. `status text NOT NULL`
14. `record_json jsonb NOT NULL`
15. `created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`

`created_at` is operational metadata and is excluded from the mathematical intent hash.

### Constraints

- `intent_id` must match `^v9simintent:[0-9a-f]{64}$`.
- `intent_hash` must match `^[0-9a-f]{64}$`.
- `contract_version` must equal `ATOM_TRUE_V9_SIM1_INTENT_1`.
- `canonicalization_version` must equal `ATOM_TRUE_V9_SIM_CANONICAL_V4A_1`.
- `simulator_version` must equal `ATOM_TRUE_V9_SIM_1`.
- `symbol` must equal `COIN`.
- `horizon`/`horizon_seconds` pairs must be exactly:
  - `30S`/`30`
  - `1M`/`60`
  - `5M`/`300`
  - `15M`/`900`
  - `30M`/`1800`
  - `1H`/`3600`
- `eligible_at >= cutoff_at`.
- `source_v3_status` must be `AVAILABLE`, `PROVISIONAL`, or `UNAVAILABLE`.
- `decision` must be `LONG`, `SHORT`, or `NO_TRADE`.
- `status` must be `ACTIONABLE`, `NO_TRADE`, or `UNAVAILABLE`.
- `record_json` must be a JSON object.
- No foreign keys.
- No uniqueness constraint on horizon, cutoff, session, date, or source cycle.

### Index

Create exactly one non-unique lookup index:

```
atom_v9_sim_intents_lookup_idx
```

on:

```
(symbol, horizon, eligible_at, intent_id)
```

### Unlimited history

- Unlimited sequential intent and trade history.
- No daily, session, or lifetime cap.
- No deletion, rotation, overwrite, replacement, or truncation.
- No uniqueness rule may limit repeated horizon activity over time.
- `NO_TRADE` and `UNAVAILABLE` intents remain persistable evidence.
- `NO_TRADE` and `UNAVAILABLE` never occupy a simulated position.
- The one-open-trade-per-horizon rule belongs to later lifecycle phases, not SIM-2 persistence.

### Role

Create `atom_v9_sim_runtime` with exactly:

```
LOGIN
NOINHERIT
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOREPLICATION
NOBYPASSRLS
```

The migration contains no password.

If the role already exists, fail with `duplicate_object`. Do not adopt or alter an existing role.

Grant the role:

- `USAGE` on schema `public`.
- `SELECT` and `INSERT` only on `public.atom_v9_sim_intents`.

Grant no sequence privileges.

The simulator role receives no privileges on production V1–V4, forecast, outcome, state, truth, calibration, `RANGE`, probability, or legacy evidence tables.

Explicitly preserve isolation from:

- `atom_v9_v4_forecasts`
- `atom_v9_v4_outcomes`
- `atom_v9_v4_states`
- `forecasts`
- `forecast_outcomes`
- `volatility_forecasts`
- `volatility_forecast_outcomes`

Revoke simulator-table access from:

- `PUBLIC`
- `anon`
- `authenticated`
- `service_role`
- `atom_v9_v4_runtime`

### RLS and append-only enforcement

Enable and FORCE row-level security.

Create exactly two role-specific policies:

- `atom_v9_sim_intents_runtime_select`
- `atom_v9_sim_intents_runtime_insert`

Only `atom_v9_sim_runtime` receives these policies.

Create function:

```
public.atom_v9_sim_reject_mutation()
```

Properties:

- `RETURNS trigger`
- `LANGUAGE plpgsql`
- `SECURITY INVOKER`
- `SET search_path = pg_catalog`
- Raises: `SIM evidence is append-only`

Revoke function execution from:

- `PUBLIC`
- `anon`
- `authenticated`
- `service_role`
- `atom_v9_v4_runtime`
- `atom_v9_sim_runtime`

Create:

- Row-level `BEFORE UPDATE OR DELETE` trigger: `atom_v9_sim_intents_reject_update_delete`.
- Statement-level `BEFORE TRUNCATE` trigger: `atom_v9_sim_intents_reject_truncate`.

The runtime role must not own the table and must not bypass RLS.

### Serialization

SIM-2 must use the existing SIM-1:

- `serialize_intent`
- `deserialize_intent`

`record_json` stores the JSON object obtained from the canonical serialized intent.

PostgreSQL JSONB key normalization is allowed.

Raw JSONB bytes are never treated as the mathematical hash input.

Every loaded row must:

1. Deserialize through `deserialize_intent`.
2. Recalculate and validate `intent_hash` and `intent_id`.
3. Match every duplicated relational column exactly.
4. Reject missing, unknown, malformed, or noncanonical content.

### Store API

Future SIM-2 implementation creates:

```python
class SimulationIntentStore
```

Exact public methods:

- `insert(intent: SimulationTradeIntent) -> str`
- `get(intent_id: str) -> SimulationTradeIntent | None`

The constructor receives an explicit no-argument database connection factory.

It must not:

- Read environment variables.
- Use `DATABASE_URL`.
- Use V4 credentials.
- Fall back to privileged credentials.
- Scan production tables.

Before table access, verify `current_user` equals `atom_v9_sim_runtime`.

### Insert results

Exact successful results:

- `INSERTED`
- `IDEMPOTENT`

Use an atomic PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` mechanism.

If insertion conflicts:

1. Re-read the row by `intent_id` or `intent_hash`.
2. Deserialize and fully validate it.
3. Compare its complete immutable intent content.

Exact identical content returns `IDEMPOTENT`.

Different content reusing either identity raises:

```
SimulationIntentConflictError
reason = SIM2_INTENT_CONFLICT
```

Malformed or mismatched stored content raises:

```
SimulationIntentRowInvalidError
reason = SIM2_ROW_INVALID
```

Wrong database role raises:

```
SimulationIntentRoleError
reason = SIM2_ROLE_MISMATCH
```

Every successful operation commits.

Every conflict or failure rolls back.

Connections and cursors acquired by the store are closed on every path.

### Authorized SIM-2 implementation files

After this freeze is merged, SIM-2 may create exactly:

- `migrations/010_create_v9_sim_intents.sql`
- `quant/v9_sim2_store.py`
- `tests/test_v9_sim2_persistence.py`

It may not modify `quant/v9_sim1_contract.py` or any production file.

### Required tests

Freeze tests for:

- Exact table shape and column order.
- Every constraint.
- One lookup index.
- Exact role attributes.
- Existing-role conflict.
- Exact grants and revocations.
- Absence of production-table privileges.
- ENABLE and FORCE RLS.
- Exact policies.
- Row-level UPDATE/DELETE rejection.
- Statement-level TRUNCATE rejection.
- Safe trigger function configuration.
- Serialization round trip.
- Relational-column/payload equality.
- Hash and ID tamper rejection.
- Inserted result.
- Idempotent identical insert.
- Conflicting identity.
- Concurrent identical insertion.
- Commit, rollback, and connection closure.
- Current-user enforcement.
- Missing and malformed rows.
- Unlimited horizon history.
- Persistable `NO_TRADE` and `UNAVAILABLE` intents.
- No mutation SQL.
- No environment or credential fallback.
- No production imports or table scans.
- Full existing suite remains green.
- Final diff contains only the three authorized SIM-2 files.

### Phase boundary

SIM-2 implements storage only.

It does not implement runtime capture, open-position enforcement, entry, exit, resolution, P&L, compact state, web integration, Render changes, broker access, or order submission.
