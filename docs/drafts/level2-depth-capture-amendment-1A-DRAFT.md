# ATOM COIN Level II Depth Capture — Amendment 1A: Observer Runtime (DRAFT)

**Draft status:** PREPARED BY CLAUDE AT OWNER REQUEST under `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B` delegated drafting. Zero controlling authority until adopted by its author of record (ChatGPT Pro, or the Owner directly under 1B), independently reviewed on its final head, and Owner-merged as a documentation-only change.  
**Decision ID (proposed):** `ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1A`  
**Amends:** `ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1` §8 (implementation scope) only  
**Owner decision incorporated:** 2026-09-03, option (a) — authorize an ATOM Schwab observer worker service (composition root, OAuth token store, lease, Schwab credentials on Render)  
**Change type:** Documentation only

---

## 0. Why this amendment exists

The base freeze authorizes capture "in the existing observer runtime" and states "No new service is authorized." Implementation returned `BLOCKED` on 2026-09-03 with this finding:

- ATOM's `quant/schwab_market_worker.py` is a library with no composition root. `main()` returns exit code `2` unless a `worker_factory` is injected, and no module in the repository injects one.
- No Render service in the ATOM workspace runs it. `quant/web.py` starts Alpaca, G2, Massive NDX, and options pollers only.
- The only live COIN `NASDAQ_BOOK` stream belongs to `coin-v8-schwab-level2-worker` in the Coin-market-api repository, outside the base freeze's scope.

Therefore no runtime exists to which capture can attach. The Owner chose to create one inside ATOM rather than capture from the V8 worker.

## 1. Exact amendment to §8

Strike, in §8 of the base freeze:

> No new service is authorized. If the existing observer runtime cannot safely own this append-only capture without a new service or broader credential boundary, implementation returns `BLOCKED` for a separate decision.

Replace with:

> Exactly one new Render Background Worker, `atom-schwab-observer-worker`, is authorized as the observer runtime for the existing `SchwabMarketWorker`, together with the composition root, durable OAuth vault, lease, dedicated database role, and dedicated credentials named in Amendment 1A. It exists to host the already-frozen read-only Schwab observer lane and the Level II capture sink. It receives no production writer credential, no simulator credential, no broker authority, and no consumer into any quant, evidence, SIM, or trading path.

Every other section of the base freeze is unchanged: source boundary, persisted columns, append-only law, observer-only isolation, no research promotion, capture semantics, publication independence, required tests, activation gate, acceptance receipt, and frozen conclusion.

## 2. Service and gates

```text
Service:        atom-schwab-observer-worker   (Render Background Worker, ATOM repository)
Start command:  python -m quant.schwab_observer_worker
Runtime gates:  ATOM_SCHWAB_MARKET_DATA_ENABLED=true   (existing worker gate, lowercase true only)
                the Level II capture gate named by the merged job card (capture stays off until it is true)
```

Both gates default off. The worker with the observer gate on and the capture gate off streams and publishes transiently exactly as the frozen S1/S2A lane specifies, and persists nothing. Render auto-deploy remains disabled; deploys are manual at an exact SHA.

## 3. Credentials and isolation

The worker receives exactly these dedicated environment names and nothing else from the production or simulator credential sets:

```text
ATOM_SCHWAB_CLIENT_ID
ATOM_SCHWAB_CLIENT_SECRET
ATOM_SCHWAB_REDIRECT_URI              (https, no query, no fragment — per the existing _require_https_url rule)
ATOM_SCHWAB_OBSERVER_DATABASE_URL     (PostgreSQL username exactly atom_schwab_observer; TLS required; session mode; port 6543 fails closed)
```

The worker must not receive `DATABASE_URL`, any V4/V9 writer credential, the E-1 reader credential, any `ATOM_V9_SIM*` credential, a service-role key, or any Alpaca credential. Presence of any such name fails closed before network or database I/O, following the SIM-4 worker's existing refusal pattern. `quant/web.py` refuses the four names above.

The Schwab OAuth surface remains exactly the frozen one: `/v1/oauth/authorize`, `/v1/oauth/token`, `/marketdata/v1/quotes` for `$NDX`, `/trader/v1/userPreference` for streamer metadata only, and `wss://streamer-api.schwab.com/ws` with `NASDAQ_BOOK` fields `0,1,2,3` for `COIN`. No account, position, order, or trading endpoint. Account fields incidentally returned by `userPreference` are discarded exactly as today.

## 4. Persistence additions (one migration)

One migration, at the next unoccupied ordinal on the implementation base (expected `032` after SIM-5's `031`; if occupied, stop `BLOCKED`), creates in the ATOM production project:

**4.1 Role.** `atom_schwab_observer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, no password (the Owner sets it afterwards). No membership, ownership, schema `CREATE`, sequence privilege, or RLS bypass.

**4.2 The Level II depth table** exactly as the base freeze §2–§3 specifies, with `SELECT` and `INSERT` only for `atom_schwab_observer`, forced RLS, and `UPDATE`/`DELETE`/`TRUNCATE` rejection triggers. Duplicate handling: unique on `(symbol, provider_epoch, source_sequence)` with `ON CONFLICT DO NOTHING` — deterministic, never overwrites.

**4.3 OAuth vault** — `public.atom_schwab_oauth_vault`, one row, operational state, not evidence:

```text
vault_key                text PRIMARY KEY  = 'ATOM_SCHWAB_OBSERVER_1'   (check-constrained)
access_token             text NULL
refresh_token            text NULL
expires_at_epoch         double precision NULL
token_version            bigint NOT NULL DEFAULT 0
pending_state_digest     text NULL
pending_state_expires_at double precision NULL
updated_at               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
```

It backs the existing `OAuthStore` protocol exactly: `save_state_digest` and `consume_state_digest` (single-use, expiring), `load_tokens`, and `compare_and_swap_tokens` implemented as a conditional `UPDATE ... WHERE token_version = expected` that bumps the version. `atom_schwab_observer` has `SELECT`, `INSERT` (seed only), and `UPDATE` on this one row through forced-RLS policies; no `DELETE`/`TRUNCATE`. Access is revoked from `PUBLIC`, `anon`, `authenticated`, `service_role`, and every other ATOM role. Tokens are never logged, never returned by any CLI, never included in health or receipts. The append-only law of the base freeze applies to the depth table; it does not apply to this vault or the lease, which are mutable operational singletons by design and hold no market evidence.

**4.4 Lease** — `public.atom_schwab_observer_lease`, one row:

```text
lease_key    text PRIMARY KEY = 'ATOM_SCHWAB_OBSERVER_1'   (check-constrained)
owner_token  text NULL
expires_at   double precision NULL
updated_at   timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
```

It backs the existing `Lease` protocol: `acquire(owner_token, ttl)` is a conditional `UPDATE` succeeding only when the row is unowned or expired; `renew` succeeds only when `owner_token` matches and is unexpired; `release` succeeds only when it matches. TTL and renewal use the worker's existing constants (45 s / 15 s). Rolling replacement therefore yields exactly one streaming owner; a stale owner cannot publish or capture, because the worker already fences every publish and send on the lease.

## 5. Composition root (new module)

`quant/schwab_observer_worker.py` constructs, from the four environment names only: the PostgreSQL `OAuthStore` and `Lease` above, `SchwabOAuthSession`, the existing in-process `schwab_market_bus` bus (transient publication contract unchanged), a `CapturingBus` wrapper, and `SchwabMarketWorker` with the default websocket factory and a fresh random `owner_token` per process. It injects itself through the existing `main(env, worker_factory)` seam. `schwab_market_worker.py` and `schwab_market_bus.py` are not modified.

The `CapturingBus` delegates `publish_ndx` and `publish_book` to the existing bus unchanged. Only after `publish_book` returns `True` — i.e., the snapshot was already accepted by the frozen normalization and lease-fenced publication — does it hand the exact accepted `BookSnapshot` to the capture sink through a bounded non-blocking queue. The sink writes append-only rows on its own thread with batched inserts and its own connection. Capture never blocks, delays, or fails publication; sink failure or overflow is a health counter and a receipt line, never a publication failure and never a fabricated durable claim (base freeze §7).

**OAuth bootstrap CLI**, in the same module, for the Owner only:

```text
python -m quant.schwab_observer_worker authorize          → prints the authorize URL (state digest saved to the vault); prints no token
python -m quant.schwab_observer_worker callback --url …    → completes the exchange, compare-and-swaps tokens into the vault; prints only OK/FAILED
```

Re-authorization is an Owner operating duty on Schwab's refresh-token schedule. When refresh fails the worker enters `AUTHORIZATION_UNAVAILABLE`, publishes nothing, captures nothing, and keeps the lease so no second owner appears; it does not retry authorization on its own.

## 6. Coexistence check before activation (Owner)

Schwab commonly permits one active streamer session per account. Before setting the observer gate to `true`, the Owner verifies whether an ATOM login disconnects `coin-v8-schwab-level2-worker`. If it does, the Owner decides which worker runs; this amendment authorizes no change to the V8 worker and no second Schwab account. If the check cannot be performed, activation waits.

## 7. Authorized files (supersedes the job card's file list for this job)

- create `quant/schwab_observer_worker.py` (composition root, PostgreSQL store and lease, `CapturingBus`, OAuth CLI);
- create `quant/level2_depth_capture.py` (row serialization, capture sink, insert store, health counters);
- create `migrations/032_create_level2_depth_capture.sql` (or the verified next ordinal);
- create `tests/test_schwab_observer_worker.py` and `tests/test_level2_depth_capture.py`;
- minimally modify `quant/web.py` only to refuse the four observer credential names.

No change to `quant/schwab_market_worker.py`, `quant/schwab_market_bus.py`, `quant/live_market.py`, any family, V9, evidence, E-1, SIM, or UI file. If another file is required, stop `BLOCKED`.

## 8. Additional required tests

Beyond the base freeze §10: gates default off and require lowercase `true`; forbidden credential names fail closed before I/O; `web.py` refuses the four names; the vault CAS rejects a stale version; the state digest is single-use and expiring; the lease admits one owner across a simulated rolling replacement and a stale owner cannot publish; `CapturingBus` captures only after `publish_book` returns `True`; capture overflow and sink failure never affect publication and are counted; tokens never appear in logs, exceptions, repr, CLI output, health, or receipts; no endpoint outside the frozen Schwab surface is reachable; migration creates exactly the role, three tables, policies, triggers, and grants above; full existing suite green; final diff contains only the files in §7.

## 9. Activation, receipt, rollback

Activation follows the base freeze §11 with one addition: step 6 above precedes the Owner's activation approval. The Owner sets the role password, provisions the four environment names on the worker only, completes the OAuth bootstrap, deploys the exact merged SHA, and only then sets the two gates.

The base freeze §12 receipt applies unchanged, plus: worker identity and single lease owner; vault `token_version` advancing without token disclosure; and health counters showing zero capture-induced publication failures.

Rollback: gates off, or suspend the worker. Captured rows remain immutable. The Owner may revoke the Schwab authorization at Schwab; the vault row is then invalid and the worker fails closed.

## 10. What this amendment does not authorize

No use of captured depth by Q5, any family, V2–V4, E-1, SIM, or trading; no S3; no second market-data source; no change to the V8 worker; no Alpaca credential on this worker; no broker, account, order, or position endpoint; no change to the transient publication contract; no research on the captured history.

**END — DRAFT ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1A**
