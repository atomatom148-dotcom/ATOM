# H2-D-7 one-session historical-admission freeze

**Status:** LAW — implementation authorized; execution not yet passed  
**Current runtime:** H2-D-6 passed and the benchmark worker is suspended  
**Next gate:** one new certified session through the existing sequential path

## Decision

H2-D-7 may attempt exactly one new historical session. It reuses the frozen
`H1 → H2B → H2C resolve → score` path and the existing append-only tables and
least-privilege roles.

| Frozen field | Exact value |
|---|---|
| Historical session | `2026-07-24` |
| Replay run ID | `h2d-2026-07-24` |
| Maximum interior quote gap | `5` seconds |
| Expected forecast rows | `frame_count × 72` |
| Expected outcome rows | `frame_count × 6` |

The target session and run ID were absent during the read-only preflight on
August 31, 2026. Runtime must prove absence again before H1 starts. An existing
manifest, forecast, or outcome row fails the gate; no alternate identity or
date is allowed.

## Ordered gate

1. Connect through exactly `atom_historical_score_reader` and prove the target
   session, run ID, forecasts, and outcomes are absent.
2. Run the existing single-process H1 replay with the frozen five-second gap
   limit. Only `REPLAY_COMPLETE + CERTIFIED` with no reason codes may persist.
3. Connect through exactly `atom_historical_replay_writer`. The existing atomic
   writer must insert one manifest plus exactly `frame_count × 72` forecasts.
4. Verify the complete manifest and forecast set.
5. Connect through exactly `atom_historical_outcome_resolver` and insert exactly
   `frame_count × 6` outcomes.
6. Read through exactly `atom_historical_score_reader`, require 72 metrics and
   exact lineage/counts, and record the manifest, artifact, ordered forecast,
   ordered outcome, metric, scoring, and control hashes.

Any certification, role, count, lineage, hash, database, or provider failure
fails closed. If forecasts commit before a later stage fails, stop without
deleting, rewriting, or repairing evidence; recovery requires a separate,
narrow decision for this same immutable identity.

H2-D-6 already proved exact zero-write retries through both persistence roles.
H2-D-7 does not repeat that completed gate or add a general recovery framework.

## Existing boundary

H2-D-7 adds no migration, table, role, grant, index, queue, or scheduler. Forced
RLS, append-only triggers, immutable identities, and the existing writer,
resolver, and score-reader credentials remain authoritative.

It changes no V9 mathematics, thresholds, behavior, outputs, quant-family code,
live service, production evidence, Render or Supabase tier, or broker authority.
Replay remains sequential. Parallel replay and continuous replay remain off.

## Stopping rule

After one final `PASSED` or `FAILED` receipt, stop. Restore the benchmark start
command to `sleep infinity` and suspend it. A pass certifies one-session
admission only; it does not authorize backfill or continuous historical replay.
