# V2 unlimited-history refresh: bounded-memory blocker

## Decision

Do not ship a purported streaming repair against the frozen V2 implementation.
The database reader accumulates every page, but removing that accumulation alone
does not bound the build: every later V2 stage also retains data proportional to
the lifetime evidence count. Producing byte-for-byte identical V2 output with
bounded memory therefore requires a coordinated external-memory redesign of the
frozen V2-A through V2-D pipeline. That exceeds the permitted query/index-only
repair and risks changing frozen floating-point results.

No production rebuild, migration, permission change, merge, or deployment was
performed as part of this investigation.

## Root cause and retention proof

`PostgresV2StateBuilder.read_pages()` extends one list for every keyset page and
returns a tuple containing the complete directional or magnitude history. It
then creates per-horizon target and observation lists and a list containing every
source identity. Peak memory consequently grows with evidence count before V2-A
starts.

The frozen math is not an iterator-based consumer that can safely replace those
lists:

* V2-A groups all targets and observations in dictionaries of lists, constructs
  canonical target and family-observation tuples, constructs support sets, and
  embeds those tuples in the hashed `V2ADataset`.
* V2-B copies every admitted family into `x`, `y`, score, residual, and calibrated
  tuples and makes repeat passes whose `math.fsum` order is part of the exact
  output.
* V2-C creates identity-to-residual dictionaries, pair lists, score tuples, and
  complete-case matrices over the admitted history.
* V2-D validates the upstream content hashes. Substituting incremental summaries
  would therefore alter the frozen input objects and their hashes, even before
  considering floating-point reduction order.

Thus a generator at the SQL boundary would only move the unbounded retention to
V2-A. A disk spool would bound the reader but not runtime memory when the frozen
builders materialize it. Neither is honestly bounded-memory processing.

## Query investigation boundary

The page SQL orders and keysets on
`(f.horizon, f.cutoff_epoch, f.forecast_id)`, while the migrations present in the
deployed tree add a proof-publication index and only a forecast
`(cycle_id, forecast_id)` index. Static inspection therefore cannot prove that a
supporting composite forecast index exists in production.

There is no production database connection in this worktree environment.
Accordingly, this investigation cannot truthfully provide:

* `EXPLAIN (ANALYZE, BUFFERS)` for a representative production cutoff;
* the effective production `statement_timeout` (including role/database/session
  overrides);
* the canceled backend statement or log evidence needed to distinguish the V2
  builder query from the unrelated replay-history query; or
* before/after production query plans.

Those facts must be captured read-only from the affected database before choosing
an index. Adding a speculative migration without the plan could create the wrong
large index and would not solve the independently proven memory blocker.

## Safe next design step

Obtain explicit approval to redesign V2-A through V2-D as an external-memory
pipeline. The design must define a canonical on-disk record format, stable merge
ordering, exact duplicate/conflict grouping, external support joins, and
reduction algorithms proven bit-identical to today's ordered `math.fsum` calls.
Only after parity and bounded-RSS tests pass at every required row count should a
query plan drive a narrowly targeted `CREATE INDEX CONCURRENTLY` migration with
a short lock timeout.

Until then, fail closed and retain the latest valid V2 state and its historical
evidence. Do not publish a receipt or candidate state from a partial build.
