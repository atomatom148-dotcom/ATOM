# V-1A Amendment 3D - Gate 2 Startup Failure Disposition

Decision ID: ATOM-V1A-AMENDMENT-3D-GATE2-STARTUP-DISPOSITION-1

Status: PROPOSED. No effect before independent review on the exact final head, all required checks green, zero unresolved material findings, and Owner merge under section 10.

Author: ChatGPT Pro - architecture and freeze authority

Date: 2026-09-09

Repository: atomatom148-dotcom/ATOM

Sole documentation-PR path: docs/v-1a-amendment-3d-gate2-startup-diagnostic.md, mode 100644

Implementation and checklist executor: Codex.

Merge, credentials, infrastructure, diagnostic submission and invocation authority: Owner.

## 1. Decision and limited supersession

Disposition the failed Amendment 3C Gate 2 provenance probe identified in section 2 as a non-consuming startup failure, not successful provenance, scientific evidence or an accepted runtime baseline. Keep Gate 2 blocked. Authorize an ordered, secret-free diagnostic path and, only after independently accepted diagnosis establishes necessity, one minimal correction in one fresh, independently reviewed implementation PR.

This amendment adds no executable file. Its documentation merge authorizes read-only investigation and preparation of the diagnostic command and evidence packet. It does not submit a diagnostic, change service configuration, implement a correction, build, run another provenance probe or advance any later activation gate. Each action requires its separate gate below.

The incorporated law is V-1A, TLS Amendment 1, Amendment 2A, Amendments 3, 3A as adopted by 3B, 3B and 3C, together with the effective governance freezes, FREEZE.md and AGENTS.md. Only these provisions change:

- Amendment 3 sections 2.4 and 5.2, as amended, and Amendment 3C Gate 2 receive the single secret-free diagnostic-command exception in sections 4-5. The diagnostic is not an additional scorecard CLI mode or a provenance probe.
- Amendment 3B section 3 and Amendment 3C sections 1-2 receive the single conditional corrective-integration exception in sections 6-7. Their complete history audit remains mandatory; a second merge is not accepted merely because it is called a repair.
- Amendment 3C Gate 2 cannot be re-entered until section 8's diagnosis-and-correction gate passes. Its original probe approval cannot authorize a retry.

All other rules remain controlling. References to Amendment 3 mean its text as corrected by 3A and 3B. No superseded duration guarantee, command-capacity guarantee or cross-job native-system attestation is reinstated. Nothing here authorizes weakening a frozen startup predicate to make an observed environment pass.

## 2. Exact incident and disposition

The incident identities are fixed:

```text
service       = srv-daa7thgae00c73a2lmn0
service name  = atom-h2d3-benchmark
failed job J0 = job-dagtlu1t0dsc73fouvtg
source E0     = f4d11dfe4ad8622800726107969682df8ae2ddea
build B0      = dep-dagthcu7bikc73c00s3g
M_3C          = f4d11dfe4ad8622800726107969682df8ae2ddea
3C PR         = 335
M_impl        = 73d1f21403144f62a0abf12c3ea3a163e2cd6cd2
original PR   = 333
reviewed head = 7d313a6b8371d1b84b1e0e2bcd72085ccb6241bf
M_3B          = 8e08a58f696459970ec8f991a37e2c914a5bc911
```

The Owner reports that J0 ran E0 from B0, exited status 1 before producing provenance JSON, accessed no database evidence, emitted no seal and performed no protected calculation. The exact failed startup predicate is not yet established. Do not convert an exit code, silent log or hypothesis into a diagnosis.

Authoring-time authenticated reads corroborated the B0-to-E0 deploy association, E0's PR #335 integration, the service's suspended/inert state and disabled automatic deploys/previews. The returned J0 log range contained the launch command and no provenance JSON. Those reads did not return a terminal job object proving exit status 1 or independently establish every no-access assertion. The Owner's incident facts remain the proposed disposition basis; the evidence gate below must substantiate them before diagnostic execution. A deploy object labeled live does not override the separately observed suspended service or establish job success.

Disposition: J0 failed Gate 2. It produced no accepted provenance record, artifact approval, readiness identity, seal or research result. On verification of the stated no-evidence/no-seal execution, it consumed zero scientific looks and creates no sealed-recovery obligation. This neither restores nor increases any existing look budget. Retain the failed job, exact submitted command, source/build identities, logs, terminal evidence and authorization history unchanged in the existing private operational acceptance packet. Do not create a statistical negative receipt for a process that produced none, rewrite J0 as successful, or use its absence of output to certify runtime artifacts.

Track the startup defect as unresolved until independently accepted diagnosis and correction verification exist. Record each later step separately; J0 remains failed even after repair. Missing, truncated or contradictory evidence leaves the relevant fact unverified and the next gate blocked. Discovery of secret exposure, evidence access, a seal or protected output overrides the proposed non-consuming classification and invokes the retained incident/recovery law without suppression or a replacement look.

## 3. Gate D0 - Evidence and containment before diagnostic approval

After lawful 3D merge, Codex may collect existing authenticated, read-only repository and Render control-plane evidence. Do not run an application process to investigate the failed application process under this inspection authority.

Before approving a diagnostic, an independent reviewer must accept:

1. J0's exact submission, source/build association, terminal status and complete available output disposition; its lawful Gate 2 approval; and a source/control-flow review showing why the executed command could not access evidence, seal or calculate on the observed path. Blank logs alone are not proof. Any log/telemetry coverage limit is explicit.
2. Current complete relevant job/seal/receipt and window accounting: J0 and all other relevant jobs terminal, no uncertain submission, no valid seal awaiting recovery, and no unclosed or ambiguously closed no-ref-update window. Do not overwrite a recovery build or merge this amendment through an active freeze window.
3. Both runtime secrets effectively absent from the diagnostic environment, not merely hidden by a service override: ATOM_E1_SCORECARD_READONLY_DATABASE_URL and ATOM_V1B_GITHUB_TOKEN. Inspect existing service/group/blueprint/secret-file/build sources through authorized private controls without printing secret values. No administrative or fallback credential may be supplied to the diagnostic.
4. The exact service remains suspended, at the existing 4c-8g capacity, with automatic deploys and previews off and the unchanged inert base command below. The Owner holds exclusive configuration/build control; no competing writer, deploy, job, shell session or automated retry is admitted.

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"
```

Inspect and preserve B0 before any new build. Render's selected successful artifact must still be B0 for the diagnostic. If it is unavailable, replaced or ambiguous, stop; do not rebuild E0 and call that the same B0. No hidden historical-artifact selector or per-job environment override is presumed.

Merging this documentation changes repository history, not the retained build. For this diagnostic only, E0 is an immutable forensic source reference and need not equal current main. Authenticate E0, B0 and this amendment's actual adoption externally. This exception cannot authorize provenance, readiness, evidence access or a secret-bearing execution from stale main; all such executions retain the exact current-E window predicate.

## 4. Gate D1 - One exact, reviewed secret-free diagnostic

### 4.1 Closed purpose and command review

Codex may prepare one fixed native Render one-off diagnostic command for this incident, retained in the existing private packet rather than installed as the base command or added as a repository module. Its sole purpose is to identify the first failing startup predicate or the startup operation that prevents that predicate from being evaluated. It cannot diagnose by calling the full provenance probe.

Derive the diagnostic from the exact J0 command and E0 startup-guard source. Before submission, freeze its complete command bytes and SHA-256, the source-to-predicate mapping and offline test evidence. Each literal predicate identifier must map to one exact source expression and evaluation position. The map covers only the inline bootstrap and the existing common startup-isolation guard, including prerequisite local operations needed to evaluate them. No operator-supplied expression, arbitrary file/command, environment-selected test, dynamic diagnostic plugin or general-purpose debug shell is allowed.

Retain the exact isolated interpreter switches -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc, frozen CPython/version law and Amendment 3A's non-writing exception-hook prefix. Instrument refusal reporting only. Evaluate in the original dependency/short-circuit order; stop on the first false predicate or failing prerequisite operation, never execute past a failed security guard, replace a failed value, or treat an exception as a true result. Preparing the diagnostic must not change the repository worktree or B0.

Startup-only guard logic may be reproduced in the inline diagnostic only where independent review and offline tests establish semantic equivalence, including the original module/import stage and permitted local side effects. In particular, do not import additional modules before a predicate that observes the original module/path state. An application import may occur only after its original preceding gates pass and only when exact-source review proves that the import and selected guard remain local, non-secret, non-network and non-calculating. Never call provenance_probe_main(), scorecard main(), recovery dispatch, readiness scanning or runtime-provenance/closure measurement. If a needed expression cannot be isolated within this boundary, stop rather than expand the diagnostic.

### 4.2 Only permitted observation and output

The diagnostic may inspect only the already-authorized local startup facts necessary for its frozen predicates: interpreter flags/origins, frozen non-secret version/identity operands, initial and prescribed bootstrap path state, effective environment key names for absence tests, expected local file/type/path and preload/archive facts, and the existing startup-hook/module conditions. It may read a non-secret environment value only where the original predicate already requires that exact operand. It must not read credential values, credential files, arbitrary process memory or another process's environment.

Its application output is exactly one ASCII line in one of these forms:

```text
V1B_STARTUP_DIAGNOSTIC:FALSE:<predicate_id>
V1B_STARTUP_DIAGNOSTIC:ERROR:<operation_id>
V1B_STARTUP_DIAGNOSTIC:NOT_REPRODUCED
```

Identifiers are fixed literals from the independently reviewed mapping, not values obtained from the environment, paths, exceptions or inputs. The angle-bracket notation is never transmitted. FALSE means an evaluated predicate was false; ERROR means a mapped prerequisite operation raised or could not complete, not that a later predicate was evaluated. NOT_REPRODUCED means only that no failure occurred within the approved diagnostic surface in that job. It is not PASS, provenance or readiness. Exit status is 1 for FALSE/ERROR and 0 for NOT_REPRODUCED; exit 0 never advances Gate 2.

No traceback, exception text, raw value, actual path, environment dump, token/URI/verifier or credential digest, database identity readback, component digest, provenance JSON, model count, readiness object, seal, receipt or protected statistic may be emitted. Application stderr remains empty. No filesystem write, cache repair, package installation, subprocess/network call or database connection is authorized; only the prescribed in-memory bootstrap changes and the one diagnostic line are permitted. Render's own launch/lifecycle messages are control-plane evidence, not application diagnostic output. A pre-interpreter/platform failure or missing/truncated line remains inconclusive, not a fabricated predicate result.

This command is an explicit narrow diagnostic exception to the provenance-command registry and its ordinary output contract, not a change to the real probe, normal invocation or recovery commands. It expires after this incident's one accepted diagnostic job terminates. No persistent debug mode or more verbose production failure path is authorized.

### 4.3 Submission gate

An independent reviewer must approve the exact command digest, predicate mapping, equivalence/no-side-effect tests and D0 packet. The Owner must then give affirmative action-time approval identifying J0, the exact service, E0, B0, command digest and unchanged capacity. Codex stops until that approval exists.

Submit the approved diagnostic once through the existing Owner-controlled native Create-job route, with no base resume, build, environment change or command substitution. Require source/build/configuration observations bracketing submission and retain the actual returned diagnostic job ID. A timeout or missing acknowledgement requires job listing/retrieval and retained reconciliation, not another POST. Approval of J0, this amendment or a repair PR is not diagnostic submission approval.

Preserve job termination/output evidence and reverify base suspension. One diagnostic job is authorized, not a retry loop. An inconclusive diagnostic, a changed native startup environment or an unsupported transport leaves the failure undiagnosed and V1B blocked; further active diagnostics require separate documentation-first authority.

## 5. Gate D2 - Diagnose before choosing a correction

Correlate the diagnostic identifier with its frozen source expression, original J0 command, retained B0/E0 facts and relevant permitted control-plane observations. A later native job is not the original process. Same build does not prove identical native startup state. Distinguish a reproduced predicate failure, an explained command/source defect, and a hypothesis or non-reproduction.

Independently accept a diagnosis only when the evidence explains the original failure and supports a specific minimal remedy without protected data. Retain the finding, affected predicate/operation, relevant source locations, causal explanation, reproduction limits and offline regression case. A diagnostic line by itself neither proves the remedy safe nor approves changed runtime bytes.

Select one branch, based on that evidence:

- Existing operational remedy only: the defect is correctable solely by an already authorized 3C service-scoped action. Identify that exact authority, obtain its action-time Owner approval, perform only that action and independently verify its result. No implementation PR is permitted merely to record or work around this branch.
- Implementation correction necessary: independent review establishes the smallest source defect and an unchanged-strength correction within section 6. The Owner approves the exact correction scope before Codex starts implementation.
- Unresolved or outside authority: stop. A new version/dependency, additional accepted startup path/value, provider-layer mutation, secret-delivery change, weakened guard or wider operational remedy requires another narrow documentation-first decision, not an interpretation of this amendment.

A genuine missing security condition must be satisfied; it cannot be removed, allowlisted around or replaced by an Owner assertion. No production probe is used to discover successive fixes.

## 6. Gate D3 - Conditional single corrective implementation PR

Only after D2's accepted diagnosis and action-time Owner scope approval, Codex may open one fresh PR from lawful post-3D main. Its change surface is limited to:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

The permitted delta is the minimal implementation correction for the diagnosed startup defect, its focused regression tests, and only the source-authority/history binding and focused tests necessary to recognize this amendment and this one correction under section 7. No surrounding refactor, formatting sweep, unrelated repair, dependency/certificate/migration change, permanent diagnostic framework or additional file is authorized. The original five-path history-audit surface remains unchanged; this two-path correction subset does not shrink it.

Preserve all frozen versions, mathematical kernels and operations, secret boundaries and startup security requirements. The four real transformed launch commands and their retained text invariants are not changed by implication. If diagnosis requires changing their frozen bytes or other frozen requirements beyond this explicit correction scope, obtain a further documentation-first correction before implementation. Never make the real launcher behave like the diagnostic or print its predicate details with credentials present.

Required regression evidence includes a synthetic/local reproduction of the diagnosed failure; the corrected behavior under the unchanged requirement; retained rejection of genuinely unsafe startup conditions; and no pre-guard secret access, network/evidence read, file write or protected output. Preserve the existing startup, command, history, credential, receipt, one-look, recovery and scientific tests. Do not access production evidence to generate a fixture or use test results to claim provider behavior.

Keep all fixes and review responses within that single PR before merge. It requires independent substantive review on its exact final head, all actual required checks green, zero unresolved P1/P2 or other material findings, and Owner-only merge. Any head change invalidates earlier final-head clearance. A merge does not authorize deployment or another probe.

## 7. Exact corrective lineage; no hidden second integration

This is the sole exception to 3B's single-integration rule and 3C's prohibition on another implementation PR. Preserve PR #333 and M_impl as the original lawful integration; never replace their historical identities with the corrective merge.

Let M_3D be this amendment's actual lawful Owner merge. If the implementation branch is needed, let PR_fix, H_fix and M_fix be the actual sole correction PR, independently reviewed final head and Owner merge. None is invented in this proposal. Require the ordered first-parent history:

```text
M_3B < M_impl < M_3C <= E0 < M_3D < M_fix <= E1
```

E0 equals M_3C for this incident. E1 is the later exact authenticated execution revision, never an alias for E0. Without an implementation correction, omit M_fix and retain exactly one implementation integration, with M_3D <= E1.

The correction's minimal verifier update must authenticate 3D's actual adoption identity, path, mode, blob and raw digest fixed after M_3D exists. Using the existing bounded authenticated authority transport, identify and verify exactly one post-3D corrective PR/integration with the approved two-path scope, actual review/Owner-merge proof and exact source binding. No caller-selected correction SHA, new credential/endpoint family, approval schema or generic "latest implementation" rule is introduced. A source file does not embed its own digest or future merge identity.

Continue the complete history audit from V1A adoption ac85cc9e99ccc499789f3ef79b186768d99fb0d6. The only permitted implementation integrations are exactly [M_impl] on the no-code branch or exactly [M_impl, M_fix] on the corrected branch. Reject every other surface-touching or hidden implementation integration, including direct pushes, renamed changes, reverts and changed-then-restored intervals. Authenticate the corrective PR's complete delta and its reviewed head-to-merge correspondence; a count of two alone is insufficient.

On the corrected branch, use M_fix as the current reviewed implementation tree for path/mode/blob/raw-byte/worktree comparisons. Simultaneously prove that the three other original implementation paths and the closed reused-source set remain unchanged from M_impl, including intervening history. Perform the amended proof at every initial, pre-seal, final and recovery checkpoint. The existing execution-source identity binds E1; no readiness, seal or statistical receipt field/version is added or repurposed. Old source/build identities and any older official receipts remain immutable.

No third implementation integration is authorized. The unchanged no-ref-update window prohibits all merges while active; neither 3D nor a corrective merge bypasses it. Discovery of a pending seal bars replacement deployment and invokes that seal's original recovery contract, never recovery on M_fix or a rebuilt B0.

## 8. Gate D4 - Conditions to return to Amendment 3C Gate 2

No new provenance probe is authorized now. Return to 3C Gate 2 only after independent review accepts the diagnosed cause, completed permitted correction, regression/result evidence, lawful correction merge where required, current no-seal/no-pending-job accounting and continuing secret absence/suspension.

The Owner must separately approve the exact later E1 and secret-free build/probe plan under 3C Gate 2. Bind a new actual successful build B1 to E1 and independently verify the applicable source lineage before any probe submission. B0, diagnostic output and successful offline tests are not a substitute for B1's provenance. Do not label a rebuild as B0 or reuse an unproduced provenance record. No runtime version, artifact or CPU selection may depend on research outcomes.

Only after those gates and action-time Owner approval may one normal provenance probe use the unchanged reviewed probe contract. Another failure stops again; it grants no repeated probe, patch or integration. A success still requires 3C's independent measured-artifact/startup acceptance. It does not install credentials, open an invocation window, prove readiness or authorize a protected calculation.

All remaining 3C gates must then pass in their retained order, with their own action-time approvals. Prior gate approvals do not automatically transfer to E1/B1. No exact or uncertain operational action is repeated merely to recreate its record.

## 9. Preserved boundaries and failure handling

Keep the base suspended/inert throughout this diagnostic and correction workflow. Later secret-free preparation uses only 3C's existing separately approved preparation exception. No secret-bearing base resume, continuous worker, scheduler, cron, polling loop, automatic retry, parallel invocation, broker action, capital use or production-consumer change is authorized.

Both named runtime secrets remain absent through diagnostics and any later secret-free build/probe. This amendment authorizes no credential creation, installation, rotation, restoration, fallback or scope expansion; no database connection, migration, role change, restart, pooler operation or evidence access. Existing 3C single-action budgets and source/scope/redaction rules are unchanged. In particular, unavailable 3B section 7 project-and-reader-scoped pooler disposition still requires verified NOLOGIN, URI absence, an OPEN incident and V1B blocked. No cache wait, old-password test or Owner assertion substitutes for it.

Preserve every V1A/TLS/2A target, horizon, forecaster, benchmark, causal rule, lineage, session convention, original T_amend, earliest boundary, readiness minimum, numerical order, RNG/bootstrap stream, threshold and multiplicity rule. Keep all eight 2A evidence files and active-phase pointers unchanged. Diagnostics, repair history and elapsed time are not scientific inputs.

Preserve seal-before-results, one look per manifest/cell, exact same-seal/source/build/runtime recovery, terminal exclusion, first-complete-receipt retention and nonselective publication. Preserve operational payload version 2 and EXACT_SUBMISSION_OR_CONSUMING_INCIDENT, all stage-correct BLOCKED/INVALID routes, truthful null identities and the existing receipt schemas/filenames. No diagnostic record is a research receipt. Any discovered real seal remains consumed and must be dispositioned under the retained law, even if J0 was initially reported non-consuming.

Protective stopping cancels and verifies the actual one-off job as well as suspending and verifying the base; base suspension alone is not job termination. Preserve original evidence and recovery artifacts. Unexpected credentials, network/evidence access, output, configuration drift, uncertain submission or a broader defect requires stopping and the retained incident route, not improvisation or suppressing the failure.

## 10. Effectivity, final-head acceptance and Codex handoff

The amendment PR must add exactly the sole Markdown file named above at mode 100644, with no other addition, edit, rename or deletion. A PDF rendition is an external reading copy, not a second PR file or controlling source. No existing amendment, root document, implementation, test, dependency, certificate, workflow, configuration, migration or receipt is changed by this documentation PR.

Before Owner merge, require independent substantive review of the exact final head and incorporated affected provisions, with explicit examination of the incident evidence limitations, diagnostic isolation/output contract, narrow second-integration exception and probe embargo. Retain the actual final head, file blob/raw digest, review identity/time, findings dispositions and actual required check names/conclusions. Every required check must be green on the applicable exact head/base; missing, pending, skipped, neutral, cancelled or failed is not green. No unresolved P1/P2 or other material finding may remain. Recheck head, relevant history, checks, findings and absence/lawful closure of any active freeze window immediately before merge. Only the Owner may merge.

After lawful merge, Codex's only forward sequence is:

```text
D0 evidence and containment
-> D1 independent exact-command review + Owner diagnostic approval
-> one secret-free diagnostic; retain truthful output and termination
-> D2 independent diagnosis + Owner remedy-scope approval
-> existing authorized operational remedy OR one D3 correction PR
-> independent correction verification; Owner-only merge if applicable
-> D4 independent return-gate review
-> separate Owner authorization under 3C Gate 2
```

Stop at every action-time Owner gate and whenever a prerequisite is missing. No protected V1B calculation begins under this amendment. This proposal asserts neither diagnosis, independent approval, correction, PR creation/merge nor permission to run another provenance probe.

## Verification anchors

Controlling repository sources are the existing V-1A/TLS/2A and Amendment 3/3A/3B/3C documents, inspected at E0; PR #333 and its retained original integration; and PR #335's E0 integration of 3C. Authoring-time operational reads were Render get_deploy(B0), get_service(service) and list_logs(J0) for 2026-09-09 22:00:00Z through 23:00:00Z. Their observations and limits are stated in section 2; they are not a future action-time acceptance packet.

Platform reference: Render, One-Off Jobs, https://render.com/docs/one-off-jobs, consulted 2026-09-09. Its documented latest-successful-build/environment snapshot and independent job lifecycle support the build-selection and protective-stop requirements; they do not attest identical native startup across jobs. Python's 3.14 command-line documentation, https://docs.python.org/3.14/using/cmdline.html, is supporting context for isolated startup switches, not authority to change the frozen CPython 3.14.3 version or any retained guard.
