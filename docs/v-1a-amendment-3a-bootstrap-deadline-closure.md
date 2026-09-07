# V-1A Amendment 3A — V-1B Bootstrap and Deadline Closure

**Decision ID:** `ATOM-V1A-AMENDMENT-3A-BOOTSTRAP-DEADLINE-CLOSURE-1`
**Status:** PROPOSED — no effect before independent final-head review, green required checks, zero material findings, and Owner merge.
**Author:** ChatGPT Pro — architecture and freeze authority
**Date:** 2026-09-07
**Document state:** Complete narrow follow-on for review; not an assertion of implementation or operational acceptance.
**Sole documentation-PR path:** `docs/v-1a-amendment-3a-bootstrap-deadline-closure.md`
**Implementation owner:** Codex; the required separate V-1B implementation PR remains the sole implementation vehicle and has one implementation owner.
**Approval, merge, credentials, infrastructure and budget authority:** Owner.

## 1. Decision, effectivity and exclusions

This amendment closes exactly nine implementation ambiguities in the Owner-merged V-1A Amendment 3:

1. every probe, normal, recovery-outer and recovery-child inline bootstrap receives one exact non-writing exception-hook prefix;
2. authenticated GitHub transport receives an exact 64 MiB per-response raw-wire cap and deadline-aware work receives an exact 64 KiB work chunk, with an explicit bounded-native-call model;
3. each paginated page receives its own request-local 60-second deadline while the unchanged pagination and checkpoint deadlines remain cumulative;
4. the final repository checkpoint must be completely validated before the final runtime remeasurement, and that remeasurement remains inside the same checkpoint deadline;
5. a resolver child that reaches or crosses a deadline enters irreversible failure quarantine and is killed, reaped and closed even though cleanup necessarily occurs after acceptance time has expired; and
6. dependency `files()`/`RECORD` ownership is defined for the observable frozen dependency closure, including safe wheel-installed script members, without pretending that a shared installation root assigns every inert physical file to every distribution or that the runtime has a generic file-I/O tracer;
7. New York civil-time construction is forced to the exact `tzdata` distribution resource already covered by the dependency tree, never an unmeasured system TZif or earlier cache; and
8. GitHub HTTPS uses one CPython-default CA bundle observed by the secret-free probe, independently approved and continuously remeasured, with its first use explicitly rooted in Amendment 3's foundational Render native/system-layer/default-PKI boundary rather than circularly self-authenticated by a GitHub response; and
9. the competing final-GitHub and final-database “immediately before receipt” requirements are replaced by one exact indivisible terminal-verification order.

This amendment changes only the corresponding command, deadline, resolver-cleanup, final-checkpoint/final-database-authority ordering, dependency-ownership, time-zone-source and GitHub-transport-trust provisions of `ATOM-V1A-AMENDMENT-3-V1B-OPERATIONAL-PREREQUISITES-1`. V-1A, TLS Amendment 1, Amendment 2A and every other Amendment 3 rule remain controlling. In particular, this amendment changes no model, formula, numerical operation or order, benchmark, population, threshold, classification, multiplicity, session convention, causal cutoff, earliest-boundary rule, minimum, lineage/cohort rule, calibration, bootstrap/RNG stream, seal, one-look rule, recovery identity, receipt schema, status, stage, reason code, filename, source table, credential, role, service, command option, manifest membership, protected statistic or publication rule.

This is additive law, not a replacement of Amendment 3. The original Amendment 3 document remains byte-unchanged. The documentation PR for this amendment adds exactly this one file. It adds no implementation, test, dependency, certificate, migration, workflow, configuration, approval comment, seal or receipt. Drafting, reviewing or merging it performs no build, probe, job, network request, database connection, evidence read, password or role action, backend termination, restart, deployment, service resume, ruleset mutation, credential operation, IPv4 purchase or protected calculation.

After Owner merge, Codex may apply these provisions only inside the already authorized V-1B implementation surface and tests. No deadline or operational target bypasses independent exact-final-head review, actual required-green checks, zero unresolved material findings or Owner merge.

## 2. Exact non-writing bootstrap transformation

### 2.1 Frozen source transformation

Let the exact ASCII byte string `H` be:

```text
import sys;sys.excepthook=sys.unraisablehook=lambda *_:None;
```

`H` is exactly 60 bytes, contains no LF, CR, shell quote, environment read, file operation, network operation, output operation or secret access, and ends with the shown semicolon. It creates one no-closure variable-argument lambda, assigns that same object to both `sys.excepthook` and `sys.unraisablehook`, and returns `None` for every call. It never writes to stdout or stderr and never delegates to an earlier hook.

For an exact Amendment 3 inline `-c` source byte string `S`, define:

```text
T(S) = H + S
```

There is no separator, normalization, regenerated whitespace or newline between `H` and `S`. Apply `T` exactly once to each of these four execution sites and nowhere else:

- the complete probe `-c` body in Amendment 3 §2.4;
- the complete normal scorecard `-c` body in Amendment 3 §5.2, before any one of the nine unchanged CLI suffixes;
- the complete recovery-outer `-c` body in Amendment 3 §5.2; and
- the complete recovery-child `-c` body decoded by the outer process and supplied to its isolated `execv` child.

For recovery, transformation order is exact:

1. decode Amendment 3's fixed embedded lowercase child-source hexadecimal to the original child source `S_child` and require byte equality to the original normal `-c` body;
2. compute `S_child_3A = T(S_child)`;
3. replace exactly the one embedded lowercase hexadecimal encoding of `S_child` in the original recovery-outer source with `S_child_3A.hex()`; call that otherwise unchanged source `S_outer_rehexed`; and
4. use `T(S_outer_rehexed)` as the recovery-outer `-c` body.

No operator, environment value, launcher or runtime chooses the prefix or regenerated child bytes. The normal and recovery-child transformed body has these deterministic text properties:

```text
len(S_child_3A)       = 3092
len(S_child_3A.hex()) = 6184
sha256(S_child_3A)    = f79378de92204cfec2fe4818c341cc23b5dfb685179f05e5722441ce9a608d62
```

The transformed probe body has these deterministic text properties:

```text
len(T(S_probe))       = 3100
sha256(T(S_probe))    = e4907f41ac3c60efdfe7874677d0214ccca0eab9f0ab6d56820b47633eefc143
```

All lengths above count ASCII bytes and exclude the shell quotes, interpreter arguments and any newline. These values are command-text invariants, not runtime-artifact, seal or receipt fields. Amendment 3's former fixed recovery-child values `3032`, `6064` and `5c24ae7113db69c57436dafa42cb3b8aa9961ad14577e0729825fd50edf87d0c` are superseded only for this transformed command. The actual-seal recovery-capacity calculation must use the complete transformed outer command, the 6,184-byte child-source hex, every substitution and the unchanged 4,096-byte margin. No pre-3A command measurement is reusable.

Every interpreter switch, path/bootstrap check, environment prohibition, synthetic `quant` namespace construction, probe entry point, `runpy` call, recovery staging operation, child `execv` argument, manifest suffix and recovery option remains byte-identical after removing the exact added prefix and the mechanically regenerated child hex. The inert parent command and the internal resolver-child source are not transformed by this section.

### 2.2 Hook lifetime and failure meaning

The exact prefix is the first executable source in each transformed `-c` body. The reviewed scorecard module captures the installed hook object at its earliest import-time opportunity without invoking it, and the common startup guard requires:

```text
sys.excepthook is captured_bootstrap_hook
sys.unraisablehook is captured_bootstrap_hook
```

No reviewed probe, normal, recovery or imported application path may explicitly replace, wrap, invoke or restore either hook. Interpreter dispatch to the exact hook after an otherwise uncaught exception is its sole purpose. The existing import-time no-output/no-network/no-secret rule remains exact. A guard mismatch fails before either runtime secret is read and follows the unchanged new-seal or consuming-recovery route.

An ordinary uncaught Python exception raised after `H` has executed but before application-owned output is attempted therefore produces no traceback or other hook output; CPython exits nonzero. An explicit `SystemExit(1)` remains non-writing. This closes Amendment 3's claim that a handled inline-bootstrap refusal has empty stdout and stderr when a bootstrap primitive raises instead of returning a false predicate. It does not turn a recovery failure into a new look, erase a staged retained-seal file, create a new receipt type or change any stage-dependent failure route.

The transformation cannot govern a failure before the `-c` source begins executing, including command-source compilation failure, interpreter/native-loader failure, signal termination or platform failure. Such an event remains an infrastructure failure with no inferred output or acceptance fact. Exact command/source review makes a syntax-different command unauthorized; this amendment does not claim a no-op hook ran when it did not.

## 3. Bounded GitHub deadline-work model

### 3.1 Exact literals and raw-wire boundary

Add these exact positive integer implementation literals beside Amendment 3's five unchanged GitHub deadline literals:

```text
GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES = 67_108_864
GITHUB_DEADLINE_WORK_CHUNK_BYTES   = 65_536
```

The first value is exactly 64 × 1024 × 1024 bytes. The second is exactly 64 × 1024 bytes. They are fixed source literals, not environment/configuration values, server hints, scientific limits or identity/seal/receipt fields.

`GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES` applies separately to each authenticated GitHub HTTP response. “Raw wire” here means every HTTP/1.1 response octet returned by the authenticated TLS stream after TLS decryption and before HTTP framing removal: status line, headers, the header terminator, transfer-coding syntax and trailers when present, and the encoded body. TLS record bytes that the application cannot observe are not double-counted. Amendment 3's content-encoding, framing, status, redirect and complete-EOF requirements remain unchanged.

At most 67,108,864 raw-wire bytes may be retained or accepted for one response. Equality passes only if the next deadline-bound receive proves clean TLS EOF and the complete response is parsed and response-local validation finishes before every applicable deadline. A 67,108,865th octet, an inability to prove EOF, a partial framing unit or an allocation/read defect rejects and discards the whole response. No cap-sized prefix is parsed, cached or combined with another request. The cap is per response, not a relaxation or reset of the 180-second pagination or 300-second checkpoint deadlines.

`GITHUB_DEADLINE_WORK_CHUNK_BYTES` is the maximum requested/read/hashed work unit for deadline-aware local regular-file and fixed `/proc` byte reads, incremental hashes and implementation-controlled incremental copy/validation loops. A file with an observed finite size is read in units of at most 65,536 bytes, with a final EOF/growth check and unchanged pre/post metadata equality. No file prefix is accepted if the file grows, shrinks, changes identity or crosses a deadline.

### 3.2 Cooperative bounded-native-call rule

Amendment 3's monotonic deadlines are acceptance deadlines. Network DNS-result consumption, address attempts, TCP, TLS, request writes and response reads remain nonblocking and use only the remaining time to the earliest applicable deadline. This amendment does not permit a blocking network call followed by a late timeout check.

Within the accepted local Render build/kernel boundary, a synchronous local or native primitive is conforming only under this closed model:

- call `time.monotonic_ns()` immediately before and immediately after the primitive;
- require both observations to be strictly earlier than every applicable absolute deadline; equality fails;
- bound every implementation-controlled byte read/hash/copy unit to at most 65,536 bytes;
- give a whole-value byte materialization, delimiter search/split/slice/join/copy, HTTP dechunk/framing copy, decoder, parser, fixed-pattern validator or canonicalizer only one complete response already bounded by the 67,108,864-byte raw-wire cap, or a transitive in-memory value derived solely from that capped response;
- perform deadline checks between implementation-controlled collection items, files, mappings and work chunks; and
- discard the primitive's result if its post-call observation is late, even when the primitive otherwise returned successfully.

The closed acceptance-bearing synchronous operations covered by this rule are:

- fixed-path `stat`, `lstat`, `fstat`, `open`, `read`, `islink` and `readlink`/`realpath` operations for already authorized local repository/runtime regular files, §6.1's exact interpreter install-scheme roots/members, §6.2's governed `tzdata` member and §6.3's one observed GitHub CA-bundle target;
- fixed-root `os.walk`/`scandir` iterator creation and one-entry advancement used to reconstruct the already frozen stdlib/dependency/native trees;
- `importlib.metadata.distribution`, `.version`, `.files` and `.locate_file` only for the exact normalized names in `EXPECTED_DEPENDENCY_VERSIONS`, with each result constrained to §6.1's exact canonical install-scheme roots and ownership law;
- iteration/snapshot of `sys.modules`, the exact same-process executable mappings, and the resulting finite module/file/mapping collections; fixed ordering, duplicate checks, path classification and canonicalization over those collections;
- reads of the already frozen `sys`, `sysconfig` paths, `platform`, byte-order, `float_info`/float-rounding, CPython cache-tag/version, libc, libpq-version and Render-service scalar facts; the retained `zoneinfo` module/class/TZPATH invariants in §6.2; CPython `ssl.get_default_verify_paths()` and the exact trust-object scalars in §6.3; exact `dlsym` resolution and mapping/file-offset validation for only `log` and `exp` in the already covered libm;
- fixed `/proc/self/{cmdline,exe,maps}` and `/proc/<returned-resolver-pid>/{exe,maps}` identity/mapping reads; `pidfd_open` and nonblocking pidfd/poll state observations;
- incremental digest operations; and
- pure CPU byte materialization, search/split/slice/join/copy, framing/dechunk copying, decoding, parsing, fixed-pattern validation, sorting, canonicalization and comparison on a capped response operand or on a finite frozen-local collection constructed only through the preceding checked operations; and one strict ASCII materialization plus `SSLContext.load_verify_locations(cadata=...)`/certificate-store validation over the exact stable-read CA-bundle bytes in §6.4.

Each directory iterator and each `next`/entry classification receives immediate monotonic pre/post checks; traversal remains inside the already approved canonical roots, checks between every entry, and cannot accept a partial enumeration as complete. Each metadata distribution/file and module/mapping item is likewise checked before and after use. None of these operations accepts an operator path, environment-selected distribution, new symbol, new process, network result or research/evidence value. A native whole-response `bytes(...)`, `find`/`split`/slice/join/dechunk copy, UTF-8/ASCII decoder or JSON/parser call, a sort/canonicalization of the finite frozen-local collections above, or §6.4's whole already-stable-read CA-bundle ASCII/trust-store operation need not be interruptible inside the call. Its input must come from the exact bounded or fixed local source above, and it must have immediate monotonic pre/post checks. This exception does not permit reading or hashing an entire unbounded local file in one call; local-file and CA-bundle acquisition remains chunked at 65,536 bytes. Returning after expiration is failure, never timely completion.

Closing/releasing an already-open local descriptor, pipe, pidfd, selector, iterator or socket, discarding an already-created in-memory buffer, and killing/reaping an already-created exact child are cleanup, not acceptance-bearing primitives. They must occur promptly on both success and failure but do not need a still-live acceptance deadline merely to release fixed resources. After failure or expiry, every result associated with that resource is irreversibly discarded before cleanup. Cleanup may use only the already-held resource handle or exact returned child PID; it may not open another path, read more acceptance data, create a child, perform network I/O, access a secret or produce an acceptance fact. A cleanup operation that does not return prevents further application work; it can never convert the failure into success. Section 5 supplies the exact resolver and local-Git subprocess quarantine sequences.

Exactly one resolver `Popen` is additionally authorized for each GitHub network request: Amendment 3's one resolver child with the exact absolute interpreter, isolated switches, fixed reviewed `-c` source, fixed file descriptors and exact secret-free environment. Its immediate pre-call observation must be timely. Its immediate post-call observation must be timely for success; if late, §5.1's quarantine is mandatory. No other resolver child, shell, executable, path, host, input, environment key or retry is authorized by this exception. The separately existing closed local-Git proof subprocess commands are not resolver children; each retains its exact arguments/environment, receives only the positive remaining checkpoint time, and follows §5.2. Neither allowance creates a generic subprocess permission.

This bounded model supersedes only an interpretation that every permitted local/native call must be asynchronously preemptible. It never permits acceptance after expiry, an unbounded operand, an unbounded caller-selected path, a network fallback, a background continuation or checking only after an unbounded network operation returns.

## 4. Page-local request deadlines and complete final-checkpoint order

### 4.1 Page-local 60-second semantics

Preserve Amendment 3's five exact durations and shared `time.monotonic_ns()` clock. Each HTTP request, including each page of a paginated collection and each fixed-ID request launched while classifying that collection, receives one new 60-second request-total absolute deadline beginning immediately before that request's resolver-child creation. It remains subordinate to the already active 180-second pagination deadline when applicable and the 300-second checkpoint deadline.

For a paginated page, that page's 60-second request-total deadline covers exactly:

1. its DNS resolution, resolver audit and timely normal-success reap/closure;
2. all address attempts, TCP connection and TLS verification;
3. request construction/transmission;
4. complete raw-wire receipt and clean EOF;
5. HTTP status/header/framing/trailer and content-encoding validation;
6. strict JSON decoding with duplicate-key rejection;
7. complete page-local schema/canonical-body/digest/envelope validation for every authority-candidate object on that page under Amendment 3's unchanged comment-classification rules; and
8. validation of that page's exact same-origin/same-path `rel=next` state.

The page deadline ends after step 8. It does not carry into the next page, a later fixed-ID request, or cross-page/cross-endpoint uniqueness, lifecycle, selection, ancestry, history or coherent-ref validation. The next page or fixed-ID endpoint gets its own 60-second request-total deadline, but no page or request resets or extends the original pagination or checkpoint deadline. A response validator may not issue a nested request under the response's request-total clock. Cross-page validation runs under the still-original pagination and checkpoint deadlines; each network request it initiates receives its own subordinate 60-second deadline.

For a non-paginated response, the same 60-second deadline covers complete response receipt plus all schema and semantic validation dependent only on that response. Cross-endpoint validation occurs under the checkpoint deadline after each contributing response has independently passed. Any page-local validation postponed past its own request deadline is nonconforming. Any collection-wide validation incorrectly charged to only the last page's 60-second clock is also nonconforming.

For the initial approval bootstrap only, the complete approval-comment collection and the fixed-ID ruleset requests used solely to classify its already page-validated Owner approval candidates form one closed first logical authority operation. Each ruleset GET remains a distinct HTTP endpoint and receives its own subordinate 60-second request deadline, but it is the sole exception to §6.4's prohibition on another endpoint before the uniquely current approval is known. During this closed operation no repository, ref, commit, pull-request, tree, blob, raw-file, receipt-history or other GitHub request may begin. Historical approval candidates retain their own authenticated payloads and need not carry the current process's CA observation; none can supply the runtime baseline unless its ruleset is the unique current ruleset and every other selection rule passes. Immediately after classification, validate the uniquely current approval's linked review and require its approved `github_tls_trust` to equal the local observation before any endpoint outside this closed operation or any database access. The classification responses may determine only the candidates' existing current/closed lifecycle state; they cannot alter, complete or replace an approval, review, provenance object or trust value.

The unchanged 10-second connect deadline and 20-second read-idle deadline remain request-local. The connect deadline is not renewed per address. Read-idle resets only on at least one newly delivered response octet. Completion observed exactly at any deadline fails. No timeout retry, pagination restart, cached-page reuse, background completion or partial-page acceptance is permitted.

### 4.2 Final checkpoint and runtime remeasurement

For the final post-cell checkpoint, use this exact order within one unchanged 300-second checkpoint context:

1. complete every required authenticated GitHub request, every page and fixed-ID request, and every response-local validation under §4.1;
2. complete every cross-page and cross-endpoint approval, history, merge, signature, ancestry, tree/blob/raw-byte, terminal-receipt, uniqueness and coherent-reference validation;
3. perform and fully validate the closing exact ruleset and `refs/heads/main` reads required by Amendment 3's no-ref-update window;
4. construct in memory a complete repository-checkpoint candidate, but do not return, accept or serialize it as final proof;
5. on the already open exact direct-host TLS connection and unchanged read-only snapshot, execute and fully validate exactly the second database-authority query required by V-1A §15.3, with no reconnect, new transaction, evidence read or other SQL;
6. perform §6.4's closing stable remeasurement and exact approved equality of the sole GitHub CA bundle, and recheck §6.2's empty `zoneinfo.TZPATH` and retained module/class invariants;
7. with the same checkpoint deadline still active, perform the complete final runtime remeasurement and equality checks required by Amendment 3 §2.3, including both governed `tzdata` members, using the 65,536-byte work chunks and bounded-native-call checks in §3.2; and
8. perform one final monotonic checkpoint check strictly before the deadline, then return the already validated checkpoint and proceed only to existing in-memory receipt construction/output.

Steps 5–8 may begin only after steps 1–4 have succeeded completely. Step 5 retains the exact V-1A database-authority query, transaction and direct-host TLS law. V-1A supplies no separate database-query timeout literal, and this amendment invents none: bracket the one synchronous execution with immediate monotonic observations and require both observations to be strictly before this same checkpoint acceptance deadline. A return at or after expiry is discarded and fails the final checkpoint. If the call does not return, no receipt, acceptance fact or further application work can occur; Amendment 3's existing protective job-cancellation, retained-seal and exact-recovery/consuming-negative rules govern, and a cancellation cannot create a timely result. Steps 6–7 receive a deadline-check callback tied to the same absolute checkpoint end; they may not use a fresh checkpoint, pagination or request deadline. A deadline crossed during a permitted local/native operation is detected by its immediate post-call check and fails the final checkpoint. No material GitHub, repository, source, ruleset, ref, database authority, provenance, GitHub-transport-trust or runtime validation may be deferred until after step 7. No protected value, receipt or PASS is accepted merely because an earlier part of the terminal sequence finished before the remainder expired.

This ordered sequence expressly replaces, only for final evaluated-receipt construction, both V-1A §15.3's statement that its second database-authority query runs “again immediately before evaluated receipt construction” and Amendment 3 §4's statement that no network operation intervenes between the final repository checkpoint and synchronous receipt construction. The exact step-5 query is the sole permitted intervening network operation. “Immediately before” for both inherited provisions now means membership in this one indivisible post-cell terminal-verification sequence: after truthful cells exist, no evidence read or protected calculation occurs; after step 5, no further database or other network operation occurs; after step 7, only the final monotonic check and existing in-memory receipt construction/output occur. The active no-ref-update window continues to prevent `main` movement throughout the sequence. This changes no query text, database fact, GitHub fact, calculation or receipt field.

A failure in this final checkpoint, including the database query or deadline exhaustion in steps 5–8, uses the existing POST-EVALUATION AUTHORITY INVALID route. Earlier checkpoints retain Amendment 3's exact stage-correct `BLOCKED` or PRE-CELL INVALID routing. This amendment adds no timeout reason or schema.

## 5. Resolver deadline quarantine and exact cleanup

### 5.1 Resolver child

Normal resolver success still requires the exact child output, live pidfd identity, two byte-identical mapping observations, approved executable/native subset, one `0x01` acknowledgement, exit status 0, synchronous reap and closure of every pipe/pidfd strictly before the shared connect deadline. Addresses are not usable until all of those facts have passed.

If any applicable deadline is reached or crossed before that success point, or any resolver validation fails, the parent irreversibly marks the resolver and request failed before performing cleanup. From that point:

- no address, output byte or child status can be accepted;
- the acknowledgement byte must not be written;
- the GitHub token must not be read, copied or formatted;
- no socket or network request may be created;
- no second resolver child, retry, alternate host/path/resolver or cached address may be used; and
- later cleanup success cannot clear the failure or create a timely observation.

The parent closes the acknowledgement writer without a byte, discards the resolver output/addresses without accepting a prefix, sends the hard-kill operation if the exact child is not already proven exited, synchronously reaps that exact returned PID, and closes the stdin/stdout pipes and pidfd. Deadline checks are not used to skip cleanup. Kill/reap/fd-close work that begins or completes after expiry is a quarantine-only exception to the acceptance deadline: it may do nothing except terminate and account for the already created child and release its fixed resources. It does not extend/reset a deadline, validate data, access a secret, emit output or permit success.

The same rule applies when the one authorized `Popen`, `pidfd_open`, `/proc` read or other §3.2 resolver-audit primitive returns only after the deadline. If `Popen` returned a child handle, that child is quarantined and reaped. If child creation raised or returned ambiguously and absence of a surviving child cannot be proved through the exact local process API, the request and job are failed and may not return to application authority work; control-plane termination/incident handling is required under existing Amendment 3 law. No replacement request or look is authorized.

The resolver routine may return to its caller only after either timely complete success or proved reap/closure on failure. If synchronous reap cannot be proved, the parent must not read the token, continue the checkpoint, emit a scorecard record or claim terminal application success. The job remains failed/incident-pending until the existing control plane proves termination. A child that exits concurrently with expiry is still discarded: the monotonic completion observation, not eventual exit, controls acceptance.

Network I/O outside the resolver remains nonblocking and uses only the earliest remaining request/connect/read-idle/pagination/checkpoint time. Once time has expired, no further network I/O is permitted. Local close/release of the already-open socket remains mandatory under §3.2's quarantine-only cleanup rule even though no acceptance time remains. This section creates no post-expiry network cleanup request, new process, thread, future or watchdog.

### 5.2 Existing local-Git proof subprocesses

Every Amendment 3-authorized local-Git proof subprocess receives the exact positive time remaining to the immutable checkpoint as its sole subprocess timeout. Its stdout/status is usable only when the command terminates, is synchronously reaped, and the immediate post-command monotonic observation is strictly before the checkpoint deadline. It receives no token, database URI, credential helper, caller stdin or network authority, and its exact command/environment/output validation remains unchanged.

If that timeout fires, the command returns only at or after expiry, or termination/output validation otherwise fails, the checkpoint is irreversibly failed and all stdout/status is discarded. The implementation must kill the exact child if still live, synchronously reap it and close its already-held pipes/descriptors. That kill/reap/close may complete after checkpoint expiry solely under §3.2's quarantine-only cleanup rule. It cannot make the command timely, expose a partial stdout prefix, launch another Git command, reset the checkpoint, continue repository authority work or authorize a retry. If reap cannot be proved, application authority work and scorecard output cannot continue; the job remains failed under existing incident/termination law.

## 6. Installed-data and GitHub-trust closure

### 6.1 Exact `RECORD` member resolution, including installed scripts

For each exact normalized distribution in `EXPECTED_DEPENDENCY_VERSIONS`, the dependency-tree input remains every non-cache installed regular member returned by that installed distribution's `importlib.metadata.files()`/`RECORD`, resolved only by that same `Distribution.locate_file`. The collector obtains the preferred-prefix `sysconfig` scheme once and strictly canonicalizes and deduplicates the exact roots named `purelib`, `platlib`, `scripts`, `data`, `include` and `platinclude`. Every root must be an absolute existing directory, its reported normalized path must equal its real path, and it must be from that same accepted interpreter/prefix. No environment, `PATH`, current-directory search or distribution metadata may add a root.

For one returned `PackagePath`, let `R` be its exact UTF-8 POSIX spelling. `R` must be nonempty and relative, contain no NUL, backslash, empty component or `.` component, and already equal its POSIX-normalized spelling. A `..` component is not rejected merely because it exists: all `..` components must form one leading run, with no later `..`, and `R` must equal the exact canonical POSIX `relpath` from that distribution's canonical `locate_file("")` base to the final canonical target. This is the sole lexical-escape exception. It covers an installed wheel member moved by the installer into an exact `sysconfig` scheme destination, including a direct console-script target under `scripts`; it does not authorize a caller-selected parent traversal.

Resolve the member through the owning distribution's `locate_file` and no other join. Normalize the located path without following a substitute; require that normalized path to equal its real path; require every traversed component below the selected scheme root and the final target to be non-symlink; and require the final target to be an existing regular file. The target must lie within at least one of the exact deduplicated scheme roots. When roots nest, classify it under the unique most-specific containing root; equal canonical roots were already deduplicated. A leading-`..` `R` whose target is outside all such roots, whose spelling differs from the exact canonical `relpath`, or whose target reaches an unapproved root fails. An absolute member, cancellable interior traversal, symlink, missing/non-regular target or ambiguous root likewise fails.

The unchanged dependency-tree logical key is the normalized distribution name, `/`, and the exact `R`. Leading `..` tokens in `R` remain literal authenticated `RECORD` key tokens in that logical identifier; the logical key is never reused as a filesystem path. Sort and hash the same exact `{path,size,sha256}` records as V-1A requires. Reject a duplicate logical key and reject any canonical physical target claimed by more than one `(distribution,R)` member, even when the two logical keys differ. A byte or metadata change retains the existing failure route. This section does not make an installed console script executable authority or put `scripts` on `sys.path`; it only makes a legitimate installed `RECORD` member part of the already required byte hash.

For this observable inherited closure, “unlisted dependency file” means a loaded third-party module `__spec__.origin`/`__file__`, or another distribution artifact explicitly enumerated by the frozen collector, that cannot map uniquely to the owning expected distribution's `files()`/`RECORD` membership. Every such enumerated artifact must map to its one owning `(distribution,R)` member and enter the same dependency tree. A loaded origin or required enumerated artifact outside that tree is rejected; shared `purelib`, `platlib` or another scheme-root residence is not ownership.

A physical file is not attributed to a distribution merely because it shares an install-scheme root. An otherwise inert filesystem entry that is not returned by an expected distribution's `files()`/`RECORD` and is not a loaded origin or another artifact explicitly enumerated below is outside this ownership predicate and is not rejected solely by root residence. Executable mappings remain governed by Amendment 3's separate complete `loaded_native_tree` and system-library rules. A mapping attributable to an expected distribution must also satisfy that distribution's membership only where incorporated dependency/native law already requires it; this clarification does not force every system/native mapping into a Python distribution `RECORD`.

This amendment does not claim to observe arbitrary direct file reads performed inside Python or a C extension, install a generic file-I/O/audit tracer, or prove absence of every physical extra beneath a shared root. If reviewed application code adds another dependency data input, that exact distribution-relative path must be added documentation-first to §6.2's closed governed set before use. `requirements.txt`, exact dependency versions and every artifact-component formula remain unchanged.

### 6.2 Forced `tzdata` source for New York civil time

The implementation contains this exact nonempty governed dependency-data mapping as a source literal:

```text
GOVERNED_DEPENDENCY_DATA_PATHS = {
    "tzdata": (
        "tzdata/zoneinfo/America/New_York",
        "tzdata/zoneinfo/UTC",
    ),
}
```

Both members must be returned by exact `tzdata==2025.3` `files()`/`RECORD`, map uniquely through §6.1 to canonical non-symlink regular files under the accepted dependency root, and be included in every initial and repeated `dependency_tree_sha256` measurement. Their logical paths, sizes and bytes are therefore covered by the existing dependency-tree digest; no new runtime-identity, seal or receipt key is added.

At the common reviewed module's first application-owned initialization, after capturing §2's installed exception-hook identity but before importing `tzdata`, `exchange_calendars`, pandas, NumPy or any other third-party/calendar module, and before constructing any `ZoneInfo`, require that `zoneinfo` and `tzdata` are absent from `sys.modules`. Import the standard-library `zoneinfo` only from the already covered stdlib. Retain the module object, `zoneinfo.__dict__["reset_tzpath"]`, `zoneinfo.__dict__["ZoneInfo"]`, and `zoneinfo.__dict__["ZoneInfo"].__dict__["clear_cache"]`; the last value is the class-dictionary descriptor, not a newly produced bound-method object. Then call exactly:

```text
zoneinfo.reset_tzpath(())
zoneinfo.ZoneInfo.clear_cache()
```

and require `zoneinfo.TZPATH == ()` immediately afterward. This ordering is common to probe, normal and recovery-child entry. Recovery-outer staging constructs no time-zone object. An earlier `zoneinfo`/`tzdata` module, earlier `ZoneInfo` object, populated earlier cache, nonempty path, substituted class/function/module, or failed reset is a startup defect before either runtime secret is read. No system `/usr/share/zoneinfo`, `TZPATH`, `PYTHONTZPATH`, environment path or caller-supplied TZif is accepted.

Every reviewed application construction of New York civil time uses the retained standard-library class with exactly `ZoneInfo("America/New_York")`; exchange-calendars 4.13.2's direct XNYS path also constructs exactly `ZoneInfo("UTC")` in `calendar_helpers.py`. Before the complete third-party closure is imported, after that import, before each reviewed construction, at each artifact measurement, before sealing and during final verification, require the retained module object and each exact class-dictionary/function object named above to remain identical and require `zoneinfo.TZPATH == ()`. Under that empty search path, both successful constructions must use the exact installed `tzdata==2025.3` package fallback; require their resulting `.key` values to equal `America/New_York` and `UTC` respectively. After the complete closure import, require the XNYS calendar class's retained time-zone object and `exchange_calendars.calendar_helpers.UTC` to be instances of the retained class with those exact keys. The complete `tzdata` distribution remains hashed, and both exact scientifically governed members above are additionally required by identity and ownership. Neither retained reset/cache-clear callable may be invoked again after the one initial ordered reset/clear to select a different source or result.

This freezes the source bytes used for the existing XNYS session/cutoff mathematics; it changes no civil-time formula, calendar, boundary or date. If the exact standard-library/fallback behavior, either governed member or the empty-path invariant cannot be proved on the accepted build, the probe or invocation fails under its existing stage route. It is not authority to use system TZif bytes, add a time-zone file or change `tzdata`.

### 6.3 One explicit GitHub TLS trust-bundle observation

Amendment 3 §2.4's exhaustive probe-read allowlist is expanded only by this subsection's one non-secret CPython-default CA-bundle observation. After common startup isolation and time-zone isolation, the secret-free same-build probe loads the complete permitted local module/native closure, then calls the frozen CPython `ssl.get_default_verify_paths()` while every prohibited certificate/environment override remains absent. That fixed scalar query and its implementation's existence metadata checks for the compiled default locations are permitted; no default directory is enumerated and no certificate bytes except the selected cafile are read. Require `.openssl_cafile_env == "SSL_CERT_FILE"`, require `.openssl_cafile` to be a nonempty absolute path, and require the effective `.cafile` to equal `.openssl_cafile` exactly. The probe records that reported `.cafile` path, fully resolves it to one canonical absolute target, opens that target with `O_NOFOLLOW`, requires an existing regular file, reads it with stable pre/post metadata in units of at most 65,536 bytes, and strictly ASCII-decodes the complete observed bytes as a PEM CA bundle. Intermediate components of the reported path may be symlinks only inside the already accepted Render/system-layer trust boundary; this is not a no-symlink claim, and every later fresh resolution must produce the identical canonical target and digest. Only after this observation and any stdlib/codec initialization it caused does the probe collect and measure the complete four-component artifact/runtime baseline. It does not read or accept `.capath` as a trust source.

The probe and common closure may import and artifact-cover the standard-library/native `ssl` implementation, but they must not call `ssl.create_default_context()`, `SSLContext.load_default_certs()`, `SSLContext.set_default_verify_paths()`, `SSLContext.load_verify_locations()` or any equivalent certificate-store loader. The probe observes/hashes bytes only; it creates no TLS context, parses no certificates into a store, performs no resolver/network operation and reads no second system trust path. The evidence-capable path in §6.4 is the sole certificate-store load authorized here.

The exact object is:

```text
github_tls_trust = {
    "source": "ssl.get_default_verify_paths().cafile",
    "reported_cafile_path": exact absolute path returned by CPython,
    "canonical_cafile_path": exact fully resolved absolute regular-file path,
    "cafile_size_bytes": exact positive integer byte length,
    "cafile_sha256": SHA-256 of those exact bytes,
}
```

Add `github_tls_trust` as exactly one additional key to the successful `ATOM-V1B-RUNTIME-PROBE-1` object in Amendment 3 §2.4 and to `P`, the exact `ATOM-V1B-RUNTIME-PROVENANCE-1` object in §§2.5–2.6. The value in `P` is byte-for-byte the probe observation; the successful probe object's canonical hash and `provenance_sha256` bind it. `A` retains its Amendment 3 key set and contains the extended `P` under `payload.provenance`; therefore `approval_payload_sha256`, review binding and Owner approval bind this object without a redundant top-level field. Every exact-schema validator and canonical fixture is updated accordingly. The non-secret reported/canonical CA paths do enter that public payload; no private acceptance-packet locator, secret, certificate bytes or token digest does.

The Owner and independent operational reviewer inspect the probe's complete stable-read path/size/digest evidence together with the same-build provider/system-layer/default-PKI evidence before posting/accepting `A` and before any evidence-capable job is created. This requirement authorizes no shell, byte download, second probe output or other bundle-retrieval path; the approved probe observation and retained control-plane evidence are the review inputs. The object is an operational transport-trust record, not a fifth runtime-artifact component and not a receipt field. A different compiled/effective path, target, size, digest, build or unstable file blocks approval.

### 6.4 Bootstrap trust boundary and repeated enforcement

The first evidence-capable process cannot use a GitHub response to cryptographically bootstrap the CA bundle that authenticates that same response. This amendment does not claim otherwise. For the first approval-comment collection, the exact same-build bundle externally accepted under §6.3 is the designated GitHub TLS bootstrap trust root inside Amendment 3's already explicit trust in the Owner-approved Render native build/kernel/control-plane boundary. The later authenticated approval comparison is continuity/correlation proof, not the origin of that first TLS trust. This does not claim remote attestation against a compromised Render system layer or CA program. A stronger embedded pin or repository CA artifact requires a separate documentation-first decision.

The evidence-capable process uses this exact order once per process: common startup/zone isolation; complete permitted third-party/native closure load; exact stable CA-bundle observation through a fresh `ssl.get_default_verify_paths()` result and freshly resolved reported path; complete local four-component/runtime candidate measurement after every lazy effect of that observation; construction of exactly one `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` loaded only by `load_verify_locations(cadata=exact_ascii_pem)` from those already verified bytes; then an immediate complete artifact/runtime remeasurement that must equal the pre-context candidate exactly. Only after that equality may it create the resolver, read the PAT or open the first GitHub socket. It calls neither `ssl.create_default_context()` nor `load_default_certs()`/`set_default_verify_paths()`, supplies no `cafile`, `capath` or second `cadata`, and does not inherit another context/store. The sole context has `verify_mode=CERT_REQUIRED`, `check_hostname=True`, minimum TLS 1.2 and the exact HTTP/1.1 ALPN rule; every TLS wrap uses `server_hostname="api.github.com"`. A non-ASCII/invalid/empty bundle, zero accepted CA certificates, property mismatch, newly loaded/changed artifact or other context defect fails before token transmission.

The approval-comment collection remains the first logical GitHub authority operation. For the initial bootstrap, that closed operation includes only §4.1's fixed-ID ruleset requests needed to classify the already page-validated approval candidates; those distinct HTTP endpoints are not permission to fetch any other authority fact before selection. After the unique current Owner approval and its linked review are completely validated, the process requires its locally observed `github_tls_trust` object to equal the extended approved `P` exactly before any repository, ref or other GitHub endpoint outside that closed operation and before any database access. A historical closed candidate's different authenticated trust observation is not a replacement baseline and does not by itself invalidate the uniquely current approval; it remains governed by the unchanged lifecycle and review validation. Missing/duplicate/edited approval, a mismatch on the uniquely current approval or an inability to complete the closed approval-classification operation fails under the existing pre-evidence route. The initial context is already rooted by the external system-layer acceptance above; the fetched digest does not retroactively authenticate it. On later pre-seal, final and recovery checkpoints, the retained approved object is available before the first request: call `ssl.get_default_verify_paths()` again, re-require the exact `.openssl_cafile_env`/`.openssl_cafile`/`.cafile` invariants above, and require its newly reported `.cafile` path, freshly resolved canonical target, stable size and digest to equal the approved object; use only the same immutable already measured context. No second context, store reload, retained-path-only shortcut or context mutation is permitted.

Within every checkpoint, after the last GitHub response and all response/cross-endpoint validation, call `ssl.get_default_verify_paths()` again, re-require the exact compiled/effective-default invariants above, validate its newly reported `.cafile`, freshly resolve that reported path, remeasure the canonical target's stable bytes, size and digest, and require the complete object to equal the approved observation before that checkpoint can pass. In the final checkpoint this closing trust-bundle equality is part of §4.2 after construction of the unaccepted repository candidate and before final runtime remeasurement. All deadline-bearing reads, hashes, ASCII materialization and the one native trust-store load use §§3–4. A changed reported path, symlink target, file, metadata, bundle or context is never repaired by retaining an earlier canonical pathname, re-reading a newer default or choosing a new baseline. No GitHub request follows a mismatch.

This GitHub system-layer trust exception is separate from Supabase database TLS. The exact repository-pinned 1,367-byte Supabase CA, direct hostname and `verify-full` law remain unchanged, and the GitHub bundle cannot be used for PostgreSQL. Conversely, the database CA is not silently repurposed for GitHub.

## 7. Repository identity, implementation, tests and acceptance

### 7.1 Amendment 3A adoption identity and history boundary

This amendment's GitHub PR number, Owner merge SHA, merge timestamp, Git blob and raw-file SHA-256 do not exist as accepted literals until the one-file documentation PR is Owner-merged. No draft head, proposed PR number, locally computed commit, placeholder, branch tip or model prediction may supply them. After that merge and before the implementation PR's final head is reviewed, the implementation must freeze exact source literals for:

```text
amendment_3a_decision_id = "ATOM-V1A-AMENDMENT-3A-BOOTSTRAP-DEADLINE-CLOSURE-1"
amendment_3a_path        = "docs/v-1a-amendment-3a-bootstrap-deadline-closure.md"
amendment_3a_pr_number   = actual Owner-merged PR number
amendment_3a_merge_sha   = actual 40-lowercase-hex Owner merge SHA
amendment_3a_merged_at   = actual authenticated GitHub merge timestamp
amendment_3a_git_blob    = actual 40-lowercase-hex Git blob at that merge
amendment_3a_sha256      = SHA-256 of the exact merged raw file bytes
```

At every initial, pre-seal, final and recovery repository checkpoint, authenticate the exact repository and PR; Owner author/merger identity; merged state, merge commit, merge time and passing GitHub signature verification; exact one-file first-parent diff; path and mode `100644`; decision ID; blob identity and raw bytes; ancestry after the existing Amendment 3 merge and before execution `E`; and byte-identical presence of this document at `E`. A signature or ancestry alone is insufficient. A changed/missing document, wrong PR/path/mode/author/merger, extra diff path, guessed literal or unavailable proof fails under the existing stage route. This adds no identity, seal or receipt field.

Amendment 3's post-amendment first-parent history classifier keeps its original lower boundary and gains exactly one ordered documentation exception. After separately authenticating this one Amendment 3A documentation merge, enumerate and classify the complete first-parent interval:

```text
acc004ff074018bf36dfb40aa651497ef5b39b1e..E
```

That interval must contain exactly one conforming Amendment 3A one-file documentation merge, followed in first-parent order by exactly one conforming V-1B implementation merge, and otherwise only conforming receipt-only merges in their already allowed positions. The authenticated Amendment 3A merge is the sole documentation exception and is classified explicitly rather than as an implementation or receipt merge. No commit between Amendment 3 and Amendment 3A is skipped; any other documentation, code or unrelated merge fails the classifier. The unique implementation merge must descend from the actual Amendment 3A merge; an implementation head based only on Amendment 3 must be updated before final review.

The actual post-merge literals, document bytes and revised interval require independent verification on the implementation PR's exact final head. Until the documentation merge exists and those facts are frozen, the implementation cannot pass final acceptance or be deployed.

### 7.2 Implementation surface, tests and gates

The implementation delta authorized by this amendment is limited to:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

The broader Amendment 3 implementation allowlist remains controlling, but this amendment itself authorizes no change to `requirements.txt`, `certs/supabase-prod-ca-2021.crt`, a migration, another module or any operational/configuration file. It may be incorporated into the required separate V-1B implementation PR—whether that PR is already open or is opened later—only after this documentation amendment is Owner-merged; any changed implementation head requires fresh exact-head review and checks.

Retain every applicable V-1A/TLS/2A/Amendment 3 test. Add focused synthetic tests proving at least:

1. `H` is exactly 60 ASCII bytes and is the first source bytes exactly once in probe, normal, recovery outer and decoded recovery child; both hooks are the same non-writing lambda and remain unchanged through entry; normal/recovery child length, hex length and SHA-256 equal §2.1; recovery rehexing is exact; all other command bytes/options remain unchanged; and representative bootstrap `OSError`, `KeyError`, failed `stat`/`sysconfig` lookup and explicit predicate refusal produce nonzero exit with empty stdout/stderr after `H` executes.
2. The raw-wire and work-chunk literals equal 67,108,864 and 65,536; exact-cap plus timely clean EOF passes; the next octet, partial EOF or deadline equality discards the whole response; local files are read/hashed in at-most-65,536-byte units with metadata/growth checks; immediate-pre/post-checked whole-response `bytes`, slice, join, copy, framing, dechunk, decode and parse operations accept only cap-bounded/transitively bounded operands; a late successful return is rejected; and no blocking network operation is introduced.
3. Every page receives a distinct 60-second request-total deadline; its complete page-local schema/digest/link validation occurs inside that deadline; page 2 does not inherit page 1's request deadline; neither page resets 180 or 300 seconds; fixed-ID classification requests each receive a new subordinate 60-second deadline; collection-wide validation uses the original pagination/checkpoint clocks rather than the last page's clock; and equality at any boundary fails without retry. Test that only those fixed-ID ruleset requests may occur inside the initial closed approval-classification operation, that no repository/ref/other endpoint or database access begins before unique-current selection and trust correlation, and that a historical closed candidate cannot replace the selected trust baseline.
4. The final event order is complete GitHub/page/cross-endpoint/source validation, closing ruleset/ref validation, unaccepted repository-checkpoint candidate, the exact existing second database-authority query on the already open snapshot, closing approved-CA/zone invariant validation, deadline-aware runtime remeasurement, final deadline check, then existing receipt construction. Test that this is one indivisible post-cell sequence; the database query is the sole network operation after the closing ref, no evidence/protected calculation follows it, no network operation follows it, and no material validation follows runtime remeasurement. The query has immediate monotonic pre/post checks under the unchanged checkpoint acceptance deadline; a simulated late return is rejected, and a nonreturn cannot emit a receipt or continue application work. Do not assert or invent an inherited database timeout. Runtime remeasurement cannot start early, reset the checkpoint or escape its deadline. Its fixed-root directory iteration, exact-distribution metadata, module/mapping traversal and sorting, platform/libpq/float/scalar reads, `dlsym`/offset work, local-file chunks and finite frozen-local-object operations all receive the §3.2 checks; an expiry during the database query or any permitted primitive routes to POST-EVALUATION AUTHORITY INVALID.
5. Resolver `Popen`, pidfd and fixed `/proc` operations have immediate monotonic pre/post checks. Test expiry before output, during either map read, before acknowledgement, during child exit/reap and on a late-returning `Popen`; irreversible quarantine writes no acknowledgement, accesses no token, opens no network socket, discards all addresses, creates no second child, retries nothing and proves kill/reap/fd closure. Separately test each already authorized local-Git subprocess timeout/late return: discard stdout/status, kill and reap the exact child, close held resources, perform no later authority work and never retry. Reap/close/release after expiry is cleanup only, requires no fictitious remaining deadline, and never changes failure to success or exposes a result. An unresolved child/resource prevents return to application work.
6. Every non-cache regular member returned by each exact distribution's `files()`/`RECORD` is canonically resolved and hashed. Test normal in-root members and leading-`..` members whose exact canonical `relpath` lands in each permitted install-scheme class, including generated direct `scripts` members. Reject absolute/empty/dot/cancellable/interior traversal, an escape outside all exact scheme roots, a noncanonical spelling, symlink component, non-regular/missing target, duplicate logical member and shared physical target. Prove the logical key retains the exact `RECORD` spelling but is never opened as a path. Test loaded-origin/explicit-artifact outside-tree rejection, separate loaded-native mapping treatment and an inert unrelated scheme-root file that is neither attributed nor rejected solely by residence.
7. The common entry rejects any earlier `zoneinfo`/`tzdata` module or object state, performs the exact empty-path reset/cache-clear before third-party/calendar import, retains the module, reset function, class and `ZoneInfo.__dict__["clear_cache"]` descriptor identities without comparing transient bound-method objects, and requires `TZPATH == ()` through final verification. The governed mapping is exactly the nonempty §6.2 literal; both `tzdata==2025.3` members (`America/New_York` and `UTC`) have unique `RECORD` ownership and enter every dependency hash; the retained XNYS/calendar-helper objects have the exact class and keys; and a system TZif, environment path, prior cache, changed path, wrong key or unowned/missing/changed member fails without changing the existing date/session math.
8. The probe-read allowlist grows by only the one stable CPython-default cafile observation and the probe never constructs/loads an SSL context. Prove the probe order is closure load, fresh default-cafile query/resolution/observation, then artifact plan/measurement. Its exact `github_tls_trust` key, canonical hash and identical `P` value validate, while `A` retains its key set and binds the extended `P`. Test absent trust overrides; exact `.openssl_cafile_env == "SSL_CERT_FILE"`, nonempty absolute `.openssl_cafile` and `.cafile == .openssl_cafile`; reported/canonical-target/regular-file/size/digest validation; 65,536-byte reads; admitted system-layer intermediate symlinks with exact repeated resolution; retargeting or mutation rejection; the reviewable stable-read/control-plane evidence boundary without an invented byte-retrieval path; and the explicit external bootstrap-trust boundary. In an evidence process, prove closure then default-cafile observation precede the artifact baseline, the one cadata-only context follows it, and immediate complete artifact equality precedes resolver/token access; hostname/CERT_REQUIRED/TLS/ALPN properties are exact; no default/capath/second context is used; the initial closed approval-classification operation permits only its required fixed-ID ruleset requests, selected-current trust correlation precedes every endpoint outside that operation and database access, and a historical trust observation is never selected as the process baseline; and approved pre/closing checks at initial, pre-seal, final and recovery each re-call `get_default_verify_paths()` and freshly re-resolve/re-hash the reported cafile. A mismatch follows the existing stage route and never selects a new baseline.
9. After the documentation merge, freeze and authenticate the actual Amendment 3A PR number, Owner merge SHA/time, one-file path/mode/diff, signature, decision ID, Git blob, raw bytes/SHA-256 and ancestry. Test missing/guessed/wrong values and changed execution-tree bytes; require the implementation merge to descend from 3A; enumerate the complete first-parent interval from exact Amendment 3 merge `acc004ff074018bf36dfb40aa651497ef5b39b1e` through `E`; require exactly one ordered 3A documentation merge followed by exactly one implementation merge; and prove that no intervening or other documentation/code/unrelated merge escapes classification while existing receipt-only positions remain unchanged.

The local focused command remains:

```text
python -m pytest -q tests/test_volatility_scorecard.py
```

It uses synthetic credentials/evidence only and proves no live Render, GitHub-token, database, evidence or protected-result acceptance. The repository's actual required CI checks remain mandatory and unchanged.

Both this one-file documentation PR and the final V-1B implementation PR require independent review on their exact final heads, all actual required checks green, zero unresolved P1/P2/material findings and Owner-authorized merge. Earlier-head review, the merged Amendment 3 review, local tests, document arithmetic or a generic green badge cannot satisfy either new final-head gate. The documentation amendment must merge first. Codex then applies the exact implementation delta. Owner alone supplies merge authority; Codex may perform a mechanical GitHub merge only under an explicit current Owner instruction after every gate is proved, never autonomously or from an earlier blanket instruction. Operational setup remains forbidden until the implementation's separate gate and every unchanged Amendment 3 acceptance condition have passed.

## 8. Explicit preservation and re-entry

Preserve all V-1A, TLS Amendment 1, Amendment 2A and Amendment 3 law except the exact source transformation, deadline-work semantics, final-checkpoint/final-database-authority ordering, installed-member ownership, forced time-zone source and GitHub transport-trust/probe-provenance extension above. The deadline durations remain 10/20/60/180/300 seconds. The resolver still has one child and the same address/output protocol. The no-ref-update window, credential and incident lifecycle, backend/restart proof, IPv4 cost gate, actual-seal capacity rule, one-off containment, nine commands, two scorecard CLI options, HOLD/WAIT/usage behavior, startup isolation, four-component runtime identity, direct-host database TLS, database-authority query/facts, one-snapshot scan, seal-before-results rule, first-complete-receipt duty and normal/rollback cleanup remain exact. Only the relative terminal placement of the second database-authority query is replaced by §4.2. Only the successful probe and `P` gain §6.3's one exact non-secret object; `A` binds that extended `P` without a new key, and no research identity, seal or receipt schema changes.

The re-entry order is:

```text
this one-file Amendment 3A documentation PR
→ independent exact-final-head review + required-green checks + zero material findings
→ Owner merge
→ apply the narrow 3A delta to the separate V-1B implementation PR
→ full inherited + focused tests and independent exact-final-head implementation review
→ required-green checks + zero material findings
→ Owner implementation merge
→ unchanged Amendment 3 operational prerequisites plus the secret-free governed-time/trust probe and Owner-controlled setup
→ exact transformed one-off invocation or recovery under unchanged research law
```

No repository or operational action is asserted by this document. No actual CPython-default CA path/target/size/digest, installed wheel path, authoritative Render command-capacity value, live runtime result, live deadline behavior, provider acceptance, credential state, database state, evidence count, seal or receipt is claimed. If implementation or platform behavior cannot satisfy these exact boundaries, stop for another documentation-first decision; do not weaken a command, bound, trust/time source, deadline, cleanup obligation or proof at action time.

---

## Non-normative source and observation boundary

The implementation review should use the following primary specifications for mechanism semantics only:

- Python 3.14 `zoneinfo`, including data-source order, `reset_tzpath()` and `ZoneInfo.clear_cache()`: <https://docs.python.org/3.14/library/zoneinfo.html>
- Python 3.14 `ssl`, including `get_default_verify_paths()`, `SSLContext`, hostname checking and `load_verify_locations(cadata=...)`: <https://docs.python.org/3.14/library/ssl.html>
- Python 3.14 `importlib.metadata` distribution-file and `PackagePath.locate()` behavior: <https://docs.python.org/3.14/library/importlib.metadata.html>
- Python 3.14 `sysconfig` install-scheme paths: <https://docs.python.org/3.14/library/sysconfig.html>
- PyPA installed-project `RECORD` path semantics: <https://packaging.python.org/en/latest/specifications/recording-installed-packages/>
- `exchange-calendars` 4.13.2 XNYS source, including its `ZoneInfo("America/New_York")` literal: <https://github.com/gerrymanoim/exchange_calendars/blob/4.13.2/exchange_calendars/exchange_calendar_xnys.py>
- `exchange-calendars` 4.13.2 calendar helpers, including the XNYS path's `ZoneInfo("UTC")` literal: <https://github.com/gerrymanoim/exchange_calendars/blob/4.13.2/exchange_calendars/calendar_helpers.py>

These references do not supply an accepted build path, file list, CA digest or runtime result. In particular, no exact Python 3.14 Render build or installed target-wheel `RECORD` was executed during this documentation draft. The normative rule deliberately validates the actual same-build metadata and canonical install-scheme target rather than freezing a console-script filename inferred from another environment. Vendor or package changes cannot silently alter this amendment.
