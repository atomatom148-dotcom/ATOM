# ATOM AI Role, Innovation, and Improvement Authority Freeze — Amendment 1A

**Decision ID:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1A`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Before merge this is proposed final text and grants no authority. At its Owner-approved merge commit it becomes controlling law.  
**Author:** ChatGPT Pro, ATOM Chief Architect and Freeze Custodian  
**Amends:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1` version 1.0  
**Base adoption:** pull request `#278`, merged at `09b7922be7e19d11dd8816f3d3cc9e70f736509d`  
**Technical authority:** none

---

## 0. Nature and Limits

This is a narrow governance clarification authored after read-only adversarial review of the merged role freeze.

It changes only:

1. how current Owner instructions operate within and across frozen boundaries;
2. how governance, technical, and operational authority interact without circular precedence;
3. what final-head review substitution means when a named reviewer is unavailable;
4. the rule for required checks, which remain mandatory and receive no substitution path under this amendment; and
5. the continuity rule when the sole freeze author is unavailable.

It does not change any ATOM, V9, SIM, SEI, Horizon, historical replay, Parent/Child, market-data, database, persistence, source, mathematical, risk, broker, execution, Render, Supabase, or production behavior.

No code, migration, external-system action, environment change, active-phase change, deployment, restart, or data mutation is authorized by this amendment.

Every provision of `ATOM-AI-ROLE-AUTHORITY-FREEZE-1` not expressly amended below remains in force.

---

## 1. Findings and Final Dispositions

### F1 — Owner operational authority required clarification

Accepted and corrected. The merged `AGENTS.md` placed an explicit current Owner operational instruction at position seven in one linear precedence list and limited it to operating within the first six items. That wording correctly prevented an informal instruction from silently rewriting frozen law, but it could also be read as unnecessarily reducing the Owner's immediate day-to-day operating authority.

### F2 — Linear precedence created circularity

Accepted and corrected. The merged list separately named any latest applicable Owner-approved ChatGPT Pro freeze and the role-governance freeze itself. Because the role-governance freeze also satisfied the first item, a later technical freeze could be misread as superseding governance law even when it addressed a different subject.

### F3 — Reviewer unavailability required a substitution rule

Accepted and corrected. An unavailable named reviewer may be replaced by an Owner-designated independent reviewer on the final intended head. Reviewer unavailability cannot remove final-head review.

### F4 — Required-check substitution was outside scope

Accepted and corrected. This amendment creates no required-check substitution or waiver. Every required check must be green. Changing, removing, or replacing a required check requires a separate Owner-approved ChatGPT Pro amendment before merge.

### F5 — Amendment status had to remain accurate after merge

Accepted and corrected. This document and its receipt use a self-executing effectivity rule: they grant no authority before merge and become frozen at the Owner-approved merge commit. They do not remain marked `PROPOSED` or `PENDING` after entering `main`.

### F6 — Sole freeze-author unavailability

Accepted as a material continuity risk and intentionally dispositioned without creating a substitute author. ChatGPT Pro remains the sole freeze author under the Owner's explicit decision. If ChatGPT Pro is unavailable, boundary-crossing change remains `BLOCKED`; the Owner retains all operations already permitted by existing law and all immediate protective stop, suspension, rollback, rejection, and termination authority.

### F7 — Operator summary and reviewer-finding ranking

Accepted and corrected. `AGENTS.md` now includes the Owner's authority to choose among already-authorized options and to reject, pause, or permanently end a program. Claude, specialist, and reviewer findings remain above implementation convenience and tool defaults, while remaining advisory beneath applicable freezes and Owner authority.

### F8 — In-place edit to the base freeze

Dispositioned without changing the base document. The base freeze remains an immutable historical adoption record. This amendment explicitly supersedes base §3, and `AGENTS.md` requires reading merged amendments and states that base §3 is superseded when this amendment is effective. The historical base text is not silently rewritten.

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

### 2.1 Sole freeze-author continuity

ChatGPT Pro remains the sole author of architecture freezes, amendments, superseding decisions, and final freeze reconciliations.

If ChatGPT Pro is temporarily unavailable:

- the Owner may continue every action already permitted by applicable governance and technical freezes;
- the Owner may reprioritize, choose among already-authorized options, approve or reject merges, authorize already-permitted deployments, stop, suspend, disable, roll back, revoke credentials, pause, or terminate programs;
- Claude, Codex, Copilot Max, specialists, and automated systems may continue only already-authorized work within their frozen roles; and
- every requested governance or technical boundary change remains `BLOCKED` until ChatGPT Pro authors the required amendment and the Owner approves it.

No substitute freeze author is authorized by this amendment. This is an intentional single-author continuity constraint, not an omission or an implied transfer of authority.

---

## 3. Subject-Matter Authority — Replacement for Base §3

Base §3, **Authority Hierarchy**, is superseded by this section when this amendment becomes effective.

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

The latest applicable Owner-approved ChatGPT Pro technical freeze or amendment controls system behavior within its named subject and scope.

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

Documented Claude, specialist, and reviewer findings rank above implementation convenience, tool defaults, and informal suggestions. They remain advisory: they cannot override an applicable freeze, expand an authorized scope, or replace the Owner's final authority.

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

### 4.2 Minimum valid review and checks

Before merge, the final intended head must have:

- at least one completed independent read-only review appropriate to the change;
- every P1 and P2 finding resolved, corrected, or explicitly dispositioned;
- zero unresolved material review threads; and
- every required check green.

This amendment authorizes no check waiver, substitution, or bypass. A required check may be changed, removed, or replaced only by a separate Owner-approved ChatGPT Pro amendment that expressly identifies that check before the affected merge.

For a documentation-only freeze or amendment, an acceptable independent reviewer may be Claude, Codex, Copilot's pull-request reviewer, or a designated qualified human reviewer. ChatGPT Pro remains the author and final technical auditor and cannot be the sole independent reviewer of its own freeze text.

For implementation work, the implementation owner cannot be the sole independent reviewer of the same final head.

### 4.3 Owner authority preserved

The Owner remains the final merge approver and may select the substitute reviewer. The Owner may not convert reviewer unavailability into a silent no-review path unless a later Owner-approved ChatGPT Pro amendment explicitly changes this law.

---

## 5. Receipt Clarification

The `review_state` text in `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1_RECEIPT.json` is superseded.

The correct permanent interpretation is:

> Final-head independent review and every required green check are mandatory. If a named reviewer is unavailable, the Owner may designate a substitute reviewer on the final intended head; reviewer unavailability is not a review waiver and does not create a check waiver.

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

This documentation-only pull request may change exactly:

1. `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A.md` — this amendment;
2. `AGENTS.md` — subject-matter authority, complete Owner operational authority, sole-author continuity, amendment reading order, reviewer-finding ranking, and strict review/check rules;
3. `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1_RECEIPT.json` — completed adoption review and amendment/effectivity clarification; and
4. `docs/ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1A_RECEIPT.json` — amendment identity, findings, effectivity, review requirements, and precedence effect.

The base freeze file is intentionally not edited. Amendment history remains additive rather than silently rewriting the adopted source document.

No other file or system may change in this correction.

---

## 7. Merge Gate

This amendment is documentation only.

Before merge:

1. review the final intended head independently;
2. resolve or disposition every P1 and P2 finding;
3. confirm zero unresolved material threads;
4. confirm every required check is green;
5. obtain explicit Owner approval to merge; and
6. merge without runtime deployment.

No check substitution is authorized. No implementation, migration, Render action, Supabase action, source connection, environment change, service restart, evidence write, broker action, or production mutation accompanies this amendment.

---

## 8. Frozen Conclusion

> The Owner's current word controls objectives, priorities, authorized choices, protective actions, merges, and every operation already permitted by existing law. A request to cross a frozen boundary is binding direction to prepare a ChatGPT Pro amendment, but execution waits for the Owner-approved merged amendment. Governance law controls governance subjects. Technical freezes control technical subjects. Neither silently supersedes the other. A named reviewer may be replaced when unavailable, but final-head independent review and required green checks may not be removed. ChatGPT Pro remains the sole freeze author; if unavailable, boundary-crossing change is intentionally blocked while all already-authorized and protective Owner powers remain available.

**END — ATOM-AI-ROLE-AUTHORITY-FREEZE-1A**