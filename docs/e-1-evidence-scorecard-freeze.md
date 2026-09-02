# E-1 read-only evidence scorecard freeze

**Status:** LAW — documentation-only freeze, amended by E-1A; read-only implementation authorized only after E-1A merges and migration 029 is applied  
**Current runtime:** V9 thin, V4 worker, and SIM-4 worker on `main`; Family Evidence Cadence active since August 31  
**Next gate:** E-2 pre-registered single-hypothesis evaluation (separate amendment, not authorized here)

## Decision

**Evidence scoring before strategy change — September 2, 2026:** ATOM has
roughly two weeks of live COIN evidence and no canonical, reproducible
scorecard over it. Informal read-only queries on September 2 (not evidence; not
receipted) showed every family and the V9 synthesis at coin-flip hit rates
below 15M once midpoint ties are excluded, faint and unproven direction at
15M–1H, and no relationship between forecast magnitude and accuracy. Those
numbers are motivation only. Nothing in them changes V9, and this phase does
not act on them.

E-1 authorizes one read-only, single-process scorecard reader over existing
evidence. It produces a receipt. It changes nothing. Its purpose is to make the
ledger answer "is any cell worth a pre-registered test" with fixed statistics
that cannot be tuned after looking.

**E-1A amendment — September 2, 2026:** PR #261 merged with eleven unresolved
Codex review threads and a review that covered an earlier commit than the
merged head. This amendment dispositions every thread, applies the owner's
review notes, and freezes the one narrow privilege exception E-1 needs. E-1 is
gross candidate screening only: `cost_bps` is frozen at exactly `0.0`.

## Scope

The reader scores two layers over one explicit set of regular XNYS sessions:

- **FAMILY** — the window population is every row of `public.forecasts` in the
  cell `(quant_id, formula_version, symbol, horizon)`, left-joined to
  `public.forecast_outcomes` on `forecast_id`. Admissibility and outcome
  eligibility come only from the existing legacy publication-proof seam
  `atom_v9_internal.read_legacy_evidence_publications_for_records(text, timestamptz, bigint[])`,
  called with the population's `forecast_id` values in batches of at most
  `65536`, once with kind `DIRECTIONAL_FORECAST` and once with kind
  `DIRECTIONAL_OUTCOME`, at `p_as_of` equal to the receipt's snapshot time.
  A forecast is **admissible** only when a `DIRECTIONAL_FORECAST` proof exists
  and its `commit_observed_at` is strictly before `to_timestamp(maturity_epoch)`.
  An outcome is **eligible** only when a `DIRECTIONAL_OUTCOME` proof exists for
  the same `forecast_id` and the outcome's `resolved_epoch` lies in
  `[maturity_epoch, maturity_epoch + 5.0]`. These are the same timing rules
  `PostgresEvidenceStore.phase_e_cohorts` applies. The cohort reader
  `read_legacy_evidence_publications_for_cohorts` is **not** used: it clamps to
  256 rows per cohort. Proof logic is reused through the seam, never
  re-implemented.
- **V9** — the window population is every row of `public.atom_v9_v4_forecasts`
  whose decoded `evidence_origin` is `PRODUCTION`, in the cell
  `(v3_model_version, symbol, horizon, cohort_id, cohort_hash)`, left-joined to
  `public.atom_v9_v4_outcomes` on `forecast_record_id`. Values are decoded only
  through the existing `deserialize_forecast_record` and
  `deserialize_outcome_record` seams. Persistence eligibility is hydrated only
  through the authoritative proof reader
  `atom_v9_internal.read_forecast_commit_proof(text)` applied with
  `V4AWriter._apply_commit_proof`; a forecast is **admissible** only when the
  hydrated record's `persistence_proof_eligible` is `True`. Stored forecast JSON
  and deserialization alone never establish persistence eligibility. An outcome
  is **eligible** only when its `target_timing_status` is `VERIFIED` and its
  `proof_eligible` is `True`. Distinct cohorts are never pooled; a cohort with
  fewer than ten contributing sessions is `INSUFFICIENT` by construction.

Sessions are supplied as explicit UTC dates and echoed in the receipt. The
default is the most recent completed regular sessions, count supplied as an
input. Partial sessions are excluded.

## Frozen statistics

These rules are fixed before any receipt is produced and may not be changed in
E-1.

1. **Non-overlapping RTH windows.** Horizon seconds are exactly
   `30S=30, 1M=60, 5M=300, 15M=900, 30M=1800, 1H=3600`. Within a cell and
   session, order admissible forecasts by `(cutoff, primary key)` — `forecast_id`
   for FAMILY, `forecast_record_id` for V9 — ascending. Select the first forecast
   whose interval `[cutoff, cutoff + horizon_seconds]` lies inside 09:30–16:00
   America/New_York; thereafter select the next forecast whose cutoff is at
   least `horizon_seconds` after the previously selected cutoff and whose
   interval lies inside those hours. Selection restarts at each session. This
   is the same spacing rule the existing sparse effective-observation counter in
   `phase_e_cohorts` applies. Every admissible row outside those hours is
   counted as `n_non_rth`; every admissible in-hours row not selected because
   it is closer than `horizon_seconds` to the previous selection is counted as
   `n_overlap_excluded`. Selected forecasts are the cell's windows. Every cell
   reconciles exactly:
   `n_rows = n_inadmissible + n_population` and
   `n_population = n_non_rth + n_overlap_excluded + n_windows`.
2. **Window kinds.** Each window receives exactly one kind, tested in this
   order: `ABSTAIN` if the forecast is null, non-finite, or exactly `0`; else
   `INVALID_OUTCOME` if there is no eligible outcome or the outcome is null or
   non-finite; else `TIE` if the outcome is exactly `0`; else `DECIDED`. The four
   counts sum to `n_windows`. Abstentions and invalid outcomes are excluded from
   every metric. Ties are excluded from directional metrics and included as
   zero in economic metrics. `n_decided` is the `DECIDED` count; `n_economic` is
   `TIE + DECIDED`.
3. **Session counts.** `n_sessions` is the number of scored sessions in which
   the cell has at least one economic window; it is the bootstrap cluster count
   and the value the ten-session classification gate reads. `n_decided_sessions`
   is the number of scored sessions in which the cell has at least one decided
   window; it is used only by the hit-rate bootstrap. Requested sessions that
   contribute no window to a cell are not counted for that cell.
4. **Per-cell descriptive metrics.**
   `n_rows`, `n_inadmissible`, `n_population`, `n_non_rth`,
   `n_overlap_excluded`, `n_windows`, `n_abstain`, `n_invalid_outcome`,
   `n_ties`, `n_decided`, `n_economic`, `n_sessions`, `n_decided_sessions`;
   `hit_rate` (over decided windows) and
   `z_hit = (hit_rate - 0.5) * sqrt(n_decided) / 0.5`;
   `mean_signed_bps = mean(sign(forecast) * outcome)` over economic windows;
   `corr_forecast_outcome` (Pearson, economic windows);
   `calibration_corr = corr(|forecast|, |outcome|)` (economic windows); and
   `hit_rate_by_magnitude_quartile`, computed over decided windows ordered by
   `(|forecast|, cutoff, primary key)` ascending and partitioned into four
   contiguous rank groups with boundaries at `floor(k * n_decided / 4)` for
   `k = 1, 2, 3`; equal magnitudes may fall in different groups by that order;
   when `n_decided < 4` the field is an empty list.
   Undefined values are `null`: `hit_rate` and `z_hit` when `n_decided = 0`;
   either correlation when fewer than two points or zero variance in either
   input; both economic bootstrap intervals when `n_economic = 0`; and the
   hit-rate bootstrap interval whenever `n_decided = 0`, independently of the
   economic intervals, so a tie-only cell still produces a receipt. The receipt
   contains no `NaN` or infinity anywhere. `z_hit` and any plain-standard-error
   statistic are descriptive only: they are reported but never used for
   classification, because windows are serially dependent even when
   non-overlapping.
5. **Inference.** The only inferential statistic is a session-clustered
   percentile bootstrap. The economic cluster population is the `n_sessions`
   sessions with at least one economic window, sorted ascending; for each of
   exactly `200000` resamples, draw `n_sessions` sessions with replacement using
   CPython `random.Random(0).choices(sessions, k=n_sessions)`, seeded once per
   cell and consumed in order; the resampled statistic is the sum of the drawn
   sessions' signed-bps sums divided by the sum of their economic counts, which
   equals the mean over the pooled windows. The hit-rate bootstrap uses the
   same procedure over the `n_decided_sessions` sessions with at least one
   decided window, drawing `k = n_decided_sessions`, only when
   `n_decided > 0`. Sort the resampled statistics ascending and report the
   percentile interval whose zero-based indices are
   `lower = floor((1 - level) / 2 * (B - 1))` and
   `upper = ceil((1 + level) / 2 * (B - 1))` with `B = 200000`, at
   `level = 0.999` and `level = 0.95` for `mean_signed_bps` and at `level = 0.95`
   for `hit_rate`. Bootstrap parameters are fixed here and echoed in the
   receipt.
6. **Cost line.** `cost_bps` is frozen at exactly `0.0` for E-1 and is not an
   input. E-1 is gross candidate screening only. No nonzero or adjustable cost
   may affect classification before the separately authorized E-3 cost model.
   Bid/ask alone is quoted spread and must not be labeled realized or effective
   spread; E-1 measures no spread.
7. **Classification.** Each cell receives exactly one label:
   - `INSUFFICIENT` if `n_economic < 100` or `n_sessions < 10`;
   - `CANDIDATE` if not insufficient and the `0.999` session-clustered
     bootstrap interval for `mean_signed_bps` lies entirely above `0`;
   - `NOISE` otherwise.
   The `0.999` interval is the fixed multiplicity guard for every cell that is
   not `INSUFFICIENT`, in both layers, FAMILY and V9-cohort alike. The receipt
   reports `n_cells_eligible`, the count of such cells across both layers, and
   `expected_false_candidates = n_cells_eligible * 0.0005`. If
   `n_cells_eligible` exceeds `100`, the multiplicity budget is exceeded: the
   receipt sets `multiplicity_budget_exceeded = true`, every eligible cell is
   labeled `NOISE`, and no `CANDIDATE` may be assigned in that receipt. The
   level and the budget are not tunable per run. No cell may be labeled `EDGE`,
   `TRADEABLE`, or any positive claim. `CANDIDATE` means only "eligible for a
   pre-registered E-2 test." Negative intervals confer no label and authorize
   no sign-flip.
8. **No selection after looking.** The reader scores every cell in the layer.
   It has no family, horizon, cohort, or date filter other than the session set.

## Frozen boundaries

E-1 is read-only and single-process. Apart from the single exception in
"Authorized privilege exception" below, it adds no migration, table, role,
grant, policy, default privilege, index, queue, scheduler, service, endpoint,
UI, or compute change. It changes no V9 mathematics, thresholds, weights,
family code, synthesis, evidence, outcome, Truth credit, simulator behavior,
SIM-4 entry rule, broker, account, order, execution, or trading authority. It
adds no dependency beyond the Python standard library and the already-pinned
`psycopg`.

Database access is one explicitly read-only `REPEATABLE READ` transaction for
the entire run, with a per-statement timeout of at most `60s`, using the
existing credential `supabase_read_only_user`, which holds no `INSERT`,
`UPDATE`, or `DELETE` privilege on any table, already holds `USAGE` on
`atom_v9_internal` through `pg_read_all_data`, and holds `BYPASSRLS`, which is
required because all four evidence tables enforce row-level security whose
SELECT policies name only the runtime and proof-owner roles. The reader refuses
any credential that holds a write privilege on the four evidence tables and
refuses any credential without `BYPASSRLS`, because a policy-filtered read
would score an empty ledger as if it were evidence. All counts, both layer
reads, and every proof-seam call observe that one snapshot, and the receipt
records `pg_current_snapshot()`. The reader must not be run during regular XNYS
session hours; there is no override. Forecast, outcome, manifest, persistence,
receipt, and every other write must remain `0`. Existing evidence may not be
deleted, rewritten, repaired, or backfilled.

Implementation is limited to one module (`quant/evidence_scorecard.py`), one
command-line entry point, and tests. Statistics, including the bootstrap, are
pure functions over in-memory rows and are unit-tested on synthetic data with
hand-computed expected values and the fixed seed. The database read and each
proof-seam call are thin, separately tested seams.

## Authorized privilege exception

E-1's two proof seams are `STABLE`, `SECURITY DEFINER` functions owned by
`atom_v9_proof_owner` with `search_path = pg_catalog`, executable today only by
`atom_v9_proof_owner` and `atom_v9_v4_runtime`. `PUBLIC`, `anon`,
`authenticated`, and `service_role` cannot execute them and must remain unable
to. `supabase_read_only_user` already holds `USAGE` on `atom_v9_internal`
through `pg_read_all_data` and holds `BYPASSRLS`; no schema, table, or policy
grant is needed or authorized.

Production state verified on September 2, 2026 (PostgreSQL 17.6):
`pg_auth_members` holds exactly one row for member `postgres` in role
`atom_v9_proof_owner`, with grantor `supabase_admin`, `admin_option = true`,
`inherit_option = false`, `set_option = false`. The migration runner
`postgres` is not a superuser and does not inherit the owner's privileges, so
a bare `GRANT EXECUTE` fails. PostgreSQL records role grants per grantor: a
grant executed by `postgres` cannot modify the `supabase_admin` row and instead
creates a separate `postgres`-grantor row. The handoff below therefore uses a
temporary `postgres`-grantor row that exists only inside the migration
transaction, and never touches the `supabase_admin` row. This is the same
pattern migration `027` uses and verifies.

This amendment authorizes exactly two `EXECUTE` grants, to the existing
read-only role, applied by migration `029` as one transaction in exactly this
order, and nothing else:

```sql
-- migrations/029_authorize_e1_scorecard_proof_reads.sql
-- One transaction. Every ASSERT is a DO block that RAISEs on failure,
-- rolling back everything.

-- 1. ASSERT starting state: exactly one pg_auth_members row for
--    (member = postgres, role = atom_v9_proof_owner) with
--    grantor = supabase_admin, admin_option = true,
--    inherit_option = false, set_option = false;
--    has_schema_privilege('supabase_read_only_user',
--    'atom_v9_internal', 'USAGE') is true;
--    pg_roles.rolbypassrls is true for supabase_read_only_user; and
--    supabase_read_only_user can execute no function in atom_v9_internal.

-- 2. Temporary handoff: a second, postgres-grantor row.
GRANT atom_v9_proof_owner TO postgres WITH INHERIT TRUE, SET FALSE;

-- 3. The two authorized grants.
GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_forecast_commit_proof(text)
TO supabase_read_only_user;

GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
  )
TO supabase_read_only_user;

-- 4. Remove only the temporary row; the supabase_admin row is untouched.
REVOKE atom_v9_proof_owner FROM postgres GRANTED BY postgres;

-- 5. ASSERT the exact state from step 1 holds again.

-- 6. ASSERT supabase_read_only_user can EXECUTE both functions; PUBLIC,
--    anon, authenticated, and service_role can execute neither; and no
--    other function in atom_v9_internal is executable by
--    supabase_read_only_user.

-- 7. Any failed assertion RAISEs; the whole transaction rolls back.
```

Net membership change: none. The temporary row is created and removed inside
the same transaction and is proven absent at commit. Migration `029` contains
only that authorization. If the runner cannot create or revoke the temporary
row, the migration fails closed and the exception must be re-authorized with a
different mechanism; nothing is applied by hand. A third function grant, any
table privilege, policy, role, schema, or default-privilege change is not
authorized.

## Receipt and stopping rule

Each run emits one JSON receipt to standard output containing:

- the exact session dates scored, the frozen `cost_bps = 0.0`, bootstrap
  parameters, the snapshot marker, and the reader's code version;
- rows read from each of the four tables, rows returned by each proof-seam
  call, and the query wall time;
- every cell in both layers with all metrics in "Frozen statistics", both
  bootstrap intervals, the V9 cell's `cohort_id` and `cohort_hash`, and its
  label;
- `n_cells_eligible`, `expected_false_candidates`, and
  `multiplicity_budget_exceeded`;
- `forecast_writes=0`, `outcome_writes=0`, `evidence_writes=0`,
  `read_only=true`, `bypassrls=true`;
- a SHA-256 over the canonical JSON of everything above.

The receipt is evidence about evidence. It is not itself stored in the ledger
and it authorizes nothing. E-1 is complete after the first receipt over at
least ten regular sessions is produced and reviewed. That receipt is the
baseline for E-2.

## Order of work after E-1A merges

1. Migration `029` in its own PR under the merge gate.
2. Implementation in its own PR under the merge gate.
3. One receipt, after hours, on the suspended benchmark worker or locally.
No receipt, E-2, or E-3 work begins before all three, in that order.

## What E-1 does not authorize

- No E-2 hypothesis test. E-2 must freeze, before any further data is read,
  exactly one hypothesis: family set, equal weights, fixed signs, combination
  rule, horizon, evaluation sessions, primary endpoint, and pass/fail
  thresholds. The first evaluation window is a locked pilot for variance and
  cost estimation, not proof; the confirmatory sample size must be derived
  from the pilot's variance of net signed bps at a stated power, not from a
  binomial approximation.
- No cost model, spread measurement, or slippage assumption.
- No SIM-4 tradeability floor, position sizing by magnitude, or entry-rule
  change.
- No new market-data driver, symbol, family, or Parent-Child expansion.
- No retirement, reweighting, or sign-flip of any existing family.
