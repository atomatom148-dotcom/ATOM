# ATOM AI Role, Innovation, and Improvement Authority Freeze — Amendment 1A

**Decision ID:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1A`  
**Status:** PROPOSED — DOCUMENTATION ONLY — AWAITING OWNER APPROVAL  
**Effective only when:** owner approved and merged  
**Author:** ChatGPT Pro, ATOM Chief Architect and Freeze Custodian  
**Amends:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1` version 1.0  
**Base adoption:** pull request `#278`, merged at `09b7922be7e19d11dd8816f3d3cc9e70f736509d`  
**Technical authority:** none

---

## 0. Nature and Limits

This is a narrow governance clarification authored after read-only adversarial review of the merged role freeze.

It changes only:

1. how current Owner instructions operate within and across frozen boundaries;
2. how governance, technical, and operational authority interact without circular precedence; and
3. what final-head review substitution means when a named reviewer is unavailable.

It does not change any ATOM, V9, SIM, SEI, Horizon, historical replay, Parent/Child, market-data, database, persistence, source, mathematical, risk, broker, execution, Render, Supabase, or production behavior.

No code, migration, external-system action, environment change, active-phase change, deployment, restart, or data mutation is authorized by this amendment.

Every provision of `ATOM-AI-ROLE-AUTHORITY-FREEZE-1` not expressly amended below remains in force.

---

## 1. Findings Accepted

### F1 — Owner operational authority required clarification

The merged `AGENTS.md` placed an explicit current Owner operational instruction at position seven in one linear precedence list and limited it to operating within the first six items. That wording correctly prevented an informal instruction from silently rewriting frozen law, but it could also be read as unnecessarily reducing the Owner's immediate day-to-day operating authority.

### F2 — Linear precedence created circularity

The merged list separately named:

1. any latest applicable Owner-approved ChatGPT Pro freeze; and
2. the role-governance freeze itself.

Because the role-governance freeze also satisfies item one, a later technical freeze could be misread as superseding role-governance law even when it addressed a different subject. That conflicts with the protected-boundary and subject-matter rules already contained in the role freeze.

### F3 — Review substitution required a hard floor

The adoption receipt stated that a Codex review request could be dispositioned by the Owner if Codex was unavailable. Read alone, that could be misread as allowing review to be waived. The intended law is substitution of reviewer, not removal of final-head review.

---

## 2. Owner Operational Authority

The Owner remains the highest human authority over ATOM's objective, priority, budget, vendor selection, risk tolerance, stop or suspension decisions, merge, activation, and capital.

A current Owner operational instruction is immediately controlling when it:

- selects or reprioritizes work already permitted by the applicable freezes;
- chooses among already-authorized implementation or operational options;
- sets or limits cost and vendor use;
- orders a protective stop, suspension, disablement, rollback, or credential revocation;
- approves or rejects a merge;
- authorizes a deployment or activation already permitted by the applicable technical freeze; or
- rejects, pauses, or permanently ends a program.

The Owner's current word is therefore not treated as merely the seventh item in a general hierarchy.

When a current Owner instruction requests an action that would cross or change a frozen governance or technical boundary:

1. the instruction is a binding Owner objective for ChatGPT Pro to prepare the necessary amendment or superseding freeze;
2. it does not silently rewrite the existing document;
3. it does not authorize implementation, migration, deployment, source connection, authority expansion, or production mutation across that boundary before the amendment is Owner approved and merged; and
4. protective stop and rollback authority remains immediate under §17 of the base freeze.

This mechanism does not reduce Owner sovereignty. It is the Owner-selected method for preserving exact law, reviewability, and audit lineage while allowing the Owner to change direction at any time.

---

## 3. Subject-Matter Authority — Replacement for Base §3

Base §3, **Authority Hierarchy**, is superseded by this section.

There is no single linear precedence list across unlike subjects. Authority is resolved by subject.

### 3.1 Governance domain

`ATOM-AI-ROLE-AUTHORITY-FREEZE-1`, this amendment, and any later explicit amendment to that decision control:

- AI and human role boundaries;
- freeze authorship;
- implementation ownership;
- innovation and improvement workflow;
- review requirements and reviewer substitution;
- evidence and receipt governance;
- final technical-audit authority; and
- the amendment procedure for this governance law.

A technical freeze cannot amend, supersede, or weaken this governance domain unless it explicitly identifies the role-governance decision being amended and follows its ChatGPT Pro authorship, independent review, Owner approval, and documentation-only merge procedure.

### 3.2 Technical domain

The latest applicable Owner-approved ChatGPT Pro technical freeze or amendment controls the system behavior within its named subject and scope.

Among technical documents addressing the same subject:

1. the explicit later amendment controls the clause it supersedes;
2. the narrowest applicable restriction controls;
3. `SIMULATION_FREEZE.md` controls simulator work;
4. `FREEZE.md` controls the root ATOM V9 technical boundary;
5. `PHASES.md` controls the phase map where it does not conflict with a freeze; and
6. existing implementation is last and never overrides law.

A governance freeze cannot silently alter a technical formula, source, persistence rule, service boundary, or authority path merely because it is newer. Such a change requires an explicit technical amendment naming the affected technical law.

### 3.3 Operational domain

A current Owner operational instruction controls immediately within all applicable governance and technical freezes as specified in §2 of this amendment.

ChatGPT Pro phase authorizations, Codex implementation contracts, specialist role cards, and operational runbooks operate beneath those applicable freezes and the Owner's current permitted instruction.

### 3.4 Cross-domain conflict rule

When documents appear to conflict:

- first determine whether they address the same subject;
- apply each document within its own subject;
- do not treat a later document in another subject as implicit supersession;
- require explicit amendment language for a protected-boundary change; and
- stop as `BLOCKED` if the subject or supersession remains ambiguous.

This closes the circularity between a general reference to Owner-approved freezes and the separately named role-governance law.

---

## 4. Final-Head Review — Amendment to Base §16 and §20

The base law's final-head review requirement remains mandatory.

### 4.1 Review cannot be waived for unavailability

If a named reviewer such as Codex is unavailable, at usage limit, disconnected, or otherwise unable to complete review, the Owner may designate another independent reviewer for the final intended head.

Unavailability may change the reviewer. It may not remove the review.

### 4.2 Minimum valid review

Before merge, the final intended head must have:

- at least one completed independent read-only review appropriate to the change;
- every P1 and P2 finding resolved, corrected, or explicitly dispositioned;
- zero unresolved material review threads; and
- all required checks green or an exact Owner-approved check substitution expressly allowed by the controlling freeze.

For a documentation-only freeze or amendment, an acceptable independent reviewer may be Claude, Codex, Copilot's pull-request reviewer, or a designated qualified human reviewer. ChatGPT Pro remains the author and final technical auditor and cannot be the sole independent reviewer of its own freeze text.

For implementation work, the implementation owner cannot be the sole independent reviewer of the same final head.

### 4.3 Owner authority preserved

The Owner remains the final merge approver and may select the substitute reviewer. The Owner may not convert reviewer unavailability into a silent no-review path unless a later Owner-approved ChatGPT Pro amendment explicitly changes this law.

---

## 5. Receipt Clarification

The `review_state` text in `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1_RECEIPT.json` is superseded.

The correct permanent interpretation is:

> Final-head independent review is required. If a named reviewer is unavailable, the Owner may designate a substitute reviewer on the final intended head; reviewer unavailability is not a review waiver.

For the original adoption in pull request `#278`, the recorded evidence is:

- final intended head: `a7b26defb92c55197d50605580041e62c678cc23`;
- CircleCI test: success;
- GitHub Analyze: success;
- SonarCloud quality gate: success with zero new issues;
- Copilot final-head review: approval recommended;
- prior receipt finding: corrected;
- unresolved material threads: zero; and
- merge commit on `main`: `09b7922be7e19d11dd8816f3d3cc9e70f736509d`.

The original adoption therefore remains valid. This amendment clarifies its governing interpretation rather than reversing it.

---

## 6. Required Repository Integration

When this amendment is Owner approved, its documentation-only PR may change exactly:

1. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md` — this amendment;
2. `AGENTS.md` — replace the circular linear precedence section with the subject-matter authority model and add this amendment to mandatory reading;
3. `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1_RECEIPT.json` — record the completed adoption review and this amendment; and
4. `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A_RECEIPT.json` — record amendment identity, review, and precedence effect.

No other file or system may change in this correction.

---

## 7. Merge Gate

This amendment is documentation only.

Before merge:

1. review the final intended head independently;
2. resolve or disposition every P1 and P2 finding;
3. confirm zero unresolved material threads;
4. confirm all required checks are green;
5. obtain explicit Owner approval to merge; and
6. merge without runtime deployment.

No implementation, migration, Render action, Supabase action, source connection, environment change, service restart, evidence write, broker action, or production mutation accompanies this amendment.

---

## 8. Frozen Conclusion

> The Owner's current word controls objectives, priorities, protective actions, merges, and every operation already permitted by existing law. A request to cross a frozen boundary is binding direction to prepare a ChatGPT Pro amendment, but execution waits for the Owner-approved merged amendment. Governance law controls governance subjects. Technical freezes control technical subjects. Neither silently supersedes the other. A named reviewer may be replaced when unavailable, but final-head independent review may not be removed.

**END — ATOM-AI-ROLE-AUTHORITY-FREEZE-1A**
