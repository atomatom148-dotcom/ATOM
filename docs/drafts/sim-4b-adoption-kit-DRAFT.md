# SIM-4B adoption kit (DRAFT — for the Owner or Codex to apply; zero authority)

Claude prepared the SIM-4B draft (`docs/drafts/sim-4b-batched-terminalization-amendment-DRAFT.md`, merged in #350) under Amendment 1B. Claude does not edit `PHASES.md` or `AGENTS.md` and does not place its own draft at a controlling path; that adoption step belongs to the Owner (author of record, 1B §2.1) or to Codex on the Owner's instruction. This kit gives the exact text.

## A. Final document — `docs/sim-4b-batched-terminalization-amendment.md`

Copy the merged draft and replace its first four lines (title through **Amends, explicitly**) with:

```
# SIM-4B — Batched persistence of non-entering terminal decisions

**Decision ID:** `ATOM-SIM-4B-BATCHED-TERMINALIZATION-AMENDMENT-1`
**Status:** FROZEN ON OWNER-APPROVED MERGE
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling simulator law within the SIM-5 active phase.
**Author of record:** the Owner, adopting a Claude-prepared draft under Amendment 1B §2.1 (ChatGPT Pro capacity/availability fallback). Draft preparer: Claude. This line records that Owner authorship was used.
**Subject:** SIM-4 terminal-entry persistence throughput. Simulator work; `SIMULATION_FREEZE.md` and the merged SIM-3A/SIM-4A documents control everything this amendment does not name.
**Amends, explicitly:** `docs/sim-3a-final-runtime-fence-addendum.md` §2, the list beginning *"For each terminal decision, on that same owner session: 1. begin the database transaction; …"*, which now applies per terminal decision or per bounded same-horizon batch of non-entering terminal decisions as frozen in §1 below. Every other SIM rule — the two-second window, quote predicates, terminal precedence, existing-terminal idempotency, restart-gap and late-intent routing, the admission fence, single runtime ownership, one open position per horizon, append-only evidence, SIM-5 resolution — is unchanged.
```

Keep §0–§4 verbatim. Delete §5 ("Claude's recommendation"); it is not law.

Reduce the draft file to a status marker:

```
# SIM-4B — Batched terminalization: draft

**Status:** SUPERSEDED by `docs/sim-4b-batched-terminalization-amendment.md` in this PR. This file is intentionally only a status marker so no draft can be mistaken for controlling law.
```

## B. `PHASES.md` — one line appended to the "Paper simulator phases" introduction paragraph (after "…no later phase may be implemented early.")

```
SIM-4B (`docs/sim-4b-batched-terminalization-amendment.md`) amends SIM-4
terminal persistence throughput inside the SIM-5 phase; it authorizes no
later simulator phase.
```

## C. `AGENTS.md` — "Active phase pointer" section, new bullet before `- Not authorized:`

```
- Owner-approved SIM-4B batched terminalization is separately authorized
  alongside SIM-5 under `docs/sim-4b-batched-terminalization-amendment.md`
  (`ATOM-SIM-4B-BATCHED-TERMINALIZATION-AMENDMENT-1`) and does not change,
  take, or block the SIM-5 active-phase pointer. Its only authority is the
  exact implementation allowlist `quant/v9_sim4_worker.py`,
  `quant/v9_sim4_entry.py`, `tests/test_v9_sim4_entry.py`, and
  `tests/test_v9_sim4b_batched_terminalization.py`, deployed to the existing
  `atom-v9-sim4-worker` only. No migration, schema, role, credential, contract,
  hash, canonicalization, SIM-5, SIM-6, web, or production change. The Owner is
  author of record under Amendment 1B §2.1; Claude prepared the draft.
```

No change to the `- Not authorized:` bullet (no new service, role, credential, or source).

## D. Merge gate for the adoption PR

Documentation-only; four files (`docs/sim-4b-batched-terminalization-amendment.md` new, the draft reduced to a marker, `PHASES.md`, `AGENTS.md`). Independent review of the final intended head, every P1/P2 dispositioned, zero unresolved material threads, required checks green, Owner merge. Implementation begins only after that merge. If both kits are adopted, apply them in one PR or in sequence; the `AGENTS.md` bullets are independent and both go before `- Not authorized:`.
