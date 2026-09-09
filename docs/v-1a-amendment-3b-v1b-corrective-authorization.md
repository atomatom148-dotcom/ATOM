V-1A Amendment 3B — V1B Corrective Authorization

Decision ID: ATOM-V1A-AMENDMENT-3B-V1B-CORRECTIVE-AUTHORIZATION-1
Status: PROPOSED. No implementation or operational authority before the gates in §9 and the Owner’s merge.
Author: ChatGPT Pro — architecture and freeze authority
Date: 2026-09-08
Repository: atomatom148-dotcom/ATOM
Inspected main: 7a1356e9106c4d28086368d239d00125b05be1ac — an inspection baseline, not an execution authorization.
Sole documentation-PR path: docs/v-1a-amendment-3b-v1b-corrective-authorization.md
Implementation owner: Codex, in one fresh, separate implementation PR after this amendment becomes effective.
Merge, credential, infrastructure, disruption and expenditure authority: Owner.

1. Decision and exact scope

This amendment dispositions the PR #326 review-order incident prospectively, restores a valid documentation-first implementation path, enforces a single implementation integration, and replaces three unavailable platform-proof contracts. It preserves native one-off execution; it does not authorize a continuously running V1B service.

The incorporated technical law is docs/v-1a-volatility-first-freeze.md, docs/v-1a-amendment-1-tls-trust-anchor.md, docs/v-1a-amendment-2a-tiered-readiness-boundaries.md, docs/v-1a-amendment-3-v1b-operational-prerequisites.md, and the exact Amendment 3A bytes identified in §2. Role governance remains ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1.md and its effective amendments, together with AGENTS.md.

Only these provisions are replaced or clarified:

|Existing provision                                                                 |Controlling correction                                                                                                                              |
|-----------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
|Amendment 3A effectivity and §§7.1–7.2                                             |§2 prospectively adopts its exact bytes as corrected here; §3 replaces descent-only eligibility and requires a fresh post-3B implementation PR.     |
|Amendment 3 §§2.5–2.6 and §5.3, including their capacity-only BLOCKED exception    |§4 replaces the vendor command-limit guarantee and its approval object; the exact command and seal transport remain unchanged.                      |
|Amendment 3 §§2.4–2.6; Amendment 3A §6.4’s inherited foundational platform boundary|§5 replaces cross-job native-system-layer attestation with an explicit managed-platform trust boundary and retained observable controls.            |
|Amendment 3 §§6.1 and 6.3 and their restart/finalization cross-references          |§6 replaces the three hard time maxima and deadline-derived continuity interval with event evidence and actual lossless reconciliation.             |
|Amendment 3 §§6.1, 6.3 and 6.4 pooler provisions and no-pooler-action restriction  |§7 replaces inaccessible frontend/lease enumeration with provider-scoped disposition and conditionally permits one reader-scoped provider operation.|
|Amendment 3 §5.4 and activation terminology                                        |§8 confirms native one-off execution only.                                                                                                          |

The corresponding approval, sequencing, rollback, appendix and acceptance references in Amendments 3 and 3A use these replacements, not the superseded predicates. In particular, no retained cross-reference may reintroduce a vendor startCommand maximum, an unchanged cross-job native layer attestation, or D_submit_max, D_restart_max or D_post_max as an acceptance requirement. Every unrelated provision remains controlling.

FREEZE.md’s continuous-evidence/database-maintenance clauses and TLS Amendment 1 §5 retain only the already authorized single-project-restart exception, now conditioned on §6 rather than the replaced hard-maxima arithmetic. The exception still permits an availability interruption, never evidence loss. No root document, active-phase pointer, historical amendment or evidence file is rewritten. The SIM-5 active pointer remains unchanged.

This documentation PR adds exactly this one Markdown file. It adds no code, test, dependency, certificate, workflow, configuration, migration, seal or receipt. Authoring, reviewing or merging it runs no probe, job, database operation, credential operation, restart or protected calculation.

2. PR #326 incident: accepted finding, prospective repair

The incident is the failure to obtain independent review on PR #326’s final intended head before merging it. The relevant immutable identities are:

```text
prior cleared head = 6b29c0e4aa93d0947acc25a0be64ba82f44d7ad5
final PR head      = 7fa6b06d0b2d41155309bb63b5331c30263bbba7
historical merge   = 9accee6056dfcd6a6ab06d7f538ce6e5b47ee4e9
merged_at          = 2026-09-07T23:37:59Z
path               = docs/v-1a-amendment-3a-bootstrap-deadline-closure.md
git_blob           = 62441ea2c05da92960b785c8331dcd7c7e3d91ef
raw_file_sha256    = 312546ab6b75b2b81a70c8174070a3901fe934c7d3a63a0cefcc081c80db6125
mode               = 100644
```

The intervening 60c73d2 and 7fa6b06 changes were not covered by the earlier clearance. The later review, submitted at 2026-09-08T02:58:55Z, identifies merged commit 9accee6056 and raises P1 comment 3953930097 and P2 comment 3953930090. A summary badge referring to the PR head does not convert that review into a pre-merge review.

Disposition: accept both findings. The P1 is a documentation-first governance incident, not an acceptable merge procedure; the P2 is a substantive implementation-history defect corrected by §3. Neither is dismissed because the PR is already merged. Keep the historical merge, document bytes, comments, review timestamps and findings intact. No backdating, amended historical approval, force-push or claim that “review completed” cured the ordering is permitted.

Until this amendment’s lawful merge, Amendment 3A’s defective adoption supplies no valid implementation authorization. This proposal does not itself close either GitHub thread or claim that an independent review has passed.

At its lawful merge, this amendment prospectively adopts the exact identified Amendment 3A text, except for the express corrections here. Its reviewer must examine that incorporated text and the affected Amendment 3 provisions, not merely this file’s diff. The new review and Owner merge supply the missing prospective authorization; they do not rewrite the historical violation or waive the general pre-merge review rule.

Before that merge, the independent reviewer must verify the incident identities, the two substantive dispositions and the §3 history audit. The PR discussion must link each old finding to the exact corrective head and section, and the affected material threads must be formally resolved after verification. Closure means the correction has been verified for prospective adoption, not that the old merge was compliant.

The pre-merge audit must also establish whether implementation, operational actions, seals or results were produced in reliance on the defective adoption. This document asserts no zero-impact finding from PR-search results alone. Any such action is recorded truthfully. An additional implementation integration or an undispositioned operational/sealed-look incident blocks effectivity under this amendment; it is not silently grandfathered. Protective containment remains available under existing authority.

3. Exactly one implementation integration

Let M_3B be this amendment’s actual authenticated Owner merge, M_impl the sole lawful V1B implementation integration into main, and E the authorized execution revision. These are verified repository facts, not operator-selected substitutes. The actual PR number, merge SHA/time, blob and raw SHA-256 for this amendment are frozen and independently verified in the implementation only after M_3B exists. No source file embeds its own digest.

The implementation-change surface V1B_CHANGE_PATHS is exactly:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
requirements.txt
certs/supabase-prod-ca-2021.crt
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

The original calendar-only dependency restriction and conditional migration authorization remain unchanged. Listing a conditional path does not authorize creating or applying it. The additional logic required by this correction belongs only in the scorecard and its test module. The implementation reviewer also fixes the unchanged reused-source set required by Amendment 2A §10.3; binding that set authorizes no edits to it.

Use the authenticated V-1A adoption ac85cc9e99ccc499789f3ef79b186768d99fb0d6 as the history audit anchor. Establish its baseline path state, then inspect every first-parent integration through the proposed amendment’s current base and, later, through E. Use complete authenticated PR/commit history and changed-path evidence, including introduced commits where necessary; neither a title search nor an endpoint tree comparison is a complete history audit.

Before this documentation merge there must be zero V1B implementation integrations since that anchor. Any intervening integration touching V1B_CHANGE_PATHS, or otherwise containing V1B implementation, fails that prerequisite. Existing legacy content at the anchor is not itself a new integration. A hidden implementation under an unrelated PR title, a direct push, a squash/rebase integration, a rename, deletion/recreation or a change subsequently reverted cannot evade classification.

For execution, require the ordered first-parent relation:

```text
V-1A adoption < Amendment 3 merge < historical Amendment 3A merge
             < M_3B < M_impl <= E
```

There must be exactly one integration touching V1B_CHANGE_PATHS or implementing V1B in the complete audited interval: M_impl. It must correspond to the fresh, independently reviewed, Owner-merged implementation PR. A second associated or surface-touching integration is rejected even if its final bytes match, it is called a repair, or it restores earlier bytes. Do not designate a later merge as “the implementation” to conceal an earlier one.

Separately authorized changes disjoint from V1B_CHANGE_PATHS may occur outside an active Amendment 3 §4 no-ref-update window. After M_impl, any change to the closed reused-source set also fails the existing exact-source binding, including a changed-and-restored interval. No unrelated change is permission to alter an imported primitive. The no-ref-update window itself remains unchanged: no main movement of any kind is allowed while that window is active.

Close any pre-3B implementation PR without merge and retain its history. After M_3B, Codex may start the authorized implementation on a fresh descendant branch and open one fresh PR. Do not retarget, reopen or rename an earlier implementation PR as the authorized vehicle. Existing draft material may be mechanically reapplied only after effectivity, without carrying forward its PR identity, review, checks or approval. All implementation corrections occur within that one PR before its merge.

At initial, pre-seal, final and recovery checkpoints, retain Amendment 2A’s exact path-presence, mode, blob, raw-byte and regular-worktree verification against M_impl, and additionally verify this amendment’s authenticated adoption and the unique-integration predicate. Use the existing bounded GitHub transport and stage-correct failure routes. Incomplete history is failure, not zero matches; no deadline is extended.

The existing separately reviewed protective revert of M_impl remains a withdrawal operation after lawful window closure, not a second accepted implementation or authority to run. A reverted or subsequently modified implementation cannot execute under this approval. Any later implementation revision requires a separate documentation-first decision without restoring consumed looks.

4. Render command capacity: exact transport, no guarantee

Replace Amendment 3 §5.3’s vendor-limit prerequisite with this policy: the exact native recovery transport is permitted, but successful future recovery is not guaranteed.

Keep the complete Amendment 3 recovery command as transformed by Amendment 3A, its unchanged hexadecimal seal transport, local-file staging, isolated outer/child execution and validation. Keep exact in-memory construction and round-trip validation of the complete would-be canonical seal plus LF and the fully rendered recovery command. Do not shorten a lineage, choose a later boundary, compress or reserialize a seal, add an alternate payload source, or introduce another environment variable or launcher.

Remove L, accepted_render_startCommand_limit_bytes, the 4,096-byte reserve, the two capacity inequalities, and the requirement for authoritative vendor limit evidence. Neither a remembered limit nor a successful synthetic command is a permanent capacity guarantee. This amendment authorizes no capacity-probing job and imposes no new seal-size population cap.

The former capacity-only post-read BLOCKED exception is withdrawn. A malformed candidate, failed exact rendering/round-trip, allocation defect or other actual pre-seal protocol failure uses the ordinary existing stage route; after evidence reading that is null-seal PRE-CELL INVALID. Mere absence of a published vendor maximum is no longer a defect. Every unchanged prerequisite must pass before the exact candidate seal is emitted and protected computation begins.

For an actual recovery, the Owner submits only the exact original rendered command, after the unchanged retained-seal and terminal-exclusion checks. Retain the submitted non-secret command bytes and authenticated job evidence; require exact command equality wherever the control plane returns the command. The normal runtime retained-seal validation remains mandatory. A successful Create-job response is not proof of successful staging, execution or recovery.

A rejection, truncation, unsupported payload, missing acknowledgement or failed launch never authorizes another seal. Resolve an uncertain submission through the existing job-list/retrieval path; do not blindly resubmit. If the only authorized transport cannot execute, preserve the original consumed-look obligation and follow Amendment 2A §8.6 and the existing incident procedure. Submit any first complete truthful receipt already produced. Do not fabricate a process-generated negative, claim terminal completion from an API error, or replace the identity. When no conforming terminal receipt can be produced, the program remains incomplete pending the existing documentation-first incident disposition.

This is an explicit acceptance of possible operational non-recoverability, not a promise that every seal fits Render’s interface. It changes neither the confirmatory budget nor mandatory nonselective receipt publication.

Exact operational-metadata replacement. In Amendment 3 §2.6, replace the complete capacity = C object with exactly:

```json
{"mechanism":"Render native one-off Create job startCommand","recovery_transport_policy":"EXACT_SUBMISSION_OR_CONSUMING_INCIDENT","service_id":"srv-daa7thgae00c73a2lmn0"}
```

Change only the operational payload A.schema_version to ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-2. Preserve its other keys, P, W, the independent-review and Owner-approval envelopes, authenticated identities and canonical hashing. Recompute all enclosing hashes from the actual new payload. Existing version-1 approvals remain immutable historical records and must still be examined under the historical-window/duplicate rules; an active or ambiguously closed old approval blocks launch. Only version 2 may authorize a new current window under this amendment.

This changes operational authority metadata only. It adds no readiness, run, seal, statistical receipt or negative-receipt field or version.

5. Native startup: explicit trust, observable verification

Replace the demand that Render attest identical native/system-layer bytes and archive absence across separate job instances. Render’s documented build-and-environment snapshot is not expanded into an undocumented host-image or hardware attestation.

The trusted pre-interpreter boundary is Render’s managed service control plane, job launcher, operating system, native loader and managed Python startup image. Owner adoption of this amendment explicitly accepts that boundary. The platform must be trusted to launch the selected managed runtime without hidden hostile startup execution; an application running afterward cannot prove that proposition about its own pre-start environment. A known violation or evidence contradicting that trust blocks launch and triggers the existing protective incident route, not acceptance by assertion.

The following controls remain mandatory: the secret-free build and probe of the selected successful B; independent approval of its measured artifact closure; the exclusive build/configuration writer window; effective absence of every frozen startup-injection key; approved build/source/command resolution; and absence of both runtime credentials during the probe. Before secret installation and each secret-bearing job, verify the documented build/environment selection and all available control-plane configuration facts. Do not claim that these reads inspect a future job’s /etc, /proc, archive landmark or native mappings.

Preserve every exact isolated command, Amendment 3A hook transformation, Python/stdlib root rule, /etc/ld.so.preload and archive-absence guard, dependency/native measurement, CA check and invocation-bound dispatch rule. The bootstrap and common guard execute before application secret access. Approved-byte comparison remains mandatory before database connection, followed by the unchanged pre-seal/final remeasurement. Recovery still requires the original build and sealed runtime identity; a different native artifact or dispatch is not approved merely because the version label matches.

The credentials are available to the trusted platform/native startup through the configured environment before application guards execute. Do not describe this as cryptographic isolation from Render or as proof that an unknown pre-interpreter hook could not read them. Observable startup drift remains a possible credential-exposure incident: no evidence access, protective PAT revocation and job/base containment, with database-credential remediation governed by the existing incident rules. A later successful check does not erase that exposure possibility.

The existing private startup-isolation record and control_plane_evidence_sha256 bind this explicit trust decision, the actual probe, build/configuration observations and exact runtime checks. No independent vendor attestation of an unchanged cross-job system layer is required. No guard is removed, no startup-injection key is allowed, no unapproved artifact becomes a baseline, and no new secret-delivery channel is introduced.

6. One restart: actual completion and lossless continuity

Remove D_submit_max, D_restart_max, D_post_max, t_submit_latest, the deadline-derived t_safe_end acceptance rule, and every inequality or finalization requirement depending on them. Historical records remain unchanged. New records do not invent zeros, infinity, guessed SLAs or reconstructed timestamps for those operands. An elapsed-time target or monitoring timeout is not proof of continuity or authority to retry.

Keep the exact administrative connection, reader-OID fence, two termination passes, password transaction and row-version proof, one-primary/zero-replica inventory, exclusive role/project writer window, single top-level Restart project action, post-restart reconnect, stable control-system identity and strictly newer postmaster-generation checks from Amendment 3 §6.3. Keep the same secret protections, URI absence, suspended/inert base and zero V1B jobs. The Owner must give the existing affirmative action-time disruption approval after independent pre-action review.

Pre-action evidence. Retain the exhaustive existing writer/input/obligation inventory, observed server-clock t_guard_start, component identities, immutable prefix hashes and source/destination watermarks. Require zero unprotected accepted inputs, writes, retries, leases or due obligations and zero unresolved pre-guard commit ambiguity.

Each path must already provide either the frozen no-input/no-due-obligation condition or the existing external durable capture-and-reconciliation route. A time-limited quiet interval alone is not sufficient when eligible input could resume before an unbounded restart completes: that path must already have lossless durable protection covering such input. Market closure, an in-memory queue, sampled health or a prediction of a short outage does not establish it.

For a durable path, retention is tied to unambiguous destination commit and identity/hash reconciliation, not an assumed restart duration. Already deployed source behavior must prevent required input loss, destructive acknowledgement, overwrite and expiry while pending, including its existing exhaustion/backpressure behavior. Refusing an input whose capture is required is not lossless containment. This amendment authorizes no new queue, writer, source, pause, disablement, replay mechanism or configuration change to manufacture these conditions. If the existing paths cannot satisfy them, do not restart.

Single submission and completion. Retain t_submit using the existing server-clock lower-bound query and its original-generation guard. Observe that the reviewed inventory/contracts and exclusive window remain effective, then confirm the exact approved action once. Human or network delay is recorded, not assigned a fictitious maximum. An uncertain action is investigated through the same project control plane/support; never click again merely because acknowledgement is absent.

Retain the actual exact-project action and completion evidence, available vendor timestamps with their stated meaning, and observed request/completion bounds when an internal timestamp is unavailable. Keep the existing full-project restart semantics, complete instance inventory and post-restart database-generation conjunction. A toast, healthy status, elapsed wait or dropped connection alone cannot pass it. Preserve the original server-observed t_submit and require the post-restart generation to be strictly later; do not substitute a convenient lower bound.

Actual reconciliation. Using the unchanged server-clock query forms, retain an observed t_reconciliation_cutoff and a later t_recovery_complete upper bound. For every path, verify the original durable prefix unchanged and account for every required record/obligation through the cutoff. No-input paths must actually have had none. Durable paths must map each accepted identity exactly once to either an identity/hash-verified destination commit or one still-retained durable pending record, with contiguous destination watermarks and zero unexplained gaps, duplicates, truncations, changed event times or ambiguous destructive acknowledgements.

Accounted pending work is not evidence readiness. It must complete through the already authorized writer, and independent final reconciliation must prove the complete maintenance cohort committed. The final cohort ends at a newly observed cutoff after restart completion and covers all previously identified pending identities. Subsequent traffic must remain protected by the same continuously effective contracts; it does not require a permanently empty queue or extend the maintenance cohort forever. No record within the final cohort may remain pending when activation is approved. This expressly replaces only the moving-all-future-pending-set interpretation of the former finalization rule.

A missing interval, lost input, expired record, unknown inventory, incomplete restart barrier or irreconcilable prefix leaves the incident OPEN and V1B blocked. Preserve a verified NOLOGIN fence and URI absence; never describe an unknown role state as fenced. Do not restore LOGIN, finalize, repeat the restart, backfill, impute or alter evidence to obtain a pass. Post-action proof is an acceptance gate, not permission to start with known unprotected inputs. A slow but fully evidenced lossless recovery is not invalid solely because a guessed duration was exceeded.

7. Poolers: provider-scoped disposition, not invented visibility

Keep the security boundary covering every applicable Shared Supavisor session/transaction plane, Dedicated Pooler and legacy pooler for project afyiydxbjgzaiswnbcyj. The legitimate scorecard remains direct-host-only. PostgreSQL backend zeros and a newer postmaster do not by themselves prove that pre-rotation pooler frontends, cached authentication or queued leases are unusable after LOGIN restoration.

Replace the requirement for the Owner to enumerate inaccessible individual frontend/cache/lease records with an authenticated, project-and-reader-scoped Supabase support/control-plane disposition in the existing private incident packet. It must identify the exact project, database, reader name and retained reader OID; cover every applicable pooler plane or provide authoritative evidence of its absence; distinguish observations, actions and provider guarantees; and state coverage limits.

Acceptance requires provider evidence that every pre-rotation authenticated reader frontend and queued/server lease was terminated or irrevocably contained, and that no stale verifier or previously authenticated frontend can obtain reader database access after LOGIN is restored. Coverage must include the entire fenced period, not just a snapshot taken before a new stale-authenticated frontend could arrive. The provider must identify the completion event or applicable deployed behavior and its scope. No individual internal session ID is mandatory when the provider supplies complete scoped coverage.

If an operation is necessary, this amendment conditionally authorizes one coordinated provider-executed reader-scoped drain/purge of old reader frontends, queued/server leases and cached authentication on those applicable planes. It occurs after the acknowledged password change and completed primary restart, while verified NOLOGIN remains active, the URI remains absent and all V1B jobs remain absent. Before execution, retain the provider’s exact supported procedure, covered planes, expected effects and completion evidence; obtain independent scope review and the Owner’s affirmative approval. Keep the role/project window exclusive through final disposition.

The operation may not alter another role, grant, credential, database instance, source or writer, introduce a second password rotation or project restart, or require a project-wide interruption affecting other clients. Any such widening requires a separate amendment. No guessed pooler API, self-hosted administrative command, permission expansion or secret disclosure to a support transcript is authorized. An uncertain provider action is reconciled, not repeated blindly.

This is a conditional authority, not a claim that Supabase currently offers that scoped operation or guarantees the required coverage. A generic FAQ, fixed cache wait, one failed old-password test, self-hosted source code or repeated PostgreSQL zeros does not substitute for the scoped disposition. If the provider cannot establish complete termination/containment or cannot perform a conforming operation, preserve verified NOLOGIN and URI absence, keep the incident OPEN and block activation. Do not convert unavailable proof into an Owner assertion of safety.

Only after this disposition and §6 pass may the unchanged guarded URI provisioning, LOGIN restoration, reader/prepared/settings zero checks and private incident finalization proceed. Retain all original secret-free confirmation bounds and exact rotation-row checks. No old password, verifier, verifier digest, token or full URI enters the packet’s public projection.

8. Meaning of active; preserved scientific and security law

“V1B active” means one currently authorized native Render one-off invocation for one exact frozen manifest, including an exact recovery when applicable. It does not mean an always-on service. Completion, HOLD, WAIT, rejection or failure ends that invocation; none automatically launches the next one.

Use only atom-h2d3-benchmark, service srv-daa7thgae00c73a2lmn0, with the existing authorized 4c-8g capacity. Preserve the secret-free preparation exception and the exact inert base command:

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"
```

The base remains suspended whenever either runtime credential is installed. No continuous worker, cron, scheduler, Render Workflow workload, readiness-polling loop, automatic retry or parallel V1B job is authorized. The existing nine-manifest registry, sequential window protocol and same-identity recovery rules remain unchanged. Protective stopping cancels/verifies the one-off job itself as well as suspending/verifying the base. Preserve original build, seals and receipts while any recovery obligation remains.

All V1A/TLS/2A mathematics remain unchanged: targets, horizons, manifest/cell partition, original T_amend, earliest boundaries, all readiness minima including the 1H necessary floor, causal scale/lineage/cohort rules, benchmark/gate definitions, numerical order, RNG/bootstrap streams, thresholds and global multiplicity. No duration, transport result or operational observation becomes a scientific input or permits population selection.

Preserve the direct database/project/reader identity, pinned CA and verify-full/SCRAM restrictions, read-only snapshots, catalog/privilege checks, two authorized proof readers, append-only evidence, no production-consumer change and all broker/capital prohibitions. Preserve both exact runtime secret names and their allowed sources; the GitHub PAT remains repository-only Contents:read plus implicit Metadata:read. No new credential, fallback, write scope, secret logging, exposed-password restoration or automatic rotation is granted.

Preserve seal-before-results, one look per manifest/cell, exact recovery identity, first-complete-receipt retention/publication, truthful null identities and every statistical/negative receipt schema and filename. New-seal failure before evidence remains BLOCKED; after evidence and before a seal it follows the existing null-seal PRE-CELL INVALID route; accepted recovery/post-seal failures remain consuming; final authority failure after complete truthful cells remains POST-EVALUATION AUTHORITY INVALID. An external failure without a truthful runtime receipt remains an incident, never a fabricated receipt or replacement look. No protected partial values may be disclosed.

9. Exact-head review, effectivity and implementation handoff

The documentation PR must contain exactly the sole path above at mode 100644. Before Owner merge, independent review of its exact final head must verify the complete corrected contract, §2’s incorporated identities and impact disposition, and §3’s no-prior-implementation audit. No same-author review satisfies independence.

The reviewer must specifically examine the changed risk contracts: recoverability is not guaranteed; the managed pre-interpreter platform is trusted rather than remotely attested; actual continuity is mandatory; and unavailable provider pooler coverage still blocks activation. These decisions must not be hidden as wording-only changes.

Record the full final-head SHA, exact file blob/raw digest, substantive independent review, each P1/P2 disposition, zero unresolved material findings/threads, and the actual required check names and green conclusions. Resolve and formally close the two carried PR #326 findings after verifying their corrections. A usage-limit reply, review request, earlier-head clearance, green summary badge or absent branch-protection flag is not a substitute. Do not waive, remove or reinterpret a required check. A required check that is missing, pending, skipped, neutral, cancelled or failing is not green; any required integration check must demonstrably cover the exact candidate head and applicable base. Any amendment-head change requires review and checks covering the resulting exact head. Recheck the actual head, base/history, findings and checks immediately before merge; changed material invalidates the gate.

Only the Owner may then merge this documentation PR. That merge is M_3B and supplies prospective implementation authority. It does not attest that any operational predicate is already true. No implementation begins and no implementation PR opens before it.

Afterward, Codex implements only the authorized surface in the single fresh PR. In addition to all preserved tests, require focused coverage of: pre-amendment/duplicate/renamed/direct-push and changed-then-restored integrations; permitted disjoint history outside the window; operational payload-v2 and old-window handling; recovery transport failure without a new look; unchanged startup guards and native-drift failure; and every unchanged receipt/secret boundary. Review the operational restart and pooler checklists against missing, uncertain and contradictory evidence; synthetic tests cannot certify provider behavior.

That implementation independently requires exact-final-head review, all required checks green, zero unresolved P1/P2/material findings and Owner merge. Deployment, the single restart/provider operation, credential provisioning and each invocation retain their separate operational gates and action-time Owner authority. No merge request in this task authorizes their execution now.

Completion of this drafting task: one proposed documentation amendment. Independent review, required CI, thread closure, Owner merge, implementation and operational acceptance are separate facts and are not asserted by this file.

Source and verification anchors

Repository facts above were read from the authenticated repository at the inspected main and PR #326 metadata/review records. The controlling source locations are the five technical document paths in §1, AGENTS.md, PR #319’s adoption identity, and PR #326 review 5136859752 with comments 3953930097 and 3953930090. These identifiers support inspection; they do not replace runtime authenticated verification or supply a future merge identity.

Public platform references consulted on 2026-09-08 are Render One-Off Jobs (https://render.com/docs/one-off-jobs), Render Retrieve job (https://api-docs.render.com/reference/retrieve-job), and Supabase Supavisor FAQ (https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI). Render documents the build/environment snapshot and one-off lifecycle. These references are not evidence of an exact command-size maximum, unchanged native-system-layer attestation, or completed reader-specific pooler purge. Actual operational evidence remains separately required.
