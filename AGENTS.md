# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md`
3. Every amendment to that role-governance freeze present on current `main`;
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md` and
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B.md` govern only from their
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
base freeze and Amendment 1A. The base documents remain immutable historical
adoption records and are not silently rewritten.

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

### Claude implementation delegation

Codex remains the default implementation owner. Claude may be named as the sole
implementation owner for one exact job when ChatGPT Pro or the Owner issues a
job card beneath controlling law naming Claude in that role. The job card must
state the controlling freeze, exact scope, permitted and prohibited actions,
required tests and evidence, PASS/FAIL/INVALID/BLOCKED rules, stop condition,
and receipt. Claude receives no general implementation authority from one job.

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

- Active phase: **Level II durable depth capture — implementation**.
- Controlling text: `ATOM_LEVEL2_DEPTH_CAPTURE_FREEZE_1.md` at the Owner-approved
  merge of PR #288, plus `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B.md` for
  implementation-owner delegation.
- Named implementation owner: **Claude** for this Level II capture job only.
- Authorized order: implement the smallest default-off observer-only durable
  capture path and one isolated append-only table; add only the required
  least-privilege migration, tests, deterministic receipt/health proof, and
  activation gate; final-head independent review; every required check green;
  Owner merge; then apply the approved migration and activate only the Level II
  capture gate.
- E-1 remains preserved and may resume after this bounded Level II capture job;
  no E-1 mathematics, scorecard statistics, reader roles, or evidence semantics
  may change during this phase.
- L-1 remains unchanged. Its read-only acceptance receipt remains authorized
  when its required session evidence is mature and does not block this bounded
  Level II capture job.
- Not authorized by this pointer: E-2, E-3, E-4, drift-adjusted benchmarking,
  S3, Q5 changes, family/V9/SIM use of Level II, broker/trading authority,
  additional market-data sources, new services, or unrelated credentials.

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
