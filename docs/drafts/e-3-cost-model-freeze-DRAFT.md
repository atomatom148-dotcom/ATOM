# E-3 — COIN Cost Model (DRAFT freeze)

**Draft status:** prepared by Claude at Owner request under 1B delegated drafting; zero authority until adopted and Owner-merged.  
**Phase:** E-3 (listed in `PHASES.md` as "not authorized"; this draft is the freeze that would authorize it)  
**Change type:** documentation only; the implementation that follows is one read-only reader and one receipt

## 1. Purpose

Fix `cost_bps(h)` per horizon from evidence already stored, so that E-2 and every later promotion decision are net of friction. E-1 froze `cost_bps = 0.0` deliberately; E-3 is the phase that replaces the zero with a measurement.

## 2. Source (read-only, already durable)

The isolated simulator project's `public.atom_v9_sim_entries` rows with `entry_status = 'ENTERED'` embed the exact executable quote (`bid`, `ask`, `bid_size`, `ask_size`, `provider_event_ns`, `accepted_at`) that SIM-4 selected inside its two-second window. These are real SIP quotes at real decision instants, on the same clock the paper simulator trades on. No new data source, no production table, no Level II, no Alpaca call.

Once SIM-5 is live, its `RESOLVED` rows add the exit quote at the endpoint. E-3 may use both; it does not wait for SIM-5.

## 3. Frozen measurement

For each entry quote:

```text
mid_bps_spread = 10000 * (ask - bid) / ((ask + bid) / 2)
```

Per horizon `h`, over the evaluation session set (explicit UTC dates, regular hours only, partial sessions excluded, same rules as E-1):

```text
cost_bps(h)        = median(mid_bps_spread) over ENTERED entries at horizon h        (round trip: pay half at entry, half at exit)
cost_bps_p75(h)    = 75th percentile
cost_bps_p95(h)    = 95th percentile
slippage_bps       = 0.0   (one share; frozen; revisit only under a later freeze)
n_quotes(h), n_sessions(h)
```

When SIM-5 `RESOLVED` rows exist, additionally report the realized round trip `realized_cost_bps(h) = median(entry_half_spread + exit_half_spread)` and the difference from `cost_bps(h)`.

Reasoning for the median: E-2 needs one number per horizon fixed in advance; the median is robust to the wide quotes at the open. The percentiles are reported so nobody mistakes the median for the worst case.

## 4. Receipt

One JSON receipt: session dates, per-horizon table above, by-session-hour breakdown of `mid_bps_spread` (nine 45-minute buckets), the snapshot marker, reader code version, `read_only = true`, forecast/outcome/entry/resolution writes all `0`, and a SHA-256 over the canonical JSON. The receipt states, per horizon, the ratio `cost_bps(h) / median(|expected_return_bps|)` from the V9 layer over the same sessions — the single number that says whether the horizon is arithmetically viable. No label is attached; that judgment belongs to E-2 and the Owner.

## 5. Boundaries

Read-only, single process, one dedicated read-only credential on the simulator project (a new `NOLOGIN`-style pattern is not needed: reuse of `atom_v9_sim_entry_runtime` is **not** authorized; E-3 gets its own `atom_e3_cost_reader` role with `SELECT` on `atom_v9_sim_entries` and, when present, `atom_v9_sim_resolutions`, created by one migration on the simulator project under the SIM-3B §4.1 procedure). No production project access. No E-1 role reuse. No write anywhere.

Implementation surface: `quant/cost_model.py` (new), `tests/test_cost_model.py` (new), one simulator-project migration, one benchmark-worker start command set by the Owner.

## 6. What E-3 does not authorize

No change to E-1's frozen `cost_bps = 0.0` for the existing receipt; no promotion, retirement, or reweighting; no SIM behavior change; no trading. E-2 consumes `cost_bps(h)` from the E-3 receipt only after that receipt is produced and reviewed.
