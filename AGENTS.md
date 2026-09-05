# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md`
3. Every amendment to that role-governance freeze present on current `main`;
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md`,
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B.md`,
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1C.md`, and
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1D.md` govern only from their
   respective Owner-approved merge commits
4. `FREEZE.md`
5. `SIMULATION_FREEZE.md`
6. `PHASES.md`
7. The freeze and amendments for the active phase

Do not rely on chat memory as authority.

## Authority by subject

There is no single linear precedence list across unlike subjects.

### Governance domain

`ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` and its effective merged
amendments control AI and human role boundaries, freeze authorship,
implementation ownership, innovation workflow, review requirements, evidence
governance, and final technical-audit authority.

When `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md` is effective, its §3
supersedes base §3. When `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B.md` is
effective, its explicit delegation and Owner-author-of-record fallback clauses
supersede conflicting sole-author and Claude-implementation restrictions in the
base freeze and Amendment 1A. When `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1C.md`
is effective, its automatic Claude implementation-fallback rule supersedes only
the per-job explicit-naming requirement in Amendment 1B §1 when Codex is
objectively unavailable. Amendment 1D grants Claude autonomous execution and
repair authority inside already-approved frozen boundaries and removes Codex or
ChatGPT Pro unavailability as a prerequisite for that execution. The base
documents remain immutable historical adoption records and are not silently
rewritten.

A technical freeze cannot supersede governance law on those subjects unless it
explicitly identifies and amends the role-governance decision through its
required authorship, review, Owner-approval, and documentation-only merge
procedure.

### Technical domain

The latest applicable Owner-approved technical freeze or amendment controls
system behavior within its named subject and scope. Among technical documents
addressing the same subject, the explicit later amendment and the narrowest
applicable restriction control. `SIMULATION_FREEZE.md` controls simulator work,
then `FREEZE.md`, then `PHASES.md`, then existing implementation.

Governance law cannot silently change a technical formula, source, persistence
rule, service boundary, or authority path. Such a change requires an explicit
technical amendment naming the affected law.

### Owner operational authority

A current Owner operational instruction controls immediately when it:

- selects or reprioritizes work already allowed by the applicable freezes;
- chooses among already-authorized implementation or operational options;
- sets cost or vendor limits;
- orders a protective stop, suspension, disablement, rollback, or credential
  revocation;
- approves or rejects a merge;
- authorizes a deployment or activation already permitted by the applicable
  technical freeze; or
- rejects, pauses, or permanently ends a program.

When the Owner requests an action that crosses a frozen governance or technical
boundary, that request is binding direction to prepare the required amendment.
It does not silently rewrite existing law or authorize execution across the
boundary before the amendment is Owner approved and merged. Protective stop and
rollback authority remains immediate.

### Freeze-author continuity and delegated drafting

ChatGPT Pro remains the normal freeze and amendment author. Claude may prepare
draft freeze, amendment, phase, preregistration, acceptance-gate, or research
contract text at Owner request, but a Claude draft has zero controlling
authority by itself.

If ChatGPT Pro lacks current capacity or availability, the Owner may explicitly
adopt a prepared draft directly and becomes the author of record. Claude remains
the draft preparer only. The same documentation-first ordering, independent
final-head review, required-green-check, and Owner merge requirements remain.
Claude does not become freeze author through this path.

### Claude autonomous execution and repair

Codex remains the preferred default implementation engineer. Under Amendment
1D, Claude may independently assume and execute an already-authorized frozen
implementation or repair job without waiting for Codex or ChatGPT Pro to become
unavailable.

Inside that exact frozen boundary Claude may create, implement, test, fix,
repair, assemble, commit, maintain the PR, resolve findings, merge after all
mandatory gates pass, perform already-authorized operational steps, deploy or
restart already-authorized services, verify behavior, and capture the required
receipt. No additional ChatGPT Pro approval is required merely to move between
those already-authorized steps.

Claude may not reinterpret or widen a frozen boundary. One job still has one
implementation owner at a time; once Claude assumes a job, ownership stays with
Claude through completion unless the Owner explicitly transfers it.

When Claude implements, Claude may not be the sole final-head reviewer. Codex,
Copilot's pull-request reviewer, a qualified human, or the Owner must provide
independent final-head review. Every required check remains mandatory and green.

### Cross-domain conflicts

First determine whether the documents address the same subject. Apply each
within its own subject. Do not infer cross-domain supersession. If the subject
or supersession remains ambiguous, stop as `BLOCKED`.

Documented Claude, specialist, and reviewer findings rank above implementation
convenience, tool defaults, and informal suggestions. They remain advisory and
cannot override an applicable freeze, expand authorized scope, or replace the
Owner's final authority.

## Startup statement

Before taking any action, inspect the current `main` commit, confirm each
controlling document exists at that commit, and state:

- controlling role-governance freeze and amendments, technical freezes, and
  commit;
- currently authorized phase;
- files and systems permitted to change;
- prohibited changes;
- merge and deployment authority.

If instructions conflict, stop. The narrowest, latest Owner-approved freeze
within the applicable subject controls. Do not infer permission from previous
code, an open PR, or chat context.

## Hard stop

Stop and request Owner approval if:

- controlling documents conflict or are ambiguous;
- work requires changing a freeze;
- a required action is not expressly authorized;
- scope expands to another phase, service, database, role, credential, or
  deployment;
- implementation reveals that the frozen design cannot work as written.

No implied permission. "Probably intended" means not authorized.

## Phase separation

A documentation freeze or amendment is its own phase. Merge it before opening
an implementation PR.

Implementation, migrations, production execution, deployment, and later
research phases are separate unless the controlling text explicitly says
otherwise.

## Freeze changes

Never edit controlling law without explicit Owner approval.

A freeze amendment must:

- be documentation-only;
- identify every changed rule;
- receive independent review on the final intended head;
- resolve or disposition all P1 and P2 findings;
- have zero unresolved material threads;
- have every required check green; and
- be merged by the Owner before implementation begins.

If a named reviewer is unavailable, the Owner may designate a substitute
independent reviewer on the final intended head. Unavailability may change the
reviewer; it may not remove the review.

No check waiver, substitution, or bypass is implied. A required check may be
changed, removed, or replaced only by a separate Owner-approved amendment that
expressly identifies that check before the affected merge.

A green check or "review completed" badge that covers an earlier commit, or
that leaves material threads unresolved, is not approval. Never merge first and
repair afterward.

## Change discipline

Make only the minimum authorized changes. No opportunistic cleanup,
refactoring, dependency updates, migrations, grants, deployments, or
configuration changes.

Before presenting a PR, compare the diff against the controlling freeze line by
line and report:

- controlling document and commit;
- exact authorization;
- changed files;
- tests performed;
- prohibited areas confirmed untouched;
- unresolved review findings;
- whether Owner merge is required.

## External systems

GitHub merge authority does not imply authority to change Supabase, Render,
brokers, market-data services, credentials, billing, or production state.
Each requires explicit authorization from the controlling phase or Owner.

## Trading boundary

No broker orders, live trading authority, account actions, position actions, or
money movement without an explicit Owner-approved freeze permitting that exact
action.

## Active phase pointer

Update this section only by Owner-approved documentation change.

- Active phase: **SIM-5 — six-horizon causal resolution**.
- Controlling text: `docs/sim-4a-exact-sim5-resolution-freeze.md`, plus the
  existing merged simulator freezes it explicitly preserves.
- Implementation owner: **Codex preferred; Claude may autonomously assume and
  complete this already-frozen job under Amendment 1D**.
- Authorized order: one SIM-5 implementation PR by the active implementation
  owner; independent final-head review and green required checks; lawful merge;
  apply migration `031` once to the isolated simulator project; enable
  `ATOM_V9_SIM5_ENABLED=true` on the existing SIM-4 worker; deploy the exact
  merged SHA; capture deployment proof and then live causal resolution
  acceptance when market evidence is available.
- E-1 is complete and its official receipt is preserved at
  `docs/e-1-official-scorecard-receipt-2026-09-03.json`.
- Level II durable capture remains separately authorized observer-only work and
  does not feed or block SIM-5.
- L-1 acceptance remains separately authorized when its required sessions are
  mature and does not take or block the SIM-5 pointer.
- Owner-approved L-2 state-cache read-reduction work remains separately
  authorized alongside SIM-5 and does not take or block the SIM-5 pointer.
- Owner-approved SIM-5W read-only web-card work is separately authorized
  alongside SIM-5 under `docs/sim-5w-read-only-sim-web-card-freeze.md` and does
  not take or block the SIM-5 pointer. Its only new authority is the exact
  resolution-only role `atom_v9_sim_web_reader`, the exact web-only credential
  `ATOM_V9_SIM_WEB_READONLY_DATABASE_URL`, migration 032, and the exact file and
  deployment surface frozen there.
- Owner-approved HIST8 corpus work is separately authorized alongside SIM-5
  under `docs/isolated-historical-corpus-eight-instrument-amendment.md`
  (`ATOM-HIST8-CORPUS-AMENDMENT-1`) and does not change, take, or block the
  SIM-5 active-phase pointer. Its only added authority is private schema
  `atom_research_history`, importer role `atom_hist8_importer`, offline-only
  credential `ATOM_HIST8_IMPORT_DATABASE_URL`, and the exact implementation
  allowlist: `research/hist8/schema.sql`, `research/hist8/corpus.py`,
  `research/hist8/calendar_manifest.json`, `tests/test_hist8_corpus.py`, and
  append-only artifacts under `docs/receipts/hist8/`, using only the frozen
  Alpaca SIP, Coinbase Exchange, and Massive `I:COMP` historical sources.
  This entry expressly excepts only that HIST8 scope from the following
  prohibition on new roles/credentials/sources; every other prohibition
  remains unchanged. All HIST8 gates apply. No new service or project and
  no production, V1B, SIM, V9, broker, execution, or model-research authority
  is granted.
- Not authorized: E-2, E-3, E-4, SIM-6 or later simulator phases, Level-II
  mathematical use, V9/family changes except the exact L-2 implementation
  surface, new services/roles/credentials/sources except the exact SIM-5W
  reader role and web-only credential above, broker/account/order authority,
  or live-capital trading.

## What each document is for

- `AGENTS.md` tells the operator how to operate.
- `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` and its effective merged
  amendments control AI roles, Owner operational authority, innovation,
  implementation ownership, review substitution, evidence, and final audits.
- Technical freeze documents tell the operator what the system is legally
authorized to do.
- `PHASES.md` tells it where the program currently is.
- The Owner's explicit approval decides whether the next boundary may be
  crossed through the applicable controlling freeze or amendment.
