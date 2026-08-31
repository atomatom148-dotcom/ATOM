# H2-D-4 compute decision

**Status:** COMPLETE — keep current Render and Supabase tiers  
**Canary deploy:** `dep-daacm4qjnfac7385uj8g`  
**Git commit:** `9e0980e704d34e21b035b1d5449671f547568597`  
**Final receipt:** `2026-08-31T02:20:22.466259156Z`

## Decision

Keep the H2-D benchmark worker at **4 CPU / 8 GB RAM** and keep the current
Supabase compute tier unchanged. Keep the date-level worker limit at exactly
two. H2-D-4 authorizes no scaled replay, scheduler, production workload, or
tier change. H2-D-5 remains a separate, unauthorized gate.

## Canary measurements

| Measurement | Result |
|---|---:|
| Status | `PASSED` |
| Sequential runtime | `4260.734213` seconds |
| Two-worker runtime | `2188.294593` seconds |
| Speedup | `1.9470569578619206` |
| Peak worker RSS | `381312` KiB |
| Worker limit | `2` |
| Surviving workers | `0` |
| Evidence writes | `0` |
| Read-only | `true` |
| Pre/post evidence unchanged | `true` |

The sequential leg used about one CPU core. The two-worker leg held near two
cores and remained below the four-core Render limit. Observed service memory
stayed below 700 MB of the available 8 GB. More Render CPU or RAM would not
improve the frozen two-worker canary enough to justify a tier change.

## Parity receipt

| Historical session | Session parity SHA-256 | Evidence snapshot SHA-256 |
|---|---|---|
| `2026-06-15` | `4aef9851962ff5c6ac328a80ed1305f25c71da0d1aa08f250fad5c4ccca84758` | `f10e484ac90a20a3d8a784461076e8eea3f5f53f3dc8d7f66b304f2fd330f891` |
| `2026-07-22` | `ee5c92cc0d611bc33b6f3a6a1ae1b32ee3e6f7153859a4f9badf73a9a14f0fc5` | `0be75a1ef632182816d345d6b827b96f81372c5c7db71f212c0a7afd4a57a546` |

Both control workers and both parallel workers exited `0`. Exact parity passed
for both dates without evidence mutation.

## Database and provider observations

After the canary, Supabase reported `ACTIVE_HEALTHY` on PostgreSQL 17.6. The
database exposed 120 direct connection slots; three client backends were
present when checked. Cumulative database statistics showed a 98.401398%
buffer-hit ratio, zero deadlocks, and zero conflicts. Performance advisors had
no H2-D-4 sizing blocker. Informational findings outside this phase were not
changed.

The pre-canary authentication proof connected both historical database URLs as
the dedicated `atom_historical_score_reader` role with
`transaction_read_only = on`. After that proof, the completed canary reported
no database or provider failure.

## Operational state

The benchmark start command was restored to `sleep infinity`, the worker was
manually suspended, and billing stopped. Production V9, evidence, mathematical
outputs, Render compute, and Supabase compute were not changed.
