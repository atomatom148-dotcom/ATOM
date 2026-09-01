# ATOM TRUE V9 — S2 NDX Production Activation Freeze

**Status:** LAW after merge  
**Change type:** Documentation and bounded repair only  
**Authorized operational path:** Existing independent NDX benchmark/display seam only  
**Level II status:** Observer-only; separate market-hours proof still required

## 1. Decision

Production activation of the read-only Schwab `$NDX` quote is authorized through ATOM's existing independent NDX benchmark/display seam.

The activation may:

1. merge the already-bounded NDX bridge after its latest-head checks and review pass;
2. deploy the resulting `main` commit to the existing `atom-v9-thin` web service; and
3. after the static service-authentication prerequisite below is present, change only the activation switch:

```text
ATOM_SCHWAB_NDX_ENABLED=true
```

The bridge may replace only the existing Massive NDX poller. It may not add a new display, family input, evidence path, or decision path.

## 2. Exact source, authentication, and destination boundary

The authorized source is the existing read-only route:

```text
https://coin-market-api.onrender.com/schwab/quote/%24NDX
```

The Coin service protects this route with its existing private-site HTTP Basic authentication. Before NDX activation, `atom-v9-thin` must have these static, non-Schwab service-authentication mappings:

```text
ATOM_COIN_MARKET_USERNAME = Coin service APP_USERNAME
ATOM_COIN_MARKET_PASSWORD = Coin service APP_PASSWORD
```

These values are prerequisites, not activation switches. They may authenticate only the exact HTTPS origin and exact `$NDX` quote route above. The bridge must reject redirects rather than forwarding credentials to another origin or to HTTP. Credentials must never be logged, returned by an API, committed to GitHub, or reused for any account, order, execution, Level II, or trading path.

The authorized destination is only the existing NDX benchmark/display handoff already represented by the live market state's `NDX` input.

The bridge must:

- accept only an explicitly successful `READ ONLY` `$NDX` response;
- require the wrapper symbol to be exactly `$NDX`;
- preserve the provider event timestamp;
- enforce the existing NDX freshness limit independently of Coin polling progress;
- reject wrong-symbol, malformed, stale, future, redirected, or invalid values;
- publish only NDX fields when an NDX update or expiry occurs during an in-flight COIN cycle;
- publish honest NDX unavailability rather than zero or retained stale data; and
- remain disabled unless the exact environment flag above is true.

No Schwab credential or token moves into ATOM. The existing Coin-market-api service remains the Schwab credential-owning boundary.

## 3. NDX activation is independent of COIN Level II proof

COIN Level II proof is not a prerequisite for NDX production activation.

The two lanes are independent:

```text
NDX read-only quote
  -> existing independent benchmark/display seam

COIN NASDAQ_BOOK Level II
  -> observer-only lane
  -> separate regular-market-hours proof
```

A missing, failed, incomplete, or not-yet-run COIN Level II market-hours proof must not block, disable, delay, or revoke the NDX display activation.

Conversely, successful NDX activation grants no proof, promotion, eligibility, authority, or mathematical use to COIN Level II.

## 4. Level II remains observer-only

COIN Level II remains observer-only and must still pass its own separate regular-market-hours proof.

Until a later explicit freeze says otherwise, Level II may not enter:

- Q5 or any other quant family;
- V2, V3, or V4;
- eligibility, aggregation, weighting, forecasts, or outcomes;
- durable evidence or Truth credit;
- simulator entry or resolution;
- broker, account, position, transaction, order, cancellation, replacement, execution, or trading authority.

Q5 remains unchanged.

## 5. Permanent no-change boundary

This activation changes no:

- V9 mathematics;
- Q1-Q12 equation or family version;
- V2, V3, or V4 rule;
- evidence row, outcome, lineage, proof rule, or Truth-credit calculation;
- broker or account access;
- order or execution path;
- trading authority;
- database schema or migration;
- historical replay behavior; or
- simulator authority.

It also creates no second NDX consumer and no second live-decision path.

## 6. Activation and rollback

Activation is complete only when:

1. the controlling implementation PR is merged from a clean latest head;
2. repository CI, CircleCI, and SonarQube pass;
3. the merged commit is deployed to `atom-v9-thin`;
4. the static Coin service-authentication mappings are present on `atom-v9-thin`;
5. `ATOM_SCHWAB_NDX_ENABLED=true` is set on that service; and
6. the existing display seam shows either a fresh provider-timestamped NDX value or honest unavailability.

Rollback is exact and independent of Level II:

```text
ATOM_SCHWAB_NDX_ENABLED=false
```

Rollback returns NDX selection to the prior source behavior and changes no evidence or V9 state. The static service-authentication prerequisites do not enable polling while this flag is false.

## 7. Scope boundary

This document authorizes only NDX production activation through the existing independent benchmark/display seam.

It does not authorize any COIN Level II promotion, new UI, V9 change, evidence change, Truth-credit change, broker/account/order path, or trading authority.
