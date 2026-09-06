# E-4 driver candidates roadmap

**Status:** PROPOSED — roadmap only; authorizes no implementation  
**Depends on:** the E-2 confirmatory receipt (`PASS`, `FAIL`, or `UNDERPOWERED`) exists  
**Next gate:** E-4a freeze (separate amendment)

## Decision

**One driver at a time, after the composite has been judged — September 2,
2026:** the families can only find structure present in what they observe.
Today that is COIN midpoints from HTTP quote polling and an NDX reference.
Two candidate drivers are named here so that their order is fixed before any
result is known, and so that neither is added while `E2-H1` is being
evaluated. Adding a driver during the composite test would make the result
unattributable.

This document authorizes nothing. Each sub-phase below requires its own
freeze, its own pre-registration, and its own receipts.

## Ordered candidates

### E-4a — BTC reference (observer only)

- **Rationale:** COIN is a levered crypto-beta proxy; a 24/7 BTC reference
  can carry overnight and intraday information that no current input sees.
- **Shape:** follow the S0/S1 pattern exactly — a disabled, isolated,
  read-only observer with deterministic freshness, deduplication, and
  transient publication; no evidence write, no family input, no UI. The E-4a
  freeze must name the single source, its freshness bound, and the exact
  feature (a trailing BTC log return ending at least one second before the
  COIN cutoff).
- **Test:** a separate E-4b pre-registration, in the E-2 form, evaluating the
  frozen feature as a standalone direction signal at 15M on E-1 windows with a
  locked pilot, fixed confirmatory formula, and the same PASS rule. Only after
  E-4b `PASS` may a further amendment consider a family or synthesis change.

### E-4c — COIN Level II order-book imbalance

- **Rationale:** the Schwab Level II worker already runs observer-only;
  book imbalance is among the better-documented short-horizon predictors.
- **Governance:** Level II is already governed by S2B (market-hours proof,
  pending) and S3 (optional Q5 successor). E-4c adds nothing to those phases
  and may not run ahead of them. When S2B has passed, an E-4c pre-registration
  in the E-2 form evaluates one frozen imbalance feature at 15M before any S3
  consideration.

## Ordering rule

E-4a before E-4c. Neither begins before the E-2 confirmatory receipt exists.
No driver is evaluated together with another driver or with a composite
change in the same window. A `FAIL` on a driver closes that driver's
hypothesis; a variation is a new pre-registration.

## Explicitly not on this roadmap

- Symbol expansion. Correlated names do not multiply independent evidence and
  invite selection bias; the scoring protocol proves itself on COIN first.
- Parent-Child quant expansion. Governed separately; not a driver.
- Any sign-flip or retirement of an existing family on the strength of a
  scorecard.
- Any SIM-4, sizing, runtime, broker, or trading change.
