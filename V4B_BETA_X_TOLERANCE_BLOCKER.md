# V4B frozen-contract blocker

## Blocker

`BETA_X_TOLERANCE_VALUE_MISSING`

The V4B implementation authorization freezes the Beta inverse probability
tolerance, iteration limits, and continued-fraction tolerance, but it does not
state the exact replacement x-tolerance approved in the referenced final Max
blocker-audit amendment. That amendment and value are not present on current
main.

The authorization expressly requires implementation to stop when the exact
approved replacement x-tolerance is unavailable and forbids guessing or using
an alternate tolerance. Consequently, no V4B production code, migration, Beta
implementation, or tests have been added.

## Required resolution

Provide the exact binary64 x-tolerance value approved by Max. Once supplied,
V4B can freeze that value as the bisection x-width stopping criterion alongside:

- probability tolerance: `1e-12`;
- maximum bisection iterations: `128`;
- continued-fraction tolerance: `1e-14`; and
- maximum continued-fraction iterations: `256`.

No other architecture decision is requested by this blocker report.
