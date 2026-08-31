# ATOM TRUE V9 — SIM-3A P1 Review Amendment

**Status:** LAW after merge  
**Amends:** PR #223 and `docs/sim-3a-exact-sim4-entry-freeze.md`  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only  
**Simulator:** `ATOM_TRUE_V9_SIM_1`  
**Mode:** `PAPER_ONLY`

This document resolves the four unresolved P1 review threads on PR #223. It is a controlling amendment to the exact SIM-4 entry freeze. Where this amendment conflicts with the original SIM-3A document, this amendment controls.

This amendment does not implement SIM-4 and does not authorize or implement SIM-5, SIM-6, broker access, order submission, options, execution P&L, compact simulator state, or any V9 mathematical change.

## 1. Exact Alpaca SIP source identity

The original label `ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1` is valid only when the live COIN quote was obtained from an Alpaca latest-quotes request that explicitly selected the SIP feed.

The exact initial live request is frozen as:

```text
https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=COIN%2CQQQ&feed=sip
```

The query must contain the explicit parameter:

```text
feed=sip
```

Omitting `feed`, relying on an account default, using `iex`, using a different feed, or accepting a quote whose feed cannot be proven does not establish SIP identity.

A SIM-4 executable quote may use:

```text
source_spec = ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1
```

only when all of the following hold:

1. The quote came from the exact production request path above.
2. The request explicitly selected `feed=sip`.
3. The response item was the `COIN` item from that successful request.
4. The existing live validation accepted its bid, ask, sizes, and provider timestamp.
5. The exact provider nanosecond identity was preserved through the accepted-quote handoff.
6. The immutable market/V9 publication committed before the SIM-4 callback.

A quote from any other source path must not be relabeled as SIP. When exact SIP provenance is absent or ambiguous, the production quote continues normally but no SIM-4 executable-quote event is submitted.

There is no feed fallback for SIM-4. The simulator must fail closed rather than use an unproven source identity.

The existing `SIM4_QUOTE_SOURCE_SPEC` constant remains unchanged because this amendment makes the live request match that identity.

## 2. Exact advisory-lock key derivation

The same-horizon collision transaction must use one exact cross-process and cross-version PostgreSQL advisory-lock key derivation.

Freeze:

```text
SIM4_ADVISORY_LOCK_NAMESPACE = ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1
```

For one canonical horizon, construct exactly these bytes:

```python
lock_payload = (
    b"ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1\x00COIN\x00"
    + horizon.encode("ascii")
)
```

The horizon must be exactly one of:

```text
30S
1M
5M
15M
30M
1H
```

Calculate:

```python
digest = hashlib.sha256(lock_payload).digest()
unsigned_key = int.from_bytes(digest[:8], byteorder="big", signed=False)
lock_key = unsigned_key if unsigned_key < 2**63 else unsigned_key - 2**64
```

Acquire exactly the one-argument transaction-scoped PostgreSQL lock:

```sql
SELECT pg_advisory_xact_lock(%s::bigint)
```

with `lock_key` as the only parameter.

The exact golden lock keys are:

| Horizon | First eight SHA-256 bytes | Signed bigint lock key |
| --- | --- | ---: |
| `30S` | `1452ca2a23cfcadf` | `1464455111187090143` |
| `1M` | `fc6b54126ca0e440` | `-258020115535043520` |
| `5M` | `bb7a3f095c07c11a` | `-4937564732027059942` |
| `15M` | `ed2b7efcb1db9ee6` | `-1356851238941253914` |
| `30M` | `d8cda95882e8542d` | `-2824415193672952787` |
| `1H` | `562d0756494d6197` | `6209627528392171927` |

The transaction must acquire this lock before it reads:

- any existing terminal entry for the intent;
- durable open occupancy for the horizon; or
- any row used to choose `ENTERED` versus `SKIPPED_POSITION_OPEN`.

The lock remains held until commit or rollback.

Forbidden lock derivations include:

- Python `hash()`;
- PostgreSQL `hashtext` or `hashtextextended`;
- process-random values;
- database collation-dependent text hashing;
- implementation-selected namespaces;
- a different byte order;
- a different digest slice; and
- separate lock domains for rolling versions.

Every concurrently deployed SIM-4 version must acquire the same key for the same horizon.

## 3. Exact terminal-decision precedence

SIM-4 freezes one precedence order for normal processing and restart recovery. A restart must not change a provable position collision into a restart gap.

For one intent, the worker and store apply the following order:

1. **Existing terminal record.** Under the exact horizon lock, check whether the intent already has a terminal entry record. Validate and return the existing immutable result idempotently. Do not create another record.
2. **Non-actionable intent.** `NO_TRADE` maps to `SKIPPED_NO_TRADE`; `UNAVAILABLE` maps to `SKIPPED_UNAVAILABLE`. Open occupancy does not alter these non-actionable mappings.
3. **Durable open-position collision.** For an actionable intent, re-read durable open occupancy under the exact horizon lock. If exactly one durable open `ENTERED` record exists, emit `SKIPPED_POSITION_OPEN` and preserve that exact record's `entry_id` as `blocking_entry_id`.
4. **Restart gap.** Only when the intent is actionable, no durable open entry exists, and `publication_at < runtime_started_at`, emit `SKIPPED_RESTART_GAP`.
5. **Late-window expiry.** Only when the intent is actionable, no durable open entry exists, the publication did not precede runtime start, and the late-intent rule in Section 4 applies, emit `SKIPPED_WINDOW_EXPIRED`.
6. **Live pending selection.** Only an actionable intent surviving all prior steps may inspect the bounded quote buffer or become an in-memory pending intent.

Therefore:

```text
SKIPPED_POSITION_OPEN takes precedence over SKIPPED_RESTART_GAP.
```

During startup recovery:

1. Read `runtime_started_at` once from the injected UTC clock.
2. Recover durable horizon occupancy first.
3. Query only unmatched intents in the already-frozen bounded interval `[runtime_started_at - 2 seconds, runtime_started_at)`.
4. Process those intents in ascending `publication_at`, canonical horizon order, and `intent_id`.
5. For each actionable intent, acquire the exact advisory lock and re-read occupancy before choosing a status.
6. Emit `SKIPPED_POSITION_OPEN` when occupied; otherwise emit `SKIPPED_RESTART_GAP`.

Recovery never reconstructs or selects a pre-restart quote.

If durable state contains more than one open `ENTERED` record for one horizon, the store/runtime is invalid. SIM-4 must fail closed for that horizon and must not choose an arbitrary blocker.

## 4. Bounded late-intent handling

The SIM-4 persisted-intent adapter and worker must bound delivery and queue delay without retroactive entry selection.

### 4.1 Intent handoff timestamp

Immediately before the nonblocking SIM-4 intent enqueue, the adapter reads the injected UTC clock exactly once as:

```text
intent_handed_off_at
```

The value is runtime-only metadata. It is not part of the SIM-1 intent, entry record, entry hash, or database schema.

The value must be a finite timezone-aware UTC datetime. If it is invalid or the clock read fails, no SIM-4 intent event is admitted; SIM-1/SIM-2 persistence remains successful and unchanged.

The immutable internal event contains only:

```python
@dataclass(frozen=True, slots=True)
class SimulationEntryIntentEvent:
    intent: SimulationTradeIntent
    handed_off_at: datetime
```

### 4.2 Worker-processing timestamp

At the beginning of processing that intent event, before inspecting the quote buffer, the single SIM-4 worker reads the injected UTC clock exactly once as:

```text
intent_processed_at
```

This timestamp is also runtime-only metadata and is not persisted or hashed.

An actionable intent is late when either:

```text
intent_handed_off_at > entry_deadline_at
```

or:

```text
intent_processed_at > entry_deadline_at
```

A late actionable intent must not inspect or select any buffered quote.

After applying the precedence in Section 3:

- an occupied horizon produces `SKIPPED_POSITION_OPEN`;
- a pre-runtime publication with no open occupancy produces `SKIPPED_RESTART_GAP`; and
- every other late actionable intent produces `SKIPPED_WINDOW_EXPIRED`.

A handoff or processing time exactly equal to `entry_deadline_at` is not late. At exact equality, the worker may inspect already-buffered quotes under the original inclusive deadline rules. If no valid executable quote is currently buffered, the intent remains pending; equality alone must not finalize `SKIPPED_WINDOW_EXPIRED`.

The worker finalizes an otherwise-unfilled pending intent as `SKIPPED_WINDOW_EXPIRED` only after a subsequent injected UTC clock read is strictly greater than `entry_deadline_at`. Before finalizing, it drains every SIM-4 event already admitted to the FIFO queue whose immutable admission timestamp is less than or equal to `entry_deadline_at`, in normal FIFO order. A quote callback with `accepted_at <= entry_deadline_at` that completes `put_nowait` before that strictly-greater expiry observation is therefore accounted for before expiry. A quote callback that has not completed queue admission by that observation is not an admitted SIM-4 event and cannot be reconstructed or applied retroactively.

An intent processed before its deadline may become pending only until this exact strictly-greater expiry boundary. The worker's blocking wait must be bounded by the earliest pending deadline and, on equality, must continue until the first strictly-greater clock observation after accounting for already-admitted equality-boundary events. Expiry does not depend on a later market event.

No intent handed off or first processed strictly after its deadline may produce `ENTERED`, even if a buffered quote would otherwise satisfy the provider-time predicates.

## 5. Exact quote-buffer eviction

Late-intent finalization makes finite age-based quote eviction provable.

For each worker loop event, use one valid injected UTC clock value named:

```text
event_now
```

A buffered quote is expired and must be evicted when:

```text
event_now > quote.accepted_at + exactly 2 seconds
```

At exact equality, the quote remains retained until `event_now` becomes strictly greater.

This rule is safe because every intent that could use that quote must have:

```text
publication_at <= quote.accepted_at
entry_deadline_at = publication_at + 2 seconds
```

and therefore cannot have a usable deadline later than `quote.accepted_at + 2 seconds`. Any future-delivered intent beyond that bound is terminalized under Section 4 and cannot claim the quote retroactively.

The worker must apply eviction:

1. before adding an incoming quote to the quote buffer;
2. after processing an intent event;
3. after processing a quote event; and
4. whenever the earliest pending deadline wakes the worker.

When the quote buffer is at capacity:

1. evict every quote expired under the exact rule above;
2. retain all nonexpired quotes in deterministic selection order;
3. append the incoming quote only if capacity is then available; and
4. if capacity is still unavailable, drop only the incoming quote.

No nonexpired older quote may be evicted merely to make room. No synthetic terminal entry is created for quote-buffer overflow. Production remains unaffected.

Quote-buffer ordering remains ascending:

1. `accepted_at`;
2. `provider_event_ns`; and
3. `quote_id`.

This amendment forbids an unbounded "future delayed intent might still need this quote" retention rule. The quote buffer must be able to drain after the exact two-second retention bound.

## 6. Required amendment tests

SIM-4 implementation must add tests for all original SIM-3A requirements and these exact amendments.

### SIP source identity

- the live Alpaca latest-quotes request explicitly contains `feed=sip`;
- the exact frozen URL requests `COIN` and `QQQ` from SIP;
- omitted-feed, IEX, alternate-feed, and unprovable-source paths submit no SIM-4 quote event;
- a non-SIP quote cannot be hashed or persisted with the SIP source-spec identity; and
- exact provider nanoseconds survive the SIP request path into the quote contract.

### Advisory lock

- exact namespace bytes;
- exact NUL separators;
- exact ASCII horizon bytes;
- SHA-256 first-eight-byte extraction;
- big-endian conversion;
- signed two's-complement conversion;
- all six golden lock keys;
- exact one-argument `pg_advisory_xact_lock(bigint)` call;
- lock acquisition before existing-entry and occupancy reads;
- lock held through terminal insert and commit/rollback;
- two concurrent/rolling implementations use the same key; and
- no Python or PostgreSQL text-hash shortcut.

### Collision and restart precedence

- durable open occupancy plus recent unmatched actionable intent produces `SKIPPED_POSITION_OPEN`;
- the exact open `entry_id` is preserved as `blocking_entry_id`;
- the same input without open occupancy produces `SKIPPED_RESTART_GAP`;
- non-actionable restart intents preserve their normal statuses;
- collision precedence is identical before and after restart;
- occupancy is re-read under the lock;
- multiple durable open entries fail closed; and
- recovery ordering is deterministic.

### Late intents

- intent handoff time after deadline cannot enter;
- worker processing time after deadline cannot enter;
- buffered quotes are not inspected for a late intent;
- ordinary late actionable intent produces `SKIPPED_WINDOW_EXPIRED`;
- open-position collision still precedes late expiry;
- restart gap still precedes late expiry when no position is open;
- handoff exactly at deadline follows the inclusive boundary;
- processing exactly at deadline may use an already-buffered valid quote;
- equality with no valid quote remains pending rather than expiring immediately;
- an equality-boundary quote admitted before the first strictly-greater expiry observation is processed before expiry;
- a quote not admitted by the strictly-greater expiry observation is never reconstructed or applied retroactively;
- pending wait is bounded by the earliest deadline and then the first strictly-greater clock observation;
- expiry does not require a later market event; and
- runtime clock failure does not affect SIM-1/SIM-2 persistence or production.

### Quote eviction

- quote retained at `accepted_at + 2 seconds` exactly;
- quote evicted one microsecond after the retention boundary;
- expired quotes are removed before buffer-capacity rejection;
- nonexpired quotes are never evicted to make room;
- incoming quote alone is dropped when capacity remains full;
- delayed intents cannot keep quotes forever;
- repeated late intents cannot permanently fill the quote buffer;
- deterministic quote ordering survives eviction; and
- no historical reconstruction or synthetic evidence is created.

## 7. Documentation-only and phase boundary

This amendment changes documentation only.

It creates no Python implementation, test implementation, migration, schema, database object, Render change, web route, runtime hook, broker capability, simulator entry, simulator resolution, P&L, or compact state.

The original exact six-file SIM-4 implementation boundary remains unchanged:

1. `migrations/027_create_v9_sim_entries.sql`;
2. `quant/v9_sim4_entry.py`;
3. `tests/test_v9_sim4_entry.py`;
4. minimal post-success persisted-intent callback changes in `quant/v9_sim3_capture.py`;
5. minimal exact SIP/provider-nanosecond and post-publication callback changes in `quant/live_market.py`; and
6. SIM-4 construction/lifecycle changes only in `quant/web.py`.

After this amendment merges, Codex may implement SIM-4 only under the combined original SIM-3A freeze and this controlling amendment.

SIM-5 and SIM-6 remain unauthorized.
