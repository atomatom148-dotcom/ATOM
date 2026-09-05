# Scope note — V-1A readiness depends on `scale_status` alone

Issued 2026-09-05 by Claude (read-only reviewer), read against the repository at
the current main commit, not against chat history.

- Controlling document: `docs/v-1a-volatility-first-freeze.md`
- Main commit: `ac85cc9e99ccc499789f3ef79b186768d99fb0d6` (merge of PR #319, 2026-09-04T18:38:18-04:00)
- File: 2,529 lines, SHA-256 `9e53d4b9f8eab8c76e317495b49cfe205056e35629493bf0c1f46e03e94a07d8`
- No amendment to V-1A has been merged since #319. No Amendment 2A PR is open.

## 1. The finding

§7.3 MATURE-only is the entire V4C dependency of this freeze:

> `kappa(f)` is usable only when reconstructed `ScaleResult.status == "MATURE"`
> and `kappa` is finite and strictly positive.

Occurrence counts across all 2,529 lines:

| Token | occurrences |
|---|---|
| `ScaleResult` | 1 (§7.3) |
| `range_status` | **0** |
| `threshold_status` | **0** |
| `calibrate_range` | **0** |
| `build_thresholds` | **0** |
| `RangeResult` / `ThresholdResult` | **0** |

`MATURE` appears exactly three times: the §7.3 heading, the §7.3 rule above, and
"MATURE-only kappa acceptance" in the §12.2 required-tests list.

**V-1A readiness is gated on `scale_status` and nothing else.** `range_status`
and `threshold_status` are not referenced anywhere in the freeze.

## 2. Consequences for Amendment 2A

**The `range_status` question is out of scope.** Whatever its true disposition —
the structural reading in Correction 2, or the calibration-quality reading in the
Erratum — it does not gate V-1A. Amendment 2A should say nothing about it. If the
current draft states the fixed-250 range-status defect as an established finding,
that is wrong twice over: the claim is downgraded (Erratum §1), and the subject
is outside this freeze. Under the owner's standing rule to make only the minimum
authorized change and never combine phases, it belongs to a separate V4C track.

**Keeping `threshold_status` outside frozen V-1A readiness is correct**, and for
a stronger reason than session-masking: the freeze never references it. The
session-mask reasoning in Correction 3 remains sound but is not load-bearing
here.

**The kappa dependency splits the two families cleanly.** §7 applies "for each
selected V9 target forecast `f`", and the §6.4 accounting states
`n_kappa_unavailable` is "V9 only: ... FAMILY value is zero."

- **FAMILY-VOL cells** have no V4C dependency at all. They are blocked solely by
  the §11 minima — regression windows, regression sessions, and the same for each
  gate population.
- **V9-VOL cells** are blocked by `scale_status` and then by the §11 minima.

## 3. Where V-1A actually stands, measured

From the persisted V4C state (`ATOM_TRUE_V9_V4C_PROBABILITY_1`,
`state_as_of` 2026-09-05T00:06:08Z), applying §7.3:

| Horizon | calibration pool | `scale_status` | kappa usable under §7.3 |
|---|---|---|---|
| 30S | 4,773 | MATURE | **yes** |
| 1M | 2,866 | MATURE | **yes** |
| 5M | 598 | PROVISIONAL | no |
| 15M | 102 | PROVISIONAL | no |
| 30M | 0 | UNAVAILABLE | no |
| 1H | 0 | UNAVAILABLE | no |

This explains the prior audit result exactly. The V9 1H funnel ended with 39
pre-kappa windows and zero surviving kappa windows because `scale_status` is
UNAVAILABLE at 1H, so every window went to `n_kappa_unavailable` under §7.3. Not
a data-volume problem at that stage — a status gate.

Blocking condition per horizon, from Correction 2:

- 5M — pool 598 clears the 250 raw floor, so the failing condition is
  `neff >= 200`. No date can be given; N_eff on this series does not track n.
- 15M — pool 102, below the 250 raw floor. Raw count binds first.
- 30M (196 selected) and 1H (95 selected) — pool is empty; both need 500 selected
  pairs before the pool is even non-empty. 1H is ~27 trading days from that at the
  measured +15/day, which yields PROVISIONAL, not MATURE.

## 4. What this does to the tiered boundary

It strengthens it and narrows it. Only 30S and 1M have usable kappa today, and
the V9 cells at 5M and longer are blocked on a condition (`neff >= 200`) that
accumulation may not resolve on any schedule. The FAMILY cells are on an entirely
separate and simpler clock.

An all-cells READY rule chains the first receipt to a condition with no
predictable arrival date. A tiered rule can bank 30S and 1M now, and the FAMILY
cells on their own minima, without waiting on it.

## 5. Standing caveat

I have not read Amendment 2A. Nothing here approves it. This note establishes
what the merged freeze actually depends on so the amendment can be checked
against it.

## 6. Provenance

Repository read at `origin/main` = `ac85cc9`. Counts from `grep -c` over
`docs/v-1a-volatility-first-freeze.md` at that commit. Status values from
read-only SQL against production project `afyiydxbjgzaiswnbcyj` on 2026-09-05,
`atom_v9_v4_states` only. No preregistered statistic computed. No state changed.
