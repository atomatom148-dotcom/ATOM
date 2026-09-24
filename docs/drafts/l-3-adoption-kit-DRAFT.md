# L-3 adoption kit (DRAFT — for the Owner or Codex to apply; zero authority)

Claude prepared the L-3 draft (`docs/drafts/l-3-durable-evidence-outbox-amendment-DRAFT.md`, merged in #350) under Amendment 1B. Claude does not edit `FREEZE.md`, `PHASES.md`, or `AGENTS.md` and does not place its own draft at a controlling path; that is the adoption step, which belongs to the Owner (author of record, 1B §2.1) or to Codex on the Owner's instruction. This kit gives the exact text so adoption is one documentation-only PR with no authoring left to do.

## A. Final document — `docs/l-3-durable-evidence-outbox-freeze.md`

Copy the merged draft and replace its first six lines (title through **Prerequisite**) with:

```
# L-3 — Durable evidence outbox and asynchronous drain

**Decision ID:** `ATOM-L-3-DURABLE-EVIDENCE-OUTBOX-FREEZE-1`
**Status:** FROZEN ON OWNER-APPROVED MERGE
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling law for the L-3 phase.
**Author of record:** the Owner, adopting a Claude-prepared draft under Amendment 1B §2.1 (ChatGPT Pro capacity/availability fallback). Draft preparer: Claude. This line records that Owner authorship was used.
**Amends, explicitly:** `FREEZE.md` derived-state worker amendment, sentence *"The live web runtime remains the sole market, forecast, outcome, and evidence writer"* — see §3 and the additive `FREEZE.md` section below. Every other freeze is unchanged.
**Prerequisite (met):** the L-1 acceptance receipt (`docs/l-1-acceptance-receipt-2026-09-24.md`, FAIL) is merged. L-1 stops per its own terms; L-3 is its successor, not a second L-1 mechanism.
```

Keep §0–§7 verbatim. Delete §8 ("Claude's recommendation"); it is not law.

Reduce the draft file to a status marker (precedent: `docs/drafts/g-1-v4c-gamma-challenger-research-contract-DRAFT.md`):

```
# L-3 — Durable evidence outbox: draft

**Status:** SUPERSEDED by `docs/l-3-durable-evidence-outbox-freeze.md` in this PR. This file is intentionally only a status marker so no draft can be mistaken for controlling law.
```

## B. `FREEZE.md` — additive section, inserted immediately before `## Forbidden until explicit freeze amendment`

```
## Durable evidence outbox amendment (L-3)

The controlling contract is `docs/l-3-durable-evidence-outbox-freeze.md`
(`ATOM-L-3-DURABLE-EVIDENCE-OUTBOX-FREEZE-1`). When its gate is on, the
sentence of the derived-state worker amendment above that reads "The live web
runtime remains the sole market, forecast, outcome, and evidence writer" is
superseded by: the live web runtime remains the sole market-data acceptor and
the sole producer of forecast, outcome, and evidence items; those items are
made durable in the evidence outbox table by the web runtime and are written to
the ledger by exactly one drain process holding the evidence runtime-owner
lease. When the gate is off, the web runtime writes the ledger itself as
before. Permanent laws 1–10 are unchanged; the drain process computes nothing,
is not a second brain, and receives no truth credit. This amendment states the
boundary only; implementation, migration `034`, the drain service, and
activation follow the order of work in the controlling contract.
```

The original sentence is not rewritten (additive history, as Amendment 1A did for the base freeze).

## C. `PHASES.md` — new entry under "Evidence ledger operations phases", after the L-1 entry and before its **Rule** line

```
### L-3 — Durable evidence outbox and asynchronous drain (freeze; implementation authorized on merge)

L-1's acceptance receipt (`docs/l-1-acceptance-receipt-2026-09-24.md`) is
FAIL; L-1 stops. L-3 replaces the bounded in-memory outbox with the durable
queue table `public.atom_v9_evidence_outbox` written by `atom-v9-thin` and
drained, strictly in sequence and exactly once, by one Starter background
worker `atom-evidence-writer` running the unchanged ledger logic, under
`docs/l-3-durable-evidence-outbox-freeze.md`. Gated by
`ATOM_EVIDENCE_DURABLE_OUTBOX_ENABLED=1` on both services, disabled by
default. No mathematics, identity, proof, cadence, or evidence change; the
existing runtime role is reused; no tier change. Acceptance: the L-1 bar in
each of the first two complete sessions with the gate on, plus zero sequence
gaps and zero undrained rows older than 60 s at session close. Order of work:
this freeze, one implementation PR, migration `034`, service creation and
deployment per the contract, the acceptance receipt.
```

## D. `AGENTS.md` — "Active phase pointer" section

Insert this bullet before the `- Not authorized:` bullet:

```
- Owner-approved L-3 durable evidence outbox work is separately authorized
  alongside SIM-5 under `docs/l-3-durable-evidence-outbox-freeze.md`
  (`ATOM-L-3-DURABLE-EVIDENCE-OUTBOX-FREEZE-1`) and does not change, take, or
  block the SIM-5 active-phase pointer. Its only new authority is the queue
  table `public.atom_v9_evidence_outbox` in the existing ATOM project via
  migration `034`, one Render background worker `atom-evidence-writer`
  (Starter, `oregon`, `python -m quant.evidence_drain_worker`, Auto-Deploy
  Off) reusing the existing `atom_v9_v4_runtime` role, the gate
  `ATOM_EVIDENCE_DURABLE_OUTBOX_ENABLED`, and the exact implementation
  allowlist `migrations/034_create_v9_evidence_outbox.sql`,
  `quant/evidence_outbox.py`, `quant/evidence_drain_worker.py`,
  `quant/web.py` (composition only), `quant/live_market.py` (acceptance-ready
  source only), and `tests/test_l3_durable_outbox.py`. The Owner is author of
  record under Amendment 1B §2.1; Claude prepared the draft. No mathematics,
  identity, proof, cadence, tier, credential, broker, or trading authority is
  granted.
```

Replace the `- Not authorized:` bullet with:

```
- Not authorized: E-2, E-3, E-4, SIM-6 or later simulator phases, Level-II
  mathematical use, V9/family changes except the exact L-2 implementation
  surface, new services/roles/credentials/sources except the exact SIM-5W
  reader role/web-only credential, the exact `atom-workflows` readiness
  service, and the exact `atom-evidence-writer` drain worker above,
  broker/account/order authority, or live-capital trading.
```

## E. Merge gate for the adoption PR

Documentation-only; five files (`docs/l-3-durable-evidence-outbox-freeze.md` new, the draft reduced to a marker, `FREEZE.md`, `PHASES.md`, `AGENTS.md`). Independent review of the final intended head (Codex: comment `@codex review`; or Copilot; or a human), every P1/P2 dispositioned, zero unresolved material threads, required checks green, Owner merge. Implementation begins only after that merge.
