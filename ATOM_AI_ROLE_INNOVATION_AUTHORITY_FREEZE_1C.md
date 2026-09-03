# ATOM AI Role, Innovation, and Improvement Authority Freeze — Amendment 1C

**Decision ID:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1C`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling governance law.  
**Author:** ChatGPT Pro, ATOM Chief Architect and Freeze Custodian  
**Amends:** `ATOM-AI-ROLE-AUTHORITY-FREEZE-1B` implementation-owner continuity only  
**Technical authority:** none by itself

## 0. Owner objective

The Owner requires authorized implementation work to continue when Codex is unavailable, capacity-limited, usage-limited, disconnected, or otherwise unable to begin or continue an already-authorized implementation job. The purpose of this amendment is continuity only. It does not widen any technical freeze, phase, repository surface, service, credential, database, source, broker, or trading authority.

## 1. Default owner and automatic fallback

Codex remains ATOM's default implementation owner.

When Codex is unavailable, capacity-limited, usage-limited, disconnected, or otherwise unable to begin or continue an already-authorized implementation job, Claude automatically becomes implementation owner for that exact job without a new technical freeze or per-job delegation amendment, provided all of the following are already true:

1. a controlling technical freeze or merged phase document authorizes the job;
2. the job's exact implementation surface, prohibited actions, required tests, evidence, stop conditions, and merge/deployment gates are already defined;
3. Claude can perform the work without crossing or reinterpreting any frozen boundary; and
4. no different implementation owner is simultaneously active on the same job.

The fallback is triggered by objective unavailability evidence, including an explicit usage-limit/capacity response, failed invocation caused by service unavailability, or an Owner/ChatGPT Pro determination that Codex cannot presently execute the job. No ceremonial waiting period is required.

## 2. Authority inherited by Claude

Claude inherits only the implementation authority already granted for the exact job. Claude may:

- edit only the files and systems already authorized;
- implement the frozen contract;
- run required tests and deterministic verification;
- commit and push the implementation branch;
- open and update the implementation PR;
- correct review findings within the existing frozen scope; and
- prepare the deployment or migration artifacts expressly authorized by the controlling phase.

Claude may not:

- author, amend, supersede, or reinterpret controlling law;
- widen the phase or job;
- change frozen mathematics, source identity, timestamp contracts, persistence semantics, instrument scope, credentials, services, roles, databases, or broker authority unless the controlling technical freeze already authorizes that exact change;
- add opportunistic cleanup or refactors;
- waive required checks;
- approve its own implementation as the sole independent final-head reviewer; or
- proceed through an ambiguity that would otherwise be `BLOCKED`.

## 3. One owner per job; no duplicate implementation

One implementation job still has exactly one implementation owner at a time.

Once Claude validly assumes a job under this fallback, Claude remains implementation owner through completion of that exact job unless the Owner explicitly transfers ownership. Codex becoming available again does not invalidate or duplicate Claude's in-scope work and does not create a second implementation branch by default.

If Codex had already materially begun implementation before becoming unavailable, the Owner or ChatGPT Pro must choose one branch/owner before work resumes. Parallel competing implementations are prohibited unless separately authorized.

## 4. Review and merge gates unchanged

When Claude implements, Claude may not be the sole final-head reviewer. Independent final-head review remains mandatory from at least one of Codex, Copilot's pull-request reviewer, a qualified human reviewer, or the Owner as permitted by controlling governance.

Every required check must be green. Every material P1 and P2 finding must be resolved or explicitly dispositioned. Material review threads must be zero. Owner merge authority remains unchanged.

Implementation fallback does not imply migration, deployment, activation, credential, Supabase, Render, broker, or capital authority. Those actions occur only when separately authorized by the applicable technical freeze and Owner instruction.

## 5. Freeze and architecture authority unchanged

ChatGPT Pro remains the normal architecture, phase-planning, freeze/amendment, and final technical-audit authority. Amendment 1B's delegated-drafting and Owner-author-of-record fallback remain unchanged.

Claude gains no equal governance authority from this amendment. Claude implementation work remains subordinate to all controlling freezes, amendments, job cards, evidence rules, preregistrations, and Owner decisions.

## 6. Effect on Amendment 1B

Amendment 1B §1 is superseded only to the extent that Claude no longer requires a fresh explicit per-job naming event when Codex is objectively unavailable for an already-authorized implementation job. All other 1B restrictions remain controlling.

The automatic fallback never creates authority for a job that is not already technically authorized.

## 7. Immediate continuity rule

On this amendment's Owner-approved merge, any currently authorized implementation job that is blocked solely because Codex is usage-limited or unavailable may transfer immediately to Claude under Sections 1–4 without another technical amendment.

This includes the then-active SIM-5 implementation only if its controlling SIM-5 freeze is already merged and all work remains inside its exact authorized implementation surface.

## 8. Frozen conclusion

> Codex remains the default implementation engineer. If Codex cannot presently execute an already-authorized job, Claude automatically becomes implementation owner for that exact frozen job and may carry it through implementation, tests, PR preparation, and in-scope review repairs. Claude receives no new architecture or freeze authority, cannot widen scope, cannot self-approve, and cannot bypass checks. One owner remains responsible for one job through completion unless the Owner explicitly transfers it.

**END — ATOM-AI-ROLE-AUTHORITY-FREEZE-1C**
