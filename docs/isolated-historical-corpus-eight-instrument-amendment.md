# ATOM - Standalone Isolated Eight-Instrument Historical Corpus Authorization

**Decision ID:** `ATOM-HIST8-CORPUS-AMENDMENT-1`  
**Author:** ChatGPT Pro  
**Proposed repository path:** `docs/isolated-historical-corpus-eight-instrument-amendment.md`  
**Reviewed repository baseline:** `166a0e5b945e4f19ae41f392e75e3560d72acc1b`  
**Status:** FROZEN ON OWNER-APPROVED MERGE; no authority before that merge.  
**Implementation owner after the documentation gate:** Codex.

## 1. Standalone authority and effectivity

This document is a standalone historical-corpus authorization. It does not depend on, incorporate, require, or await any parent historical-data authorization. It becomes independently effective only upon its own Owner-approved documentation-only merge. Before that merge it grants no implementation or operational authority.

Upon that merge, authorize only the isolated schema, historical ingestion/backfill, deterministic derivation, validation, focused tests, and receipts needed to supply reproducible offline research inputs. This opens no model-research execution or promotion phase and changes no existing frozen mathematics, V1B/V-1B, SIM, V9, production behavior, broker, execution, risk, or capital authority. The active production/SIM phase pointer is unchanged.

## 2. Frozen population, sources, and bounds

The corpus identity is `HIST8_20240901_20260901_V1`.

| Instrument | Only authorized source/feed | Canonical source product |
|---|---|---|
| COIN, QQQ, SPY, NVDA, XLE, GLD | Alpaca / explicit `sip` | The exact named equity/ETF's `1Min` trade OHLCV bars |
| BTC-USD | Coinbase Exchange / BTC-USD spot exchange candles | `BTC-USD`, `granularity=60`; not another venue or an aggregated crypto feed |
| NASDAQ | Massive / existing authorized `I:COMP` index feed | `I:COMP`, multiplier 1, timespan minute; index OHLC, not trade bars |

NASDAQ means only the authorized `I:COMP` instrument. No NDX, QQQ, futures, proxy, symbol substitution, or fallback feed is permitted. Bind the exact provider instrument and feed identity in the import manifest. Unavailable access is reported, never worked around by changing source. No subscription or vendor-account changes are authorized.

Freeze the same half-open, two-calendar-year interval for every instrument:

```text
start_inclusive = 2024-09-01T00:00:00Z
end_exclusive   = 2026-09-01T00:00:00Z
```

Only bars wholly inside that interval qualify. These bounds do not roll forward with execution time. Provider-inclusive endpoints, overlapping pages, and extra returned bars must be normalized to these bounds and counted; finish every required page/range before claiming acquisition complete.

For all six equities, explicitly use `adjustment=raw`, `asof=2026-09-01`, and USD. Preserve source precision without floating-point conversion or local price adjustment. Record volume units as shares for equities and BTC for BTC-USD. NASDAQ values are index points; volume is `NULL` / `NOT_APPLICABLE`, never manufactured zero. These conventions apply only to this corpus.

## 3. Canonical minutes, sessions, and completeness

Maintain exactly one canonical 1m series per instrument. Every timestamp is a timezone-aware UTC interval-start timestamp; a minute denotes `[t, t+60 seconds)`. Reject misalignment rather than silently rounding timestamps. Preserve provider timestamps and the normalization rule in lineage. A bar is available for a historical decision no earlier than its interval end; retrieval time is separate and is not proof of historical availability.

Equities: use each instrument's applicable U.S. cash-exchange calendar, with session dates in `America/New_York`. Include only scheduled RTH minutes from 09:30 to the actual session close. Honor holidays, exceptional closures, early closes, and daylight-saving changes. Closed-calendar minutes are not missing data. Do not include extended hours or a bar beginning at the session close.

NASDAQ: use the Nasdaq cash-session calendar and the same RTH interval rules, while retaining index-value semantics. A scheduled minute without an index bar is missing, not a repeated index value.

BTC-USD: freeze sessions as UTC civil days `[00:00:00Z, next 00:00:00Z)`, every day including weekends and holidays, with 1,440 expected minutes. Exchange outages or absent candles are gaps, not equity-market closures. Never clip BTC to equity RTH.

Bind the complete dated session schedule, calendar/timezone versions, and schedule hash before ingestion. The reviewed schedule - not a mutable library default - controls every rerun.

For each instrument, an eligible research session requires exactly one valid canonical bar at every expected minute. Preserve otherwise-valid minutes from incomplete sessions as incomplete canonical evidence, but exclude the entire session from eligible 1m inputs and all derived research bars. Record the missing minutes and session exclusion separately. No forward/backward filling, interpolation, synthetic candles, zero-volume padding, or shortened-window substitution is allowed.

Equal treatment means common bounds and rules, not forced equal row counts. Differences in calendars, trading days, and documented gaps remain visible.

## 4. Deterministic derivation only

Freeze derivation version `HIST8_DERIVE_1`. Derive 5m, 15m, 30m, and 1H directly from canonical 1m bars, with durations 300, 900, 1,800, and 3,600 seconds. Do not independently download them or derive one longer timeframe from another.

For duration `m` minutes, anchor nonoverlapping windows at the session open: `start = session_open + k*m minutes`, for integers `k >= 0`. Admit only windows ending at or before session close and containing exactly the `m` expected, unique, contiguous, valid canonical minutes from one eligible session.

```text
open   = first canonical minute's open
high   = maximum canonical high
low    = minimum canonical low
close  = last canonical minute's close
volume = exact sum of canonical volume, where applicable
```

Use exact decimal values and deterministic arithmetic without additional rounding. NASDAQ derived volume remains null. Bind the ordered canonical row identifiers and hashes used by every derived bar. No cross-session window is allowed.

Count incomplete windows and residual session tails without emitting bars for them. Under this convention, a 390-minute RTH session supplies six full 1H bars and one excluded 30-minute tail; a 210-minute early-close session supplies three and one excluded tail. BTC supplies 24 1H bars on a complete UTC day. Retain tail minutes in canonical 1m and any independently eligible shorter derivations.

## 5. Isolated, append-only persistence and reuse

Use only one Owner-designated isolated research Supabase project, distinct from production and SIM. This authorization permits use of that isolated project for the HIST8 corpus only; it does not authorize creating an additional project, service, or billing commitment. Bind its exact project/database identity in the reviewed implementation manifest; absent or mismatched identity blocks all database writes.

The new database surface is limited to private schema `atom_research_history`, append-only tables `bars` and `manifests`, and their necessary constraints, indexes, mutation-rejection protections, and project-local least-privilege grants. Manifests may bind immutable external source artifacts; references must remain retrievable and hash-verifiable.

Each bar must store or immutably bind corpus/instrument identity, timeframe, UTC start, session date/calendar, OHLCV and units/null semantics, source/feed/product, originating retrieval/import identity, derivation version, source-row lineage, and content hash. Canonical lineage identifies the preserved provider artifact and exact source record; derived lineage identifies its ordered canonical inputs.

Enforce non-null database uniqueness on `(corpus_id, instrument, timeframe, bar_start_utc)`. A different import ID, feed, derivation version, or hash cannot bypass that identity. An exact semantic replay is a no-op after comparison; a same-key difference is a recorded conflict that fails closed. Fresh attempt metadata is not a content difference and never replaces originating provenance; record it separately in an append-only manifest. `ON CONFLICT DO UPDATE` and equivalent mutable upserts are prohibited. Reject `UPDATE`, `DELETE`, and `TRUNCATE` at the database boundary; the importer receives only required `SELECT`/`INSERT` access, not ownership or mutation authority.

Existing rows/artifacts may be copied or bound read-only only after proving exact source/feed, interval, bounds, sessions, adjustment mode, precision, completeness, and lineage compliance. Otherwise backfill missing compliant canonical minutes into this corpus. Never alter the original store or accepted rows. Conflicting corrections require a separate decision; they cannot be smuggled in as another canonical version.

Use bounded offline import commands only: zero live writers, schedules, streaming subscriptions, production consumers, or trading/execution integrations. Do not distribute corpus credentials to production/SIM, expose public APIs, add cross-database consumers, change deployment configuration, or resume a suspended worker. No production or SIM migration is authorized.

## 6. Validation and immutable snapshots

Validate every accepted row for finite positive OHLC; `low <= min(open,close) <= max(open,close) <= high`; finite nonnegative volume where applicable; exact null/unit rules; alignment; uniqueness; interval/date bounds; session/calendar compliance; and exact source/feed/product identity. Validate every derivation's complete ordered input set, aggregation values, lineage, and hash independently.

Freeze the canonical serialization and hashing implementation before import. Use SHA-256 content and provenance manifests with deterministic field/numeric encodings and explicit sorted row order. Bind all source artifacts, calendar schedules, masks, and code versions needed to reproduce them; hashes without retained inputs are insufficient.

Seal each completed import in an immutable snapshot manifest defining exact row membership and eligibility masks. Later authorized missing-row backfills may append rows and a new snapshot, never change an earlier snapshot. Every comparison must use the same explicitly identified snapshot. Calendar gaps and invalid/rejected input remain counted; validation success must not be described as gap-free two-year coverage when it is not.

## 7. Common partitions and future reporting

Freeze these UTC, half-open partitions for all instruments and timeframes:

| Partition | Inclusive start | Exclusive end |
|---|---|---|
| Training | `2024-09-01T00:00:00Z` | `2026-03-01T00:00:00Z` |
| Validation | `2026-03-01T00:00:00Z` | `2026-06-01T00:00:00Z` |
| Test | `2026-06-01T00:00:00Z` | `2026-09-01T00:00:00Z` |

No random reshuffle, instrument-specific date optimization, or performance-dependent exclusions. Future separately authorized research must keep features causal, purge training/validation examples whose target intervals enter a later partition, fit transformations without later-partition data, and use test data only under its frozen evaluation protocol. Disclose prior exposure: this partitioning cannot turn already-inspected history into an untouched confirmatory holdout.

Report every instrument separately - including coverage, exclusions, sample size, and its research results or unavailable status - before any pooled eight-instrument statistic. Pooling requires a separately preregistered method/weighting; stronger instruments cannot conceal weak or unavailable instruments. No such statistic or study is authorized by this amendment.

The four staged SPY, NVDA, XLE, and GLD 1H SIP files are reconciliation evidence only. Compare only matching source, adjustment, interval, and session definitions; otherwise mark them `NOT_COMPARABLE`. Retain discrepancies. Never use these files to replace canonical minutes, fill gaps, change derivation alignment, or supply independently sourced research 1H bars.

## 8. Required post-import receipt

Produce one append-only receipt identifying:

- Exact controlling `ATOM-HIST8-CORPUS-AMENDMENT-1` identity and Owner-approved documentation merge commit; actual implementation/execution commit; authorization document hashes; project, database, schema, table, and snapshot identities.
- Source/feed/product by instrument; source request/adjustment settings; canonical and derived timeframe definitions; exact bounds, session conventions, calendar hashes, and partition boundaries.
- All 40 instrument/timeframe combinations, including zero-count cells: stored and research-eligible row counts, minimum/maximum timestamps (null for empty cells), expected/observed/missing minutes, incomplete sessions, rejected inputs, and excluded windows/tails by non-overlapping reason.
- Observed input duplicates, accepted duplicate count, conflicts, every validation result, and truthful coverage status; source, row-content, provenance, snapshot, and eligibility-manifest hashes.
- Exact derivation-code Git blob and SHA-256 hashes, plus the same bindings for ingestion, normalization, calendar, validation, and serialization code and any reused dependencies affecting output.
- A second full replay of the same retained source inputs and derivation: zero new bar rows, zero accepted duplicates, zero changed accepted rows, identical content/membership hashes, and unchanged originating provenance. A new append-only attempt receipt is permitted. Separately demonstrate resumable missing-row backfill without overwriting existing rows.
- Evidence of zero production consumers/live writers/execution paths: reviewed code/deployment dependency surface, project and privilege isolation, absence of production/SIM credential distribution and cross-database integrations, and rejection tests for mutation and wrong-project access. A self-declared boolean or empty query log alone is insufficient.

A missing proof, unresolved same-key conflict, wrong source/project, mutable accepted row, or unverifiable lineage cannot receive a successful integrity receipt. An unavailable instrument remains explicit; partial availability cannot be called a complete eight-instrument corpus.

## 9. Documentation gate and exact Codex handoff

The documentation PR may add only this authorization. It must contain no implementation, migration, data import, active-phase-pointer change, or runtime/configuration change. Require independent final-head review, all mandatory checks green, zero unresolved material findings, and Owner approval/merge. That Owner-approved documentation-only merge is the sole effectivity event for `ATOM-HIST8-CORPUS-AMENDMENT-1`; no parent decision, parent approval, or parent merge is required.

Only after that gate, hand Codex this implementation job: create the isolated schema/tables/protections; implement the three authorized historical source adapters and validated reuse/backfill; derive the four timeframes from canonical minutes; implement frozen validation/snapshot/partition rules; add focused tests; and produce the receipt above. Nothing else.

The implementation file allowlist is only `research/hist8/schema.sql` (isolated-only migration, never registered with production migrations), `research/hist8/corpus.py` (offline command and corpus logic), `research/hist8/calendar_manifest.json` (dated schedules and source identities), `tests/test_hist8_corpus.py`, and append-only artifacts under `docs/receipts/hist8/`. Do not overwrite an occupied path without verifying it belongs to this job. Codex must bind the verified isolated destination and exact changed/artifact paths in one implementation PR. Existing production, V1B, SIM, V9, mathematics, evidence, dependencies, workflows, services, credentials, and configuration remain unchanged except the expressly authorized isolated importer access. No surrounding refactor or additional platform is authorized. Required access or scope beyond this contract returns to the Owner/ChatGPT Pro, not an implementation workaround.

The implementation PR requires independent final-head review, mandatory green checks, and lawful Owner-authorized merge before isolated migration/import execution. Its receipt then receives ChatGPT Pro's final boundary/integrity audit. A corpus acceptance decision confers data-integrity acceptance only, never predictive-value or trading approval.

**END - ATOM-HIST8-CORPUS-AMENDMENT-1**
