# E-1 read-only evidence scorecard freeze

**Status:** LAW — documentation-only freeze, amended by E-1A and E-1B; read-only implementation authorized only after E-1B merges and migration 030 is applied  
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

**E-1B amendment — September 2, 2026:** E-1A named `supabase_read_only_user`
as the reader credential. That role is platform-managed: its password is set
by Supabase, is not exposed to the owner, and cannot be reset by `postgres`
(no admin option), so no receipt can be run with it. The owner chose, from two
presented options, to reuse the existing dedicated read-only role
`atom_historical_score_reader`, whose credential is already provisioned on the
benchmark worker. E-1B changes only the credential, the row-level-security
rule that follows from it, and the privileges migration `030` may apply.
Every statistic, boundary, and label in this freeze is unchanged.

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
   and the value the ten-session eligibility minimum reads. `n_decided_sessions`
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
7. **Classification and multiplicity budget.** A cell is **eligible** when it
   satisfies both classification minimums: `n_economic >= 100` and
   `n_sessions >= 10`. `INSUFFICIENT` cells are those that are not eligible;
   they keep that label and never consume the budget.
   The multiplicity budget is exactly `100` eligible cells across the complete
   receipt, both layers, FAMILY and V9-cohort alike. The receipt reports
   `n_cells_eligible`, `multiplicity_budget = 100`, and
   `expected_false_candidates = n_cells_eligible * 0.0005`. Exactly `100`
   eligible cells is permitted.
   When `n_cells_eligible <= 100`, each eligible cell receives exactly one
   label: `CANDIDATE` if the `0.999` session-clustered bootstrap interval for
   `mean_signed_bps` lies entirely above `0`, otherwise `NOISE`. The `0.999`
   interval is the fixed guard for every eligible cell.
   When `n_cells_eligible > 100`, the budget is exceeded: every descriptive
   statistic and every interval is preserved and reported unchanged; the
   receipt sets `multiplicity_budget_exceeded = true` and records the
   eligible-cell count and the cap; every `CANDIDATE` classification is
   withheld; no eligible cell is relabeled `NOISE`, because that would be
   statistically misleading; each eligible cell's `label` is `null` with
   `classification_reason = MULTIPLICITY_BUDGET_EXCEEDED`; and the receipt is
   unusable for promotion or E-2 inference (`usable_for_e2 = false`).
   The level, the budget, and this behavior are fixed. No dynamic cap,
   automatic threshold adjustment, or phase expansion. Expansion to more
   symbols requires a separately pre-registered multiplicity phase. No cell may
   be labeled `EDGE`, `TRADEABLE`, or any positive claim. `CANDIDATE` means
   only "eligible for a pre-registered E-2 test." Negative intervals confer no
   label and authorize no sign-flip.
8. **No selection after looking.** The reader scores every cell in the layer.
   It has no family, horizon, cohort, or date filter other than the session set.

## Frozen boundaries

E-1 is read-only and single-process. Apart from the exceptions in "Authorized
privilege exception" below, it adds no migration, table, role, grant, policy,
default privilege, index, queue, scheduler, service, endpoint, UI, or compute
change. It changes no V9 mathematics, thresholds, weights, family code,
synthesis, evidence, outcome, Truth credit, simulator behavior, SIM-4 entry
rule, broker, account, order, execution, or trading authority. It adds no
dependency beyond the Python standard library and the already-pinned
`psycopg`.

Database access is one explicitly read-only `REPEATABLE READ` transaction for
the entire run, with a per-statement timeout of at most `60s`, using the
existing credential `atom_historical_score_reader`: the `LOGIN`, `NOINHERIT`,
`NOBYPASSRLS`, non-superuser role created by
`supabase/migrations/20260826144639_create_historical_replay_outcomes.sql`,
already provisioned on the benchmark worker as `HISTORICAL_SCORE_DATABASE_URL`,
holding no `INSERT`, `UPDATE`, or `DELETE` privilege on any table. Its existing
`SELECT` on the three `atom_historical_replay_*` tables and every H2-D contract
that reads through it are unchanged.

Because that role cannot bypass row-level security, migration `030` grants it
a permissive `USING (true)` `SELECT` policy on each of the four evidence
tables, and the reader verifies full read before reading anything. For each of
the four tables it asserts `has_table_privilege(current_user, table, 'SELECT')`,
that `pg_policies` holds a `SELECT` policy whose `roles` include
`current_user` with `permissive = 'PERMISSIVE'` and `qual = 'true'`, and that
no restrictive `SELECT` policy on that table applies to `current_user`. The
receipt records `rls_full_read_verified = true`. The reader refuses any
credential that holds a write privilege on the four evidence tables and
refuses any credential that fails full-read verification, because a
policy-filtered read would score an empty ledger as if it were evidence. The
credential value never leaves Render: the benchmark worker's start command
passes `HISTORICAL_SCORE_DATABASE_URL` into
`ATOM_E1_SCORECARD_READONLY_DATABASE_URL` for the reader process, and the
reader reads only that variable. All counts, both layer reads, and every
proof-seam call observe that one snapshot, and the receipt records
`pg_current_snapshot()`. The reader must not be run during regular XNYS
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
`atom_v9_proof_owner` with `search_path = pg_catalog`. `PUBLIC`, `anon`,
`authenticated`, and `service_role` cannot execute them and must remain unable
to. The four evidence tables and the schema `atom_v9_internal` are owned by
`postgres`, so table grants, policies, and schema usage need no ownership
handoff; only function grants do.

Production state verified on September 2, 2026 (PostgreSQL 17.6):
`pg_auth_members` holds exactly one row for member `postgres` in role
`atom_v9_proof_owner`, with grantor `supabase_admin`, `admin_option = true`,
`inherit_option = false`, `set_option = false`. The migration runner
`postgres` is not a superuser and does not inherit the owner's privileges, so
a bare `GRANT EXECUTE` on those functions fails. PostgreSQL records role grants
per grantor: a grant executed by `postgres` cannot modify the `supabase_admin`
row and instead creates a separate `postgres`-grantor row. Function grants
therefore use a temporary `postgres`-grantor row that exists only inside the
migration transaction and never touches the `supabase_admin` row. This is the
same pattern migration `027` uses and verifies.

**Migration `029` (E-1A, applied September 2, 2026):** granted `EXECUTE` on
both proof readers to `supabase_read_only_user`. E-1B supersedes that
credential; `030` withdraws those two grants so exactly one E-1 credential
exists.

**Migration `030` (E-1B):** authorizes exactly the following, as one
transaction in this order, and nothing else:

```sql
-- migrations/030_authorize_e1_scorecard_score_reader.sql
-- One transaction. Every ASSERT is a DO block that RAISEs on failure,
-- rolling back everything.

-- 1. ASSERT starting state:
--    atom_historical_score_reader exists with LOGIN, NOSUPERUSER,
--    NOBYPASSRLS; holds no INSERT, UPDATE, or DELETE on any table; holds
--    SELECT on exactly atom_historical_replay_forecasts,
--    atom_historical_replay_outcomes, atom_historical_replay_runs and on
--    no other table; holds no USAGE on atom_v9_internal; has no policy on
--    any of the four evidence tables; the four evidence tables and the
--    schema atom_v9_internal are owned by postgres; the postgres
--    membership row in atom_v9_proof_owner is exactly as in 029 step 1;
--    supabase_read_only_user can execute exactly the two 029 functions
--    and no other function in atom_v9_internal.

-- 2. Schema usage and table reads (postgres owns these; no handoff).
GRANT USAGE ON SCHEMA atom_v9_internal TO atom_historical_score_reader;

GRANT SELECT ON public.forecasts, public.forecast_outcomes,
                public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes
TO atom_historical_score_reader;

-- 3. One permissive full-read SELECT policy per evidence table.
CREATE POLICY forecasts_e1_scorecard_select
  ON public.forecasts FOR SELECT TO atom_historical_score_reader USING (true);
CREATE POLICY forecast_outcomes_e1_scorecard_select
  ON public.forecast_outcomes FOR SELECT TO atom_historical_score_reader USING (true);
CREATE POLICY atom_v9_v4_forecasts_e1_scorecard_select
  ON public.atom_v9_v4_forecasts FOR SELECT TO atom_historical_score_reader USING (true);
CREATE POLICY atom_v9_v4_outcomes_e1_scorecard_select
  ON public.atom_v9_v4_outcomes FOR SELECT TO atom_historical_score_reader USING (true);

-- 4. Temporary handoff for the proof-owner functions (as 029 step 2).
GRANT atom_v9_proof_owner TO postgres WITH INHERIT TRUE, SET FALSE;

-- 5. Move the two EXECUTE grants from the superseded credential.
GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_forecast_commit_proof(text)
TO atom_historical_score_reader;
GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
  )
TO atom_historical_score_reader;
REVOKE EXECUTE ON FUNCTION
  atom_v9_internal.read_forecast_commit_proof(text)
FROM supabase_read_only_user;
REVOKE EXECUTE ON FUNCTION
  atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
  )
FROM supabase_read_only_user;

-- 6. Remove only the temporary row (as 029 step 4).
REVOKE atom_v9_proof_owner FROM postgres GRANTED BY postgres;

-- 7. ASSERT final state: the membership state from step 1 holds
--    exactly; atom_historical_score_reader holds SELECT on the four
--    evidence tables and the three historical tables and on no other
--    table, holds no INSERT, UPDATE, or DELETE anywhere, holds USAGE on
--    atom_v9_internal, can execute exactly the two authorized functions
--    and no other function in atom_v9_internal, and is named by exactly
--    one permissive SELECT policy with qual true on each evidence table;
--    supabase_read_only_user can execute no function in
--    atom_v9_internal; PUBLIC, anon, authenticated, and service_role can
--    execute neither function and hold no SELECT on the four evidence
--    tables; every pre-existing policy on the four tables is unchanged.

-- 8. Any failed assertion RAISEs; the whole transaction rolls back.
```

Net membership change: none. Net credential change: none — no role is
created, no password is set or reset. Migration `030` contains only that
authorization. A third function grant, any privilege for any other role, any
`BYPASSRLS` attribute, any change to an existing policy, or any
default-privilege change is not authorized.

## Receipt and stopping rule

Each run emits one JSON receipt to standard output containing:

- the exact session dates scored, the frozen `cost_bps = 0.0`, bootstrap
  parameters, the snapshot marker, and the reader's code version;
- rows read from each of the four tables, rows returned by each proof-seam
  call, and the query wall time;
- every cell in both layers with all metrics in "Frozen statistics", both
  bootstrap intervals, the V9 cell's `cohort_id` and `cohort_hash`, its
  `label`, and its `classification_reason` (`null` unless the budget is
  exceeded);
- `n_cells_eligible`, `multiplicity_budget = 100`,
  `expected_false_candidates`, `multiplicity_budget_exceeded`, and
  `usable_for_e2`;
- `forecast_writes=0`, `outcome_writes=0`, `evidence_writes=0`,
  `read_only=true`, `rls_full_read_verified=true`, and the reader's
  `current_user`;
- a SHA-256 over the canonical JSON of everything above.

The receipt is evidence about evidence. It is not itself stored in the ledger
and it authorizes nothing. E-1 is complete after the first receipt over at
least ten regular sessions is produced and reviewed. A receipt with
`multiplicity_budget_exceeded = true` does not complete E-1 and is not a
baseline for E-2. That receipt is the baseline for E-2 only when
`usable_for_e2 = true`.

## Order of work after E-1B merges

1. Migration `030` in its own PR under the merge gate, then applied once as a
   single transaction through the migration runner.
2. Implementation in its own PR under the merge gate, including the full-read
   verification above.
3. One receipt, after hours, on the suspended benchmark worker: the owner sets
   the start command to
   `ATOM_E1_SCORECARD_READONLY_DATABASE_URL="$HISTORICAL_SCORE_DATABASE_URL" python -m quant.evidence_scorecard --recent-sessions 10; sleep infinity`,
   resumes the service, the receipt is captured from the service logs, and
   the owner restores `sleep infinity` and suspends the service. The
   operator holds no tool that changes a start command or resumes a service.
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
