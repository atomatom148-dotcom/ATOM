# V-1A Amendment 3 — V-1B Operational Prerequisites

**Decision ID:** `ATOM-V1A-AMENDMENT-3-V1B-OPERATIONAL-PREREQUISITES-1`  
**Status:** PROPOSED — no effect before independent final-head review, green required checks, zero material findings, and Owner merge.  
**Author:** ChatGPT Pro — architecture and freeze authority  
**Date:** 2026-09-06  
**Document state:** Complete replacement for review; not an assertion of implementation or operational acceptance.  
**Sole documentation-PR path:** `docs/v-1a-amendment-3-v1b-operational-prerequisites.md`  
**Inspected repository:** `atomatom148-dotcom/ATOM`  
**Inspected main:** `f0035147a646fc7d4c7002c8a2706f4987f6a10c`  
**Corrects PR:** #325 at exact head `0fbdf3f7088e14cb18e352b2e5dfd3e44d13f991`, including the prior correction of `87d36e93b80ec0fc3b29613b400efa921d8e0750`. Neither earlier head supplies this document’s final-head approval.  
**Implementation owner:** Codex; one separate implementation PR and one implementation owner.  
**Approval, merge, credentials, infrastructure and budget authority:** Owner.

## 1. Decision, effectivity and exclusions

Remove exactly six V-1B prerequisites: the pre-merge runtime-hash bootstrap contradiction; the missing narrowly scoped GitHub credential; the unprotected-main predicate; the unspecified one-shot Render command/lifecycle; the exposed existing reader password; and direct-host IPv4 reachability.

This amendment changes only the provisions expressly identified below in:

- `docs/v-1a-volatility-first-freeze.md` (`ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`), principally §§12.2, 13.2.1, 15.1, 16.2–16.4, 19, and the corresponding stop/sequence provisions;
- `docs/v-1a-amendment-1-tls-trust-anchor.md` (`ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1`), solely its hash-bootstrap cross-references, password-preservation restriction and operational-setup restrictions; and
- `docs/v-1a-amendment-2a-tiered-readiness-boundaries.md` (`ATOM-V1A-AMENDMENT-2A-TIERED-READINESS-1`), solely its inherited runtime-literal comparisons, protected-main predicate, no-new-credential restriction and operational-setup restrictions in §§8.3, 9.1, 10–11 and corresponding cross-references.

All other law remains controlling. The original documents and all eight Amendment 2A evidence files remain byte-unchanged. This PR adds only this document: no implementation, certificate, dependency, migration, receipt, workflow, pointer or configuration file is added or edited.

Drafting, reviewing and merging this amendment do not execute its later operational steps. No database connection, database evidence access, protected statistic, live readiness scan, runtime fingerprint probe, password rotation, credential provisioning, deployment, service resume or purchase occurs in this documentation phase.

After this amendment’s Owner merge, Codex may resume only the separate documentation-conforming V-1B implementation. Operational setup requires that implementation’s independent final-head review, green required checks, zero material findings and Owner merge, followed by the Owner’s exact deployment/invocation authorization. IPv4 additionally requires §7’s separate action-time cost confirmation. Immediate protective suspension or credential revocation retains its existing authority.

The operational target is availability before Tuesday, 2026-09-08. That target never changes readiness, backdates a run, moves a boundary or permits an early protected result. `T_amend` remains Amendment 2A’s verified adoption time; this amendment creates no new research anchor.

### 1.1 Closed authority and source map

This document is complete for Amendment 3; it is not a list of instructions to edit an earlier draft. V-1A, TLS Amendment 1 and Amendment 2A remain incorporated controlling law except for the express replacements below. `AGENTS.md` remains unchanged. Its active SIM-5 pointer is not transferred. The already merged TLS Amendment 1 §5 parallel-V-1B exception continues; no SIM, HIST8, V-1C, V-2, broker or capital authority is added. The Owner expressly reserves every merge in this correction and the subsequent V-1B implementation/receipt sequence; no general delegated execution provision is used to bypass that reservation.

The only later code additions allowed by this correction are inside the previously authorized scorecard and test modules: the exact non-consuming probe entry point in §2.4, the existing-GitHub-metadata reader in §2.6, and the actual-seal capacity gate in §5.3. No new module, service, CLI credential, environment variable, disk, provenance file in the runtime, migration ordinal, or third-party dependency is implied. The probe is a separately authorized Python entry point, not a third scorecard CLI option.

The only additional metadata operations are the explicitly identified non-secret approval/review comments in the already existing ATOM PR #325 discussion. They use the already authorized GitHub host/repository and existing Owner GitHub control plane. The scorecard uses only its one read-only PAT for their authenticated reads. This is an express narrow extension of repository-authority metadata reads, not an unnamed URL, alternative credential or market/evidence source. No private incident artifact, token-scope screenshot, Render API credential or secret is made readable by the scorecard.

The one routing exception is §5.3’s capacity-only BLOCKED refusal after a count-only scan but before successful seal emission. It expressly replaces V-1A §24 and Amendment 2A §8.6 only for that condition. All other after-read and after-seal defects retain their existing INVALID routes. There is no change to the contents or hash algorithms of a successful readiness object, run identity, seal or receipt.

In this document, a response-derived identifier is not an operator-selected freeze value. `E` is the exact authenticated execution commit under §4; `B` is the actual build-producing deploy ID under §2.5; `J` is the actual id returned by Render Create job; `M` is one exact §5.2 manifest ID; and `L` is the verified vendor capacity under §5.3. No command sends an unresolved angle-bracket placeholder. A missing source value stops the specified step; it is never invented or silently assigned by implementation.

## 2. Invocation-bound runtime identity; version law unchanged

### 2.1 What remains frozen before implementation merge

Preserve every existing `runtime_identity` key and type and every version/platform/float requirement in V-1A §13.2.1, including:

```text
render_service_id       = srv-daa7thgae00c73a2lmn0
render_runtime          = python
python_implementation   = CPython
python_version_source   = PYTHON_VERSION
python_version_env      = 3.14.3
python_version          = 3.14.3
python_cache_tag        = cpython-314
platform_system         = Linux
platform_machine        = x86_64
byteorder               = little
libc_name               = glibc
libc_version            = 2.36
float_radix             = 2
float_mant_dig          = 53
float_max_exp           = 1024
float_rounds            = 1
```

`libpq_version` remains its exact independently reviewed V-1B integer literal. `EXPECTED_DEPENDENCY_VERSIONS` remains the complete literal, exact-version object required by §13.2.1, including the imported transitive closure and `exchange-calendars==4.13.2`. Where the base freeze delegates a literal to implementation review, that delegation remains unchanged; this amendment supplies no guessed replacement version.

No invocation-time dependency resolution, version range, update, alternative wheel selection by an operator, package installation or version discovery used as an acceptance baseline is authorized. `requirements.txt` retains its existing append-only calendar-closure restriction. Repository source, requirements, reused primitives, migration presence/absence and CA bytes remain bound to the authenticated reviewed implementation merge under Amendment 2A §10.3. Invocation-derived runtime hashes never replace that source-integrity proof.

### 2.2 Authenticated bytes, invocation-derived dispatch

Replace the old requirement to embed the four runtime-artifact component digests, their combined digest, the CPU-dependent `libm_dispatch` object/digest and the complete runtime-manifest digest as pre-merge host literals. Do not replace any version literal, file-coverage rule, native-library inclusion, normalized-path rule, source/bytecode restriction, tree ordering, duplicate rejection, mapping requirement, canonical JSON rule or repository-source binding.

The baseline for installed bytes is the independently approved same-build provenance record in §§2.4–2.6, established with neither runtime credential present. A scorecard process may measure its installed bytes, but may not approve those bytes as its own baseline. It must obtain the approved record through §2.6 and compare all four components exactly before database connection. Record availability, authenticated Owner approval and independent review are prerequisites, not checks that can be deferred until after evidence access.

`libm_dispatch` is different from the artifact-byte baseline: it is derived in the actual invocation process after the complete approved import/native closure is loaded, using the existing `dlsym` and ASLR-neutral executable-mapping/file-offset procedure. `log` and `exp` must resolve inside the exact approved libm file already covered by `loaded_native_tree_sha256`. No pre-merge probe or provenance probe fixes their CPU-selected offsets. A CPU difference may change dispatch between unsealed invocations; it may not change the approved bytes for a build or replace a sealed dispatch.

The existing formulas remain:

```text
runtime_artifact_sha256 = sha256(canonical_json(runtime_artifact_components))
libm_dispatch_sha256    = sha256(canonical_json(libm_dispatch))
runtime_manifest_sha256 = sha256(canonical_json(runtime_manifest_body))
```

`runtime_manifest_body` is the complete V-1A §13.2.1 runtime object excluding only its own `runtime_manifest_sha256`. The complete third-party/native closure must be loaded before fingerprinting; initialization that would load a new executable artifact later is not deferred until an actual connection. The same local initialization/coverage routine is used by the probe and scorecard. It must not open a database, perform network I/O or inspect research results when called by the probe. No outcome-dependent CPU, build, library or invocation selection is permitted.

### 2.3 Binding, repeated checks and recovery

Put the approved-byte, invocation-derived `runtime_manifest_sha256` into the existing Amendment 2A §§8.3–8.4 identity bodies. Their existing hashes and the existing seal bind it; the evaluated receipt carries the complete `runtime_identity`. Add no readiness/run/seal/receipt key or version. The build/provenance approval is operational authority metadata, not a research receipt.

Before the seal/protected-computation transition and immediately before receipt construction, remeasure all covered bytes and recompute the complete runtime body/digest. Require exact equality both to the approved artifact components and to the invocation’s initial complete runtime body/digest. Preserve the existing repeated repository-source, CA and authority checks. Do not accept a late import, dynamic executable load, replaced artifact, changed mapping or altered dispatch.

Recovery first validates the retained seal using Amendment 2A §10.2, then retrieves the same source-revision approval under §2.6. Its build must remain the original approved `B`, and its four observed component digests must match that approval before a database connection. Independently derive the full recovery runtime and require its digest to equal the `runtime_manifest_sha256` in both sealed identity bodies. Those bodies carry the digest, not the complete runtime object: do not claim they contain fields they do not contain. Where the original complete runtime object was retained, compare its canonical bytes too. Verify both identity hashes and `seal_record_sha256` unchanged. A new build or CPU dispatch never becomes a recovery baseline, even if package version labels match.

The original successful build must not be replaced while any valid seal lacks its first complete terminal receipt. A failed sealed job is recovered using that still-selected artifact; it does not depend on an unimplemented ability to select an arbitrary historical artifact in Create job. Unrelated main advancement does not rebuild that sealed execution revision. The separately inspected current head must still satisfy Amendment 2A’s ancestry/prior-look guard. If the platform loses or replaces the required build, fail through the existing consuming-negative route; do not relabel a rebuild as the old build.

New-seal failures before evidence reads are BLOCKED. Except for §5.3’s explicit capacity-only exception, failures after evidence reads but before sealing are null-seal PRE-CELL INVALID. Once a valid recovery seal has been accepted, any missing provenance, authentication failure, different build, artifact mismatch or other failed prerequisite is consuming PRE-CELL INVALID, never BLOCKED. A failed final authority/runtime check after all truthful manifest cells exist uses POST-EVALUATION AUTHORITY INVALID. Keep all original sealed fields, initial authority proof and truthful-null merge-identity rules; emit no protected partial values.

### 2.4 Exact non-consuming provenance probe

The sole probe entry point is `provenance_probe_main()` in `quant/volatility_scorecard.py`. It takes no function argument, command argument, stdin input, manifest ID, approval file or credential. It returns the process exit code described below. It may be implemented only in the already authorized module and tested only in the existing test module.

Its exact one-off `startCommand`, with no substitutions, is:

```text
python -B -c 'from quant.volatility_scorecard import provenance_probe_main; raise SystemExit(provenance_probe_main())'
```

`-B` suppresses bytecode-cache writes for the probe; it neither changes the frozen Python version nor permits execution of uncovered sourceless bytecode. Module/package import must have no connection, environment-dump, logging, evidence-read or file-write side effect. Before loading the measurement closure, the entry point requires the keys themselves `ATOM_E1_SCORECARD_READONLY_DATABASE_URL` and `ATOM_V1B_GITHUB_TOKEN` to be absent from `os.environ`; empty strings do not satisfy absence. It does not unset or mask a secret after startup to claim absence. The control-plane removal sequence in §2.5 is also mandatory.

The probe reads only: the verified local implementation/worktree and already authorized CA; the V-1A §13.2.1 local runtime files, installed metadata and `/proc` mappings; the existing `PYTHON_VERSION` and documented Render `RENDER_SERVICE_ID`, `RENDER_GIT_COMMIT` and repository/branch metadata; and the process UTC clock. Its source SHA must equal local `git rev-parse HEAD` and `RENDER_GIT_COMMIT`. The external operator has already matched those source bytes to authenticated GitHub history. No undocumented `RENDER_BUILD_ID`, operator-supplied build ID, credential helper, private record, evidence/receipt parsing, database connection or network call is allowed in the probe.

On success, write exactly one canonical UTF-8 JSON object plus one final LF to stdout, flush successfully, and return 0. The object has exactly these keys:

```text
schema_version              = "ATOM-V1B-RUNTIME-PROBE-1"
render_service_id           = "srv-daa7thgae00c73a2lmn0"
execution_source_sha        = observed and locally verified E
python_version              = "3.14.3"
runtime_artifact_components = exact four-component V-1A object
runtime_artifact_sha256     = SHA-256 of its canonical component object
probe_generated_at_utc      = measured UTC RFC3339 microsecond timestamp
```

The output includes no dispatch object, database value, count, readiness object, seal, receipt, credential, environment dump or protected statistic. It creates or modifies no file and writes nothing to stderr. The operator captures stdout from the existing Render job log stream, identified by the actual Create job response ID `J`; a synthetic or manually reconstructed record is not an observation.

For a handled validation, import-closure, hashing or environment defect, write exactly the following JSON plus one LF to stdout, create no file, write nothing to stderr and return 1:

```json
{"mode":"V1B_PROVENANCE","reason":"PROVENANCE_PROBE_FAILED","status":"BLOCKED"}
```

Any supplied argument is refused before a measurement, with no files/stderr, return 2 and exactly:

```json
{"mode":"V1B_PROVENANCE","reason":"INVALID_PROBE_ARGUMENTS","status":"USAGE_ERROR"}
```

A failure before Python/entry-point execution, termination by signal, broken stdout or truncated/missing log record is an infrastructure failure, not a successful observation. The control plane records BLOCKED; it does not manufacture the required success line or assume exit 0. A handled failure consumes no research identity. A new probe may be separately authorized only after the failed job is proven terminal and its defect is repaired within existing authority.

### 2.5 Secret-free build/probe sequence and actual build identity

The Owner performs these steps through the existing authenticated Render control plane, on service `srv-daa7thgae00c73a2lmn0` only. The scorecard receives no Render API key. The first build/probe precedes provisioning the new PAT and reinstallation of the rotated reader URI. A later build/probe uses the same sequence; it never reintroduces the exposed URI.

1. Verify that every earlier job is terminal and that no valid seal is awaiting recovery. Keep automatic deploys/previews off; reserve an exclusive manual configuration/build window. Set the base `startCommand` to exactly `python -c "raise SystemExit(0)"` and verify suspension. This invariant holds during all later steps, including rollback.
2. Remove both named secret keys from the service’s configured environment using the Environment control plane and Save only. A service-level deletion must not reveal the same key from a linked environment group. Inspect effective key names and linked-group/secret-file configuration privately. A key supplied by a group, blueprint injection, mounted secret file or baked artifact is not cured by deleting a service override. This amendment does not authorize editing a shared group or another service: such a configuration blocks the probe until a separately authorized, service-scoped correction removes that source. Do not log secret values. Retain only key-absence evidence.
3. When this is a later probe and the same valid dedicated PAT/rotated URI must be restored, the Owner may retain those existing values only transiently in the existing secure control-plane session for this removal/reinstallation cycle. No new variable, file, command argument, clipboard transcript, token replacement or exposed-password backup is created. If secure retention is unavailable or lost, remain suspended; do not restore an exposed value or mint an unapproved replacement. On the initial probe, do not provision either secret early merely to remove it again.
4. Build the exact approved source `E` with the unchanged `pip install -r requirements.txt` and `PYTHON_VERSION=3.14.3`, with both keys absent. The existing per-invocation `ATOM_V1B_AUTHORIZED_MAIN_SHA`, when set, equals `E`; it is not used to carry provenance. Obtain the actual build-producing deploy object through Render’s service deploy history. `B` is that object’s returned immutable id, with `commit.id = E` and verified successful build completion. In `ATOM-V1B-RUNTIME-PROVENANCE-1`, the term `render_build_id` means this build-producing deploy ID; it is not an undocumented vendor field. `render_deploy_id` is the same `B` for this record. A build-only failure, a requested but unsuccessful deploy, a configuration-only redeploy mistaken for a build, an ambiguous latest artifact or a caller-assigned ID is unusable.
5. With no intervening build/configuration writer, re-read effective environment key absence and the successful deploy/artifact selection, verify the base is suspended/inert, then Create job with exactly §2.4’s `startCommand`. Create job’s native snapshot must be the latest successful artifact `B` and the now-secret-free configured environment. There is no assumed per-job environment override parameter. Retain the request, returned `J`, source/deploy observations bracketing creation and complete probe stdout. Resolve uncertain POST outcomes by listing/retrieving jobs, not by sending another POST.
6. Verify the exact success record, its local-byte/component hashes, job termination and parent suspension. Compare the returned source/service to `B` and `E`; independent acceptance must examine the authenticated build history, reviewed source/blob bindings and complete observation. A process’s own version strings or digests alone do not approve it. The trusted roots for this operational approval are the authenticated Render build/control plane, the authenticated reviewed GitHub source and the independent human/agent acceptance beneath Owner approval. This is not claimed to be remote hardware attestation against a compromised Render control plane or kernel.
7. Construct the provenance record below from those observed values. Keep its original canonical bytes and SHA-256 in the existing private operational acceptance packet. On initial setup only, after the probe terminates, obtain §3’s PAT scope evidence and §5.3’s authoritative vendor-limit evidence (not the later actual-seal calculation), perform §6’s one actual rotation, and insert only the properly scoped dedicated PAT and newly rotated conforming URI using Save only. Record that URI-update confirmation, finalize the incident, and only then obtain independent acceptance and issue §2.6’s Owner approval. For a later build/probe, reuse the same completed rotation and finalized incident record; restore only the same still-valid PAT and same already-rotated conforming URI retained under step 3. A later probe does not authorize or require another password rotation, a replacement PAT or a new incident completion timestamp. Reconfirm scope, incident disposition, current vendor-limit evidence and safe credential reinstallation before issuing that later source revision’s separate approval; preserve the original rotation timestamp and finalization digest unless a separately authorized factual incident addendum requires explicit new review. Because a newly created one-off snapshots configured variables and the existing successful artifact, this does not require a new build. Verify the source build remains `B` before each evidence-capable job. If the platform instead changes the artifact, refuses the expected snapshot semantics or requires an unapproved replacement build, no evidence-capable job is accepted.

The provenance record has exactly:

```text
schema_version              = "ATOM-V1B-RUNTIME-PROVENANCE-1"
render_service_id           = "srv-daa7thgae00c73a2lmn0"
render_build_id             = B as defined above
render_deploy_id            = B
repository                  = "atomatom148-dotcom/ATOM"
execution_source_sha        = E
build_command               = "pip install -r requirements.txt"
python_version              = "3.14.3"
runtime_artifact_components = unchanged exact object from successful probe
runtime_artifact_sha256     = unchanged digest from successful probe
probe_generated_at_utc      = unchanged timestamp from successful probe
```

There is one approved build/provenance baseline per execution SHA `E`. A different build of the same SHA is not automatically the approved build. No latest-record-wins rule, reconstruction of an old build ID or replacement baseline is allowed. For a new execution revision, the process is repeated without changing any sealed identity. For a valid pending recovery, preserve its original build instead of starting this process.

### 2.6 Exact approval transport, authentication and lifetime

The runtime cannot read the private acceptance packet and does not have a Render control-plane credential. Therefore the Owner mirrors only the following non-secret approval payload into the existing PR #325 discussion. This explicitly defined mirror is the sole runtime input for approved provenance and the vendor capacity; it is not an environment variable, local approval file, alternate credential, new repository file or arbitrary URL.

Let `P` be the complete §2.5 provenance record. Let `C` be the exact capacity object:

```text
mechanism = "Render native one-off Create job startCommand"
service_id = "srv-daa7thgae00c73a2lmn0"
accepted_render_startCommand_limit_bytes = L, a positive integer from §5.3 evidence
recovery_capacity_margin_bytes = 4096
vendor_evidence_reference = exact non-secret official reference or support case ID
vendor_evidence_sha256 = SHA-256 of retained non-secret vendor confirmation bytes
vendor_evidence_observed_at_utc = actual verification time, UTC RFC3339 microseconds
```

The approval payload `A` has exactly:

```text
schema_version = "ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-1"
provenance = P
provenance_sha256 = sha256(canonical_json(P))
capacity = C
probe_job_id = actual successful §2.4 job ID J
probe_observation_sha256 = sha256(canonical_json(successful probe object))
control_plane_evidence_sha256 = digest of retained non-secret same-build/secret-absence evidence
pat_scope_evidence_sha256 = digest of retained non-secret §3 scope evidence, NEVER a token digest
incident_record_id = "ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06"
incident_finalization_sha256 = digest of the finalized non-secret-field incident record
rotation_status = "COMPLETED"
rotation_completion_timestamp = actual finalized §6.1 timestamp
```

Private exposure locations or mechanics are not in `A`. The digests above identify retained non-secret control records, not passwords, token bytes, password verifiers, headers or full secret environments. The record reviewer inspects the retained underlying records privately; a digest alone is not proof of their contents.

The exact metadata actions use the existing Owner/reviewer GitHub connections, never the V-1B PAT for a write:

```text
POST https://api.github.com/repos/atomatom148-dotcom/ATOM/issues/325/comments
body = {"body": <the canonical JSON text specified below plus one LF>}
```

First the implementation/operator presents `A` and its canonical SHA-256 for independent acceptance. The independent reviewer posts exactly this JSON object (with observed digest substituted):

```text
schema_version = "ATOM-V1B-OPERATIONAL-REVIEW-1"
approval_payload_sha256 = sha256(canonical_json(A))
verdict = "PASS"
material_findings = 0
```

Only after independently verifying the successful probe, same-build evidence, PAT scope, finalized incident and current vendor limit does the Owner post exactly:

```text
schema_version = "ATOM-V1B-OPERATIONAL-APPROVAL-1"
payload = A
approval_payload_sha256 = sha256(canonical_json(A))
independent_review_comment_id = actual returned ID of that prior PASS review comment
independent_reviewer_user_id = its authenticated author numeric ID
independent_reviewer_login = its authenticated author login
```

Both are append-only authority comments: their `created_at` must equal `updated_at`; edits/deletion are forbidden. Retain the original API envelopes, canonical bodies, IDs and hashes privately through final program audit and any valid recovery. An amendment comment is not an Owner merge or statistical publication.

For every evidence-capable invocation, the existing repository verification phase performs authenticated GET using only `ATOM_V1B_GITHUB_TOKEN`:

```text
https://api.github.com/repos/atomatom148-dotcom/ATOM/issues/325/comments?per_page=100&page=1
```

Read all pages by increasing page by one while a same-origin/same-path `rel=next` is present; validate the next link agrees with that exact request and never follow another host, repository or path. An incomplete, inconsistent or failed pagination is not an empty result. Select the unique exact-schema Owner approval whose `payload.provenance.execution_source_sha == E`. Owner identity is `user.id = 307819087` and `user.login = atomatom148-dotcom` in the authenticated API envelope. Require its canonical body, all digests and fields to validate; its source/service/build tuple to match the approved execution; and its referenced prior unedited PASS review, found in the same fully read discussion, to hash the identical `A`. The reviewer’s authenticated ID/login must equal the two explicit reviewer fields in the Owner approval and must differ from the Owner approval author. Those fields are the runtime’s exact designation input; it does not read a private designation file. The Owner and independent final audit additionally verify actual independence from the implementation job in the retained ownership/review record. Mere comment text claiming “Owner” or “PASS” is insufficient.

No zero-match fallback, duplicate approval, “latest” choice, caller-selected comment ID, local metadata cache or URL extracted from a comment is accepted. Fixed references in `A` are evidence locators for the external reviewer, not runtime fetch instructions. The runtime derives `B` from authenticated `P`, not from an invented environment field. The Owner’s bracketing Render evidence proves the actual job’s artifact selection; the runtime separately proves exact approved bytes/source. Do not describe the latter as a direct Render API attestation inside the process.

Fetch/revalidate the identical approval and review body hashes at the pre-seal and final repository checks, and during recovery. Verify the approval predates the invocation’s evidence read; the external launcher does not create the job until approval exists. The underlying private scope/incident/limit evidence and same-build selection must still be valid at action time. Any discovered change stops the action rather than silently updating `A`. Approvals remain retained after PAT removal. Approval loss, duplicate approval or post-seal mismatch uses §2.3 failure routing.

The public-repository status remains mandatory. GitHub documents public issue-comment reads without additional optional repository permissions, but live acceptance must prove that these exact authenticated reads work with the restricted PAT. A refusal does not authorize Issues/Pull requests permissions, an unauthenticated retry or another source. No approval-comment read is made by the secret-free probe.

## 3. Exactly one additional Render secret

Authorize exactly one new secret environment variable, on the named benchmark service only:

```text
ATOM_V1B_GITHUB_TOKEN
```

It must be an Owner-provisioned fine-grained personal access token with:

```text
resource owner         = atomatom148-dotcom
repository selection   = only atomatom148-dotcom/ATOM
repository permissions = Contents: read; implicit Metadata: read
all other optional permissions = no access
all write permissions  = none
```

No classic PAT, additional repository, account/organization permission, administrative permission, Pull requests permission, Checks permission or write scope is authorized. Token scope is verified by the Owner at provisioning; a successful `GET` alone is not proof of least privilege.

Before acceptance for any evidence-capable V-1B invocation, retain non-secret GitHub control-plane evidence proving the same fine-grained PAT’s exact (1) resource owner `atomatom148-dotcom`, (2) repository selection of only `atomatom148-dotcom/ATOM`, and (3) repository permissions Contents: read plus implicit Metadata: read, with every other optional permission No access and every write permission absent. The evidence may be a timestamped settings export or screenshots plus the token’s non-secret name/identifier, but must never contain the token value, token hash, authorization header or recovery code. The Owner-controlled V-1B operational acceptance record stores or references those artifacts; the independent acceptance reviewer must inspect them. Missing, ambiguous, stale, cropped or non-correlatable scope evidence is `BLOCKED`; successful API reads cannot cure it.

The scorecard’s sole token source is that exact Render-injected environment variable, read directly in memory. Missing, empty, malformed, expired, revoked, rejected or insufficient authentication fails closed under the existing timing rules. No command-line argument, stdin, local file, `.env` load, secret-file mount, Git credential helper, `gh` login/configuration, `GH_TOKEN`, `GITHUB_TOKEN`, other environment alias, unauthenticated request or fallback credential may supply it. Local non-network Git object/worktree checks remain permitted; Git/CLI credential discovery does not.

Use the token only for authenticated HTTPS `GET`s to GitHub’s API for this exact repository’s existing authority/history/receipt verification. Never put it in a URL or subprocess argument. Never forward it on a cross-origin redirect. Do not serialize or log the token, its digest, an `Authorization` header, a complete environment, a credential-bearing request or an exception containing any of those. Persistence is restricted to Render’s secret storage; the process uses it transiently in memory for authenticated transport. It enters no manifest, seal, receipt, test fixture or repository artifact.

Required authenticated PR metadata and merge proof remain mandatory. The inspected repository is public; endpoints exposing public PR metadata can be used with the authenticated request without granting new optional token permissions. If GitHub refuses a required read, or repository visibility/permissions change, stop: do not remove authentication, broaden the token or replace PR metadata with an unsigned commit-message assertion. Deployment acceptance must prove that the exact restricted token can perform every required read before any database access.

This new secret is separate from, and never a substitute for, the existing database URI. No Render API or Supabase administrative token is installed in the scorecard runtime.

## 4. Authenticated default-branch predicate instead of branch protection

Select the predicate-replacement route. This amendment authorizes no branch-protection, ruleset, repository visibility, review-policy or check-policy mutation.

In Amendment 2A §§9.1 and 10.3 and every incorporated V-1B reference, replace “current protected main head” with “authenticated current default-branch head for the exact repository, whose default branch is main.” A `protected=false` flag is not itself a V-1B failure; inability to prove the new predicate is.

For each required repository-verification checkpoint:

1. Authenticated repository metadata must identify repository `atomatom148-dotcom/ATOM`, repository ID `1339927428`, owner `atomatom148-dotcom`, and `default_branch = main`. A rename, different repository, changed default branch or unavailable identity is not silently accepted.
2. Authenticated ref metadata must identify exactly `refs/heads/main` and its 40-lowercase-hex commit SHA, `H`. Do not substitute a local remote-tracking branch, cached response, PR head, tag, environment claim or caller-supplied ref. Inconsistent observations during a check must be reread before passing; unresolved inconsistency fails closed.
3. For a new-seal invocation, execution SHA `E` must be `H`. For exact recovery, `E` remains the sealed execution SHA and must be an authenticated ancestor of separately inspected current `H`. The current head and retained seal/terminal history must contain no conflicting look.
4. In both modes, retain `RENDER_GIT_COMMIT == ATOM_V1B_AUTHORIZED_MAIN_SHA == git rev-parse HEAD == E`, the exact Owner-merged V-1A/TLS/2A/implementation identities, their verified PR merge metadata, signed-merge verification, ancestry and exact implementation/worktree mode/blob/raw-byte checks. Ancestry alone remains insufficient. Verify this amendment’s Owner-merged adoption in that same authorized history; it adds no identity-schema field and never replaces `amendment_merge_sha` or `T_amend`.

Required signed merge objects must retain GitHub’s passing signature verification and authenticated association with the exact Owner-approved merged PR. A signature alone does not establish Owner approval, required-green checks, PR scope or merge identity. Do not replace any existing exact merge-time, evidence-byte or implementation-diff proof.

Perform the existing initial, pre-seal/prior-look and final checks with this replacement predicate. Unrelated main movement is not authority to substitute an execution SHA inside an invocation. All existing timing-dependent failures, consuming-negative rules and truthful-null exceptions remain unchanged. The absence of GitHub-enforced branch protection never waives independent final-head review, actual required-green checks, zero material findings or Owner merge.

## 5. Exact Render commands and one-shot containment

### 5.1 Only permitted service and configuration delta

```text
workspace_id       = tea-d9g2b1m7r5hc73e7ufk0
service_name       = atom-h2d3-benchmark
service_id         = srv-daa7thgae00c73a2lmn0
repository         = atomatom148-dotcom/ATOM
branch             = main
runtime            = native python
region             = oregon
plan               = 4c-8g
instances          = 1
autoDeploy         = no
autoDeployTrigger  = off
```

Do not create a new permanent service, cron schedule, workflow, disk, database or background loop; do not resize or modify another service. Preserve the existing build command `pip install -r requirements.txt`, using the separately reviewed exact dependency changes only. Preserve previews disabled.

After both merge gates, the Owner may configure only: the exact probe/base/job commands below and in §2.4; `PYTHON_VERSION=3.14.3`; the existing per-invocation `ATOM_V1B_AUTHORIZED_MAIN_SHA`; the §3 secret; the §6 replacement value for the existing reader URI, including their exact §2.5 removal/reinstallation sequence; and the exact deployment/suspension operations in this section. No generic environment replacement is authorized.

Remove the inspected stale service command:

```text
python -m quant.evidence_scorecard --recent-sessions 10; sleep infinity
```

It must not execute during V-1B setup or invocation. No sleep, polling loop, cron entry, queue consumer, scheduler, retry wrapper, shell continuation into E-1, or unattended restart into a new scorecard attempt is permitted.

### 5.2 Closed command registry

During all V-1B setup, provenance, invocation, recovery and cleanup operations, the base background service start command remains permanently inert and exactly:

```text
python -c "raise SystemExit(0)"
```

No scorecard command is ever stored as the base service’s start command. Each authorized scorecard command exists only in the explicitly created one-off job’s `startCommand`. From the verified repository root, that one-off `startCommand` is exactly one row below:

```text
python -m quant.volatility_scorecard --manifest-id v1b-early-4
python -m quant.volatility_scorecard --manifest-id v1b-family-5m
python -m quant.volatility_scorecard --manifest-id v1b-family-15m
python -m quant.volatility_scorecard --manifest-id v1b-family-30m
python -m quant.volatility_scorecard --manifest-id v1b-family-1h
python -m quant.volatility_scorecard --manifest-id v1b-v9-5m
python -m quant.volatility_scorecard --manifest-id v1b-v9-15m
python -m quant.volatility_scorecard --manifest-id v1b-v9-30m
python -m quant.volatility_scorecard --manifest-id v1b-v9-1h
```

These are alternatives for separate invocations, not a script to run all nine. Do not add an operator-selected date, session count, minimum, seed, horizon override, output-based retry or force flag. The registry, early-terminal prerequisite and deterministic boundary resolver remain exactly Amendment 2A’s.

Exact recovery uses the same selected command with exactly this existing suffix:

```text
--recovery-seal-file /tmp/atom-v1b-seals/<seal_record_sha256>.json
```

Replace the angle-bracket token with the retained record’s exact 64-lowercase-hex digest. A one-off job does not inherit the base service’s local recovery file. Therefore, for recovery only, its exact `startCommand` is the following local staging-and-exec template, not an assumption that the file already exists:

```text
python -c 'import os,sys; d="/tmp/atom-v1b-seals"; os.mkdir(d,0o700); p=d+"/<seal_record_sha256>.json"; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); f=os.fdopen(fd,"wb"); f.write(bytes.fromhex("<seal_bytes_hex>")); f.close(); os.execv(sys.executable,[sys.executable,"-m","quant.volatility_scorecard","--manifest-id","<manifest_id>","--recovery-seal-file",p])'
```

Only three substitutions are allowed: `manifest_id` is one exact registry value; `seal_record_sha256` is the original record’s 64-lowercase-hex digest; and `seal_bytes_hex` is the lowercase hexadecimal encoding of the entire original canonical seal file, including its final newline. The Owner-controlled launcher verifies those domains and the retained seal before submitting the command. Neither a credential nor any partial/result statistic may enter the command. The prelude creates a private directory and exclusive non-symlink file, refuses an existing directory/file, writes only those retained bytes, and replaces itself with the original scorecard invocation. It adds no scorecard option, environment variable, source file, network retrieval or dependency. It does not reconstruct seal fields or rehash a replacement identity.

The scorecard still independently performs every original §10.2 file/schema/hash/manifest check before repository or database access. A prelude failure or platform command-size limit authorizes no truncation, alternative payload source, automatic retry or new-seal fallback. Resolve the same retained-seal recovery under the existing failure/incident rules. No new durable store is created.

### 5.3 Actual-seal recovery-command capacity; no global seal maximum

Remove the previous `max_seal_bytes` prerequisite entirely. Implementation must not invent length/count caps for lineage strings, cohort traces, candidate sessions, identifiers, authority fields or any other seal member to make the recovery command fit. No field, row, event, candidate or scientific population is dropped, shortened, sampled or renamed for transport size.

Before evidence-capable activation, the Owner obtains and independently verifies an authoritative Render limit `L` in UTF-8 bytes of the usable one-off `startCommand`, for the exact Create job mechanism and complete launch path. Retain current official vendor documentation, an explicit API/control-plane limit disclosure or a Render support confirmation. An absent OpenAPI `maxLength` is not unlimited capacity. `ARG_MAX`, local shell success, an accepted smaller request and a guessed constant are not the vendor limit. If a provider states a character/request-body limit, the retained evidence must establish its exact conversion/applicability to this command; otherwise it is unverifiable. If transport/API and launch constraints differ, use the smallest verified usable capacity. The fixed margin remains exactly 4096 bytes. `C` in §2.6 carries that verified `L` and its evidence reference; the runtime does not fetch Render support or an unapproved website.

No numeric Render limit has been supplied by this amendment as an observed fact. Until the specified authoritative value and evidence exist, approval cannot be posted and evidence-capable activation is BLOCKED. This is the already requested vendor-capacity gate, not delegation of a scientific/schema bound to implementation. The probe and document/synthetic tests need no database access and do not create a seal.

For a new-seal invocation that has found its earliest READY candidate in its one frozen snapshot, complete all pre-inference validations, then construct the complete would-be seal in memory exactly as Amendment 2A §7.3 requires, including its unchanged self-hash. Let:

```text
S = canonical_json(complete would-be seal_record).encode("utf-8") + b"\n"
n = len(S)
C_recovery = exact §5.2 recovery startCommand rendered with:
             manifest_id = this invocation's validated M
             seal_record_sha256 = this would-be record's actual seal hash
             seal_bytes_hex = S.hex()
command_bytes = len(C_recovery.encode("utf-8"))
overhead_bytes = command_bytes - 2 * n
required_capacity_bytes = command_bytes + 4096
```

Use exact nonnegative integer byte arithmetic. Render the whole command, including every quote, space, pathname, source-code character, manifest ID, digest and the hex encoding of the final seal LF. Verify that parsing the template recreates exactly `S` and the original scorecard/recovery argv; the source template in §5.2 is the only template. No approximate “about 400 bytes,” global maximum, maximum-size lineage fixture or implementation-defined limit is used.

The exact gate is:

```text
command_bytes == overhead_bytes + 2 * n
command_bytes + 4096 <= L
```

Equality in the second line passes. One byte over fails. A complete would-be seal is only an in-memory candidate until this gate and every unchanged seal prerequisite pass. Do not emit it, write it to a file, create the recovery job, perform protected computation or claim a consumed identity merely to measure its size. On PASS, freeze these exact bytes; the next emitted consuming seal must be byte-identical `S`. Any later change requires rebuilding/rechecking the unconsumed candidate before emission, not emitting different bytes under the measured capacity. Emitting and successfully capturing that original canonical seal is still the consumption event; no human is inserted between seal and results.

If the limit/proof is unavailable, stale under a known vendor change or incompatible, if exact byte measurement of an otherwise schema-valid candidate cannot establish usable capacity, or if either equation fails, return BLOCKED before seal emission and require documentation-first recovery redesign. This narrow capacity-only refusal uses the existing Amendment 2A-amended V-1A §14.1 BLOCKED negative schema, its existing singleton reason code and existing official negative filename rules, with all three seal/readiness fields null; no key/status/schema is invented. `stage` retains its frozen literal. This expressly permits that one non-consuming authority refusal after the count-only scan, notwithstanding the ordinary after-read INVALID rule. Close/roll back the read-only snapshot. The complete canonical negative is written/retained by the same existing negative-receipt path; stdout contains only that complete negative plus LF, stderr is empty, and the command exits 1. No candidate seal, counts, partial results or ad-hoc debug record is emitted. A malformed/unencodable or otherwise schema-invalid seal and any separate, already established protocol/identity/causality/proof defect are not relabeled as capacity failure and retains the earlier applicable INVALID route.

HOLD, WAIT_FIRST_MANIFEST and usage-error behavior is unchanged and constructs no seal-size fixture. A later separately authorized new-seal retry scans the same anchored candidate sequence and must still select the earliest qualifying boundary; a smaller later boundary or shortened lineage is forbidden. A capacity refusal consumes no look but is not permission to invent a workaround.

For recovery, the retained original seal has already consumed its identity. Recompute the exact original command size and verify the current action-time vendor capacity before submission. Failure is not a fresh BLOCKED look: resolve the original consuming-negative/incident obligation under Amendment 2A §8.6. No smaller reserialized seal, compression, alternate payload file/source, new environment variable, new command template, new boundary or replacement identity is authorized.

### 5.4 Native one-off lifecycle; no continuous worker execution

The containment mechanism is one Render native one-off job attached to this exact existing base service, not an indefinitely running background-worker start process. This is the sole narrow exception permitting a transient execution instance derived from the existing benchmark service; it grants no new permanent service or autonomous launcher.

The Owner-controlled Render control plane launches the job. The scorecard receives no infrastructure token and cannot launch, repeat or suspend jobs itself. Use the existing 4c-8g capacity only, with no simultaneous benchmark daemon and no parallel V-1B job. Before launch verify the job will inherit the exact approved successful build `B` and configured environment under §§2.5–2.6, not merely the most recent deploy request. Keep that build selected until any consuming seal has its first complete terminal receipt; no rebuild or source-switch is a crash-recovery method. The runtime must still prove the original frozen service identity and actual execution SHA; an incompatible job identity is not relabeled to pass.

Keep the base service suspended except for any Render-required build/configuration preparation. Whenever the base service is resumed for such preparation, its start command remains exactly `python -c "raise SystemExit(0)"`; it is never replaced by E-1, a V-1B scorecard, recovery staging, sleep loop or another workload. The inert command performs no database or repository-authority access and no V-1B invocation. After preparation, verify suspension before creating a one-off job. If the exact build/configuration cannot be obtained while preserving this invariant, stop; do not resume a continuous scorecard worker.

Create exactly one job per authorized invocation; do not automatically retry a job-creation request with an uncertain outcome. Resolve the existing job identity/status through the control plane first. Before another invocation, inspect prior job completion, retained logs/seals and official receipts under the existing one-look rules. A crash, deployment event or lost API acknowledgement cannot authorize a replacement identity.

The job ends when the one-shot command exits. Capture the complete seal through the existing execution-log sink before protected calculation, and retain the first complete canonical evaluated or negative receipt and its hash before runtime teardown can destroy the only copy. Logging that complete frozen receipt after construction is permitted; logging partial protected values is not. Preserve exact HOLD/WAIT/usage outputs and their no-file requirements. No new receipt schema or automatic publication is introduced.

After every invocation, including HOLD, WAIT, usage failure, BLOCKED, INVALID or evaluated completion, verify that the job has terminated and that the base service is suspended with the inert base command still configured. A protective stop must cancel the running one-off job and suspend/verify the base service; suspending the parent alone is insufficient. Loss of a seal, result or execution-status proof follows the existing incident rules and never permits an unverified rerun.

After all authorized V-1B invocations have terminated, every manifest is either terminally recorded or otherwise closed by Owner decision, and independent review confirms that no hash-valid seal remains without a terminal receipt and no valid exact recovery remains pending, remove `ATOM_V1B_GITHUB_TOKEN` from Render and revoke the dedicated fine-grained PAT in GitHub. Retain non-secret evidence of Render-secret removal and PAT revocation in the operational closure record. This cleanup is mandatory on normal completion, not only rollback. If a valid recovery remains pending, the token may persist only for that bounded recovery window and may not be used for unrelated work; removal and revocation are immediate once the final recovery obligation closes.

## 6. One same-role password rotation; exact URI invariants

### 6.1 Private incident lifecycle and actual blast radius

The authoritative private incident record is exactly:

```text
ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06
```

It is a security/operations record in the existing Owner-held private V-1B acceptance packet, not a repository path, Render secret file, database evidence row or runtime input. The packet already retains control-plane/seal material under this amendment; no new cloud store or runtime network source is created. Retain an initial and subsequent finalized canonical record version under that same incident ID; do not overwrite the initial facts. The packet records the exact private locator and access custodian, disclosed to the independent incident/acceptance reviewer, not to the public PR. A logical ID without a real retained record and a reviewer-accessible private locator is not completion. The public amendment neither asserts that this packet has already been finalized nor invents an exposure vector.

Initial pre-rotation state. Before the authorized rotation, create/retain the record with:

```text
incident_record_id = "ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06"
rotation_status = "PENDING"
rotation_completion_timestamp = null
record_status = "OPEN"
```

Include the verified exposure vector; first-known and discovery timestamps; earliest-possible exposure bound when earlier exposure cannot be excluded; every known secret-bearing artifact/location and its actual disposition (redacted, removed, access-restricted or necessarily retained); actual disposition timestamps/control planes; evidence sources, uncertainty and access-review coverage. Unknown values are explicitly unknown, not fabricated dates. Do not copy the password, verifier, full URI or secret-bearing artifact into the incident record. Record only a secure locator for an artifact that must remain restricted. The initial exposure window is open-ended; a planned rotation time is not its closing bound.

PENDING with a null completion timestamp is the required valid initial state, not a contradictory missing-finalization defect. It permits the separately authorized protective/rotation work but never evidence-capable V-1B activation. A failed or uncertain rotation leaves it PENDING with the observed failure/uncertainty appended; it cannot be marked completed from an intention, a submitted request or a job-start timestamp.

Mandatory post-rotation finalization. After the one actual successful password change, append the actual confirmation source and its measured UTC timestamp. Set `rotation_status = "COMPLETED"` and `rotation_completion_timestamp` to that actual confirmed-completion timestamp, not a placeholder, anticipated value, earliest exposure time or document date. The exact timestamp source is the secure control plane’s successful password-change completion event; when the exact psql route in §6.3 is used, it is the server-clock observation returned immediately after acknowledged COMMIT. That latter timestamp is explicitly an observed completion upper bound, not a claim to know an unavailable internal commit instant. Preserve that distinction in the private timeline. Record the conforming Render URI update confirmation separately; it is not the password-change time.

Complete the artifact dispositions and the bounded investigation below, recording retained-artifact access controls/retention reasons and any telemetry gaps. Append the final record version with `record_status = "FINALIZED"`, actual independent reviewer/Owner disposition and non-secret evidence references. PENDING initial records remain retained. The finite old-password new-authentication exposure window ends at confirmed invalidation; this alone does not close pre-existing authenticated sessions or erase already disclosed data. Record separately when any such sessions ended or were lawfully contained. Unknown pre-existing-session exposure is not silently assigned the password timestamp.

Evidence-capable activation requires the real finalized version, COMPLETED/non-null actual rotation timestamp, the updated conforming URI, and independent acceptance of the documented incident disposition. §2.6 exposes only the opaque incident ID/finalization digest/completion timestamp and approval, never private incident contents. Missing finalization, uncertain invalidation or an unresolved wider-privilege/active-abuse finding blocks activation. Limited historical telemetry may be recorded and explicitly dispositioned by the Owner; it cannot support an assertion that no abuse occurred.

Privilege finding preserved precisely. The frozen/catalog-verified role remains LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS, with no reader memberships, no database/non-system-schema CREATE and no durable-table INSERT/UPDATE/DELETE/TRUNCATE path under the V-1A checks. Preserve the established no-durable-table-mutation/no-BYPASSRLS finding for the verified state; do not expand a point-in-time check into an unverified claim about every instant of the exposure window.

The role does have effective database TEMPORARY through PUBLIC. That is explicitly allowed by V-1A §§13.3 and 15.3 and is unaffected by NOINHERIT or absence of role memberships. Thus the exposure is not limited to confidentiality: an unauthorized session might create/use temporary objects and consume temporary storage, sort/spill space, connections, locks, CPU, memory or other availability resources. Existing SELECT and permitted proof-function access can also consume resources. A malicious client is not constrained merely because the legitimate scorecard chooses a read-only transaction. The legitimate scorecard still must prove `pg_my_temp_schema() = 0`, no temporary objects, all existing privilege/SECURITY DEFINER checks and a single read-only REPEATABLE READ snapshot. Do not revoke PUBLIC TEMPORARY, change role attributes or add restrictions under this incident-documentation grant.

The incident reviewer must examine available authentication/session records, temporary-object/storage metadata, connection occupancy, resource/availability telemetry and any anomalous permitted-function use for the bounded exposure and surviving-session window. Include temporary-relation creation/use, temp-file growth, disk/storage pressure, long-lived/idle transactions, lock/wait effects and connection exhaustion; investigate any separately reachable storage interface rather than infer its absence from table ACLs. Separate role-attributed observations from database-wide counters. No log gap or absent current temporary object proves absence of past abuse. Preserve the distinction between temporary/resource abuse and a previously absent durable-table write/BYPASSRLS privilege.

Only read-only incident investigation through the Owner’s existing administrative audit channel is authorized. It may inspect role/ACL and connection/temporary-object/resource metadata; it may not run an abuse demonstration, create a temp table, fill storage, acquire test locks, change privileges, delete evidence or score a research population. An identified write/BYPASSRLS/membership expansion, unexplained active session or wider compromise is a separate material incident; use existing protective-stop authority and separate explicit remediation authority, not an improvised repair in this PR.

### 6.2 Rotation

After the required merges and before any V-1B connection, authorize exactly one password rotation for:

```text
project         = afyiydxbjgzaiswnbcyj
database        = postgres
role            = atom_e1_scorecard_reader
Render variable = ATOM_E1_SCORECARD_READONLY_DATABASE_URL
Render service  = srv-daa7thgae00c73a2lmn0
```

The Owner uses an existing privileged, project-verified administrative channel outside the scorecard runtime. Verify the exact project/direct target before transmission. Change only that existing role’s password; create no role, membership, grant, policy, default privilege, database object, evidence mutation or password-containing repository migration. The scorecard itself receives no administrative capability.

Generate a fresh high-entropy password and transmit/store it only through secure credential channels. No exposed password or password verifier is copied into this amendment, a command history, SQL/script file, log, ticket, fixture, receipt or source repository. The rotation mechanism must not expose the new password through SQL/error/audit logging. Rotation never requires authenticating with or disclosing the old password.

Update only the password component of the already TLS-conforming existing Render URI. Where the earlier authorized pinned-CA URI update has not yet been applied, perform that exact existing TLS Amendment 1 update as well; it is not a second TLS choice. The final accepted URI preserves exactly:

```text
host         = db.afyiydxbjgzaiswnbcyj.supabase.co
port         = 5432
database     = postgres
user         = atom_e1_scorecard_reader
sslmode      = verify-full
sslrootcert  = certs/supabase-prod-ca-2021.crt
sslcertmode  = disable
require_auth = scram-sha-256
gssencmode   = disable
```

The pinned CA remains exactly 1,367 bytes with SHA-256:

```text
700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7
```

Preserve all original raw-query, duplicate, exactly-once decoding, dual-parser, `PQconninfo`, explicit URI-password, no-ambient/no-file/no-argument, certificate, SCRAM, GSS and no-pooler rules. The rotated password is percent-encoded only as necessary for URI userinfo; no other URI identity or security value is substituted.

The exposed password may never be restored, reused, retained as a fallback, installed in another environment or included in a rollback. If the new password or Render update fails, keep the worker suspended and correct provisioning of that same new credential without reverting the database password. A second password replacement is not authorized by this one-rotation grant. An uncertain rotation outcome must be resolved through the secure control plane, not by guessing, repeating the rotation or trying the exposed password.

After confirmed rotation, complete the mandatory §6.1 finalization with the actual timestamp and Render-update evidence before activation. Later connection/authority acceptance uses only the new credential and the frozen direct-host TLS/reader checks before evidence access. This amendment phase itself performs none of those connections or checks.

### 6.3 Exact secure administrative action; no runtime administrator

This subsection closes the previously generic “administrative channel” for the one rotation. It authorizes only the Owner’s existing direct PostgreSQL administrative credential, supplied through a private interactive prompt on the Owner’s administrative terminal. It does not provision a new administrative credential, put it in Render, use the V-1B PAT for PostgreSQL, or allow a pooler. The terminal is not the scorecard/probe process. Its recorded working directory is the verified implementation repository root containing the exact pinned CA; no `.pgpass`, service file, `.psqlrc`, PG/SSL target override or client-certificate fallback is used.

Exact command, containing no password:

```text
psql -X -W -v ON_ERROR_STOP=1 --dbname='postgresql://postgres@db.afyiydxbjgzaiswnbcyj.supabase.co:5432/postgres?sslmode=verify-full&sslrootcert=certs/supabase-prod-ca-2021.crt&sslcertmode=disable&require_auth=scram-sha-256&gssencmode=disable'
```

Only for this separately authorized administrative rotation connection, the password is taken from psql’s forced private prompt rather than URI userinfo. This is an explicit administration-only exception to the incorporated URI-password-source requirement; V-1B and conditional migration 033 keep their existing credential-source rules unchanged. All target, CA, certificate-chain/hostname, SCRAM and GSS values remain exact. No client incapable of enforcing this tuple may be substituted. The Owner must already control a client/administrative channel that protects cleartext and password verifiers from session recording, history, exceptions and SQL/audit-log disclosure; no logging-policy change or new administrator is authorized to manufacture that capability.

The initial private incident record must be PENDING/null. After connecting, the Owner verifies `session_user = current_user = postgres`, `current_database() = postgres`, the direct endpoint and active certificate-verified TLS. The exact non-secret SQL identity query is:

```sql
SELECT session_user, current_user, current_database(),
       (SELECT ssl FROM pg_catalog.pg_stat_ssl
        WHERE pid = pg_catalog.pg_backend_pid()) AS tls_active;
```

Any mismatch stops before the password mutation. The Owner then executes, in this order, in that same private session:

```text
BEGIN;
SET LOCAL password_encryption = 'scram-sha-256';
\password atom_e1_scorecard_reader
COMMIT;
SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC',
               'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS rotation_completion_observed_at_utc;
\q
```

The `\password` inputs are the same fresh high-entropy password twice in its private prompts; never the exposed password. PostgreSQL documents that `\password` encrypts the value before submitting `ALTER ROLE` and avoids cleartext in command history/server logs. That is not a promise that every external session recorder or audit configuration suppresses sensitive verifiers; the preceding secure-channel requirement remains mandatory. No returned/printed password or verifier is acceptance evidence.

Only an acknowledged successful COMMIT and the actual subsequent server-clock output (or an authoritative control-plane completion event if the acknowledgement is lost) support COMPLETED. For an uncertain commit, keep PENDING and resolve the one actual action through secure administration; do not rerun `\password`, try the exposed password, or assert a planned timestamp. A confirmed unsuccessful transaction leaves no completed rotation and no activation. The already-authorized one rotation means one confirmed password replacement, not permission to rotate repeatedly while debugging. Reinstall the confirmed new URI in the exact Render variable using Save only; finalize §6.1 afterward. A missing secure administrative capability is an explicit setup block, not an implied alternative tool.

### 6.4 Bounded incident inspection path

The Owner/reviewer uses the existing private Supabase administrative audit/log interface for project `afyiydxbjgzaiswnbcyj`, and, when current metadata is needed, the same verified direct administrative connection as §6.3 in a separate read-only transaction. No secret-bearing query text, log body or incident locator is copied into public PR comments. Restrict the audit’s time filter to the recorded exposure/surviving-session window; unknown lower or upper bounds are explicitly recorded as such. Inspect only existing records; no new instrumentation, load test or evidence query is installed by this amendment.

The following concrete metadata queries are authorized after the documentation/implementation gates solely for this security investigation, never for V-1 readiness. They read no six-table research evidence and do not invoke proof readers:

```sql
BEGIN READ ONLY;
SELECT pid, backend_start, xact_start, query_start, state,
       wait_event_type, wait_event
FROM pg_catalog.pg_stat_activity
WHERE usename = 'atom_e1_scorecard_reader'
ORDER BY pid;

SELECT c.oid, n.nspname, c.relpersistence
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_roles AS r ON r.oid = c.relowner
WHERE r.rolname = 'atom_e1_scorecard_reader'
  AND c.relpersistence = 't'
ORDER BY c.oid;

SELECT datname, numbackends, temp_files, temp_bytes, deadlocks, stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = 'postgres';
COMMIT;
```

These outputs are private, point-in-time indicators, not proof of historical non-use or role attribution for database-wide counters. The existing audit interface supplies the historical connection/storage/resource evidence and its exact coverage gaps. Inspecting existing role/ACL snapshots uses the already frozen V-1A §15.3 catalog proof, without widening it or substituting that snapshot for historical evidence. Any further administrative mutation, session termination, grant change, storage cleanup or logging-policy change requires its existing separate protective/Owner authority; no such action is hidden in these read-only queries. Missing telemetry is recorded, not “repaired” by reproducing an attack.

## 7. Direct-host IPv4 add-on; separate cost gate

Authorize the dedicated Supabase IPv4 add-on for project `afyiydxbjgzaiswnbcyj` only, conditional on a separate affirmative Owner confirmation immediately before the billable action.

At action time, the operator must show the exact project, whether the add-on is already enabled, the vendor’s then-current incremental hourly/monthly cost and billing basis, the applicable replica/other charges, and any required plan change or connection disruption. Obtain an explicit Owner confirmation for that exact quoted action. This amendment is not cost confirmation, does not freeze a remembered price and does not authorize an organization-plan upgrade, replica or other add-on. If already enabled, do not purchase it again.

If approved and absent, enable only that project’s dedicated direct-database IPv4 add-on. Preserve the DNS hostname and entire §6 tuple. IPv4 changes transport reachability, not database identity, TLS hostname verification, source eligibility or authority.

After propagation, verify the same direct hostname resolves to a usable IPv4 address and the later approved invocation passes the pinned-CA `verify-full` connection checks. Do not replace the URI hostname with an IP literal, add `hostaddr`, edit `/etc/hosts`, use a proxy, substitute Supavisor/PgBouncer, choose a different port, weaken TLS or move to another project. No static IP literal becomes a new frozen identity. Connection/catalog verification is later setup/execution work, not work performed in this documentation phase.

Any inability to confirm price, enable the approved add-on or establish the exact direct connection remains a blocker; it is not authority for an alternative route. This grant does not enable IPv4 for HIST8’s separate project `pjbjpgnmniwcajqkuhge`. HIST8 remains outside PR #325 and receives no connectivity, TLS, credential, migration or execution authority from this amendment. Any dedicated-IPv4 authority for HIST8 requires a separate documentation-first follow-on amendment under HIST8’s own controlling corpus law, with its own action-time cost confirmation and exact direct-host/no-pooler constraints. Do not add that follow-on decision or any HIST8 path to PR #325.

## 8. Exact operational and repository rollback

Before setup, retain a non-secret action-time configuration record: deployed commit, command, build command, plan, instance count, runtime, region, branch, auto-deploy/previews state and presence/value of non-secret variables being changed. Record secret names and provisioning state only; never snapshot a credential value or the exposed URI. This operational record is not a statistical receipt or a new required schema.

Rollback is exactly:

1. Cancel and verify termination of any running V-1B one-off job; suspend and verify the named base service. Preserve every seal, complete receipt and required log. Classify a crossed seal only through existing Amendment 2A rules. Keep its exact build and retained seal available until recovery produces the first complete terminal receipt or the consuming-negative/incident obligation is lawfully closed; cancellation alone does not erase a pending look. Protective cancellation/revocation may occur immediately, but does not authorize replacing that build or claiming recovery eligibility was restored.
2. Restore the action-time non-secret configuration only while the base service remains suspended. The base command remains exactly `python -c "raise SystemExit(0)"`. Do not restore the historical E-1 command even as a suspended configuration value during V-1B rollback; any later return to E-1 is outside this amendment. Restore the previous `PYTHON_VERSION`/authorized-SHA presence and value if those fields were changed, without launching the reverted runtime. Leave all untouched settings untouched.
3. Remove the newly added `ATOM_V1B_GITHUB_TOKEN` from this service and revoke that dedicated PAT through the Owner’s secure control plane. Do not install another token or credential fallback. This is the rollback path for the same cleanup independently required on normal completion by §5.4.
4. Keep the newly rotated database password and its conforming reader URI. The exposed password and obsolete TLS configuration are excluded from restoration, including a platform’s automatic environment rollback. If a safe URI cannot be retained, remove the URI and remain suspended rather than restoring the exposed credential.
5. Repository rollback follows Amendment 2A §10.3 exactly: a separately reviewed revert of only the verified V-1B implementation merge’s first-parent diff on then-current `main`. Never reset history or revert a later per-invocation head containing receipts. Preserve all freezes, this amendment, the eight evidence files, seals and receipts. A non-clean revert requires a reviewed rollback plan; no unrelated refactor or ad-hoc privilege rollback.
6. Do not automatically disable an IPv4 add-on already relied on by other direct clients. Disabling the newly enabled project-wide add-on requires a separate Owner instruction after connection-impact and billing confirmation. It is not a means to restore an old password or erase a consumed look.

A Render rollback that would replay the old command, restore an exposed secret, lose retained evidence or start an unauthorized runtime must not be invoked. A suspended service with the rotated credential retained is the safe rollback state; rollback never restores research eligibility.

## 9. Implementation, review and acceptance requirements

The exhaustive later implementation surface remains exactly:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
requirements.txt
certs/supabase-prod-ca-2021.crt
```

`migrations/033_authorize_v1_volatility_scorecard_reader.sql` remains conditional on the original privilege proof/collision rules and is never used for rotation or incident logging. The calendar dependency restriction and exact CA bytes remain unchanged. No helper module, launcher service, workflow, generic framework, credential alias, runtime provenance file or new third-party dependency is authorized. The module supplies only its existing scorecard CLI and the explicitly named §2.4 probe entry point; the Owner’s control-plane operations are not a new autonomous launcher.

Retain every applicable V-1A/TLS/2A test. Within the existing test module add focused synthetic tests for:

1. Exact probe command/entry point, absent-versus-empty secret-key rejection, no environment fallback, no connection/network/evidence/dispatch output, complete common import/hash closure, exact JSON/file/stderr/exit rules and truncated-output rejection. Test that the probe and evidence-capable mode cover identical artifact bytes without using a CPU-specific probe dispatch baseline.
2. Authenticated same-build provenance; build-producing deploy identity rather than a fictional environment field; secret removal before Create job; Save-only reinstallation without rebuild; group/key reappearance rejection; stale/changed build rejection; immutable build retention while recovery is pending.
3. Exact §2.6 comment schemas and canonical hashes, Owner envelope identity, prior independent-review binding, complete safe pagination, duplicate/missing/edited approval rejection, and fixed metadata source. No acceptance fallback on API refusal or private repository. Provenance/readiness/run/receipt binding and sealed CPU/artifact drift retain exact negative routing.
4. All nine exact manifest commands and the exact recovery template. Render/parse actual complete synthetic seals including their final LF; prove hexadecimal doubling and all wrapper bytes are counted. Test `command_bytes + 4096 == L` passes, one byte more fails, and missing/unverified limit fails before emission. Test long legal lineage/cohort fields without inventing caps, no truncation, no later-boundary substitution, unchanged successful seal bytes, the narrow new-seal capacity BLOCKED exception and consuming recovery failure. Do not assert a finite maximum seal size.
5. Retained PAT scope proof, missing/extra permissions, secret-redaction behavior and normal-completion removal/revocation, not just rollback. URI/password changes preserve the exact target/TLS tuple and never restore the exposed password.
6. Initial incident PENDING/null state permits rotation but blocks activation; uncertain rotation cannot finalize; actual completed timestamp and finalized record are mandatory. PUBLIC TEMPORARY is correctly acknowledged while legitimate scorecard temp use remains forbidden. Rollback keeps the base inert and preserves every seal/receipt/incident version.

A local test command is `python -m pytest -q tests/test_volatility_scorecard.py` in the already authorized development/test environment with synthetic credentials/evidence only. The repository’s actual required CI checks and their existing commands remain mandatory; no check workflow or dependency is altered to make them green. These tests do not constitute a live provenance probe or operational acceptance.

Before an evidence-capable job is created, independent operational acceptance must have the successful credential-free probe, authenticated exact-build/source proof, approved §2.6 record, authoritative vendor capacity, PAT scope evidence, finalized incident, securely configured exact URI and any separately approved IPv4 action. Launching that closed command is not acceptance of a database connection or authority to read evidence. During its ordinary initial repository phase, that invocation proves every required authenticated read using the restricted PAT; it then passes the exact URI/TLS and one-snapshot database-authority checks before evidence reading. No circular requirement demands a prior unlisted token/connection-test job; no trial protected evaluation is a connectivity test. Setup data may contain catalog/authority facts but no research-population counts or statistics.

No separate unlisted “preflight CLI” is assumed. The non-consuming probe is §2.4. The evidence-capable CLI is §5.2 and its frozen ordering is the authority/connectivity gate before evidence reads. Owner-controlled external checks use only the explicit control-plane paths in Appendix A. A runtime failure of those pre-read gates yields the existing BLOCKED negative without a consuming seal.

The corrected documentation PR and separate implementation PR both require fresh independent review on the exact final head, every actual required check green, zero unresolved P1/P2/material findings and Owner-only merge. The full corrected documentation replaces the same sole PR #325 path; earlier-head badges do not satisfy either gate. Any new head invalidates earlier final-head approval. ChatGPT Pro authors and audits; Codex owns the narrow implementation, tests, commits and PR preparation. No deadline, self-review, inherited generic merge permission or successful mock may bypass Owner merge or actual check evidence.

Each subsequent receipt remains its own documentation-only PR adding exactly one immutable official-schema JSON at its frozen path, with exact-head independent review, green checks, zero material findings and Owner merge. Neither an operational approval comment nor this document is such a receipt.

## 10. Explicit preservation and re-entry

Preserve every V-1A and Amendment 2A formula, numerical operation/order, target, benchmark, threshold, classification, global 12-cell multiplicity, nine-manifest membership, full-session convention, strict candidate/causal cutoff, earliest-boundary rule, all six minima, lineage/cohort reset, calibration law, bootstrap/RNG stream, seal-before-results rule, one-look rule, recovery identity, negative-receipt/null-identity rule, nonselective continuation duty and receipt rule except the explicit prerequisite comparisons in this amendment.

In particular, the exact 1H 121-window/21-full-session necessary lower floor remains necessary and not sufficient. No change is authorized to V9/Q3 mathematics, existing source primitives, SIM, HIST8, evidence capture or cadence, V-1C, V-2, implied-volatility comparison, trading, broker access, risk limits or capital. Operational availability is not statistical `READY` and not evidence of profitability.

The re-entry order is:

```text
this one-file documentation amendment
→ independent final-head review + green required checks + zero material findings
→ Owner merge
→ separate Codex V-1B implementation and exact-head acceptance
→ Owner implementation merge
→ Owner-controlled inert/secret-free build and exact provenance probe
→ independent build acceptance and verified vendor capacity
→ action-time IPv4 confirmation when needed, scoped PAT and actual rotation
→ secure Save-only provisioning and finalized incident
→ independent operational review and Owner approval metadata
→ exact authorized one-off invocation; unchanged readiness and exact actual-seal capacity gate
→ original successful seal and unchanged protected calculations
→ verified job termination and worker suspension with inert base command preserved
→ when no valid recovery remains pending: remove Render PAT secret + revoke dedicated PAT
→ unchanged receipt publication and final audit
```

Appendix A closes the operational action/input/output paths; Appendix B specifies failure and lifecycle simulation cases; Appendix C maps review findings and records the limited contradiction scan. They are part of this complete amendment, not permission to implement an unspecified follow-on mechanism. If the required work cannot fit these exact boundaries, stop for a documentation-first decision. HIST8’s IPv4 issue is explicitly deferred to a separate follow-on amendment and is not part of PR #325. Tuesday’s deadline supplies priority, not permission to weaken proof.

## Appendix A. Complete operational action and data-path ledger

### A.1 Control-plane catalogue

All network actions in this catalogue are Owner-controlled operations outside the probe and scorecard, except the exact read-only GitHub operations expressly assigned to the scorecard. They use the Owner’s existing authenticated vendor/connector session or already-held administrative capability. No new Render/Supabase control-plane API key, runtime environment alias or credential-bearing shell command is authorized. A connector must actually support the stated action; an unavailable action is not implemented by an imagined tool or a broader credential. The Owner may use the corresponding existing authenticated vendor interface. The exact HTTP method/path/body below define the operation independently of a client’s UI spelling. No credential value or Authorization header belongs in the retained action record.

`SVC = srv-daa7thgae00c73a2lmn0`; the Render workspace is always `tea-d9g2b1m7r5hc73e7ufk0`. Only the following Render operations are authorized for this workflow:

| Action | Exact operation and input | Accepted output / rejection |
|---|---|---|
| Inspect parent | `GET https://api.render.com/v1/services/SVC` | Exact service/workspace, native Python, repository/main, 4c-8g, one instance, auto-deploy/previews off, command and suspended state. Wrong/missing state blocks launch. |
| Make parent inert | In the same service’s Settings, set Start Command to exactly `python -c "raise SystemExit(0)"`; save without running a scorecard. This corresponds to Update service’s start-command setting only. | Read back the literal command. No E-1, sleep or scorecard is ever the saved parent command. |
| Suspend / narrowly resume | `POST https://api.render.com/v1/services/SVC/suspend` or, solely for §2.5’s necessary build preparation, `POST .../resume`, with no command/credential input body. | Acknowledgement followed by service-state readback. Resume never changes the inert command and is followed by suspension before a job is created. |
| Remove one secret | `DELETE https://api.render.com/v1/services/SVC/env-vars/ATOM_E1_SCORECARD_READONLY_DATABASE_URL` and separately the same path ending `ATOM_V1B_GITHUB_TOKEN`; equivalently delete the two keys in Environment and Save only. | Confirm both effective keys absent, including group/injection checks. A direct-variable deletion is not proof about linked groups. No secret-value output is retained. |
| Set one allowed variable | Service Environment → the exact allowed key → the specified value → Save only. The corresponding single-key API is `PUT .../env-vars/{exact_key}` with only `{"value": <the authorized value>}` through the private control plane. | Confirm key/provisioning state privately. For non-secret Python/SHA values record exact value; for secrets record no value/digest. No bulk environment replacement. |
| Build exact source | `POST https://api.render.com/v1/services/SVC/deploys` with `{"commitId": E, "clearCache":"clear"}`. No `deployMode`, image, branch, dependency or command override is added. | Retain actual returned deploy ID; retrieve it and successful-build evidence, verify `commit.id = E`. A queued request or different-source build is not acceptance. Cache clearing introduces no dependency choice or source change. |
| Identify successful build | `GET .../services/SVC/deploys/{B}` and service deploy-history reads, with returned pagination cursors followed. | Authenticated successful **build-producing** deploy `B` and no intervening newer build between approval and job creation. The job API is not assumed to expose a `buildId`. |
| Create exactly one job | `POST https://api.render.com/v1/services/SVC/jobs` with exactly `{"startCommand": Q}`; `Q` is the literal §2.4 probe, one literal §5.2 normal command, or the exact validated §5.2 recovery template. | Actual response `id = J`; retain request and response. Omit `planId` to inherit the unchanged 4c-8g base plan. There is no per-job env override, arbitrary build selector, schedule or retry parameter. |
| Resolve / monitor job | `GET .../services/SVC/jobs/{J}`; for an uncertain creation acknowledgement, `GET .../services/SVC/jobs` with actual pagination, correlated to the authorized request/creation window. | Resolve the existing job before any further POST. A pending/running/unknown status is not terminal. Manual control-plane status checks are not a runtime polling loop. |
| Capture job output | Existing Render job log stream / One-off Jobs view for actual `J`, or the already available Render log reader with `resource=[J]`. Follow its returned log continuation metadata to completeness. | Retain exact application message bytes after separating platform timestamp/envelope metadata; do not alter canonical JSON/LF content. Truncation or loss is failure, not reconstructed output. |
| Cancel running job | `POST .../services/SVC/jobs/{J}/cancel`, then retrieve `J`; separately suspend/read back parent. | Both terminal job and suspended/inert parent must be proved. Suspending the parent alone does not stop a job. |

The allowed GitHub operational writes are the exact §2.6 review/approval comments and the already authorized documentation/implementation/receipt PR workflow, performed through the Owner/reviewer’s own connection. The read-only runtime PAT cannot perform a write. Runtime reads are the original authenticated repository/PR/commit/blob/receipt history plus the fixed §2.6 PR #325 comment collection. No URL in a record becomes a runtime fetch target.

The allowed Supabase IPv4 operation is through the existing Owner-authenticated project Add-ons interface, or the equivalent verified management endpoint:

```text
GET   https://api.supabase.com/v1/projects/afyiydxbjgzaiswnbcyj/billing/addons
PATCH https://api.supabase.com/v1/projects/afyiydxbjgzaiswnbcyj/billing/addons
body = {"addon_variant":"ipv4_default","addon_type":"ipv4"}
```

The PATCH is permitted only after §7’s separately recorded affirmative action-time cost/impact confirmation and only when the add-on is absent. An already-enabled add-on requires no purchase. No `SUPABASE_ACCESS_TOKEN` or other administrative variable is created in Render, and no management call is made by the scorecard. Existing direct DNS resolution/TLS verification uses the original hostname, never an IP substitution. The corresponding HIST8 project action is explicitly not authorized. Disabling IPv4 is not in this sequence without §8’s separate Owner instruction.

### A.2 Sequence ledger: inputs, authority, environment, output, failure and lifetime

The entries below cover each new prerequisite and its place in the existing program. A step may consume only an input whose source is named here or in its cited normative clause. No field comes from a model’s memory, a guessed future number or a default credential search.

| Step and command/action | Exact inputs and authority source | Data and environment path | Output / failure route / lifetime |
|---|---|---|---|
| **A0 — Documentation adoption**: update only the named PR #325 file; independent review/checks; Owner merge | This complete document; exact current PR head; actual named checks and independent review from GitHub | GitHub repository metadata/worktree, no Render/Supabase input | New reviewed/merged SHA only after gates. A draft/hash is not approval. Any new head requires fresh review. No runtime action. |
| **A1 — Separate Codex implementation**: existing allowed files and `python -m pytest -q tests/test_volatility_scorecard.py`, plus unchanged required CI | Owner-merged Amendment 3, V-1A/TLS/2A, exact implementation source | Synthetic/local test data only; no production URI/PAT or evidence | Tests, exact diff and implementation PR; failures block that merge. Owner merge fixes implementation identity; no PR self-merge. |
| **A2 — Record incident initial state**: create/retain §6.1’s initial private version | Actual known exposure facts, restricted original artifact locators, Owner incident authority | Existing private acceptance packet; no runtime file/env/network read | PENDING/null/OPEN with uncertainty and dispositions; retained, not overwritten. This permits authorized rotation, never activation. |
| **A3 — Contain and sanitize parent**: A.1 inert/suspend/remove operations | Exact service ID; existing Owner control plane; current configuration readback | Both URI and PAT absent from effective configured environment and the build; no group/file fallback | Non-secret absence/inert/suspension proof. Missing proof → setup BLOCKED; no probe. No other service/group edit. |
| **A4 — Build**: A.1 exact deploy request | Authenticated `E`; frozen Python/dependencies/build command; no pending valid recovery | Existing Render build system, reviewed source, secret-free configuration | Actual build-producing `B`, successful-build/source evidence. Failed/different/ambiguous build → BLOCKED. Keep `B` selected. |
| **A5 — Probe**: exact §2.4 command in Create job only | Same `B`; documented local Render identity; local runtime/artifact files; no arguments | No URI/PAT, stdin, network, approval file, database or evidence | One exact probe JSON/LF, no file/stderr, exit 0; exact handled failure/usage outputs otherwise. Capture actual `J`, terminate and verify suspension. Never consumes a seal. |
| **A6 — Provenance approval preparation**: build `P` from observation and authenticated `B` | Complete successful probe, independent build/source review, original canonical hashes | Existing private acceptance packet; public mirror contains only defined non-secret fields | Approved artifact candidate; no process can approve its own hashes. No dispatch baseline. Wrong/absent evidence → BLOCKED, not a new runtime baseline. |
| **A7 — Vendor capacity and IPv4 cost gates**: obtain authoritative `L`; A.1 Add-ons action only after §7 confirmation | Current authoritative Render limit evidence, exact positive byte `L`; separate Supabase project-specific quote/impact approval | Owner/vendor control plane only; no runtime API credential or website fetch | Retained evidence and `C`; absent/ambiguous `L` blocks evidence-capable activation. Cost not confirmed → no purchase. Neither supplies an evaluation boundary. |
| **A8 — Scope PAT and rotate database password**: GitHub fine-grained-token settings with §3 permissions; exact §6.3 private psql action | Existing Owner accounts/admin privilege; PENDING incident; fresh password from secure private generator; exact CA/target | PAT later stored only in named Render secret; admin/new DB password only secure prompts/control plane; no runtime admin token | Non-secret scope record; one confirmed password replacement and actual completion timestamp. Failure/uncertainty stays PENDING and suspended. Never test/reinstall old password. |
| **A9 — Provision and finalize**: Save-only values for the two exact keys; append final incident record | Same verified `B`, scoped dedicated PAT, confirmed rotated URI, actual timestamp/update receipts, §6.4 investigation | Render secret storage plus private incident packet; no new build, file/alias or secret in source | Finalized incident and secure-provisioning proof. Wider privilege/uncontained active abuse or missing finalization → BLOCKED. Preserve initial incident version. |
| **A10 — Publish operational approval**: exact §2.6 reviewer comment then Owner comment | Completed `A`, canonical digest, actual independent review ID/author and source `E` | Existing authenticated GitHub PR #325 metadata; runtime later uses only read-only PAT | Unique immutable Owner approval/review binding; comment IDs from actual responses. No main commit/rebuild required, no new repository file. Missing/edited/duplicate → failure route in §2.3. |
| **A11 — Normal manifest launch**: one exact §5.2 command in Create job | Actual Owner invocation authorization, `M`, then-current exact `E`, same approved `B`, accepted `A` | One new job’s native snapshot; URI/PAT only exact Render variables; no parent daemon | In-process argument/history/provenance/byte/token checks first. Deferred no-first-receipt → exact WAIT and no DB. Other pre-read failures → existing BLOCKED negative. No unauthenticated/API-scope workaround. |
| **A12 — Connect and count-only scan**: existing normal CLI, no extra preflight command | Exact URI/CA; initial authority; original one-snapshot population/lineage rules | One read-only REPEATABLE READ connection. Its first DB operation obtains original `scan_started_at`; full authority proof precedes evidence-table reads | Earliest READY candidate or exact HOLD. No protected metrics/bootstraps. Normal after-read defects → PRE-CELL INVALID. No separate connectivity snapshot or latest-state substitute. |
| **A13 — Actual-seal transport gate**: in-memory §5.3 rendering | This invocation’s complete schema-valid candidate seal `S`, actual `M`/hash, approved current `L` | Same process/snapshot, exact UTF-8/LF bytes; no file/network/protected output | Exact integer inequality. PASS permits only identical seal bytes. Capacity-only FAIL → existing null-seal BLOCKED negative/exit 1; no consuming seal. Invalid seal/protocol defects retain INVALID. |
| **A14 — Consume and evaluate**: existing seal emission and frozen evaluator | Successful gate, exact `S`, unchanged V-1A/2A prerequisites | Same process/snapshot and existing execution-log sink | Successful complete captured seal consumes one identity. Then original calculations only. Final source/runtime/authority rechecks; first complete evaluated or consuming-negative receipt retained, never result-selected. |
| **A15 — Crash/recovery**: original §5.2 recovery template, no new mode | Original retained canonical seal including LF; actual sealed identity; same retained `B` and approved source; current ancestor/prior-look proof | Inline hex → sole private `/tmp/atom-v1b-seals/<hash>.json` → original `--recovery-seal-file`; no network seal retrieval | Validate input before resource access. Valid-seal prerequisite mismatch → consuming INVALID. Invalid file/prelude does not erase original pending seal. No replacement look or automatic POST retry. |
| **A16 — Stop, publish, close or rollback**: cancel/status + suspend/readback; immutable receipt PR; §8 reversal | Actual job IDs/statuses, first complete receipts, all retained seals, Owner closure/revert decision | Existing logs/private acceptance packet/GitHub receipt paths; no recreated evidence | Both job terminal and base suspended/inert. Publish one frozen receipt per required PR. No cleanup while valid recovery pending. Then remove/revoke PAT; retain rotated URI, original records and immutable history. Repository revert only implementation diff, independently reviewed and Owner-merged. |

The mutation authority in A8/A9 is credential administration, not evidence mutation. A12/A14 alone are the official scorecard snapshot/evaluation. A2/A6/A7/A9/A10 are operational evidence, not new study receipts or a READY publication. A0/A1 do not execute any later step.

## Appendix B. Adversarial walk-through and executable document-model audit

### B.1 Outcome matrix

The following cases were walked through against the normative clauses; implementations must preserve these outcomes. They are failures to accept unsafe execution, not permissions to repair outside scope.

| Adversarial case | Required outcome and decisive clause |
|---|---|
| Probe is created while a service-level secret is removed but a linked group still supplies it | No accepted probe; §2.5 effective-source proof fails, and §2.4 rejects key presence even when its value is empty. No shared-group edit is silently authorized. |
| Operator clears the variables only inside Python after startup | Not secret-free: §2.5 removal must precede Create job’s environment snapshot; §2.4 cannot unset to manufacture absence. |
| PAT/URI restored while an already-created probe is running | The provider’s snapshot is isolated, but §2.5 still requires probe termination before restoration; do not waive the ordered evidence requirement. |
| Probe tries to call GitHub to discover its build ID | Forbidden. §2.4 is network-free and reads no build-ID variable. Owner binds actual build-producing deploy `B` externally under §2.5. |
| Probe artifact measurement is accepted because its versions match | Forbidden. Independent approved same-build provenance is required by §2.2; measurement/versions alone are not acceptance. |
| Approval record is inaccessible in the private packet from a job | No runtime private-packet read is attempted. §2.6 supplies the exact Owner-authenticated non-secret metadata mirror and reviewer identity. |
| Caller supplies a provenance file, alternative variable, comment URL or build ID | Rejected; none is an authorized normal/probe input. §2.6 uses fixed collection plus existing `E`, validates uniqueness and does not dereference payload URLs. |
| Comment read requires more PAT scope or pagination is incomplete | BLOCKED before database access, not empty history or an unauthenticated fallback; §§2.6 and 3. |
| A build is produced after approval or while a sealed crash awaits recovery | It cannot silently replace `B`; §§2.3/2.5. New-seal mismatch blocks before reads; accepted-seal recovery consumes failure. |
| Same native bytes but a different CPU chooses different `log`/`exp` offsets before the first seal | Allowed only within authenticated libm/native files, with invocation-derived dispatch; §2.2. No probe dispatch literal. |
| Different dispatch or native bytes appear during recovery | Consuming INVALID under §2.3; never rebaseline or create another look. |
| An approval is edited, duplicated, not posted by the authenticated Owner, or not bound to the independent review | §2.6 rejects it; pre-read BLOCKED on a new seal, consuming negative after accepted recovery seal. |
| Parent accidentally resumes or platform restarts it | Its only command is inert. No scorecard or E-1 can start from parent configuration; §§5.2/5.4/8. |
| Vendor publishes no numeric usable `startCommand` byte limit | No `L` is invented. §5.3 blocks approval/evidence-capable activation. Absence of `maxLength` is not infinity. |
| Legal lineage/cohort strings grow beyond any synthetic fixture | No scientific bound is introduced. §5.3 measures the actual complete candidate seal and wrapper in that invocation. |
| Exact recovery command plus 4096 bytes equals `L` | Capacity passes; §5.3 uses `<=`. One byte more fails before consuming emission. |
| New-seal capacity fails after evidence counts were read | The express capacity-only exception returns existing null-seal BLOCKED, not a contradictory default INVALID; §§1.1/5.3. No statistic or candidate seal is emitted. |
| A protocol-invalid or noncanonical seal is disguised as “too big” | It keeps the existing PRE-CELL INVALID route; §5.3 requires a schema-valid candidate and does not downgrade other defects. |
| Candidate seal is changed after its command size passes | Recalculate before emission; only measured byte-identical `S` may become consuming. No changed seal is emitted under old arithmetic. |
| Complete sealed recovery no longer fits a verified current vendor limit | Original identity is already consumed. §5.3/Amendment 2A consuming-negative/incident rules apply; no new BLOCKED look or truncated payload. |
| Incident initial record lacks a completed timestamp because rotation has not occurred | Correct initial PENDING/null state. It authorizes the scoped rotation step but blocks activation; §6.1. |
| Password-change request was sent but its outcome is unknown | Remain PENDING; use actual secure confirmation, never the planned time or an automatic second rotation; §§6.1/6.3. |
| Rotation succeeds but Render update or private finalization is missing | No activation or approval payload; §§6.1/2.6. Newly rotated password remains in force; old value never restored. |
| Operator treats password rotation as terminating existing authenticated sessions | Not established. §6.1 keeps surviving-session exposure separate from new-authentication invalidation and requires investigation/containment evidence. |
| Analyst says NOINHERIT/no memberships means no TEMPORARY privilege | Incorrect; §6.1 preserves effective PUBLIC TEMPORARY and requires temporary-object/storage/connection/resource investigation. |
| Attacker disregards the scorecard’s read-only transaction convention | The incident analysis does not assume compliance. The existing no-durable-table-write/no-BYPASSRLS finding remains narrower; §6.1. Legitimate scorecard temp-use prohibitions are unchanged. |
| Parent is suspended while a one-off is still running | Not complete containment. §5.4/A.1 separately require cancellation/terminal job proof and parent suspension. |
| Creation request times out after Render may have accepted it | Resolve the actual job by control-plane listing/retrieval before any new POST; no autonomous duplicate invocation. |
| First complete result is unfavorable or an INVALID receipt | Retain and submit it unchanged; original Amendment 2A one-look/nonselective continuation law remains. No favorable-result replacement. |
| Normal-success path ends with the dedicated PAT still installed | Incomplete cleanup. §5.4 requires removal plus GitHub revocation once all authorized invocations are closed and no valid recovery remains pending. |
| Rollback proposes restoring old E-1 command, exposed password or obsolete trust setting | Forbidden even on a suspended base during V-1B rollback; §8 retains the inert command, rotated URI and pinned TLS. |
| Rollback would reset current main or erase an earlier receipt/evidence artifact | Forbidden; §8 permits only the reviewed implementation first-parent diff revert on then-current main. |
| HIST8’s similar IPv4 issue is added while fixing V-1B | Outside PR #325. §7 retains `pjbjpgnmniwcajqkuhge` exclusion and requires its own follow-on amendment. |
| Earlier PR-head checks/review are green but the replacement has not been reviewed | No merge. §9 requires fresh exact-final-head independent review, green actual checks, zero material findings and Owner-only merge. |

### B.2 What was actually tested during document authoring

A separate document-model and byte-transport simulation, not ATOM implementation, ran in the authoring sandbox. It completed 125 assertions with zero failures, including 27 transport-fixture cases covering all nine manifest identifiers, final-LF preservation, Unicode UTF-8 bytes, long legal payload strings, exact inline-hex doubling, shell/Python parsing, the 4096-byte margin, equality/one-byte-failure boundaries, secret/group absence, approval ordering, PENDING/finalized incident states, build/runtime drift, new-seal versus accepted-seal failure routes, pending-recovery cleanup and the permanently inert base.

The byte fixtures deliberately test transport arithmetic; they are not claimed to be production-schema-valid or real official V-1B seals. The transition model tests the document’s ordering/guards, not an implementation that has not yet passed its separate PR. No database, Render job, real PAT, role change, real incident finalization or protected statistic was used. These assertions are not independent final-head review, live platform acceptance, proof of an actual numeric Render capacity, or proof that all deployment prerequisites have already passed.

## Appendix C. Findings disposition, cross-contract scan and remaining activation gates

### C.1 Earlier review findings and exact resolving clauses

“Resolved in text” below means the corrective rule is authored and internally checked. It does not mark a GitHub thread resolved or claim independent reviewer acceptance of a head that has not yet been pushed.

| Earlier finding / request | Classification in the earlier record | Exact resolving clause(s) | Authored disposition |
|---|---|---|---|
| Invocation self-approves installed artifact bytes | P1 | §§2.2, 2.4–2.6 | Same-build independent approval predates database access; runtime compares approved components and cannot create its own baseline. |
| Scorecard command stored on background parent | P1 | §§5.2, 5.4, 8; A.1 | Permanent inert parent; scorecard/probe/recovery commands only in explicit one-off jobs; rollback cannot restore E-1. |
| PAT privileges asserted without retained verifiable evidence | P2 | §3; §2.6 approval payload | Non-secret owner/repository/permission evidence retained and independently inspected; successful reads are not scope proof. |
| PAT not removed/revoked on normal completion | P2 | §5.4; §8 step 3 | Normal closure and rollback both require Render removal plus GitHub revocation; valid recovery is not silently abandoned. |
| Exposed credential lacks vector/window/artifact disposition | P2 | §§6.1, 6.3–6.4 | Real private incident record with actual facts/unknowns, disposition/custodian, open initial window and confirmed final timeline; no credential reproduced. |
| Recovery inline hex may exceed platform capacity | Earlier observation elevated to a required correction | §§5.3, 2.6 `C`; B.1/B.2 | Actual complete candidate seal and exact wrapper measured, final LF doubled, fixed 4096 margin, authoritative vendor `L`; no inferred global bound. |
| HIST8 faces a separate connectivity issue | Scope observation / separately identified P2 consequence, not permission to widen this PR | §7; §10 | Existing exclusion remains; distinct HIST8 amendment and cost confirmation required. |
| Probe command/entry point and inherited-secret handling unspecified | Current P1 operational gap | §§2.4–2.5; A.1/A.2 A3–A5 | Exact Python callable/command, exact output/file/exit rules, delete-before-snapshot sequence, group/fallback guard and no guessed environment override. |
| Later runtime cannot obtain/authenticate approved record or build ID | Current P1 operational gap | §§2.5–2.6; A.2 A6/A10/A11 | Actual build-producing deploy ID, exact fixed GitHub metadata mirror, public reviewer identity, canonical hashes and lifecycle; no runtime private file/Render token/build env. |
| `max_seal_bytes` depends on unfrozen implementation field limits | Current P2 specification gap | §5.3; §9 test 4 | Global maximum removed; no lineage/count maxima delegated; per-invocation complete-seal gate runs before consumption. |
| Pre-rotation incident record demands a future completion time | Current P2 lifecycle gap | §§6.1, 6.3; A.2 A2/A8/A9 | Valid PENDING/null initial record; actual success timestamp then mandatory finalized version; no activation before finalization. |
| “Disclosure only” ignores PUBLIC TEMPORARY/resource abuse | Owner-required correction | §§6.1, 6.4 | Durable-table/BYPASSRLS finding preserved narrowly; temporary-object, storage, connection and availability abuse explicitly investigated. |
| Setup/token tests, approval and invocation could form a circular prerequisite | Additional contradiction caught during this rewrite | §§2.5–2.6, 9; A.2 A9–A13 | Approval exists before job creation; normal CLI proves actual token/TLS/authority before evidence; actual seal size is checked only after count scan. No unlisted test job. |
| Capacity-only post-count BLOCKED conflicts with inherited after-read INVALID | Additional contradiction caught during this rewrite | §§1.1, 5.3 | Express narrow routing exception; malformed/protocol-invalid seals and all consuming recovery failures keep INVALID. |
| Rollback’s old-command restoration contradicts permanent inert base | Additional contradiction caught during this rewrite | §8 step 2; A.1/B.1 | Old command restoration removed from V-1B operations and rollback, even as a suspended value. |
| Recovery text claims full runtime body is inside sealed identity bodies | Additional precision defect caught during this rewrite | §2.3 | Correctly compares their existing digest; compares full body only where separately retained. No new seal key. |
| Repeating the build/probe sequence could demand a second password rotation | Additional lifecycle ambiguity caught during final scan | §2.5 steps 3 and 7; §6.1 | Initial setup rotates once. Later probes reinstall the same valid credentials and reuse the completed incident record and original timestamp; no second rotation or replacement PAT is implied. |

### C.2 Cross-contract contradiction scan

| Controlling source / boundary | Cross-check performed | Result of the authored contract scan |
|---|---|---|
| V-1A §§2–11 | No model, formula, numerical order, causal rule, benchmark, population, threshold, classification, bootstrap/RNG or multiplicity change introduced | Preserved by incorporation; no scientific parameter supplied by operational records. |
| V-1A §§12–16 and TLS Amendment 1 | Existing implementation allowlist/conditional 033, exact CA bytes, direct hostname/port/database/role, full TLS tuple, catalog/no-write checks and original runtime field set | Preserved; only explicitly named operational comparison/credential/probe changes and the separately named administration-prompt exception apply. |
| V-1A §24 and Amendment 2A §8.6 | Stage-dependent refusal routing | Capacity-only post-count BLOCKED exception explicit; all other protocol/recovery/final-authority routes retain their required semantics. |
| Amendment 2A §§5–10 | Nine manifests, earliest boundary from original `T_amend`, six minima, initial snapshot timestamp, same-process seal/results, prior-look guards, sealed recovery, byte binding | Preserved. Capacity/approval comments create neither a READY artifact nor a new research anchor or look. |
| `AGENTS.md` and merged TLS §5 | Governance domain, SIM-5 pointer and narrow parallel V-1B exception, distinct documentation/implementation/operations, Owner merge | No pointer, role-governance or SIM/HIST8 scope change. Codex implementation remains separate; fresh exact-head review/Owner merge mandatory. |
| Render one-off behavior | Latest successful artifact plus configured-environment snapshot, no inherited parent local file/disk, `startCommand` override, parent suspension not terminating a job | Explicit secret-free snapshot, no fictitious override/build env, exact inline recovery staging and separate job/parent containment. |
| PostgreSQL 17 privileges/authentication | PUBLIC TEMPORARY independent of NOINHERIT, temporary/resource risk, TLS/SCRAM source rules, password-change completion versus already-authenticated sessions | Privilege finding narrowed accurately; no PUBLIC TEMPORARY revocation or RLS mutation. Private incident lifecycle no longer demands a future timestamp. |
| Secret lifecycle / sources | One runtime PAT, one existing reader URI, no probe secrets, retained scope evidence, normal closure plus rollback | Exact sources/absence/reinstallation/cleanup paths specified. Private evidence never becomes an implied runtime input. |
| Complete command/data dependency scan | All new operands have fixed literal domains or exact authenticated response/record sources; exact command bytes measured in the actual invocation | No unresolved implementation-chosen seal limits, approval file, build-ID environment variable, alternate credential or arbitrary fetch URL remains in the authored path. |

Internal scan conclusion: zero newly introduced internal contract contradictions were found in the defined paths and modeled cases after the corrections recorded above. This is an author’s bounded adversarial check, not a claim of mathematical completeness, a substitute for independent review, or a statement that operational blockers are zero.

Operational acceptance is not asserted. In particular, no authoritative numeric Render `startCommand` capacity was established by the official references inspected for this document. `L` must be obtained through §5.3’s explicit vendor evidence path; until then evidence-capable activation is BLOCKED. The same-build probe, effective secret absence, actual one-off identity/inheritance, secure administrative rotation, real private incident finalization, token scope/reads, direct-host TLS reachability and action-time IPv4 cost confirmation also require their actual prescribed acceptance evidence. Those are the retained fail-closed gates, not facts inferred from document tests or green CI. If vendor behavior cannot satisfy one of the frozen mechanisms, the required redesign remains documentation-first; this document does not claim it has already succeeded.

---

## Source record and verification boundary

The correction targets PR #325 head `0fbdf3f7088e14cb18e352b2e5dfd3e44d13f991`. Authenticated GitHub metadata reported the PR open/unmerged with one changed path, `docs/v-1a-amendment-3-v1b-operational-prerequisites.md`, source Git blob `199c00624806461290d97428854bb331e4a00f9d`, reported source-file SHA-256 `ba5f80c6ce0b546b422652cac49b723a8b8e0c92df8e23fd9ecc4982252aa170`, size 49,486 bytes. These identify the correction input, not the hash of this replacement.

The inspected current main remained `f0035147a646fc7d4c7002c8a2706f4987f6a10c`; GitHub reported it unprotected. V-1A source blob was `4bafc8e1d0d52e05b2832f1355b903d544e953ec`; Amendment 2A source blob was `e95dbbe3780629366cd77f8d9d8c2c6f26086450`; `AGENTS.md` source blob at the correction head was `26f12b78098429bad77450c742ed58c66434e30e`. The exact inherited source documents, not a summary of prior chats, govern unchanged mathematics and receipts:

- V-1A: `docs/v-1a-volatility-first-freeze.md`, especially §§12–19 and 24–26.
- TLS Amendment 1: `docs/v-1a-amendment-1-tls-trust-anchor.md`, especially §§2–6.
- Amendment 2A: `docs/v-1a-amendment-2a-tiered-readiness-boundaries.md`, especially §§5–11.
- `AGENTS.md`: governance/technical-domain separation, Owner operational instructions, phase separation, final-head review, active-pointer boundary.

Read-only Render service/deploy metadata on 2026-09-06 still showed the named parent suspended, one 4c-8g instance, auto-deploy off and the stale E-1/sleep command. The observed existing latest deploy was not a V-1B acceptance build. This document did not replace that command, fetch environment secret values, create a build/job, rotate a password, access database evidence, publish an operational approval or purchase IPv4.

Official vendor references inspected on 2026-09-06:

1. Render One-Off Jobs — https://render.com/docs/one-off-jobs — creation-time artifact/environment snapshot, one-off command, termination, separate cancellation, log retention and lack of inherited persistent disk.
2. Render Create job — https://api-docs.render.com/reference/post-job — body parameters `startCommand` and optional `planId`; no per-job environment or arbitrary-build parameter is inferred.
3. Render Default Environment Variables — https://render.com/docs/environment-variables — documented service/commit fields; no `RENDER_BUILD_ID` assumption.
4. Render Environment Variables and Secrets — https://render.com/docs/configure-environment-variables — Save only, Save and deploy, rebuild distinction, group precedence and secret files.
5. Render Trigger deploy / Retrieve deploy — https://api-docs.render.com/reference/create-deploy and https://api-docs.render.com/reference/retrieve-deploy — exact commit/build-producing deployment observation.
6. Render Delete / Add or update environment variable — https://api-docs.render.com/reference/delete-env-var and https://api-docs.render.com/reference/update-env-var — single-service keys do not remove group-supplied variables.
7. Render Cancel running job / Suspend / Resume — https://api-docs.render.com/reference/cancel-job, https://api-docs.render.com/reference/suspend-service-1 and https://api-docs.render.com/reference/resume-service-1.
8. GitHub issue-comment REST API — https://docs.github.com/en/rest/issues/comments — fixed repository discussion transport and public-resource read behavior; actual authenticated least-privilege reads remain a deployment gate.
9. PostgreSQL 17 Privileges — https://www.postgresql.org/docs/17/ddl-priv.html — PUBLIC privileges and TEMPORARY semantics.
10. PostgreSQL 17 SET TRANSACTION / ALTER ROLE / psql — https://www.postgresql.org/docs/17/sql-set-transaction.html, https://www.postgresql.org/docs/17/sql-alterrole.html and https://www.postgresql.org/docs/17/app-psql.html — transaction limits, password administration and private `\password` behavior.
11. Supabase Dedicated IPv4 Address — https://supabase.com/docs/guides/platform/ipv4-address — exact project add-on management and connection-impact context; no remembered cost substitutes for action-time confirmation.

These references explain supported mechanics, not fulfilled gates. Vendor changes do not silently amend this freeze. No numeric limit, private incident fact, future merge/build/job ID, actual review conclusion or successful deployment is fabricated by this complete document.
