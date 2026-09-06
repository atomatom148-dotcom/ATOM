# V-1A Amendment 3 — V-1B Operational Prerequisites

**Decision ID:** `ATOM-V1A-AMENDMENT-3-V1B-OPERATIONAL-PREREQUISITES-1`  
**Status:** PROPOSED — no effect before independent final-head review, green required checks, zero material findings, and Owner merge.  
**Author:** ChatGPT Pro — architecture and freeze authority  
**Date:** 2026-09-06  
**Sole documentation-PR path:** `docs/v-1a-amendment-3-v1b-operational-prerequisites.md`  
**Inspected repository:** `atomatom148-dotcom/ATOM`  
**Inspected main:** `f0035147a646fc7d4c7002c8a2706f4987f6a10c`  
**Corrects PR:** #325 at reviewed head `87d36e93b80ec0fc3b29613b400efa921d8e0750`; that head is superseded by the corrected final head and may not satisfy the merge gate.  
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

### 2.2 Exact replacement for the circular hash requirement

Replace only the requirement that the following host-dependent values be embedded as pre-merge expected literals:

```text
runtime_artifact_components
runtime_artifact_sha256
libm_dispatch
libm_dispatch_sha256
runtime_manifest_body's complete literal value
runtime_manifest_sha256's literal value
```

For a new-seal invocation, after the complete permitted import/native closure has been loaded and before any database connection or evidence access, derive those values from the actual process that will perform that invocation. Preserve, without alteration, the four-component coverage, path normalization, ordering, duplicate rejection, source/bytecode restrictions, regular-file rules, executable mappings, exact native-library coverage, `dlsym` resolution, non-ASLR file-offset construction and canonical hashing algorithms in §13.2.1.

Verify the frozen version/platform/float fields and exact libpq/dependency literals first. Then construct the complete observed runtime body with the original exact key set. Freeze that body and its digest in memory. Do not substitute a value supplied by an operator, a developer computer, CI, a different Render build, or a pre-merge probe on unrelated build/runtime provenance. No pre-merge CPU-specific fingerprint is a prerequisite or authority for host-dependent dispatch values.

Installed runtime bytes are not self-authenticating merely because the invocation hashes them. Before any V-1B database connection, evidence access, readiness scan or consuming seal, an Owner-controlled non-consuming runtime-provenance acceptance must exist for the exact successful Render build from which V-1B one-off jobs will be created. The provenance probe runs as a separate one-off job derived from that exact successful build while the base service remains on the inert §5 command, with the database URI and `ATOM_V1B_GITHUB_TOKEN` absent from the probe environment. It may read only local repository/build/runtime files and non-secret Render build identity. It computes the unchanged §13.2.1 byte coverage for `python_executable_sha256`, `stdlib_tree_sha256`, `dependency_tree_sha256`, and `loaded_native_tree_sha256` and emits no libm dispatch baseline, database value, evidence count, readiness value or protected statistic.

The retained non-secret `ATOM-V1B-RUNTIME-PROVENANCE-1` control-plane record binds exactly:

```text
schema_version = ATOM-V1B-RUNTIME-PROVENANCE-1
render_service_id = srv-daa7thgae00c73a2lmn0
render_build_id = exact successful Render build identifier
render_deploy_id = exact deployment/configuration identifier, when Render exposes one; otherwise null
repository = atomatom148-dotcom/ATOM
execution_source_sha = exact 40-lowercase-hex reviewed implementation/main SHA used for that build
build_command = pip install -r requirements.txt
python_version = 3.14.3
runtime_artifact_components = exact four-component §13.2.1 object
runtime_artifact_sha256 = sha256(canonical_json(runtime_artifact_components))
probe_generated_at_utc = exact probe/control-plane UTC timestamp
```

`render_build_id` is mandatory. The Owner retains the complete canonical record and its SHA-256 in the private V-1B operational acceptance record. Independent implementation acceptance verifies that the probe came from the same exact successful build identity later selected for V-1B jobs, the source SHA and reviewed implementation bytes match authenticated GitHub history, and the four component digests are approved before the first database/evidence-capable V-1B invocation. A record from a different build, source SHA, service, or mutable/unverifiable build identity is unusable.

Every evidence-capable new-seal invocation independently recomputes the same four artifact component digests before any database connection or evidence access and requires exact equality to that approved provenance record. Those approved byte digests flow unchanged into the invocation’s `runtime_artifact_sha256` and `runtime_manifest_sha256`, which remain bound into readiness identity, run identity and seal. The provenance record adds no receipt/seal key and is not research evidence.

`libm_dispatch` remains invocation-derived because its non-ASLR symbol offset can depend on the actual CPU dispatch selected for that process. It is accepted only when both `log` and `exp` resolve inside the exact authenticated libm/native artifact already covered by the approved `loaded_native_tree_sha256`, using the unchanged mapping and offset rules. The resulting dispatch object/digest is bound into the invocation runtime manifest and, once sealed, is immutable for recovery. This authenticates installed bytes without reintroducing a cross-CPU pre-merge dispatch literal.

The existing formulas remain:

```text
runtime_artifact_sha256 = sha256(canonical_json(runtime_artifact_components))
libm_dispatch_sha256    = sha256(canonical_json(libm_dispatch))
runtime_manifest_sha256 = sha256(canonical_json(runtime_manifest_body))
```

`runtime_manifest_body` is still exactly the original `runtime_identity` key set excluding only `runtime_manifest_sha256`. There is no self-hash in its own hash boundary.

A conforming unsealed invocation may encounter a different Render CPU/native fingerprint from a different unsealed invocation while still satisfying all frozen versions and source bindings. Its identity records that difference. This permission is not permission to select a CPU, fingerprint, invocation or result after seeing protected output. It never defeats a prior seal or terminal-receipt guard.

### 2.3 Binding, final verification and recovery

Insert the invocation-derived `runtime_manifest_sha256` into the existing Amendment 2A §8.3 readiness-identity body and §8.4 run-identity body. The existing seal binds those bodies and their hashes. The existing evaluated `runtime_identity` serializes the complete invocation-bound object. Add no runtime, readiness, run, seal or receipt key; change no schema version or official filename.

Recompute the complete observed runtime body and digest before the seal/protected-computation transition and at final verification immediately before receipt construction. Require exact canonical-body equality and exact digest equality to the invocation’s initial frozen runtime. Recheck all existing source/CA bindings as already required. No later import, dynamic module load, changed component, changed native mapping or changed `log`/`exp` dispatch is accepted.

For exact recovery, validate the original retained seal first under Amendment 2A §10.2. Before database or evidence access, independently authenticate the recovery job’s `render_build_id` against the retained approved `ATOM-V1B-RUNTIME-PROVENANCE-1` record, recompute all four byte digests, and require exact equality to that approved record. Independently derive the recovery process’s full runtime body using the same algorithms. Its complete runtime body and digest—including the invocation-dependent `libm_dispatch` object and digest—must equal the runtime identity frozen into both original sealed identity bodies; those bodies and the sealed readiness/run/seal hashes must also verify exactly. Recovery may never adopt a newly observed body, a new CPU dispatch or a different successful build as a replacement baseline. Recheck the approved artifact bytes and exact sealed runtime identity again at final verification.

A different recovery CPU dispatch, artifact/native hash or version is a mismatch, not a new look. Use only the existing timing-dependent failure routes: pre-evidence new-seal failures are `BLOCKED`; pre-seal failures after evidence access are null-seal PRE-CELL INVALID; accepted-seal recovery or other post-seal failures consume the original identity under Amendment 2A §8.6. Final verification failure after truthful cells exist uses the applicable existing post-evaluation authority-invalid route. No partial protected value is emitted.

`HOLD`, `WAIT_FIRST_MANIFEST` and usage-error output/file/exit rules remain exact. Invocation-derived runtime values are not a separately published runtime or READY receipt.

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

After both merge gates, the Owner may configure only: the exact commands below; `PYTHON_VERSION=3.14.3`; the existing per-invocation `ATOM_V1B_AUTHORIZED_MAIN_SHA`; the §3 secret; the §6 replacement value for the existing reader URI; and the exact deployment/suspension operations in this section. No generic environment replacement is authorized.

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

### 5.3 Recovery startCommand capacity gate

The inline-hex recovery design is authorized only if its complete maximum command is proven to fit Render’s accepted `startCommand` capacity before operational activation and before any consuming seal can exist.

During the implementation PR, derive a finite upper bound `max_seal_bytes` for every canonical `ATOM-V1B-MANIFEST-SEAL-1` record permitted by the frozen schema and the implementation’s validated input-length bounds. The bound includes the final newline and every legal manifest/lineage/cohort representation. If any seal field affecting serialized size lacks an enforceable finite maximum, the inline-hex recovery design is unproven and V-1B is `BLOCKED` for documentation-first redesign.

Render the exact §5.2 recovery template with a maximum-size valid synthetic seal fixture and maximum-length legal substitutions. Measure UTF-8 bytes, not characters:

```text
max_recovery_startCommand_bytes = len(utf8(exact rendered recovery startCommand))
                                = fixed template/substitutions + 2 * max_seal_bytes
recovery_capacity_margin_bytes  = 4096
required_startCommand_capacity  = max_recovery_startCommand_bytes + 4096
```

Before activation, retain non-secret action-time vendor/control-plane evidence establishing Render’s accepted `startCommand` limit in bytes for this exact one-off-job mechanism. The evidence must be authoritative enough for independent review: current Render documentation, API/schema/control-plane limit disclosure, or Render support confirmation tied to this product behavior. A guessed shell/OS `ARG_MAX`, an observed shorter command, or successful local execution is not proof of the Render field limit.

Acceptance requires:

```text
accepted_render_startCommand_limit_bytes >= required_startCommand_capacity
```

The implementation acceptance record retains `max_seal_bytes`, the exact measured command byte count, the 4096-byte margin, the accepted Render limit, evidence source/date and PASS/FAIL arithmetic. If the limit is unavailable, ambiguous, smaller, measured in an incompatible unit, or the inequality fails, V-1B is `BLOCKED` before any evidence-capable activation or consuming seal and requires documentation-first recovery redesign. Truncation, compression, alternate payload storage, a new environment variable, network retrieval, or discovering the problem during recovery is forbidden.

### 5.4 Native one-off lifecycle; no continuous worker execution

The containment mechanism is one Render native one-off job attached to this exact existing base service, not an indefinitely running background-worker start process. This is the sole narrow exception permitting a transient execution instance derived from the existing benchmark service; it grants no new permanent service or autonomous launcher.

The Owner-controlled Render control plane launches the job. The scorecard receives no infrastructure token and cannot launch, repeat or suspend jobs itself. Use the existing 4c-8g capacity only, with no simultaneous benchmark daemon and no parallel V-1B job. Before launch verify the job will inherit the exact authorized successful build and configured environment, not merely the most recent deploy request. The runtime must still prove the original frozen service identity and actual execution SHA; an incompatible job identity is not relabeled to pass.

Keep the base service suspended except for any Render-required build/configuration preparation. Whenever the base service is resumed for such preparation, its start command remains exactly `python -c "raise SystemExit(0)"`; it is never replaced by E-1, a V-1B scorecard, recovery staging, sleep loop or another workload. The inert command performs no database or repository-authority access and no V-1B invocation. After preparation, verify suspension before creating a one-off job. If the exact build/configuration cannot be obtained while preserving this invariant, stop; do not resume a continuous scorecard worker.

Create exactly one job per authorized invocation; do not automatically retry a job-creation request with an uncertain outcome. Resolve the existing job identity/status through the control plane first. Before another invocation, inspect prior job completion, retained logs/seals and official receipts under the existing one-look rules. A crash, deployment event or lost API acknowledgement cannot authorize a replacement identity.

The job ends when the one-shot command exits. Capture the complete seal through the existing execution-log sink before protected calculation, and retain the first complete canonical evaluated or negative receipt and its hash before runtime teardown can destroy the only copy. Logging that complete frozen receipt after construction is permitted; logging partial protected values is not. Preserve exact HOLD/WAIT/usage outputs and their no-file requirements. No new receipt schema or automatic publication is introduced.

After every invocation, including HOLD, WAIT, usage failure, BLOCKED, INVALID or evaluated completion, verify that the job has terminated and that the base service is suspended with the inert base command still configured. A protective stop must cancel the running one-off job and suspend/verify the base service; suspending the parent alone is insufficient. Loss of a seal, result or execution-status proof follows the existing incident rules and never permits an unverified rerun.

After all authorized V-1B invocations have terminated, every manifest is either terminally recorded or otherwise closed by Owner decision, and independent review confirms that no hash-valid seal remains without a terminal receipt and no valid exact recovery remains pending, remove `ATOM_V1B_GITHUB_TOKEN` from Render and revoke the dedicated fine-grained PAT in GitHub. Retain non-secret evidence of Render-secret removal and PAT revocation in the operational closure record. This cleanup is mandatory on normal completion, not only rollback. If a valid recovery remains pending, the token may persist only for that bounded recovery window and may not be used for unrelated work; removal and revocation are immediate once the final recovery obligation closes.

## 6. One same-role password rotation; exact URI invariants

### 6.1 Exposure record and bounded blast radius

The old `atom_e1_scorecard_reader` credential is treated as exposed. This public amendment deliberately does not reproduce the credential, any secret-bearing artifact, or sensitive exposure mechanics, and it does not invent facts that have not been verified. Before rotation or V-1B activation, the Owner must create and retain the authoritative private incident record:

```text
ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06
```

That private record must state, without copying the secret itself: the exact exposure vector; first known exposure timestamp; last possible exposure timestamp; discovery timestamp; every known secret-bearing artifact/location; whether each artifact was deleted, redacted, access-restricted or necessarily retained; disposition timestamp and control plane; and rotation completion timestamp. The exposure window is exactly from first known exposure until the old password is successfully invalidated by rotation; uncertainty is recorded as uncertainty rather than narrowed by assumption. If an artifact cannot be removed, the record identifies its retained location, access controls and retention reason. The private incident record is security/operations evidence, not V-1 statistical evidence, and is not added to this public PR.

The credential’s authority is bounded to the already frozen role `atom_e1_scorecard_reader`: LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS, no role memberships, no database/schema create path, and no INSERT/UPDATE/DELETE/TRUNCATE authority under the V-1A catalog-wide checks. Its intended blast radius is therefore disclosure of rows readable through that role’s existing SELECT/RLS/proof-function authority, not database mutation or RLS bypass. This does not prove the credential was unused; the private incident record records any available access-log review and its limits. Discovery of a write path, BYPASSRLS, broader membership, different target or unexplained access is a new material incident and stops V-1B for separate review.

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

Later connection/authority acceptance uses only the new credential and the frozen direct-host TLS/reader checks before evidence access. This amendment phase itself performs none of those connections or checks.

## 7. Direct-host IPv4 add-on; separate cost gate

Authorize the dedicated Supabase IPv4 add-on for project `afyiydxbjgzaiswnbcyj` only, conditional on a separate affirmative Owner confirmation immediately before the billable action.

At action time, the operator must show the exact project, whether the add-on is already enabled, the vendor’s then-current incremental hourly/monthly cost and billing basis, the applicable replica/other charges, and any required plan change or connection disruption. Obtain an explicit Owner confirmation for that exact quoted action. This amendment is not cost confirmation, does not freeze a remembered price and does not authorize an organization-plan upgrade, replica or other add-on. If already enabled, do not purchase it again.

If approved and absent, enable only that project’s dedicated direct-database IPv4 add-on. Preserve the DNS hostname and entire §6 tuple. IPv4 changes transport reachability, not database identity, TLS hostname verification, source eligibility or authority.

After propagation, verify the same direct hostname resolves to a usable IPv4 address and the later approved invocation passes the pinned-CA `verify-full` connection checks. Do not replace the URI hostname with an IP literal, add `hostaddr`, edit `/etc/hosts`, use a proxy, substitute Supavisor/PgBouncer, choose a different port, weaken TLS or move to another project. No static IP literal becomes a new frozen identity. Connection/catalog verification is later setup/execution work, not work performed in this documentation phase.

Any inability to confirm price, enable the approved add-on or establish the exact direct connection remains a blocker; it is not authority for an alternative route. This grant does not enable IPv4 for HIST8’s separate project `pjbjpgnmniwcajqkuhge`. HIST8 remains outside PR #325 and receives no connectivity, TLS, credential, migration or execution authority from this amendment. Any dedicated-IPv4 authority for HIST8 requires a separate documentation-first follow-on amendment under HIST8’s own controlling corpus law, with its own action-time cost confirmation and exact direct-host/no-pooler constraints. Do not add that follow-on decision or any HIST8 path to PR #325.

## 8. Exact operational and repository rollback

Before setup, retain a non-secret action-time configuration record: deployed commit, command, build command, plan, instance count, runtime, region, branch, auto-deploy/previews state and presence/value of non-secret variables being changed. Record secret names and provisioning state only; never snapshot a credential value or the exposed URI. This operational record is not a statistical receipt or a new required schema.

Rollback is exactly:

1. Cancel and verify termination of any running V-1B one-off job; suspend and verify the named base service. Preserve every seal, complete receipt and required log. Classify a crossed seal only through existing Amendment 2A rules.
2. Restore the action-time non-secret configuration only while the base service remains suspended. The historical E-1 command may be restored as an inert configuration value only; this amendment authorizes no E-1 execution or restoration of its sleep loop to a running service. Restore the previous `PYTHON_VERSION`/authorized-SHA presence and value if those fields were changed, without launching the reverted runtime. Leave all untouched settings untouched.
3. Remove the newly added `ATOM_V1B_GITHUB_TOKEN` from this service and revoke that dedicated PAT through the Owner’s secure control plane. Do not install another token or credential fallback. This is the rollback path for the same cleanup independently required on normal completion by §5.4.
4. Keep the newly rotated database password and its conforming reader URI. The exposed password and obsolete TLS configuration are excluded from restoration, including a platform’s automatic environment rollback. If a safe URI cannot be retained, remove the URI and remain suspended rather than restoring the exposed credential.
5. Repository rollback follows Amendment 2A §10.3 exactly: a separately reviewed revert of only the verified V-1B implementation merge’s first-parent diff on then-current `main`. Never reset history or revert a later per-invocation head containing receipts. Preserve all freezes, this amendment, the eight evidence files, seals and receipts. A non-clean revert requires a reviewed rollback plan; no unrelated refactor or ad-hoc privilege rollback.
6. Do not automatically disable an IPv4 add-on already relied on by other direct clients. Disabling the newly enabled project-wide add-on requires a separate Owner instruction after connection-impact and billing confirmation. It is not a means to restore an old password or erase a consumed look.

A Render rollback that would replay the old command, restore an exposed secret, lose retained evidence or start an unauthorized runtime must not be invoked. A suspended service with the rotated credential retained is the safe rollback state; rollback never restores research eligibility.

## 9. Implementation, review and acceptance requirements

The later implementation surface remains exactly:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
requirements.txt
certs/supabase-prod-ca-2021.crt
```

`migrations/033_authorize_v1_volatility_scorecard_reader.sql` remains conditional on its original privilege proof and collision rules. It is not repurposed for password rotation. No other implementation file, helper service, dependency, database storage, workflow, launcher module or environment alias is authorized.

Retain every existing V-1A/TLS/2A test. Add focused tests within the existing test module proving:

- Frozen versions/libpq/dependencies/source bindings still reject mismatch; a same-build non-consuming provenance probe produces the exact approved four-component artifact record; every evidence-capable invocation and recovery independently matches those byte digests before database/evidence access; and invocation-derived CPU dispatch needs no cross-CPU pre-merge literal while still binding into the sealed runtime identity. A different build, changed installed byte or post-seal CPU/native drift cannot be accepted or rebaselined.
- The sole token source and scope contract, retained non-secret PAT control-plane evidence for resource owner/sole-repository selection/exact permissions, no fallback or secret serialization, required authenticated reads, exact repository/default-ref equality, signed merge/ancestry/blob/worktree proof and recovery’s separate current-head check. Unprotected `main` alone is accepted; an unverifiable/stale/wrong ref, unproven/over-broad token scope or changed source is not.
- The base service can contain only the inert `python -c "raise SystemExit(0)"` command during V-1B operations; the closed nine scorecard commands and recovery staging template can appear only in one-off-job `startCommand`; original two CLI options, exact HOLD/WAIT/usage behavior, early-terminal prerequisite, retained-seal recovery, no loop/automatic retry, first-complete-receipt retention, and unchanged one-look/failure routing. Mocked control-plane tests do not claim live one-shot acceptance.
- The recovery-capacity calculation has a finite schema/input upper bound, measures UTF-8 bytes of the complete maximum rendered recovery command including doubled seal bytes, adds exactly 4096 bytes of margin, and fails activation when the authoritative Render limit is unavailable or below required capacity.
- URI changes cannot alter any non-password identity/TLS field beyond the previously authorized pinned-root correction, and rollback never restores the exposed credential. Use synthetic credentials only.

Before operational activation, the Owner’s acceptance record must additionally prove: the approved same-build `ATOM-V1B-RUNTIME-PROVENANCE-1` record and independent byte equality; retained non-secret PAT scope evidence plus actual restricted-token reads; the exact successful build/runtime identity; the §5.3 recovery-command capacity arithmetic and authoritative Render-limit evidence; native one-off containment with the base command remaining inert; complete output/seal capture; absence of a concurrently running benchmark daemon; terminal job status plus parent suspension; the private incident-record identifier and completed old-password rotation; rotated-URI verification; and—if purchased—the separately approved V-1B IPv4 action. Missing evidence is pending or `BLOCKED`, never an inferred `PASS`. Setup must succeed before a consuming seal; no trial protected run is a connectivity test.

Both this amendment PR and the separate implementation PR require independent review on their exact final heads, all actual required checks green, zero unresolved P1/P2/material findings, and Owner merge. Earlier-head reviews and generic green badges do not suffice. No waiver, bypass, self-review substitute, merge delegation or deadline exception is granted. Codex handles repository implementation, tests, commits and PR preparation; ChatGPT Pro authors the freeze and performs final architecture/receipt audits.

Each later receipt publication remains a separate documentation-only PR adding exactly one immutable official-schema JSON file under the existing filename rules, with independent final-head review, green checks, zero material findings and Owner merge.

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
→ Owner-controlled exact setup, secure rotation and action-time IPv4 confirmation
→ exact authorized one-off invocation; original readiness and seal rules
→ verified job termination and worker suspension with inert base command preserved
→ when no valid recovery remains pending: remove Render PAT secret + revoke dedicated PAT
→ unchanged receipt publication and final audit
```

If the required work cannot fit these exact boundaries, stop for a documentation-first decision. HIST8’s IPv4 issue is explicitly deferred to a separate follow-on amendment and is not part of PR #325. Tuesday’s deadline supplies priority, not permission to weaken proof.

---

## Non-normative source record

Repository law was inspected at `f0035147a646fc7d4c7002c8a2706f4987f6a10c`, using authenticated GitHub reads. V-1A blob: `4bafc8e1d0d52e05b2832f1355b903d544e953ec`; Amendment 2A blob: `e95dbbe3780629366cd77f8d9d8c2c6f26086450`. PR #321 reports merge `166a0e5b945e4f19ae41f392e75e3560d72acc1b`, merged at `2026-09-05T15:45:58Z`, and prior TLS merge `2126b53d1f3419f193eeddf0d7ca066f0fd161af`. Runtime verification must obtain its own required authenticated proofs; these inspection notes are not a substitute.

Read-only service metadata on 2026-09-06 showed the exact service in §5 suspended, one 4c-8g instance, auto-deploy off and the stale command quoted in §5. No environment secret value was requested or reproduced. GitHub reported default branch `main`, public repository visibility and `protected=false`.

Vendor references checked 2026-09-06, for operational mechanics only:

- Render, One-Off Jobs: https://render.com/docs/one-off-jobs. Jobs inherit the base service’s successful build/configuration, terminate on command exit, and are not terminated by suspending the base service. They do not inherit a persistent disk.
- GitHub, Managing your personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens.
- GitHub, REST API endpoints for commits and pull requests: https://docs.github.com/en/rest/commits/commits and https://docs.github.com/en/rest/pulls/pulls. Required proof reads must be demonstrated using the restricted authenticated token; no extra scope is inferred.
- Supabase, Dedicated IPv4 Address for Ingress: https://supabase.com/docs/guides/platform/ipv4-address. Live project-specific availability, impact and cost are separately confirmed at action time.

Vendor changes cannot silently amend the contract. No live runtime, connection, scope, review or deployment acceptance is asserted by this source record.
