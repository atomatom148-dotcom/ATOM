# H2-D-7 one-session historical-admission freeze

**Status:** COMPLETE — exact frozen execution passed  
**Current runtime:** benchmark restored to `sleep infinity` and suspended  
**Next gate:** a separate read-only target-qualification freeze

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

## Completion receipt

The single frozen admission passed on commit
`9d389083ac6b8ffd81f4ba236bf9cbca163a6d36`.

| Result | Exact value |
|---|---|
| Frames | `9,528` |
| Forecast writes | `686,016` |
| Outcome writes | `57,168` |
| Manifest writes | `1` |
| Artifact SHA-256 | `661218b81b6c7b4b51700d5138e218b9d8e3ae4acc626dfa7de9d4d2c6510d31` |
| Manifest SHA-256 | `37dd439ab90048ef552fda52ccebc928fc221e1e2af94792f24e11b293663658` |
| Forecast SHA-256 | `e5b7395acbf0647b2f2b26086b69a3930ba9bbc0d8fb30f3003effcbe9ff98ff` |
| Outcome SHA-256 | `1f456b3e32747ab0b7a47ee9abe82e07bf7341d02923f1589fe243617bf03a62` |
| Metric SHA-256 | `204bb34317cb05faad447171791525f9f9da56f11e8bfa359867595d391a611f` |
| Scoring SHA-256 | `a49437306ef951c775202ee383f1978236b11cf1f55f8a8c075708554b11a36c` |
| Control SHA-256 | `725b8f3820e1cf6474464527b24d2d304c9bd5eaf0fdfc40e8f3c243bcaf6871` |
| Peak RSS | `344,548 KiB` |
| Elapsed | `3247.929675s` |
| New-date admission | `true` |
| Continuous / parallel replay | `false / false` |

The exact writer, resolver, and reader roles passed. Existing evidence was not
rewritten or deleted.

## Stopping rule

After one final `PASSED` or `FAILED` receipt, stop. Restore the benchmark start
command to `sleep infinity` and suspend it. A pass certifies one-session
admission only; it does not authorize backfill or continuous historical replay.
