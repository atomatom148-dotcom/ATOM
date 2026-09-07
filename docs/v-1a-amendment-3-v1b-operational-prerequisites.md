# V-1A Amendment 3 — V-1B Operational Prerequisites

**Decision ID:** `ATOM-V1A-AMENDMENT-3-V1B-OPERATIONAL-PREREQUISITES-1`  
**Status:** PROPOSED — no effect before independent final-head review, green required checks, zero material findings, and Owner merge.  
**Author:** ChatGPT Pro — architecture and freeze authority  
**Date:** 2026-09-06  
**Exact-head correction review date:** 2026-09-07
**Document state:** Complete replacement for review; not an assertion of implementation or operational acceptance.  
**Sole documentation-PR path:** `docs/v-1a-amendment-3-v1b-operational-prerequisites.md`  
**Inspected repository:** `atomatom148-dotcom/ATOM`  
**Inspected main:** `f0035147a646fc7d4c7002c8a2706f4987f6a10c`  
**Corrects PR:** #325 at exact reviewed input head `caeae8c1be63a54c5926b56c8aa44eb04be247ff`, including every earlier correction. That input head and every earlier head are superseded by the corrected final head and cannot satisfy its review or merge gate.
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

The only later code additions allowed by this correction are inside the previously authorized scorecard and test modules: the exact non-consuming probe entry point and common startup-isolation guard in §2.4, the existing-GitHub-metadata reader with §2.6's deadlines and internal secret-free resolver child, and the actual-seal capacity gate in §5.3. No new module, service, CLI credential, environment variable, disk, provenance file in the runtime, migration ordinal, or third-party dependency is implied. The probe is a separately authorized Python entry point, not a third scorecard CLI option. The startup guard and resolver are internal implementation routines, not new entry points or CLI options. Section 4 selects an Owner-enforced no-ref-update window and adds no descendant classifier or scorecard input.

The only additional GitHub metadata/control operations are the explicitly identified non-secret approval/review comments in the already existing ATOM PR #325 discussion and §4's temporary no-ref-update ruleset lifecycle. They use the already authorized GitHub host/repository and existing Owner GitHub control plane. The scorecard uses only its one read-only PAT for authenticated reads and can neither create nor remove the ruleset. This is an express narrow extension of repository-authority metadata reads and temporary ref containment, not an unnamed URL, alternative credential or market/evidence source. No private incident artifact, token-scope screenshot, Render API credential or secret is made readable by the scorecard.

The one in-process routing exception is §5.3’s capacity-only BLOCKED refusal after a count-only scan but before successful seal emission. It expressly replaces V-1A §24 and Amendment 2A §8.6 only for that condition. All other defects observed by the running process after read/seal retain their existing INVALID routes. Section 4 separately defines evidence preservation when a window breach is first knowable only from the mandatory post-terminal history audit: a terminated process cannot fabricate a replacement INVALID receipt. If no valid seal was emitted, no look was consumed and any later invocation remains subject to the existing eligibility/incident law plus a fresh reviewed window; if a valid seal was emitted, the look remains consumed, no replacement look is authorized, and the first complete receipt retains its existing Amendment 2A disposition. There is no change to the contents, hash algorithms or ordinary publication duties of a successful readiness object, run identity, seal or receipt.

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

The original successful build must not be replaced while any valid seal lacks its first complete terminal receipt. A failed sealed job is recovered using that still-selected artifact; it does not depend on an unimplemented ability to select an arbitrary historical artifact in Create job. Section 4's active no-ref-update window holds `refs/heads/main` at `E` while a secret-bearing invocation or recovery can create or discharge a look; no later commit is substituted or rehashed as the sealed execution revision. If the platform loses or replaces the required build, fail through the existing consuming-negative route; do not relabel a rebuild as the old build.

New-seal failures before evidence reads are BLOCKED. Except for §5.3’s explicit capacity-only exception, failures observed in process after evidence reads but before sealing are null-seal PRE-CELL INVALID. Once a valid recovery seal has been accepted, any in-process missing provenance, authentication failure, different build, artifact mismatch or other failed prerequisite is consuming PRE-CELL INVALID, never BLOCKED. A failed in-process final authority/runtime check after all truthful manifest cells exist uses POST-EVALUATION AUTHORITY INVALID. Section 4 alone controls a breach first established after process termination by interval history; it preserves rather than rewrites the already emitted candidate bytes. Keep all original sealed fields, initial authority proof and truthful-null merge-identity rules; emit no protected partial values.

A §2.6 GitHub deadline exhaustion, incomplete response or forbidden retry is inability to verify repository authority at that exact checkpoint, not `WAIT`, an empty result, an infrastructure-only exception or authority to continue in the background. At a new-seal initial checkpoint before evidence it is `BLOCKED`; after evidence but before seal it is null-seal PRE-CELL INVALID. After seal emission, or after a recovery seal has been accepted, it is consuming PRE-CELL INVALID until complete truthful cells exist; at the final check after complete truthful cells it is POST-EVALUATION AUTHORITY INVALID. Use only the existing schema, stage, singleton reason and null/non-null identity fields applicable to that route. Add no timeout-specific status, reason code, receipt field or retry identity.

### 2.4 Exact non-consuming provenance probe

The sole probe entry point is `provenance_probe_main()` in `quant/volatility_scorecard.py`. It takes no function argument, command argument, stdin input, manifest ID, approval file or credential. It returns the process exit code described below. It may be implemented only in the already authorized module and tested only in the existing test module.

Its exact one-off `startCommand`, with no substitutions, is:

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; i=tuple(sys.path); r=os.getcwd(); z="/etc/ld.so.preload"; b=any((k.startswith("PYTHON") and k!="PYTHON_VERSION") or k.startswith(("_PYTHON","LD_","DYLD_","BASH","GIT_","OPENSSL_")) or k in {"ENV","SHELLOPTS","PS4","KSHENV","ZDOTDIR","GCONV_PATH","GLIBC_TUNABLES","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","http_proxy","https_proxy","all_proxy","no_proxy","SSL_CERT_FILE","SSL_CERT_DIR","SSLKEYLOGFILE","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix=="/dev/null/atom-v1b-no-pyc" and os.environ.get("PYTHON_VERSION")=="3.14.3" and not b and not os.path.lexists(z) and not {"site","sitecustomize","usercustomize"}.intersection(sys.modules) and not any(n=="quant" or n.startswith("quant.") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and len(i)==len(set(i)) and all(isinstance(v,str) and v and os.path.isabs(v) and os.path.realpath(v)==v for v in i)); o or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme("prefix")); a=tuple(dict.fromkeys((r,os.path.realpath(p["purelib"]),os.path.realpath(p["platlib"])))); d=os.path.join(r,"quant"); v=os.path.join(d,"volatility_scorecard.py"); x=os.path.realpath(sys.executable); w=shutil.which("python"); o=(all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath("/proc/self/exe") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat("/dev/null",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec("quant",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules["quant"]=importlib.util.module_from_spec(s); from quant.volatility_scorecard import provenance_probe_main; raise SystemExit(provenance_probe_main())'
```

`-I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc` is one indivisible launch requirement. `-I` supplies isolated mode, ignores Python environment configuration and excludes the current directory and user site from the interpreter-created path; `-S` separately prevents automatic `site`, `.pth`, `sitecustomize` and `usercustomize` processing; `-B` suppresses bytecode-cache writes. `-B` does not by itself suppress bytecode reads, so the exact `pycache_prefix` points cache lookup beneath the verified character device `/dev/null`; reviewed source/bytecode validation must still reject every sourceless `.pyc`/`.pyo`. None changes the frozen Python version or permits uncovered bytecode. Because isolated/no-site startup omits both repository and installed dependency roots, the literal bootstrap preserves the interpreter-created standard-library path first, then appends, in order and with exact first-occurrence de-duplication, only the verified real repository root and the `purelib`/`platlib` roots returned by that interpreter's `sysconfig`. It must not call `site.main()`, `site.addsitedir()`, process a `.pth` file, add a user-site path, use `PYTHONPATH`, or import `sitecustomize` or `usercustomize`. The verified repository root must equal the real working directory before job creation; a different, relative, symlink-substituted or unverifiable root is rejected.

The literal first phase imports only `os` and `sys`, checks the flags, initial path and environment, and rejects every `_PYTHON*` key before importing or calling `sysconfig`. That order is frozen because `_PYTHON_SYSCONFIGDATA_NAME` and `_PYTHON_SYSCONFIGDATA_PATH` can otherwise select executable sysconfig data despite `-I`/`-E`. Only after that rejection may the bootstrap import the named standard-library helpers, derive paths, bind the launcher and insert a synthetic `quant` namespace package whose sole search location is the verified regular repository `quant` directory. It is constructed from the shown `ModuleSpec(..., loader=None, is_package=True)`; `module_from_spec` supplies CPython's standard namespace loader, so acceptance binds that resulting standard loader, `__package__ = "quant"`, the one exact `__path__`/`submodule_search_locations`, and absence of an origin/file rather than incorrectly requiring the resulting loader to remain `None`. This exact-head command deliberately does not execute tracked `quant/__init__.py`, whose eager import surface is not an authorized startup dependency; the initializer remains byte/source-bound and unedited. The namespace permits reviewed `quant.*` child imports without adding a file or widening the implementation allowlist. No other synthetic package, meta-path hook or loader is permitted.

The inline pre-import guard and the implementation's common startup-isolation guard both run before either runtime secret is read, copied or parsed. No repository or third-party application code is imported until the inline guard has passed. The scorecard module's import-time body may define/import reviewed code only: it must not read either runtime secret, open a connection, perform network I/O, dump the environment, log, inspect evidence or write a file; `provenance_probe_main()` and the existing scorecard `main()` invoke the common guard before any secret access. The guards require `sys.flags.isolated = 1`, `ignore_environment = 1`, `no_user_site = 1`, `no_site = 1`, `safe_path = 1` and `dont_write_bytecode = 1`; exact `sys.pycache_prefix`; the exact preferred-prefix path construction above; absence of `site`, `sitecustomize`, `usercustomize` and any prior `quant` module before bootstrap; exact synthetic-parent state afterward; and the verified regular source and interpreter bindings. They reject any relative, duplicate, missing or symlink-substituted bootstrap root or path not explained by the interpreter-created standard-library roots plus the verified real repository, `purelib` and `platlib` roots. Equality of `purelib` and `platlib` is permitted only through the literal stable first-occurrence de-duplication; no bootstrap entry may preexist in or duplicate the initial path.

Define the startup-injection set as every effective environment key beginning `PYTHON` except `PYTHON_VERSION`; every key beginning `_PYTHON`, `LD_`, `DYLD_`, `BASH`, `GIT_` or `OPENSSL_`; and the exact keys `ENV`, `SHELLOPTS`, `PS4`, `KSHENV`, `ZDOTDIR`, `GCONV_PATH`, `GLIBC_TUNABLES`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, their four lowercase spellings, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `SSLKEYLOGFILE`, `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE`. `PYTHON_VERSION` must exist exactly once with value `3.14.3`. Every startup-injection key must be absent, not empty, and `/etc/ld.so.preload` must not exist, including as a symlink. On the credential-free probe instance for exact build `B`, the inline guard proves those process/filesystem facts and proves that retained `PATH`, `shutil.which("python")`, real `sys.executable` and `/proc/self/exe` identify the same approved regular executable. The control plane separately proves the effective environment-key, command, build and configuration facts before either runtime secret is installed; restoring the two secrets may not change `PATH`, command resolution, build selection or any non-secret configuration. The inline and common guards independently recheck all process-visible facts before application code reads a secret; unsetting, masking or overwriting a value after process creation never cures its presence.

The pre-secret startup acceptance is provider-bound, not an impossible claim that Render's control plane can inspect a future one-off's `/etc` or `/proc`. The retained `ATOM-V1B-STARTUP-ISOLATION-1` portion of the existing operational packet binds the exact successful secret-free probe `J`, `B`, its `/etc/ld.so.preload` absence, exact interpreter/path/native measurements, the complete effective configured-environment absence, and current authoritative Render documentation or support evidence that a one-off for this service snapshots the selected successful build and its native runtime/system layer plus the then-configured environment. Independent review must accept that same-artifact/system-layer continuity before either secret is installed. Immediately before each secret-bearing Create job, the Owner revalidates through the control plane that `B` remains selected, no later build/deploy or configuration writer intervened, the only delta from the accepted secret-free environment is the two authorized secrets, every startup-injection key remains absent, and the exact isolated command is supplied. This is the complete feasible prelaunch proof; it explicitly does not claim a new per-job `/etc` or `/proc` read.

The trusted boundary is therefore the authenticated Render control plane's binding of the new job to the independently probed `B` and unchanged native runtime/system layer. If current vendor evidence cannot bind that layer, if the platform can silently substitute it, or if `B`/configuration continuity is ambiguous, no runtime secret is installed and V-1B is `BLOCKED`; a valid pending recovery remains on its existing consuming incident path and is not “re-probed.” An actual secret-bearing process still checks `/etc/ld.so.preload`, interpreter and every process-visible injection fact before application secret access. Because its native loader has already started, any such late mismatch is treated as possible credential exposure as well as startup failure: close without database/evidence access, preserve the applicable new-seal or consuming-recovery route, revoke the PAT under protective authority, keep the service suspended and require documentation-first disposition for the database credential. It is not retroactive proof that an unapproved loader saw nothing. Within the accepted provider boundary, this closes Python/sysconfig path injection, user-site/customization hooks, shell initialization/function/trace controls, command-wrapper substitution, Git/proxy/trust-store override paths, dynamic-loader audit/preload/library-selection hooks and the system preload file before a secret-bearing process begins. It does not protect against a compromised Render control plane/kernel or approved CPython/native artifact.

For the credential-free probe, the keys themselves `ATOM_E1_SCORECARD_READONLY_DATABASE_URL` and `ATOM_V1B_GITHUB_TOKEN` must additionally be absent from `os.environ`; empty strings do not satisfy absence. The probe does not unset or mask a secret after startup to claim absence. The control-plane removal sequence in §2.5 is also mandatory.

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

For an evidence-capable new-seal launch, inability to prove the external startup barrier prevents Create job and is non-consuming `BLOCKED`. An inline-bootstrap refusal exits 1 with empty stdout/stderr before application entry; it is a setup `BLOCKED` observation, not a scorecard negative file or a consuming invocation. A common-guard refusal after the reviewed source has loaded but before database/evidence access uses the existing `BLOCKED` route without a seal. Neither case invents a startup-specific receipt schema/reason or permits a weaker command. For recovery, the original seal has already consumed its identity: external/bootstrap/guard failure preserves that pending obligation and follows the existing consuming recovery/incident route. No process-side observation can retroactively prove that an unapproved pre-interpreter hook did not see a secret.

### 2.5 Secret-free build/probe sequence and actual build identity

The Owner performs these steps through the existing authenticated Render control plane, on service `srv-daa7thgae00c73a2lmn0` only. The scorecard receives no Render API key. The first build/probe precedes provisioning the new PAT and reinstallation of the rotated reader URI. A later build/probe uses the same sequence; it never reintroduces the exposed URI.

1. Verify that every earlier job is terminal and that no valid seal is awaiting recovery. Keep automatic deploys/previews off; reserve an exclusive manual configuration/build window. Set the base `startCommand` to exactly `python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"` and verify suspension. This invariant holds during all later steps, including rollback.
2. Remove both named secret keys and every §2.4 startup-injection key from this service's configured environment using the Environment control plane and Save only. This is the only new environment cleanup authorized by the startup correction. A service-level deletion must not reveal the same key from a linked environment group. Inspect effective key names and linked-group/secret-file/blueprint configuration privately. The upcoming secret-free probe—not a claimed control-plane filesystem read—must observe `/etc/ld.so.preload` absent in the exact successful build/runtime. A key supplied by a group, blueprint injection, mounted secret file or baked artifact is not cured by deleting a service override. This amendment does not authorize editing a shared group, another service, a build artifact or `/etc`: such a source blocks the probe until a separately authorized, service-scoped correction removes it. Do not log secret values. Retain only key-name/configuration absence and inert-command evidence before the probe; the probe supplies the system-preload/interpreter observation.
3. When this is a later probe and the same valid dedicated PAT/rotated URI must be restored, the Owner may retain those existing values only transiently in the existing secure control-plane session for this removal/reinstallation cycle. No new variable, file, command argument, clipboard transcript, token replacement or exposed-password backup is created. If secure retention is unavailable or lost, remain suspended; do not restore an exposed value or mint an unapproved replacement. On the initial probe, do not provision either secret early merely to remove it again.
4. Build the exact approved source `E` with the unchanged `pip install -r requirements.txt` and `PYTHON_VERSION=3.14.3`, with both keys absent. The existing per-invocation `ATOM_V1B_AUTHORIZED_MAIN_SHA`, when set, equals `E`; it is not used to carry provenance. Obtain the actual build-producing deploy object through Render’s service deploy history. `B` is that object’s returned immutable id, with `commit.id = E` and verified successful build completion. In `ATOM-V1B-RUNTIME-PROVENANCE-1`, the term `render_build_id` means this build-producing deploy ID; it is not an undocumented vendor field. `render_deploy_id` is the same `B` for this record. A build-only failure, a requested but unsuccessful deploy, a configuration-only redeploy mistaken for a build, an ambiguous latest artifact or a caller-assigned ID is unusable.
5. With no intervening build/configuration writer, re-read effective runtime-secret/startup-injection absence and the successful deploy/artifact selection, verify the base is suspended with the exact isolated inert command, then Create job with exactly §2.4’s `startCommand`. Do not claim this pre-job control-plane read inspected `/etc`; the secret-free probe itself supplies that live observation. Create job’s native snapshot must be the latest successful artifact `B` and the now-secret-free, startup-isolated configured environment. There is no assumed per-job environment override parameter. Retain the request, returned `J`, source/deploy observations bracketing creation and complete probe stdout. Resolve uncertain POST outcomes by listing/retrieving jobs, not by sending another POST.
6. Verify the exact success record, its local-byte/component hashes, job termination and parent suspension. Compare the returned source/service to `B` and `E`; independent acceptance must examine the authenticated build history, reviewed source/blob bindings and complete observation. A process’s own version strings or digests alone do not approve it. The trusted roots for this operational approval are the authenticated Render build/control plane, the authenticated reviewed GitHub source and the independent human/agent acceptance beneath Owner approval. This is not claimed to be remote hardware attestation against a compromised Render control plane or kernel.
7. Construct the provenance record below from those observed values. Keep its original canonical bytes and SHA-256 in the existing private operational acceptance packet. On initial setup only, after the probe terminates, obtain §3’s PAT scope evidence, §5.3’s authoritative vendor-limit evidence (not the later actual-seal calculation), and §2.4's provider-bound same-artifact/system-layer evidence. Then open and independently accept §4’s no-ref-update window while both runtime secrets remain absent. Only inside that active accepted window perform §6’s temporary `NOLOGIN`, pre-rotation drain/two reader-OID-selected termination passes and full reader/unattributed guards, one actual verified rotation, post-rotation stale-verifier drain, pooler termination-or-containment proof and conforming-URI provisioning; install only the properly scoped dedicated PAT and newly rotated conforming URI using Save only; restore `LOGIN`; and complete every required backend/prepared/settings zero check. Immediately re-read the complete effective environment and configuration: relative to the accepted secret-free state, only those two authorized secret keys may have been added; every startup-injection key remains absent; the isolated inert command, `B` and every other non-secret value remain exact. Bind the still-current accepted `B` system-preload/interpreter baseline without claiming the control plane re-read `/etc` or `/proc`. Record the no-ref-window, URI-update and startup-isolation confirmations, finalize the incident, and only then obtain independent acceptance and issue §2.6’s Owner approval. For a later build/probe, first lawfully close any earlier window and satisfy §2.5 step 1; after the later probe, open and independently accept a new §4 window before restoring the same still-valid PAT and same already-rotated conforming URI retained under step 3. A later probe does not authorize another password rotation, replacement PAT or new incident completion timestamp. Reconfirm scope, incident disposition, current vendor-limit/system-layer evidence, prior backend/pooler-termination-or-containment disposition, the newly accepted window and safe credential reinstallation before issuing that source revision’s separate approval; preserve the original rotation timestamp and finalization digest unless a separately authorized factual incident addendum requires explicit new review. Because a newly created one-off snapshots configured variables and the existing successful artifact, this does not require a new build. Before every evidence-capable new-seal or recovery Create job, revalidate and retain the effective startup-injection absence, accepted `B`/provider-bound system-layer baseline, isolated command and active-window proof; permit no configuration/ref writer between that proof and job creation. This is not a new probe and does not abandon a pending seal. If the platform instead changes the artifact, exposes an injection source, loses the window, refuses the accepted snapshot semantics or requires an unapproved replacement build, no evidence-capable job is accepted.

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

Let `W` be the exact canonical non-secret public projection of the independently accepted §4 opening record:

```text
schema_version       = "ATOM-V1B-NO-MAIN-UPDATE-WINDOW-1"
repository           = "atomatom148-dotcom/ATOM"
repository_id        = 1339927428
ruleset_id           = actual returned positive integer
name                 = "ATOM-V1B-NO-MAIN-UPDATE-1"
target               = "branch"
source_type          = "Repository"
source               = "atomatom148-dotcom/ATOM"
enforcement          = "active"
conditions           = {"ref_name":{"include":["refs/heads/main"],"exclude":[]}}
rules                = [{"type":"deletion"},{"type":"non_fast_forward"},{"type":"update","parameters":{"update_allows_fetch_and_merge":false}}]
bypass_actors         = []
created_at            = exact immutable GitHub timestamp from Owner readback
updated_at            = exact GitHub timestamp at the accepted opening readback
execution_source_sha  = E
manifest_id           = M
opened_at_utc         = actual Owner-control-plane opening observation, UTC RFC3339 microseconds
```

The `rules` list above is the canonical type-sorted projection, independent of response ordering. The Owner's write-authorized creation/readback must expose and prove the empty `bypass_actors`; the runtime's read-only PAT is not expected to receive that sensitive field. The Owner/reviewer instead bind its absence to the same returned ruleset ID and initial `updated_at`; any edit, deletion/recreation or changed public projection later fails §4. `W` contains no credential and no general ruleset URL. When any earlier V-1B window for this repository has lawfully closed, the private `control_plane_evidence_sha256` bound into the new approval additionally covers every such earlier window's exact `W`, Owner-approval comment ID, terminal-output/seal/receipt disposition, complete control/history audit, ruleset-deletion readback and closure time. A lawful closure is either §4's clean closure or a documentation-first incident disposition that expressly authorizes deletion. An incident-closed no-seal window must additionally prove no seal/look existed and expressly say whether any later fresh window—including one for the same or a different `E` or `M`—is permitted; an incident involving a consumed seal grants no replacement look. That retained repository-wide closure chain is reviewed before the new window is approved; it does not edit or delete an earlier immutable approval comment.

The approval payload `A` has exactly:

```text
schema_version = "ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-1"
provenance = P
provenance_sha256 = sha256(canonical_json(P))
capacity = C
no_ref_update_window = W
no_ref_update_window_sha256 = sha256(canonical_json(W))
probe_job_id = actual successful §2.4 job ID J
probe_observation_sha256 = sha256(canonical_json(successful probe object))
control_plane_evidence_sha256 = digest of retained non-secret same-build, runtime-secret-absence, startup-isolation and §4 no-ref-update-window evidence
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

Every authenticated GitHub `GET` used by the initial, pre-seal/prior-look, final or recovery repository check uses these exact immutable integer literals:

```text
GITHUB_CONNECT_TIMEOUT_NS            = 10_000_000_000
GITHUB_READ_IDLE_TIMEOUT_NS          = 20_000_000_000
GITHUB_REQUEST_TOTAL_TIMEOUT_NS      = 60_000_000_000
GITHUB_PAGINATION_TOTAL_TIMEOUT_NS   = 180_000_000_000
GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS   = 300_000_000_000
```

They are implementation literals, not environment/configuration values, operator inputs, server hints or receipt/identity fields. All elapsed-time decisions use `time.monotonic_ns()`. One 300-second checkpoint deadline starts immediately before the checkpoint's first DNS or network operation and ends only after every required endpoint, page, canonical body, hash, signature, ancestry, uniqueness and coherent-ref validation for that checkpoint has completed. Each paginated collection gets one separate 180-second pagination deadline beginning immediately before page 1's DNS/network operation and ending only after the fully validated final page; it is not reset by any page or response and remains subordinate to the earlier checkpoint deadline. Each request gets one 60-second request-total deadline beginning before its DNS/network operation. Its 10-second connect sub-deadline covers DNS resolution, all address attempts, TCP connection and TLS certificate/hostname verification together; it is not renewed per address. Its 20-second read-idle deadline begins after request bytes are transmitted and is reset only when at least one new response octet is delivered; it covers stalls before status, within headers/framing and within the body. The request-total deadline covers request transmission through full response receipt and validation. Every operation must finish before the earliest applicable connect, read-idle, request-total, pagination or checkpoint deadline; checking only after an unbounded call returns is nonconforming.

Synchronous in-process `getaddrinfo()` is not accepted as deadline enforcement. For each request, before reading, copying or formatting `ATOM_V1B_GITHUB_TOKEN`, the reviewed scorecard starts exactly one short-lived resolver child using the same approved absolute `sys.executable`, the exact isolated interpreter switches from §2.4, fixed reviewed `-c` source in `quant/volatility_scorecard.py`, `close_fds = true`, a private stdout pipe, stderr redirected to the null device and an explicit child environment containing only `PYTHON_VERSION=3.14.3`. File descriptor 0 is not caller input: it is a parent-owned private acknowledgement pipe carrying only the fixed protocol below; no operator byte or secret enters it. The child resolves only `api.github.com` port `443` with `AF_UNSPEC`, `SOCK_STREAM` and `IPPROTO_TCP`. It discards a duplicate full normalized entry after its first occurrence. On success it emits exactly one canonical ASCII JSON object plus LF with sole key `addresses`; the value contains 1 through 64 remaining entries in first-returned order, each exactly `["AF_INET", numeric_address, 443]` or `["AF_INET6", numeric_address, 443, flowinfo, scope_id]`, with integer flow/scope values. The complete output maximum is 16,384 bytes. It writes those bytes directly to descriptor 1, closes descriptor 1, and then blocks without further import, dynamic load, resolution or network action awaiting exactly the single acknowledgement octet `0x01` followed by EOF on descriptor 0. Any other family, invalid numeric address/port/type, empty result, 65th unique entry, encoding beyond that byte cap, caught resolution/serialization error, other/no acknowledgement, nonzero exit or trailing stdout byte is failure; nothing is truncated or partially accepted. The fixed child catches errors, writes no diagnostic, and exits 1; null-device stderr redirection is a second containment and no child diagnostic enters the scorecard's required-empty stderr. Neither runtime secret, proxy/trust variable, credential, repository value nor caller-supplied host enters its environment, arguments, acknowledgement pipe or output.

The parent opens and retains a Linux pidfd for the returned child PID, drains the private stdout pipe nonblockingly while enforcing both the 16,384-byte cap and shared connect deadline, and requires EOF after the single line while the pidfd and `poll()` both prove that same child remains alive. Before token access or acknowledgement, the parent requires `/proc/<pid>/exe` to resolve to the exact approved interpreter and reads `/proc/<pid>/maps` twice using the unchanged V-1A executable-mapping/path/digest rules. The two complete canonical map observations must be byte-identical. Every child executable regular-file mapping must be either the exact measured Python executable or an exact path-and-byte-digest member of the parent invocation's already frozen candidate `loaded_native_tree`; every executable anonymous/special mapping must satisfy the inherited permitted-mapping rules. That parent candidate is subsequently required to equal the authenticated approved provenance before the request/checkpoint can pass. Thus no child-only native byte becomes an unapproved component and no provenance schema expands. An unreadable/racing map, changed child identity, extra/different executable file or mapping defect causes the parent to close the acknowledgement pipe without a byte, kill if still live, synchronously reap, close every pipe/pidfd, discard all addresses and fail before token access.

Only after successful output, identity and two-map validation does the parent write exactly `0x01`, close the acknowledgement pipe, require child exit 0, synchronously reap it and close the pidfd strictly before the shared connect deadline. On byte 16,385, premature child exit, failure or deadline it performs the same kill/reap/close/discard route. No resolver child, thread or future may survive either outcome. The parent then reads the token and performs nonblocking address attempts and TLS handshake itself, using `api.github.com` exactly for SNI and hostname verification and the same deadline; it never sends the token to the resolver or connects to an unreturned address. All socket connect, TLS handshake, request write and response reads use nonblocking state plus the remaining monotonic deadlines; a timeout path closes the socket synchronously. This resolver child adds no service, module, dependency, credential source, retry or runtime input; its pure-Python imports remain within the measured stdlib tree, and its native execution is accepted only by the exact subset proof above.

Success requires each applicable completion observation to be strictly earlier than every applicable deadline; equality or one nanosecond later fails. A failed deadline, partial status/header/body, invalid framing, any HTTP `3xx` status, any response containing a `Location` header or incomplete page is discarded and cannot be combined with cached bytes, a prior checkpoint or another invocation. Follow no redirect—not even same-origin—and never retransmit the `Authorization` header in response to one. Close the response/connection as applicable. Do not automatically retry a timed-out/failed request, honor `Retry-After`, sleep/back off, use unauthenticated transport, change host/path/page size, continue pagination in the background or fall back to a local cache. Section 4 permits no ref-movement reread: a changed or mixed ref observation fails that checkpoint inside its original immutable deadlines.

Read all pages by increasing page by one while a same-origin/same-path `rel=next` is present; validate the next link agrees with that exact request and never follow another host, repository or path. An incomplete, inconsistent or failed pagination is not an empty result. First collect every structurally valid exact-schema V-1B Owner approval for repository `atomatom148-dotcom/ATOM` and repository ID `1339927428`, without prefiltering its execution SHA or manifest. Authenticate each Owner envelope as `user.id = 307819087` and `user.login = atomatom148-dotcom`, validate its canonical body/digests sufficiently to obtain its exact fixed positive `W.ruleset_id`, and, under the same checkpoint/pagination deadline, make the fixed-ID ruleset `GET` required by §4 for every collected approval—never just the newest comment or selected manifest. Classify one as `CURRENT` only when that request returns HTTP 200 and the complete public projection equals its exact `W` with active enforcement. A ruleset HTTP 404 may classify an older approval as `HISTORICAL_CLOSED`, rather than a duplicate, only when it predates the proposed current window and the proposed current approval's independently reviewed `control_plane_evidence_sha256` covers that earlier approval's exact repository-wide lawful closure record described above. A 200 mismatch, disabled rule, 403/other status, missing closure binding, a prior rule left active, or any ambiguous response fails the checkpoint; none is historical by assumption.

Require exactly one `CURRENT` approval and zero other active/current V-1B window for the repository. Only then require that sole current approval's `payload.provenance.execution_source_sha == E`, `payload.no_ref_update_window.execution_source_sha == E` and `payload.no_ref_update_window.manifest_id == M`. Require its canonical body, all digests and fields—including exact `W` and `no_ref_update_window_sha256`—to validate; its source/service/build/window tuple to match the approved execution; and its referenced prior unedited PASS review, found in the same fully read discussion, to hash the identical `A`. The reviewer’s authenticated ID/login must equal the two explicit reviewer fields in the Owner approval and must differ from the Owner approval author. Those fields are the runtime’s exact designation input; it does not read a private designation file. The Owner and independent final audit additionally verify actual independence from the implementation job and every cited historical closure in the retained ownership/review record. Mere comment text claiming “Owner,” “PASS” or “closed” is insufficient.

No zero-current fallback, multiple-current choice, “latest” choice, caller-selected comment/ruleset ID, local metadata cache or URL extracted from a comment is accepted. Historical immutable approvals are retained for audit but can never be reused as current authority; their lawful deletion/closure does not permanently prevent a later sequential window. Fixed references in `A` are evidence locators for the external reviewer, not runtime fetch instructions. The runtime derives `B` from authenticated `P`, not from an invented environment field. The Owner’s bracketing Render evidence proves the actual job’s artifact selection; the runtime separately proves exact approved bytes/source. Do not describe the latter as a direct Render API attestation inside the process.

Fetch/revalidate the identical current approval and review body hashes, repeat the complete current/historical classification, and reject any newly active duplicate at the pre-seal and final repository checks and during recovery. Verify the current approval predates the invocation’s evidence read; the external launcher does not create the job until approval exists. The underlying private scope/incident/limit/window-closure evidence and same-build selection must still be valid at action time. Any discovered change stops the action rather than silently updating `A`. Approvals remain retained after PAT removal. Current-approval loss, ambiguous lifecycle state, multiple current approvals or post-seal mismatch uses §2.3 failure routing.

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

Use the token only for authenticated HTTPS `GET`s to GitHub’s API for this exact repository’s existing authority/history/receipt verification. Never put it in a URL or subprocess argument. Every HTTP `3xx` response or `Location` header is a hard failed request: follow no redirect of any origin and never retransmit the `Authorization` header. Do not serialize or log the token, its digest, an `Authorization` header, a complete environment, a credential-bearing request or an exception containing any of those. Persistence is restricted to Render’s secret storage; the process uses it transiently in memory for authenticated transport. It enters no manifest, seal, receipt, test fixture or repository artifact.

Required authenticated PR metadata and merge proof remain mandatory. The inspected repository is public; endpoints exposing public PR metadata can be used with the authenticated request without granting new optional token permissions. If GitHub refuses a required read, or repository visibility/permissions change, stop: do not remove authentication, broaden the token or replace PR metadata with an unsigned commit-message assertion. Deployment acceptance must prove that the exact restricted token can perform every required read before any database access.

This new secret is separate from, and never a substitute for, the existing database URI. No Render API or Supabase administrative token is installed in the scorecard runtime.

## 4. Authenticated default-branch predicate instead of branch protection

Select the Owner-enforced no-ref-update-window route. No descendant or “unrelated change” classifier is used while an invocation can create or discharge a V-1B look. Except for the exact temporary rule below, this amendment still authorizes no branch-protection, ruleset, repository visibility, standing review-policy or standing check-policy mutation.

In Amendment 2A §§9.1 and 10.3 and every incorporated V-1B reference, replace “current protected main head” with “authenticated current default-branch head for the exact repository, whose default branch is `main`, held at the exact execution SHA by the active §4 no-ref-update window.” A pre-window `protected=false` flag is not itself a failure. Absence, ambiguity or loss of the exact active window is.

After the exact Amendment 3 and implementation merges and the credential-free accepted build/probe, but before either `ATOM_V1B_GITHUB_TOKEN` or `ATOM_E1_SCORECARD_READONLY_DATABASE_URL` is installed in or otherwise made accessible to the Render service, the Owner opens one window scoped to exactly one manifest `M`. That window may contain its single new-seal attempt and only the exact recovery attempts needed to discharge a seal emitted by that attempt, or it may be opened solely to discharge one already-pending exact seal for `M`; it may never contain another manifest, new look or replacement identity. A later sequential window—whether for the same or a different `E` or `M`—is permitted only after the prior repository-wide window was lawfully closed, its exact ruleset was deleted, its immutable approval became `HISTORICAL_CLOSED` under §2.6, and the new window receives fresh independent review and Owner approval; an incident-closed window additionally obeys the no-seal/retry restriction below. Concurrent or overlapping windows are forbidden across the entire repository, not merely within one execution SHA or manifest. The Owner first verifies no merge queue entry, auto-merge, bot, workflow, direct push, administrative push or other accepted ref-update request is pending for `refs/heads/main`; authenticates the repository identity/default branch and current 40-lowercase-hex head `E`; and records the complete pre-window matching-ruleset state plus every applicable prior closure. Any queued or uncertain writer or still-active earlier rule must be resolved without updating `main` before the window opens.

The Owner then creates and activates one temporary repository branch ruleset named exactly `ATOM-V1B-NO-MAIN-UPDATE-1`, targeting only `refs/heads/main`, with exactly these effective rules and no bypass actor, role, team or app:

```text
target                 = branch
enforcement            = active
include                = refs/heads/main
exclude                = none
restrict updates       = enabled
restrict deletions     = enabled
block force pushes     = enabled
bypass actors          = none
```

This is the sole narrow exception to the otherwise preserved no-ruleset-mutation rule. It authorizes no required review, status check, merge method, visibility, default-branch, actor-permission or other repository-setting change. The Owner uses its existing authenticated GitHub control plane, never the read-only V-1B PAT. If GitHub cannot apply `restrict updates` to the exact existing ref without an implicit administrator/Owner bypass, if an organization/enterprise rule can override it, or if the exact effective state cannot be read back, evidence-capable activation is `BLOCKED`; a procedural promise, open PR freeze, branch-protection badge or endpoint-equality observation is not a substitute.

The retained non-secret `ATOM-V1B-NO-MAIN-UPDATE-WINDOW-1` operational record binds the returned ruleset ID, its creation and last-update timestamps, its complete canonical write-authorized readback and digest, repository ID, exact ref, `E`, opening time, zero pending-writer observations, pre-window ruleset-state digest, invocation/recovery manifest `M`, and the actual Owner identity. It also binds the complete opening ruleset-history proof defined below. Before installing either runtime secret, read back the same active ruleset and authenticate `refs/heads/main == E`. No runtime secret is installed and no job is created until independent operational acceptance verifies that record. Its exact non-secret projection `W` and digest are explicit fields of the §2.6 approval payload; the complete private/control-plane evidence remains bound by `control_plane_evidence_sha256`. Neither adds a receipt, seal or identity field.

Using only the Owner's existing write-authorized GitHub control plane—not the V-1B PAT—read the complete new ruleset history at opening with `GET https://api.github.com/repos/atomatom148-dotcom/ATOM/rulesets/{W.ruleset_id}/history?per_page=100&page=1`, following every authenticated same-origin/same-path `rel=next` page to completion. Reject a repeated/skipped page, inconsistent pagination, non-200 response or incomplete body. Canonically sort the complete returned entries by integer `version_id`; reject a duplicate/nonpositive ID. For every listed ID, make `GET https://api.github.com/repos/atomatom148-dotcom/ATOM/rulesets/{W.ruleset_id}/history/{version_id}` and retain the complete authenticated version object. For the highest version, require `state.id`, `name`, `target`, `source_type`, `source`, `enforcement`, `conditions` and the type-sorted complete `rules` to equal the corresponding fields in `W`, and require `state.bypass_actors = []`. Separately require the current fixed-ID GET's public `id`/name/target/source/enforcement/conditions/rules plus `created_at`/`updated_at` projection to equal `W`, and its write-authorized `bypass_actors` to equal `[]`; do not compare either vendor response to `W`'s local repository ID, `E`, `M` or `opened_at_utc` fields. Retain the canonical history list, every version body/API envelope and their SHA-256 digests as the opening history baseline. The Owner's credential already needs Administration: write to create/delete the rule; this history read is part of that same narrow control-plane lifecycle and supplies no permission or credential to the runtime.

From before the accepted opening until the post-deletion closure readback, the Owner holds one exclusive repository ref/settings-writer gate: no second operator, merge queue, auto-merge, bot, workflow or other automation may acquire or schedule authority to update `main`, its default-branch identity or the temporary rule. From accepted opening until the window is lawfully closed, every merge, queue delivery, auto-merge, bot/direct/admin push, force update and `main` ref deletion/recreation is prohibited, including SIM, HIST8, documentation, implementation, rollback and receipt merges. Pull-request/comment/review metadata that cannot update a Git ref remains permitted. The selected ruleset may not be edited, disabled, bypassed, deleted or replaced. `E -> X -> E` is a breach even though endpoint equality is restored. The source-safety invariant between brackets is the continuously active, unchanged, literal-`refs/heads/main`, empty-bypass selected rule plus `main = E`; default-branch metadata and other matching-ruleset state are required exact at the opening, runtime, post-job and closure brackets but are not falsely claimed to have a complete interval log. The writer gate forbids intentionally changing them; any separately discovered transient change is an operational incident, but it is a V-1B source-identity breach only if the selected rule or `main` invariant was lost. Any emergency protective action may stop the Render job or revoke credentials immediately, but it does not authorize a main-ref update or erase a crossed seal. If the exclusive writer gate or the absence of pending writers cannot be established, no runtime secret is installed.

For every initial, pre-seal/prior-look, final and exact-recovery repository checkpoint, authenticated repository metadata must still identify repository `atomatom148-dotcom/ATOM`, repository ID `1339927428`, owner `atomatom148-dotcom` and `default_branch = main`; authenticated ref metadata must identify exactly `refs/heads/main` and `H = E`. The checkpoint performs §2.6's complete approval classification and then uses the fixed ID from the one `CURRENT` validated Owner approval `W`—never a caller-selected ID—to make an authenticated, deadline-bound `GET` of exactly `https://api.github.com/repos/atomatom148-dotcom/ATOM/rulesets/{W.ruleset_id}?includes_parents=true`. Require HTTP 200 and exact equality of the response's `id`, `name`, `target`, `source_type`, `source`, `enforcement`, `conditions`, type-sorted complete `rules`, `created_at` and `updated_at` projection to `W`; `W.repository`, `repository_id`, `execution_source_sha` and `manifest_id` must equal the checkpoint's exact repository, `E` and selected `M`. The read-only response may omit `bypass_actors`; if it returns that field, it must equal `[]`. Its omission never creates a bypass assumption: the independently accepted Owner readback proved `[]`, and the runtime's unchanged ID plus `updated_at` binds that opening state. A 404 for the purported current rule, omission/mismatch, new rule, changed parameter, disabled enforcement, changed timestamp, multiple current approvals or missing current approval fails the checkpoint.

Do not substitute a local remote-tracking branch, cache, PR head, tag, environment claim, caller-supplied ref/ruleset or descendant. Build one coherent checkpoint observation by reading the ref to immutable `H`, obtaining the exact ruleset projection and all required commit/tree/blob/PR/receipt facts by immutable object identity, and rereading both the fixed ruleset ID and ref after validation. Both ruleset projections must equal `W`, and both ref observations must equal `E`. A changed ruleset/ref, mixed observation or unresolved inconsistency fails immediately; there is no movement reread, replacement ruleset or descendant acceptance. Retain `RENDER_GIT_COMMIT == ATOM_V1B_AUTHORIZED_MAIN_SHA == git rev-parse HEAD == E`, every exact Owner-merged V-1A/TLS/2A/Amendment-3/implementation identity, verified PR/signed-merge/ancestry proof and every existing implementation/worktree mode/blob/raw-byte and prior-look check. The final checkpoint, including the second ruleset/ref read, occurs after truthful cell calculation and immediately before receipt construction; on success the process performs no intervening network operation, blocking wait, dynamic load or mutable source read before synchronously constructing the receipt. Any persistent mismatch observable at that final checkpoint uses the preserved POST-EVALUATION AUTHORITY INVALID route as the first complete terminal receipt. These endpoint snapshots prove the state at their observation times; they do not purport to detect a transient `E -> X -> E` ref movement or ruleset edit/reversion between observations.

The external Owner-controlled launcher revalidates the ruleset ID, unchanged `updated_at`/canonical readback and `H = E` immediately before each secret-bearing Create job. After that job is terminal, while the exclusive writer gate and rule remain active, it repeats the fixed-ID/ref/default-branch reads and the complete Owner-authorized history/version sequence above. Require the complete canonical history list and every version body to be byte-identical to the opening baseline, the current selected state to remain active/no-bypass/equal to `W`, `default_branch = main` at the bracket and `H = E`. This post-terminal ruleset-history audit—not the runtime endpoint snapshots—is what can detect a transient selected-rule edit/reversion; a deletion/recreation cannot restore the same ruleset ID and would fail the fixed-ID/history reads. Because the continuously active exact `update`, `deletion` and `non_fast_forward` rules had no bypass actor and their version history did not change, an accepted `main` ref update during that interval was forbidden by the selected GitHub enforcement mechanism; the two exact `H = E` brackets confirm its endpoints. No nonexistent exhaustive ref-event/default-branch/other-ruleset ledger is claimed. A discovered selected-history/version change, accepted/effective bypass, fixed-ID loss or `H != E`, and any persistent default-branch mismatch at a required bracket, is a window breach; endpoint equality alone cannot cure a selected-history change. A rejected update request that provably changed no selected-ruleset/ref state is retained in the audit but is not a source-identity failure and does not consume a look. If GitHub cannot supply the complete independently reviewable selected-rule history/version endpoints, expose the empty bypass list to the Owner, enforce the exact rule on this repository/plan, or keep the exclusive writer gate, V-1B is `BLOCKED` before either secret is installed.

The Owner may close the window as clean only after the complete control/history audit passes and exactly one of these mutually exclusive branches is proved: (a) no Create-job request was accepted—every uncertain POST is resolved through job listing/retrieval, no job/seal/look exists, the setup failure is retained, and the two runtime secrets are absent/revoked as their lifecycle requires; (b) one authorized job exists, it is terminal, no seal was emitted, and the complete required output disposition is retained—HOLD, WAIT, usage, pre-seal negative, or a provably pre-application bootstrap/infrastructure failure with its required empty output and control-plane evidence; or (c) every emitted valid seal has its first complete terminal evaluated/consuming-negative receipt retained and hash-bound. Truncated/missing output permits branch (b) only when independent control-plane/startup evidence proves the process failed before any seal-capable application entry; otherwise absence of a seal is unproven and the window remains open for incident/recovery disposition. A valid seal without its first complete terminal receipt likewise keeps the same ruleset active through exact recovery or lawful consuming-negative/incident closure. The receipt PR may be prepared but cannot merge while the rule is active. At clean closure, while retaining the exclusive writer gate, recheck that no merge/queue/bot/workflow/direct/admin ref update is pending; independently verify the unchanged fixed-ID ruleset/history, default branch and `H = E`; record the close time and applicable setup/job/output/seal/receipt digests; then delete exactly this temporary ruleset through the Owner control plane. Still admitting no ref/settings writer, verify the pre-window matching-ruleset state is restored and `H = E`. Only after that post-deletion readback may the Owner release the exclusive gate and allow unrelated or receipt merges. A pending/uncertain writer, job outcome, seal state or inability to hold the gate leaves the rule active and prevents clean closure.

Failure to open or verify the window before secrets/evidence is non-consuming `BLOCKED`. A breach observable by the running process after evidence reads but before seal follows the existing null-seal PRE-CELL INVALID route. A breach observable by the running process after seal or while exact recovery is pending/accepted follows the existing consuming-negative route; after complete truthful cells an observable final-check failure uses POST-EVALUATION AUTHORITY INVALID.

A breach first discovered only after process termination by the mandatory control/history audit or other authoritative evidence cannot retroactively change bytes already emitted by the terminated process. It is therefore a documentation-first repository-authority/security incident, not permission to fabricate, replace, suppress or amend a runtime receipt. If no valid seal was emitted, no look was consumed: retain the setup/job/output evidence unchanged and allow no later invocation until the reviewed incident disposition proves the no-seal state, lawfully closes/deletes this window and confirms that a fresh window is permitted by all existing eligibility and incident rules. This amendment independently grants no retry. If a valid seal was emitted, retain every seal, log and first complete receipt unchanged; the look remains consumed, no replacement look is authorized, and that first receipt must be submitted/merged exactly as Amendment 2A §§7.3 and 11 already require. If no first complete receipt exists, the original exact recovery or consuming-negative/incident obligation remains; no new identity is created.

Nothing in this post-terminal branch changes Amendment 2A's receipt, nonselective-continuation or one-look law. The separately retained incident record binds the later-discovered control evidence without altering the official receipt schema or selecting on protected output. In either the no-seal or sealed branch, the window may not be recorded as cleanly closed. If the exact rule remains active, retain it and the exclusive writer gate; if it was lost or changed, do not fabricate continuity or create a replacement ruleset under this amendment—hold all voluntary ref/settings writers and obtain the documentation-first incident decision plus the applicable existing receipt/recovery disposition before lawful deletion/closure or any further V-1B invocation. Once closure and post-deletion readback are lawfully authorized, any required receipt PR proceeds under its unchanged rule. Such an unauthorized enforcement/window breach is not ordinary “unrelated main movement.” The active no-bypass rule structurally defers all authorized unrelated movement, so ordinary repository work cannot consume a sealed V-1B identity.

Required signed merge objects retain GitHub’s passing signature verification and authenticated association with the exact Owner-approved merged PR. A signature alone does not establish Owner approval, required-green checks, PR scope or merge identity. No existing exact merge-time, evidence-byte, implementation-diff, receipt or one-look proof is replaced.

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

After both merge gates, the Owner may configure only: the exact isolated probe/base/job commands below and in §2.4; `PYTHON_VERSION=3.14.3`; the existing per-invocation `ATOM_V1B_AUTHORIZED_MAIN_SHA`; removal from this service only of a §2.4 startup-injection key; the §3 secret; the §6 replacement value for the existing reader URI, including their exact §2.5 removal/reinstallation sequence; and the exact deployment/suspension operations in this section. No generic environment replacement, shared-group edit or platform-file mutation is authorized.

Remove the inspected stale service command:

```text
python -m quant.evidence_scorecard --recent-sessions 10; sleep infinity
```

It must not execute during V-1B setup or invocation. No sleep, polling loop, cron entry, queue consumer, scheduler, retry wrapper, shell continuation into E-1, or unattended restart into a new scorecard attempt is permitted.

### 5.2 Closed command registry

During all V-1B setup, provenance, invocation, recovery and cleanup operations, the base background service start command remains permanently inert and exactly:

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"
```

No scorecard command is ever stored as the base service’s start command. Each authorized scorecard command exists only in the explicitly created one-off job’s `startCommand`. Every normal row uses §2.4's same two-phase guard, direct `sys.path` bootstrap and exact synthetic namespace `quant` parent, then executes the existing module as `__main__`; interpreter options are not scorecard CLI options.

The exact normal-command bootstrap is the following complete byte string with no trailing whitespace:

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; i=tuple(sys.path); r=os.getcwd(); z="/etc/ld.so.preload"; b=any((k.startswith("PYTHON") and k!="PYTHON_VERSION") or k.startswith(("_PYTHON","LD_","DYLD_","BASH","GIT_","OPENSSL_")) or k in {"ENV","SHELLOPTS","PS4","KSHENV","ZDOTDIR","GCONV_PATH","GLIBC_TUNABLES","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","http_proxy","https_proxy","all_proxy","no_proxy","SSL_CERT_FILE","SSL_CERT_DIR","SSLKEYLOGFILE","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix=="/dev/null/atom-v1b-no-pyc" and os.environ.get("PYTHON_VERSION")=="3.14.3" and not b and not os.path.lexists(z) and not {"site","sitecustomize","usercustomize"}.intersection(sys.modules) and not any(n=="quant" or n.startswith("quant.") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and len(i)==len(set(i)) and all(isinstance(v,str) and v and os.path.isabs(v) and os.path.realpath(v)==v for v in i)); o or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme("prefix")); a=tuple(dict.fromkeys((r,os.path.realpath(p["purelib"]),os.path.realpath(p["platlib"])))); d=os.path.join(r,"quant"); v=os.path.join(d,"volatility_scorecard.py"); x=os.path.realpath(sys.executable); w=shutil.which("python"); o=(all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath("/proc/self/exe") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat("/dev/null",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec("quant",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules["quant"]=importlib.util.module_from_spec(s); import runpy; runpy.run_module("quant.volatility_scorecard",run_name="__main__",alter_sys=True)'
```

An authorized normal `startCommand` is exactly that bootstrap, one ASCII U+0020 space, and exactly one of these nine suffix byte strings, with no additional byte:

```text
--manifest-id v1b-early-4
--manifest-id v1b-family-5m
--manifest-id v1b-family-15m
--manifest-id v1b-family-30m
--manifest-id v1b-family-1h
--manifest-id v1b-v9-5m
--manifest-id v1b-v9-15m
--manifest-id v1b-v9-30m
--manifest-id v1b-v9-1h
```

These are alternatives for separate invocations, not a script to run all nine. Do not add an operator-selected date, session count, minimum, seed, horizon override, output-based retry or force flag. The registry, early-terminal prerequisite and deterministic boundary resolver remain exactly Amendment 2A’s.

Exact recovery uses the same selected command with exactly this existing suffix:

```text
--recovery-seal-file /tmp/atom-v1b-seals/<seal_record_sha256>.json
```

Replace the angle-bracket token with the retained record’s exact 64-lowercase-hex digest. A one-off job does not inherit the base service’s local recovery file. Therefore, for recovery only, its exact `startCommand` is the following local staging-and-exec template, not an assumption that the file already exists:

```text
python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; i=tuple(sys.path); r=os.getcwd(); z="/etc/ld.so.preload"; b=any((k.startswith("PYTHON") and k!="PYTHON_VERSION") or k.startswith(("_PYTHON","LD_","DYLD_","BASH","GIT_","OPENSSL_")) or k in {"ENV","SHELLOPTS","PS4","KSHENV","ZDOTDIR","GCONV_PATH","GLIBC_TUNABLES","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","http_proxy","https_proxy","all_proxy","no_proxy","SSL_CERT_FILE","SSL_CERT_DIR","SSLKEYLOGFILE","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix=="/dev/null/atom-v1b-no-pyc" and os.environ.get("PYTHON_VERSION")=="3.14.3" and not b and not os.path.lexists(z) and not {"site","sitecustomize","usercustomize"}.intersection(sys.modules) and not any(n=="quant" or n.startswith("quant.") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and len(i)==len(set(i)) and all(isinstance(v,str) and v and os.path.isabs(v) and os.path.realpath(v)==v for v in i)); o or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme("prefix")); a=tuple(dict.fromkeys((r,os.path.realpath(p["purelib"]),os.path.realpath(p["platlib"])))); d=os.path.join(r,"quant"); v=os.path.join(d,"volatility_scorecard.py"); x=os.path.realpath(sys.executable); w=shutil.which("python"); o=(all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath("/proc/self/exe") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat("/dev/null",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec("quant",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules["quant"]=importlib.util.module_from_spec(s); D="/tmp/atom-v1b-seals"; os.mkdir(D,0o700); P=D+"/<seal_record_sha256>.json"; F=os.open(P,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); H=os.fdopen(F,"wb"); H.write(bytes.fromhex("<seal_bytes_hex>")); H.close(); Q=bytes.fromhex("696d706f7274206f732c7379733b20653d66726f7a656e736574286f732e656e7669726f6e293b20663d7379732e666c6167733b20693d7475706c65287379732e70617468293b20723d6f732e67657463776428293b207a3d222f6574632f6c642e736f2e7072656c6f6164223b20623d616e7928286b2e737461727473776974682822505954484f4e222920616e64206b213d22505954484f4e5f56455253494f4e2229206f72206b2e737461727473776974682828225f505954484f4e222c224c445f222c2244594c445f222c2242415348222c224749545f222c224f50454e53534c5f222929206f72206b20696e207b22454e56222c225348454c4c4f505453222c22505334222c224b5348454e56222c225a444f54444952222c2247434f4e565f50415448222c22474c4942435f54554e41424c4553222c22485454505f50524f5859222c2248545450535f50524f5859222c22414c4c5f50524f5859222c224e4f5f50524f5859222c22687474705f70726f7879222c2268747470735f70726f7879222c22616c6c5f70726f7879222c226e6f5f70726f7879222c2253534c5f434552545f46494c45222c2253534c5f434552545f444952222c2253534c4b45594c4f4746494c45222c2252455155455354535f43415f42554e444c45222c224355524c5f43415f42554e444c45227d20666f72206b20696e2065293b206f3d28662e69736f6c617465643d3d3120616e6420662e69676e6f72655f656e7669726f6e6d656e743d3d3120616e6420662e6e6f5f757365725f736974653d3d3120616e6420662e6e6f5f736974653d3d3120616e6420662e736166655f7061746820616e64207379732e646f6e745f77726974655f62797465636f646520616e64207379732e707963616368655f7072656669783d3d222f6465762f6e756c6c2f61746f6d2d7631622d6e6f2d7079632220616e64206f732e656e7669726f6e2e6765742822505954484f4e5f56455253494f4e22293d3d22332e31342e332220616e64206e6f74206220616e64206e6f74206f732e706174682e6c657869737473287a2920616e64206e6f74207b2273697465222c2273697465637573746f6d697a65222c2275736572637573746f6d697a65227d2e696e74657273656374696f6e287379732e6d6f64756c65732920616e64206e6f7420616e79286e3d3d227175616e7422206f72206e2e7374617274737769746828227175616e742e222920666f72206e20696e207379732e6d6f64756c65732920616e64206f732e706174682e697361627328722920616e64206f732e706174682e7265616c706174682872293d3d7220616e64206c656e2869293d3d6c656e287365742869292920616e6420616c6c286973696e7374616e636528762c7374722920616e64207620616e64206f732e706174682e697361627328762920616e64206f732e706174682e7265616c706174682876293d3d7620666f72207620696e206929293b206f206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b20696d706f727420696d706f72746c69622e6d616368696e6572792c696d706f72746c69622e7574696c2c73687574696c2c737461742c737973636f6e6669673b20703d737973636f6e6669672e6765745f706174687328736368656d653d737973636f6e6669672e6765745f7072656665727265645f736368656d6528227072656669782229293b20613d7475706c6528646963742e66726f6d6b6579732828722c6f732e706174682e7265616c7061746828705b22707572656c6962225d292c6f732e706174682e7265616c7061746828705b22706c61746c6962225d292929293b20643d6f732e706174682e6a6f696e28722c227175616e7422293b20763d6f732e706174682e6a6f696e28642c22766f6c6174696c6974795f73636f7265636172642e707922293b20783d6f732e706174682e7265616c70617468287379732e65786563757461626c65293b20773d73687574696c2e77686963682822707974686f6e22293b206f3d28616c6c286f732e706174682e697361627328742920616e64206f732e706174682e7265616c706174682874293d3d7420616e64206f732e706174682e697364697228742920666f72207420696e20612920616e64206e6f74207365742861292e696e74657273656374696f6e28692920616e64206f732e706174682e7265616c706174682864293d3d6420616e6420737461742e535f4953444952286f732e7374617428642c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e64206f732e706174682e7265616c706174682876293d3d7620616e6420737461742e535f4953524547286f732e7374617428762c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e642077206973206e6f74204e6f6e6520616e64206f732e706174682e697361627328772920616e64206f732e706174682e7265616c706174682877293d3d783d3d6f732e706174682e7265616c7061746828222f70726f632f73656c662f657865222920616e6420737461742e535f4953524547286f732e7374617428782c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e64206f732e61636365737328782c6f732e585f4f4b2920616e6420737461742e535f4953434852286f732e7374617428222f6465762f6e756c6c222c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f646529293b206f206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b207379732e706174682e657874656e642861293b207475706c65287379732e70617468293d3d692b61206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b20733d696d706f72746c69622e6d616368696e6572792e4d6f64756c655370656328227175616e74222c6c6f616465723d4e6f6e652c69735f7061636b6167653d54727565293b20732e7375626d6f64756c655f7365617263685f6c6f636174696f6e733d5b645d3b207379732e6d6f64756c65735b227175616e74225d3d696d706f72746c69622e7574696c2e6d6f64756c655f66726f6d5f737065632873293b20696d706f72742072756e70793b2072756e70792e72756e5f6d6f64756c6528227175616e742e766f6c6174696c6974795f73636f726563617264222c72756e5f6e616d653d225f5f6d61696e5f5f222c616c7465725f7379733d5472756529").decode("ascii"); os.execv(sys.executable,[sys.executable,"-I","-S","-B","-X","pycache_prefix=/dev/null/atom-v1b-no-pyc","-c",Q,"--manifest-id","<manifest_id>","--recovery-seal-file",P])'
```

The embedded lowercase hexadecimal literal is fixed document text, not a fourth substitution. It is exactly the ASCII encoding of the complete normal-command `-c` body immediately above, including its `runpy.run_module(...)` tail and excluding the surrounding shell quotes and any newline:

```text
len(Q.encode("ascii"))       = 2422
len(Q.encode("ascii").hex()) = 4844
sha256(Q.encode("ascii"))    = 65b72b6c26e518e41611efee7ddf09e0feb0186532202bd52898c9f45c21dd83
```

Implementation and command-construction tests must decode the embedded literal and require exact byte equality to that normal-command body, as well as the stated length and digest. A mismatch is a documentation/implementation mismatch and blocks activation. It may not be repaired by selecting a different bootstrap or direct source-file runner.

Only three substitutions are allowed: `manifest_id` is one exact registry value; `seal_record_sha256` is the original record’s 64-lowercase-hex digest; and `seal_bytes_hex` is the lowercase hexadecimal encoding of the entire original canonical seal file, including its final newline. The embedded child bootstrap is immutable and is never caller-, environment- or operator-supplied. The Owner-controlled launcher verifies those three domains and the retained seal before submitting the command. Neither a credential nor any partial/result statistic may enter the command. The prelude creates a private directory and exclusive non-symlink file, refuses an existing directory/file, writes only those retained bytes, and replaces itself with the original scorecard invocation. It adds no scorecard option, environment variable, source file, network retrieval or dependency. It does not reconstruct seal fields or rehash a replacement identity.

The outer recovery process executes the same complete two-phase startup prefix as the normal command through construction of the exact synthetic `quant` namespace. It imports no repository or third-party module and reads neither runtime secret before that prefix succeeds. It then stages the retained seal and replaces itself with a fresh isolated interpreter whose `-c` argument is the decoded exact normal-command body. That child therefore repeats the complete flag, environment, system-preload, path, `sysconfig`, interpreter, source and synthetic-parent checks before `runpy` loads any application module or either runtime secret can be read. Direct execution of `quant/volatility_scorecard.py` is forbidden.

The outer source contains no U+0027 single quote; the three angle-bracket substitutions remain inside double-quoted Python strings and cannot become shell redirections. The child receives `sys.argv = ["-c", "--manifest-id", manifest_id, "--recovery-seal-file", retained_seal_path]` before `runpy.run_module(..., run_name="__main__", alter_sys=True)`, preserving the normal module-execution semantics. Before creating the outer process, the control plane proves §2.4 startup-injection-key absence, exact command/configuration and continued selection of the accepted `B`; the retained provider-bound secret-free-probe baseline supplies the system-preload/launcher proof without an impossible new recovery probe or claimed control-plane `/etc` read. Both outer and child still recheck the live system-preload/launcher facts before application secret access. The scorecard independently performs every original §10.2 file/schema/hash/manifest check before repository or database access. A prelude/startup failure or platform command-size limit authorizes no truncation, alternative payload source, automatic retry or new-seal fallback. Resolve the same retained-seal recovery under the existing failure/incident rules. No new durable store is created. Section 5.3 measures the fully substituted command and counts the embedded 4,844-byte bootstrap hex as fixed overhead; no earlier recovery-template measurement remains valid.

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

The §5.2 template corrected at this head is longer than every earlier recovery template. Any earlier command-byte measurement is superseded. `command_bytes`, `overhead_bytes` and the retained vendor-capacity comparison must be recomputed from the complete corrected outer `-I -S -B` command, its child `execv` arguments, the direct path-bootstrap source and every escaped source byte; no earlier wrapper constant or measurement may be reused.

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

Keep the base service suspended except for Render-required build/configuration preparation performed while both runtime secrets are absent. Whenever the base service is resumed for that secret-free preparation, its start command remains exactly `python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"`; it is never replaced by E-1, a V-1B scorecard, recovery staging, sleep loop or another workload. Once either runtime secret is installed, the base service may not be resumed. A later build/probe first removes both secrets and repeats the complete §2.5 secret-free sequence. The inert command performs no database or repository-authority access and no V-1B invocation. After preparation, verify suspension before creating a one-off job. If the exact build/configuration cannot be obtained while preserving this invariant, stop; do not resume a continuous scorecard worker.

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

Mandatory post-rotation finalization. After the one actual successful password change, append the actual confirmation source and its measured UTC timestamp. Set `rotation_status = "COMPLETED"` and `rotation_completion_timestamp` to that actual confirmed-completion timestamp, not a placeholder, anticipated value, earliest exposure time or document date. The exact timestamp source is the secure control plane’s successful password-change completion event; when the exact psql route in §6.3 is used, it is the server-clock observation returned immediately after acknowledged COMMIT. That latter timestamp is explicitly an observed completion upper bound, not a claim to know an unavailable internal commit instant. Preserve that distinction in the private timeline.

Password replacement prevents later authentication with the old password but does not terminate an already authenticated PostgreSQL session; an ordinary role may also replace its own password or persist per-role/per-database session defaults from such a surviving session. This amendment therefore selects an exact temporary `NOLOGIN` fence plus complete backend termination, not an administrative notation or discretionary containment alternative. Section 6.3 first sets the existing reader role `NOLOGIN`, drains two consecutive possible PostgreSQL 17 `authentication_timeout` maxima plus one second under the exact pre-timer settings, runs two administrator-authorized termination passes selecting every client backend by the immutable reader OID, and proves repeated reader/unattributed/prepared-transaction zeros plus absence of global or database-specific reader settings before the one password replacement. It keeps `NOLOGIN` active and the URI absent through the post-rotation drain and accepted pooler-containment observation, provisions the URI while still fenced, and restores `LOGIN` only afterward. Before the new URI is installed or `record_status = "FINALIZED"`, it must prove that every PostgreSQL process authenticated as `atom_e1_scorecard_reader` before the fence—and every reader or not-yet-attributed client process appearing during the bounded authentication drains—has ended or cannot carry the old credential past the atomic final guard. `backend_start` is retained as process-incarnation evidence but is not treated as authentication-completion time and never excludes a row from termination. An active, idle, idle-in-transaction, waiting or different-database backend is not implicitly contained. If complete termination or clean pre-auth/prepared/role-setting state cannot be proved, the role remains `NOLOGIN`, all benchmark/V-1B jobs remain terminal, the parent remains suspended/inert, the reader URI remains absent, the incident remains OPEN and evidence-capable activation is prohibited. No `ALTER ROLE ... RESET`, prepared-transaction action, catalog edit, new role grant or guessed baseline is authorized. That contained stopped state does not permit incident finalization.

The direct-only/no-pooler rule constrains the legitimate scorecard, not an attacker. Supabase Shared Pooler session/transaction endpoints, and any enabled Dedicated Pooler or legacy PgBouncer endpoint, are therefore part of the incident boundary. A pooler frontend socket is not a PostgreSQL backend and may be absent from `pg_stat_activity` while idle; the document does not relabel it as terminated. It is accepted as explicitly contained only after all of the following are independently established while `NOLOGIN` remains active: every server-side backend/lease for the reader is included in the exact PostgreSQL zero proofs; the one password replacement is confirmed; no pre-rotation reader backend or prepared transaction survives; and current authoritative Supabase documentation or Owner-control-plane/support evidence establishes that a frontend or cached old verifier cannot create a database session using the invalidated password after `LOGIN` is restored. The private incident packet must inventory every available Shared/Dedicated/legacy pooler plane, retain role/project-scoped frontend/cache/server-lease observations and their coverage limits, and state which frontends were terminated versus contained. If any frontend retains a usable server lease, the vendor semantics/evidence are unavailable, or stale cached authentication could regain database access after restoration, keep `NOLOGIN`, remove/keep absent the URI and require a documentation-first, vendor-supported drain/purge decision. This amendment does not invent or authorize an undocumented pooler administration endpoint, connect the scorecard through a pooler, or infer safety from `pg_stat_activity` alone.

Record the conforming Render URI update confirmation separately; it is not the password-change or backend-termination time. The finalized incident version retains the preflight and pre-fence inventory; the immutable reader OID; exact `NOLOGIN`/`LOGIN` transaction acknowledgements and server-clock bounds; the verified PostgreSQL 17 authentication/pre-timer settings and `preauth_activity_fully_visible` proof; both reader-OID-selected termination-transaction outputs; every false/exception; every prepared-transaction and global/database role-setting observation; all pre-rotation reader/unattributed zero observations; the post-rotation 601-second drain and all reader/unattributed guard observations before provisioning and atomically before `LOGIN`; the post-`LOGIN` and pre-finalization reader-only zero observations and server-clock times; the pooler-plane inventory/termination-or-containment evidence; the retained successful `\password`/`ALTER ROLE` status; and proof that the parent stayed suspended/inert with the URI absent through rotation, the post-rotation drain and accepted pooler-containment observation. Thereafter it records the one authorized fenced URI-provisioning event while `NOLOGIN` remained true, the parent remained suspended/inert and no job existed. No password, URI, verifier, query body containing a secret or unrestricted activity text is retained.

Complete the artifact dispositions and the bounded investigation below, recording retained-artifact access controls/retention reasons and any telemetry gaps. Append the final record version with `record_status = "FINALIZED"`, actual independent reviewer/Owner disposition and non-secret evidence references. PENDING initial records remain retained. The direct-PostgreSQL old-password new-backend exposure ends when the `NOLOGIN` commit is confirmed; already-started authentication and existing PostgreSQL sessions remain in the surviving-session window until the full drain/termination/zero proof completes. Pooler-frontend authentication is a separate interval and does not inherit that cutoff; close it only at the confirmed rotation plus accepted pooler containment observation above. The final password replacement after zero invalidates any password an earlier surviving reader session may have selected. The role remains `NOLOGIN` through secure URI provisioning and is restored to its frozen `LOGIN` state only by the later, separately acknowledged §6.3 transaction. Record the fence, drain, rotation, pooler-containment and restoration bounds separately; none erases already disclosed data.

Evidence-capable activation requires the real finalized version, COMPLETED/non-null actual rotation timestamp, exact §6.3 pre- and post-rotation authentication drains/termination with all required backend/prepared-transaction zero observations, explicit pooler termination-or-containment proof, the updated conforming URI, and independent acceptance of the documented incident disposition. §2.6 exposes only the opaque incident ID/finalization digest/completion timestamp and approval, never private incident contents. Missing finalization, uncertain invalidation, incomplete termination/visibility/pooler containment or an unresolved wider-privilege/active-abuse finding blocks activation. Limited historical telemetry may be recorded and explicitly dispositioned by the Owner; it cannot support an assertion that no abuse occurred.

Privilege finding preserved precisely. The frozen/catalog-verified steady state remains LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS, with no reader memberships, no database/non-system-schema CREATE and no durable-table INSERT/UPDATE/DELETE/TRUNCATE path under the V-1A checks. The only role-attribute exception is §6.3's temporary `NOLOGIN` fence and exact restoration of `LOGIN`; no other attribute may change. Preserve the established no-durable-table-mutation/no-BYPASSRLS finding for the verified state; do not expand a point-in-time check into an unverified claim about every instant of the exposure window.

The role does have effective database TEMPORARY through PUBLIC. That is explicitly allowed by V-1A §§13.3 and 15.3 and is unaffected by NOINHERIT or absence of role memberships. Thus the exposure is not limited to confidentiality: an unauthorized session might create/use temporary objects and consume temporary storage, sort/spill space, connections, locks, CPU, memory or other availability resources. Existing SELECT and permitted proof-function access can also consume resources. A malicious client is not constrained merely because the legitimate scorecard chooses a read-only transaction. The legitimate scorecard still must prove `pg_my_temp_schema() = 0`, no temporary objects, all existing privilege/SECURITY DEFINER checks and a single read-only REPEATABLE READ snapshot. Except for §6.3's exact temporary `NOLOGIN` fence and exact `LOGIN` restoration, do not revoke PUBLIC TEMPORARY, change any other role attribute or add any other restriction under this incident-documentation grant.

The incident reviewer must examine available authentication/session records, temporary-object/storage metadata, connection occupancy, resource/availability telemetry and any anomalous permitted-function use for the bounded exposure and surviving-session window. Include temporary-relation creation/use, temp-file growth, disk/storage pressure, long-lived/idle transactions, lock/wait effects and connection exhaustion; investigate any separately reachable storage interface rather than infer its absence from table ACLs. Separate role-attributed observations from database-wide counters. No log gap or absent current temporary object proves absence of past abuse. Preserve the distinction between temporary/resource abuse and a previously absent durable-table write/BYPASSRLS privilege.

Only read-only incident investigation through the Owner’s existing PostgreSQL/Supabase administrative audit channels is authorized apart from §6.3's exact `NOLOGIN`/password/`LOGIN` and target-backend termination operations. It may inspect role/ACL, direct/backend, pooler frontend/cache/server-lease and temporary-object/resource metadata; it may not run an abuse demonstration, connect using the old credential, create a temp table, fill storage, acquire test locks, change another privilege/attribute, delete evidence or score a research population. No pooler drain/purge or configuration mutation is authorized by an observation. An identified write/BYPASSRLS/membership expansion, usable stale pooler authentication, unexplained active session or wider compromise is a separate material incident; use existing protective-stop authority and a separate explicit remediation decision, not an improvised repair in this PR.

### 6.2 Rotation

After the required merges and before any V-1B connection, authorize exactly one password rotation for:

```text
project         = afyiydxbjgzaiswnbcyj
database        = postgres
role            = atom_e1_scorecard_reader
Render variable = ATOM_E1_SCORECARD_READONLY_DATABASE_URL
Render service  = srv-daa7thgae00c73a2lmn0
```

The Owner uses an existing privileged, project-verified administrative channel outside the scorecard runtime. Verify the exact project/direct target before transmission. Change only that existing role’s password plus its temporary §6.3 `LOGIN -> NOLOGIN -> LOGIN` state; create no role, membership, grant, policy, default privilege, database object, evidence mutation or password-containing repository migration. The scorecard itself receives no administrative capability.

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

Complete §6.3's `NOLOGIN` fence, pre-rotation authentication drain, exact reader-OID-selected termination and repeated reader/unattributed/prepared-transaction zero verification before the one password rotation. Keep `NOLOGIN` and the URI absent through the exact post-rotation stale-verifier drain, conservative unattributed-client guard and pooler containment proof, then provision the conforming URI, repeat the full pre-`LOGIN` guard, restore `LOGIN` atomically with its final guard, prove the specified post-`LOGIN` reader-only backend/prepared/settings zeros, and complete mandatory §6.1 finalization with the actual fence/termination/rotation/containment/restoration evidence before activation. Later connection/authority acceptance uses only the new credential and the frozen direct-host TLS/reader checks before evidence access. This amendment phase itself performs none of those connections or checks.

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

Any mismatch stops before containment or password mutation. At this point every benchmark/V-1B job must be terminal, the parent must be suspended with the isolated inert command, and `ATOM_E1_SCORECARD_READONLY_DATABASE_URL` must be absent from every effective Render source. The new password remains only in the Owner's private generator/prompt path until the fenced termination checks below pass.

Before sending the preflight query, establish the exclusive role-administration window defined below; it begins before this preflight and remains uninterrupted through final verification. Then run this exact capability/version/limit preflight:

```sql
WITH reader AS (
  SELECT oid, rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole,
         rolreplication, rolbypassrls, rolconfig
  FROM pg_catalog.pg_roles
  WHERE rolname = 'atom_e1_scorecard_reader'
),
caller AS (
  SELECT oid, rolsuper, rolcreaterole
  FROM pg_catalog.pg_roles
  WHERE rolname = current_user
),
auth_limit AS (
  SELECT setting, unit, min_val, max_val, context
  FROM pg_catalog.pg_settings
  WHERE name = 'authentication_timeout'
)
SELECT reader.oid AS reader_role_oid,
       reader.rolcanlogin AS reader_can_login,
       reader.rolinherit AS reader_inherits,
       reader.rolsuper AS reader_is_superuser,
       reader.rolcreatedb AS reader_can_createdb,
       reader.rolcreaterole AS reader_can_createrole,
       reader.rolreplication AS reader_can_replicate,
       reader.rolbypassrls AS reader_bypasses_rls,
       reader.rolconfig AS reader_global_settings,
       (
         caller.rolsuper
         OR (
           caller.rolcreaterole
           AND pg_catalog.pg_has_role(
                 current_user, reader.oid, 'MEMBER WITH ADMIN OPTION'
               )
         )
       ) AS role_attribute_change_authorized,
       (
         caller.rolsuper
         OR pg_catalog.pg_has_role(current_user, 'pg_signal_backend', 'USAGE')
       ) AS termination_authorized,
       (
         caller.rolsuper
         OR pg_catalog.pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')
         OR pg_catalog.pg_has_role(current_user, reader.oid, 'USAGE')
       ) AS activity_fully_visible,
       (
         caller.rolsuper
         OR pg_catalog.pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')
       ) AS preauth_activity_fully_visible,
       current_setting('server_version_num')::integer AS server_version_num,
       current_setting('pre_auth_delay') AS pre_auth_delay,
       current_setting('log_hostname') AS log_hostname,
       auth_limit.setting AS authentication_timeout,
       auth_limit.unit AS authentication_timeout_unit,
       auth_limit.min_val AS authentication_timeout_min,
       auth_limit.max_val AS authentication_timeout_max,
       auth_limit.context AS authentication_timeout_context
FROM reader
CROSS JOIN caller
CROSS JOIN auth_limit;
```

Require exactly one row and retain its `reader_role_oid` as immutable for the complete fence/rotation/restoration sequence; every later role observation and role cast must resolve to that same OID. Immediately capture that observed value into the psql variable used below, and retain the displayed source row separately:

```text
SELECT oid::text AS reader_role_oid
FROM pg_catalog.pg_roles
WHERE rolname = 'atom_e1_scorecard_reader'
\gset atom_v1b_
```

The value stored by `\gset` must equal the displayed preflight `reader_role_oid`; any mismatch or failed/non-single-row `\gset` stops before mutation. No caller may set, unset, recapture or replace `atom_v1b_reader_role_oid` except for the exact reconnect rehydration below. The exclusive role-administration window already opened before the preflight remains in force through final incident verification: no other session, automation or operator may create, drop, rename, alter, grant to/from or change settings for this role. If that exclusion cannot be established or a concurrent/unknown role action appears, stop without further mutation and require documentation-first disposition.

If an expressly authorized reconnect below creates a fresh psql client, it does not establish a new baseline. In that fresh client, query only a candidate variable:

```text
SELECT r.oid::text AS candidate_reader_role_oid
FROM pg_catalog.pg_roles AS r
WHERE r.rolname = 'atom_e1_scorecard_reader'
\gset atom_v1b_reconnect_
```

Display that candidate and require exact equality to the originally retained immutable OID under the still-active exclusive role-administration window. Only after that comparison may the Owner execute exactly `\set atom_v1b_reader_role_oid :atom_v1b_reconnect_candidate_reader_role_oid` followed immediately by `\unset atom_v1b_reconnect_candidate_reader_role_oid`, then rerun the identity guard below. A missing/multiple row, unavailable original record or mismatch stops; no mutation or replacement baseline follows. This is the sole OID-variable rehydration exception. A disconnect after the password COMMIT but before acknowledged `LOGIN` restoration remains a blocking incident unless the later explicit lost-ack read-only route is used; no post-rotation sleep or mutation is silently resumed in a new client.

Before every name-based `ALTER ROLE` or `\password` below, before each reader-OID-selected termination statement, and at every repeated role/backend/prepared/settings checkpoint, run this exact identity guard in the same psql session and require the sole result `reader_identity_exact = true` before sending the next statement:

```sql
SELECT count(*) = 1
       AND COALESCE(
             bool_and(
               r.oid = :'atom_v1b_reader_role_oid'::oid
               AND r.rolname = 'atom_e1_scorecard_reader'
             ),
             false
           ) AS reader_identity_exact
FROM pg_catalog.pg_roles AS r
WHERE r.oid = :'atom_v1b_reader_role_oid'::oid
   OR r.rolname = 'atom_e1_scorecard_reader';
```

The `OR` intentionally detects rename-plus-recreate as two/nonmatching rows. A false, NULL, missing-variable, parse or query result stops before the guarded statement; do not recapture an OID or retarget the action. Because PostgreSQL's role-mutation syntax is name-based, this immediate guard plus the exclusive role-administration window—not the spelling alone—is the frozen name-to-OID binding.

Require the exact frozen reader booleans `true, false, false, false, false, false, false` in the order `rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls`; `reader_global_settings IS NULL`; all four authorization/visibility predicates true, including the stricter `preauth_activity_fully_visible`; `170000 <= server_version_num < 180000`; `pre_auth_delay = '0'`; `log_hostname = 'off'`; and `authentication_timeout_unit = 's'`, `authentication_timeout_min = '1'`, `authentication_timeout_max = '600'`, `authentication_timeout_context = 'sighup'`. The two termination statements use only the already held administrator or `pg_signal_backend` capability proved here; this amendment authorizes no role membership, `SET ROLE` privilege or grant. Reader-role visibility alone cannot reveal unattributed pre-authentication rows. This amendment authorizes no `GRANT pg_read_all_stats`; a false stricter predicate blocks before `NOLOGIN`. Also run the exact query below and require zero rows. Migration 030 created no role-level setting and no later controlling law authorizes one; a row/value is a material incident, not authority to reset or adopt it.

```sql
SELECT s.setdatabase, s.setrole, s.setconfig
FROM pg_catalog.pg_db_role_setting AS s
WHERE s.setrole = :'atom_v1b_reader_role_oid'::oid
ORDER BY s.setdatabase, s.setrole;
```

Run this exact cluster-wide prepared-transaction count before the fence and retain it separately from backend counts:

```sql
SELECT count(*) AS reader_prepared_transactions
FROM pg_catalog.pg_prepared_xacts AS p
WHERE p.owner = (
  SELECT r.rolname
  FROM pg_catalog.pg_roles AS r
  WHERE r.oid = :'atom_v1b_reader_role_oid'::oid
    AND r.rolname = 'atom_e1_scorecard_reader'
);
```

It must equal zero. A prepared transaction has no live backend to terminate and can retain locks after its originating backend ends; it is therefore neither a terminated backend nor acceptable containment. A nonzero pre-fence result permits only the exact `NOLOGIN` and two backend-termination passes below as protective containment, then requires the role to remain `NOLOGIN`, the URI to remain absent and a separate documentation-first disposition; it forbids password rotation, `LOGIN` restoration and incident finalization. No `COMMIT PREPARED`, `ROLLBACK PREPARED`, GID selection or prepared-transaction mutation is authorized here. Repeat this identical count after the second termination pass, with each later repeated zero-backend checkpoint, immediately after the password transaction, after Render URI provisioning while fenced, with each post-`LOGIN` checkpoint and at final verification; every result must be zero.

The current authentication setting is recorded but never used to shorten the drain. A failure authorizes no grant, membership, setting reset, alternative administrator or broader mutation predicate. Privately retain the preflight, the zero-row role-setting result and this complete pre-fence inventory across all databases/states:

```sql
SELECT pg_catalog.clock_timestamp() AS inventory_observed_at,
       a.pid, a.backend_start, a.datname, a.application_name,
       a.client_addr, a.client_port, a.state, a.wait_event_type, a.wait_event
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
ORDER BY a.backend_start, a.pid;
```

Select the termination-only route under a temporary login fence; no surviving backend is accepted as “contained.” In the same private session execute exactly:

```text
\set AUTOCOMMIT on
BEGIN;
ALTER ROLE atom_e1_scorecard_reader NOLOGIN;
COMMIT;
SELECT pg_catalog.clock_timestamp() AS nologin_completion_upper_bound
\gset atom_v1b_
SELECT to_char(
         :'atom_v1b_nologin_completion_upper_bound'::timestamptz
           AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS nologin_completion_upper_bound_utc;
```

Require the exact identity guard immediately before `ALTER ROLE`, again after its COMMIT, and a fresh `pg_roles` observation for `oid = :'atom_v1b_reader_role_oid'::oid` with exactly one row, exact name and `rolcanlogin = false`. Immediately rerun the guard before this first fresh termination transaction:

```sql
BEGIN;
WITH targets AS MATERIALIZED (
  SELECT a.pid, a.backend_start, a.datname, a.application_name,
         a.client_addr, a.client_port, a.state
  FROM pg_catalog.pg_stat_activity AS a
  WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
    AND a.backend_type = 'client backend'
    AND a.pid <> pg_catalog.pg_backend_pid()
)
SELECT t.pid, t.backend_start, t.datname, t.application_name,
       t.client_addr, t.client_port, t.state,
       pg_catalog.pg_terminate_backend(t.pid, 10000::bigint) AS terminated
FROM targets AS t
ORDER BY t.backend_start, t.pid;
COMMIT;
```

The preflight must prove that the existing administrative session is a superuser or already has `pg_signal_backend`; no new membership or grant is authorized. Each exact statement materializes only current `client backend` rows whose `usesysid` equals the immutable reader OID and supplies only those PIDs to `pg_terminate_backend`. PostgreSQL 17's stock `pg_terminate_backend(pid, timeout)` nevertheless has no `(pid, backend_start)` identity overload: after selection and before the operating-system signal, the selected process can exit and the numeric PID can be recycled. With the existing administrator/`pg_signal_backend` authority, that residual interval could signal a different non-superuser backend. This amendment accepts that narrowly bounded residual only for these two exact, fresh, OID-selected termination passes because PostgreSQL supplies no stock identity-bound signaling primitive; it does not claim cross-role signaling is impossible. Any observed or suspected collateral termination is a material operational incident and stops V-1B. The transaction must return every selected `(pid, backend_start)` and complete with acknowledged `COMMIT`; a signal permission error, statement error or uncertain transaction outcome fails the pass. The transaction grants no durable membership, setting or new capability.

The active `NOLOGIN` fence blocks a new completed login but does not prove every authentication exchange already underway has ended. PostgreSQL 17 can apply `AuthenticationTimeout` once while collecting the startup/SSL packet and then reset and apply it again during `InitPostgres` authentication; `PerformAuthentication()` precedes the `rolcanlogin` enforcement. PostgreSQL can also delay before starting those timers or perform reverse DNS outside them, so the preflight's exact `pre_auth_delay = '0'` and `log_hostname = 'off'` are mandatory and must remain unchanged throughout the fence. With those two pre-timer paths disabled, a hostile old-password connection can occupy nearly twice the 600-second maximum before the fence rejects it. After the first termination pass, wait exactly twice the verified maximum plus one second—1201 seconds—which is conservatively more than 1201 seconds after the already-confirmed `NOLOGIN` commit. Never substitute the observed current setting, a single 601-second interval or wall-clock subtraction:

```sql
SELECT pg_catalog.pg_sleep(1201.0::double precision);
```

An interrupted sleep proves no drain; after reconnecting with the exact administrative command and revalidating identity, `NOLOGIN`, PostgreSQL 17, the 600-second maximum, `pre_auth_delay = '0'` and `log_hostname = 'off'`, start a fresh complete 1201-second sleep. No SIGHUP, database configuration change or Owner/control-plane setting mutation is permitted during the fence. After an uninterrupted sleep, revalidate those facts and execute the exact complete `BEGIN`/OID-selected termination/`COMMIT` transaction above a second time against a fresh scan. These are two mandated passes, not an output-based retry loop. Reconcile every pre-fence inventory `(pid, backend_start)` with a true termination result or a fresh proof that that exact incarnation ended naturally; retain every false result/exception. No row is excluded by database, state, age or application.

In fresh autocommit statements, run this exact count, wait exactly one second, and run the identical count again:

```sql
SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS reader_client_backends,
       count(*) FILTER (
         WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS all_reader_processes,
       count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid IS NULL
       ) AS unattributed_client_backends
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
   OR (a.backend_type = 'client backend' AND a.usesysid IS NULL);

SELECT pg_catalog.pg_sleep(1.0::double precision);

SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS reader_client_backends,
       count(*) FILTER (
         WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS all_reader_processes,
       count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid IS NULL
       ) AS unattributed_client_backends
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
   OR (a.backend_type = 'client backend' AND a.usesysid IS NULL);
```

All three columns in both observations and every accompanying prepared-transaction count must equal zero, and `rolcanlogin` must remain false. These pre-rotation NULL guards close the untimed post-authentication/pre-`rolcanlogin` interval for every process that could have cached the old `LOGIN` state before the fence; the already proved `preauth_activity_fully_visible` is mandatory. Rerun the exact global `rolconfig` and `pg_db_role_setting` checks and again require NULL/zero rows. Only then perform the one password replacement while the role remains fenced:

```text
SELECT pg_catalog.clock_timestamp() AS rotation_lower_bound
\gset atom_v1b_
SELECT to_char(
         :'atom_v1b_rotation_lower_bound'::timestamptz
           AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS rotation_lower_bound_utc;
BEGIN;
SET LOCAL password_encryption = 'scram-sha-256';
\password atom_e1_scorecard_reader
COMMIT;
SELECT pg_catalog.clock_timestamp() AS rotation_completion_upper_bound
\gset atom_v1b_
SELECT to_char(
         :'atom_v1b_rotation_lower_bound'::timestamptz
           AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS rotation_lower_bound_utc,
       to_char(
         :'atom_v1b_rotation_completion_upper_bound'::timestamptz
           AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS rotation_completion_upper_bound_utc;
```

The `\password` inputs are the same fresh high-entropy password twice in its private prompts; never the exposed password. PostgreSQL documents that `\password` encrypts the value before submitting `ALTER ROLE` and avoids cleartext in command history/server logs. That is not a promise that every external session recorder or audit configuration suppresses sensitive verifiers; the preceding secure-channel requirement remains mandatory. No returned/printed password or verifier is acceptance evidence.

`COMMIT` may be entered only after `\password` itself completes without cancellation, EOF, prompt mismatch, client/meta-command error or server error and psql reports the successful non-secret server command tag exactly `ALTER ROLE`. Retain a redacted private action record proving that exact `\password` completion and command tag without prompt input, verifier, generated SQL or secret-bearing terminal bytes. If that success is not observed, do not issue `COMMIT`: if the session remains usable issue `ROLLBACK;` and `\q`; if psql has exited, prove the administrative connection ended so PostgreSQL discarded its open transaction. Leave the incident PENDING and do not repeat `\password` under this grant. Only the conjunction of (1) that retained successful `\password`/`ALTER ROLE` status, (2) acknowledged `COMMIT`, and (3) the subsequent server-clock upper bound establishes the one rotation; a successful no-op `COMMIT` cannot substitute for item 1. Preserve both time bounds. Require `rolcanlogin = false`, a fresh all-reader-process count of zero and the prepared-transaction count of zero again.

Starting only after that acknowledged rotation-completion upper bound, keep `NOLOGIN` unchanged, the reader URI absent and the parent suspended/inert, and execute this exact uninterrupted post-rotation stale-verifier drain:

```sql
SELECT pg_catalog.pg_sleep(601.0::double precision);
```

This 601 seconds is not a bound on a fresh socket's startup/DNS path. It exhausts the single at-most-600-second `AuthenticationTimeout` around `ClientAuthentication()` for an exchange that had acquired the old verifier before rotation. It does not bound PostgreSQL's later, untimed interval between successful authentication and `InitializeSessionUserId()`'s `rolcanlogin` check; during that interval `pg_stat_activity.usesysid` remains NULL. A connection reaching verifier acquisition only after rotation sees the new verifier, while `NOLOGIN` still prevents a completed login. An interrupted sleep proves no drain.

After the uninterrupted sleep, revalidate the same immutable role OID, `rolcanlogin = false`, PostgreSQL 17, the 600-second maximum and unchanged `pre_auth_delay = '0'`/`log_hostname = 'off'`. Then, in fresh autocommit statements, execute this exact post-rotation guard, wait exactly one second and execute the entire guard again:

```sql
SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS reader_client_backends,
       count(*) FILTER (
         WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS all_reader_processes,
       count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid IS NULL
       ) AS unattributed_client_backends
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
   OR (a.backend_type = 'client backend' AND a.usesysid IS NULL);

SELECT pg_catalog.pg_sleep(1.0::double precision);

SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS reader_client_backends,
       count(*) FILTER (
         WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS all_reader_processes,
       count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid IS NULL
       ) AS unattributed_client_backends
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
   OR (a.backend_type = 'client backend' AND a.usesysid IS NULL);
```

All three columns in both observations must equal zero. The NULL count is intentionally cluster-wide and conservative: it contains every visible client process not yet attributed to a role, including any old-verifier exchange paused in the untimed post-authentication/pre-`rolcanlogin` interval. It is never used as authority to signal an unattributed or other-role process. The all-reader count preserves the wider process invariant in the same observation. Repeat the prepared-transaction count at both checkpoints and the global/database role-setting checks. No third termination pass is authorized. Any row, changed OID/setting/version, incomplete visibility or failed observation keeps the URI absent, role fenced and incident OPEN for separate remediation; it never permits `LOGIN` or finalization.

Before provisioning the URI or restoring `LOGIN`, the Owner and independent incident reviewer use only the existing authenticated Supabase project audit/support control plane to retain one non-secret `ATOM-V1B-READER-POOLER-CONTAINMENT-1` observation with exactly: project ref `afyiydxbjgzaiswnbcyj`; database role `atom_e1_scorecard_reader`; observation time; inventory of Shared Supavisor session and transaction modes plus any enabled Dedicated Pooler or legacy PgBouncer plane; the vendor/control-plane evidence reference and digest; observed or explicitly unavailable frontend/cache/server-lease coverage; confirmation that every server-side reader lease is represented by the repeated zero `pg_stat_activity` proof; and the vendor-grounded conclusion that no pre-rotation frontend or cached old verifier can obtain a PostgreSQL backend after the confirmed password replacement. This is a read-only observation/support confirmation, not a connection attempt or pooler mutation. It must classify each discovered frontend as vendor-confirmed terminated or explicitly contained by zero live server lease, active `NOLOGIN`, completed rotation and inability of the invalidated credential to create a later backend. An unknown plane, usable lease, unsupported conclusion or evidence limited to the legitimate direct URI blocks finalization and requires a separate documentation-first vendor drain/purge decision; never test the exposed password.

While `NOLOGIN` remains verified, install that same confirmed new credential in the exact Render URI using Save only, keep the parent suspended, create no job, and read back the permitted non-secret configuration plus secret provisioning state. Then recheck `rolcanlogin = false`; repeat the complete two-observation post-rotation guard above, including all three zero columns and the one-second interval; and require the prepared-transaction count zero, `rolconfig IS NULL` and zero `pg_db_role_setting` rows at both checkpoints. Only after that provisioning is accepted, rerun the exact OID guard, begin one transaction, call `pg_stat_clear_snapshot()` and run one further complete post-rotation guard query. Require all three counts zero before sending the name-based `ALTER ROLE`; if any is nonzero, issue `ROLLBACK` and take the failure route. Only the all-zero branch executes:

```text
BEGIN;
SELECT pg_catalog.pg_stat_clear_snapshot();
SELECT count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS reader_client_backends,
       count(*) FILTER (
         WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
       ) AS all_reader_processes,
       count(*) FILTER (
         WHERE a.backend_type = 'client backend'
           AND a.usesysid IS NULL
       ) AS unattributed_client_backends
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid
   OR (a.backend_type = 'client backend' AND a.usesysid IS NULL);
ALTER ROLE atom_e1_scorecard_reader LOGIN;
COMMIT;
SELECT pg_catalog.clock_timestamp() AS login_restore_completion_upper_bound
\gset atom_v1b_
SELECT to_char(
         :'atom_v1b_login_restore_completion_upper_bound'::timestamptz
           AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS login_restore_completion_upper_bound_utc;
```

An old-verifier process capable of reaching that untimed interval already has an initial backend-status slot before authentication and is therefore included by the immediate NULL-or-target guard. A process not yet represented there has not acquired the old verifier; any authentication it begins after this point uses the rotated verifier. The query/`ALTER ROLE` transaction is the final fence transition; no external connection or administrative action may intervene.

Require the complete original frozen role-attribute values with `rolcanlogin = true`, `rolconfig IS NULL` and zero `pg_db_role_setting` rows. Then run this exact reader-only two-observation query with its one-second interval, plus the exact prepared-transaction count at each checkpoint:

```sql
SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (WHERE a.backend_type = 'client backend')
         AS reader_client_backends,
       count(*) AS all_reader_processes
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid;

SELECT pg_catalog.pg_sleep(1.0::double precision);

SELECT pg_catalog.pg_stat_clear_snapshot();

SELECT count(*) FILTER (WHERE a.backend_type = 'client backend')
         AS reader_client_backends,
       count(*) AS all_reader_processes
FROM pg_catalog.pg_stat_activity AS a
WHERE a.usesysid = :'atom_v1b_reader_role_oid'::oid;
```

Both columns at both observations must be zero. The cluster-wide unattributed-client guard has already served its narrowly defined purpose inside the atomic pre-`LOGIN` fence transition; after `LOGIN`, a newly arriving unattributed client would authenticate only against the rotated verifier and is not evidence of a surviving old-password session. Any reader process, prepared transaction or role-setting row before an authorized scorecard job is nevertheless a material incident. Immediately before finalization clear the statistics snapshot and execute one further copy of the exact reader-only count, require both columns zero, repeat the prepared-transaction zero count and NULL/zero role-setting observations, and record:

```text
SELECT to_char(
         pg_catalog.clock_timestamp() AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
       ) AS reader_backend_termination_verified_at_utc;
\q
```

Each non-secret bound is emitted immediately after its server-clock observation: the `NOLOGIN` upper bound, both rotation bounds and the `LOGIN` upper bound. That immediate emission remains retainable even if the one expressly authorized pre-rotation reconnect loses psql variables. This final non-secret row must also be captured completely before `\q`. A missing earlier bound, cast/format failure, truncated row or lost output leaves the incident OPEN and is not reconstructed from client time.

`ALTER ROLE ... NOLOGIN`, the one `\password`, `ALTER ROLE ... LOGIN`, and the two administrator-authorized, reader-OID-selected termination passes are the only new database mutations. Each pass supplies to `pg_terminate_backend` only PIDs selected directly inside that fresh statement by the exact reader-role OID and `backend_type = 'client backend'`; it relies only on the preflight-proved existing administrator/`pg_signal_backend` capability and does not grant or assume `SET ROLE`. This selection boundary does not erase the explicitly accepted post-selection PID-reuse interval above. A stored/operator-supplied PID, another role selected by query predicate, broad idle-session cleanup, scheduled cleanup, `pg_cancel_backend`, prepared-transaction mutation, grant, membership or other attribute change is forbidden.

Any remaining backend or prepared-transaction row, incomplete visibility, wrong/changed version or maximum, false result without a reconciled ended incarnation, permission failure, SQL/client/meta-command error or missing observation leaves the incident OPEN and V-1B blocked. On a failure before URI provisioning, keep the URI absent. On a failure after fenced URI provisioning but before acknowledged `LOGIN` restoration, remove the URI and keep/verify `NOLOGIN`; this is the failure route, not a requirement to remove the URI during the uninterrupted successful provisioning-to-restoration sequence. In either case keep the parent suspended. An uncertain password COMMIT is resolved through the secure administrative channel while `NOLOGIN` remains in force and is never repeated; a known failed/cancelled `\password` follows the explicit rollback path above and also is not repeated. If the `LOGIN` COMMIT acknowledgement is lost, reconnect with the exact administrative command and read the complete target-role attributes before any further mutation or activation. A verified `rolcanlogin = false` is a safely fenced failure: remove the URI and remain blocked. A verified exact restored `LOGIN` state resolves the role outcome only if the two mandated post-restoration zero backend/prepared-transaction observations and the final zero backend/prepared-transaction observation pass; record the readback and its server-clock upper bound instead of inventing the lost commit time. An ambiguous role state, any reader backend/prepared transaction or any evidence that the new password escaped is a separate material incident requiring immediate protective stop and documentation-first remediation; this amendment authorizes no automatic reassertion, extra termination pass, prepared-transaction mutation or second password replacement. The role may not remain `NOLOGIN` for activation or be marked finalized merely because it is safely contained.

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

SELECT transaction, prepared, owner, database
FROM pg_catalog.pg_prepared_xacts
WHERE owner = 'atom_e1_scorecard_reader'
ORDER BY prepared, transaction;

SELECT datname, numbackends, temp_files, temp_bytes, deadlocks, stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = 'postgres';
COMMIT;
```

These outputs are private, point-in-time indicators, not proof of historical non-use or role attribution for database-wide counters. The existing audit interface supplies the historical connection/storage/resource evidence and its exact coverage gaps. Inspecting existing role/ACL snapshots uses the already frozen V-1A §15.3 catalog proof, without widening it or substituting that snapshot for historical evidence. Section 6.3's exact temporary `NOLOGIN`, one password replacement, exact `LOGIN` restoration and two reader-OID-selected `pg_terminate_backend` passes are the sole exceptions to this subsection's read-only rule. Any other administrative mutation, session termination, grant change, storage cleanup or logging-policy change requires its existing separate protective/Owner authority; no such action is hidden in these read-only queries. Missing telemetry is recorded, not “repaired” by reproducing an attack.

## 7. Direct-host IPv4 add-on; separate cost gate

Authorize the dedicated Supabase IPv4 add-on for project `afyiydxbjgzaiswnbcyj` only, conditional on a separate affirmative Owner confirmation immediately before the billable action.

At action time, the operator must show the exact project, whether the add-on is already enabled, the vendor’s then-current incremental hourly/monthly cost and billing basis, the applicable replica/other charges, and any required plan change or connection disruption. Obtain an explicit Owner confirmation for that exact quoted action. This amendment is not cost confirmation, does not freeze a remembered price and does not authorize an organization-plan upgrade, replica or other add-on. If already enabled, do not purchase it again.

If approved and absent, enable only that project’s dedicated direct-database IPv4 add-on. Preserve the DNS hostname and entire §6 tuple. IPv4 changes transport reachability, not database identity, TLS hostname verification, source eligibility or authority.

After propagation, verify the same direct hostname resolves to a usable IPv4 address and the later approved invocation passes the pinned-CA `verify-full` connection checks. Do not replace the URI hostname with an IP literal, add `hostaddr`, edit `/etc/hosts`, use a proxy, substitute Supavisor/PgBouncer, choose a different port, weaken TLS or move to another project. No static IP literal becomes a new frozen identity. Connection/catalog verification is later setup/execution work, not work performed in this documentation phase.

Any inability to confirm price, enable the approved add-on or establish the exact direct connection remains a blocker; it is not authority for an alternative route. This grant does not enable IPv4 for HIST8’s separate project `pjbjpgnmniwcajqkuhge`. HIST8 remains outside PR #325 and receives no connectivity, TLS, credential, migration or execution authority from this amendment. Any dedicated-IPv4 authority for HIST8 requires a separate documentation-first follow-on amendment under HIST8’s own controlling corpus law, with its own action-time cost confirmation and exact direct-host/no-pooler constraints. Do not add that follow-on decision or any HIST8 path to PR #325.

## 8. Exact operational and repository rollback

Before setup, retain a non-secret action-time configuration record: deployed commit, command, build command, plan, instance count, runtime, region, branch, auto-deploy/previews state and presence/value of non-secret variables being changed. Record secret names and provisioning state only; never snapshot a credential value or the exposed URI. This operational record is not a statistical receipt or a new required schema.

Rollback is exactly:

1. Cancel and verify termination of any running V-1B one-off job; suspend and verify the named base service. Preserve every seal, complete receipt and required log. Classify a crossed seal only through existing Amendment 2A rules and §4's post-terminal evidence-preservation procedure; a valid-seal look remains consumed and nonreplaceable, and its first complete receipt retains the unchanged publication duty. Keep its exact build and retained seal available until recovery produces the first complete terminal receipt or the consuming-negative/incident obligation is lawfully closed; cancellation alone does not erase a pending look. Protective cancellation/revocation may occur immediately, but does not authorize replacing that build or claiming recovery eligibility was restored.
2. Restore the action-time non-secret configuration only while the base service remains suspended. The base command remains exactly `python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"`. Do not restore the historical E-1 command even as a suspended configuration value during V-1B rollback; any later return to E-1 is outside this amendment. Restore the previous `PYTHON_VERSION`/authorized-SHA presence and value if those fields were changed, without launching the reverted runtime. Never restore a §2.4 startup-injection key. Leave all untouched settings untouched.
3. Remove the newly added `ATOM_V1B_GITHUB_TOKEN` from this service and revoke that dedicated PAT through the Owner’s secure control plane. Do not install another token or credential fallback. This is the rollback path for the same cleanup independently required on normal completion by §5.4.
4. Never restore the exposed password or obsolete TLS configuration, including through a platform environment rollback. Keep the new password and conforming reader URI only if every §6.3 containment, rotation, `LOGIN` restoration, backend/prepared-transaction zero and final verification passed and the incident was independently finalized; if safe URI retention later becomes impossible, remove the URI and remain suspended. On any incomplete, failed or uncertain path, remove/keep absent the URI, suspend the parent and preserve the reader role's exactly observed state. If that observed state is `NOLOGIN`, leave it fenced. If it is `LOGIN`, ambiguous or otherwise unsafe, this rollback supplies no silent second fence: obtain separate explicit protective/remediation authority. Rollback does not authorize reasserting `NOLOGIN`, `LOGIN`, an extra termination pass, prepared-transaction mutation, a second password replacement or incident finalization.
5. Repository rollback may begin only after §4's window is lawfully closed—therefore only after no valid seal remains without its first complete terminal receipt or other lawful consuming-negative/incident discharge—and then follows Amendment 2A §10.3 exactly: a separately reviewed revert of only the verified V-1B implementation merge’s first-parent diff on then-current `main`. No repository revert or rollback merge is permitted while the no-ref-update window is active. Never reset history or revert a later per-invocation head containing receipts. Preserve all freezes, this amendment, the eight evidence files, seals and receipts. A non-clean revert requires a reviewed rollback plan; no unrelated refactor or ad-hoc privilege rollback.
6. Do not automatically disable an IPv4 add-on already relied on by other direct clients. Disabling the newly enabled project-wide add-on requires a separate Owner instruction after connection-impact and billing confirmation. It is not a means to restore an old password or erase a consumed look.

A Render rollback that would replay the old command, restore an exposed secret, lose retained evidence or start an unauthorized runtime must not be invoked. The safe rollback state is a suspended service with the isolated inert command, §4's window retained for any undischarged seal, and the role/URI in the exact completed or fenced state required above. Rollback never restores research eligibility.

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

1. Exact probe command/entry point and common startup guard: all six `sys.flags`; direct preferred-prefix `sysconfig` bootstrap; standard-library-before-repository-before-stable-deduplicated `purelib`/`platlib` ordering; `runpy`'s `-m`-equivalent `__name__`, `__spec__`, `__package__`, `sys.argv[0]` and option-tail behavior; and rejection of relative/missing/symlink-substituted/preinserted roots, `PYTHONPATH`, user/global `sitecustomize`, `usercustomize`, executable `.pth`, `site` helpers and every forbidden process-visible startup key. Prove no module-import secret read, no post-start unsetting cure, absent-versus-empty runtime-secret rejection, no connection/network/evidence/dispatch output, complete common import/hash closure, exact JSON/file/stderr/exit rules and truncated-output rejection. The probe and evidence-capable mode cover identical artifact bytes without a CPU-specific probe dispatch baseline.
2. Authenticated same-build provenance; build-producing deploy identity rather than a fictional environment field; secret removal before Create job; secret-free probe observation of `/etc/ld.so.preload`, `PATH` and resolved launcher; effective startup-injection-key absence; current provider evidence binding later one-offs to the accepted `B` native artifact/system layer; and explicit rejection of a claimed control-plane future-job `/etc`/`/proc` read. Test linked-group/secret-file/blueprint/baked-source and empty-value rejection; Save-only installation of only the two secrets without rebuild or non-secret drift; exact pre-job control-plane revalidation; live inline mismatch as possible exposure; no secret-bearing parent resume; stale/changed/ambiguous build or system-layer rejection; no re-probe while recovery is pending; and immutable build retention through recovery.
3. Exact §2.6 comment schemas and canonical hashes, Owner envelope identity, prior independent-review binding, fixed metadata source and all five exact deadline literals. Test monotonic boundaries one nanosecond before, exactly at and after expiration; the secret-free isolated resolver child, bounded/canonical address output, private one-byte acknowledgement, pidfd identity, two equal child-map reads, exact-interpreter/parent-candidate native subset proof, extra/racing/unreadable mapping rejection, hard kill plus synchronous reap, no leaked child/thread/future and no token/URI in its environment/arguments/pipe/output; stalled DNS/address/TCP/TLS/request-write/status/header/framing/body; read-idle slow drip; multi-page pagination and multi-endpoint checkpoint totals; no deadline reset; incomplete responses; every `3xx`/`Location` rejection with no Authorization retransmission; connection close; no retry/`Retry-After`/cache/background fallback; immediate failure on a changed/mixed ref with no movement reread; and exact stage routing. Retain duplicate/missing/edited approval rejection, no acceptance fallback on API refusal/private repository, and exact provenance/readiness/run/receipt and sealed CPU/artifact routing.
4. The inert parent, probe, all nine exact manifest commands, recovery outer process and recovery child carry exact `-I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc`; normal/recovery use the same direct synthetic-parent runner and only the original CLI options. Render/parse actual complete synthetic seals including their final LF with the corrected longer recovery template; prove hexadecimal doubling and every wrapper/escaping/child-source/child-argv byte is counted. Test `command_bytes + 4096 == L` passes, one byte more fails, and missing/unverified limit fails before emission. Test long legal lineage/cohort fields without caps, no truncation/later-boundary substitution, unchanged successful seal bytes, the narrow new-seal capacity BLOCKED exception and consuming recovery failure. Do not assert a finite maximum seal size or reuse an earlier template measurement.
5. Retained PAT scope proof, missing/extra permissions, secret-redaction behavior and normal-completion removal/revocation, not just rollback. URI/password changes preserve the exact target/TLS tuple and never restore the exposed password.
6. Initial incident PENDING/null state permits containment/rotation but blocks activation; uncertain rotation cannot finalize; immutable reader OID; exact frozen `NOINHERIT`; temporary `NOLOGIN`; PostgreSQL 17, zero pre-auth delay/hostname lookup, fixed 600-second maximum and `preauth_activity_fully_visible` proof; the uninterrupted pre-rotation 1201-second drain; both exact administrator-authorized, reader-OID-selected termination transactions; full reader plus cluster-wide unattributed-client zeros before rotation; immediate retained emission of every server-clock bound; successful `\password`/`ALTER ROLE` status before COMMIT; the exact post-rotation 601-second stale-verifier drain with no third kill; reader plus cluster-wide unattributed-client zeros after that drain, after URI provisioning and in the same transaction immediately before `LOGIN`; post-`LOGIN` reader-only zeros; all mandated prepared-transaction zeros; NULL global `rolconfig` and zero per-database role-setting rows at every specified checkpoint; explicit direct/Shared/Dedicated/legacy pooler termination-or-containment proof; one password replacement while fenced; URI provisioning while fenced; and exact `LOGIN` restoration are mandatory. Test startup-packet and authentication timers separately and straddled; the untimed post-authentication/pre-`rolcanlogin` interval represented by a NULL `usesysid` before and after rotation; active, idle, idle-in-transaction, waiting and other-database target sessions; an authentication caching the old `LOGIN` state before the fence; an authentication acquiring the old verifier immediately before rotation; an authentication reaching it after rotation; another-role and cluster-wide unattributed client activity; post-selection PID reuse by another role and collateral-termination incident handling; false return followed by a proved-ended incarnation versus a remaining PID; an owned prepared transaction; a cancelled/mismatched/no-op `\password`; a pooler frontend/cache with no visible backend; a post-restoration reader backend as material; a surviving reader's global/per-database `ALTER ROLE ... SET`; incomplete stats/pre-auth/pooler visibility/termination/role authority; wrong version/maximum/OID; saved PID, narrowed state/database predicate, another role selected by the SQL predicate, `pg_cancel_backend`, prepared-transaction/pooler mutation, new grant/`SET ROLE`, setting reset/adoption, automatic retry and second password rotation rejection. PUBLIC TEMPORARY remains acknowledged; any incomplete path preserves the observed role state, removes the URI, leaves the incident OPEN and requires separate authority for a second fence; rollback keeps the base isolated/inert and preserves every seal/receipt/incident version.
7. The no-ref-update-window contract requires an exact active no-bypass ruleset and `refs/heads/main == E` before either runtime secret is installed, at every runtime checkpoint and through terminal discharge of any seal. Test exact `W` schema/hash and manifest binding; repository-wide complete `CURRENT`/`HISTORICAL_CLOSED` approval classification; a lawfully closed immutable older approval followed by one fresh current window; zero and multiple current windows including overlaps across different `E` or `M`; the fixed read-only ruleset GETs under the checkpoint deadline; omitted versus returned empty `bypass_actors`; both ruleset/ref observations; final ruleset/ref check immediately before receipt construction; pending writers and the exclusive writer gate through post-delete readback; missing/implicit bypass; unavailable/incomplete history or version evidence; persistent default-branch/ruleset/ref mismatch observable by the process; transient rule edit/reversion producing changed history, delete/recreate producing fixed-ID loss, and the invariant that no accepted `main` update is possible while the exact unchanged no-bypass rule is active; rejected versus effective bypass attempts; mixed observations; zero ref-movement rereads; one-manifest/single-look scope; window retention through recovery; exact closure evidence; prohibition on receipt/unrelated merges while active; runtime stage-correct failure routing; and the distinct post-terminal incident branches: no valid seal means no consumed look and no retry beyond existing law plus a fresh reviewed window, while a valid seal remains consumed/nonreplaceable and its first complete receipt keeps the unchanged Amendment 2A disposition. A provably rejected request with no state change is audit-only and non-consuming; no descendant or “unrelated change” acceptance exists inside the window.

A local test command is `python -m pytest -q tests/test_volatility_scorecard.py` in the already authorized development/test environment with synthetic credentials/evidence only. The repository’s actual required CI checks and their existing commands remain mandatory; no check workflow or dependency is altered to make them green. These tests do not constitute a live provenance probe or operational acceptance.

Before an evidence-capable job is created, independent operational acceptance must have the successful credential-free isolated probe; authenticated exact-build/source/launcher and startup-injection proof; approved §2.6 record including `W`; authoritative vendor capacity; PAT scope evidence; finalized incident with exact backend/prepared-transaction termination-or-zero and pooler containment; securely configured exact URI; and any separately approved IPv4 action. Launching that closed command is not acceptance of a database connection or authority to read evidence. During its ordinary initial repository phase, that invocation proves every required authenticated read—including the fixed ruleset projection—within §2.6's exact deadlines using the restricted PAT; it then passes the exact URI/TLS and one-snapshot database-authority checks before evidence reading. No circular requirement demands a prior unlisted token/connection-test job; no trial protected evaluation is a connectivity test. Setup data may contain catalog/authority/session facts but no research-population counts or statistics.

No separate unlisted “preflight CLI” is assumed. The non-consuming probe is §2.4. The evidence-capable CLI is §5.2 and its frozen ordering is the authority/connectivity gate before evidence reads. Owner-controlled external checks use only the explicit control-plane paths in Appendix A. A runtime failure of those pre-read gates yields the existing BLOCKED negative without a consuming seal.

The corrected documentation PR and separate implementation PR both require fresh independent review on the exact final head, every actual required check green, zero unresolved P1/P2/material findings and Owner-only merge. The full corrected documentation replaces the same sole PR #325 path; earlier-head badges do not satisfy either gate. Any new head invalidates earlier final-head approval. ChatGPT Pro authors and audits; Codex owns the narrow implementation, tests, commits and PR preparation. No deadline, self-review, inherited generic merge permission or successful mock may bypass Owner merge or actual check evidence.

Each subsequent valid receipt remains its own documentation-only PR adding exactly one immutable official-schema JSON at its frozen path, with exact-head independent review, green checks, zero material findings and Owner merge. Section 4 creates no publication exception. Neither an operational approval comment nor this document is such a receipt.

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
→ independent build/launcher/startup-isolation acceptance and verified vendor capacity
→ action-time IPv4 confirmation when needed and retained scoped-PAT evidence
→ Owner opens and independent review accepts the exact no-ref-update window while both runtime secrets remain absent
→ temporary NOLOGIN + fixed 1201-second bounded authentication drain + exact reader-OID-selected termination + full pre-rotation reader/unattributed/prepared zero verification
→ one actual password rotation while fenced + exact 601-second stale-verifier drain + explicit pooler termination-or-containment proof + secure Save-only URI/PAT provisioning + exact LOGIN restoration + finalized incident
→ independent operational review and Owner approval metadata
→ exact isolated one-off invocation; unchanged readiness, exact E-held window and exact actual-seal capacity gate
→ original successful seal and unchanged protected calculations
→ verified job termination and worker suspension with inert base command preserved
→ exact post-terminal fixed-ID/history/ref audit + applicable clean or reviewed-incident disposition
→ Owner-authorized exact ruleset deletion + restored-state and H = E readback under the exclusive writer gate
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
| Make parent inert | In the same service’s Settings, set Start Command to exactly `python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c "raise SystemExit(0)"`; save without running a scorecard. This corresponds to Update service’s start-command setting only. | Read back the literal command. No E-1, sleep or scorecard is ever the saved parent command. |
| Suspend / narrowly resume | `POST https://api.render.com/v1/services/SVC/suspend` or, solely for §2.5’s secret-free build preparation, `POST .../resume`, with no command/credential input body. | Acknowledgement followed by service-state readback. Resume never changes the isolated inert command, is forbidden while either runtime secret is installed, and is followed by suspension before a job is created. |
| Remove one secret/startup key | `DELETE https://api.render.com/v1/services/SVC/env-vars/ATOM_E1_SCORECARD_READONLY_DATABASE_URL` and separately the same path ending `ATOM_V1B_GITHUB_TOKEN` or one exact §2.4 service-level startup-injection key; equivalently delete the named key in Environment and Save only. | Confirm runtime secrets and every injection source required by the current step absent, including group/file/blueprint/baked checks. A direct-variable deletion is not proof about linked sources; no shared-source edit is authorized. No secret-value output is retained. |
| Set one allowed variable | Service Environment → the exact allowed key → the specified value → Save only. The corresponding single-key API is `PUT .../env-vars/{exact_key}` with only `{"value": <the authorized value>}` through the private control plane. | Confirm key/provisioning state privately. For non-secret Python/SHA values record exact value; for secrets record no value/digest. No bulk environment replacement. |
| Build exact source | `POST https://api.render.com/v1/services/SVC/deploys` with `{"commitId": E, "clearCache":"clear"}`. No `deployMode`, image, branch, dependency or command override is added. | Retain actual returned deploy ID; retrieve it and successful-build evidence, verify `commit.id = E`. A queued request or different-source build is not acceptance. Cache clearing introduces no dependency choice or source change. |
| Identify successful build | `GET .../services/SVC/deploys/{B}` and service deploy-history reads, with returned pagination cursors followed. | Authenticated successful **build-producing** deploy `B` and no intervening newer build between approval and job creation. The job API is not assumed to expose a `buildId`. |
| Create exactly one job | After the §2.4 prelaunch barrier, `POST https://api.render.com/v1/services/SVC/jobs` with exactly `{"startCommand": Q}`; `Q` is the literal isolated §2.4 probe, one literal isolated §5.2 normal command, or the exact validated isolated §5.2 recovery template. | Actual response `id = J`; retain request, response and bracketing startup/build state. Omit `planId` to inherit the unchanged 4c-8g base plan. There is no per-job env override, arbitrary build selector, schedule or retry parameter. |
| Resolve / monitor job | `GET .../services/SVC/jobs/{J}`; for an uncertain creation acknowledgement, `GET .../services/SVC/jobs` with actual pagination, correlated to the authorized request/creation window. | Resolve the existing job before any further POST. A pending/running/unknown status is not terminal. Manual control-plane status checks are not a runtime polling loop. |
| Capture job output | Existing Render job log stream / One-off Jobs view for actual `J`, or the already available Render log reader with `resource=[J]`. Follow its returned log continuation metadata to completeness. | Retain exact application message bytes after separating platform timestamp/envelope metadata; do not alter canonical JSON/LF content. Truncation or loss is failure, not reconstructed output. |
| Cancel running job | `POST .../services/SVC/jobs/{J}/cancel`, then retrieve `J`; separately suspend/read back parent. | Both terminal job and suspended/inert parent must be proved. Suspending the parent alone does not stop a job. |

The allowed GitHub operational writes are the exact §2.6 review/approval comments, the already authorized documentation/implementation/receipt PR workflow outside an active window, and §4's temporary ruleset lifecycle, all performed through the Owner/reviewer’s own connection. For one window, the exact operations are: read the repository/default-ref and all matching rulesets; create one repository ruleset whose name, target, conditions, active enforcement, three rules and empty bypass list equal §4; read back that returned ruleset ID and ref; with the same Owner control plane, fully paginate `GET /repos/atomatom148-dotcom/ATOM/rulesets/{id}/history?per_page=100&page=1` and retrieve every returned version with `GET /repos/atomatom148-dotcom/ATOM/rulesets/{id}/history/{version_id}` at opening and after each job; and, only after §4's clean-closure predicates or its reviewed incident-closure predicates pass, delete that same ID and read back the restored matching-ruleset/ref state. The complete authenticated response bodies/envelopes and pagination are retained; the history/version operations require the same Owner-side Administration: write permission used for creation/deletion and are never made with the runtime PAT. No update, replace, bypass or second concurrent/overlapping ruleset operation is authorized. A later sequential lifecycle is permitted only after the earlier window's lawful closure/deletion, with a fresh `W`, independent review and Owner approval. If the earlier incident closure proved no valid seal/look, a fresh window also requires the express retry authorization in §4; an incident involving a valid consumed seal never permits a replacement look. At most one current active V-1B window may exist repository-wide, regardless of `E` or `M`. The exclusive ref/settings-writer gate begins before opening and ends only after deletion plus restored-state/`H = E` readback. Any API/UI representation must be independently shown to encode exactly §4; an unavailable or ambiguous mapping blocks the window. The read-only runtime PAT cannot perform a write. Runtime reads are the original authenticated repository/PR/commit/blob/receipt history, the fixed §2.6 PR #325 comment collection and every fixed `W.ruleset_id` endpoint needed for §2.6 current/historical classification at each checkpoint. No URL in a record becomes a runtime fetch target; each ruleset path is constructed only from a validated positive integer in an approval's `W`.

The allowed Supabase IPv4 operation is through the existing Owner-authenticated project Add-ons interface, or the equivalent verified management endpoint:

```text
GET   https://api.supabase.com/v1/projects/afyiydxbjgzaiswnbcyj/billing/addons
PATCH https://api.supabase.com/v1/projects/afyiydxbjgzaiswnbcyj/billing/addons
body = {"addon_variant":"ipv4_default","addon_type":"ipv4"}
```

The PATCH is permitted only after §7’s separately recorded affirmative action-time cost/impact confirmation and only when the add-on is absent. An already-enabled add-on requires no purchase. No `SUPABASE_ACCESS_TOKEN` or other administrative variable is created in Render, and no management call is made by the scorecard. Existing direct DNS resolution/TLS verification uses the original hostname, never an IP substitution. The corresponding HIST8 project action is explicitly not authorized. Disabling IPv4 is not in this sequence without §8’s separate Owner instruction.

The only additional database mutations in this correction are §6.3's exact temporary `ALTER ROLE atom_e1_scorecard_reader NOLOGIN`, two Owner-run `pg_terminate_backend(pid, 10000::bigint)` passes, the already-authorized one password replacement while fenced, and exact `ALTER ROLE atom_e1_scorecard_reader LOGIN` restoration. Each termination statement selects only the exact reader-role OID and `backend_type = 'client backend'` inside the same fresh SQL statement and uses only the preflight-proved existing administrator/`pg_signal_backend` capability; no membership or `SET ROLE` path is added. The new credential remains unprovisioned through both passes, rotation, the post-rotation drain and pooler-containment observation, and the role remains `NOLOGIN` through the later authorized URI provisioning. The associated waits/verification are the fixed uninterrupted 1201-second two-timeout pre-rotation drain; exact 601-second post-rotation stale-verifier drain; proven visibility of pre-authentication rows; full reader and conservative cluster-wide unattributed-client guards both before rotation and again before provisioning/atomically before `LOGIN`; post-`LOGIN` reader-only guards; exact one-second confirmation intervals; role/process/prepared-transaction queries; NULL/zero global/database role-setting checks; and read-only pooler-plane termination-or-containment evidence in §6.3. A setting row is never reset under this amendment. No scorecard/runtime administrator, stored PID, unattributed process, other role selected by the SQL predicate, new privilege, role-attribute change other than that exact temporary `NOLOGIN`/`LOGIN` fence, cancel, generic session cleanup or loop is authorized.

### A.2 Sequence ledger: inputs, authority, environment, output, failure and lifetime

The entries below cover each new prerequisite and its place in the existing program. A step may consume only an input whose source is named here or in its cited normative clause. No field comes from a model’s memory, a guessed future number or a default credential search.

| Step and command/action | Exact inputs and authority source | Data and environment path | Output / failure route / lifetime |
|---|---|---|---|
| **A0 — Documentation adoption**: update only the named PR #325 file; independent review/checks; Owner merge | This complete document; exact current PR head; actual named checks and independent review from GitHub | GitHub repository metadata/worktree, no Render/Supabase input | New reviewed/merged SHA only after gates. A draft/hash is not approval. Any new head requires fresh review. No runtime action. |
| **A1 — Separate Codex implementation**: existing allowed files and `python -m pytest -q tests/test_volatility_scorecard.py`, plus unchanged required CI | Owner-merged Amendment 3, V-1A/TLS/2A, exact implementation source | Synthetic/local test data only; no production URI/PAT or evidence | Tests, exact diff and implementation PR; failures block that merge. Owner merge fixes implementation identity; no PR self-merge. |
| **A2 — Record incident initial state**: create/retain §6.1’s initial private version | Actual known exposure facts, restricted original artifact locators, Owner incident authority | Existing private acceptance packet; no runtime file/env/network read | PENDING/null/OPEN with uncertainty and dispositions; retained, not overwritten. This permits authorized rotation, never activation. |
| **A3 — Contain and sanitize parent**: A.1 inert/suspend/remove operations | Exact service ID; existing Owner control plane; current configuration/readback and §2.4 injection set | URI/PAT and every configured startup-injection source absent; no group/file/blueprint/baked fallback; exact inert command and selected source/build inputs | Non-secret configured-key/inert/suspension proof. The control plane does not claim a future `/etc`/`/proc` read; missing configuration proof → setup BLOCKED/no probe. Only exact service-key deletion is authorized. |
| **A4 — Build**: A.1 exact deploy request | Authenticated `E`; frozen Python/dependencies/build command; no pending valid recovery | Existing Render build system, reviewed source, secret-free configuration | Actual build-producing `B`, successful-build/source evidence. Failed/different/ambiguous build → BLOCKED. Keep `B` selected. |
| **A5 — Probe**: exact isolated §2.4 command in Create job only | Same `B`; documented local Render identity; exact flags/path/launcher; local runtime/artifact and `/etc/ld.so.preload` state; no arguments | No URI/PAT, startup hook, stdin, network, approval file, database or evidence | One exact probe JSON/LF plus retained non-secret launcher/system-preload observation, no file/stderr, exit 0; exact handled failure/usage outputs otherwise. Capture actual `J`, terminate and verify suspension. Never consumes a seal. |
| **A6 — Provenance/startup approval preparation**: build `P` and the §2.4 startup baseline from observation and authenticated `B` | Complete successful probe, independent build/source review, original canonical hashes and current provider same-artifact/system-layer evidence | Existing private acceptance packet; public mirror contains only defined non-secret fields/digests | Approved artifact/startup candidate; no process can approve its own hashes and no control-plane `/etc` read is fabricated. No dispatch baseline. Wrong/absent evidence → BLOCKED, not a new runtime baseline. |
| **A7 — Vendor capacity and IPv4 cost gates**: obtain authoritative `L`; A.1 Add-ons action only after §7 confirmation | Current authoritative Render limit evidence, exact positive byte `L`; separate Supabase project-specific quote/impact approval | Owner/vendor control plane only; no runtime API credential or website fetch | Retained evidence and `C`; absent/ambiguous `L` blocks evidence-capable activation. Cost not confirmed → no purchase. Neither supplies an evaluation boundary. |
| **A8 — Freeze main and scope PAT evidence**: create/read back §4's exact temporary no-ref-update ruleset while both runtime secrets remain absent; inspect §3 fine-grained-token scope without installing it | Exact `E`, `M`, zero pending writers, pre-window ruleset state, existing Owner GitHub control plane, independent reviewer, scoped token metadata | GitHub control plane/private packet only; parent remains suspended/inert and URI/PAT absent from Render | Active no-bypass window record with `main == E`, interval-evidence capability and independent acceptance; non-secret PAT-scope record. Any ambiguity/bypass/pending writer blocks installation and invocation. |
| **A9 — Fence, terminate, rotate, contain, provision and finalize**: exact §6.3 private psql `NOLOGIN`, pre-rotation 1201-second bounded drain, two administrator-authorized reader-OID-selected termination transactions, full pre-rotation reader/unattributed/prepared/role-setting checks, one verified `\password`, post-rotation 601-second stale-verifier drain, repeated reader/unattributed guards, read-only pooler containment proof, Save-only URI/PAT, atomic final guard/`LOGIN`, reader-only final checks and incident finalization | Accepted §4 window; existing Owner accounts/admin or `pg_signal_backend` capability; PENDING incident; fresh password; exact CA/target; immutable reader OID; verified PostgreSQL 17/600-second maximum, zero pre-auth delay/hostname lookup, `preauth_activity_fully_visible` and authority | Reader URI absent through termination, rotation, post-rotation drain and pooler proof; it is installed only at the later authorized fenced provisioning step while `NOLOGIN`, parent suspension/inertness and no-job state persist. PAT is installed only inside the accepted window; admin/new DB password uses only secure prompts/control plane. | Every target PostgreSQL backend ended, every prepared count zero, the conservative unattributed-client guard is zero before rotation and before the atomic `LOGIN` transition, pooler frontends are terminated or explicitly contained, and one password replacement is confirmed. Failure removes the URI, preserves the exactly observed role state, leaves incident OPEN/service suspended and authorizes no silent second fence. Never repeat/test old password. |
| **A10 — Publish operational approval**: exact §2.6 reviewer comment then Owner comment | Completed `A`, canonical digest, actual independent review ID/author and source `E` | Existing authenticated GitHub PR #325 metadata; runtime later uses only read-only PAT | Unique immutable Owner approval/review binding; comment IDs from actual responses. No main commit/rebuild required, no new repository file. Missing/edited/duplicate → failure route in §2.3. |
| **A11 — Normal manifest launch**: one exact isolated §5.2 command in Create job | Actual Owner invocation authorization, window-bound `M`, `H = E`, same approved `B`, accepted `A`, exact startup/window proof | One new job’s native snapshot; URI/PAT only exact Render variables; no startup hook or parent daemon | Startup guard, arguments and authenticated history/provenance/byte/token reads within exact §2.6 deadlines first. Deferred no-first-receipt → exact WAIT/no DB. Other pre-read failures → existing BLOCKED. No retry/fallback or ref-movement reread. |
| **A12 — Connect and count-only scan**: existing normal CLI, no extra preflight command | Exact URI/CA; initial authority; original one-snapshot population/lineage rules | One read-only REPEATABLE READ connection. Its first DB operation obtains original `scan_started_at`; full authority proof precedes evidence-table reads | Earliest READY candidate or exact HOLD. No protected metrics/bootstraps. Normal after-read defects → PRE-CELL INVALID. No separate connectivity snapshot or latest-state substitute. |
| **A13 — Actual-seal transport gate**: in-memory §5.3 rendering | This invocation’s complete schema-valid candidate seal `S`, actual `M`/hash, approved current `L` | Same process/snapshot, exact UTF-8/LF bytes; no file/network/protected output | Exact integer inequality. PASS permits only identical seal bytes. Capacity-only FAIL → existing null-seal BLOCKED negative/exit 1; no consuming seal. Invalid seal/protocol defects retain INVALID. |
| **A14 — Consume and evaluate**: existing seal emission and frozen evaluator | Successful gate, exact `S`, unchanged V-1A/2A prerequisites, active unchanged §4 window and `H = E` | Same process/snapshot and existing execution-log sink | Complete captured seal consumes one identity. Then original calculations only. Exact-head/source/runtime/authority rechecks; any ref/ruleset movement fails by stage; first complete receipt retained, never result-selected. |
| **A15 — Crash/recovery**: corrected isolated §5.2 recovery template, no new mode | Original canonical seal/LF and identity; same `B`/source/startup state; same active window, exact `H = E` and prior-look proof | Isolated outer inline hex → private `/tmp/atom-v1b-seals/<hash>.json` → isolated child/original recovery option; no network seal retrieval | Validate input before resource access. Window/ref or prerequisite mismatch → consuming INVALID/incident route. Invalid file/prelude does not erase pending seal. No replacement look or automatic POST/GitHub retry. |
| **A16 — Stop, audit, cleanly close or incident-hold the window, publish or rollback**: resolve any Create result; cancel/status + suspend/readback where a job exists; §4 control/history audit and closure; immutable receipt PR; §8 reversal | Actual job IDs/statuses or proof no Create was accepted, first complete receipts, retained seals, complete ruleset history/version and ref/default-branch brackets, Owner closure/incident/revert decision | Existing logs/private packet/GitHub receipt paths; no recreated evidence | Base suspended/inert; any job terminal. Keep `main == E` and ruleset active while recovery/outcome is pending. §4's exact zero-job, terminal-no-seal or terminal-receipt branch plus a clean audit permits exact-rule deletion under the writer gate and only then publication/unrelated work. For a breach first found post-terminal: with no valid seal, no look was consumed and any later window remains subject to existing law; with a valid seal, the first receipt keeps its unchanged publication duty, the look remains consumed and no replacement is permitted. Remove/revoke PAT only when allowed; retain rotated URI/records/history. Reviewed Owner-merged revert only. |

The mutation authority in A8/A9 is credential administration, not evidence mutation. A12/A14 alone are the official scorecard snapshot/evaluation. A2/A6/A7/A9/A10 are operational evidence, not new study receipts or a READY publication. A0/A1 do not execute any later step.

## Appendix B. Adversarial walk-through and executable document-model audit

### B.1 Outcome matrix

The following cases were walked through against the normative clauses; implementations must preserve these outcomes. They are failures to accept unsafe execution, not permissions to repair outside scope.

| Adversarial case | Required outcome and decisive clause |
|---|---|
| Probe is created while a service-level secret is removed but a linked group still supplies it | No accepted probe; §2.5 effective-source proof fails, and §2.4 rejects key presence even when its value is empty. No shared-group edit is silently authorized. |
| Operator clears the variables only inside Python after startup | Not secret-free: §2.5 removal must precede Create job’s environment snapshot; §2.4 cannot unset to manufacture absence. |
| `PYTHONPATH`, user/global `sitecustomize`, an executable `.pth`, `LD_PRELOAD`/another `LD_*`, `BASH_ENV` or an exported Bash function can run before application code | No secret-bearing process is created. Exact `-I -S -B`, direct path bootstrap and the external startup-injection barrier are indivisible; an empty or post-start-cleared value still fails under §2.4. |
| Isolated startup cannot import `quant`, so an operator calls `site.addsitedir()` or drops `-S` | Rejected. Only the literal direct preferred-prefix `sys.path` bootstrap is authorized; it processes no `.pth` and all probe/parent/normal/recovery processes retain `-I -S -B`. |
| `PATH` resolves `python` through a wrapper, or only the recovery child drops isolation | Startup acceptance fails before a secret-bearing Create job. The secret-free launcher binding and both recovery interpreter argument lists must remain exact; §§2.4–2.5 and 5.2. |
| PAT/URI restored while an already-created probe is running | The provider’s snapshot is isolated, but §2.5 still requires probe termination before restoration; do not waive the ordered evidence requirement. |
| Probe tries to call GitHub to discover its build ID | Forbidden. §2.4 is network-free and reads no build-ID variable. Owner binds actual build-producing deploy `B` externally under §2.5. |
| Probe artifact measurement is accepted because its versions match | Forbidden. Independent approved same-build provenance is required by §2.2; measurement/versions alone are not acceptance. |
| Approval record is inaccessible in the private packet from a job | No runtime private-packet read is attempted. §2.6 supplies the exact Owner-authenticated non-secret metadata mirror and reviewer identity. |
| Caller supplies a provenance file, alternative variable, comment URL or build ID | Rejected; none is an authorized normal/probe input. §2.6 uses fixed collection plus existing `E`, validates uniqueness and does not dereference payload URLs. |
| Comment read requires more PAT scope or pagination is incomplete | BLOCKED before database access, not empty history or an unauthenticated fallback; §§2.6 and 3. |
| A resolver child loads a native executable mapping absent from the parent candidate, changes maps while paused, exits before inspection or receives a caller byte | Discard all addresses and fail before token access. Exact pidfd/interpreter identity, two equal map reads, native subset and sole `0x01` parent acknowledgement are mandatory; §2.6. |
| DNS/TCP/TLS, request write, status/header/body or a later page stops making progress | The earliest exact monotonic connect/read/request/checkpoint deadline aborts and discards the whole observation. No automatic retry, partial-page use or deadline reset; §§2.3/2.6. |
| A peer sends one byte inside each read-idle interval forever | Read-idle may reset, but the immutable request-total and checkpoint deadlines still terminate the read. Completion exactly at a deadline fails. |
| GitHub returns a same-origin or cross-origin redirect, or a `Location` header on any response | Hard request failure. Follow no redirect and never retransmit Authorization; §§2.6/3. |
| The same GitHub deadline fails before evidence, after evidence, after seal/recovery acceptance or during the post-cell final check | Route respectively to BLOCKED, null-seal PRE-CELL INVALID, consuming PRE-CELL INVALID or POST-EVALUATION AUTHORITY INVALID; no timeout-specific schema/reason. |
| A build is produced after approval or while a sealed crash awaits recovery | It cannot silently replace `B`; §§2.3/2.5. New-seal mismatch blocks before reads; accepted-seal recovery consumes failure. |
| Same native bytes but a different CPU chooses different `log`/`exp` offsets before the first seal | Allowed only within authenticated libm/native files, with invocation-derived dispatch; §2.2. No probe dispatch literal. |
| Different dispatch or native bytes appear during recovery | Consuming INVALID under §2.3; never rebaseline or create another look. |
| A prior immutable approval for the same or a different `E`/`M` refers to a lawfully closed and deleted ruleset | Classify it `HISTORICAL_CLOSED` only through its 404 plus the new approval's independently reviewed repository-wide closure binding. It is retained but is not a duplicate current authority. Exactly one fresh `CURRENT` approval across all execution SHAs/manifests remains required; §2.6. |
| An approval is edited, not posted by the authenticated Owner, not bound to independent review, has an ambiguous/unclean closure, or produces zero/multiple current windows | §2.6 rejects the checkpoint; pre-read BLOCKED on a new seal, consuming negative after accepted recovery seal. No “latest” selection. |
| An unrelated SIM/HIST8/documentation/receipt merge is queued before the window | Resolve or remove the pending writer without moving `main`, then open the exact window; otherwise activation is BLOCKED. Once active, even an unrelated merge is deferred until lawful closure; §4. |
| A persistent `refs/heads/main`/ruleset mismatch is observed by the running process | Window breach with the existing failure route for the evidence/seal stage; never substitute a descendant or replacement look; §4. |
| The post-terminal history/version audit first reveals a rule edit/reversion or fixed-ID loss, or other authoritative evidence reveals an effective bypass/ref update although runtime snapshots passed | Do not retroactively fabricate, suppress or amend a runtime receipt. If no valid seal was emitted, no look was consumed; retain the setup/job/output evidence and require reviewed incident closure before any later window allowed by existing law. If a valid seal was emitted, retain and submit its first complete receipt under unchanged Amendment 2A law; that look remains consumed and no replacement is allowed. The window cannot close cleanly in either branch; §4. |
| `refs/heads/main` changes while its commit/tree/receipt facts are being read | Discard the mixed observation and fail that checkpoint inside its original §2.6 deadlines. No movement reread is authorized. |
| A rule has an Owner/admin/app bypass, the ruleset is persistently edited/disabled/deleted/recreated, or complete history/version evidence is unavailable | No accepted window. Runtime detects persistent fixed-ID/projection failures at its checkpoints; the Owner history audit detects rule-version changes. Before secrets/evidence failure is BLOCKED; a crossed seal remains consumed and is handled only through §4's applicable runtime or post-terminal incident route, never by ref movement or a new look. |
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
| Active, idle, idle-in-transaction, waiting or other-database reader backends exist at rotation | Every reader-OID client backend is included regardless of state/database. The new URI remains absent through the authentication drain, both termination passes and the full reader/unattributed zero guards; §§6.1/6.3. |
| An old-password connection stalls through startup-packet handling and then authentication | The fixed uninterrupted 1201-second two-timeout drain outlasts both PostgreSQL 17 maxima before the second fresh pass. A 601-second drain is rejected as insufficient; any unreconciled backend or post-restoration backend is material. |
| An authentication acquired the old verifier immediately before the password COMMIT and finishes later | `NOLOGIN` remains active and the exact 601-second post-rotation authentication-phase drain expires that verifier exchange before URI provisioning or `LOGIN`; no third termination pass or shortened wait. |
| `pre_auth_delay` is nonzero, `log_hostname` is on, or either changes during the fence | The 1201-second proof is unavailable. No setting mutation is authorized; preserve/obtain protective state and block for documentation-first resolution. |
| A materialized reader PID exits and is reused by another role before the signal | PostgreSQL has no stock `(pid, backend_start)` signaling primitive. The exact fresh OID-selected statement minimizes but cannot eliminate that residual under the existing administrator/`pg_signal_backend` capability; any observed or suspected collateral termination is a material incident and stops V-1B; §6.3. |
| The checked backend exits and its PID is recycled in PostgreSQL's residual interval between the internal role check and OS signal | Do not claim identity-bound signaling. This narrow source-documented residual is accepted only for the two exact passes; any observed/suspected collateral termination is a material incident and stops V-1B. No broader identity or extra pass is authorized. |
| `pg_terminate_backend` returns false, activity is not fully visible, a target remains, or the final post-provisioning count is nonzero | A false race is acceptable only with all later fresh zero observations. Otherwise remove/keep absent the URI, keep the incident OPEN and parent suspended; no second rotation or broader kill. |
| A reader-owned prepared transaction exists after its backend ends | It is neither terminated nor contained by a zero activity count. Keep/establish the authorized fence, leave the URI absent and require a separate disposition; no prepared-transaction mutation is authorized. |
| `\password` is cancelled, mismatched or errors, followed by a successful no-op COMMIT | Not a rotation. COMMIT is forbidden without the retained successful `\password`/`ALTER ROLE` tag; rollback, remain PENDING and do not repeat under this grant. |
| A Shared/Dedicated/legacy pooler frontend authenticated with the old password is absent from `pg_stat_activity` | It is not called terminated. Finalization requires the exact plane inventory and vendor-grounded proof that it has no live server lease and cannot regain a backend after rotation; otherwise remain fenced and require a separate drain/purge decision. |
| A global `rolconfig` value or `pg_db_role_setting` row exists for the reader before restoration | Keep `NOLOGIN`, URI absent and incident OPEN. Do not reset/adopt it under this amendment; it is a material persisted-state finding requiring documentation-first disposition. |
| Analyst says NOINHERIT/no memberships means no TEMPORARY privilege | Incorrect; §6.1 preserves effective PUBLIC TEMPORARY and requires temporary-object/storage/connection/resource investigation. |
| Attacker disregards the scorecard’s read-only transaction convention | The incident analysis does not assume compliance. The existing no-durable-table-write/no-BYPASSRLS finding remains narrower; §6.1. Legitimate scorecard temp-use prohibitions are unchanged. |
| Parent is suspended while a one-off is still running | Not complete containment. §5.4/A.1 separately require cancellation/terminal job proof and parent suspension. |
| Creation request times out after Render may have accepted it | Resolve the actual job by control-plane listing/retrieval before any new POST; no autonomous duplicate invocation. |
| First complete result is unfavorable or an INVALID receipt, including when later control evidence creates a §4 incident | Retain and submit it unchanged under original Amendment 2A receipt/one-look/nonselective-continuation law. No favorable-result replacement or suppression is authorized; later control evidence is retained separately and never selected by result content. |
| Normal-success path ends with the dedicated PAT still installed | Incomplete cleanup. §5.4 requires removal plus GitHub revocation once all authorized invocations are closed and no valid recovery remains pending. |
| Rollback proposes restoring old E-1 command, exposed password or obsolete trust setting | Forbidden even on a suspended base during V-1B rollback; §8 retains the inert command, rotated URI and pinned TLS. |
| Rollback would reset current main or erase an earlier receipt/evidence artifact | Forbidden; §8 permits only the reviewed implementation first-parent diff revert on then-current main. |
| HIST8’s similar IPv4 issue is added while fixing V-1B | Outside PR #325. §7 retains `pjbjpgnmniwcajqkuhge` exclusion and requires its own follow-on amendment. |
| Earlier PR-head checks/review are green but the replacement has not been reviewed | No merge. §9 requires fresh exact-final-head independent review, green actual checks, zero material findings and Owner-only merge. |

### B.2 What was actually tested during document authoring

The prior 125-assertion/27-transport-fixture authoring run applies only to the superseded input text at `caeae8c1be63a54c5926b56c8aa44eb04be247ff`. It did not test this correction's isolated runner, longer recovery command, resolver/deadline behavior, no-ref-update window or authentication-drain/termination lifecycle and is not evidence for the corrected final head. This correction claims no replacement assertion count or successful execution.

Before final-head approval, the document model and later implementation tests must add every case in §9 and B.1, render and parse the exact corrected commands, and record the actual command/test count and results without editing a result to fit an earlier claim. Synthetic fixtures remain non-production and do not constitute a Render job, GitHub/PAT acceptance, PostgreSQL termination, real incident finalization, protected statistic, independent review or operational acceptance.

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
| Startup permits `PYTHONPATH`, site/user customization, shell functions or native preload hooks to execute before runtime-secret access | Exact-head P1 | §§2.4–2.5, 5.2–5.4, 8, 9; A.1–A.2 | Every Python path uses `-I -S -B` and the direct no-site bootstrap; prelaunch evidence excludes shell/native injection, system preload and launcher drift before either secret-bearing process can start. |
| GitHub transport has no exact connect/read/request/pagination deadline | Exact-head P2 | §§2.3, 2.6; §9 test 3 | Five immutable monotonic deadlines cover connect, read-idle, request total, pagination total and checkpoint total; the bounded resolver/nonblocking transport forbid reset/retry/fallback and route failure by the existing evidence/seal stage. |
| Unrelated `main` movement can make a sealed execution fail final `E == H` | Exact-head P1 | §§2.6, 4; §9 test 7 | Owner-enforced no-ref-update window holds exact `main == E` from before either runtime secret is installed through terminal discharge. Runtime checkpoints detect persistent state loss; the mandatory post-terminal history audit detects transient edit/revert/delete/recreate. Authorized unrelated merges are deferred. A post-terminal breach with no valid seal consumed no look and any later window remains governed by existing eligibility/incident law; a breach after a valid seal leaves the first receipt's disposition unchanged, holds the consumed look and never permits a replacement identity. Lawfully closed sequential windows do not deadlock on their retained immutable approvals. |
| Password rotation leaves pre-rotation authenticated reader backends alive | Exact-head P1 | §§6.1–6.4; §9 test 6; A.1–A.2 | Temporary `NOLOGIN`, immutable OID/pre-timer/pre-auth-visibility proof, 1201-second pre-rotation drain and two administrator-authorized reader-OID-selected termination transactions precede rotation. Exact reader-process, prepared/settings and cluster-wide unattributed-client guards run before rotation, after the 601-second stale-auth drain, after URI provisioning and atomically before `LOGIN`; reader-only guards continue afterward. Pooler frontends must be terminated or explicitly proven unable to regain a backend. No new `SET ROLE` grant, discretionary containment or silent repair permits finalization. |

### C.2 Cross-contract contradiction scan

| Controlling source / boundary | Cross-check performed | Result of the authored contract scan |
|---|---|---|
| V-1A §§2–11 | No model, formula, numerical order, causal rule, benchmark, population, threshold, classification, bootstrap/RNG or multiplicity change introduced | Preserved by incorporation; no scientific parameter supplied by operational records. |
| V-1A §§12–16 and TLS Amendment 1 | Existing implementation allowlist/conditional 033, exact CA bytes, direct hostname/port/database/role, full TLS tuple, catalog/no-write checks and original runtime field set | Preserved; only explicitly named operational comparison/credential/probe changes and the separately named administration-prompt exception apply. |
| V-1A §24 and Amendment 2A §8.6 | Stage-dependent refusal routing | Capacity-only post-count BLOCKED exception remains the only after-read exception. Startup, GitHub deadline, unsafe-head and session-setup failures use the existing stage's BLOCKED/INVALID route; no new schema or reason code. |
| Amendment 2A §§5–10 | Nine manifests, earliest boundary from original `T_amend`, six minima, initial snapshot timestamp, same-process seal/results, prior-look guards, sealed recovery and byte/source binding | Preserved. §4 temporarily holds the authenticated default ref exactly at `E` across one manifest's new-seal/recovery lifecycle; no descendant, current head or ref event moves a boundary, identity, result or look. |
| `AGENTS.md` and merged TLS §5 | Governance domain, SIM-5 pointer and narrow parallel V-1B exception, distinct documentation/implementation/operations, Owner merge | No pointer, role-governance or SIM/HIST8 scope change. Codex implementation remains separate; fresh exact-head review/Owner merge mandatory. |
| Render one-off/CPython startup behavior | Build/configuration snapshot, command shell/loader/Python startup, no inherited parent local disk, `startCommand` override, parent suspension not terminating a job | Secret-free launcher is bound; configurable shell/native hooks are absent before secret installation; probe/parent/normal/recovery use exact isolated commands; recovery staging and child are both covered. |
| PostgreSQL 17/Supabase connection planes | PUBLIC TEMPORARY, TLS/SCRAM/password rotation, both startup/authentication timers and pre-timer paths, stale-verifier lifetime, activity/prepared visibility, reader-OID-selected administrative signaling, direct and pooler frontend/server leases | No PUBLIC TEMPORARY/RLS change. Exact `NOLOGIN`/`LOGIN`, zero pre-auth delay/hostname lookup, two reader-OID-selected termination passes, pre/post-rotation unattributed-client guards, post-rotation stale-auth drain, backend/prepared zeros and explicit pooler termination-or-containment proof precede finalization; no new role grant or invented pooler mutation endpoint. |
| Secret lifecycle / sources | One runtime PAT, one existing reader URI, no probe secrets, retained scope/startup/session evidence, normal closure plus rollback | Exact sources/absence/reinstallation/cleanup paths specified. New URI stays absent until termination proof; private evidence never becomes runtime input. |
| Complete command/data dependency scan | All new operands have fixed literals or exact authenticated response/record sources; command bytes use the corrected runner; head facts remain exact under one accepted window | No unresolved timeout, startup path, descendant baseline, termination target, seal limit, approval file, build-ID environment variable, alternate credential or arbitrary fetch URL remains in the authored path. |

Internal scan conclusion: zero newly introduced internal contract contradictions were found in the defined paths and modeled cases after the corrections recorded above. This is an author’s bounded adversarial check, not a claim of mathematical completeness, a substitute for independent review, or a statement that operational blockers are zero.

Operational acceptance is not asserted. In particular, no authoritative numeric Render `startCommand` capacity was established by the official references inspected for this document. `L` must be obtained through §5.3’s explicit vendor evidence path; until then evidence-capable activation is BLOCKED. The same-build isolated probe, effective startup-injection/system-preload absence, exact launcher, actual one-off identity/inheritance, secure administrative rotation, authentication drain/termination/zero proof, real private incident finalization, token scope/deadlined reads, direct-host TLS reachability and action-time IPv4 cost confirmation also require their actual prescribed acceptance evidence. Those are retained fail-closed gates, not facts inferred from document text, synthetic tests or green CI. If vendor behavior cannot satisfy one frozen mechanism, redesign remains documentation-first; this document does not claim it has already succeeded.

---

## Source record and verification boundary

Authenticated read-only GitHub inspection on 2026-09-07 confirmed PR #325 open and unmerged, with base `f0035147a646fc7d4c7002c8a2706f4987f6a10c`, exact input head `caeae8c1be63a54c5926b56c8aa44eb04be247ff`, and exactly one changed path: `docs/v-1a-amendment-3-v1b-operational-prerequisites.md`, Git blob `da088882e5398cb4834c839aebde1101e1c00638`. This narrow correction was authored against those exact input bytes. It changes only the four exact-head findings identified in Appendix C and their necessary command, test, lifecycle and appendix consumers. The corrected final head/blob/hash do not exist until Codex applies this text; none is predicted here, and the reviewed input head cannot satisfy the new final-head gate.

The inspected current main remained `f0035147a646fc7d4c7002c8a2706f4987f6a10c`; GitHub reported it unprotected. V-1A source blob was `4bafc8e1d0d52e05b2832f1355b903d544e953ec`; Amendment 2A source blob was `e95dbbe3780629366cd77f8d9d8c2c6f26086450`; `AGENTS.md` source blob at the correction head was `26f12b78098429bad77450c742ed58c66434e30e`. The exact inherited source documents, not a summary of prior chats, govern unchanged mathematics and receipts:

- V-1A: `docs/v-1a-volatility-first-freeze.md`, especially §§12–19 and 24–26.
- TLS Amendment 1: `docs/v-1a-amendment-1-tls-trust-anchor.md`, especially §§2–6.
- Amendment 2A: `docs/v-1a-amendment-2a-tiered-readiness-boundaries.md`, especially §§5–11.
- `AGENTS.md`: governance/technical-domain separation, Owner operational instructions, phase separation, final-head review, active-pointer boundary.

Read-only Render service/deploy metadata on 2026-09-06 still showed the named parent suspended, one 4c-8g instance, auto-deploy off and the stale E-1/sleep command. The observed existing latest deploy was not a V-1B acceptance build. This document did not replace that command, fetch environment secret values, create a build/job, rotate a password, access database evidence, publish an operational approval or purchase IPv4.

Official vendor references from the input document and the 2026-09-07 exact-head correction review:

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
12. CPython 3.14 command line, path initialization, `site` and `runpy` — https://docs.python.org/3.14/using/cmdline.html, https://docs.python.org/3.14/library/sys_path_init.html, https://docs.python.org/3.14/library/site.html and https://docs.python.org/3.14/library/runpy.html — isolated/no-site flags, path/user-site/customization behavior and `-m`-equivalent module execution.
13. GNU libc Dynamic-Linker Hardening — https://sourceware.org/glibc/manual/latest/html_node/Dynamic-Linker-Hardening.html — loader environment/preload surfaces considered by the prelaunch barrier.
14. PostgreSQL 17 server-signaling and statistics functions — https://www.postgresql.org/docs/17/functions-admin.html and https://www.postgresql.org/docs/17/monitoring-stats.html — `pg_terminate_backend` timeout behavior and current backend observations.
15. PostgreSQL 17 connection settings and Supabase role limits — https://www.postgresql.org/docs/17/runtime-config-connection.html and https://supabase.com/docs/guides/database/postgres/roles-superuser — `authentication_timeout` and hosted administrative-role constraints.
16. GitHub rulesets — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets, https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets and https://docs.github.com/en/rest/repos/rules — branch targeting, restrict-update/delete/force-push behavior, bypass lists, Metadata-read fixed-ID ruleset GETs (whose read-only response may omit `bypass_actors`) and authenticated ruleset lifecycle; actual plan/effective-state/history capability remains an operational gate.
17. CPython socket, SSL, subprocess and selectors — https://docs.python.org/3.14/library/socket.html, https://docs.python.org/3.14/library/ssl.html, https://docs.python.org/3.14/library/subprocess.html and https://docs.python.org/3.14/library/selectors.html — isolated resolver-process, nonblocking connection/handshake/I/O and synchronous child cleanup mechanics used to make the frozen monotonic deadlines enforceable.
18. PostgreSQL 17 backend startup/source and server-signaling behavior — https://doxygen.postgresql.org/backend__startup_8c_source.html, https://doxygen.postgresql.org/postinit_8c_source.html and https://www.postgresql.org/docs/17/functions-admin.html — the startup-packet and authentication timers, pre-timer delay/hostname paths, authentication-before-`LOGIN` order, the intervening not-yet-role-attributed backend state and `pg_terminate_backend` capability/timeout behavior; these ground the 1201-second pre-rotation drain, two reader-OID-selected termination passes, 601-second post-rotation stale-auth drain and conservative NULL-`usesysid` guards before rotation and `LOGIN`.
19. Supabase database connection methods and Supavisor behavior — https://supabase.com/docs/guides/database/connecting-to-postgres and https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI — Shared/Dedicated pooler planes and frontend/server-connection separation considered by the explicit termination-or-containment record; no legitimate pooler route or undocumented administrative operation is authorized.

These references explain supported mechanics, not fulfilled gates. Vendor changes do not silently amend this freeze. No numeric limit, private incident fact, future merge/build/job ID, actual review conclusion or successful deployment is fabricated by this complete document.
