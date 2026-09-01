# SIM-4 paper Trading API WebSocket authentication amendment

**Status:** Controlling narrow amendment  
**Authorized implementation:** SIM-4 authentication only  
**Unaffected phases:** SIM-5 and SIM-6 remain outside this amendment

## 1. Precedence and exact purpose

This document amends only the SIM-4 Alpaca authentication mechanism frozen by the merged SIM-3B/SIM-4 documents. Where an earlier document requires Broker AuthX or forbids all Alpaca Trading API credentials, this amendment controls only for the isolated SIM-4 worker's existing COIN SIP market-data WebSocket.

No other boundary is relaxed.

## 2. Sole authorization

The dedicated Render Background Worker `atom-v9-sim4-worker`, running `python -m quant.v9_sim4_worker`, may receive one Alpaca **paper Trading API** key pair through these dedicated worker-only environment names:

```text
ATOM_V9_SIM4_ALPACA_PAPER_API_KEY_ID
ATOM_V9_SIM4_ALPACA_PAPER_API_SECRET_KEY
```

The existing provisioning-attestation ID and SHA-256 settings remain required. Their evidence must identify this exact key pair as generated from the Alpaca paper-trading environment and provisioned only to the isolated SIM-4 worker. Credential provenance is a deployment invariant; the worker must not call an account or trading endpoint to discover or validate it.

No standard Alpaca environment name, alias, fallback, inherited environment group, or production-service credential is authorized.

## 3. Exact network boundary

The worker may open only:

```text
wss://stream.data.alpaca.markets/v2/sip
```

After the TLS WebSocket is open, it must send exactly one Alpaca key/secret authentication message, require the existing authenticated success acknowledgement within the existing timeout, and then send the existing exact COIN quote subscription:

```json
{"action":"subscribe","quotes":["COIN"]}
```

The key and secret may be used only to construct the WebSocket authentication frame. They must never be placed in a URL, persisted, returned, logged, included in telemetry, included in exception text, or exposed through object representations.

The existing source identity remains exactly:

```text
ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1
```

## 4. Hard prohibitions

The following remain impossible and forbidden:

- Alpaca live-account credentials of any kind;
- every Alpaca HTTP or REST request, including both paper and live Trading API hosts;
- every account, position, order, asset-trading, trade-update, portfolio, activity, transfer, watchlist, OAuth, and Broker API endpoint;
- order submission, cancellation, replacement, preview, or status polling;
- use of an Alpaca trading SDK/client in the SIM-4 worker;
- credentials on the ATOM web service, publisher runtime, production V9 services, benchmarks, family workers, or any service other than `atom-v9-sim4-worker`;
- fallback to `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, any base-URL variable, or the superseded AuthX client variables.

Presence of a forbidden authority variable must continue to fail closed before database or network I/O, even when its value is empty.

## 5. Preserved law

This amendment changes no:

- V9, V1-V4D, family, target, direction, quantity, entry-price, or return mathematics;
- publication, eligible-time, two-second entry-window, deadline, ordering, collision, reconciliation, restart, advisory-lock, queue, or terminal-status rule;
- symbol, feed, quote schema, source specification, source hash, or SIP identity;
- simulator Supabase project, roles, DSNs, installation identity, row-level authority, or publication/entry separation;
- append-only intent, publication, entry, checkpoint, or historical-record rule;
- production hook, web route, UI, broker authority, account authority, order authority, deployment topology, or service ownership boundary.

No migration, schema, data rewrite, backfill, deletion, or history cap is authorized.

## 6. Exact implementation surface

Codex may modify only:

```text
quant/v9_sim4_worker.py
quant/web.py
tests/test_v9_sim4_isolation.py
```

The worker change must replace the AuthX HTTP token exchange with the exact WebSocket key/secret authentication frame. The web change may only extend the existing worker-credential refusal set for the two new dedicated names. The test change may only prove this amendment and preserve all existing SIM-4 invariants.

No refactor or unrelated cleanup is authorized.

## 7. Required tests and merge gate

Before merge, Codex must prove at minimum:

1. the two new dedicated settings and the existing attestation are required with no fallback;
2. old AuthX, standard Alpaca, base-URL, broker, live, account, position, order, and production variables fail closed before external I/O;
3. the only Alpaca network destination is the exact SIP WebSocket;
4. the first client frame is the exact authentication object and the existing COIN subscription follows only after the authenticated acknowledgement;
5. no Alpaca HTTP client, token endpoint, REST host, trading SDK, account path, position path, or order path exists in the worker implementation;
6. secrets cannot appear in repr, exceptions, logs, or telemetry;
7. the ATOM web service rejects the new worker-only credential names;
8. focused SIM-4 tests, the full test suite, Python compilation, and diff checks pass;
9. the final PR changes only the three authorized implementation files.

## 8. Deployment and live simulated-entry proof

After merge, deploy the merged commit manually to the existing isolated worker because its Render auto-deploy is disabled. Configure the paper key pair and attestation only on that worker and enable the existing SIM-4 flag.

A passing live proof requires all of the following:

- the worker owns the existing isolated database session and reaches its existing ready state;
- authenticated COIN SIP quotes are admitted under the unchanged source identity;
- the dedicated simulator database's immutable entry count increases from the pre-amendment baseline;
- newly appended entries reference existing immutable intents/publications and preserve every frozen status, deadline, quote, and hash rule;
- no account, position, order, trade-update, or Trading API REST request occurs;
- no production service receives the credentials or changes deployment state.

“Live simulated entries” means simulated records produced from real-time SIP quotes only. It never means live-account access or real order execution.

## 9. Rollback

Rollback is limited to disabling the existing SIM-4 enable flag or redeploying the prior worker commit. Already appended simulator history remains immutable and must not be removed or rewritten.
