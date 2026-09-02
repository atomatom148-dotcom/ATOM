# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md`
3. `FREEZE.md`
4. `SIMULATION_FREEZE.md`
5. `PHASES.md`
6. The freeze and amendments for the active phase

Do not rely on chat memory as authority.

## Precedence

1. Explicit current owner decision
2. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` for role, innovation,
   workflow, evidence, and final-audit authority
3. Latest merged phase-specific freeze/amendment
4. `SIMULATION_FREEZE.md` for simulator work
5. `FREEZE.md`
6. `PHASES.md`
7. Existing implementation

The narrowest applicable restriction controls. Existing code does not override
a freeze.

## Startup statement

Before taking any action, inspect the current `main` commit, confirm each
controlling document exists at that commit, and state:

- controlling role-governance and technical freezes and commit;
- currently authorized phase;
- files and systems permitted to change;
- prohibited changes;
- merge and deployment authority.

If instructions conflict, stop. The narrowest, latest owner-approved freeze
controls. Do not infer permission from previous code, an open PR, or chat
context.

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
- receive review on the final intended head;
- resolve or disposition all material findings;
- be merged by the owner before implementation begins.

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
- `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md` controls AI roles,
  innovation, implementation ownership, evidence, and final audits.
- Freeze documents tell it what is legally authorized.
- `PHASES.md` tells it where the program currently is.
- The owner's explicit approval decides whether the next boundary may be
  crossed.
