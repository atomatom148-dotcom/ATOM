# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md`
3. Every later merged amendment to that role-governance freeze, currently
   `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md`
4. `FREEZE.md`
5. `SIMULATION_FREEZE.md`
6. `PHASES.md`
7. The freeze and amendments for the active phase

Do not rely on chat memory as authority.

## Authority by subject

There is no single linear precedence list across unlike subjects.

### Governance domain

`ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` and its latest explicit merged
amendments control AI and human role boundaries, freeze authorship,
implementation ownership, innovation workflow, review requirements, evidence
governance, and final technical-audit authority.

A technical freeze cannot supersede governance law on those subjects unless it
explicitly identifies and amends the role-governance decision through its
required authorship, review, owner-approval, and documentation-only merge
procedure.

### Technical domain

The latest applicable owner-approved ChatGPT Pro technical freeze or amendment
controls system behavior within its named subject and scope. Among technical
documents addressing the same subject, the explicit later amendment and the
narrowest applicable restriction control. `SIMULATION_FREEZE.md` controls
simulator work, then `FREEZE.md`, then `PHASES.md`, then existing
implementation.

Governance law cannot silently change a technical formula, source, persistence
rule, service boundary, or authority path. Such a change requires an explicit
technical amendment naming the affected law.

### Owner operational authority

A current owner operational instruction controls immediately when it selects or
reprioritizes work already allowed by the applicable freezes; sets cost or
vendor limits; orders a protective stop, suspension, disablement, rollback, or
credential revocation; approves or rejects a merge; or authorizes a deployment
or activation already permitted by the applicable technical freeze.

When the owner requests an action that crosses a frozen governance or technical
boundary, that request is binding direction for ChatGPT Pro to prepare the
required amendment. It does not silently rewrite existing law or authorize
execution across the boundary before the amendment is owner approved and
merged. Protective stop and rollback authority remains immediate.

### Cross-domain conflicts

First determine whether the documents address the same subject. Apply each
within its own subject. Do not infer cross-domain supersession. If the subject
or supersession remains ambiguous, stop as `BLOCKED`.

## Startup statement

Before taking any action, inspect the current `main` commit, confirm each
controlling document exists at that commit, and state:

- controlling role-governance freeze and amendments, technical freezes, and
  commit;
- currently authorized phase;
- files and systems permitted to change;
- prohibited changes;
- merge and deployment authority.

If instructions conflict, stop. The narrowest, latest owner-approved freeze
within the applicable subject controls. Do not infer permission from previous
code, an open PR, or chat context.

## Hard stop

Stop and request owner approval if:

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

Never edit controlling law without explicit owner approval.

A freeze amendment must:

- be documentation-only;
- identify every changed rule;
- receive independent review on the final intended head;
- resolve or disposition all material findings;
- be merged by the owner before implementation begins.

If a named reviewer is unavailable, the owner may designate a substitute
independent reviewer on the final intended head. Unavailability may change the
reviewer; it may not remove the review.

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
- whether owner merge is required.

## External systems

GitHub merge authority does not imply authority to change Supabase, Render,
brokers, market-data services, credentials, billing, or production state.
Each requires explicit authorization from the controlling phase or owner.

## Trading boundary

No broker orders, live trading authority, account actions, position actions, or
money movement without an explicit owner-approved freeze permitting that exact
action.

## Active phase pointer

Update this section only by owner-approved documentation change.

- Active phase: **L-1 — evidence ledger throughput**, implementation and one
  gated deployment of `atom-v9-thin` authorized.
- Controlling text: `docs/l-1-evidence-ledger-throughput-freeze.md`.
- Also controlling for context: `FREEZE.md`, `SIMULATION_FREEZE.md`,
  `PHASES.md`.
- Queued behind L-1 step 3 and a further owner-approved pointer change:
  **E-1 — read-only evidence scorecard**, as amended by the latest merged E-1
  amendment (`docs/e-1-evidence-scorecard-freeze.md`). Not authorized while
  the pointer names L-1: migration `030`, E-1 implementation, any E-1
  receipt, E-2, E-3, E-4.

## What each document is for

- `AGENTS.md` tells the operator how to operate.
- `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` and its merged amendments
  control AI roles, owner operational authority, innovation, implementation
  ownership, review substitution, evidence, and final audits.
- Technical freeze documents tell the operator what the system is legally
  authorized to do.
- `PHASES.md` tells it where the program currently is.
- The owner's explicit approval decides whether the next boundary may be
  crossed through the applicable ChatGPT Pro-authored freeze or amendment.
