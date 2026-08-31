# H2-D-5 bounded scaled-replay freeze

**Status:** LAW — implementation authorized; execution not yet passed  
**Current runtime:** H2-D-1 sequential  
**Next gate:** one four-session read-only scale proof

## Decision

H2-D-5 may run exactly four certified sessions in exactly two ordered batches
of two worker processes. Each worker owns one complete date. Work inside a date
remains chronological and sequential. The worker limit remains two on the
existing Render 4 CPU / 8 GB benchmark service.

The frozen sessions are:

| Historical session | Immutable replay run ID |
|---|---|
| `2026-06-17` | `h2d-2026-06-17` |
| `2026-06-18` | `h2d-2026-06-18` |
| `2026-06-22` | `h2d-2026-06-22` |
| `2026-06-23` | `h2d-2026-06-23` |

No other date or replay identity is accepted.

## Read-only parity contract

For each date, the worker must:

1. Read the existing certified manifest, forecasts, outcomes, and 72 scoring
   metrics through the dedicated read-only database roles.
2. Run H1 into a local temporary spool without persistence.
3. Require exact equality for session identity, replay identity, dataset,
   configuration, lineage, frame and availability counts, artifact hash,
   ordered forecast hash, outcome hash, and all 72 canonical metrics.
4. Read the stored control again after the scaled run and require byte-exact
   equality with the pre-run control.

No tolerance, repair, partial promotion, or date replacement is allowed. No
evidence insert, update, delete, repair, or recertification is authorized.

## Operational boundary

- Execute exactly two ordered batches of two worker processes.
- Start no nested process, thread, executor, queue, or asynchronous task inside
  a date worker.
- A date or worker failure fails the complete proof and stops the active peer.
- Only the existing bounded transient database reconnect behavior may retry a
  read. A complete date is never rerun automatically.
- Each batch and the whole proof have finite timeouts. Every process must be
  terminated and joined on failure or timeout.
- The final receipt records ordered session receipts, control hashes, elapsed
  time, worker exit codes, peak worker memory, zero writes, and zero survivors.

## Exclusions and promotion

H2-D-5 authorizes no Render or Supabase tier change, scheduler, continuous
replay, production deployment, baseline rewrite, V9 change, or evidence write.
Production `atom-v9-thin` remains untouched. Passing this proof returns the
benchmark service to `sleep infinity` and suspension. H2-D-6 remains
unauthorized until the H2-D-5 receipt passes a separate freeze decision.
