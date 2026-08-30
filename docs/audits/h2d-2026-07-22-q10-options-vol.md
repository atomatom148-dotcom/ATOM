# H2-D 2026-07-22 Q10 lineage audit

## Verdict

**Pass — certified unavailable placeholders, not a lineage or scoring defect.**
This was a read-only audit. No production command was run and no forecast or
outcome was written, replaced, or deleted.

The certified `h2d-2026-07-22` receipt contains 752,040 forecast slots
(10,445 frames × 12 families × 6 horizons), 62,670 outcomes, and 72 score
records. The six `q10_options_vol` score records are the only records with
`eligible_count = 0`, `resolved_count = 0`, and null accuracy/error metrics.

## Lineage trace

| Field | Audited value |
| --- | --- |
| Stored identity | `(h2d-2026-07-22, cutoff_at, q10_options_vol, horizon)`; one immutable primary-key slot for every replay cutoff and each of `30S`, `1M`, `5M`, `15M`, `30M`, `1H` |
| Formula / numerical type | `coin-options-skew-delta-v2` / `DIRECTIONAL_BPS` |
| Forecast availability | `UNAVAILABLE`; `expected_return_bps = NULL` |
| Forecast exclusion reason | `REPLAY_Q10_DATA_UNAVAILABLE` |
| Historical input | Alpaca historical SIP NBBO for COIN/QQQ only; no historical option surface, contract observations, IV, or Greeks |
| Data schema | `alpaca-historical-sip-nbbo-v1` |
| Source schema | `alpaca-sip-quote-size-shares-v1` (the schema selected for the July 2026 session) |
| Outcome eligibility | Outcomes are horizon targets shared by all families and remain immutable; the scorer does not admit an outcome when its forecast slot is unavailable |

H1 deliberately returns `None` for Q10 because the replay input contract has no
options surface. It persists all six slots as explicit unavailable placeholders
with the Q10-specific reason. H2-C first requires `forecast.availability_status
= 'AVAILABLE'`; therefore none of those placeholders increments eligible or
resolved counts. With a zero resolved denominator, directional accuracy, RMSE,
MAE, and mean error are correctly null. Outcome coverage cannot turn an
unavailable forecast into eligible evidence.

The stored slot identity, Q10 formula version, replay data/source schema, and
reason code all agree with the frozen producer and scorer contracts. Admitting
these rows would manufacture a forecast from absent inputs and weaken the
eligibility rule, so no Q10 repair is authorized.
