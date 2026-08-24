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
