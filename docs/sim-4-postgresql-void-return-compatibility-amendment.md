# SIM-4 PostgreSQL void-return compatibility amendment

**Status:** Controlling narrow repair  
**Authorized implementation:** SIM-4 horizon advisory-lock return decoding only

## Exact authorization

The existing `SimulationEntryStore.get_existing_entry_in_transaction` call to:

```sql
SELECT pg_advisory_xact_lock(%s::bigint)
```

must continue to acquire the same transaction-scoped per-horizon advisory lock with the same frozen key, transaction, ordering, and authority rules.

After `cursor.fetchone()`, the following exact successful void-return representations are permitted:

```python
None
(None,)
("",)
```

Bare `None` and `(None,)` are existing accepted behavior. This amendment adds only the PostgreSQL/Psycopg compatibility representation `("",)`.

Every other value remains malformed and must raise the existing `SimulationEntryStateError` before any entry or occupancy decision proceeds.

## Exact implementation surface

Codex may modify only:

```text
quant/v9_sim4_entry.py
tests/test_v9_sim4_entry.py
```

The production change is limited to adding `("",)` to the existing successful horizon-lock result check. No helper, abstraction, refactor, migration, dependency, configuration, diagnostic, or unrelated cleanup is authorized.

## Preserved law

This amendment changes no:

- advisory-lock SQL, namespace, key derivation, key values, scope, acquisition point, or transaction lifetime;
- runtime-owner lock, activation lock, deadline-publication lock, admission fence, or checkpoint behavior;
- V9 or SIM mathematics, intent mapping, entry price, quantity, direction, deadline, quote selection, collision precedence, restart handling, or terminal status;
- database role, DSN, project identity, RLS, least privilege, Supabase isolation, or Render service boundary;
- Alpaca authentication, SIP source identity, market-data subscription, broker authority, account authority, position authority, order authority, or trading authority;
- append-only intents, publications, entries, checkpoints, hashes, identities, or historical records.

No existing row may be deleted, rewritten, migrated, backfilled, or corrected in place.

## Required tests

Codex must prove:

1. `(None,)` remains accepted;
2. `("",)` is accepted as the additional successful void-return representation;
3. bare `None` remains accepted;
4. all other shapes and values remain rejected with `SimulationEntryStateError`;
5. the exact advisory-lock SQL, horizon key, lock-before-read order, transaction ownership, existing-entry precedence, and occupancy rules remain unchanged;
6. focused SIM-4 entry tests and the full suite pass;
7. Python compilation and `git diff --check` pass;
8. the implementation PR changes exactly the two authorized files.

## Deployment and reactivation

After merge, Codex may manually deploy merged `main` to the existing isolated Render worker:

```text
atom-v9-sim4-worker
srv-dabgssvavr4c73852m3g
python -m quant.v9_sim4_worker
```

No environment-variable, credential, start-command, service-plan, Supabase, or production-service change is authorized.

A passing reactivation proof requires the existing worker to remain active beyond the prior `READY_LOOP / SimulationEntryStateError` failure point, advance the isolated simulator checkpoint, and append immutable SIM-4 terminal entry records from existing publications under all previously frozen rules. Existing history must remain intact.

Rollback is limited to disabling or suspending the isolated worker and redeploying the preceding commit. Durable simulator history remains append-only.
