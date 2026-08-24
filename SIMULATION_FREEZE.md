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
