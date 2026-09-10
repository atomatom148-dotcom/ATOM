# ATOM — Render Workflows Readiness Amendment 1

**Decision ID:** `ATOM-RENDER-WORKFLOWS-READINESS-AMENDMENT-1`  
**Status:** FROZEN ON OWNER-APPROVED MERGE; no authority before that merge.  
**Author:** ChatGPT Pro  
**Owner objective:** Establish the first ATOM-owned Render Workflow service in the canonical `atomatom148-dotcom/ATOM` repository without moving HIST8, SIM, V9, production, or trading behavior into Workflows.

## 1. Narrow authority

This amendment authorizes exactly one new Render Workflow service and one readiness-only repository surface. It is infrastructure/readiness authority only.

It explicitly supersedes, for this one service only, the existing HIST8 and active-pointer prohibitions on a new service, Workflow files, a Workflow-only dependency, and Render configuration. Every other prohibition remains unchanged.

This amendment does **not** authorize HIST8 ingestion, HIST8 database access, historical-provider access, SIM work, V9 work, production consumption, market-data streaming, evidence writes, broker/account/order access, model research, or live-capital trading through Render Workflows.

The active phase remains SIM-5. The existing HIST8 authorization remains separately active and unchanged except that this readiness service may exist. HIST8 execution remains on its currently authorized bounded offline path until a later Owner-approved amendment explicitly moves or adds a HIST8 task to Workflows.

## 2. Exact Render service identity

Authorize exactly:

- Render workspace: `tea-d9g2b1m7r5hc73e7ufk0` (`My Workspace`)
- Service type: Render Workflow
- Service name: `atom-workflows`
- Source repository: `https://github.com/atomatom148-dotcom/ATOM`
- Branch: `main`
- Region: `oregon`
- Runtime: Python
- Auto-Deploy: `Off`
- Root Directory: repository root / blank
- Build Command: `pip install -r workflows/requirements.txt`
- Start Command: `python -m workflows.main`
- Environment variables/secrets: none for readiness

No existing Render service may be repointed, renamed, restarted, suspended, resized, or reconfigured by this amendment. No second Workflow service is authorized.

## 3. Exact implementation surface

After this documentation amendment is lawfully merged, one implementation PR may create exactly:

- `workflows/__init__.py`
- `workflows/main.py`
- `workflows/requirements.txt`
- `tests/test_workflows_readiness.py`

No existing Python module, root `requirements.txt`, migration, freeze, HIST8 implementation file, SIM file, V9 file, CI workflow, Render service, database object, role, credential, or production configuration may be changed by that implementation PR.

`workflows/requirements.txt` must contain only the Render Python SDK dependency required for this readiness surface:

```text
render>=1.0.1
```

The implementation must use the current Render Python SDK contract:

```python
from render import TaskContext, Workflows

app = Workflows()
```

It registers exactly one task named `readiness_smoke`. The task accepts `TaskContext` as its first positional argument plus only a small `check_id: str` and optional `metadata: str`, performs no I/O, and returns only:

```python
{
    "check_id": check_id,
    "metadata": metadata,
    "status": "ready",
}
```

The module must call `app.start()` only beneath its `if __name__ == "__main__":` startup guard. Importing the module registers definitions only and must not execute the task.

## 4. Isolation laws

The readiness Workflow must not import or invoke `research.hist8.corpus` or any other HIST8 execution module. It must not read environment secrets, open a database connection, call Alpaca, Coinbase, Massive, Schwab, Supabase, a broker, or any ATOM live service, and must not create files or durable evidence.

The Workflow receives no production authority and no dependency relationship is created from existing ATOM services to this Workflow. Workflow absence, failure, deletion, or task failure must have zero effect on existing production, SIM, V1B, V9, market-data, evidence, or web services.

No existing ATOM service may add `render>=1.0.1` to its dependency surface as part of this readiness phase. The dependency is isolated in `workflows/requirements.txt` specifically to avoid changing existing service builds.

## 5. Implementation and test gate

Codex is the preferred implementation owner. One implementation owner owns the PR.

Before implementation merge, prove on the exact final head:

- the changed-file set is exactly the four authorized files;
- `render>=1.0.1` installs and exposes `render.Workflows` and `render.TaskContext` in a clean Python environment;
- module import registers only the readiness task and does not call `app.start()`;
- `readiness_smoke` is deterministic and side-effect free;
- no HIST8, SIM, V9, production worker, database, provider, broker, or secret path is imported or invoked;
- root dependencies and all existing service entrypoints remain unchanged; and
- the existing required repository checks remain green.

A fallback SDK shim may be used only in a unit test explicitly testing registration mechanics when the real SDK is absent. It cannot satisfy the real-SDK installation/import gate and cannot mask an SDK contract failure.

Independent final-head review, every required green check, zero unresolved material threads, and Owner-authorized merge are mandatory.

## 6. Deployment gate

Only after the implementation PR is lawfully merged may the exact new `atom-workflows` service be created with the configuration in section 2.

Before creation/deploy, verify the deployed source revision is the implementation merge commit or a descendant whose four authorized Workflow file blobs are byte-identical to the reviewed implementation merge. If any Workflow blob differs, stop `BLOCKED` and require fresh review of the changed surface.

The first deployment performs registration only. Do not invoke any task until the service reports successful startup/registration.

Then invoke exactly one harmless readiness run using:

```text
check_id = workflow-readiness-1
metadata = initial-deploy
```

PASS requires the exact returned value:

```json
{"check_id":"workflow-readiness-1","metadata":"initial-deploy","status":"ready"}
```

Also record workspace, service identity, deployed SHA, Workflow file blob identities, build/start commands, registration result, task-run identity/status, and confirmation that no environment variables or secrets were configured.

Registration or task failure is `FAIL`/`INVALID` as applicable. Do not add secrets, broaden files, add a second task, or improvise another service to make the proof pass.

## 7. No HIST8 promotion by implication

A successful readiness proof establishes only that Render Workflows can build, register, and execute a harmless ATOM-owned task from the canonical ATOM repository.

It does not authorize moving `research/hist8/corpus.py`, HIST8 database credentials, source credentials, imports, derivation, replay, receipts, or any other workload into the Workflow service. That requires a later documentation-first amendment defining the exact task graph, secrets, retry/idempotency rules, execution bounds, and receipt requirements.

## 8. Wrong-repository correction

The readiness scaffold previously merged into `atomatom148-dotcom/Coin-market-api` is not an authorized ATOM Workflow home. It may be removed by a separate narrow revert limited to the files/dependency introduced by that scaffold. The revert must not alter unrelated Coin-market-api behavior. Because existing Coin-market-api services auto-deploy from `main`, that cleanup merge must receive its own review/checks and its resulting deployments must be verified separately; this amendment itself performs no Coin-market-api or Render mutation.

## 9. Frozen conclusion

> ATOM owns its Workflow infrastructure in `atomatom148-dotcom/ATOM`. The first service is exactly `atom-workflows`, Auto-Deploy Off, Oregon, readiness-only, with an isolated Workflow dependency and one deterministic no-I/O smoke task. No HIST8, SIM, V9, production, broker, database, credential, or research behavior moves into Workflows until a later Owner-approved amendment explicitly authorizes it.

**END — ATOM-RENDER-WORKFLOWS-READINESS-AMENDMENT-1**
