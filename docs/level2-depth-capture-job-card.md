# Level II Durable Depth Capture — Claude Job Card

**Job ID:** `LEVEL2-DEPTH-CAPTURE-IMPLEMENTATION-1`  
**Controlling governance:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1B`  
**Controlling technical freeze:** `ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1`  
**Named implementation owner:** Claude  
**Owner:** ATOM Owner

## Objective

Implement only the smallest default-off observer-only durable capture path for accepted normalized COIN Schwab `NASDAQ_BOOK` Top-3 snapshots.

## Exact scope

Permitted repository/runtime scope is limited to:

- the existing Schwab COIN `NASDAQ_BOOK` observer lane;
- one new isolated append-only Level II depth table;
- the minimum least-privilege migration/grants/policies/triggers needed for that table;
- one default-off Level II depth-capture gate;
- exact snapshot serialization and insert path;
- deterministic duplicate/idempotency handling required by the freeze;
- tests and deterministic capture health/receipt proof.

## Permitted actions

Claude may implement, test, commit, and prepare the implementation PR for this exact job. Claude may use repository tools needed to do so beneath the controlling freezes.

## Prohibited actions

Do not change Q5, Q1-Q12 families, V2/V3/V4, evidence scoring, E-1, SIM, broker/account/order paths, execution, trading authority, source identity, NDX behavior, existing Level II normalization mathematics, unrelated credentials, unrelated services, or surrounding code. Do not implement E-3, drift-adjusted benchmarking, S3, a new Level II signal, or any Level II consumer. Do not add a new service unless implementation proves the existing observer runtime cannot safely own capture; if so return `BLOCKED`.

## Required tests

Prove all requirements in `ATOM_LEVEL2_DEPTH_CAPTURE_FREEZE_1.md`, including exact COIN-only Top-3 persistence, field/timestamp/order parity, deterministic duplicate handling, append-only UPDATE/DELETE/TRUNCATE rejection, disabled-gate behavior, and zero Q5/family/V4/SIM/broker side effects.

## Required evidence

The implementation PR must identify changed files, exact test commands/results, migration identity, runtime gate name, database authority, and prohibited surfaces confirmed untouched. After approved activation, produce the freeze-required market-session acceptance receipt showing advancing durable rows and no unexplained accepted-to-committed gap.

## PASS

PASS only when the final intended head satisfies the controlling freeze exactly, every required check is green, independent final-head review has no unresolved material findings, append-only protections are proven, default-off behavior is proven, and scope contains no unauthorized consumers or authority expansion.

## FAIL

FAIL when deterministic tests show incorrect persistence, mutation is possible, unauthorized consumers are reached, capture changes existing observer behavior, or activation produces an unexplained durability gap.

## INVALID

INVALID when the proof cannot establish exact source/field/timestamp identity, the tested revision is not the final intended head, required market-session evidence is incomplete, or receipts cannot identify the deployed revision/database/source boundary.

## BLOCKED

Return `BLOCKED` if the job requires a new service, new source, broader credential, Q5/family/V9/SIM change, E-3/drift work, unsupported database authority, or any change outside the controlling freeze.

## Stop condition

Stop immediately at the first required authority expansion or architectural contradiction. Do not work around a freeze.

## Review and merge

Claude may not be sole reviewer of its own implementation. Final-head independent review must be Codex, Copilot's PR reviewer, a qualified human, or the Owner. Every required check must be green. Owner retains final merge, migration-apply, deployment, activation, credential, broker, and capital authority.
