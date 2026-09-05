# Correction 3 — `threshold_status` is a different problem, and it answers itself on 2026-09-23

Issued 2026-09-05 by Claude (read-only reviewer). Follows Corrections 1 and 2.
No preregistered statistic computed; sources in §6.

## 1. The gate

`build_thresholds` (`quant/v9_v4c_predictive.py:379`):

```python
valid = tuple(x for x in observations if _resolved_by(x, reference_end) and math.isfinite(x.actual_bps))
magnitudes = tuple(abs(x.actual_bps) for x in valid); neff, reasons = effective_n(magnitudes)
sessions = len({x.session_id for x in valid})
mature = bool(magnitudes) and sessions >= 20 and neff >= 500
```

Three conditions, ANDed: non-empty, **`sessions >= 20`**, and **`neff >= 500`**.
`observations` is the calibration pool — the growing side — so unlike
`range_status` this gate is not computed on a population pinned at 250.

Two things to note. `neff >= 500` is **2.5x** the scale gate's 200. And the
series is `abs(x.actual_bps)` — absolute *realized return*, not absolute error,
so it is a third series distinct from anything persisted.

## 2. Why every horizon is UNAVAILABLE right now: the session count

The current V4C evidence window is **2026-08-26 12:05Z to 2026-09-04 23:57Z**.
That is Aug 26, 27, 28, 31 and Sep 1, 2, 3, 4 — **8 trading sessions.**

`sessions >= 20` therefore fails at every horizon, whatever the pool size. That
is sufficient on its own to explain 30S being UNAVAILABLE with 4,773 calibration
pairs. No inference needed.

**This is not the `range_status` defect.** It is a population that grows with
time, and the condition clears on schedule:

| | |
|---|---|
| Sessions in pool now | 8 |
| Needed | 20 |
| Remaining trading days | 12 (Sep 8-11, 14-18, 21-23; Sep 7 is Labor Day) |
| 20th session lands | **Wednesday 2026-09-23** |

## 3. What is currently unobservable, and why that matters

Because `sessions >= 20` and `neff >= 500` are ANDed into a single status, the
persisted state **cannot tell us today whether `neff >= 500` is reachable.** The
session count masks it at every horizon.

On 2026-09-23 that mask lifts, and 30S becomes a free natural experiment: its
calibration pool will be roughly 7,000 pairs and its session count will reach 20
on the same day. Then:

- `threshold_status` flips to MATURE -> `neff >= 500` is satisfiable, and
  `threshold_status` is merely slow, not defective.
- `threshold_status` stays UNAVAILABLE -> `neff >= 500` is the binding
  constraint, and it is a **harder** version of the Correction 2 problem: 500 on
  a series whose analogues plateau in the low hundreds.

I am not going to predict which. The persisted evidence is genuinely split:
at 30S, N_eff is **213.9** on the absolute-error series but **645.6** on the
squared-error series. `build_thresholds` uses a third series again. Guessing
between those is exactly the error I made twice already in this review.

## 4. Recommendation to the freeze author

**Do not legislate `threshold_status` in either direction before 2026-09-23.**
Waiting costs nothing — no cell can satisfy any V4C maturity gate before then
anyway — and on that date the system answers the question at no cost and with
certainty. Legislating now means guessing at the very thing that is about to
become observable.

This is a different disposition from `range_status`, where Correction 2 shows the
population is pinned at 250 permanently and no amount of waiting resolves it.
Concretely:

- `range_status` — structural. Needs an exclusion from READY, or an
  implementation change to the split, under its own freeze and phase.
- `threshold_status` — undetermined. Needs a two-and-a-half-week wait, then one
  observation.
- `scale_status` — partially cleared (30S and 1M MATURE); at 1H it is a long
  accumulation problem, mid-October to leave UNAVAILABLE, per Correction 2.

## 5. A latent session-boundary inconsistency

V4C derives `session_id` as `forecast.cutoff_at.date().isoformat()` — a **UTC**
calendar date (`quant/evidence_outbox.py:517` and `:532`). Everywhere else in the
codebase sessions come from `session_of()`
(`quant/evidence_scorecard.py:119`), which converts to `America/New_York` first.
Two different session definitions in one pipeline.

Measured impact today: **none.** Of 545,230 forecasts since 2026-08-26, zero have
a cutoff at or after 20:00 ET, and distinct ET dates (8) equal distinct UTC dates
(8). The observed cutoff window is 05:31-19:59 ET, which never crosses the
20:00 ET / 00:00 UTC boundary.

It is latent, not active. But if COIN coverage is ever extended past 20:00 ET,
the V4C session count silently diverges from every other session boundary:
`sessions >= 20` would pass before 20 real trading sessions, and one ET session
would split into two `session_id` values. It also feeds
`rolling_session_ids[-20:]` in `calibrate_range`. Worth pinning to `session_of()`
in a future implementation phase; it is not a reason to hold the amendment.

## 6. Provenance

Code at `origin/main`: `quant/v9_v4c_predictive.py:379-386`,
`quant/evidence_outbox.py:509-536`, `quant/evidence_scorecard.py:119`. Counts
from read-only SQL against production project `afyiydxbjgzaiswnbcyj` on
2026-09-05, against `atom_v9_v4_states` and a `count(*)`/`count(distinct)` on
`atom_v9_v4_forecasts.cutoff_at` only. No row content was read from the ledger
and no gate statistic was computed. No state changed.
