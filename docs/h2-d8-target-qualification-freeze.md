# H2-D-8 two-session target-qualification freeze

**Status:** LAW — documentation-only freeze; read-only implementation authorized after merge  
**Current runtime:** H2-D-7 passed; benchmark is idle and suspended  
**Next gate:** qualify at most two exact absent targets for a separate amendment

## Decision

H2-D-8 may inspect only the fixed candidate dates below, in ascending order, and
select the first two dates that satisfy the existing H1 data-quality and
identity-absence gates.

| Order | Historical session | Replay run ID |
|---:|---|---|
| 1 | `2026-07-27` | `h2d-2026-07-27` |
| 2 | `2026-07-28` | `h2d-2026-07-28` |
| 3 | `2026-07-29` | `h2d-2026-07-29` |
| 4 | `2026-07-30` | `h2d-2026-07-30` |
| 5 | `2026-07-31` | `h2d-2026-07-31` |

This phase is target qualification only. It authorizes no historical admission
and no evidence write.

## Ordered qualification gate

For each candidate, sequentially:

1. Read through exactly `atom_historical_score_reader` and prove that the
   session and replay run ID are absent from replay manifests, run manifests,
   forecasts, and outcomes.
2. Run the existing read-only H1 preflight with the frozen maximum interior
   quote gap of `5` seconds.
3. Record the exact status, reason codes, result source, maximum interior gap,
   frame count, and any lineage or content digests emitted by the existing
   preflight.
4. Mark a target `QUALIFYING` only when identity absence is exact and H1 is
   `REPLAY_COMPLETE + CERTIFIED` with no reason codes.
5. Continue in fixed order until two targets qualify, then stop without
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
- `forecast_writes=0`, `outcome_writes=0`, and
  `pre_post_unchanged=true`;
- `continuous_replay_enabled=false` and
  `parallel_replay_enabled=false`.

Stop after the first final `PASSED` or `FAILED` receipt. Restore the benchmark
start command to `sleep infinity` and suspend it.

A pass qualifies at most two candidate identities. It does not authorize a write
canary. Before any admission, a separate narrow amendment must freeze the exact
qualified sessions, replay run IDs, expected counts, and write stopping rule.
