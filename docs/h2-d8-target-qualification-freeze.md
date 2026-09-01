# H2-D-8 two-session target-qualification freeze

**Status:** LAW — documentation-only freeze; read-only implementation authorized after merge  
**Current runtime:** H2-D-7 passed; benchmark is idle and suspended  
**Next gate:** qualify at most two exact absent targets for a separate amendment

## Decision

**Final bounded amendment — September 1, 2026:** The original July 27–31
window and the August 3–7 window both produced zero qualifying targets and zero
writes. Replace only that exhausted candidate set with the remaining 16 regular
August sessions below. This is one bounded read-only qualification run, not a
general date-selection or backfill framework. Every other H2-D-8 rule and
stopping boundary remains unchanged.

H2-D-8 may inspect only the fixed candidate dates below, in ascending order, and
select the first two dates that satisfy the existing H1 data-quality and
identity-absence gates.

| Order | Historical session | Replay run ID |
|---:|---|---|
| 1 | `2026-08-10` | `h2d-2026-08-10` |
| 2 | `2026-08-11` | `h2d-2026-08-11` |
| 3 | `2026-08-12` | `h2d-2026-08-12` |
| 4 | `2026-08-13` | `h2d-2026-08-13` |
| 5 | `2026-08-14` | `h2d-2026-08-14` |
| 6 | `2026-08-17` | `h2d-2026-08-17` |
| 7 | `2026-08-18` | `h2d-2026-08-18` |
| 8 | `2026-08-19` | `h2d-2026-08-19` |
| 9 | `2026-08-20` | `h2d-2026-08-20` |
| 10 | `2026-08-21` | `h2d-2026-08-21` |
| 11 | `2026-08-24` | `h2d-2026-08-24` |
| 12 | `2026-08-25` | `h2d-2026-08-25` |
| 13 | `2026-08-26` | `h2d-2026-08-26` |
| 14 | `2026-08-27` | `h2d-2026-08-27` |
| 15 | `2026-08-28` | `h2d-2026-08-28` |
| 16 | `2026-08-31` | `h2d-2026-08-31` |

This phase is target qualification only. It authorizes no historical admission
and no evidence write.

## Ordered qualification gate

For each candidate, sequentially:

1. Read through exactly `atom_historical_score_reader` and prove that the
   session and replay run ID are absent from replay manifests, run manifests,
   forecasts, and outcomes.
2. Run the existing read-only H1 preflight with the configured maximum
   interior quote gap of `5` seconds.
3. Independently inspect the emitted COIN gap telemetry and require the observed
   maximum interior gap to be at most `5` seconds. A valid retrieval proof does
   not waive this H2-D-8 gate.
4. Record the exact status, reason codes, result source, maximum interior gap,
   frame count, and any lineage or content digests emitted by the existing
   preflight.
5. Mark a target `QUALIFYING` only when identity absence is exact, H1 is
   `PREFLIGHT_ONLY + DATA_COMPLETE`, reason codes are empty, and the observed
   COIN maximum interior gap is at most `5` seconds.
6. Continue in fixed order until two targets qualify, then stop without
   inspecting later candidates.

A candidate rejected for honest market-data quality may be recorded and skipped.
A database, credential, provider, system, lineage, or receipt error fails the
complete phase immediately. It must not be converted into a rejection or
silently skipped.

## Frozen boundaries

H2-D-8 is read-only and single-process. It adds no migration, table, role,
grant, index, queue, scheduler, service, or compute change. It changes no V9
mathematics, thresholds, behavior, outputs, quant-family code, live service,
existing evidence, Render tier, Supabase tier, or broker authority.

Forecast, manifest, persistence, and outcome writes must all remain `0`.
Parallel replay and continuous replay remain disabled. Existing evidence may not
be deleted, rewritten, repaired, or backfilled.

Implementation is limited to the smallest reuse or narrow extension of the
existing D7 read-only preflight needed to accept this fixed list and stop after
two qualifying targets. Do not add a general backfill engine or theoretical
date-selection framework.

## Final receipt and stopping rule

The final receipt must include:

- every inspected candidate in order;
- exact status and reason codes for each;
- exact selected sessions and replay run IDs, if any;
- absence counts for manifests, run manifests, forecasts, and outcomes;
- maximum interior gap and result source for each candidate;
- `manifest_writes=0`, `forecast_writes=0`, `persistence_writes=0`,
  `outcome_writes=0`, and `pre_post_unchanged=true`;
- `continuous_replay_enabled=false` and
  `parallel_replay_enabled=false`.

Stop after the first final `PASSED` or `FAILED` receipt. Restore the benchmark
start command to `sleep infinity` and suspend it.

A pass qualifies at most two candidate identities. It does not authorize a write
canary. Before any admission, a separate narrow amendment must freeze the exact
qualified sessions, replay run IDs, expected counts, and write stopping rule.
