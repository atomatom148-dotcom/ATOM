# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md`
3. Every amendment to that role-governance freeze present on current `main`;
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md` governs only from its
   Owner-approved merge commit
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
supersedes base §3. The base document remains an immutable historical adoption
record and is not silently rewritten.

A technical freeze cannot supersede governance law on those subjects unless it
explicitly identifies and amends the role-governance decision through its
required authorship, review, Owner-approval, and documentation-only merge
procedure.

### Technical domain

The latest applicable Owner-approved ChatGPT Pro technical freeze or amendment
controls system behavior within its named subject and scope. Among technical
documents addressing the same subject, the explicit later amendment and the
narrowest applicable restriction control. `SIMULATION_FREEZE.md` controls
simulator work, then `FREEZE.md`, then `PHASES.md`, then existing
implementation.

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
boundary, that request is binding direction for ChatGPT Pro to prepare the
required amendment. It does not silently rewrite existing law or authorize
execution across the boundary before the amendment is Owner approved and
merged. Protective stop and rollback authority remains immediate.

### Sole freeze-author continuity

ChatGPT Pro remains the sole freeze and amendment author. If ChatGPT Pro is
unavailable, the Owner and every assigned worker may continue only work already
permitted by applicable freezes. The Owner retains immediate authority to
reprioritize, choose among authorized options, approve or reject merges,
authorize already-permitted deployments, stop, suspend, disable, roll back,
revoke credentials, pause, or terminate programs. A requested boundary change
remains `BLOCKED` until ChatGPT Pro authors the amendment and the Owner approves
it. No substitute freeze author is implied.

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
changed, removed, or replaced only by a separate Owner-approved ChatGPT Pro
amendment that expressly identifies that check before the affected merge.

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

- Active phase: **E-1 — read-only evidence scorecard**.
- Controlling text: `docs/e-1-evidence-scorecard-freeze.md`, including the
  latest merged E-1C and E-1D amendments.
- Authorized order: correct migration `030` under E-1D in PR #274; merge and
  apply it; provision the dedicated `atom_e1_scorecard_reader` credential;
  correct and merge the E-1 implementation in PR #270; then produce and review
  exactly one official E-1 receipt.
- L-1 gate activation and its single deployment are complete. Its read-only
  acceptance receipt remains authorized after the first two complete regular
  XNYS sessions and does not block E-1.
- Not authorized until their own Owner-approved pointer or freeze change:
  E-2, E-3, E-4, migration `031`, SIM-5 implementation, the SIM-5 live
  resolution proof, SIM-6, or later work.

## What each document is for

- `AGENTS.md` tells the operator how to operate.
- `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` and its effective merged
  amendments control AI roles, Owner operational authority, innovation,
  implementation ownership, review substitution, evidence, and final audits.
- Technical freeze documents tell the operator what the system is legally
  authorized to do.
- `PHASES.md` tells it where the program currently is.
- The Owner's explicit approval decides whether the next boundary may be
  crossed through the applicable ChatGPT Pro-authored freeze or amendment.
