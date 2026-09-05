# V-1A Amendment 1 — Exact TLS Trust Anchor and Parallel V-1B Prerequisite

**Decision ID:** `ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Proposed text with no authority before Owner-approved merge. This amendment becomes controlling at that merge; V-1B implementation still waits for the separate Owner-merged Amendment 2A.  
**Author:** ChatGPT Pro, ATOM architecture and freeze authority  
**Date:** 2026-09-05  
**Contract path:** `docs/v-1a-amendment-1-tls-trust-anchor.md`  
**Inspected base:** `main` at `ac85cc9e99ccc499789f3ef79b186768d99fb0d6`  
**Implementation owner:** Codex, one owner and one separate implementation PR  
**Merge and operational authority:** Owner; no merge or operational action is delegated by this amendment.

## 1. Objective and exact amendment scope

Remove the two prerequisite ambiguities without changing the study: identify the one certificate V-1B may trust, and expressly permit its isolated implementation alongside active SIM-5.

This is the exact separate TLS decision required by Amendment 2A §6.3. It amends `docs/v-1a-volatility-first-freeze.md` (`ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`) only at §§12.1–12.2, 13.3, 15.1, 15.3, 16.2, and 22–26 as expressly specified below. Section 5 makes the narrow parallel-work exception to `FREEZE.md` permanent law 10 and the SIM-5 active-phase restriction in `AGENTS.md`; neither file nor the active pointer is edited.

The companion is `docs/v-1a-amendment-2a-tiered-readiness-boundaries.md`, decision `ATOM-V1A-AMENDMENT-2A-TIERED-READINESS-1`, proposed in PR #321. Its reviewed source for this amendment is head `cdffd91918a88684c9fcf8531abbc838fdc9e887`, document SHA-256 `7f4b45591187ce8ddf89565520478df861d5c3a302a7361c2fea00d566b5603d`. This reference does not approve or merge #321.

No mathematics, market-data source, evidence population, readiness predicate, manifest, threshold, inference, production or SIM behavior changes. The sole additional implementation artifact is the public CA certificate specified in §2; it is neither a credential nor market evidence.

## 2. Exact trust anchor

Replace every V-1A requirement for `sslrootcert=system` with exactly:

```text
sslrootcert=certs/supabase-prod-ca-2021.crt
```

The complete accepted normalized TLS/authentication tuple is:

```text
sslmode      = verify-full
sslrootcert  = certs/supabase-prod-ca-2021.crt
sslcertmode  = disable
require_auth = scram-sha-256
gssencmode   = disable
```

The one allowed file has these fixed identities:

```text
repository_path   = certs/supabase-prod-ca-2021.crt
file_size_bytes   = 1367
file_sha256       = 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7
git_blob_sha1     = 3d693669b23c340c57a3457bdc8b6fefe1806cc5
certificate_cn    = Supabase Root 2021 CA
certificate_der_sha256 = 807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa
not_before_utc    = 2021-04-28T10:56:53Z
not_after_utc     = 2031-04-26T10:56:53Z
```

`file_sha256` hashes the entire original PEM file, including its final LF, with no normalization. It is not the DER certificate fingerprint. The exact public PEM bytes appear in Appendix A. Codex must add them unchanged in the later implementation PR, not fetch a certificate at runtime.

Primary provenance: Supabase's official `supabase/cli` repository, commit `d6a376c82436c908efa142f4c17977f477c264b8`, path `apps/cli-go/internal/gen/types/templates/prod-ca-2021.crt`. Its Git blob identity was matched to a local reconstruction and the PEM and DER digests were independently computed on 2026-09-05. This proves the selected artifact, not a successful connection to the ATOM database.

Before any database connection, establish the repository root belonging to the verified execution revision. The process working directory must already be that root; do not silently change it or resolve the certificate relative to an arbitrary caller directory. `certs` must be a real directory and the certificate a tracked, regular, non-symlink Git file with mode `100644`. Reject any symlink component below that root, path escape, missing/unreadable file, directory/device, extra certificate, different bytes, or mismatch between the worktree file and that revision's Git blob. Verify the exact size and SHA-256 above before passing the untouched URI to libpq. The bytes must remain unchanged throughout the connection and run.

No system-root, OS-bundle, home-directory root, alternate path, environment-selected root, URL, additional CA, or weaker SSL mode is permitted. No runtime download, certificate installation into a system trust store, automatic renewal, or fallback is authorized. Certificate rotation needs its own documentation-first amendment and cannot restore a consumed confirmatory look.

## 3. DSN, proof, and failure behavior

V-1A §15.1's raw five-key query set, canonical-name checks, exactly-once decoding, independent parse of the untouched original URI, and post-connect raw `PQconninfo` parity remain unchanged. Both parsers and `PQconninfo` must report the exact relative `sslrootcert` value in §2. Do not rewrite it to an absolute URI value or override it through connect keyword arguments. All existing ambient, duplicate, password-file, client-certificate, startup-option, pooler, and alternate-identity rejections remain mandatory.

The target remains exclusively `db.afyiydxbjgzaiswnbcyj.supabase.co:5432`, database `postgres`, login `atom_e1_scorecard_reader`, supplied through the existing `ATOM_E1_SCORECARD_READONLY_DATABASE_URL`. `verify-full` must validate the server chain under the pinned CA and the exact hostname. SCRAM, disabled client certificates/GSS, post-connect `pg_stat_ssl.ssl = true`, the read-only `REPEATABLE READ` snapshot, all six-table/catalog/proof-function checks, and the frozen runtime identity remain mandatory. Trusting a supplied server certificate without CA and hostname verification is forbidden.

The exact §13.3 passing `authority_proof` changes in only two ways:

```text
dsn_sslrootcert       string = "certs/supabase-prod-ca-2021.crt"
sslrootcert_sha256    string = "700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7"
```

The first replaces the existing `system` value; the second is the only added key. `dsn_tls_fallbacks_absent = true` now also requires every §2 trust-file check. Recheck the path, tracked blob, size, and file hash after connection before evidence reads and during the final §15.3 authority recheck. Passing initial and final authority objects must still agree exactly.

This same amended proof shape applies wherever the base or Amendment 2A already embeds a complete passing authority object: the seal's `initial_authority_proof`, evaluated `authority_proof`, and applicable negative-receipt authority fields. Recompute their existing canonical hashes; do not add receipt top-level keys, change schema-version literals, change readiness/run-identity key sets, or substitute a new seal. Amendment 2A's existing `tls_amendment_merge_sha` binding identifies this decision and therefore its pinned anchor.

Failure routing is exactly Amendment 2A §8.6, not a new TLS-specific status or reason code. On a new-seal invocation, a pre-evidence authority failure is BLOCKED; a failure after evidence reading but before sealing is null-seal PRE-CELL INVALID. Once a valid recovery seal is accepted, any TLS failure, even before connection, is consuming PRE-CELL INVALID with the original sealed identity and initial authority proof. After truthful evaluated cells exist, a failed final trust/authority recheck is POST-EVALUATION AUTHORITY INVALID. No failure authorizes a replacement look or serializes partial protected statistics.

For later Owner-controlled V-1B setup only, §16.2 additionally permits replacing solely the `sslrootcert` query value in that existing reader environment variable with §2's value. Preserve the username, password, host, port, database, and other frozen query values; this is not credential creation or rotation. Do not log the URI or password. An otherwise nonconforming credential remains blocked, not silently repaired. No environment change occurs in this documentation PR. Any already-authorized direct-psql migration preflight that inherits §15.1 inherits this same trust rule, with only its existing `postgres` login exception; migration authority is not expanded.

## 4. Minimal implementation surface and tests

The later V-1B implementation surface is the existing V-1A §12.1 / Amendment 2A §10.1 surface plus exactly one public trust artifact:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
requirements.txt
certs/supabase-prod-ca-2021.crt
```

`requirements.txt` retains its exact existing calendar-only dependency-closure restriction. `migrations/033_authorize_v1_volatility_scorecard_reader.sql` remains conditional on the unchanged prior privilege proof; no ordinal, grant, role, or execution change is made. No other file is authorized.

For reconciliation with Amendment 2A §§10.1 and 10.3, its inherited exhaustive surface is read with this one expressly authorized TLS artifact addition, including the implementation first-parent-diff audit and rollback. This is the complete file-surface exception; the later adoption of 2A does not erase the separately required TLS prerequisite. The amendment and eight evidence files remain byte-unchanged, and rollback still preserves every freeze, evidence file, retained seal, and receipt.

Use only the already-authorized scorecard module and test module for the added validation. In addition to every existing V-1A/2A test, prove: exact artifact bytes and tracked path; wrong working directory, symlink, path escape, missing/changed file and extra CA rejection before connection; exact dual-parser and `PQconninfo` parity; no system/ambient/argument fallback; certificate-chain and hostname failure refusing evidence reads; the one-key proof extension in every applicable schema/seal; mid-run trust-file change failing the final authority check; and unchanged 2A new-seal/recovery failure routing. Synthetic tests do not authorize production credentials or a live research run. No new dependency, generic TLS framework, service, or unrelated refactor is authorized.

## 5. Parallel implementation, not parallel authority expansion

After both this amendment and Amendment 2A are Owner-merged in §6 order, Codex may immediately implement, test, commit, and prepare the separate V-1B implementation PR while SIM-5 continues under its own freeze. SIM-5 completion, market-open proof, receipt publication, or active-pointer transfer is not a prerequisite to that repository work. V-1B does not take or replace the SIM-5 active-phase pointer.

This expressly authorizes only two separately scoped jobs, not combined phases in one PR, competing owners of one job, or scaffolding of SIM-6, V-1C, V-2, or another phase. No SIM file, worker, credential, database, source, entry, resolution, horizon-release rule, or acceptance gate changes. SIM-5 retains its existing isolated runtime and database; V-1B's only eventual runtime remains `atom-h2d3-benchmark` (`srv-daa7thgae00c73a2lmn0`) and its existing production evidence reader. There is no shared execution loop or cross-consumption of SIM evidence.

Separate authorized SIM-5 work may continue only without changing V-1 definitions, immutable evidence, or its bound execution environment. Keep diffs separate and preserve intervening main commits. This exception does not permit ingestion interruption, evidence reduction, shared locks, resuming the suspended benchmark worker, migration application, environment mutation, deployment, protected scoring, or receipt publication merely because implementation is now permitted. Those actions retain their distinct frozen gates and Owner authority.

## 6. Adoption and unchanged evidence law

The required order is:

1. Independently review this exact final documentation head, resolve or explicitly disposition every material P1/P2 finding, obtain every required green check and zero unresolved material threads, then Owner merge this amendment.
2. Independently review and Owner merge Amendment 2A with its eight complete, hash-verified evidence artifacts through its unchanged gates.
3. Codex prepares the separate V-1B implementation PR on main containing both decisions. Independent exact-head review, all required green checks, zero unresolved material findings, and Owner merge are required before any V-1B execution.
4. Any later Owner-authorized migration/setup/run and separate immutable receipt-publication PR follow V-1A and Amendment 2A unchanged. No run, deployment, or infrastructure action is performed or delegated here.

Amendment 2A alone continues to define `T_amend` from its verified Owner-merge event, earliest prospective boundaries, the fixed four-cell early manifest and eight deferred singleton manifests, all six readiness minima, causal scale reconstruction, lineage selection/reset rules, and global 12-cell multiplicity. This TLS amendment's merge time, implementation time, certificate acquisition, or SIM-5 progress cannot reset that anchor or supply a new boundary.

Every formula, numerical operation/order, benchmark, bootstrap/RNG rule, threshold, classification, correction ruling, eight-artifact binding, seal-before-protected-results rule, one-look limit, exact recovery rule, consuming-negative rule, nonselective continuation rule, and publication gate remains unchanged. `range_status`, `threshold_status`, planning rates, and latest-state substitutes remain outside V-1A readiness. No protected result was computed for this amendment.

The documentation PR for this decision adds exactly `docs/v-1a-amendment-1-tls-trust-anchor.md` and nothing else. It does not add the runtime certificate file, implementation, tests, migrations, receipts, or pointer edits. The final PR record must report the reviewed head, exhaustive diff, document hash, actual named check conclusions, independent-review state, and unresolved material-thread count. Unfinished review/checks are pending, never an asserted PASS. Owner review and merge remain required.

All law outside the explicit TLS and parallel-implementation exceptions remains controlling. Ambiguity is a stop, not permission to widen the implementation. An unavailable or incorrect trust anchor must never be remedied by weakening TLS or changing evidence rules.

## Appendix A. Exact public PEM artifact

The file consists of the following bytes between the fences, with LF line endings and exactly one final LF. The fences are not file content.

```pem
-----BEGIN CERTIFICATE-----
MIIDxDCCAqygAwIBAgIUbLxMod62P2ktCiAkxnKJwtE9VPYwDQYJKoZIhvcNAQEL
BQAwazELMAkGA1UEBhMCVVMxEDAOBgNVBAgMB0RlbHdhcmUxEzARBgNVBAcMCk5l
dyBDYXN0bGUxFTATBgNVBAoMDFN1cGFiYXNlIEluYzEeMBwGA1UEAwwVU3VwYWJh
c2UgUm9vdCAyMDIxIENBMB4XDTIxMDQyODEwNTY1M1oXDTMxMDQyNjEwNTY1M1ow
azELMAkGA1UEBhMCVVMxEDAOBgNVBAgMB0RlbHdhcmUxEzARBgNVBAcMCk5ldyBD
YXN0bGUxFTATBgNVBAoMDFN1cGFiYXNlIEluYzEeMBwGA1UEAwwVU3VwYWJhc2Ug
Um9vdCAyMDIxIENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqQXW
QyHOB+qR2GJobCq/CBmQ40G0oDmCC3mzVnn8sv4XNeWtE5XcEL0uVih7Jo4Dkx1Q
DmGHBH1zDfgs2qXiLb6xpw/CKQPypZW1JssOTMIfQppNQ87K75Ya0p25Y3ePS2t2
GtvHxNjUV6kjOZjEn2yWEcBdpOVCUYBVFBNMB4YBHkNRDa/+S4uywAoaTWnCJLUi
cvTlHmMw6xSQQn1UfRQHk50DMCEJ7Cy1RxrZJrkXXRP3LqQL2ijJ6F4yMfh+Gyb4
O4XajoVj/+R4GwywKYrrS8PrSNtwxr5StlQO8zIQUSMiq26wM8mgELFlS/32Uclt
NaQ1xBRizkzpZct9DwIDAQABo2AwXjALBgNVHQ8EBAMCAQYwHQYDVR0OBBYEFKjX
uXY32CztkhImng4yJNUtaUYsMB8GA1UdIwQYMBaAFKjXuXY32CztkhImng4yJNUt
aUYsMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAB8spzNn+4VU
tVxbdMaX+39Z50sc7uATmus16jmmHjhIHz+l/9GlJ5KqAMOx26mPZgfzG7oneL2b
VW+WgYUkTT3XEPFWnTp2RJwQao8/tYPXWEJDc0WVQHrpmnWOFKU/d3MqBgBm5y+6
jB81TU/RG2rVerPDWP+1MMcNNy0491CTL5XQZ7JfDJJ9CCmXSdtTl4uUQnSuv/Qx
Cea13BX2ZgJc7Au30vihLhub52De4P/4gonKsNHYdbWjg7OWKwNv/zitGDVDB9Y2
CMTyZKG3XEu5Ghl1LEnI3QmEKsqaCLv12BnVjbkSeZsMnevJPs1Ye6TjjJwdik5P
o/bKiIz+Fq8=
-----END CERTIFICATE-----
```

## Source verification

Certificate source: `https://github.com/supabase/cli/blob/d6a376c82436c908efa142f4c17977f477c264b8/apps/cli-go/internal/gen/types/templates/prod-ca-2021.crt`.

TLS semantics: PostgreSQL 17 connection documentation, `https://www.postgresql.org/docs/17/libpq-connect.html`, and Supabase SSL enforcement documentation, `https://supabase.com/docs/guides/platform/ssl-enforcement`. Vendor examples are explanatory only; their pooler, home-root, or other configuration examples do not override this narrower contract.

**END — ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1**
