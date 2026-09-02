# ATOM Operating Authority

## Mandatory reading order

Before planning, editing, running migrations, opening PRs, deploying, or
changing external services, read completely:

1. `AGENTS.md`
2. `FREEZE.md`
3. `SIMULATION_FREEZE.md`
4. `PHASES.md`
5. The freeze and amendments for the active phase

Do not rely on chat memory as authority.

## Precedence

1. Explicit current owner decision
2. Latest merged phase-specific freeze/amendment
3. `SIMULATION_FREEZE.md` for simulator work
4. `FREEZE.md`
5. `PHASES.md`
6. Existing implementation

The narrowest applicable restriction controls. Existing code does not override
a freeze.

## Startup statement

Before taking any action, inspect the current `main` commit, confirm each
controlling document exists at that commit, and state:

- controlling freeze and commit;
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

- Active phase: **E-1 — read-only evidence scorecard**, freeze only.
- Controlling text: `docs/e-1-evidence-scorecard-freeze.md`, as amended by the
  latest merged E-1 amendment.
- Also controlling for context: `FREEZE.md`, `SIMULATION_FREEZE.md`,
  `PHASES.md`.
- Not authorized until their own approved phases: migration `029`, E-1
  implementation, any E-1 receipt, E-2, E-3, E-4.

## What each document is for

- `AGENTS.md` tells the operator how to operate.
- Freeze documents tell it what is legally authorized.
- `PHASES.md` tells it where the program currently is.
- The owner's explicit approval decides whether the next boundary may be
  crossed.
