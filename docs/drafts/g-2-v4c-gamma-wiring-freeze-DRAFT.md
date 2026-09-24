# G-2 — V4C Gamma Challenger production wiring (DRAFT freeze, conditional on G-1 PASS)

**Draft status:** prepared by Claude at Owner request ("add gamma") under Amendment 1B delegated drafting; zero authority until the Owner adopts it as author of record (1B §2.1) and merges it at its final path with the `AGENTS.md` pointer entry. It cannot be adopted before the G-1 confirmatory receipt exists: G-1 §16 and D9 make G-2 conditional on a PASS, and governance §14 forbids skipping falsification.
**Owner objective (recorded):** 2026-09-24, "add gamma as 12 now" — activate the coded V4C Gamma Challenger in production. This draft is the lawful form of that objective.
**Amends, explicitly:** V4C production mathematics frozen by `FREEZE.md` permanent law 1 (V1–V4 unchanged) and by `quant/v9_v4c_predictive.py` (`V4CState.__post_init__`: "V4C production gamma is frozen inactive"), for PASS horizons only. G-1 §17 ("No production Gamma activation") is superseded for those horizons at G-2's merge. Everything else is unchanged.

## 0. What gamma does and does not do

The Gamma Challenger rescales V4C's predictive variance (`eta`, `m2`, challenger kappa-squared) so that the predictive scale `kappa · sqrt(variance)` and everything built on it — range bounds, coverage, probability bands — is better calibrated to the Q3 magnitude diagnostic. It changes no forecast sign, no `final_bps`, no direction, no family, no V3 synthesis, and no directional accuracy figure. If the Owner expects gamma to move the direction card, it will not; if the Owner wants better-calibrated ranges and probabilities, this is the mechanism.

Activation creates a new V4C evidence lineage. V-1B scores V9's calibrated dispersion; its sealed look must be taken on one lineage. G-2 activation therefore waits for the V-1B receipt or records, in the V-1B receipt, that the lineage changed on the activation date, whichever the Owner chooses at adoption.

## 1. Precondition (frozen)

G-2 applies to horizon `h` only if the G-1 confirmatory receipt for `h` reads `PASS_h` (0.999 bootstrap interval of `Delta_h` entirely above zero, Q3 quartile gate PASS, coverage condition met, fit CONVERGED). Horizons that are FAIL, INSUFFICIENT, or INVALID stay exactly as today: `gamma = 0`, `phi = 1`, `gamma_status = INACTIVE`. If no horizon passes, G-2 is void and nothing is implemented.

## 2. Decision

| Frozen field | Exact value |
|---|---|
| Gate | `ATOM_V4C_GAMMA_ENABLED`; active only when exactly `1` on `atom-v9-thin` (and on `ATOM-matrix V4`, which builds V4C state); default off is byte-identical current behavior |
| Parameters | for each PASS horizon, `eta_h`, `m2_h`, and challenger `kappa2_h` taken verbatim from that horizon's G-1 confirmatory receipt; frozen constants in code, never refit online; `gamma_h = eta_h / (m2_h · (1 − eta_h))` as coded; `phi_h = 1` |
| State | `V4CState` carries per-horizon `gamma`, `phi`, `gamma_status` (`ACTIVE` for PASS horizons, `INACTIVE` otherwise) under a new state version `ATOM_TRUE_V9_V4C_GAMMA_ACTIVE_1`; the inactive assertion becomes: inactive unless the gate is on and the horizon is in the frozen PASS set |
| Mathematics | for ACTIVE horizons the predictive scale uses the challenger variance exactly as `quant/v9_v4c_predictive.py` already codes it for the study; INACTIVE horizons use today's formula unchanged |
| Lineage | forecast records written while ACTIVE carry `gamma_status = ACTIVE` in `FinalNumbers`; no historical row is rewritten; proof, eligibility, cadence, and identities are unchanged |
| Acceptance | first two complete regular sessions with the gate on, each separately, per ACTIVE horizon: 0.90 range coverage no farther from 0.90 than the last two INACTIVE sessions; no increase in `range_status`/`probability_status` UNAVAILABLE share; V4C state rows show the new version with the frozen parameters; read-only receipt |
| Rollback | gate to `0`; V4C state rebuilds under the previous version on the next build; nothing else to undo |

## 3. Implementation surface (after adoption, one PR)

`quant/v9_v4c_predictive.py` (state fields, gate-aware assertion, ACTIVE-horizon scale path using the existing challenger code), `quant/v9_v4d_integration.py` (metrics `v4.<h>.gamma.ACTIVE`), `quant/v4_state_worker.py` only if the state builder must pass the gate, `tests/test_v9_v4c_predictive.py` and `tests/test_g2_gamma_wiring.py` (new). No migration, schema, role, credential, service, SIM, family, V3, `final_bps`, direction, or web change. Any other file is `BLOCKED`.

## 4. Required tests

Gate off is byte-identical (existing suite unchanged); INACTIVE horizons unchanged with the gate on; ACTIVE horizon scale equals the study's challenger formula for the frozen parameters; frozen parameters equal the receipt values (test reads the receipt file); state version and hash change only for ACTIVE configurations; `final_bps` and direction identical with the gate on and off across a replayed session fixture; no online refit path exists; full existing suite green.

## 5. Order of work

1. G-1 confirmatory receipt (earliest 2026-10-02, when the twentieth post-adoption session closes; 13 of 20 accrued at 2026-09-23). Run once, by Codex (G-1 D8) or by whoever holds `ATOM_E1_SCORECARD_READONLY_DATABASE_URL`; receipt PR; Owner merge.
2. If any `PASS_h`: Owner adopts this text with the PASS set and parameters filled in (final path `docs/g-2-v4c-gamma-wiring-freeze.md`; `AGENTS.md` pointer entry), under the freeze merge gate.
3. Implementation PR, independent final-head review, green required checks, Owner merge.
4. Deploy `atom-v9-thin` and `ATOM-matrix V4` at the merged SHA outside regular hours; set the gate; acceptance receipt after two sessions.

## 6. Not authorized

Activation for any horizon without `PASS_h`; any refit of gamma parameters in production; any change to direction, `final_bps`, families, V3, SIM, E-, V-, L- programs, broker or trading paths; any claim that gamma is directional-edge or profitability evidence (G-1 §17).
