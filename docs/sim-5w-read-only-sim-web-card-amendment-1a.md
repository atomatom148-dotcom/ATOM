# SIM-5W read-only simulation web card — Amendment 1A (reader-role validation)

**Decision ID:** `ATOM-SIM5W-READ-ONLY-SIM-WEB-CARD-FREEZE-1A`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling within the SIM-5W subject only.  
**Amends:** `docs/sim-5w-read-only-sim-web-card-freeze.md` (`ATOM-SIM5W-READ-ONLY-SIM-WEB-CARD-FREEZE-1`) sections 3, 8, and 9 only  
**Author of record:** ATOM Owner, adopting this Claude-prepared draft directly under `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B` §2.1 (Owner approval of this exact text: 2026-09-04). Owner authorship is recorded here as that amendment requires. If ChatGPT Pro adopts the text before merge, ChatGPT Pro becomes author of record and this line is corrected in the same pull request.  
**Drafted by:** Claude at Owner request (delegated drafting; zero authority by itself)  
**Change class:** documentation only  
**Implementation base observed:** `d794a85a2a7273df2317027e04adcb8f3022f2b8`

## 0. Documented conflict

Freeze section 3 requires the web-reader DSN to pass "the existing simulator-DSN validation with `required_role="atom_v9_sim_web_reader"`". The only existing validator, `validate_simulator_database_url` in `quant/v9_sim4_entry.py`, accepts exactly the two runtime roles and raises `SimulationDatabaseConfigurationError("simulator database role is not authorized")` for every other `required_role`. Called as the freeze requires, it always fails, so the card could only ever render `NO DATA`. Section 8 excludes `quant/v9_sim4_entry.py` from the implementation surface. The frozen design therefore cannot work as written; implementation stopped `BLOCKED` per `AGENTS.md`.

## 1. Amendment to section 3

The existing validator's accepted-role set may be widened by exactly one constant and one tuple entry:

```python
SIM_WEB_READER_ROLE = "atom_v9_sim_web_reader"
```

added to the roles `validate_simulator_database_url` accepts for `required_role`. Every other validator rule — direct or session-pooler endpoint only, exact project ref, database `postgres` on explicit port 5432, complete credentials, one mandatory TLS mode, exact role-bound username, discovered project match — remains unchanged and applies to the reader DSN identically. The validator continues to reject every role outside the three named roles.

"The existing project-ref proof" in section 3 means the DSN-level proof already used by `quant/web.py` for the SIM-3 publisher: the production `DATABASE_URL` must yield a discovered Supabase project ref that is non-null and different from the reader DSN's project ref. The `atom_v9_sim_installation` identity query is not part of the SIM-5W read path; the reader receives no privilege on that table, and section 6's statement list is unchanged.

## 2. Amendment to section 8

The implementation surface additionally includes:

- `quant/v9_sim4_entry.py` — only the one-constant, one-tuple-entry widening described in section 1. No other line of that file may change.

## 3. Amendment to section 9

Before merge additionally prove:

- `validate_simulator_database_url` accepts `required_role="atom_v9_sim_web_reader"` for a correctly role-bound reader DSN, still rejects any unlisted role, and still rejects a reader-role requirement against a DSN bound to either runtime role;
- both runtime-role validation paths and every existing validator test remain unchanged and green.

## 4. Preserved law

Every other provision of `ATOM-SIM5W-READ-ONLY-SIM-WEB-CARD-FREEZE-1` remains in force unchanged: the dedicated role and its exact privilege set (section 2), the exact credential (section 3 as amended above), the exact card contents and status semantics (sections 4–5), the exact read path (section 6), the visual footprint (section 7), the merge, provisioning, and deployment gate (section 10), and the acceptance proof (section 11). No SIM worker, SIM entry/resolution contract, migration 027/031, isolation test, V9, family, broker, account, order, production, Render, or Supabase change is authorized by this amendment.

## 5. Merge gate

Documentation only. Independent final-head review, every required check green, zero unresolved material threads, Owner merge. The SIM-5W implementation PR may open only after this amendment is merged.

**END — ATOM-SIM5W-READ-ONLY-SIM-WEB-CARD-FREEZE-1A**
