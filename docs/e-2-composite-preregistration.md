# E-2 pre-registered single hypothesis: 15M trend composite

**Status:** PROPOSED — pre-registration; evaluator implementation authorized only after merge; exactly one pilot evaluation and, if warranted, exactly one confirmatory evaluation  
**Depends on:** `docs/e-1-evidence-scorecard-freeze.md` merged and one E-1 baseline receipt produced  
**Hypothesis ID:** `E2-H1`  
**Next gate:** E-3 cost model (separate amendment); nothing in E-2 authorizes trading

## Decision

**Lock the hypothesis before more data — September 2, 2026:** Informal
read-only queries on September 2 over roughly two weeks of COIN evidence showed
trend-type families leaning positive and reversion-type families leaning
negative at 15M–1H. That observation was made after looking at every family and
horizon; it is a data-selected pattern, not a finding. E-2 turns it into one
frozen, falsifiable hypothesis whose membership, weights, signs, horizon,
endpoint, cost line, sample windows, and pass/fail rule are fixed here and may
not be adjusted after any further data is read.

Evidence produced before this document merges was used to form `E2-H1` and is
formation data. It may never count toward the pilot or the confirmatory
evaluation.

## Hypothesis `E2-H1`

An equal-weight, fixed-sign direction vote of the five trend-type families has
positive mean cost-adjusted signed return on COIN at the 15M horizon over
non-overlapping regular-trading-hours windows.

### Frozen composite rule

- **Members:** `q1_momentum`, `q5_microstructure`, `q9_factor`, `q11_regime`,
  `q12_event_session`. Exactly these five. No addition, removal, or
  substitution.
- **Signs:** every member enters with sign `+1` — its own forecast direction as
  persisted. No member is flipped.
- **Weights:** equal. Magnitude is not used; the informal look showed no
  relationship between forecast magnitude and accuracy, so the composite is a
  direction vote at unit size.
- **Window:** the E-1 independent 15M window (epoch-aligned interval of `900`
  seconds), RTH-only exactly as E-1 defines it.
- **Member forecast in a window:** the member's earliest-cutoff persisted 15M
  forecast in that interval, as E-1 selects it.
- **Anchor:** the included member forecast with the latest cutoff. All
  included member cutoffs must fall within `60` seconds before the anchor;
  members outside that band abstain for the window. Decision time is the
  anchor cutoff, so no member forecast used is later than the decision.
- **Vote:** sum of member signs over included, non-abstaining members. Direction
  is the sign of the sum. The composite **abstains** when fewer than `3` members
  are included or the sum is `0`.
- **Outcome:** the persisted `outcome_bps` of the anchor forecast — the realized
  15M midpoint log return from the decision time. No other outcome may be used.
- **Ties, abstentions, unresolved:** exactly as E-1.

### Frozen endpoints

- **Primary:** `mean_cost_adjusted_bps` = mean over economic windows (ties as
  zero) of `direction × outcome_bps` minus `cost_bps`.
- **Secondary (descriptive):** hit rate over decided windows, abstention rate,
  tie rate, windows per session, calibration of `|anchor forecast|` against
  `|outcome|`, and the E-1 statistics for each member alone.
- **Cost line for the pilot:** `cost_bps = 5.0`, a declared executable-cost
  assumption (round-trip crossing of the quoted spread plus slippage). It is
  echoed in the receipt. It is replaced only by the E-3 measured value, and only
  for the confirmatory evaluation.
- **Inference:** the E-1 session-clustered bootstrap, unchanged: `2000`
  resamples, seed `0`, `95%` and `99.9%` percentile intervals.

## Pilot (locked)

- **Sessions:** the first `20` regular XNYS sessions that begin after the later
  of (a) this document's merge and (b) the first E-1 baseline receipt. The exact
  dates are recorded in the pilot receipt.
- **Lock:** no composite evaluation of any kind runs before the 20th pilot
  session closes. E-1 family receipts may be produced during the pilot; they do
  not compute the composite.
- **One run:** the pilot evaluation executes exactly once, after hours, and its
  receipt is final.
- **Purpose:** variance and cost estimation. The pilot is not proof and cannot
  pass or fail `E2-H1`.
- **Pilot outputs:** all endpoints above; the session-clustered standard error
  `SE` of the primary endpoint (interval half-width at `95%` divided by `1.96`
  is not used — `SE` is the standard deviation of the bootstrap draws); the
  per-window standard deviation `s = SE × sqrt(n_economic)`; and the
  confirmatory sample size below.

### Confirmatory sample size (fixed formula)

- Minimum detectable effect `MDE = 2.0` bps net per window.
- One-sided `alpha = 0.05` (`z = 1.645`), power `0.80` (`z = 0.842`).
- `N_conf = ceil(((1.645 + 0.842)^2 × s^2) / MDE^2)` economic windows.
- `sessions_conf = ceil(N_conf / mean economic windows per pilot session)`.
- If `sessions_conf > 60`, `E2-H1` is `UNDERPOWERED` and closed. No
  confirmatory run occurs.

## Confirmatory evaluation (locked)

- **Sessions:** the `sessions_conf` regular sessions immediately following the
  pilot. No overlap with the pilot. Exact dates recorded before the first one
  opens.
- **One run:** exactly once, after hours, after the last session closes.
- **Cost line:** the E-3 measured executable-cost value if E-3 has merged and
  produced its receipt before the confirmatory window opens; otherwise `5.0`.
  The value used is recorded in the receipt and may not be changed afterwards.
- **PASS** if and only if all three hold:
  1. the `95%` session-clustered interval of the primary endpoint lies entirely
     above `0`;
  2. the point estimate of the primary endpoint is at least `MDE`;
  3. the `95%` session-clustered interval of the hit rate lies entirely above
     `0.5`.
- **FAIL** otherwise.

A `PASS` authorizes only a separate replication amendment on a fresh window.
It authorizes no SIM-4 change, no sizing, no runtime, and no trading.
A `FAIL` or `UNDERPOWERED` closes `E2-H1`. Any variation — different members,
signs, weights, horizon, vote threshold, band, cost, MDE, or thresholds — is a
new hypothesis requiring a new ID, a new pre-registration, and a new pilot.

## Frozen boundaries

E-2 is read-only research. The evaluator is one module and its tests, reusing
the E-1 reader and statistics; it adds no migration, table, role, grant,
index, service, scheduler, endpoint, UI, dependency, or compute change. The
composite exists only inside the evaluator: it is not a family, not a V9
input, not persisted, not displayed, and not deployed. No V9 mathematics,
family code, synthesis, evidence, outcome, Truth credit, simulator, SIM-4,
broker, account, order, execution, or trading authority changes. The
evaluator must not run during regular XNYS hours. Every write counter must
remain `0`.

## Receipts

The pilot receipt and the confirmatory receipt each contain: hypothesis ID,
the exact frozen rule above, exact session dates, `cost_bps` used and its
source, bootstrap parameters, member-level E-1 statistics, every composite
endpoint with intervals, window counts by kind, `forecast_writes=0`,
`outcome_writes=0`, `evidence_writes=0`, `read_only=true`, and a SHA-256 over
the canonical JSON. The confirmatory receipt also states `PASS`, `FAIL`, or
`UNDERPOWERED` and nothing else.
