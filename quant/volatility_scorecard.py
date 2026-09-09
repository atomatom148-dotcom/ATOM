"""Pure V-1B volatility-scorecard contracts and mathematical kernels.

The I/O, repository-authority, runtime-provenance, TLS/database, seal, and
receipt orchestration live in the same module by contract, but are deliberately
kept separate from the functions in this section.  In particular, none of the
objects or functions below performs network, database, subprocess, or file I/O.
"""

from __future__ import annotations

import sys

# Amendment 3A installs this object as both non-writing interpreter hooks in
# the first executable bytes of every application ``-c`` source.  Capture it
# before any other application import can replace or wrap it.
_CAPTURED_BOOTSTRAP_HOOK = sys.excepthook

import argparse
import base64
import ctypes
import errno
import fcntl
import hashlib
import hmac
import http.client
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import random
import re
import selectors
import shlex
import shutil
import socket
import ssl
import stat
import subprocess
import sysconfig
import time
import urllib.parse
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timedelta, timezone
from enum import Enum, auto
from pathlib import Path, PurePosixPath
from types import MappingProxyType, ModuleType
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    NoReturn,
    Protocol,
    Sequence,
)


DECISION_ID = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
TLS_AMENDMENT_ID = "ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1"
AMENDMENT_ID = "ATOM-V1A-AMENDMENT-2A-TIERED-READINESS-1"
OPERATIONAL_AMENDMENT_ID = (
    "ATOM-V1A-AMENDMENT-3-V1B-OPERATIONAL-PREREQUISITES-1"
)
BOOTSTRAP_AMENDMENT_ID = (
    "ATOM-V1A-AMENDMENT-3A-BOOTSTRAP-DEADLINE-CLOSURE-1"
)
CORRECTIVE_AMENDMENT_ID = (
    "ATOM-V1A-AMENDMENT-3B-V1B-CORRECTIVE-AUTHORIZATION-1"
)
JOB_ID = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
CONTRACT_PATH = "docs/v-1a-volatility-first-freeze.md"
TLS_AMENDMENT_PATH = "docs/v-1a-amendment-1-tls-trust-anchor.md"
AMENDMENT_PATH = "docs/v-1a-amendment-2a-tiered-readiness-boundaries.md"
OPERATIONAL_AMENDMENT_PATH = (
    "docs/v-1a-amendment-3-v1b-operational-prerequisites.md"
)
BOOTSTRAP_AMENDMENT_PATH = (
    "docs/v-1a-amendment-3a-bootstrap-deadline-closure.md"
)
CORRECTIVE_AMENDMENT_PATH = (
    "docs/v-1a-amendment-3b-v1b-corrective-authorization.md"
)
CODE_VERSION = "ATOM-V1B-MANIFEST-1"
OPERATIONAL_APPROVAL_SCHEMA_VERSION = (
    "ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-2"
)
RECOVERY_TRANSPORT_POLICY = "EXACT_SUBMISSION_OR_CONSUMING_INCIDENT"

V1A_MERGE_SHA = "ac85cc9e99ccc499789f3ef79b186768d99fb0d6"
TLS_AMENDMENT_MERGE_SHA = "2126b53d1f3419f193eeddf0d7ca066f0fd161af"
AMENDMENT_MERGE_SHA = "166a0e5b945e4f19ae41f392e75e3560d72acc1b"
OPERATIONAL_AMENDMENT_MERGE_SHA = "acc004ff074018bf36dfb40aa651497ef5b39b1e"
BOOTSTRAP_AMENDMENT_MERGE_SHA = "9accee6056dfcd6a6ab06d7f538ce6e5b47ee4e9"
CORRECTIVE_AMENDMENT_MERGE_SHA = "8e08a58f696459970ec8f991a37e2c914a5bc911"
V1A_PR_NUMBER = 319
AMENDMENT_PR_NUMBER = 321
TLS_AMENDMENT_PR_NUMBER = 322
OPERATIONAL_AMENDMENT_PR_NUMBER = 325
BOOTSTRAP_AMENDMENT_PR_NUMBER = 326
CORRECTIVE_AMENDMENT_PR_NUMBER = 332
BOOTSTRAP_AMENDMENT_MERGED_AT = "2026-09-07T23:37:59Z"
CORRECTIVE_AMENDMENT_MERGED_AT = "2026-09-09T00:48:29Z"
BOOTSTRAP_AMENDMENT_GIT_BLOB_SHA1 = "62441ea2c05da92960b785c8331dcd7c7e3d91ef"
CORRECTIVE_AMENDMENT_GIT_BLOB_SHA1 = "d0af73c9ff3f4f69df464a8d1bcc7ea1ba59dada"
BOOTSTRAP_AMENDMENT_SHA256 = (
    "312546ab6b75b2b81a70c8174070a3901fe934c7d3a63a0cefcc081c80db6125"
)
CORRECTIVE_AMENDMENT_SHA256 = (
    "29891d4dad2d74cd679377b3f97442b643fea97894f02124c6c4b74519d8897f"
)

READONLY_URL_ENV = "ATOM_E1_SCORECARD_READONLY_DATABASE_URL"
AUTHORIZED_MAIN_ENV = "ATOM_V1B_AUTHORIZED_MAIN_SHA"
GITHUB_TOKEN_ENV = "ATOM_V1B_GITHUB_TOKEN"
READER_ROLE = "atom_e1_scorecard_reader"
DATABASE_NAME = "postgres"
PROJECT_REF = "afyiydxbjgzaiswnbcyj"
DIRECT_HOST = "db.afyiydxbjgzaiswnbcyj.supabase.co"
DIRECT_PORT = 5432
RENDER_SERVICE_ID = "srv-daa7thgae00c73a2lmn0"
CA_REPOSITORY_PATH = "certs/supabase-prod-ca-2021.crt"
CA_SIZE_BYTES = 1367
CA_SHA256 = "700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7"
CA_GIT_BLOB_SHA1 = "3d693669b23c340c57a3457bdc8b6fefe1806cc5"

GITHUB_API_HOST = "api.github.com"
GITHUB_API_PORT = 443
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_REPOSITORY = "atomatom148-dotcom/ATOM"
GITHUB_REPOSITORY_ID = 1_339_927_428
GITHUB_OWNER_ID = 307_819_087
GITHUB_OWNER_LOGIN = "atomatom148-dotcom"
GITHUB_REPOSITORY_PATH = "/repos/atomatom148-dotcom/ATOM"
GITHUB_MAIN_REF_PATH = "/repos/atomatom148-dotcom/ATOM/git/ref/heads/main"
GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH = (
    "/repos/atomatom148-dotcom/ATOM/issues/325/comments"
)
GITHUB_APPROVAL_COMMENTS_PATH = (
    "/repos/atomatom148-dotcom/ATOM/issues/325/comments?per_page=100&page=1"
)
GITHUB_RESOLVER_OUTPUT_LIMIT = 16_384
GITHUB_PAGE_SIZE = 100
# Internal fail-closed transport bound for the fixed GitHub REST surfaces used
# here.  It is deliberately far above the largest 100-comment page or
# repository source/blob response this closed client accepts.  This is not a
# research/schema limit and no prefix is ever accepted when it is exceeded.
GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES = 67_108_864
GITHUB_DEADLINE_WORK_CHUNK_BYTES = 65_536
GITHUB_CONNECT_TIMEOUT_NS = 10_000_000_000
GITHUB_READ_IDLE_TIMEOUT_NS = 20_000_000_000
GITHUB_REQUEST_TOTAL_TIMEOUT_NS = 60_000_000_000
GITHUB_PAGINATION_TOTAL_TIMEOUT_NS = 180_000_000_000
GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS = 300_000_000_000

EXPECTED_LIBPQ_VERSION = 180006
EXPECTED_DEPENDENCY_VERSIONS: Mapping[str, str] = MappingProxyType(
    {
        "exchange-calendars": "4.13.2",
        "korean-lunar-calendar": "0.3.1",
        "numpy": "2.4.2",
        "pandas": "3.0.0",
        "psycopg": "3.3.5",
        "psycopg-binary": "3.3.5",
        "pyluach": "2.3.0",
        "python-dateutil": "2.9.0.post0",
        "six": "1.17.0",
        "toolz": "1.1.0",
        "tzdata": "2025.3",
    }
)
GOVERNED_DEPENDENCY_DATA_PATHS = {
    "tzdata": (
        "tzdata/zoneinfo/America/New_York",
        "tzdata/zoneinfo/UTC",
    ),
}
INSTALL_SCHEME_ROOT_NAMES = (
    "purelib",
    "platlib",
    "scripts",
    "data",
    "include",
    "platinclude",
)

DATABASE_IDENTITY = MappingProxyType(
    {"supabase_project_ref": PROJECT_REF, "database_name": DATABASE_NAME}
)
HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_MICROSECOND_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:"
    r"[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
SESSION_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

HORIZON_SECONDS: Mapping[str, int] = OrderedDict(
    (
        ("30S", 30),
        ("1M", 60),
        ("5M", 300),
        ("15M", 900),
        ("30M", 1800),
        ("1H", 3600),
    )
)
HORIZONS = tuple(HORIZON_SECONDS)

BOOTSTRAP_RESAMPLES = 200_000
BOOTSTRAP_MAX_ATTEMPTS = 1_000_000
BOOTSTRAP_SEED = 0
INTERVAL_LEVELS = (0.999, 0.95)
BOOTSTRAP: Mapping[str, object] = {
    "resamples_required": 200_000,
    "max_attempts": 1_000_000,
    "seed": 0,
    "interval_levels": [0.999, 0.95],
    "cluster": "XNYS_SESSION_DATE",
    "sampling_operation": (
        "random.Random(0).choices(sessions,k=len(sessions))"
    ),
    "loss_function": "QLIKE(r,f)=log(f^2)+r^2/f^2",
    "gates": ["unconditional", "seasonal"],
}
MIN_WINDOWS = 100
MIN_SESSIONS = 10
OLS_RANK_FACTOR = 2.0**-40
NORMAL_90 = 1.6448536269514722

FAMILY_SENTINEL = None
V9_SENTINEL = {
    "v3_model_version": "__NO_ADMISSIBLE_V9_LINEAGE__",
    "symbol": "COIN",
    "cohort_id": "__NO_ADMISSIBLE_V9_LINEAGE__",
    "cohort_hash": "0" * 64,
}


class ContractError(RuntimeError):
    """A fail-closed contract error that must never contain a credential."""


class ProtocolDefect(RuntimeError):
    """A population, arithmetic, or frozen-contract defect."""


class StartupIsolationError(ContractError):
    """The live process is not the exact approved isolated process."""


class ArtifactError(ContractError):
    """Artifact bytes, coverage, mapping, or version are invalid."""


@dataclass(frozen=True, slots=True)
class CellSpec:
    cell_order: int
    forecaster: str
    horizon: str

    def public(self) -> dict[str, object]:
        return {
            "cell_order": self.cell_order,
            "forecaster": self.forecaster,
            "horizon": self.horizon,
        }


ALL_CELLS = tuple(
    [CellSpec(i, "FAMILY-VOL", horizon) for i, horizon in enumerate(HORIZONS)]
    + [
        CellSpec(i + len(HORIZONS), "V9-VOL", horizon)
        for i, horizon in enumerate(HORIZONS)
    ]
)
CELL_BY_ORDER = {cell.cell_order: cell for cell in ALL_CELLS}

MANIFEST_REGISTRY: Mapping[str, tuple[int, tuple[int, ...]]] = OrderedDict(
    (
        ("v1b-early-4", (1, (0, 1, 6, 7))),
        ("v1b-family-5m", (2, (2,))),
        ("v1b-family-15m", (3, (3,))),
        ("v1b-family-30m", (4, (4,))),
        ("v1b-family-1h", (5, (5,))),
        ("v1b-v9-5m", (6, (8,))),
        ("v1b-v9-15m", (7, (9,))),
        ("v1b-v9-30m", (8, (10,))),
        ("v1b-v9-1h", (9, (11,))),
    )
)

EVIDENCE_ARTIFACTS = (
    (
        "ORIGINAL_MEASUREMENT",
        "docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS-ORIGINAL.md",
        8314,
        "aaa58a0a36f8921bde54f0215f2a189da79a6a5c25b6e9db5d2d4f2b562cf913",
    ),
    (
        "CORRECTED_MEASUREMENT",
        "docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS.md",
        8662,
        "0b21fc0f9e2aec42939fcd74a91debbba916639cb84e95fe96c2bfcd55e41627",
    ),
    (
        "CORRECTION_1",
        "docs/evidence/CORRECTION-1-V9-1H-CALIBRATION-ARITHMETIC.md",
        8267,
        "06c993a6cd3290e306e75feb73f0facf52fd4ce6f2c04dd1357452cfc26ef3fd",
    ),
    (
        "CORRECTION_1_COVER_NOTE",
        "docs/evidence/CORRECTION-1-COVER-NOTE.txt",
        3149,
        "9e85f3cfcfe7a0629cf014a218847738793d72d0deb7814329471b9ab5621611",
    ),
    (
        "CORRECTION_2",
        "docs/evidence/CORRECTION-2-N-EFF-SATURATION-AND-RANGE-STATUS-DEFECT.md",
        7795,
        "24bfda809cc55acb26d46ccdd8a3f741b3b06dccfc064ef00568a714090dc6a5",
    ),
    (
        "CORRECTION_3",
        "docs/evidence/CORRECTION-3-THRESHOLD-STATUS.md",
        5370,
        "717c4057229a9109803e05e0eb4647e9c4648c2a272e36918f1697552157eeb8",
    ),
    (
        "ERRATUM_CORRECTION_2",
        "docs/evidence/ERRATUM-TO-CORRECTION-2.md",
        4761,
        "37a248d8a29fb258048c27549f06305ab2f5f886c38380d12cebe51da3ef33d4",
    ),
    (
        "SCOPE_NOTE_V1A_DEPENDENCY",
        "docs/evidence/SCOPE-NOTE-V1A-READINESS-DEPENDS-ON-SCALE-STATUS-ONLY.md",
        4915,
        "8c8079b428e39fee8f41e64af384c540fbb363013dee00ad3e31a285adf8109b",
    ),
)

SCOUTING_DISCLOSURE = (
    "2026-09-03 pooled overlapping-window Q3 volatility correlations, level ratios, and slopes were inspected before V-1A adoption.",
    "Q3 appeared to carry rank information while its absolute level was horizon-miscalibrated.",
    "An overlapping previous-window persistence calculation was inspected and recognized as overlap-contaminated.",
    "No exact E-1-selected non-overlapping session-clustered V-1 enc_b statistic under this frozen population was adopted as controlling evidence before V-1A.",
    "No exact V9-VOL causal-kappa enc_b statistic under this frozen population was adopted as controlling evidence before V-1A.",
    "A 2026-09-04 post-adoption audit inspected only identities, timestamps, accounting counts, selector counts, availability, and minimum failures; all 12 cells were count-insufficient and no protected V-1 inferential result was computed.",
    "A 2026-09-05 cadence measurement inspected counts, timestamps, publication-proof presence, and inter-arrival gaps; its rates were not frozen selector results.",
    "A 2026-09-05 correction and cover note withdrew the six-calibration-pairs-per-session and universal 15-week V9 1H claims; their persisted-selector rates and readiness dates remain planning evidence, not V-1A readiness results.",
    "A 2026-09-05 second correction used persisted state and status values plus arithmetic, showed that 500 selected pairs was insufficient at 5M, and withdrew the directional effective-N proxy; its structural range diagnosis was later withdrawn, and range and threshold statuses are not V-1A inputs.",
    "A 2026-09-05 third correction established that threshold_status uses a growing absolute-realized-return pool, was session-count-masked at eight sessions, and remains undetermined; its 2026-09-23 observation point is not a V-1A boundary, and its latent UTC-versus-ET session mismatch had no measured current impact.",
    "A 2026-09-05 erratum correctly withdrew the claim that fixed-250 range validation makes MATURE structurally unreachable; its all-six-PROVISIONAL status statement and cross-series q3 effective-N extrapolation are rejected, and the actual failing range predicate remains unobserved.",
    "A 2026-09-05 scope note correctly established that only scale among V4C component statuses can affect V-1A and that FAMILY-VOL has no V4C dependency; its claim that 500 selected pairs are needed before the calibration pool is nonempty and its latest-state substitute for causal kappa reconstruction are rejected.",
    "Before Amendment 2A, no enc_b value, encompassing coefficient, bootstrap interval, QLIKE value or summary, gate result, cell classification, or E-2 |mu|/(kappa*sigma) statistic for an Amendment 2A boundary was computed or inspected.",
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _cooperative_check(check: Callable[[], object] | None) -> None:
    if check is not None:
        check()


def _cooperative_call(
    check: Callable[[], object] | None,
    operation: Callable[..., Any],
    /,
    *args: object,
    **kwargs: object,
) -> Any:
    """Bracket one bounded local/native primitive with the shared deadline."""

    _cooperative_check(check)
    try:
        result = operation(*args, **kwargs)
    except BaseException:
        # A primitive that raises still returned control to Python.  Observe
        # the shared clock immediately; a late exceptional return is a
        # deadline failure, not an earlier-domain validation result.
        _cooperative_check(check)
        raise
    _cooperative_check(check)
    return result


def _cooperative_acquire(
    check: Callable[[], object] | None,
    operation: Callable[..., Any],
    cleanup: Callable[[Any], object],
    /,
    *args: object,
    **kwargs: object,
) -> Any:
    """Bracket acquisition while retaining a late-returned handle for cleanup."""

    _cooperative_check(check)
    try:
        resource = operation(*args, **kwargs)
    except BaseException:
        _cooperative_check(check)
        raise
    try:
        _cooperative_check(check)
    except BaseException:
        # Cleanup is quarantine-only and therefore is not skipped merely
        # because the acceptance deadline has already expired.
        cleanup(resource)
        raise
    return resource


def _cooperative_tuple(
    values: Iterable[Any],
    *,
    check: Callable[[], object] | None = None,
) -> tuple[Any, ...]:
    """Materialize a finite frozen collection with checked advancement."""

    iterator = _cooperative_call(check, iter, values)
    items: list[Any] = []
    while True:
        _cooperative_check(check)
        try:
            item = next(iterator)
        except StopIteration:
            _cooperative_check(check)
            break
        _cooperative_check(check)
        _cooperative_call(check, items.append, item)
    return _cooperative_call(check, tuple, items)


def _cooperative_sorted(
    values: Iterable[Any],
    *,
    key: Callable[[Any], Any] | None = None,
    check: Callable[[], object] | None = None,
) -> tuple[Any, ...]:
    """Sort one already finite checked collection as one bounded native call."""

    items = _cooperative_tuple(values, check=check)
    ordered = _cooperative_call(check, sorted, items, key=key)
    return _cooperative_call(check, tuple, ordered)


def _cooperative_canonical_sha256(
    value: object,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    """Canonical hash with fixed-size UTF-8 work between deadline checks."""

    encoder = _cooperative_call(
        check,
        json.JSONEncoder,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    digest = _cooperative_call(check, hashlib.sha256)
    pieces = _cooperative_call(check, encoder.iterencode, value)
    piece_iterator = _cooperative_call(check, iter, pieces)
    while True:
        _cooperative_check(check)
        try:
            piece = next(piece_iterator)
        except StopIteration:
            _cooperative_check(check)
            break
        _cooperative_check(check)
        # JSONEncoder can yield a whole scalar at once.  Bound each encode/hash
        # update by bytes (not Unicode code points) even when that scalar is
        # large.  The whole-value encode is the explicitly deadline-bracketed
        # native call; each subsequent digest unit is at most 65,536 bytes.
        encoded_piece = _cooperative_call(check, piece.encode, "utf-8")
        encoded_view = _cooperative_call(check, memoryview, encoded_piece)
        offset = 0
        while offset < len(encoded_view):
            _cooperative_check(check)
            end = min(
                offset + GITHUB_DEADLINE_WORK_CHUNK_BYTES,
                len(encoded_view),
            )
            chunk = _cooperative_call(
                check,
                lambda item, start, stop: item[start:stop],
                encoded_view,
                offset,
                end,
            )
            _cooperative_call(check, digest.update, chunk)
            offset = end
        _cooperative_check(check)
    return _cooperative_call(check, digest.hexdigest)


def timestamp_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True, slots=True)
class ZoneInfoIsolation:
    module: object
    reset_tzpath: object
    zoneinfo_class: type
    clear_cache_descriptor: object
    tzdata_module: object
    new_york: object
    utc: object


_ZONEINFO_ISOLATION: ZoneInfoIsolation | None = None


def _validate_zoneinfo_isolation(
    state: ZoneInfoIsolation,
    *,
    check: Callable[[], object] | None = None,
) -> None:
    module = _cooperative_call(check, sys.modules.get, "zoneinfo")
    tzdata_module = _cooperative_call(check, sys.modules.get, "tzdata")
    module_dict = _cooperative_call(check, getattr, module, "__dict__", {})
    zoneinfo_class = _cooperative_call(
        check,
        module_dict.__getitem__,
        "ZoneInfo",
    )
    class_dict = _cooperative_call(
        check,
        getattr,
        zoneinfo_class,
        "__dict__",
        {},
    )
    if (
        module is not state.module
        or tzdata_module is not state.tzdata_module
        or _cooperative_call(check, module_dict.__getitem__, "reset_tzpath")
        is not state.reset_tzpath
        or zoneinfo_class is not state.zoneinfo_class
        or _cooperative_call(check, class_dict.__getitem__, "clear_cache")
        is not state.clear_cache_descriptor
        or _cooperative_call(check, getattr, module, "TZPATH", None) != ()
        or not isinstance(state.new_york, state.zoneinfo_class)
        or _cooperative_call(check, getattr, state.new_york, "key", None)
        != "America/New_York"
        or not isinstance(state.utc, state.zoneinfo_class)
        or _cooperative_call(check, getattr, state.utc, "key", None) != "UTC"
    ):
        raise StartupIsolationError("ZONEINFO_ISOLATION_INVALID")
    _cooperative_check(check)


def _initialize_zoneinfo_isolation() -> ZoneInfoIsolation:
    """Perform the sole ordered TZPATH reset/cache clear for this process."""

    global _ZONEINFO_ISOLATION
    if _ZONEINFO_ISOLATION is not None:
        _validate_zoneinfo_isolation(_ZONEINFO_ISOLATION)
        return _ZONEINFO_ISOLATION
    if "zoneinfo" in sys.modules or "tzdata" in sys.modules:
        raise StartupIsolationError("ZONEINFO_LOADED_BEFORE_ISOLATION")
    try:
        module = importlib.import_module("zoneinfo")
        module_dict = module.__dict__
        reset_tzpath = module_dict["reset_tzpath"]
        zoneinfo_class = module_dict["ZoneInfo"]
        clear_cache_descriptor = zoneinfo_class.__dict__["clear_cache"]
        reset_tzpath(())
        zoneinfo_class.clear_cache()
        if module.TZPATH != ():
            raise StartupIsolationError("ZONEINFO_TZPATH_NOT_EMPTY")
        # Each reviewed construction follows a fresh check of every retained
        # object identity and the empty TZPATH.  Do not replace the descriptor
        # comparison with a bound-method identity comparison.
        tzdata_module = importlib.import_module("tzdata")

        def validate_preconstruction_state() -> None:
            if (
                sys.modules.get("zoneinfo") is not module
                or sys.modules.get("tzdata") is not tzdata_module
                or module.__dict__["reset_tzpath"] is not reset_tzpath
                or module.__dict__["ZoneInfo"] is not zoneinfo_class
                or zoneinfo_class.__dict__["clear_cache"]
                is not clear_cache_descriptor
                or module.TZPATH != ()
            ):
                raise StartupIsolationError("ZONEINFO_IDENTITY_CHANGED")

        validate_preconstruction_state()
        new_york = zoneinfo_class("America/New_York")
        validate_preconstruction_state()
        utc_zone = zoneinfo_class("UTC")
        state = ZoneInfoIsolation(
            module=module,
            reset_tzpath=reset_tzpath,
            zoneinfo_class=zoneinfo_class,
            clear_cache_descriptor=clear_cache_descriptor,
            tzdata_module=tzdata_module,
            new_york=new_york,
            utc=utc_zone,
        )
        _validate_zoneinfo_isolation(state)
    except StartupIsolationError:
        raise
    except BaseException:
        raise StartupIsolationError("ZONEINFO_ISOLATION_FAILED") from None
    _ZONEINFO_ISOLATION = state
    return state


def _new_york_zone():
    state = _initialize_zoneinfo_isolation()
    _validate_zoneinfo_isolation(state)
    return state.new_york


def manifest_cells(manifest_id: str) -> tuple[CellSpec, ...]:
    try:
        _, orders = MANIFEST_REGISTRY[manifest_id]
    except KeyError as error:
        raise ContractError("INVALID_MANIFEST_ID") from error
    return tuple(CELL_BY_ORDER[order] for order in orders)


def manifest_sequence(manifest_id: str) -> int:
    try:
        sequence, _ = MANIFEST_REGISTRY[manifest_id]
    except KeyError as error:
        raise ContractError("INVALID_MANIFEST_ID") from error
    return sequence


def manifest_public_cells(manifest_id: str) -> list[dict[str, object]]:
    return [cell.public() for cell in manifest_cells(manifest_id)]


def evidence_artifacts() -> list[dict[str, object]]:
    return [
        {"role": role, "path": path, "size_bytes": size, "sha256": digest}
        for role, path, size, digest in EVIDENCE_ARTIFACTS
    ]


def family_lineage(horizon: str) -> dict[str, str]:
    if horizon not in HORIZON_SECONDS:
        raise ContractError("invalid horizon")
    return {
        "quant_id": "q3_volatility",
        "formula_version": "realized-volatility-v1",
        "symbol": "COIN",
        "horizon": horizon,
    }


def v9_sentinel_lineage(horizon: str) -> dict[str, str]:
    if horizon not in HORIZON_SECONDS:
        raise ContractError("invalid horizon")
    return {**V9_SENTINEL, "horizon": horizon}


def selected_lineage_wrapper(
    spec: CellSpec, lineage: Mapping[str, str]
) -> dict[str, object]:
    validate_lineage_identity(spec, lineage)
    return {**spec.public(), "lineage_identity": dict(lineage)}


def validate_cell_spec(spec: CellSpec) -> None:
    if not isinstance(spec, CellSpec) or CELL_BY_ORDER.get(spec.cell_order) != spec:
        raise ProtocolDefect("noncanonical cell identity")


def validate_lineage_identity(
    spec: CellSpec,
    lineage: Mapping[str, str],
    *,
    allow_sentinel: bool = True,
) -> None:
    validate_cell_spec(spec)
    if not isinstance(lineage, Mapping):
        raise ProtocolDefect("lineage identity is not an object")
    if spec.forecaster == "FAMILY-VOL":
        expected = family_lineage(spec.horizon)
        if dict(lineage) != expected:
            raise ProtocolDefect("FAMILY lineage mismatch")
        return
    keys = {"v3_model_version", "symbol", "horizon", "cohort_id", "cohort_hash"}
    if set(lineage) != keys:
        raise ProtocolDefect("V9 lineage key mismatch")
    if (
        not all(isinstance(lineage[key], str) for key in keys)
        or lineage["symbol"] != "COIN"
        or lineage["horizon"] != spec.horizon
        or not lineage["v3_model_version"]
        or not lineage["cohort_id"]
        or len(lineage["cohort_hash"]) != 64
        or any(ch not in "0123456789abcdef" for ch in lineage["cohort_hash"])
    ):
        raise ProtocolDefect("V9 lineage value mismatch")
    is_sentinel = dict(lineage) == v9_sentinel_lineage(spec.horizon)
    uses_reserved_member = (
        lineage["v3_model_version"] == V9_SENTINEL["v3_model_version"]
        or lineage["cohort_id"] == V9_SENTINEL["cohort_id"]
        or lineage["cohort_hash"] == V9_SENTINEL["cohort_hash"]
    )
    if (is_sentinel and not allow_sentinel) or (uses_reserved_member and not is_sentinel):
        raise ProtocolDefect("reserved V9 sentinel used by a durable lineage")


@dataclass(frozen=True, slots=True)
class V9LineageCandidate:
    v3_model_version: str
    symbol: str
    horizon: str
    cohort_id: str
    cohort_hash: str
    cutoff_at: datetime

    def lineage_identity(self) -> dict[str, str]:
        return {
            "v3_model_version": self.v3_model_version,
            "symbol": self.symbol,
            "horizon": self.horizon,
            "cohort_id": self.cohort_id,
            "cohort_hash": self.cohort_hash,
        }


def select_v9_lineage(
    horizon: str,
    candidates: Iterable[V9LineageCandidate],
    evaluation_as_of_at: datetime,
) -> dict[str, str]:
    """Apply the outcome-blind V-1A §3.2 lineage rule."""

    if horizon not in HORIZON_SECONDS or evaluation_as_of_at.tzinfo is None:
        raise ProtocolDefect("invalid V9 lineage-selection boundary")
    eligible: list[V9LineageCandidate] = []
    for candidate in candidates:
        if not isinstance(candidate, V9LineageCandidate):
            raise ProtocolDefect("invalid V9 lineage candidate")
        identity = candidate.lineage_identity()
        spec = CELL_BY_ORDER[6 + HORIZONS.index(horizon)]
        validate_lineage_identity(spec, identity, allow_sentinel=False)
        if candidate.cutoff_at.tzinfo is None:
            raise ProtocolDefect("naive V9 cutoff")
        if candidate.horizon == horizon and candidate.cutoff_at <= evaluation_as_of_at:
            eligible.append(candidate)
    if not eligible:
        return v9_sentinel_lineage(horizon)
    selected = max(
        eligible,
        key=lambda item: (
            item.cutoff_at,
            item.v3_model_version.encode("utf-8"),
            item.cohort_id.encode("utf-8"),
            item.cohort_hash.encode("utf-8"),
        ),
    )
    return selected.lineage_identity()


@dataclass(frozen=True, slots=True)
class ValidWindow:
    session_date: date
    cutoff_at: datetime
    record_identity: str
    predicted_volatility_bps: float
    realized_volatility_bps: float
    outcome_available_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.session_date, date) or isinstance(
            self.session_date, datetime
        ):
            raise ProtocolDefect("session date must be a date")
        if self.cutoff_at.tzinfo is None or self.outcome_available_at.tzinfo is None:
            raise ProtocolDefect("window timestamps must be timezone-aware")
        if not isinstance(self.record_identity, str) or not self.record_identity:
            raise ProtocolDefect("window identity must be nonempty")
        prediction = finite(self.predicted_volatility_bps)
        realization = finite(self.realized_volatility_bps)
        if prediction is None or prediction <= 0:
            raise ProtocolDefect("valid window prediction must be finite and positive")
        if realization is None or realization < 0:
            raise ProtocolDefect("valid window realization must be finite and nonnegative")

    @property
    def order_key(self) -> tuple[date, datetime, str]:
        return self.session_date, self.cutoff_at, self.record_identity


@dataclass(frozen=True, slots=True)
class RegressionWindow:
    window: ValidWindow
    persist_1: float
    persist_20: float
    unconditional: float | None = None
    seasonal: float | None = None

    @property
    def session_date(self) -> date:
        return self.window.session_date


@dataclass(frozen=True, slots=True)
class OLSResult:
    status: str
    intercept: float | None
    persistence_coefficient: float | None
    enc_b: float | None


@dataclass(frozen=True, slots=True)
class MZResult:
    a: float | None
    b: float | None
    r2: float | None


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    attempted: int
    valid: int
    invalid: int
    ci_0999: tuple[float, float] | None
    ci_095: tuple[float, float] | None
    exhausted: bool

    @classmethod
    def zero(cls) -> "BootstrapResult":
        return cls(0, 0, 0, None, None, False)


@dataclass(frozen=True, slots=True)
class DescriptiveMetrics:
    mae_bps: float | None
    rank_corr: float | None
    level_ratio: float | None
    coverage_90: float | None
    mz_a: float | None
    mz_b: float | None
    mz_r2: float | None
    persist_rank_corr: float | None
    unconditional_rank_corr: float | None
    seasonal_rank_corr: float | None

    @classmethod
    def null(cls) -> "DescriptiveMetrics":
        return cls(*(None for _ in range(10)))


@dataclass(frozen=True, slots=True)
class GateLossData:
    rows: tuple[RegressionWindow, ...]
    candidate_losses: tuple[float, ...]
    benchmark_losses: tuple[float, ...]
    differences: tuple[float, ...]
    candidate_mean: float | None
    benchmark_mean: float | None
    difference_mean: float | None


@dataclass(frozen=True, slots=True)
class CellPopulation:
    spec: CellSpec
    lineage_identity: Mapping[str, str]
    n_input: int
    n_unselected_lineage_rows: int
    n_inadmissible: int
    n_non_rth: int
    n_overlap_excluded: int
    n_null_or_nonfinite_excluded: int
    n_nonpositive_prediction_excluded: int
    n_kappa_unavailable: int
    windows: tuple[ValidWindow, ...]
    regression: tuple[RegressionWindow, ...]
    n_persist20_unavailable: int
    n_unconditional_unavailable: int
    protocol_defect: bool = False

    def validate(self) -> None:
        validate_cell_spec(self.spec)
        validate_lineage_identity(self.spec, self.lineage_identity)
        counts = (
            self.n_input,
            self.n_unselected_lineage_rows,
            self.n_inadmissible,
            self.n_non_rth,
            self.n_overlap_excluded,
            self.n_null_or_nonfinite_excluded,
            self.n_nonpositive_prediction_excluded,
            self.n_kappa_unavailable,
            self.n_persist20_unavailable,
            self.n_unconditional_unavailable,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts
        ):
            raise ProtocolDefect("population count domain failure")
        buckets = (
            self.n_unselected_lineage_rows,
            self.n_inadmissible,
            self.n_non_rth,
            self.n_overlap_excluded,
            self.n_null_or_nonfinite_excluded,
            self.n_nonpositive_prediction_excluded,
            self.n_kappa_unavailable,
            len(self.windows),
        )
        if not isinstance(self.protocol_defect, bool):
            raise ProtocolDefect("protocol-defect flag must be boolean")
        if self.n_input != sum(buckets):
            raise ProtocolDefect("input accounting does not reconcile")
        if self.spec.forecaster == "FAMILY-VOL" and self.n_kappa_unavailable != 0:
            raise ProtocolDefect("FAMILY kappa-unavailable count must be zero")
        if tuple(sorted(self.windows, key=lambda item: item.order_key)) != self.windows:
            raise ProtocolDefect("windows are not in frozen order")
        keys = tuple(window.order_key for window in self.windows)
        if len(set(keys)) != len(keys):
            raise ProtocolDefect("duplicate selected-window identity")
        expected_regression, expected_persist_unavailable = build_regression_population(
            self.windows
        )
        expected_regression, expected_unconditional_unavailable = (
            attach_causal_benchmarks(expected_regression)
        )
        if (
            self.n_persist20_unavailable != expected_persist_unavailable
            or self.n_unconditional_unavailable
            != expected_unconditional_unavailable
            or self.regression != expected_regression
            or len(self.windows)
            != self.n_persist20_unavailable + len(self.regression)
        ):
            raise ProtocolDefect("regression or gate accounting does not reconcile")
        unconditional_rows = tuple(
            row for row in self.regression if row.unconditional is not None
        )
        seasonal_rows = tuple(row for row in self.regression if row.seasonal is not None)
        if unconditional_rows != seasonal_rows:
            raise ProtocolDefect("gate populations differ")
        sentinel = v9_sentinel_lineage(self.spec.horizon)
        if self.spec.forecaster == "V9-VOL" and dict(self.lineage_identity) == sentinel:
            if (
                self.n_unselected_lineage_rows != 0
                or self.n_inadmissible != self.n_input
                or any(buckets[index] for index in range(2, len(buckets)))
                or self.regression
                or self.n_persist20_unavailable
                or self.n_unconditional_unavailable
            ):
                raise ProtocolDefect("V9 sentinel accounting mismatch")


def assemble_cell_population(
    *,
    spec: CellSpec,
    lineage_identity: Mapping[str, str],
    n_input: int,
    n_unselected_lineage_rows: int,
    n_inadmissible: int,
    n_non_rth: int,
    n_overlap_excluded: int,
    n_null_or_nonfinite_excluded: int,
    n_nonpositive_prediction_excluded: int,
    n_kappa_unavailable: int,
    windows: Sequence[ValidWindow],
    protocol_defect: bool = False,
) -> CellPopulation:
    """Finalize ordered persistence/benchmark populations and reconcile counts."""

    ordered = tuple(windows)
    regression, n_persist20_unavailable = build_regression_population(ordered)
    regression, n_unconditional_unavailable = attach_causal_benchmarks(regression)
    population = CellPopulation(
        spec=spec,
        lineage_identity=dict(lineage_identity),
        n_input=n_input,
        n_unselected_lineage_rows=n_unselected_lineage_rows,
        n_inadmissible=n_inadmissible,
        n_non_rth=n_non_rth,
        n_overlap_excluded=n_overlap_excluded,
        n_null_or_nonfinite_excluded=n_null_or_nonfinite_excluded,
        n_nonpositive_prediction_excluded=n_nonpositive_prediction_excluded,
        n_kappa_unavailable=n_kappa_unavailable,
        windows=ordered,
        regression=regression,
        n_persist20_unavailable=n_persist20_unavailable,
        n_unconditional_unavailable=n_unconditional_unavailable,
        protocol_defect=protocol_defect,
    )
    population.validate()
    return population


def percentile_interval(
    sorted_values: Sequence[float], level: float
) -> tuple[float, float]:
    if not sorted_values:
        raise ValueError("no bootstrap values")
    if level not in INTERVAL_LEVELS:
        raise ValueError("unfrozen interval level")
    if any(finite(value) is None for value in sorted_values) or any(
        left > right for left, right in zip(sorted_values, sorted_values[1:])
    ):
        raise ValueError("bootstrap values must be finite and ascending")
    count = len(sorted_values)
    lower = math.floor(((1.0 - level) / 2.0) * (count - 1))
    upper = math.ceil(((1.0 + level) / 2.0) * (count - 1))
    return float(sorted_values[lower]), float(sorted_values[upper])


def _mean_fsum(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("empty mean")
    return math.fsum(values) / len(values)


def _median_binary64(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("empty median")
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _midranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = ((index + 1) + end) / 2.0
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def _pearson_binary64(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    try:
        xbar = math.fsum(float(value) for value in xs) / len(xs)
        ybar = math.fsum(float(value) for value in ys) / len(ys)
        sxx = math.fsum((float(x) - xbar) * (float(x) - xbar) for x in xs)
        syy = math.fsum((float(y) - ybar) * (float(y) - ybar) for y in ys)
        sxy = math.fsum(
            (float(x) - xbar) * (float(y) - ybar) for x, y in zip(xs, ys)
        )
        if not all(math.isfinite(value) for value in (xbar, ybar, sxx, syy, sxy)):
            return None
        if sxx <= 0 or syy <= 0:
            return None
        result = sxy / math.sqrt(sxx * syy)
        return result if math.isfinite(result) else None
    except (ArithmeticError, OverflowError, ValueError):
        return None


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    if any(finite(value) is None for value in (*xs, *ys)):
        return None
    return _pearson_binary64(_midranks(xs), _midranks(ys))


def mz_fit(predicted: Sequence[float], realized: Sequence[float]) -> MZResult:
    if len(predicted) < 2 or len(predicted) != len(realized):
        return MZResult(None, None, None)
    try:
        forecasts = [float(value) for value in predicted]
        outcomes = [float(value) for value in realized]
        n = len(forecasts)
        fbar = math.fsum(forecasts) / n
        ybar = math.fsum(outcomes) / n
        sff = math.fsum((value - fbar) * (value - fbar) for value in forecasts)
        sfy = math.fsum(
            (forecast - fbar) * (outcome - ybar)
            for forecast, outcome in zip(forecasts, outcomes)
        )
        syy = math.fsum((value - ybar) * (value - ybar) for value in outcomes)
        if (
            not all(math.isfinite(value) for value in (fbar, ybar, sff, sfy, syy))
            or sff <= 0
        ):
            return MZResult(None, None, None)
        slope = sfy / sff
        intercept = ybar - (slope * fbar)
        if not math.isfinite(intercept) or not math.isfinite(slope):
            return MZResult(None, None, None)
        sse = math.fsum(
            (outcome - (intercept + (slope * forecast)))
            * (outcome - (intercept + (slope * forecast)))
            for forecast, outcome in zip(forecasts, outcomes)
        )
        r2 = None
        if syy > 0 and math.isfinite(sse):
            candidate = 1.0 - (sse / syy)
            if math.isfinite(candidate):
                r2 = candidate
        return MZResult(intercept, slope, r2)
    except (ArithmeticError, OverflowError, ValueError):
        return MZResult(None, None, None)


def encompassing_ols(rows: Sequence[RegressionWindow]) -> OLSResult:
    if not rows:
        return OLSResult("RANK_DEFICIENT", None, None, None)
    try:
        persistence_values = [float(row.persist_20) for row in rows]
        forecasts = [float(row.window.predicted_volatility_bps) for row in rows]
        outcomes = [float(row.window.realized_volatility_bps) for row in rows]
        if not all(
            math.isfinite(value)
            for value in (*persistence_values, *forecasts, *outcomes)
        ):
            return OLSResult("NONFINITE", None, None, None)
        n = len(rows)
        pbar = math.fsum(persistence_values) / n
        fbar = math.fsum(forecasts) / n
        ybar = math.fsum(outcomes) / n
        spp = math.fsum(
            (value - pbar) * (value - pbar) for value in persistence_values
        )
        sff = math.fsum((value - fbar) * (value - fbar) for value in forecasts)
        spf = math.fsum(
            (persistence - pbar) * (forecast - fbar)
            for persistence, forecast in zip(persistence_values, forecasts)
        )
        spy = math.fsum(
            (persistence - pbar) * (outcome - ybar)
            for persistence, outcome in zip(persistence_values, outcomes)
        )
        sfy = math.fsum(
            (forecast - fbar) * (outcome - ybar)
            for forecast, outcome in zip(forecasts, outcomes)
        )
        q_value = spp * sff
        determinant = q_value - (spf * spf)
        intermediates = (
            pbar,
            fbar,
            ybar,
            spp,
            sff,
            spf,
            spy,
            sfy,
            q_value,
            determinant,
        )
        if not all(math.isfinite(value) for value in intermediates):
            return OLSResult("NONFINITE", None, None, None)
        if not (
            spp > 0
            and sff > 0
            and q_value > 0
            and determinant > OLS_RANK_FACTOR * q_value
        ):
            return OLSResult("RANK_DEFICIENT", None, None, None)
        persistence = ((spy * sff) - (sfy * spf)) / determinant
        enc_b = ((sfy * spp) - (spy * spf)) / determinant
        intercept = ybar - (persistence * pbar) - (enc_b * fbar)
        if not all(math.isfinite(value) for value in (persistence, enc_b, intercept)):
            return OLSResult("NONFINITE", None, None, None)
        return OLSResult("OK", intercept, persistence, enc_b)
    except (ArithmeticError, OverflowError, ValueError):
        return OLSResult("NONFINITE", None, None, None)


def qlike(realized: float, forecast: float) -> float:
    realization = finite(realized)
    prediction = finite(forecast)
    if realization is None or realization < 0 or prediction is None or prediction <= 0:
        raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE")
    try:
        loss_log = 2.0 * math.log(prediction)
        loss_ratio = realization / prediction
        loss_square = loss_ratio * loss_ratio
        value = loss_log + loss_square
    except (ArithmeticError, OverflowError, ValueError) as error:
        raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE") from error
    if not math.isfinite(value):
        raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE")
    return value


def build_regression_population(
    windows: Sequence[ValidWindow],
) -> tuple[tuple[RegressionWindow, ...], int]:
    ordered = tuple(sorted(windows, key=lambda item: item.order_key))
    regression: list[RegressionWindow] = []
    unavailable = 0
    for index, window in enumerate(ordered):
        prior = ordered[max(0, index - 20) : index]
        if len(prior) != 20 or any(
            item.outcome_available_at > window.cutoff_at for item in prior
        ):
            unavailable += 1
            continue
        try:
            persist_20 = math.fsum(
                float(item.realized_volatility_bps) for item in prior
            ) / 20
            persist_1 = float(prior[-1].realized_volatility_bps)
        except (ArithmeticError, OverflowError, ValueError):
            unavailable += 1
            continue
        if not math.isfinite(persist_20):
            unavailable += 1
            continue
        regression.append(RegressionWindow(window, persist_1, persist_20))
    return tuple(regression), unavailable


def _season_bucket(window: ValidWindow) -> int:
    local = window.cutoff_at.astimezone(_new_york_zone())
    minute = (local.hour * 60 + local.minute) - (9 * 60 + 30)
    bucket = math.floor(minute / 30)
    if bucket < 0 or bucket > 12:
        raise ProtocolDefect("seasonal cutoff outside frozen RTH buckets")
    return bucket


def attach_causal_benchmarks(
    rows: Sequence[RegressionWindow],
) -> tuple[tuple[RegressionWindow, ...], int]:
    result: list[RegressionWindow] = []
    unavailable = 0
    for index, row in enumerate(rows):
        causal = [
            prior
            for prior in rows[:index]
            if prior.window.outcome_available_at <= row.window.cutoff_at
        ]
        if not causal:
            result.append(row)
            unavailable += 1
            continue
        try:
            unconditional = math.fsum(
                float(prior.window.realized_volatility_bps) for prior in causal
            ) / len(causal)
        except (ArithmeticError, OverflowError, ValueError):
            unconditional = math.nan
        if not math.isfinite(unconditional) or unconditional <= 0:
            result.append(row)
            unavailable += 1
            continue
        profile = [
            prior
            for prior in causal
            if prior.session_date < row.session_date
            and prior.window.realized_volatility_bps > 0
        ]
        sessions = {prior.session_date for prior in profile}
        bucket = _season_bucket(row.window)
        bucket_rows = [
            prior for prior in profile if _season_bucket(prior.window) == bucket
        ]
        factor = 1.0
        if len(sessions) >= 3 and len(bucket_rows) >= 2:
            try:
                all_logs = [
                    math.log(float(prior.window.realized_volatility_bps))
                    for prior in profile
                ]
                bucket_logs = [
                    math.log(float(prior.window.realized_volatility_bps))
                    for prior in bucket_rows
                ]
                bucket_mean = math.fsum(bucket_logs) / len(bucket_logs)
                overall_mean = math.fsum(all_logs) / len(all_logs)
                factor = math.exp(bucket_mean - overall_mean)
            except (ArithmeticError, OverflowError, ValueError) as error:
                raise ProtocolDefect("seasonal profile arithmetic failure") from error
        seasonal = unconditional * factor
        if (
            not math.isfinite(factor)
            or factor <= 0
            or not math.isfinite(seasonal)
            or seasonal <= 0
        ):
            raise ProtocolDefect("seasonal profile nonfinite")
        result.append(replace(row, unconditional=unconditional, seasonal=seasonal))
    return tuple(result), unavailable


def _rows_by_session(
    rows: Sequence[RegressionWindow],
) -> tuple[list[str], dict[str, tuple[RegressionWindow, ...]]]:
    grouped: MutableMapping[str, list[RegressionWindow]] = {}
    for row in rows:
        grouped.setdefault(row.session_date.isoformat(), []).append(row)
    sessions = sorted(grouped)
    return sessions, {key: tuple(value) for key, value in grouped.items()}


def _validate_bootstrap_limits(required: int, max_attempts: int) -> None:
    if (
        not isinstance(required, int)
        or isinstance(required, bool)
        or required <= 0
        or not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < required
    ):
        raise ValueError("invalid bootstrap limits")


def bootstrap_enc_b(
    rows: Sequence[RegressionWindow],
    *,
    required: int = BOOTSTRAP_RESAMPLES,
    max_attempts: int = BOOTSTRAP_MAX_ATTEMPTS,
) -> BootstrapResult:
    _validate_bootstrap_limits(required, max_attempts)
    sessions, grouped = _rows_by_session(rows)
    if not sessions:
        return BootstrapResult(0, 0, 0, None, None, True)
    rng = random.Random(BOOTSTRAP_SEED)
    values: list[float] = []
    attempted = 0
    while len(values) < required and attempted < max_attempts:
        # NOSONAR: frozen deterministic statistical bootstrap, not a security use.
        drawn_sessions = rng.choices(sessions, k=len(sessions))  # NOSONAR
        attempted += 1
        sampled = [row for session in drawn_sessions for row in grouped[session]]
        fit = encompassing_ols(sampled)
        if fit.status == "OK" and fit.enc_b is not None and math.isfinite(fit.enc_b):
            values.append(fit.enc_b)
    if len(values) != required:
        return BootstrapResult(
            attempted,
            len(values),
            attempted - len(values),
            None,
            None,
            True,
        )
    values.sort()
    return BootstrapResult(
        attempted,
        required,
        attempted - required,
        percentile_interval(values, 0.999),
        percentile_interval(values, 0.95),
        False,
    )


def bootstrap_gate_mean(
    rows: Sequence[RegressionWindow],
    differences: Sequence[float],
    *,
    required: int = BOOTSTRAP_RESAMPLES,
    max_attempts: int = BOOTSTRAP_MAX_ATTEMPTS,
) -> BootstrapResult:
    _validate_bootstrap_limits(required, max_attempts)
    if len(rows) != len(differences):
        raise ValueError("gate row and difference lengths differ")
    grouped: MutableMapping[str, list[float]] = {}
    for row, difference in zip(rows, differences):
        value = finite(difference)
        if value is None:
            raise ValueError("non-finite gate difference")
        grouped.setdefault(row.session_date.isoformat(), []).append(value)
    sessions = sorted(grouped)
    if not sessions:
        return BootstrapResult(0, 0, 0, None, None, True)
    rng = random.Random(BOOTSTRAP_SEED)
    values: list[float] = []
    attempted = 0
    while len(values) < required and attempted < max_attempts:
        # NOSONAR: frozen deterministic statistical bootstrap, not a security use.
        drawn_sessions = rng.choices(sessions, k=len(sessions))  # NOSONAR
        attempted += 1
        drawn = [value for session in drawn_sessions for value in grouped[session]]
        try:
            candidate = math.fsum(drawn) / len(drawn)
        except (ArithmeticError, OverflowError, ValueError):
            continue
        if math.isfinite(candidate):
            values.append(candidate)
    if len(values) != required:
        return BootstrapResult(
            attempted,
            len(values),
            attempted - len(values),
            None,
            None,
            True,
        )
    values.sort()
    return BootstrapResult(
        attempted,
        required,
        attempted - required,
        percentile_interval(values, 0.999),
        percentile_interval(values, 0.95),
        False,
    )


def descriptive_metrics(population: CellPopulation) -> DescriptiveMetrics:
    windows = population.windows
    if not windows:
        return DescriptiveMetrics.null()
    forecasts = [float(window.predicted_volatility_bps) for window in windows]
    outcomes = [float(window.realized_volatility_bps) for window in windows]
    try:
        mae = math.fsum(
            abs(forecast - outcome)
            for forecast, outcome in zip(forecasts, outcomes)
        ) / len(windows)
        forecast_median = _median_binary64(forecasts)
        outcome_median = _median_binary64(outcomes)
        # Preserve the frozen exact-zero rule (including negative zero) without
        # using a floating-point equality comparison.
        zero_outcome = outcome_median.hex() in {"0x0.0p+0", "-0x0.0p+0"}
        level_ratio = None if zero_outcome else forecast_median / outcome_median
        coverage = math.fsum(
            1.0 if outcome <= NORMAL_90 * forecast else 0.0
            for forecast, outcome in zip(forecasts, outcomes)
        ) / len(windows)
    except (ArithmeticError, OverflowError, ValueError) as error:
        raise ProtocolDefect("descriptive arithmetic failure") from error
    required_finite = [mae, coverage]
    if level_ratio is not None:
        required_finite.append(level_ratio)
    if not all(math.isfinite(value) for value in required_finite):
        raise ProtocolDefect("descriptive arithmetic nonfinite")
    mz = mz_fit(forecasts, outcomes)
    regression = population.regression
    unconditional = tuple(row for row in regression if row.unconditional is not None)
    seasonal = tuple(row for row in regression if row.seasonal is not None)
    return DescriptiveMetrics(
        mae_bps=mae,
        rank_corr=spearman(forecasts, outcomes),
        level_ratio=level_ratio,
        coverage_90=coverage,
        mz_a=mz.a,
        mz_b=mz.b,
        mz_r2=mz.r2,
        persist_rank_corr=spearman(
            [row.persist_20 for row in regression],
            [row.window.realized_volatility_bps for row in regression],
        ),
        unconditional_rank_corr=spearman(
            [float(row.unconditional) for row in unconditional],
            [row.window.realized_volatility_bps for row in unconditional],
        ),
        seasonal_rank_corr=spearman(
            [float(row.seasonal) for row in seasonal],
            [row.window.realized_volatility_bps for row in seasonal],
        ),
    )


def gate_loss_data(
    rows: Sequence[RegressionWindow], benchmark: str
) -> GateLossData:
    if benchmark not in ("unconditional", "seasonal"):
        raise ValueError("invalid benchmark")
    selected: list[RegressionWindow] = []
    candidate_losses: list[float] = []
    benchmark_losses: list[float] = []
    differences: list[float] = []
    for row in rows:
        benchmark_value = getattr(row, benchmark)
        if benchmark_value is None:
            continue
        candidate_loss = qlike(
            row.window.realized_volatility_bps,
            row.window.predicted_volatility_bps,
        )
        benchmark_loss = qlike(
            row.window.realized_volatility_bps, float(benchmark_value)
        )
        difference = benchmark_loss - candidate_loss
        if not all(
            math.isfinite(value)
            for value in (candidate_loss, benchmark_loss, difference)
        ):
            raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE")
        selected.append(row)
        candidate_losses.append(candidate_loss)
        benchmark_losses.append(benchmark_loss)
        differences.append(difference)
    if not selected:
        return GateLossData((), (), (), (), None, None, None)
    try:
        candidate_mean = math.fsum(candidate_losses) / len(candidate_losses)
        benchmark_mean = math.fsum(benchmark_losses) / len(benchmark_losses)
        difference_mean = math.fsum(differences) / len(differences)
    except (ArithmeticError, OverflowError, ValueError) as error:
        raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE") from error
    if not all(
        math.isfinite(value)
        for value in (candidate_mean, benchmark_mean, difference_mean)
    ):
        raise ArithmeticError("QLIKE_ARITHMETIC_NONFINITE")
    return GateLossData(
        tuple(selected),
        tuple(candidate_losses),
        tuple(benchmark_losses),
        tuple(differences),
        candidate_mean,
        benchmark_mean,
        difference_mean,
    )


@dataclass(frozen=True, slots=True)
class ReadinessCounts:
    spec: CellSpec
    n_regression_windows: int
    n_regression_sessions: int
    n_unconditional_gate_windows: int
    n_unconditional_gate_sessions: int
    n_seasonal_gate_windows: int
    n_seasonal_gate_sessions: int

    def __post_init__(self) -> None:
        validate_cell_spec(self.spec)
        values = (
            self.n_regression_windows,
            self.n_regression_sessions,
            self.n_unconditional_gate_windows,
            self.n_unconditional_gate_sessions,
            self.n_seasonal_gate_windows,
            self.n_seasonal_gate_sessions,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        ):
            raise ProtocolDefect("readiness count domain failure")

    @property
    def all_minima_pass(self) -> bool:
        return (
            self.n_regression_windows >= MIN_WINDOWS
            and self.n_regression_sessions >= MIN_SESSIONS
            and self.n_unconditional_gate_windows >= MIN_WINDOWS
            and self.n_unconditional_gate_sessions >= MIN_SESSIONS
            and self.n_seasonal_gate_windows >= MIN_WINDOWS
            and self.n_seasonal_gate_sessions >= MIN_SESSIONS
        )

    def public(self, *, require_ready: bool = False) -> dict[str, object]:
        if require_ready and not self.all_minima_pass:
            raise ProtocolDefect("failing count in READY object")
        return {
            **self.spec.public(),
            "n_regression_windows": self.n_regression_windows,
            "n_regression_sessions": self.n_regression_sessions,
            "n_unconditional_gate_windows": self.n_unconditional_gate_windows,
            "n_unconditional_gate_sessions": self.n_unconditional_gate_sessions,
            "n_seasonal_gate_windows": self.n_seasonal_gate_windows,
            "n_seasonal_gate_sessions": self.n_seasonal_gate_sessions,
            "all_minima_pass": self.all_minima_pass,
        }


def readiness_counts(population: CellPopulation) -> ReadinessCounts:
    population.validate()
    regression = population.regression
    unconditional = tuple(row for row in regression if row.unconditional is not None)
    seasonal = tuple(row for row in regression if row.seasonal is not None)
    return ReadinessCounts(
        spec=population.spec,
        n_regression_windows=len(regression),
        n_regression_sessions=len({row.session_date for row in regression}),
        n_unconditional_gate_windows=len(unconditional),
        n_unconditional_gate_sessions=len({row.session_date for row in unconditional}),
        n_seasonal_gate_windows=len(seasonal),
        n_seasonal_gate_sessions=len({row.session_date for row in seasonal}),
    )


def manifest_is_ready(
    manifest_id: str, counts: Sequence[ReadinessCounts]
) -> bool:
    expected = manifest_cells(manifest_id)
    if tuple(item.spec for item in counts) != expected:
        raise ProtocolDefect("manifest readiness count identity/order mismatch")
    return all(item.all_minima_pass for item in counts)


def insufficient_reason_codes(counts: ReadinessCounts) -> list[str]:
    reasons: list[str] = []
    checks = (
        (
            counts.n_regression_windows < MIN_WINDOWS,
            "INSUFFICIENT_REGRESSION_WINDOWS",
        ),
        (
            counts.n_regression_sessions < MIN_SESSIONS,
            "INSUFFICIENT_REGRESSION_SESSIONS",
        ),
        (
            counts.n_unconditional_gate_windows < MIN_WINDOWS,
            "INSUFFICIENT_UNCONDITIONAL_GATE_WINDOWS",
        ),
        (
            counts.n_unconditional_gate_sessions < MIN_SESSIONS,
            "INSUFFICIENT_UNCONDITIONAL_GATE_SESSIONS",
        ),
        (
            counts.n_seasonal_gate_windows < MIN_WINDOWS,
            "INSUFFICIENT_SEASONAL_GATE_WINDOWS",
        ),
        (
            counts.n_seasonal_gate_sessions < MIN_SESSIONS,
            "INSUFFICIENT_SEASONAL_GATE_SESSIONS",
        ),
    )
    reasons.extend(reason for failed, reason in checks if failed)
    return sorted(reasons)


_ANALYTIC_FIELDS = (
    "mae_bps",
    "rank_corr",
    "level_ratio",
    "coverage_90",
    "mz_a",
    "mz_b",
    "mz_r2",
    "persist_rank_corr",
    "enc_b",
    "enc_b_ci_0999",
    "enc_b_ci_095",
    "unconditional_rank_corr",
    "seasonal_rank_corr",
    "qlike_candidate",
    "qlike_unconditional",
    "qlike_seasonal",
    "d_unconditional",
    "d_unconditional_ci_0999",
    "d_unconditional_ci_095",
    "d_seasonal",
    "d_seasonal_ci_0999",
    "d_seasonal_ci_095",
)


def _structural_cell(population: CellPopulation) -> dict[str, object]:
    windows = population.windows
    session_dates = sorted({window.session_date.isoformat() for window in windows})
    cutoffs = [window.cutoff_at for window in windows]
    counts = readiness_counts(population)
    return {
        **population.spec.public(),
        "lineage_identity": dict(population.lineage_identity),
        "session_dates": session_dates,
        "evidence_min_cutoff_at": timestamp_utc(min(cutoffs)) if cutoffs else None,
        "evidence_max_cutoff_at": timestamp_utc(max(cutoffs)) if cutoffs else None,
        "n_input": population.n_input,
        "n_unselected_lineage_rows": population.n_unselected_lineage_rows,
        "n_inadmissible": population.n_inadmissible,
        "n_non_rth": population.n_non_rth,
        "n_overlap_excluded": population.n_overlap_excluded,
        "n_null_or_nonfinite_excluded": population.n_null_or_nonfinite_excluded,
        "n_nonpositive_prediction_excluded": (
            population.n_nonpositive_prediction_excluded
        ),
        "n_kappa_unavailable": population.n_kappa_unavailable,
        "n_windows": len(windows),
        "n_sessions": len(session_dates),
        "n_persist20_unavailable": population.n_persist20_unavailable,
        "n_regression_windows": counts.n_regression_windows,
        "n_regression_sessions": counts.n_regression_sessions,
        "n_unconditional_unavailable": population.n_unconditional_unavailable,
        "n_unconditional_gate_windows": counts.n_unconditional_gate_windows,
        "n_unconditional_gate_sessions": counts.n_unconditional_gate_sessions,
        "n_seasonal_gate_windows": counts.n_seasonal_gate_windows,
        "n_seasonal_gate_sessions": counts.n_seasonal_gate_sessions,
    }


def _bootstrap_fields(
    enc: BootstrapResult,
    unconditional: BootstrapResult,
    seasonal: BootstrapResult,
) -> dict[str, int]:
    return {
        "bootstrap_attempted_draws": enc.attempted,
        "bootstrap_valid_draws": enc.valid,
        "bootstrap_invalid_draws": enc.invalid,
        "unconditional_bootstrap_attempted_draws": unconditional.attempted,
        "unconditional_bootstrap_valid_draws": unconditional.valid,
        "unconditional_bootstrap_invalid_draws": unconditional.invalid,
        "seasonal_bootstrap_attempted_draws": seasonal.attempted,
        "seasonal_bootstrap_valid_draws": seasonal.valid,
        "seasonal_bootstrap_invalid_draws": seasonal.invalid,
    }


def _invalid_cell(
    population: CellPopulation,
    reason_codes: Sequence[str],
    *,
    enc_bootstrap: BootstrapResult | None = None,
    unconditional_bootstrap: BootstrapResult | None = None,
    seasonal_bootstrap: BootstrapResult | None = None,
) -> dict[str, object]:
    result = _structural_cell(population)
    result.update({field: None for field in _ANALYTIC_FIELDS})
    enc = enc_bootstrap or BootstrapResult.zero()
    unconditional = unconditional_bootstrap or BootstrapResult.zero()
    seasonal = seasonal_bootstrap or BootstrapResult.zero()
    result.update(_bootstrap_fields(enc, unconditional, seasonal))
    result["gate_unconditional"] = (
        "UNAVAILABLE" if result["n_unconditional_gate_windows"] == 0 else "NOT_RUN"
    )
    result["gate_seasonal"] = (
        "UNAVAILABLE" if result["n_seasonal_gate_windows"] == 0 else "NOT_RUN"
    )
    result["classification"] = "INVALID"
    result["reason_codes"] = sorted(set(reason_codes))
    return result


def _descriptive_fields(metrics: DescriptiveMetrics) -> dict[str, float | None]:
    return {
        "mae_bps": metrics.mae_bps,
        "rank_corr": metrics.rank_corr,
        "level_ratio": metrics.level_ratio,
        "coverage_90": metrics.coverage_90,
        "mz_a": metrics.mz_a,
        "mz_b": metrics.mz_b,
        "mz_r2": metrics.mz_r2,
        "persist_rank_corr": metrics.persist_rank_corr,
        "unconditional_rank_corr": metrics.unconditional_rank_corr,
        "seasonal_rank_corr": metrics.seasonal_rank_corr,
    }


def evaluate_cell(
    population: CellPopulation,
    *,
    preinspected_confirmatory_statistic: bool = False,
) -> dict[str, object]:
    """Evaluate one already sealed cell under V-1A §11 precedence.

    The official bootstrap constants are intentionally not parameters of this
    entry point.  Tests of bootstrap mechanics may call the individual pure
    bootstrap helpers with smaller explicit limits.
    """

    population.validate()
    rule_one_reasons: list[str] = []
    if population.protocol_defect:
        rule_one_reasons.append("CELL_PROTOCOL_DEFECT")
    if preinspected_confirmatory_statistic:
        rule_one_reasons.append("PREINSPECTED_CONFIRMATORY_STATISTIC")
    if rule_one_reasons:
        return _invalid_cell(population, rule_one_reasons)

    counts = readiness_counts(population)
    try:
        metrics = descriptive_metrics(population)
    except ProtocolDefect:
        return _invalid_cell(population, ["CELL_PROTOCOL_DEFECT"])

    result = _structural_cell(population)
    result.update(_descriptive_fields(metrics))
    if not counts.all_minima_pass:
        for field in _ANALYTIC_FIELDS:
            result.setdefault(field, None)
        result.update(
            _bootstrap_fields(
                BootstrapResult.zero(),
                BootstrapResult.zero(),
                BootstrapResult.zero(),
            )
        )
        result["gate_unconditional"] = (
            "UNAVAILABLE" if counts.n_unconditional_gate_windows == 0 else "NOT_RUN"
        )
        result["gate_seasonal"] = (
            "UNAVAILABLE" if counts.n_seasonal_gate_windows == 0 else "NOT_RUN"
        )
        result["classification"] = "INSUFFICIENT"
        result["reason_codes"] = insufficient_reason_codes(counts)
        return result

    fit = encompassing_ols(population.regression)
    if fit.status != "OK":
        reason = (
            "FULL_SAMPLE_OLS_RANK_DEFICIENT"
            if fit.status == "RANK_DEFICIENT"
            else "FULL_SAMPLE_OLS_NONFINITE"
        )
        return _invalid_cell(population, [reason])

    try:
        unconditional_losses = gate_loss_data(population.regression, "unconditional")
        seasonal_losses = gate_loss_data(population.regression, "seasonal")
    except (ArithmeticError, OverflowError, ValueError):
        return _invalid_cell(population, ["QLIKE_ARITHMETIC_NONFINITE"])
    if unconditional_losses.rows != seasonal_losses.rows:
        return _invalid_cell(population, ["CELL_PROTOCOL_DEFECT"])

    enc_bootstrap = bootstrap_enc_b(population.regression)
    if enc_bootstrap.exhausted:
        return _invalid_cell(
            population,
            ["ENC_B_BOOTSTRAP_EXHAUSTED"],
            enc_bootstrap=enc_bootstrap,
        )
    unconditional_bootstrap = bootstrap_gate_mean(
        unconditional_losses.rows, unconditional_losses.differences
    )
    if unconditional_bootstrap.exhausted:
        return _invalid_cell(
            population,
            ["UNCONDITIONAL_GATE_BOOTSTRAP_EXHAUSTED"],
            enc_bootstrap=enc_bootstrap,
            unconditional_bootstrap=unconditional_bootstrap,
        )
    seasonal_bootstrap = bootstrap_gate_mean(
        seasonal_losses.rows, seasonal_losses.differences
    )
    if seasonal_bootstrap.exhausted:
        return _invalid_cell(
            population,
            ["SEASONAL_GATE_BOOTSTRAP_EXHAUSTED"],
            enc_bootstrap=enc_bootstrap,
            unconditional_bootstrap=unconditional_bootstrap,
            seasonal_bootstrap=seasonal_bootstrap,
        )

    assert enc_bootstrap.ci_0999 is not None
    assert enc_bootstrap.ci_095 is not None
    assert unconditional_bootstrap.ci_0999 is not None
    assert unconditional_bootstrap.ci_095 is not None
    assert seasonal_bootstrap.ci_0999 is not None
    assert seasonal_bootstrap.ci_095 is not None
    gate_unconditional = (
        "PASS" if unconditional_bootstrap.ci_0999[0] > 0 else "FAIL"
    )
    gate_seasonal = "PASS" if seasonal_bootstrap.ci_0999[0] > 0 else "FAIL"
    informative = (
        enc_bootstrap.ci_0999[0] > 0
        and gate_unconditional == "PASS"
        and gate_seasonal == "PASS"
    )
    classification = "INFORMATIVE" if informative else "NOISE"
    reasons: list[str] = []
    if not informative:
        if enc_bootstrap.ci_0999[0] <= 0:
            reasons.append("ENC_B_NOT_POSITIVE")
        if gate_unconditional == "FAIL":
            reasons.append("FAILED_UNCONDITIONAL_GATE")
        if gate_seasonal == "FAIL":
            reasons.append("FAILED_SEASONAL_GATE")

    result.update(
        {
            "enc_b": fit.enc_b,
            "enc_b_ci_0999": list(enc_bootstrap.ci_0999),
            "enc_b_ci_095": list(enc_bootstrap.ci_095),
            "qlike_candidate": unconditional_losses.candidate_mean,
            "qlike_unconditional": unconditional_losses.benchmark_mean,
            "qlike_seasonal": seasonal_losses.benchmark_mean,
            "d_unconditional": unconditional_losses.difference_mean,
            "d_unconditional_ci_0999": list(
                unconditional_bootstrap.ci_0999
            ),
            "d_unconditional_ci_095": list(unconditional_bootstrap.ci_095),
            "d_seasonal": seasonal_losses.difference_mean,
            "d_seasonal_ci_0999": list(seasonal_bootstrap.ci_0999),
            "d_seasonal_ci_095": list(seasonal_bootstrap.ci_095),
            **_bootstrap_fields(
                enc_bootstrap, unconditional_bootstrap, seasonal_bootstrap
            ),
            "gate_unconditional": gate_unconditional,
            "gate_seasonal": gate_seasonal,
            "classification": classification,
            "reason_codes": sorted(reasons),
        }
    )
    return result


def overall_verdict(
    cells: Sequence[Mapping[str, object]], *, run_protocol_defect: bool = False
) -> tuple[str, list[str]]:
    classifications = [cell.get("classification") for cell in cells]
    if any(
        value not in {"INFORMATIVE", "NOISE", "INSUFFICIENT", "INVALID"}
        for value in classifications
    ):
        raise ProtocolDefect("invalid cell classification")
    invalid_cell = "INVALID" in classifications
    if invalid_cell or run_protocol_defect:
        reasons: list[str] = []
        if invalid_cell:
            reasons.append("INVALID_CELL_PRESENT")
        if run_protocol_defect:
            reasons.append("RUN_PROTOCOL_DEFECT")
        return "INVALID", sorted(reasons)
    if "INFORMATIVE" in classifications:
        return "PASS", []
    return "FAIL", ["NO_INFORMATIVE_CELL"]


# Amendment 3 startup/runtime/provenance command and measurement contract.
PYTHON_VERSION_ENV = "PYTHON_VERSION"
EXPECTED_PYTHON_VERSION = (3, 14, 3)
EXPECTED_PYTHON_VERSION_TEXT = "3.14.3"
PYCACHE_PREFIX = "/dev/null/atom-v1b-no-pyc"
ISOLATED_PYTHON_ARGS = (
    "-I", "-S", "-B", "-X", "pycache_prefix=/dev/null/atom-v1b-no-pyc",
)
RUNTIME_COMPONENT_KEYS = (
    "python_executable_sha256",
    "stdlib_tree_sha256",
    "dependency_tree_sha256",
    "loaded_native_tree_sha256",
)
MANIFEST_IDS = (
    "v1b-early-4",
    "v1b-family-5m",
    "v1b-family-15m",
    "v1b-family-30m",
    "v1b-family-1h",
    "v1b-v9-5m",
    "v1b-v9-15m",
    "v1b-v9-30m",
    "v1b-v9-1h",
)
RECOVERY_CHILD_C_LEN = 3092
RECOVERY_CHILD_HEX_LEN = 6184
RECOVERY_CHILD_C_SHA256 = (
    "f79378de92204cfec2fe4818c341cc23b5dfb685179f05e5722441ce9a608d62"
)
BOOTSTRAP_HOOK_PREFIX = (
    "import sys;sys.excepthook=sys.unraisablehook=lambda *_:None;"
)
PROBE_C_BODY_LEN = 3100
PROBE_C_BODY_SHA256 = (
    "e4907f41ac3c60efdfe7874677d0214ccca0eab9f0ab6d56820b47633eefc143"
)

# These three strings are copied byte-for-byte from the frozen Amendment 3
# command blocks.  Do not generate or normalize them.
PROBE_START_COMMAND = "python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; j=tuple(sys.path); q=os.path.join(sys.base_prefix,sys.platlibdir,\"python314.zip\"); u=os.path.join(sys.base_prefix,sys.platlibdir,\"python3.14\"); t=os.path.join(sys.base_exec_prefix,sys.platlibdir,\"python3.14\"); y=os.path.join(t,\"lib-dynload\"); r=os.getcwd(); z=\"/etc/ld.so.preload\"; b=any((k.startswith(\"PYTHON\") and k!=\"PYTHON_VERSION\") or k.startswith((\"_PYTHON\",\"LD_\",\"DYLD_\",\"BASH\",\"GIT_\",\"OPENSSL_\")) or k in {\"ENV\",\"SHELLOPTS\",\"PS4\",\"KSHENV\",\"ZDOTDIR\",\"GCONV_PATH\",\"GLIBC_TUNABLES\",\"HTTP_PROXY\",\"HTTPS_PROXY\",\"ALL_PROXY\",\"NO_PROXY\",\"http_proxy\",\"https_proxy\",\"all_proxy\",\"no_proxy\",\"SSL_CERT_FILE\",\"SSL_CERT_DIR\",\"SSLKEYLOGFILE\",\"REQUESTS_CA_BUNDLE\",\"CURL_CA_BUNDLE\"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix==\"/dev/null/atom-v1b-no-pyc\" and sys.version_info[:3]==(3,14,3) and os.environ.get(\"PYTHON_VERSION\")==\"3.14.3\" and sys.__spec__.origin==\"built-in\" and os.__spec__.origin==\"frozen\" and os.path.__spec__.origin==\"frozen\" and not b and not os.path.lexists(z) and not {\"site\",\"sitecustomize\",\"usercustomize\"}.intersection(sys.modules) and not any(n==\"quant\" or n.startswith(\"quant.\") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and j==(q,u,y) and all(os.path.isabs(v) and os.path.realpath(v)==v for v in (q,u,t,y)) and not os.path.lexists(q) and all(os.path.isdir(v) for v in (u,t,y))); o or (_ for _ in ()).throw(SystemExit(1)); sys.path[:]=[u,y]; sys.path_importer_cache.pop(q,None); i=tuple(sys.path); i==(u,y) or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme(\"prefix\")); a=tuple(dict.fromkeys((r,os.path.realpath(p[\"purelib\"]),os.path.realpath(p[\"platlib\"])))); d=os.path.join(r,\"quant\"); v=os.path.join(d,\"volatility_scorecard.py\"); x=os.path.realpath(sys.executable); w=shutil.which(\"python\"); o=(os.path.realpath(p[\"stdlib\"])==u and os.path.realpath(p[\"platstdlib\"])==t and all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath(\"/proc/self/exe\") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat(\"/dev/null\",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec(\"quant\",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules[\"quant\"]=importlib.util.module_from_spec(s); from quant.volatility_scorecard import provenance_probe_main; raise SystemExit(provenance_probe_main())'"
NORMAL_START_COMMAND_BOOTSTRAP = "python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; j=tuple(sys.path); q=os.path.join(sys.base_prefix,sys.platlibdir,\"python314.zip\"); u=os.path.join(sys.base_prefix,sys.platlibdir,\"python3.14\"); t=os.path.join(sys.base_exec_prefix,sys.platlibdir,\"python3.14\"); y=os.path.join(t,\"lib-dynload\"); r=os.getcwd(); z=\"/etc/ld.so.preload\"; b=any((k.startswith(\"PYTHON\") and k!=\"PYTHON_VERSION\") or k.startswith((\"_PYTHON\",\"LD_\",\"DYLD_\",\"BASH\",\"GIT_\",\"OPENSSL_\")) or k in {\"ENV\",\"SHELLOPTS\",\"PS4\",\"KSHENV\",\"ZDOTDIR\",\"GCONV_PATH\",\"GLIBC_TUNABLES\",\"HTTP_PROXY\",\"HTTPS_PROXY\",\"ALL_PROXY\",\"NO_PROXY\",\"http_proxy\",\"https_proxy\",\"all_proxy\",\"no_proxy\",\"SSL_CERT_FILE\",\"SSL_CERT_DIR\",\"SSLKEYLOGFILE\",\"REQUESTS_CA_BUNDLE\",\"CURL_CA_BUNDLE\"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix==\"/dev/null/atom-v1b-no-pyc\" and sys.version_info[:3]==(3,14,3) and os.environ.get(\"PYTHON_VERSION\")==\"3.14.3\" and sys.__spec__.origin==\"built-in\" and os.__spec__.origin==\"frozen\" and os.path.__spec__.origin==\"frozen\" and not b and not os.path.lexists(z) and not {\"site\",\"sitecustomize\",\"usercustomize\"}.intersection(sys.modules) and not any(n==\"quant\" or n.startswith(\"quant.\") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and j==(q,u,y) and all(os.path.isabs(v) and os.path.realpath(v)==v for v in (q,u,t,y)) and not os.path.lexists(q) and all(os.path.isdir(v) for v in (u,t,y))); o or (_ for _ in ()).throw(SystemExit(1)); sys.path[:]=[u,y]; sys.path_importer_cache.pop(q,None); i=tuple(sys.path); i==(u,y) or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme(\"prefix\")); a=tuple(dict.fromkeys((r,os.path.realpath(p[\"purelib\"]),os.path.realpath(p[\"platlib\"])))); d=os.path.join(r,\"quant\"); v=os.path.join(d,\"volatility_scorecard.py\"); x=os.path.realpath(sys.executable); w=shutil.which(\"python\"); o=(os.path.realpath(p[\"stdlib\"])==u and os.path.realpath(p[\"platstdlib\"])==t and all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath(\"/proc/self/exe\") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat(\"/dev/null\",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec(\"quant\",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules[\"quant\"]=importlib.util.module_from_spec(s); import runpy; runpy.run_module(\"quant.volatility_scorecard\",run_name=\"__main__\",alter_sys=True)'"
RECOVERY_START_COMMAND_TEMPLATE = "python -I -S -B -X pycache_prefix=/dev/null/atom-v1b-no-pyc -c 'import os,sys; e=frozenset(os.environ); f=sys.flags; j=tuple(sys.path); q=os.path.join(sys.base_prefix,sys.platlibdir,\"python314.zip\"); u=os.path.join(sys.base_prefix,sys.platlibdir,\"python3.14\"); t=os.path.join(sys.base_exec_prefix,sys.platlibdir,\"python3.14\"); y=os.path.join(t,\"lib-dynload\"); r=os.getcwd(); z=\"/etc/ld.so.preload\"; b=any((k.startswith(\"PYTHON\") and k!=\"PYTHON_VERSION\") or k.startswith((\"_PYTHON\",\"LD_\",\"DYLD_\",\"BASH\",\"GIT_\",\"OPENSSL_\")) or k in {\"ENV\",\"SHELLOPTS\",\"PS4\",\"KSHENV\",\"ZDOTDIR\",\"GCONV_PATH\",\"GLIBC_TUNABLES\",\"HTTP_PROXY\",\"HTTPS_PROXY\",\"ALL_PROXY\",\"NO_PROXY\",\"http_proxy\",\"https_proxy\",\"all_proxy\",\"no_proxy\",\"SSL_CERT_FILE\",\"SSL_CERT_DIR\",\"SSLKEYLOGFILE\",\"REQUESTS_CA_BUNDLE\",\"CURL_CA_BUNDLE\"} for k in e); o=(f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix==\"/dev/null/atom-v1b-no-pyc\" and sys.version_info[:3]==(3,14,3) and os.environ.get(\"PYTHON_VERSION\")==\"3.14.3\" and sys.__spec__.origin==\"built-in\" and os.__spec__.origin==\"frozen\" and os.path.__spec__.origin==\"frozen\" and not b and not os.path.lexists(z) and not {\"site\",\"sitecustomize\",\"usercustomize\"}.intersection(sys.modules) and not any(n==\"quant\" or n.startswith(\"quant.\") for n in sys.modules) and os.path.isabs(r) and os.path.realpath(r)==r and j==(q,u,y) and all(os.path.isabs(v) and os.path.realpath(v)==v for v in (q,u,t,y)) and not os.path.lexists(q) and all(os.path.isdir(v) for v in (u,t,y))); o or (_ for _ in ()).throw(SystemExit(1)); sys.path[:]=[u,y]; sys.path_importer_cache.pop(q,None); i=tuple(sys.path); i==(u,y) or (_ for _ in ()).throw(SystemExit(1)); import importlib.machinery,importlib.util,shutil,stat,sysconfig; p=sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme(\"prefix\")); a=tuple(dict.fromkeys((r,os.path.realpath(p[\"purelib\"]),os.path.realpath(p[\"platlib\"])))); d=os.path.join(r,\"quant\"); v=os.path.join(d,\"volatility_scorecard.py\"); x=os.path.realpath(sys.executable); w=shutil.which(\"python\"); o=(os.path.realpath(p[\"stdlib\"])==u and os.path.realpath(p[\"platstdlib\"])==t and all(os.path.isabs(t) and os.path.realpath(t)==t and os.path.isdir(t) for t in a) and not set(a).intersection(i) and os.path.realpath(d)==d and stat.S_ISDIR(os.stat(d,follow_symlinks=False).st_mode) and os.path.realpath(v)==v and stat.S_ISREG(os.stat(v,follow_symlinks=False).st_mode) and w is not None and os.path.isabs(w) and os.path.realpath(w)==x==os.path.realpath(\"/proc/self/exe\") and stat.S_ISREG(os.stat(x,follow_symlinks=False).st_mode) and os.access(x,os.X_OK) and stat.S_ISCHR(os.stat(\"/dev/null\",follow_symlinks=False).st_mode)); o or (_ for _ in ()).throw(SystemExit(1)); sys.path.extend(a); tuple(sys.path)==i+a or (_ for _ in ()).throw(SystemExit(1)); s=importlib.machinery.ModuleSpec(\"quant\",loader=None,is_package=True); s.submodule_search_locations=[d]; sys.modules[\"quant\"]=importlib.util.module_from_spec(s); D=\"/tmp/atom-v1b-seals\"; os.mkdir(D,0o700); P=D+\"/<seal_record_sha256>.json\"; F=os.open(P,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); H=os.fdopen(F,\"wb\"); H.write(bytes.fromhex(\"<seal_bytes_hex>\")); H.close(); Q=bytes.fromhex(\"696d706f7274206f732c7379733b20653d66726f7a656e736574286f732e656e7669726f6e293b20663d7379732e666c6167733b206a3d7475706c65287379732e70617468293b20713d6f732e706174682e6a6f696e287379732e626173655f7072656669782c7379732e706c61746c69626469722c22707974686f6e3331342e7a697022293b20753d6f732e706174682e6a6f696e287379732e626173655f7072656669782c7379732e706c61746c69626469722c22707974686f6e332e313422293b20743d6f732e706174682e6a6f696e287379732e626173655f657865635f7072656669782c7379732e706c61746c69626469722c22707974686f6e332e313422293b20793d6f732e706174682e6a6f696e28742c226c69622d64796e6c6f616422293b20723d6f732e67657463776428293b207a3d222f6574632f6c642e736f2e7072656c6f6164223b20623d616e7928286b2e737461727473776974682822505954484f4e222920616e64206b213d22505954484f4e5f56455253494f4e2229206f72206b2e737461727473776974682828225f505954484f4e222c224c445f222c2244594c445f222c2242415348222c224749545f222c224f50454e53534c5f222929206f72206b20696e207b22454e56222c225348454c4c4f505453222c22505334222c224b5348454e56222c225a444f54444952222c2247434f4e565f50415448222c22474c4942435f54554e41424c4553222c22485454505f50524f5859222c2248545450535f50524f5859222c22414c4c5f50524f5859222c224e4f5f50524f5859222c22687474705f70726f7879222c2268747470735f70726f7879222c22616c6c5f70726f7879222c226e6f5f70726f7879222c2253534c5f434552545f46494c45222c2253534c5f434552545f444952222c2253534c4b45594c4f4746494c45222c2252455155455354535f43415f42554e444c45222c224355524c5f43415f42554e444c45227d20666f72206b20696e2065293b206f3d28662e69736f6c617465643d3d3120616e6420662e69676e6f72655f656e7669726f6e6d656e743d3d3120616e6420662e6e6f5f757365725f736974653d3d3120616e6420662e6e6f5f736974653d3d3120616e6420662e736166655f7061746820616e64207379732e646f6e745f77726974655f62797465636f646520616e64207379732e707963616368655f7072656669783d3d222f6465762f6e756c6c2f61746f6d2d7631622d6e6f2d7079632220616e64207379732e76657273696f6e5f696e666f5b3a335d3d3d28332c31342c332920616e64206f732e656e7669726f6e2e6765742822505954484f4e5f56455253494f4e22293d3d22332e31342e332220616e64207379732e5f5f737065635f5f2e6f726967696e3d3d226275696c742d696e2220616e64206f732e5f5f737065635f5f2e6f726967696e3d3d2266726f7a656e2220616e64206f732e706174682e5f5f737065635f5f2e6f726967696e3d3d2266726f7a656e2220616e64206e6f74206220616e64206e6f74206f732e706174682e6c657869737473287a2920616e64206e6f74207b2273697465222c2273697465637573746f6d697a65222c2275736572637573746f6d697a65227d2e696e74657273656374696f6e287379732e6d6f64756c65732920616e64206e6f7420616e79286e3d3d227175616e7422206f72206e2e7374617274737769746828227175616e742e222920666f72206e20696e207379732e6d6f64756c65732920616e64206f732e706174682e697361627328722920616e64206f732e706174682e7265616c706174682872293d3d7220616e64206a3d3d28712c752c792920616e6420616c6c286f732e706174682e697361627328762920616e64206f732e706174682e7265616c706174682876293d3d7620666f72207620696e2028712c752c742c79292920616e64206e6f74206f732e706174682e6c65786973747328712920616e6420616c6c286f732e706174682e697364697228762920666f72207620696e2028752c742c792929293b206f206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b207379732e706174685b3a5d3d5b752c795d3b207379732e706174685f696d706f727465725f63616368652e706f7028712c4e6f6e65293b20693d7475706c65287379732e70617468293b20693d3d28752c7929206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b20696d706f727420696d706f72746c69622e6d616368696e6572792c696d706f72746c69622e7574696c2c73687574696c2c737461742c737973636f6e6669673b20703d737973636f6e6669672e6765745f706174687328736368656d653d737973636f6e6669672e6765745f7072656665727265645f736368656d6528227072656669782229293b20613d7475706c6528646963742e66726f6d6b6579732828722c6f732e706174682e7265616c7061746828705b22707572656c6962225d292c6f732e706174682e7265616c7061746828705b22706c61746c6962225d292929293b20643d6f732e706174682e6a6f696e28722c227175616e7422293b20763d6f732e706174682e6a6f696e28642c22766f6c6174696c6974795f73636f7265636172642e707922293b20783d6f732e706174682e7265616c70617468287379732e65786563757461626c65293b20773d73687574696c2e77686963682822707974686f6e22293b206f3d286f732e706174682e7265616c7061746828705b227374646c6962225d293d3d7520616e64206f732e706174682e7265616c7061746828705b22706c61747374646c6962225d293d3d7420616e6420616c6c286f732e706174682e697361627328742920616e64206f732e706174682e7265616c706174682874293d3d7420616e64206f732e706174682e697364697228742920666f72207420696e20612920616e64206e6f74207365742861292e696e74657273656374696f6e28692920616e64206f732e706174682e7265616c706174682864293d3d6420616e6420737461742e535f4953444952286f732e7374617428642c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e64206f732e706174682e7265616c706174682876293d3d7620616e6420737461742e535f4953524547286f732e7374617428762c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e642077206973206e6f74204e6f6e6520616e64206f732e706174682e697361627328772920616e64206f732e706174682e7265616c706174682877293d3d783d3d6f732e706174682e7265616c7061746828222f70726f632f73656c662f657865222920616e6420737461742e535f4953524547286f732e7374617428782c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f64652920616e64206f732e61636365737328782c6f732e585f4f4b2920616e6420737461742e535f4953434852286f732e7374617428222f6465762f6e756c6c222c666f6c6c6f775f73796d6c696e6b733d46616c7365292e73745f6d6f646529293b206f206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b207379732e706174682e657874656e642861293b207475706c65287379732e70617468293d3d692b61206f7220285f20666f72205f20696e202829292e7468726f772853797374656d45786974283129293b20733d696d706f72746c69622e6d616368696e6572792e4d6f64756c655370656328227175616e74222c6c6f616465723d4e6f6e652c69735f7061636b6167653d54727565293b20732e7375626d6f64756c655f7365617263685f6c6f636174696f6e733d5b645d3b207379732e6d6f64756c65735b227175616e74225d3d696d706f72746c69622e7574696c2e6d6f64756c655f66726f6d5f737065632873293b20696d706f72742072756e70793b2072756e70792e72756e5f6d6f64756c6528227175616e742e766f6c6174696c6974795f73636f726563617264222c72756e5f6e616d653d225f5f6d61696e5f5f222c616c7465725f7379733d5472756529\").decode(\"ascii\"); os.execv(sys.executable,[sys.executable,\"-I\",\"-S\",\"-B\",\"-X\",\"pycache_prefix=/dev/null/atom-v1b-no-pyc\",\"-c\",Q,\"--manifest-id\",\"<manifest_id>\",\"--recovery-seal-file\",P])'"

# The three preceding literals are the byte-exact Amendment 3 sources.  Apply
# Amendment 3A's mechanical transformation in the required order: prefix the
# probe and normal source, prefix the decoded child, replace only that child's
# one embedded lowercase hexadecimal occurrence, then prefix the recovery
# outer source.  No command byte other than those transformations changes.
_AMENDMENT_3_PROBE_START_COMMAND = PROBE_START_COMMAND
_AMENDMENT_3_NORMAL_START_COMMAND = NORMAL_START_COMMAND_BOOTSTRAP
_AMENDMENT_3_RECOVERY_START_COMMAND = RECOVERY_START_COMMAND_TEMPLATE
_AMENDMENT_3_NORMAL_C_BODY = tuple(
    shlex.split(_AMENDMENT_3_NORMAL_START_COMMAND, posix=True)
)[7]
_AMENDMENT_3_RECOVERY_Q_MATCH = re.search(
    r'Q=bytes\.fromhex\("([0-9a-f]+)"\)',
    _AMENDMENT_3_RECOVERY_START_COMMAND,
)
if _AMENDMENT_3_RECOVERY_Q_MATCH is None:
    raise ContractError("RECOVERY_CHILD_MISMATCH")
_AMENDMENT_3_RECOVERY_CHILD_HEX = _AMENDMENT_3_RECOVERY_Q_MATCH.group(1)


def _prepend_bootstrap_hook(command: str) -> str:
    marker = "-c '"
    if command.count(marker) != 1:
        raise ContractError("COMMAND_BOOTSTRAP_MISMATCH")
    return command.replace(marker, marker + BOOTSTRAP_HOOK_PREFIX, 1)


PROBE_START_COMMAND = _prepend_bootstrap_hook(
    _AMENDMENT_3_PROBE_START_COMMAND
)
NORMAL_START_COMMAND_BOOTSTRAP = _prepend_bootstrap_hook(
    _AMENDMENT_3_NORMAL_START_COMMAND
)
_TRANSFORMED_RECOVERY_CHILD_HEX = (
    BOOTSTRAP_HOOK_PREFIX + _AMENDMENT_3_NORMAL_C_BODY
).encode("ascii").hex()
_RECOVERY_OUTER_REHEXED = _AMENDMENT_3_RECOVERY_START_COMMAND.replace(
    _AMENDMENT_3_RECOVERY_CHILD_HEX,
    _TRANSFORMED_RECOVERY_CHILD_HEX,
    1,
)
RECOVERY_START_COMMAND_TEMPLATE = _prepend_bootstrap_hook(
    _RECOVERY_OUTER_REHEXED
)

_PROBE_WORDS = tuple(shlex.split(PROBE_START_COMMAND, posix=True))
_NORMAL_WORDS = tuple(shlex.split(NORMAL_START_COMMAND_BOOTSTRAP, posix=True))
PROBE_C_BODY = _PROBE_WORDS[7]
NORMAL_C_BODY = _NORMAL_WORDS[7]
_RECOVERY_Q_MATCH = re.search(
    r'Q=bytes\.fromhex\("([0-9a-f]+)"\)',
    RECOVERY_START_COMMAND_TEMPLATE,
)
RECOVERY_CHILD_C_HEX = (
    _RECOVERY_Q_MATCH.group(1) if _RECOVERY_Q_MATCH is not None else ""
)

STARTUP_INJECTION_EXACT_KEYS = frozenset(
    {
        "ENV",
        "SHELLOPTS",
        "PS4",
        "KSHENV",
        "ZDOTDIR",
        "GCONV_PATH",
        "GLIBC_TUNABLES",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "SSLKEYLOGFILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    }
)
STARTUP_INJECTION_PREFIXES = (
    "_PYTHON",
    "LD_",
    "DYLD_",
    "BASH",
    "GIT_",
    "OPENSSL_",
)
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")


def _startup_key_is_forbidden(key: str) -> bool:
    return (
        (key.startswith("PYTHON") and key != PYTHON_VERSION_ENV)
        or key.startswith(STARTUP_INJECTION_PREFIXES)
        or key in STARTUP_INJECTION_EXACT_KEYS
    )


def validate_command_constants() -> None:
    """Pure/import-safe validation of the three frozen command strings."""
    try:
        prefix_bytes = BOOTSTRAP_HOOK_PREFIX.encode("ascii")
        probe_bytes = PROBE_C_BODY.encode("ascii")
    except UnicodeError as error:
        raise ContractError("COMMAND_BOOTSTRAP_MISMATCH") from error
    if (
        len(prefix_bytes) != 60
        or not PROBE_C_BODY.startswith(BOOTSTRAP_HOOK_PREFIX)
        or PROBE_C_BODY.count(BOOTSTRAP_HOOK_PREFIX) != 1
        or not NORMAL_C_BODY.startswith(BOOTSTRAP_HOOK_PREFIX)
        or NORMAL_C_BODY.count(BOOTSTRAP_HOOK_PREFIX) != 1
        or len(probe_bytes) != PROBE_C_BODY_LEN
        or hashlib.sha256(probe_bytes).hexdigest() != PROBE_C_BODY_SHA256
    ):
        raise ContractError("COMMAND_BOOTSTRAP_MISMATCH")
    if _PROBE_WORDS[:7] != ("python", *ISOLATED_PYTHON_ARGS, "-c"):
        raise ContractError("PROBE_COMMAND_MISMATCH")
    if len(_PROBE_WORDS) != 8:
        raise ContractError("PROBE_COMMAND_MISMATCH")
    if _NORMAL_WORDS[:7] != ("python", *ISOLATED_PYTHON_ARGS, "-c"):
        raise ContractError("NORMAL_COMMAND_MISMATCH")
    if len(_NORMAL_WORDS) != 8:
        raise ContractError("NORMAL_COMMAND_MISMATCH")
    try:
        decoded = bytes.fromhex(RECOVERY_CHILD_C_HEX).decode("ascii")
    except (ValueError, UnicodeError) as error:
        raise ContractError("RECOVERY_CHILD_MISMATCH") from error
    if (
        decoded != NORMAL_C_BODY
        or not decoded.startswith(BOOTSTRAP_HOOK_PREFIX)
        or decoded.count(BOOTSTRAP_HOOK_PREFIX) != 1
        or len(decoded.encode("ascii")) != RECOVERY_CHILD_C_LEN
        or len(RECOVERY_CHILD_C_HEX) != RECOVERY_CHILD_HEX_LEN
        or hashlib.sha256(decoded.encode("ascii")).hexdigest()
        != RECOVERY_CHILD_C_SHA256
    ):
        raise ContractError("RECOVERY_CHILD_MISMATCH")


@dataclass(frozen=True, slots=True)
class StartupObservation:
    version: tuple[int, int, int]
    isolated: int
    ignore_environment: int
    no_user_site: int
    no_site: int
    safe_path: bool
    dont_write_bytecode: bool
    pycache_prefix: str | None
    base_prefix: str
    base_exec_prefix: str
    platlibdir: str
    cwd: str
    stdlib: str
    platstdlib: str
    purelib: str
    platlib: str
    sys_path: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    loaded_modules: frozenset[str]
    sys_origin: str | None
    os_origin: str | None
    os_path_origin: str | None
    quant_package: str | None
    quant_origin: str | None
    quant_file: str | None
    quant_search_locations: tuple[str, ...]
    executable: str
    which_python: str | None
    proc_self_exe: str
    proc_cmdline: tuple[str, ...]
    q_lexists: bool
    u_is_dir: bool
    t_is_dir: bool
    y_is_dir: bool
    cwd_is_dir: bool
    quant_dir_is_dir: bool
    module_is_regular: bool
    executable_is_regular: bool
    executable_is_executable: bool
    devnull_is_char: bool
    ld_preload_lexists: bool
    # Independent post-import rechecks for the two site roots appended by the
    # isolated bootstrap.  The bootstrap's earlier check is not sufficient if
    # either directory disappears or is replaced before common validation.
    purelib_is_dir: bool = True
    platlib_is_dir: bool = True
    quant_path: tuple[str, ...] = ()
    quant_loader_type: str | None = None
    quant_loader_matches_spec: bool = False
    scorecard_package: str | None = None
    scorecard_spec_name: str | None = None
    scorecard_origin: str | None = None
    scorecard_file: str | None = None
    scorecard_loader_type: str | None = None
    scorecard_loader_name: str | None = None
    scorecard_loader_path: str | None = None
    scorecard_loader_matches_spec: bool = False
    meta_path_types: tuple[str, ...] = ()
    excepthook: object = _CAPTURED_BOOTSTRAP_HOOK
    unraisablehook: object = _CAPTURED_BOOTSTRAP_HOOK


def _runtime_type_name(value: object) -> str:
    target = value if isinstance(value, type) else type(value)
    return f"{target.__module__}.{target.__qualname__}"


def _strict_real(
    path: str,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    _cooperative_check(check)
    if not os.path.isabs(path):
        raise StartupIsolationError("STARTUP_PATH_INVALID")
    real = _cooperative_call(check, os.path.realpath, path)
    if real != path:
        raise StartupIsolationError("STARTUP_PATH_INVALID")
    _cooperative_check(check)
    return real


def _read_proc_cmdline(path: str = "/proc/self/cmdline") -> tuple[str, ...]:
    try:
        raw = Path(path).read_bytes()
        pieces = raw[:-1].split(b"\0") if raw.endswith(b"\0") else raw.split(b"\0")
        return tuple(piece.decode("utf-8", "strict") for piece in pieces)
    except (OSError, UnicodeError) as error:
        raise StartupIsolationError("STARTUP_CMDLINE_INVALID") from error


def _observe_startup_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Observe environment *names* plus the sole non-secret version value.

    Iterating ``os.environ.items()`` would read and copy the database URI and
    GitHub token before startup isolation had been accepted.  The bootstrap
    contract needs every key name, but it needs the value of only
    ``PYTHON_VERSION``.  Empty strings below are deliberate non-secret
    sentinels, not observations of the corresponding values.  The injectable
    mapping is a narrow audit seam proving value access is limited to the one
    permitted key.
    """

    source = os.environ if environment is None else environment
    try:
        keys = tuple(sorted(source))
        if any(type(key) is not str for key in keys):
            raise ValueError("environment key is not text")
        python_version = source.get(PYTHON_VERSION_ENV)
    except Exception as error:
        raise StartupIsolationError("STARTUP_ENVIRONMENT_INVALID") from error
    return tuple(
        (
            key,
            python_version
            if key == PYTHON_VERSION_ENV and isinstance(python_version, str)
            else "",
        )
        for key in keys
    )


def observe_live_startup() -> StartupObservation:
    """Observe only the already-started process; it does not read a secret."""
    q = os.path.join(sys.base_prefix, sys.platlibdir, "python314.zip")
    u = os.path.join(sys.base_prefix, sys.platlibdir, "python3.14")
    t = os.path.join(sys.base_exec_prefix, sys.platlibdir, "python3.14")
    y = os.path.join(t, "lib-dynload")
    cwd = os.getcwd()
    paths = sysconfig.get_paths(scheme=sysconfig.get_preferred_scheme("prefix"))
    executable = os.path.realpath(sys.executable)
    which_python = __import__("shutil").which("python")
    proc_self_exe = os.path.realpath("/proc/self/exe")
    quant = sys.modules.get("quant")
    quant_spec = getattr(quant, "__spec__", None)
    quant_loader = getattr(quant, "__loader__", None)
    scorecard = sys.modules.get(__name__)
    scorecard_spec = getattr(scorecard, "__spec__", None)
    scorecard_loader = getattr(scorecard, "__loader__", None)
    quant_dir = os.path.join(cwd, "quant")
    module_path = os.path.join(quant_dir, "volatility_scorecard.py")

    def is_dir_nofollow(path: str) -> bool:
        try:
            return stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode)
        except OSError:
            return False

    def is_regular_nofollow(path: str) -> bool:
        try:
            return stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode)
        except OSError:
            return False

    try:
        devnull_is_char = stat.S_ISCHR(
            os.stat("/dev/null", follow_symlinks=False).st_mode
        )
    except OSError:
        devnull_is_char = False

    return StartupObservation(
        version=tuple(sys.version_info[:3]),
        isolated=sys.flags.isolated,
        ignore_environment=sys.flags.ignore_environment,
        no_user_site=sys.flags.no_user_site,
        no_site=sys.flags.no_site,
        safe_path=bool(sys.flags.safe_path),
        dont_write_bytecode=bool(sys.dont_write_bytecode),
        pycache_prefix=sys.pycache_prefix,
        base_prefix=os.path.realpath(sys.base_prefix),
        base_exec_prefix=os.path.realpath(sys.base_exec_prefix),
        platlibdir=sys.platlibdir,
        cwd=os.path.realpath(cwd),
        stdlib=os.path.realpath(paths["stdlib"]),
        platstdlib=os.path.realpath(paths["platstdlib"]),
        purelib=os.path.realpath(paths["purelib"]),
        platlib=os.path.realpath(paths["platlib"]),
        sys_path=tuple(str(item) for item in sys.path),
        # Never enumerate environment values here.  In particular, the two
        # runtime secrets are not read, copied, or parsed before this
        # observation has passed validate_startup_observation().
        environment=_observe_startup_environment(),
        loaded_modules=frozenset(sys.modules),
        sys_origin=getattr(sys.__spec__, "origin", None),
        os_origin=getattr(os.__spec__, "origin", None),
        os_path_origin=getattr(os.path.__spec__, "origin", None),
        quant_package=getattr(quant, "__package__", None),
        quant_origin=getattr(quant_spec, "origin", None),
        quant_file=getattr(quant, "__file__", None),
        quant_search_locations=tuple(
            str(item)
            for item in (getattr(quant_spec, "submodule_search_locations", ()) or ())
        ),
        executable=executable,
        which_python=(
            os.path.realpath(which_python) if which_python is not None else None
        ),
        proc_self_exe=proc_self_exe,
        proc_cmdline=_read_proc_cmdline(),
        q_lexists=os.path.lexists(q),
        u_is_dir=is_dir_nofollow(u),
        t_is_dir=is_dir_nofollow(t),
        y_is_dir=is_dir_nofollow(y),
        cwd_is_dir=is_dir_nofollow(cwd),
        quant_dir_is_dir=is_dir_nofollow(quant_dir),
        module_is_regular=is_regular_nofollow(module_path),
        executable_is_regular=is_regular_nofollow(executable),
        executable_is_executable=os.access(executable, os.X_OK),
        devnull_is_char=devnull_is_char,
        ld_preload_lexists=os.path.lexists("/etc/ld.so.preload"),
        purelib_is_dir=is_dir_nofollow(os.path.realpath(paths["purelib"])),
        platlib_is_dir=is_dir_nofollow(os.path.realpath(paths["platlib"])),
        quant_path=tuple(str(item) for item in (getattr(quant, "__path__", ()) or ())),
        quant_loader_type=(
            _runtime_type_name(quant_loader) if quant_loader is not None else None
        ),
        quant_loader_matches_spec=(
            quant_loader is not None and quant_loader is getattr(quant_spec, "loader", None)
        ),
        scorecard_package=getattr(scorecard, "__package__", None),
        scorecard_spec_name=getattr(scorecard_spec, "name", None),
        scorecard_origin=getattr(scorecard_spec, "origin", None),
        scorecard_file=getattr(scorecard, "__file__", None),
        scorecard_loader_type=(
            _runtime_type_name(scorecard_loader)
            if scorecard_loader is not None
            else None
        ),
        scorecard_loader_name=getattr(scorecard_loader, "name", None),
        scorecard_loader_path=getattr(scorecard_loader, "path", None),
        scorecard_loader_matches_spec=(
            scorecard_loader is not None
            and scorecard_loader is getattr(scorecard_spec, "loader", None)
        ),
        meta_path_types=tuple(_runtime_type_name(item) for item in sys.meta_path),
        excepthook=sys.excepthook,
        unraisablehook=sys.unraisablehook,
    )


def validate_startup_observation(
    observation: StartupObservation,
    *,
    mode: str,
    manifest_id: str | None = None,
    recovery_seal_path: str | None = None,
) -> None:
    """Pure validator.  Production wrappers always pass a live observation."""
    validate_command_constants()
    if mode not in {"probe", "normal", "recovery"}:
        raise StartupIsolationError("STARTUP_MODE_INVALID")
    if (
        observation.version != EXPECTED_PYTHON_VERSION
        or observation.isolated != 1
        or observation.ignore_environment != 1
        or observation.no_user_site != 1
        or observation.no_site != 1
        or not observation.safe_path
        or not observation.dont_write_bytecode
        or observation.pycache_prefix != PYCACHE_PREFIX
        or observation.sys_origin != "built-in"
        or observation.os_origin != "frozen"
        or observation.os_path_origin != "frozen"
        or observation.excepthook is not _CAPTURED_BOOTSTRAP_HOOK
        or observation.unraisablehook is not _CAPTURED_BOOTSTRAP_HOOK
    ):
        raise StartupIsolationError("STARTUP_FLAGS_INVALID")

    q = os.path.join(
        observation.base_prefix, observation.platlibdir, "python314.zip"
    )
    u = os.path.join(
        observation.base_prefix, observation.platlibdir, "python3.14"
    )
    t = os.path.join(
        observation.base_exec_prefix, observation.platlibdir, "python3.14"
    )
    y = os.path.join(t, "lib-dynload")
    for value in (
        q,
        u,
        t,
        y,
        observation.cwd,
        observation.purelib,
        observation.platlib,
    ):
        if not os.path.isabs(value) or os.path.realpath(value) != value:
            raise StartupIsolationError("STARTUP_PATH_INVALID")
    appended = tuple(
        dict.fromkeys(
            (observation.cwd, observation.purelib, observation.platlib)
        )
    )
    expected_path = (u, y, *appended)
    quant_dir = os.path.join(observation.cwd, "quant")
    env = dict(observation.environment)
    if (
        observation.stdlib != u
        or observation.platstdlib != t
        or observation.sys_path != expected_path
        or len(set(expected_path)) != len(expected_path)
        or set(appended).intersection((u, y))
        or observation.q_lexists
        or not all(
            (
                observation.u_is_dir,
                observation.t_is_dir,
                observation.y_is_dir,
                observation.cwd_is_dir,
                observation.purelib_is_dir,
                observation.platlib_is_dir,
                observation.quant_dir_is_dir,
                observation.module_is_regular,
                observation.executable_is_regular,
                observation.executable_is_executable,
                observation.devnull_is_char,
            )
        )
        or observation.ld_preload_lexists
        or observation.which_python != observation.executable
        or observation.proc_self_exe != observation.executable
        or {"site", "sitecustomize", "usercustomize"}.intersection(
            observation.loaded_modules
        )
        or {"zoneinfo", "tzdata"}.intersection(observation.loaded_modules)
        or observation.quant_package != "quant"
        or observation.quant_origin is not None
        or observation.quant_file is not None
        or observation.quant_search_locations != (quant_dir,)
        or observation.quant_path != (quant_dir,)
        or observation.quant_loader_type
        != "_frozen_importlib_external.NamespaceLoader"
        or not observation.quant_loader_matches_spec
        or observation.scorecard_package != "quant"
        or observation.scorecard_spec_name != "quant.volatility_scorecard"
        or observation.scorecard_origin != os.path.join(
            quant_dir, "volatility_scorecard.py"
        )
        or observation.scorecard_file != os.path.join(
            quant_dir, "volatility_scorecard.py"
        )
        or observation.scorecard_loader_type
        != "_frozen_importlib_external.SourceFileLoader"
        or observation.scorecard_loader_name != "quant.volatility_scorecard"
        or observation.scorecard_loader_path != os.path.join(
            quant_dir, "volatility_scorecard.py"
        )
        or not observation.scorecard_loader_matches_spec
        or observation.meta_path_types
        != (
            "_frozen_importlib.BuiltinImporter",
            "_frozen_importlib.FrozenImporter",
            "_frozen_importlib_external.PathFinder",
        )
    ):
        raise StartupIsolationError("STARTUP_STATE_INVALID")
    if env.get(PYTHON_VERSION_ENV) != EXPECTED_PYTHON_VERSION_TEXT:
        raise StartupIsolationError("STARTUP_ENVIRONMENT_INVALID")
    if any(_startup_key_is_forbidden(key) for key in env):
        raise StartupIsolationError("STARTUP_ENVIRONMENT_INVALID")
    if mode == "probe" and (
        READONLY_URL_ENV in env or GITHUB_TOKEN_ENV in env
    ):
        raise StartupIsolationError("STARTUP_SECRET_PRESENT")

    words = observation.proc_cmdline
    expected_c_body = PROBE_C_BODY if mode == "probe" else NORMAL_C_BODY
    if len(words) < 8 or words[1:7] != (*ISOLATED_PYTHON_ARGS, "-c"):
        raise StartupIsolationError("STARTUP_CMDLINE_INVALID")
    if words[7] != expected_c_body:
        raise StartupIsolationError("STARTUP_CMDLINE_INVALID")
    if mode in {"probe", "normal"}:
        if words[0] != "python":
            raise StartupIsolationError("STARTUP_CMDLINE_INVALID")
    elif words[0] != observation.executable:
        raise StartupIsolationError("STARTUP_CMDLINE_INVALID")

    if mode == "probe":
        expected_tail: tuple[str, ...] = ()
    elif mode == "normal":
        if manifest_id not in MANIFEST_IDS:
            raise StartupIsolationError("STARTUP_CMDLINE_INVALID")
        expected_tail = ("--manifest-id", str(manifest_id))
    else:
        if (
            manifest_id not in MANIFEST_IDS
            or recovery_seal_path is None
            or not re.fullmatch(
                # NOSONAR: exact frozen isolated recovery path, validated below.
                r"/tmp/atom-v1b-seals/[0-9a-f]{64}\.json",  # NOSONAR
                recovery_seal_path,
            )
        ):
            raise StartupIsolationError("STARTUP_CMDLINE_INVALID")
        expected_tail = (
            "--manifest-id",
            str(manifest_id),
            "--recovery-seal-file",
            recovery_seal_path,
        )
    if words[8:] != expected_tail:
        raise StartupIsolationError("STARTUP_CMDLINE_INVALID")


def assert_production_startup(
    *,
    mode: str,
    manifest_id: str | None = None,
    recovery_seal_path: str | None = None,
) -> StartupObservation:
    """The only production bridge; there is deliberately no bypass argument."""
    observation = observe_live_startup()
    validate_startup_observation(
        observation,
        mode=mode,
        manifest_id=manifest_id,
        recovery_seal_path=recovery_seal_path,
    )
    return observation


@dataclass(frozen=True, slots=True)
class FileCandidate:
    logical_path: str
    real_path: str


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    size: int
    sha256: str

    def public(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class GithubTlsTrustObservation:
    reported_cafile_path: str
    canonical_cafile_path: str
    cafile_size_bytes: int
    cafile_sha256: str
    pem_ascii: str = field(repr=False, compare=False)

    def public(self) -> dict[str, object]:
        return {
            "source": "ssl.get_default_verify_paths().cafile",
            "reported_cafile_path": self.reported_cafile_path,
            "canonical_cafile_path": self.canonical_cafile_path,
            "cafile_size_bytes": self.cafile_size_bytes,
            "cafile_sha256": self.cafile_sha256,
        }


def _read_stable_regular_bytes(
    canonical_path: str,
    *,
    check: Callable[[], object] | None = None,
) -> bytes:
    """Read one resolved regular file with exact stable metadata."""

    listed = _validate_canonical_regular_path(canonical_path, check=check)
    descriptor = -1
    output = _cooperative_call(check, bytearray)
    try:
        descriptor = _cooperative_acquire(
            check,
            os.open,
            os.close,
            canonical_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        before = _cooperative_call(check, os.fstat, descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            raise ArtifactError("TRUST_BUNDLE_NOT_REGULAR")
        if (
            listed.st_dev,
            listed.st_ino,
            listed.st_mode,
            listed.st_size,
            listed.st_mtime_ns,
            listed.st_ctime_ns,
        ) != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ):
            raise ArtifactError("TRUST_BUNDLE_CHANGED")
        remaining = before.st_size
        while remaining:
            chunk = _cooperative_call(
                check,
                os.read,
                descriptor,
                min(GITHUB_DEADLINE_WORK_CHUNK_BYTES, remaining),
            )
            if not chunk or len(chunk) > remaining:
                raise ArtifactError("TRUST_BUNDLE_READ_FAILED")
            _cooperative_call(check, output.extend, chunk)
            remaining -= len(chunk)
        if _cooperative_call(check, os.read, descriptor, 1):
            raise ArtifactError("TRUST_BUNDLE_CHANGED")
        after = _cooperative_call(check, os.fstat, descriptor)
    except OSError as error:
        raise ArtifactError("TRUST_BUNDLE_READ_FAILED") from error
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if identity(before) != identity(after) or len(output) != before.st_size:
        raise ArtifactError("TRUST_BUNDLE_CHANGED")
    return _cooperative_call(check, bytes, output)


def observe_github_tls_trust(
    *,
    get_default_verify_paths: Callable[[], object] | None = None,
    check: Callable[[], object] | None = None,
) -> GithubTlsTrustObservation:
    """Freshly resolve and stable-read the sole CPython default CA bundle."""

    if any(
        key in os.environ
        for key in (
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "SSLKEYLOGFILE",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
        )
    ):
        raise ArtifactError("GITHUB_TLS_TRUST_OVERRIDE_PRESENT")
    verify_paths_reader = (
        ssl.get_default_verify_paths
        if get_default_verify_paths is None
        else get_default_verify_paths
    )
    paths = _cooperative_call(check, verify_paths_reader)
    openssl_cafile_env = _cooperative_call(
        check,
        getattr,
        paths,
        "openssl_cafile_env",
        None,
    )
    openssl_cafile = _cooperative_call(
        check,
        getattr,
        paths,
        "openssl_cafile",
        None,
    )
    reported = _cooperative_call(check, getattr, paths, "cafile", None)
    if (
        openssl_cafile_env != "SSL_CERT_FILE"
        or type(openssl_cafile) is not str
        or not openssl_cafile
        or not os.path.isabs(openssl_cafile)
        or reported != openssl_cafile
    ):
        raise ArtifactError("GITHUB_TLS_DEFAULT_PATH_INVALID")
    canonical = _cooperative_call(check, os.path.realpath, reported)
    if (
        type(canonical) is not str
        or not os.path.isabs(canonical)
        or _cooperative_call(check, os.path.normpath, canonical) != canonical
    ):
        raise ArtifactError("GITHUB_TLS_DEFAULT_PATH_INVALID")
    raw = _read_stable_regular_bytes(canonical, check=check)
    try:
        pem_ascii = _cooperative_call(check, raw.decode, "ascii", "strict")
    except UnicodeError as error:
        raise ArtifactError("GITHUB_TLS_BUNDLE_NOT_ASCII") from error
    if not pem_ascii:
        raise ArtifactError("GITHUB_TLS_BUNDLE_EMPTY")
    digest = _checked_sha256_bytes(raw, check=check)
    return _cooperative_call(
        check,
        GithubTlsTrustObservation,
        reported_cafile_path=reported,
        canonical_cafile_path=canonical,
        cafile_size_bytes=len(raw),
        cafile_sha256=digest,
        pem_ascii=pem_ascii,
    )


def verify_github_tls_trust(
    observed: GithubTlsTrustObservation,
    expected: Mapping[str, object],
    *,
    check: Callable[[], object] | None = None,
) -> None:
    actual = _cooperative_call(check, observed.public)
    expected_copy = _cooperative_call(check, dict, expected)
    if actual != expected_copy:
        raise ArtifactError("GITHUB_TLS_TRUST_MISMATCH")
    _cooperative_check(check)


def build_github_ssl_context(
    trust: GithubTlsTrustObservation,
    *,
    context_factory: Callable[[object], ssl.SSLContext] = ssl.SSLContext,
    check: Callable[[], object] | None = None,
) -> ssl.SSLContext:
    """Create the process's sole cadata-only GitHub TLS context."""

    context = _cooperative_call(check, context_factory, ssl.PROTOCOL_TLS_CLIENT)
    try:
        _cooperative_call(
            check,
            context.load_verify_locations,
            cadata=trust.pem_ascii,
        )
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        _cooperative_call(check, context.set_alpn_protocols, ["http/1.1"])
        accepted = _cooperative_call(
            check,
            context.get_ca_certs,
            binary_form=True,
        )
    except BaseException:
        raise ArtifactError("GITHUB_TLS_CONTEXT_INVALID") from None
    if (
        context.verify_mode != ssl.CERT_REQUIRED
        or context.check_hostname is not True
        or context.minimum_version != ssl.TLSVersion.TLSv1_2
        or not accepted
    ):
        raise ArtifactError("GITHUB_TLS_CONTEXT_INVALID")
    return context


@dataclass(frozen=True, slots=True)
class ProcMapEntry:
    start: int
    end: int
    permissions: str
    file_offset: int
    path: str | None


_PERMITTED_KERNEL_EXECUTABLE_MAPPINGS: Mapping[
    str, tuple[str, int, int | None, int | None]
] = MappingProxyType(
    {
        # The runtime platform is frozen to Linux x86_64.  These are the only
        # executable kernel mappings that are not backed by regular files.
        "[vdso]": ("r-xp", 0, None, None),
        "[vsyscall]": (
            "--xp",
            0,
            0xFFFF_FFFF_FF60_0000,
            0xFFFF_FFFF_FF60_1000,
        ),
    }
)


def _is_permitted_kernel_executable_mapping(mapping: ProcMapEntry) -> bool:
    path = mapping.path
    if path is None:
        return False
    permitted = _PERMITTED_KERNEL_EXECUTABLE_MAPPINGS.get(path)
    if permitted is None:
        return False
    permissions, file_offset, start, end = permitted
    return (
        mapping.permissions == permissions
        and mapping.file_offset == file_offset
        and (start is None or mapping.start == start)
        and (end is None or mapping.end == end)
    )


@dataclass(frozen=True, slots=True)
class RuntimeRoots:
    python_executable: str
    stdlib: str
    platstdlib: str
    purelib: str
    platlib: str


@dataclass(frozen=True, slots=True)
class RuntimeArtifactPlan:
    roots: RuntimeRoots
    dependency_versions: tuple[tuple[str, str], ...]
    stdlib_files: tuple[FileCandidate, ...]
    dependency_files: tuple[FileCandidate, ...]
    native_files: tuple[FileCandidate, ...]
    mappings: tuple[ProcMapEntry, ...]
    module_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class ArtifactComponents:
    python_executable_sha256: str
    stdlib_tree_sha256: str
    dependency_tree_sha256: str
    loaded_native_tree_sha256: str

    def public(self) -> dict[str, str]:
        return {
            "python_executable_sha256": self.python_executable_sha256,
            "stdlib_tree_sha256": self.stdlib_tree_sha256,
            "dependency_tree_sha256": self.dependency_tree_sha256,
            "loaded_native_tree_sha256": self.loaded_native_tree_sha256,
        }


@dataclass(frozen=True, slots=True)
class RuntimeMeasurement:
    components: ArtifactComponents
    runtime_artifact_sha256: str
    libm_dispatch: Mapping[str, Mapping[str, object]] | None
    libm_dispatch_sha256: str | None
    dependency_versions: tuple[tuple[str, str], ...]
    module_names: frozenset[str]
    # Internal, non-serialized membership proof used by the isolated GitHub
    # resolver audit.  Retaining the records measured for the frozen
    # component prevents a later request from manufacturing a path/digest
    # allowlist from its own child mappings.
    python_executable_record: FileRecord
    native_records: tuple[FileRecord, ...]


class FileAccess(Protocol):
    def record(self, candidate: FileCandidate) -> FileRecord:
        ...


def _validate_canonical_regular_path(
    path: str,
    *,
    check: Callable[[], object] | None = None,
) -> os.stat_result:
    """Validate the exact listed path without erasing symlink identity.

    In particular, callers must not ``realpath`` a distribution metadata path
    and then authenticate only its target.  The lexical path itself is part of
    the artifact claim.  ``lstat`` therefore precedes every no-follow open,
    and :class:`LocalFileAccess` binds this result to the descriptor metadata
    before hashing.
    """

    _cooperative_check(check)
    if type(path) is not str or not os.path.isabs(path) or "\0" in path:
        raise ArtifactError("ARTIFACT_PATH_INVALID")
    real = _cooperative_call(check, os.path.realpath, path)
    if real != path or PurePosixPath(path).as_posix() != path:
        raise ArtifactError("ARTIFACT_PATH_INVALID")
    try:
        _cooperative_check(check)
        path_stat = os.lstat(path)
        _cooperative_check(check)
    except OSError as error:
        raise ArtifactError("ARTIFACT_READ_FAILED") from error
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise ArtifactError("ARTIFACT_NOT_REGULAR")
    return path_stat


class LocalFileAccess:
    """Race-aware regular-file reader used by production measurement."""

    def __init__(self, *, check: Callable[[], object] | None = None) -> None:
        self._check = (lambda: None) if check is None else check

    def record(self, candidate: FileCandidate) -> FileRecord:
        check = self._check
        check()
        if (
            PurePosixPath(candidate.logical_path).as_posix()
            != candidate.logical_path
        ):
            raise ArtifactError("ARTIFACT_PATH_INVALID")
        path_stat = _validate_canonical_regular_path(
            candidate.real_path,
            check=check,
        )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            descriptor = _cooperative_acquire(
                check,
                os.open,
                os.close,
                candidate.real_path,
                flags,
            )
            try:
                check()
                before = os.fstat(descriptor)
                check()
                if not stat.S_ISREG(before.st_mode):
                    raise ArtifactError("ARTIFACT_NOT_REGULAR")
                listed_is_opened_file = (
                    path_stat.st_dev,
                    path_stat.st_ino,
                    path_stat.st_mode,
                    path_stat.st_size,
                    path_stat.st_mtime_ns,
                    path_stat.st_ctime_ns,
                ) == (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                if not listed_is_opened_file:
                    raise ArtifactError("ARTIFACT_CHANGED_DURING_READ")
                digest = _cooperative_call(check, hashlib.sha256)
                count = 0
                remaining = before.st_size
                while remaining:
                    check()
                    chunk = os.read(
                        descriptor,
                        min(GITHUB_DEADLINE_WORK_CHUNK_BYTES, remaining),
                    )
                    check()
                    if not chunk or len(chunk) > remaining:
                        raise ArtifactError("ARTIFACT_READ_FAILED")
                    count += len(chunk)
                    remaining -= len(chunk)
                    _cooperative_call(check, digest.update, chunk)
                # Reject growth without accepting only the originally measured
                # prefix.  Every read/hash operation is fixed-size and
                # bracketed by the caller's monotonic deadline checker.
                check()
                if os.read(descriptor, 1):
                    raise ArtifactError("ARTIFACT_CHANGED_DURING_READ")
                check()
                after = os.fstat(descriptor)
                check()
            finally:
                os.close(descriptor)
        except OSError as error:
            raise ArtifactError("ARTIFACT_READ_FAILED") from error
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if not stable or count != before.st_size:
            raise ArtifactError("ARTIFACT_CHANGED_DURING_READ")
        check()
        return FileRecord(
            candidate.logical_path,
            count,
            _cooperative_call(check, digest.hexdigest),
        )


def _normalized_distribution_name(name: str) -> str:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    if not normalized:
        raise ArtifactError("DEPENDENCY_NAME_INVALID")
    return normalized


def _is_cache_artifact(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        "__pycache__" in parts
        or path.endswith(".pyc")
        or path.endswith(".pyo")
    )


def _under(
    path: str,
    parent: str,
    *,
    check: Callable[[], object] | None = None,
) -> bool:
    try:
        common = _cooperative_call(
            check,
            os.path.commonpath,
            (path, parent),
        )
        result = common == parent
        _cooperative_check(check)
        return result
    except ValueError:
        _cooperative_check(check)
        return False


def _under_any(
    path: str,
    parents: Sequence[str],
    *,
    check: Callable[[], object] | None = None,
) -> bool:
    index = 0
    while index < len(parents):
        _cooperative_check(check)
        if _under(path, parents[index], check=check):
            _cooperative_check(check)
            return True
        _cooperative_check(check)
        index += 1
    return False


def _validate_canonical_directory_path(
    path: str,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    if type(path) is not str or not path or "\0" in path:
        raise ArtifactError("INSTALL_SCHEME_ROOT_INVALID")
    normalized = _cooperative_call(check, os.path.normpath, path)
    real = _cooperative_call(check, os.path.realpath, path)
    if not os.path.isabs(path) or path != normalized or path != real:
        raise ArtifactError("INSTALL_SCHEME_ROOT_INVALID")
    try:
        observed = _cooperative_call(check, os.lstat, path)
    except OSError as error:
        raise ArtifactError("INSTALL_SCHEME_ROOT_INVALID") from error
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ArtifactError("INSTALL_SCHEME_ROOT_INVALID")
    return path


def _collect_install_scheme_roots(
    paths: Mapping[str, str],
    *,
    check: Callable[[], object] | None = None,
) -> tuple[str, ...]:
    """Return the one preferred-prefix scheme's canonical root set."""

    roots: list[str] = []
    for name in INSTALL_SCHEME_ROOT_NAMES:
        _cooperative_check(check)
        try:
            value = _cooperative_call(check, paths.__getitem__, name)
        except (KeyError, TypeError) as error:
            raise ArtifactError("INSTALL_SCHEME_ROOT_INVALID") from error
        root = _validate_canonical_directory_path(value, check=check)
        if root not in roots:
            _cooperative_call(check, roots.append, root)
    # Longest first makes the unique most-specific classification explicit.
    return _cooperative_sorted(
        roots,
        key=lambda item: (-len(PurePosixPath(item).parts), item),
        check=check,
    )


def _validate_record_member_spelling(
    value: object,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    spelling = _cooperative_call(check, str, value)
    try:
        _cooperative_call(check, spelling.encode, "utf-8", "strict")
    except UnicodeError as error:
        raise ArtifactError("DEPENDENCY_PATH_INVALID") from error
    components = _cooperative_call(check, spelling.split, "/")
    if (
        not spelling
        or "\0" in spelling
        or "\\" in spelling
        or spelling.startswith("/")
        or not components
        or any(component in {"", "."} for component in components)
        or _cooperative_call(
            check,
            lambda item: PurePosixPath(item).as_posix(),
            spelling,
        )
        != spelling
    ):
        raise ArtifactError("DEPENDENCY_PATH_INVALID")
    seen_non_parent = False
    for component in _cooperative_tuple(components, check=check):
        _cooperative_check(check)
        if component == "..":
            if seen_non_parent:
                raise ArtifactError("DEPENDENCY_PATH_INVALID")
        else:
            seen_non_parent = True
    if not seen_non_parent:
        raise ArtifactError("DEPENDENCY_PATH_INVALID")
    return spelling


def _select_install_scheme_root(
    target: str,
    scheme_roots: Sequence[str],
    *,
    check: Callable[[], object] | None = None,
) -> str:
    matches: list[str] = []
    for root in _cooperative_tuple(scheme_roots, check=check):
        _cooperative_check(check)
        if _under(target, root, check=check):
            _cooperative_call(check, matches.append, root)
    if not matches:
        raise ArtifactError("DEPENDENCY_PATH_OUTSIDE_SCHEME")
    ordered = _cooperative_sorted(
        matches,
        key=lambda item: (-len(PurePosixPath(item).parts), item),
        check=check,
    )
    selected = ordered[0]
    selected_depth = len(PurePosixPath(selected).parts)
    if sum(
        1 for item in ordered if len(PurePosixPath(item).parts) == selected_depth
    ) != 1:
        raise ArtifactError("DEPENDENCY_SCHEME_ROOT_AMBIGUOUS")
    return selected


def _validate_no_symlink_components(
    target: str,
    root: str,
    *,
    check: Callable[[], object] | None = None,
) -> None:
    relative = _cooperative_call(check, os.path.relpath, target, root)
    if relative == os.curdir or relative.startswith(".." + os.sep):
        raise ArtifactError("DEPENDENCY_PATH_OUTSIDE_SCHEME")
    current = root
    components = _cooperative_call(check, relative.split, os.sep)
    for index, component in enumerate(_cooperative_tuple(components, check=check)):
        _cooperative_check(check)
        current = _cooperative_call(check, os.path.join, current, component)
        try:
            observed = _cooperative_call(check, os.lstat, current)
        except OSError as error:
            raise ArtifactError("DEPENDENCY_MEMBER_MISSING") from error
        if stat.S_ISLNK(observed.st_mode):
            raise ArtifactError("DEPENDENCY_MEMBER_SYMLINK")
        if index + 1 < len(components) and not stat.S_ISDIR(observed.st_mode):
            raise ArtifactError("DEPENDENCY_MEMBER_NOT_REGULAR")
    if not components or not stat.S_ISREG(observed.st_mode):
        raise ArtifactError("DEPENDENCY_MEMBER_NOT_REGULAR")


def _resolve_distribution_record_member(
    distribution: object,
    normalized_name: str,
    package_path: object,
    scheme_roots: Sequence[str],
    *,
    check: Callable[[], object] | None = None,
) -> FileCandidate | None:
    """Resolve one exact RECORD member without opening its logical key."""

    spelling = _validate_record_member_spelling(package_path, check=check)
    if _is_cache_artifact(spelling):
        return None
    base_value = _cooperative_call(check, distribution.locate_file, "")
    base_text = _cooperative_call(check, str, base_value)
    try:
        base = _validate_canonical_directory_path(base_text, check=check)
    except ArtifactError as error:
        raise ArtifactError("DEPENDENCY_BASE_INVALID") from error
    located_value = _cooperative_call(
        check,
        distribution.locate_file,
        package_path,
    )
    located_text = _cooperative_call(check, str, located_value)
    if type(located_text) is not str or not located_text or "\0" in located_text:
        raise ArtifactError("DEPENDENCY_PATH_INVALID")
    normalized_target = _cooperative_call(check, os.path.normpath, located_text)
    canonical_target = _cooperative_call(check, os.path.realpath, normalized_target)
    if (
        not os.path.isabs(normalized_target)
        or normalized_target != canonical_target
        or PurePosixPath(normalized_target).as_posix() != normalized_target
    ):
        raise ArtifactError("DEPENDENCY_PATH_INVALID")
    canonical_spelling = _cooperative_call(
        check,
        os.path.relpath,
        canonical_target,
        base,
    )
    canonical_spelling = _cooperative_call(
        check,
        canonical_spelling.replace,
        os.sep,
        "/",
    )
    if canonical_spelling != spelling:
        raise ArtifactError("DEPENDENCY_PATH_NONCANONICAL")
    selected_root = _select_install_scheme_root(
        canonical_target,
        scheme_roots,
        check=check,
    )
    _validate_no_symlink_components(
        canonical_target,
        selected_root,
        check=check,
    )
    _validate_canonical_regular_path(canonical_target, check=check)
    return FileCandidate(
        f"{normalized_name}/{spelling}",
        canonical_target,
    )


def _cooperative_read_bytes(
    path: str,
    *,
    check: Callable[[], object] | None = None,
) -> bytes:
    """Read a local/pseudo file in fixed chunks with cooperative deadlines."""

    descriptor = -1
    output = _cooperative_call(check, bytearray)
    try:
        _cooperative_check(check)
        descriptor = _cooperative_acquire(
            check,
            os.open,
            os.close,
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        while True:
            _cooperative_check(check)
            chunk = os.read(descriptor, GITHUB_DEADLINE_WORK_CHUNK_BYTES)
            _cooperative_check(check)
            if not chunk:
                break
            _cooperative_call(check, output.extend, chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return _cooperative_call(check, bytes, output)


def _cooperative_module_snapshot(
    *, check: Callable[[], object] | None = None
) -> frozenset[str]:
    names: list[str] = []
    iterator = _cooperative_call(check, iter, sys.modules)
    while True:
        _cooperative_check(check)
        try:
            name = next(iterator)
        except StopIteration:
            _cooperative_check(check)
            break
        _cooperative_check(check)
        _cooperative_call(check, names.append, name)
    return _cooperative_call(check, frozenset, names)


def _walk_regular_candidates(
    root: str,
    *,
    excluded_roots: Sequence[str] = (),
    check: Callable[[], object] | None = None,
) -> tuple[FileCandidate, ...]:
    _cooperative_check(check)
    root = _strict_real(root, check=check)
    exclusions_list: list[str] = []
    for item in _cooperative_tuple(excluded_roots, check=check):
        _cooperative_check(check)
        _cooperative_call(
            check,
            exclusions_list.append,
            _strict_real(item, check=check),
        )
    exclusions = _cooperative_call(check, tuple, exclusions_list)
    found: list[FileCandidate] = _cooperative_call(check, list)

    def walk_error(_error: OSError) -> NoReturn:
        # os.walk otherwise drops an unreadable subtree and returns a partial
        # tree digest, which is never complete artifact coverage.
        raise ArtifactError("ARTIFACT_TREE_UNREADABLE") from None

    walker = _cooperative_call(
        check,
        os.walk,
        root,
        followlinks=False,
        onerror=walk_error,
    )
    iterator = _cooperative_call(check, iter, walker)
    while True:
        # Advancing os.walk performs the underlying scandir/stat work.  A
        # check only at the top of a for-loop occurs *after* that operation,
        # so bracket each generator advancement explicitly.
        _cooperative_check(check)
        try:
            directory, dirnames, filenames = next(iterator)
        except StopIteration:
            _cooperative_check(check)
            break
        _cooperative_check(check)
        directory = _cooperative_call(check, os.path.realpath, directory)
        if _under_any(directory, exclusions, check=check):
            _cooperative_call(
                check,
                lambda target: target.__setitem__(slice(None), ()),
                dirnames,
            )
            _cooperative_check(check)
            continue
        kept_dirs: list[str] = []
        sorted_dirnames = _cooperative_call(check, sorted, dirnames)
        directory_index = 0
        while directory_index < len(sorted_dirnames):
            _cooperative_check(check)
            name = sorted_dirnames[directory_index]
            path = _cooperative_call(check, os.path.join, directory, name)
            if _cooperative_call(check, os.path.islink, path):
                raise ArtifactError("ARTIFACT_SYMLINK")
            real = _cooperative_call(check, os.path.realpath, path)
            if not _under_any(real, exclusions, check=check):
                _cooperative_call(check, kept_dirs.append, name)
            _cooperative_check(check)
            directory_index += 1
        _cooperative_call(
            check,
            lambda target, replacement: target.__setitem__(
                slice(None), replacement
            ),
            dirnames,
            kept_dirs,
        )
        sorted_filenames = _cooperative_call(check, sorted, filenames)
        file_index = 0
        while file_index < len(sorted_filenames):
            _cooperative_check(check)
            name = sorted_filenames[file_index]
            path = _cooperative_call(check, os.path.join, directory, name)
            logical_path = _cooperative_call(check, PurePosixPath, path)
            logical = _cooperative_call(check, logical_path.as_posix)
            if _cooperative_call(check, _is_cache_artifact, logical):
                _cooperative_check(check)
                file_index += 1
                continue
            if _cooperative_call(check, os.path.islink, path):
                raise ArtifactError("ARTIFACT_SYMLINK")
            _cooperative_call(
                check,
                found.append,
                FileCandidate(
                    logical,
                    _cooperative_call(check, os.path.realpath, path),
                ),
            )
            _cooperative_check(check)
            file_index += 1
    _cooperative_check(check)
    return _cooperative_call(check, tuple, found)


def validate_loaded_module_sources(
    module_names: Iterable[str],
    *,
    covered_source_paths: Iterable[str],
    covered_native_paths: Iterable[str],
    namespace_roots: Iterable[str],
    check: Callable[[], object] | None = None,
) -> None:
    """Bind every loaded module to covered source/native bytes or a builtin.

    Bytecode cache files are excluded from the trees, so they can never be an
    executable origin.  Namespace packages carry no code and are accepted only
    with the standard loader and canonical directories under approved roots.
    """

    source_items: list[str] = []
    for path in _cooperative_tuple(covered_source_paths, check=check):
        _cooperative_check(check)
        _cooperative_call(
            check,
            source_items.append,
            _strict_real(path, check=check),
        )
    native_items: list[str] = []
    for path in _cooperative_tuple(covered_native_paths, check=check):
        _cooperative_check(check)
        _cooperative_call(
            check,
            native_items.append,
            _strict_real(path, check=check),
        )
    root_items: list[str] = []
    for path in _cooperative_tuple(namespace_roots, check=check):
        _cooperative_check(check)
        _cooperative_call(
            check,
            root_items.append,
            _strict_real(path, check=check),
        )
    sources = _cooperative_call(check, frozenset, source_items)
    natives = _cooperative_call(check, frozenset, native_items)
    roots = _cooperative_call(check, tuple, root_items)

    def allowed_specless(name: str, module: object) -> bool:
        if (
            name == "__main__"
            and getattr(module, "__file__", None) is None
            and getattr(module, "__package__", None) is None
            and _runtime_type_name(getattr(module, "__loader__", None))
            == "_frozen_importlib.BuiltinImporter"
        ):
            return True
        if name in {"typing.io", "typing.re"}:
            return (
                _runtime_type_name(module) == "typing._DeprecatedType"
                and getattr(module, "__module__", None) == "typing"
            )
        if name == "cython_runtime":
            return (
                type(module) is ModuleType
                and getattr(module, "__file__", None) is None
                and getattr(module, "__loader__", None) is None
                and getattr(module, "__package__", None) is None
                and not {
                    key for key in vars(module) if not key.startswith("__")
                }
            )
        if re.fullmatch(r"_cython_[0-9]+(?:_[0-9]+)+", name):
            values = {
                key: value
                for key, value in vars(module).items()
                if not key.startswith("__")
            }
            return (
                type(module) is ModuleType
                and getattr(module, "__file__", None) is None
                and getattr(module, "__loader__", None) is None
                and getattr(module, "__package__", None) is None
                and set(values)
                == {"_common_types_metatype", "cython_function_or_method", "generator"}
                and all(
                    key == "_common_types_metatype"
                    or getattr(value, "__module__", None) == name
                    for key, value in values.items()
                )
            )
        return False

    ordered_module_names = _cooperative_sorted(module_names, check=check)
    for name in ordered_module_names:
        _cooperative_check(check)
        if type(name) is not str or not name:
            raise ArtifactError("LOADED_MODULE_NAME_INVALID")
        module = _cooperative_call(check, sys.modules.get, name)
        if module is None:
            raise ArtifactError("LOADED_MODULE_MISSING")
        spec = _cooperative_call(check, getattr, module, "__spec__", None)
        if spec is None:
            # Exact interpreter/typing/Cython runtime namespaces carry no
            # separate file origin.  The Cython types are created by already
            # loaded, mapped extension bytes; all other spec-less modules fail.
            if _cooperative_call(check, allowed_specless, name, module):
                _cooperative_check(check)
                continue
            raise ArtifactError("LOADED_MODULE_SPEC_MISSING")
        origin = _cooperative_call(check, getattr, spec, "origin", None)
        loader = _cooperative_call(check, getattr, spec, "loader", None)
        if origin in {"built-in", "frozen"}:
            expected_loader = (
                "_frozen_importlib.BuiltinImporter"
                if origin == "built-in"
                else "_frozen_importlib.FrozenImporter"
            )
            if _runtime_type_name(loader) != expected_loader:
                raise ArtifactError("LOADED_MODULE_LOADER_INVALID")
            _cooperative_check(check)
            continue
        if origin is None:
            raw_locations = _cooperative_call(
                check,
                getattr,
                spec,
                "submodule_search_locations",
                (),
            )
            raw_locations = () if raw_locations is None else raw_locations
            location_items = _cooperative_tuple(raw_locations, check=check)
            locations = _cooperative_call(
                check,
                tuple,
                (_cooperative_call(check, str, item) for item in location_items),
            )
            if (
                _runtime_type_name(loader)
                != "_frozen_importlib_external.NamespaceLoader"
                or not locations
            ):
                raise ArtifactError("LOADED_NAMESPACE_INVALID")
            for location in locations:
                _cooperative_check(check)
                canonical = _strict_real(location, check=check)
                if not _under_any(canonical, roots, check=check):
                    raise ArtifactError("LOADED_NAMESPACE_INVALID")
            _cooperative_check(check)
            continue
        if type(origin) is not str:
            raise ArtifactError("LOADED_MODULE_ORIGIN_INVALID")
        path = _strict_real(origin, check=check)
        if path.endswith((".pyc", ".pyo")):
            raise ArtifactError("LOADED_BYTECODE_FORBIDDEN")
        module_file = getattr(module, "__file__", None)
        if module_file != origin:
            raise ArtifactError("LOADED_MODULE_FILE_INVALID")
        if path.endswith(".py"):
            if (
                path not in sources
                or _runtime_type_name(loader)
                != "_frozen_importlib_external.SourceFileLoader"
            ):
                raise ArtifactError("LOADED_SOURCE_UNCOVERED")
        elif re.search(r"\.so(?:\..+)?$", path):
            if (
                path not in natives
                or _runtime_type_name(loader)
                != "_frozen_importlib_external.ExtensionFileLoader"
            ):
                raise ArtifactError("LOADED_NATIVE_UNCOVERED")
        else:
            raise ArtifactError("LOADED_MODULE_ORIGIN_INVALID")
        _cooperative_check(check)


def parse_proc_maps(
    raw: bytes,
    *,
    check: Callable[[], object] | None = None,
) -> tuple[ProcMapEntry, ...]:
    """Pure strict parser; test fixtures can supply arbitrary map bytes."""
    try:
        text = _cooperative_call(check, raw.decode, "utf-8", "strict")
    except UnicodeError as error:
        raise ArtifactError("PROC_MAPS_INVALID") from error
    result: list[ProcMapEntry] = []
    lines = _cooperative_call(check, text.splitlines)
    for line in _cooperative_tuple(lines, check=check):
        _cooperative_check(check)
        fields = _cooperative_call(check, line.split, maxsplit=5)
        if len(fields) < 5:
            raise ArtifactError("PROC_MAPS_INVALID")
        try:
            start_text, end_text = _cooperative_call(
                check,
                fields[0].split,
                "-",
                1,
            )
            start = _cooperative_call(check, int, start_text, 16)
            end = _cooperative_call(check, int, end_text, 16)
            offset = _cooperative_call(check, int, fields[2], 16)
        except (ValueError, TypeError) as error:
            raise ArtifactError("PROC_MAPS_INVALID") from error
        path = fields[5] if len(fields) == 6 else None
        if start >= end or offset < 0 or len(fields[1]) != 4:
            raise ArtifactError("PROC_MAPS_INVALID")
        _cooperative_call(
            check,
            result.append,
            ProcMapEntry(start, end, fields[1], offset, path),
        )
    return _cooperative_call(check, tuple, result)


def _collect_native_candidates(
    mappings: Sequence[ProcMapEntry],
    *,
    check: Callable[[], object] | None = None,
) -> tuple[FileCandidate, ...]:
    paths: dict[str, FileCandidate] = {}
    special_mappings: set[str] = set()
    for mapping in _cooperative_tuple(mappings, check=check):
        _cooperative_check(check)
        if "x" not in mapping.permissions:
            _cooperative_check(check)
            continue
        path = mapping.path
        if path is None:
            raise ArtifactError("NATIVE_MAPPING_ANONYMOUS_EXECUTABLE")
        if path.startswith("["):
            if (
                path in special_mappings
                or not _is_permitted_kernel_executable_mapping(mapping)
            ):
                raise ArtifactError("NATIVE_MAPPING_SPECIAL_INVALID")
            special_mappings.add(path)
            _cooperative_check(check)
            continue
        if path.endswith(" (deleted)"):
            raise ArtifactError("NATIVE_MAPPING_DELETED")
        if not os.path.isabs(path) or "\\" in path or "\0" in path:
            raise ArtifactError("NATIVE_MAPPING_PATH_INVALID")
        real = _strict_real(
            _cooperative_call(check, os.path.realpath, path),
            check=check,
        )
        candidate = FileCandidate(PurePosixPath(real).as_posix(), real)
        _cooperative_call(
            check,
            paths.setdefault,
            candidate.logical_path,
            candidate,
        )
        _cooperative_check(check)
    ordered: list[FileCandidate] = []
    for key in _cooperative_sorted(paths, check=check):
        _cooperative_check(check)
        _cooperative_call(check, ordered.append, paths[key])
    return _cooperative_call(check, tuple, ordered)


def classify_required_native_members(
    native_paths: Iterable[str],
    *,
    python_executable: str,
    check: Callable[[], object] | None = None,
) -> Mapping[str, tuple[str, ...]]:
    """Prove the frozen named native closure is present, not merely hashed.

    Filenames may contain wheel audit hashes, so classification accepts only
    the narrow ELF basename families while the surrounding artifact proof
    binds each resolved absolute path and its exact bytes.
    """

    _cooperative_check(check)
    executable = _strict_real(python_executable, check=check)
    unique_paths: set[str] = set()
    for path in _cooperative_tuple(native_paths, check=check):
        _cooperative_check(check)
        _cooperative_call(
            check,
            unique_paths.add,
            _strict_real(path, check=check),
        )
    paths = _cooperative_sorted(unique_paths, check=check)

    def compile_pattern(pattern: str) -> re.Pattern[str]:
        return _cooperative_call(check, re.compile, pattern)

    patterns: Mapping[str, re.Pattern[str]] = {
        "dynamic_loader": compile_pattern(
            r"(?:ld-linux[^/]*|ld-[0-9][^/]*)\.so(?:\..+)?"
        ),
        "libc": compile_pattern(r"libc(?:-[^.]+)?\.so(?:\..+)?"),
        "libm": compile_pattern(r"libm(?:-[^.]+)?\.so(?:\..+)?"),
        "math": compile_pattern(r"math(?:\.[^.]+)*\.so(?:\..+)?"),
        "_random": compile_pattern(r"_random(?:\.[^.]+)*\.so(?:\..+)?"),
        "_json": compile_pattern(r"_json(?:\.[^.]+)*\.so(?:\..+)?"),
        "libpq": compile_pattern(r"libpq(?:-[^.]+)?\.so(?:\..+)?"),
        "libssl": compile_pattern(r"libssl(?:-[^.]+)?\.so(?:\..+)?"),
        "libcrypto": compile_pattern(r"libcrypto(?:-[^.]+)?\.so(?:\..+)?"),
    }
    classified: dict[str, tuple[str, ...]] = {}
    python_members_list: list[str] = []
    for path in paths:
        _cooperative_check(check)
        basename = _cooperative_call(check, os.path.basename, path)
        matches_python = path == executable or _cooperative_call(
            check,
            re.fullmatch,
            r"libpython3\.14\.so(?:\..+)?",
            basename,
        ) is not None
        if matches_python:
            _cooperative_call(check, python_members_list.append, path)
        _cooperative_check(check)
    python_members = _cooperative_call(check, tuple, python_members_list)
    if not python_members:
        raise ArtifactError("NATIVE_REQUIRED_CPYTHON_MISSING")
    classified["cpython_or_libpython"] = python_members
    for member, pattern in _cooperative_tuple(patterns.items(), check=check):
        _cooperative_check(check)
        matches_list: list[str] = []
        for path in paths:
            _cooperative_check(check)
            basename = _cooperative_call(check, os.path.basename, path)
            if _cooperative_call(check, pattern.fullmatch, basename) is not None:
                _cooperative_call(check, matches_list.append, path)
            _cooperative_check(check)
        matches = _cooperative_call(check, tuple, matches_list)
        if not matches:
            raise ArtifactError(f"NATIVE_REQUIRED_{member.upper()}_MISSING")
        classified[member] = matches
        _cooperative_check(check)
    return _cooperative_call(check, MappingProxyType, classified)


def collect_runtime_artifact_plan(
    expected_dependency_versions: Mapping[str, str],
    *,
    module_names: frozenset[str] | None = None,
    proc_maps_path: str = "/proc/self/maps",
    check: Callable[[], object] | None = None,
) -> RuntimeArtifactPlan:
    """Production collector; acceptance versions are caller-owned literals."""
    _cooperative_check(check)
    if _ZONEINFO_ISOLATION is not None:
        _validate_zoneinfo_isolation(_ZONEINFO_ISOLATION, check=check)
    if not expected_dependency_versions:
        raise ArtifactError("EXPECTED_DEPENDENCIES_UNSET")
    preferred_scheme = _cooperative_call(
        check, sysconfig.get_preferred_scheme, "prefix"
    )
    paths = _cooperative_call(
        check,
        sysconfig.get_paths,
        scheme=preferred_scheme,
    )
    scheme_roots = _collect_install_scheme_roots(paths, check=check)

    def resolved_root(path: str) -> str:
        return _strict_real(
            _cooperative_call(check, os.path.realpath, path),
            check=check,
        )

    roots = RuntimeRoots(
        python_executable=resolved_root("/proc/self/exe"),
        stdlib=resolved_root(paths["stdlib"]),
        platstdlib=resolved_root(paths["platstdlib"]),
        purelib=resolved_root(paths["purelib"]),
        platlib=resolved_root(paths["platlib"]),
    )
    stdlib: dict[str, FileCandidate] = {}
    stdlib_roots = _cooperative_call(
        check,
        tuple,
        _cooperative_call(
            check,
            dict.fromkeys,
            (roots.stdlib, roots.platstdlib),
        ),
    )
    for root in stdlib_roots:
        _cooperative_check(check)
        candidates = _walk_regular_candidates(
                root,
                excluded_roots=(roots.purelib, roots.platlib),
                check=check,
            )
        _cooperative_check(check)
        for candidate in candidates:
            _cooperative_check(check)
            if candidate.logical_path in stdlib:
                raise ArtifactError("STDLIB_LOGICAL_PATH_DUPLICATE")
            stdlib[candidate.logical_path] = candidate
            _cooperative_check(check)

    dependency_files: dict[str, FileCandidate] = {}
    dependency_physical_owners: dict[str, str] = {}
    observed_versions: dict[str, str] = {}
    expected_mapping_items = _cooperative_call(
        check,
        expected_dependency_versions.items,
    )
    expected_items = _cooperative_sorted(
        expected_mapping_items,
        check=check,
    )
    for expected_name, expected_version in expected_items:
        _cooperative_check(check)
        normalized_expected = _normalized_distribution_name(expected_name)
        if normalized_expected != expected_name:
            raise ArtifactError("EXPECTED_DEPENDENCY_NAME_NOT_NORMALIZED")
        try:
            distribution = _cooperative_call(
                check,
                importlib.metadata.distribution,
                expected_name,
            )
        except importlib.metadata.PackageNotFoundError as error:
            raise ArtifactError("DEPENDENCY_MISSING") from error
        metadata = _cooperative_call(check, getattr, distribution, "metadata")
        metadata_name = _cooperative_call(check, metadata.__getitem__, "Name")
        actual_name = _normalized_distribution_name(
            str(metadata_name)
        )
        actual_version = str(
            _cooperative_call(check, getattr, distribution, "version")
        )
        if actual_name != expected_name or actual_version != expected_version:
            raise ArtifactError("DEPENDENCY_VERSION_MISMATCH")
        files = _cooperative_call(check, getattr, distribution, "files")
        if files is None:
            raise ArtifactError("DEPENDENCY_FILE_LIST_MISSING")
        observed_versions[actual_name] = actual_version
        for package_path in _cooperative_tuple(files, check=check):
            _cooperative_check(check)
            candidate = _resolve_distribution_record_member(
                distribution,
                actual_name,
                package_path,
                scheme_roots,
                check=check,
            )
            if candidate is None:
                _cooperative_check(check)
                continue
            if candidate.logical_path in dependency_files:
                raise ArtifactError("DEPENDENCY_LOGICAL_PATH_DUPLICATE")
            existing_owner = dependency_physical_owners.get(candidate.real_path)
            if existing_owner is not None:
                raise ArtifactError("DEPENDENCY_PHYSICAL_PATH_DUPLICATE")
            dependency_files[candidate.logical_path] = candidate
            dependency_physical_owners[candidate.real_path] = (
                candidate.logical_path
            )
            _cooperative_check(check)
        _cooperative_check(check)

    for distribution_name, governed_members in _cooperative_tuple(
        GOVERNED_DEPENDENCY_DATA_PATHS.items(),
        check=check,
    ):
        _cooperative_check(check)
        if distribution_name not in expected_dependency_versions:
            raise ArtifactError("GOVERNED_DEPENDENCY_UNEXPECTED")
        if not governed_members:
            raise ArtifactError("GOVERNED_DEPENDENCY_DATA_EMPTY")
        for relative in _cooperative_tuple(governed_members, check=check):
            _cooperative_check(check)
            logical = f"{distribution_name}/{relative}"
            if logical not in dependency_files:
                raise ArtifactError("GOVERNED_DEPENDENCY_DATA_MISSING")

    try:
        mappings_raw = _cooperative_read_bytes(proc_maps_path, check=check)
    except OSError as error:
        raise ArtifactError("PROC_MAPS_UNREADABLE") from error
    mappings = parse_proc_maps(mappings_raw, check=check)
    native = _collect_native_candidates(mappings, check=check)
    classify_required_native_members(
        (candidate.real_path for candidate in native),
        python_executable=roots.python_executable,
        check=check,
    )
    observed_module_names = (
        _cooperative_module_snapshot(check=check)
        if module_names is None
        else module_names
    )
    repository_root = _cooperative_call(check, os.getcwd)
    repository_module_paths: set[str] = set()
    repository_source_paths: set[str] = {"quant/volatility_scorecard.py"}
    reused_paths = _cooperative_call(
        check,
        globals().get,
        "REUSED_PRIMITIVE_PATHS",
        frozenset(),
    )
    for item in _cooperative_tuple(reused_paths, check=check):
        _cooperative_check(check)
        item_text = _cooperative_call(check, str, item)
        if _cooperative_call(check, item_text.endswith, ".py"):
            _cooperative_call(check, repository_source_paths.add, item_text)
        _cooperative_check(check)
    for source_path in _cooperative_tuple(
        repository_source_paths,
        check=check,
    ):
        _cooperative_check(check)
        repository_module_paths.add(
            _cooperative_call(
                check,
                os.path.realpath,
                os.path.join(repository_root, source_path),
            )
        )
    repository_quant_root = _cooperative_call(
        check,
        os.path.realpath,
        os.path.join(repository_root, "quant"),
    )
    # Repository modules are authenticated separately against the reviewed
    # implementation merge, but their live SourceFileLoader origins must still
    # be admitted to this complete loaded-module proof.
    stdlib_source_candidates = _cooperative_call(
        check,
        tuple,
        stdlib.values(),
    )
    dependency_source_candidates = _cooperative_call(
        check,
        tuple,
        dependency_files.values(),
    )
    source_candidates = _cooperative_call(
        check,
        lambda left, right: left + right,
        stdlib_source_candidates,
        dependency_source_candidates,
    )
    validate_loaded_module_sources(
        observed_module_names,
        covered_source_paths=(
            *(candidate.real_path for candidate in source_candidates),
            *repository_module_paths,
        ),
        covered_native_paths=(candidate.real_path for candidate in native),
        namespace_roots=(
            roots.stdlib,
            roots.platstdlib,
            roots.purelib,
            roots.platlib,
            repository_quant_root,
        ),
        check=check,
    )
    ordered_observed_versions = _cooperative_sorted(
        observed_versions.items(),
        check=check,
    )
    ordered_stdlib_keys = _cooperative_sorted(stdlib, check=check)
    ordered_dependency_keys = _cooperative_sorted(
        dependency_files,
        check=check,
    )
    ordered_stdlib = _cooperative_call(
        check,
        tuple,
        _cooperative_tuple(
            (stdlib[key] for key in ordered_stdlib_keys),
            check=check,
        ),
    )
    ordered_dependencies = _cooperative_call(
        check,
        tuple,
        _cooperative_tuple(
            (dependency_files[key] for key in ordered_dependency_keys),
            check=check,
        ),
    )
    return _cooperative_call(
        check,
        RuntimeArtifactPlan,
        roots=roots,
        dependency_versions=ordered_observed_versions,
        stdlib_files=ordered_stdlib,
        dependency_files=ordered_dependencies,
        native_files=native,
        mappings=mappings,
        module_names=observed_module_names,
    )


def _measure_tree(
    candidates: Iterable[FileCandidate],
    access: FileAccess,
    *,
    check: Callable[[], object] | None = None,
) -> tuple[tuple[FileRecord, ...], str]:
    records: list[FileRecord] = []
    seen: set[str] = set()
    for candidate in _cooperative_tuple(candidates, check=check):
        _cooperative_check(check)
        if candidate.logical_path in seen:
            raise ArtifactError("ARTIFACT_LOGICAL_PATH_DUPLICATE")
        _cooperative_call(check, seen.add, candidate.logical_path)
        record = _cooperative_call(check, access.record, candidate)
        _cooperative_call(check, records.append, record)
        _cooperative_check(check)
    _cooperative_call(check, records.sort, key=lambda item: item.path)
    public: list[dict[str, object]] = []
    for record in records:
        _cooperative_check(check)
        _cooperative_call(check, public.append, record.public())
    frozen_records = _cooperative_call(check, tuple, records)
    digest = _cooperative_canonical_sha256(public, check=check)
    _cooperative_check(check)
    return frozen_records, digest


def measure_runtime_artifacts(
    plan: RuntimeArtifactPlan,
    *,
    access: FileAccess | None = None,
    include_dispatch: bool = True,
    symbol_resolver: Callable[[bytes], int] | None = None,
    check: Callable[[], object] | None = None,
) -> RuntimeMeasurement:
    """Measure exact bytes.  Probe passes include_dispatch=False."""
    if _ZONEINFO_ISOLATION is not None:
        _validate_zoneinfo_isolation(_ZONEINFO_ISOLATION, check=check)
    reader = LocalFileAccess(check=check) if access is None else access
    executable = _cooperative_call(
        check,
        reader.record,
        FileCandidate(
            plan.roots.python_executable,
            plan.roots.python_executable,
        ),
    )
    _, stdlib_sha = _measure_tree(plan.stdlib_files, reader, check=check)
    _, dependency_sha = _measure_tree(
        plan.dependency_files, reader, check=check
    )
    native_records, native_sha = _measure_tree(
        plan.native_files, reader, check=check
    )
    components = _cooperative_call(
        check,
        ArtifactComponents,
        executable.sha256,
        stdlib_sha,
        dependency_sha,
        native_sha,
    )
    component_object = _cooperative_call(check, components.public)
    dispatch = None
    dispatch_sha = None
    if include_dispatch:
        dispatch = resolve_libm_dispatch(
            plan.mappings,
            _cooperative_call(
                check,
                set,
                _cooperative_tuple(
                    (record.path for record in native_records),
                    check=check,
                ),
            ),
            symbol_resolver=symbol_resolver,
            check=check,
        )
        dispatch_sha = _cooperative_canonical_sha256(dispatch, check=check)
    return _cooperative_call(
        check,
        RuntimeMeasurement,
        components=components,
        runtime_artifact_sha256=_cooperative_canonical_sha256(
            component_object, check=check
        ),
        libm_dispatch=dispatch,
        libm_dispatch_sha256=dispatch_sha,
        dependency_versions=plan.dependency_versions,
        module_names=plan.module_names,
        python_executable_record=executable,
        native_records=native_records,
    )


def _production_dlsym(
    symbol: bytes,
    *,
    check: Callable[[], object] | None = None,
) -> int:
    try:
        process = _cooperative_call(check, ctypes.CDLL, None)
        _cooperative_check(check)
        dlsym = process.dlsym
        _cooperative_check(check)
        dlsym.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
        dlsym.restype = ctypes.c_void_p
        address = _cooperative_call(
            check,
            dlsym,
            ctypes.c_void_p(0),
            symbol,
        )
    except (AttributeError, OSError) as error:
        raise ArtifactError("DLSYM_FAILED") from error
    if not address:
        raise ArtifactError("DLSYM_FAILED")
    return int(address)


def _looks_like_libm(path: str) -> bool:
    name = os.path.basename(path)
    return bool(re.fullmatch(r"libm(?:-[^.]+)?\.so(?:\..+)?", name))


def resolve_libm_dispatch(
    mappings: Sequence[ProcMapEntry],
    native_paths: set[str],
    *,
    symbol_resolver: Callable[[bytes], int] | None = None,
    check: Callable[[], object] | None = None,
) -> dict[str, dict[str, object]]:
    """Pure apart from injected address lookup; ASLR addresses are not output."""
    result: dict[str, dict[str, object]] = {}
    libm_path: str | None = None
    for symbol in ("exp", "log"):
        _cooperative_check(check)
        encoded_symbol = _cooperative_call(check, symbol.encode, "ascii")
        if symbol_resolver is None:
            address = _production_dlsym(encoded_symbol, check=check)
        else:
            address = _cooperative_call(
                check,
                symbol_resolver,
                encoded_symbol,
            )
        matches: list[ProcMapEntry] = []
        for item in _cooperative_tuple(mappings, check=check):
            _cooperative_check(check)
            if "x" in item.permissions and item.start <= address < item.end:
                _cooperative_call(check, matches.append, item)
            _cooperative_check(check)
        if len(matches) != 1:
            raise ArtifactError("LIBM_MAPPING_NOT_UNIQUE")
        mapping = matches[0]
        if mapping.path is None or mapping.path.startswith("["):
            raise ArtifactError("LIBM_MAPPING_INVALID")
        path = _strict_real(
            _cooperative_call(check, os.path.realpath, mapping.path),
            check=check,
        )
        if (
            path not in native_paths
            or not _looks_like_libm(path)
            or mapping.file_offset < 0
        ):
            raise ArtifactError("LIBM_MAPPING_INVALID")
        if libm_path is None:
            libm_path = path
        elif path != libm_path:
            raise ArtifactError("LIBM_MAPPING_MISMATCH")
        file_offset = address - mapping.start + mapping.file_offset
        if file_offset < 0:
            raise ArtifactError("LIBM_OFFSET_INVALID")
        _cooperative_check(check)
        result[symbol] = {
            "loaded_native_path": path,
            "file_offset": file_offset,
        }
        _cooperative_check(check)
    return _cooperative_call(
        check,
        lambda: {"exp": result["exp"], "log": result["log"]},
    )


def verify_approved_artifacts(
    measurement: RuntimeMeasurement,
    approved_components: Mapping[str, object],
    *,
    check: Callable[[], object] | None = None,
) -> None:
    approved_keys = _cooperative_sorted(approved_components, check=check)
    expected_keys = _cooperative_sorted(RUNTIME_COMPONENT_KEYS, check=check)
    approved = _cooperative_call(check, dict, approved_components)
    measured = _cooperative_call(check, measurement.components.public)
    if (
        approved_keys != expected_keys
        or not _cooperative_call(check, lambda: approved == measured)
        or _cooperative_canonical_sha256(approved, check=check)
        != measurement.runtime_artifact_sha256
    ):
        raise ArtifactError("APPROVED_ARTIFACT_MISMATCH")
    _cooperative_check(check)


@dataclass(frozen=True, slots=True)
class FrozenRuntime:
    runtime_manifest_body: Mapping[str, object]
    runtime_manifest_sha256: str
    artifact_components: Mapping[str, str]
    module_names: frozenset[str]


def build_runtime_manifest(
    scalar_identity: Mapping[str, object],
    measurement: RuntimeMeasurement,
    *,
    check: Callable[[], object] | None = None,
) -> FrozenRuntime:
    _cooperative_check(check)
    if measurement.libm_dispatch is None or measurement.libm_dispatch_sha256 is None:
        raise ArtifactError("LIBM_DISPATCH_REQUIRED")
    body = _cooperative_call(check, dict, scalar_identity)
    _cooperative_call(
        check,
        body.update,
        {
            "dependency_versions": _cooperative_call(
                check,
                dict,
                measurement.dependency_versions,
            ),
            "runtime_artifact_components": _cooperative_call(
                check,
                measurement.components.public,
            ),
            "runtime_artifact_sha256": measurement.runtime_artifact_sha256,
            "libm_dispatch": _cooperative_call(
                check,
                dict,
                measurement.libm_dispatch,
            ),
            "libm_dispatch_sha256": measurement.libm_dispatch_sha256,
        },
    )
    if "runtime_manifest_sha256" in body:
        raise ArtifactError("RUNTIME_MANIFEST_SELF_HASH")
    digest = _cooperative_canonical_sha256(body, check=check)
    return _cooperative_call(
        check,
        FrozenRuntime,
        runtime_manifest_body=body,
        runtime_manifest_sha256=digest,
        artifact_components=_cooperative_call(
            check,
            measurement.components.public,
        ),
        module_names=measurement.module_names,
    )


def verify_runtime_unchanged(
    frozen: FrozenRuntime,
    current: FrozenRuntime,
    *,
    check: Callable[[], object] | None = None,
) -> None:
    current_body = _cooperative_call(
        check,
        canonical_json,
        current.runtime_manifest_body,
    )
    frozen_body = _cooperative_call(
        check,
        canonical_json,
        frozen.runtime_manifest_body,
    )
    if (
        current_body != frozen_body
        or current.runtime_manifest_sha256 != frozen.runtime_manifest_sha256
        or current.artifact_components != frozen.artifact_components
        or current.module_names != frozen.module_names
    ):
        raise ArtifactError("RUNTIME_CHANGED")
    _cooperative_check(check)


@dataclass(frozen=True, slots=True)
class RenderedRecoveryCommand:
    command: str
    command_bytes: int
    seal_bytes: int
    overhead_bytes: int


def render_recovery_start_command(
    manifest_id: str,
    seal_record_sha256: str,
    seal_bytes: bytes,
) -> RenderedRecoveryCommand:
    validate_command_constants()
    if manifest_id not in MANIFEST_IDS:
        raise ContractError("INVALID_MANIFEST_ID")
    if HEX64_RE.fullmatch(seal_record_sha256) is None:
        raise ContractError("INVALID_SEAL_DIGEST")
    if not seal_bytes.endswith(b"\n"):
        raise ContractError("INVALID_SEAL_BYTES")
    template = RECOVERY_START_COMMAND_TEMPLATE
    if (
        template.count("<manifest_id>") != 1
        or template.count("<seal_record_sha256>") != 1
        or template.count("<seal_bytes_hex>") != 1
    ):
        raise ContractError("RECOVERY_TEMPLATE_MISMATCH")
    command = (
        template.replace("<manifest_id>", manifest_id)
        .replace("<seal_record_sha256>", seal_record_sha256)
        .replace("<seal_bytes_hex>", seal_bytes.hex())
    )
    # Shell parsing is checked without executing the command.
    words = tuple(shlex.split(command, posix=True))
    if words[:7] != ("python", *ISOLATED_PYTHON_ARGS, "-c") or len(words) != 8:
        raise ContractError("RECOVERY_TEMPLATE_MISMATCH")
    if bytes.fromhex(seal_bytes.hex()) != seal_bytes:
        raise ContractError("RECOVERY_TEMPLATE_MISMATCH")
    if bytes.fromhex(RECOVERY_CHILD_C_HEX).decode("ascii") != NORMAL_C_BODY:
        raise ContractError("RECOVERY_TEMPLATE_MISMATCH")
    size = len(command.encode("utf-8"))
    seal_size = len(seal_bytes)
    overhead = size - (2 * seal_size)
    if overhead < 0 or size != overhead + (2 * seal_size):
        raise ContractError("RECOVERY_RENDER_ARITHMETIC")
    return RenderedRecoveryCommand(
        command=command,
        command_bytes=size,
        seal_bytes=seal_size,
        overhead_bytes=overhead,
    )


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    execution_source_sha: str
    render_service_id: str


@dataclass(frozen=True, slots=True)
class ProbeDependencies:
    observe_startup: Callable[[], StartupObservation]
    validate_startup: Callable[[StartupObservation], None]
    load_complete_closure: Callable[[], frozenset[str]]
    collect_plan: Callable[[frozenset[str]], RuntimeArtifactPlan]
    file_access: FileAccess
    source_identity: Callable[[], SourceIdentity]
    utc_now: Callable[[], datetime]
    write_stdout: Callable[[bytes], None]
    observe_github_tls_trust: Callable[[], GithubTlsTrustObservation] | None = None
    post_trust_module_names: Callable[[], frozenset[str]] | None = None


def _probe_line(value: object) -> bytes:
    return canonical_json(value).encode("utf-8") + b"\n"


PROBE_FAILED = {
    "mode": "V1B_PROVENANCE",
    "reason": "PROVENANCE_PROBE_FAILED",
    "status": "BLOCKED",
}
PROBE_USAGE_ERROR = {
    "mode": "V1B_PROVENANCE",
    "reason": "INVALID_PROBE_ARGUMENTS",
    "status": "USAGE_ERROR",
}


def run_provenance_probe(
    argv_tail: Sequence[str], dependencies: ProbeDependencies
) -> int:
    """Test seam: arguments and all production observations are explicit."""
    if argv_tail:
        try:
            dependencies.write_stdout(_probe_line(PROBE_USAGE_ERROR))
        except BaseException:
            pass
        return 2
    try:
        observation = dependencies.observe_startup()
        dependencies.validate_startup(observation)
        module_names = dependencies.load_complete_closure()
        if dependencies.observe_github_tls_trust is None:
            raise ContractError("PROBE_GITHUB_TLS_TRUST_UNWIRED")
        github_tls_trust = dependencies.observe_github_tls_trust()
        if dependencies.post_trust_module_names is not None:
            module_names = dependencies.post_trust_module_names()
        plan = dependencies.collect_plan(module_names)
        measurement = measure_runtime_artifacts(
            plan, access=dependencies.file_access, include_dispatch=False
        )
        identity = dependencies.source_identity()
        if (
            identity.render_service_id != RENDER_SERVICE_ID
            or HEX40_RE.fullmatch(identity.execution_source_sha) is None
            or tuple(measurement.components.public()) != RUNTIME_COMPONENT_KEYS
        ):
            raise ContractError("PROBE_IDENTITY_INVALID")
        generated = dependencies.utc_now()
        if generated.tzinfo is None:
            raise ContractError("PROBE_CLOCK_INVALID")
        record = {
            "schema_version": "ATOM-V1B-RUNTIME-PROBE-1",
            "render_service_id": RENDER_SERVICE_ID,
            "execution_source_sha": identity.execution_source_sha,
            "python_version": EXPECTED_PYTHON_VERSION_TEXT,
            "runtime_artifact_components": measurement.components.public(),
            "runtime_artifact_sha256": measurement.runtime_artifact_sha256,
            "probe_generated_at_utc": generated.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "github_tls_trust": github_tls_trust.public(),
        }
    except Exception:
        try:
            dependencies.write_stdout(_probe_line(PROBE_FAILED))
        except BaseException:
            pass
        return 1
    # Once any success byte may have reached stdout, a sink error is an
    # infrastructure failure.  Emitting a second JSON line would turn a
    # truncated/partial success observation into an ambiguous two-record log.
    try:
        dependencies.write_stdout(_probe_line(record))
    except BaseException:
        return 1
    return 0


def _write_stdout_bytes(data: bytes) -> None:
    stream = sys.stdout.buffer
    written = stream.write(data)
    if written != len(data):
        raise OSError("short stdout write")
    stream.flush()



def _load_complete_runtime_closure() -> frozenset[str]:
    # Imports happen only after the common startup guard has passed.  The
    # explicit third-party entries ensure that every distribution in the
    # frozen dependency literal is loaded before native/file fingerprinting;
    # the returned sys.modules snapshot also binds their transitive modules.
    for name in (
        "argparse",
        "ast",
        "ctypes",
        "dateutil",
        "email.parser",
        "exchange_calendars",
        "http.client",
        "korean_lunar_calendar",
        "math",
        "numpy",
        "pandas",
        "psycopg",
        "psycopg.conninfo",
        "psycopg.connection",
        "psycopg.cursor",
        "psycopg.pq",
        "psycopg_binary",
        "pyluach",
        "quant.v9_v1_contract",
        "quant.v9_v2a_dataset",
        "quant.v9_v2b_calibration",
        "quant.v9_v2c_covariance",
        "quant.v9_v2d_evidence_state",
        "quant.v9_v3_synthesis",
        "quant.v9_v4a_evidence",
        "quant.v9_v4b_accuracy",
        "quant.v9_v4c_predictive",
        "selectors",
        "six",
        "socket",
        "ssl",
        "toolz",
        "tzdata",
        "urllib.parse",
        "zoneinfo",
    ):
        importlib.import_module(name)
    return frozenset(sys.modules)


@dataclass(frozen=True, slots=True)
class RuntimeInitialization:
    """No-network/no-database initialization shared by probe and scorecard."""

    module_names: frozenset[str]
    xnys_calendar: object
    home_dir: Path
    v4a: object
    v4b: object
    v4c: object
    psycopg_module: object
    conninfo_module: object
    zoneinfo_isolation: ZoneInfoIsolation


def _initialize_runtime_for_measurement() -> RuntimeInitialization:
    """Load and exercise every lazy local closure before artifact planning."""

    zone_state = _initialize_zoneinfo_isolation()
    _validate_zoneinfo_isolation(zone_state)
    _load_complete_runtime_closure()
    try:
        _validate_zoneinfo_isolation(zone_state)
        calendars_module = sys.modules["exchange_calendars"]
        xnys_calendar = calendars_module.get_calendar("XNYS")
        _validate_zoneinfo_isolation(zone_state)
        helpers = sys.modules["exchange_calendars.calendar_helpers"]
        xnys_zone = getattr(xnys_calendar, "tz", None)
        helper_utc = getattr(helpers, "UTC", None)
        if (
            not isinstance(xnys_zone, zone_state.zoneinfo_class)
            or getattr(xnys_zone, "key", None) != "America/New_York"
            or not isinstance(helper_utc, zone_state.zoneinfo_class)
            or getattr(helper_utc, "key", None) != "UTC"
        ):
            raise StartupIsolationError("XNYS_ZONEINFO_SOURCE_INVALID")
        home_dir = Path.home()
        v4a = sys.modules["quant.v9_v4a_evidence"]
        v4b = sys.modules["quant.v9_v4b_accuracy"]
        v4c = sys.modules["quant.v9_v4c_predictive"]
        psycopg_module = sys.modules["psycopg"]
        conninfo_module = sys.modules["psycopg.conninfo"]
    except BaseException:
        raise OrchestrationFailure("RUNTIME_CLOSURE_INITIALIZATION_FAILED") from None
    endpoint_delay = getattr(v4a, "MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS", None)
    if type(endpoint_delay) is not float or endpoint_delay.hex() != "0x1.4000000000000p+2":
        raise OrchestrationFailure("V4A_OVERLAP_CONTRACT_CHANGED")
    return RuntimeInitialization(
        module_names=frozenset(sys.modules),
        xnys_calendar=xnys_calendar,
        home_dir=home_dir,
        v4a=v4a,
        v4b=v4b,
        v4c=v4c,
        psycopg_module=psycopg_module,
        conninfo_module=conninfo_module,
        zoneinfo_isolation=zone_state,
    )


def _production_source_identity() -> SourceIdentity:
    service = os.environ.get("RENDER_SERVICE_ID", "")
    render_sha = os.environ.get("RENDER_GIT_COMMIT", "")
    if service != RENDER_SERVICE_ID or HEX40_RE.fullmatch(render_sha) is None:
        raise ContractError("PROBE_SOURCE_IDENTITY_INVALID")
    try:
        context = GithubDeadlineContext.begin_checkpoint(time.monotonic_ns)
        completed = _checkpoint_git_run(
            context,
            time.monotonic_ns,
            "rev-parse",
            "HEAD",
            check=True,
        )
    except OrchestrationFailure as error:
        raise ContractError("PROBE_SOURCE_IDENTITY_INVALID") from error
    local = completed.stdout.strip().decode("ascii", "strict")
    if local != render_sha or HEX40_RE.fullmatch(local) is None:
        raise ContractError("PROBE_SOURCE_IDENTITY_INVALID")
    return SourceIdentity(local, service)


def _production_probe_dependencies() -> ProbeDependencies:
    def validate(observation: StartupObservation) -> None:
        validate_startup_observation(observation, mode="probe")

    def collect(module_names: frozenset[str]) -> RuntimeArtifactPlan:
        return collect_runtime_artifact_plan(
            EXPECTED_DEPENDENCY_VERSIONS, module_names=module_names
        )

    def initialize() -> frozenset[str]:
        return _initialize_runtime_for_measurement().module_names

    return ProbeDependencies(
        observe_startup=observe_live_startup,
        validate_startup=validate,
        load_complete_closure=initialize,
        collect_plan=collect,
        file_access=LocalFileAccess(),
        source_identity=_production_source_identity,
        utc_now=lambda: datetime.now(timezone.utc),
        write_stdout=_write_stdout_bytes,
        observe_github_tls_trust=observe_github_tls_trust,
        post_trust_module_names=_cooperative_module_snapshot,
    )


def provenance_probe_main() -> int:
    """Exact public entry point: deliberately takes no argument."""
    return run_provenance_probe(
        tuple(sys.argv[1:]), _production_probe_dependencies()
    )


READINESS_KEYS = (
    "rule_version", "status", "amendment_merged_at_utc", "scan_started_at",
    "first_candidate_session", "boundary_session", "boundary_as_of_at",
    "selected_lineages", "cohort_trace", "counts", "readiness_identity",
)
READINESS_BODY_KEYS = (
    "decision_id", "amendment_id", "job_id", "contract_path", "amendment_path",
    "verified_main_sha", "v1a_merge_sha", "amendment_merge_sha",
    "tls_amendment_id", "tls_amendment_path", "tls_amendment_merge_sha",
    "evidence_artifacts", "manifest_id", "manifest_registry_order",
    "manifest_cells", "rule_version", "status", "amendment_merged_at_utc",
    "scan_started_at", "first_candidate_session", "boundary_session",
    "boundary_as_of_at", "selected_lineages", "cohort_trace", "counts",
    "reader_identity", "database_identity", "runtime_manifest_sha256",
)
RUN_IDENTITY_BODY_KEYS = (
    "decision_id", "amendment_id", "job_id", "contract_path", "amendment_path",
    "verified_main_sha", "v1a_merge_sha", "amendment_merge_sha",
    "tls_amendment_id", "tls_amendment_path", "tls_amendment_merge_sha",
    "evidence_artifacts", "manifest_id", "manifest_registry_order",
    "manifest_cells", "readiness_identity", "evaluation_session",
    "evaluation_as_of_at", "runtime_manifest_sha256", "selected_lineages",
)
SEAL_BODY_KEYS = (
    "seal_schema_version", "initial_authority_proof", "readiness_identity_body",
    "readiness", "run_identity_body", "run_identity",
)
SEAL_RECORD_KEYS = SEAL_BODY_KEYS + ("seal_record_sha256",)

COUNT_KEYS = (
    "cell_order", "forecaster", "horizon", "n_regression_windows",
    "n_regression_sessions", "n_unconditional_gate_windows",
    "n_unconditional_gate_sessions", "n_seasonal_gate_windows",
    "n_seasonal_gate_sessions", "all_minima_pass",
)
MANIFEST_CELL_KEYS = ("cell_order", "forecaster", "horizon")
SELECTED_LINEAGE_KEYS = MANIFEST_CELL_KEYS + ("lineage_identity",)
COHORT_EVENT_KEYS = (
    "cell_order", "forecaster", "horizon", "candidate_session", "event_type",
    "selected_lineage_identity",
)
FAMILY_LINEAGE_KEYS = ("quant_id", "formula_version", "symbol", "horizon")
V9_LINEAGE_KEYS = ("v3_model_version", "symbol", "horizon", "cohort_id", "cohort_hash")

EVALUATED_BASE_KEYS = (
    "schema_version", "decision_id", "job_id", "contract_path", "code_version",
    "verified_main_sha", "v1a_merge_sha", "run_identity", "evaluation_session",
    "evaluation_as_of_at", "generated_at_utc", "reader_identity",
    "database_identity", "runtime_identity", "authority_proof", "bootstrap",
    "cells", "overall_status", "overall_reason_codes", "scouting_disclosure",
    "read_only", "forecast_writes", "outcome_writes", "evidence_writes",
    "receipt_sha256",
)
AMENDED_EVALUATED_KEYS = (
    "amendment_id", "amendment_path", "amendment_merge_sha", "tls_amendment_id",
    "tls_amendment_path", "tls_amendment_merge_sha", "evidence_artifacts",
    "manifest_id", "manifest_registry_order", "manifest_cells", "readiness",
    "seal_record_sha256", "result_scope",
)
EVALUATED_KEYS = EVALUATED_BASE_KEYS + AMENDED_EVALUATED_KEYS

BLOCKED_BASE_KEYS = (
    "schema_version", "decision_id", "job_id", "contract_path",
    "generated_at_utc", "stage", "reason_codes", "observed_main_sha",
    "expected_main_sha", "observed_v1a_merge_sha", "observed_user",
    "observed_database", "observed_effective_host", "project_binding_verified",
    "read_only", "receipt_sha256",
)
PRE_CELL_BASE_KEYS = (
    "schema_version", "decision_id", "job_id", "contract_path",
    "verified_main_sha", "v1a_merge_sha", "evaluation_session",
    "evaluation_as_of_at", "generated_at_utc", "stage", "reason_codes",
    "reader_identity", "database_identity", "authority_proof", "read_only",
    "forecast_writes", "outcome_writes", "evidence_writes", "receipt_sha256",
)
POST_EVAL_BASE_KEYS = (
    "schema_version", "decision_id", "job_id", "contract_path",
    "verified_main_sha", "v1a_merge_sha", "run_identity", "evaluation_session",
    "evaluation_as_of_at", "generated_at_utc", "stage", "reason_codes",
    "reader_identity", "database_identity", "initial_authority_proof",
    "read_only", "forecast_writes", "outcome_writes", "evidence_writes",
    "receipt_sha256",
)
AMENDED_NEGATIVE_KEYS = (
    "amendment_id", "amendment_path", "amendment_merge_sha", "tls_amendment_id",
    "tls_amendment_path", "tls_amendment_merge_sha", "evidence_artifacts",
    "manifest_id", "manifest_registry_order", "manifest_cells", "readiness",
    "sealed_run_identity", "seal_record_sha256", "result_scope",
)
BLOCKED_KEYS = BLOCKED_BASE_KEYS + AMENDED_NEGATIVE_KEYS
PRE_CELL_KEYS = PRE_CELL_BASE_KEYS + AMENDED_NEGATIVE_KEYS
POST_EVAL_KEYS = POST_EVAL_BASE_KEYS + AMENDED_NEGATIVE_KEYS


CELL_KEYS = (
    "cell_order", "forecaster", "horizon", "lineage_identity", "session_dates",
    "evidence_min_cutoff_at", "evidence_max_cutoff_at", "n_input",
    "n_unselected_lineage_rows", "n_inadmissible", "n_non_rth",
    "n_overlap_excluded", "n_null_or_nonfinite_excluded",
    "n_nonpositive_prediction_excluded", "n_kappa_unavailable", "n_windows",
    "n_sessions", "n_persist20_unavailable", "n_regression_windows",
    "n_regression_sessions", "mae_bps", "rank_corr", "level_ratio",
    "coverage_90", "mz_a", "mz_b", "mz_r2", "persist_rank_corr", "enc_b",
    "enc_b_ci_0999", "enc_b_ci_095", "bootstrap_attempted_draws",
    "bootstrap_valid_draws", "bootstrap_invalid_draws",
    "n_unconditional_unavailable", "n_unconditional_gate_windows",
    "n_unconditional_gate_sessions", "n_seasonal_gate_windows",
    "n_seasonal_gate_sessions", "unconditional_rank_corr", "seasonal_rank_corr",
    "qlike_candidate", "qlike_unconditional", "qlike_seasonal",
    "d_unconditional", "d_unconditional_ci_0999", "d_unconditional_ci_095",
    "d_seasonal", "d_seasonal_ci_0999", "d_seasonal_ci_095",
    "unconditional_bootstrap_attempted_draws",
    "unconditional_bootstrap_valid_draws",
    "unconditional_bootstrap_invalid_draws", "seasonal_bootstrap_attempted_draws",
    "seasonal_bootstrap_valid_draws", "seasonal_bootstrap_invalid_draws",
    "gate_unconditional", "gate_seasonal", "classification", "reason_codes",
)


AUTHORITY_PROOF_KEYS = (
    "current_user", "session_user", "dsn_login_user", "dsn_password_present",
    "dsn_password_fallbacks_absent", "dsn_sslmode", "dsn_sslrootcert",
    "sslrootcert_sha256", "dsn_sslcertmode", "dsn_require_auth",
    "dsn_tls_fallbacks_absent", "tls_active", "dsn_identity_overrides_absent",
    "current_database", "database_owner", "database_create",
    "database_temporary", "database_temporary_public_only",
    "session_temp_schema_created", "effective_host", "effective_port",
    "project_binding_verified", "schema_public_usage", "schema_public_create",
    "non_system_schema_create_privilege_count", "schema_atom_v9_internal_usage",
    "proof_functions_execute", "proof_function_definitions",
    "non_system_security_definer_execute_privilege_count",
    "reader_role_attributes", "reader_role_memberships", "six_tables_select",
    "six_tables_insert", "six_tables_update", "six_tables_delete",
    "six_tables_truncate", "non_system_relation_write_privilege_count",
    "six_tables_rls_enabled", "six_tables_permissive_full_read",
    "six_tables_restrictive_select", "transaction_isolation",
    "read_only_transaction", "verification_status",
)

RUNTIME_IDENTITY_KEYS = (
    "render_service_id", "render_runtime", "python_implementation",
    "python_version_source", "python_version_env", "python_version",
    "python_cache_tag", "platform_system", "platform_machine", "byteorder",
    "libc_name", "libc_version", "float_radix", "float_mant_dig",
    "float_max_exp", "float_rounds", "libpq_version", "dependency_versions",
    "runtime_artifact_components", "runtime_artifact_sha256", "libm_dispatch",
    "libm_dispatch_sha256", "runtime_manifest_sha256",
)


def canonical_line(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8") + b"\n"


def json_clone(value: Any) -> Any:
    return json.loads(canonical_json(value))


def exact_keys(value: Any, keys: Sequence[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys) or len(value) != len(keys):
        raise ProtocolDefect(f"{label}: wrong key set")
    return value


def require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ProtocolDefect(f"{label}: boolean required")
    return value


def require_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ProtocolDefect(f"{label}: integer domain")
    return value


def require_str(value: Any, label: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or (nonempty and not value):
        raise ProtocolDefect(f"{label}: string domain")
    return value


def require_hex(value: Any, regex: re.Pattern[str], label: str) -> str:
    if type(value) is not str or regex.fullmatch(value) is None:
        raise ProtocolDefect(f"{label}: lowercase hexadecimal domain")
    return value


def require_date(value: Any, label: str) -> str:
    require_str(value, label)
    if SESSION_DATE_RE.fullmatch(value) is None:
        raise ProtocolDefect(f"{label}: YYYY-MM-DD required")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as error:
        raise ProtocolDefect(f"{label}: invalid date") from error
    return value


def require_utc_micro(value: Any, label: str) -> str:
    require_str(value, label)
    if UTC_MICROSECOND_RE.fullmatch(value) is None:
        raise ProtocolDefect(f"{label}: RFC3339 microseconds required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ProtocolDefect(f"{label}: invalid UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise ProtocolDefect(f"{label}: noncanonical UTC timestamp")
    return value


def validate_database_identity(value: Any) -> None:
    obj = exact_keys(value, ("supabase_project_ref", "database_name"), "database_identity")
    if obj != {"supabase_project_ref": "afyiydxbjgzaiswnbcyj", "database_name": "postgres"}:
        raise ProtocolDefect("database_identity: wrong target")


@dataclass(frozen=True)
class IdentityContext:
    verified_main_sha: str
    v1a_merge_sha: str
    amendment_merge_sha: str
    tls_amendment_merge_sha: str
    manifest_id: str
    database_identity: Mapping[str, Any]
    runtime_manifest_sha256: str


def validate_identity_context(context: IdentityContext) -> None:
    require_hex(context.verified_main_sha, HEX40_RE, "verified_main_sha")
    if context.v1a_merge_sha != V1A_MERGE_SHA:
        raise ProtocolDefect("wrong V-1A merge")
    if context.amendment_merge_sha != AMENDMENT_MERGE_SHA:
        raise ProtocolDefect("wrong Amendment 2A merge")
    if context.tls_amendment_merge_sha != TLS_AMENDMENT_MERGE_SHA:
        raise ProtocolDefect("wrong TLS amendment merge")
    manifest_sequence(context.manifest_id)
    validate_database_identity(dict(context.database_identity))
    require_hex(context.runtime_manifest_sha256, HEX64_RE, "runtime_manifest_sha256")


def _fixed_context_fields(context: IdentityContext) -> dict[str, Any]:
    validate_identity_context(context)
    return {
        "decision_id": DECISION_ID,
        "amendment_id": AMENDMENT_ID,
        "job_id": JOB_ID,
        "contract_path": CONTRACT_PATH,
        "amendment_path": AMENDMENT_PATH,
        "verified_main_sha": context.verified_main_sha,
        "v1a_merge_sha": context.v1a_merge_sha,
        "amendment_merge_sha": context.amendment_merge_sha,
        "tls_amendment_id": TLS_AMENDMENT_ID,
        "tls_amendment_path": TLS_AMENDMENT_PATH,
        "tls_amendment_merge_sha": context.tls_amendment_merge_sha,
        "evidence_artifacts": evidence_artifacts(),
        "manifest_id": context.manifest_id,
        "manifest_registry_order": manifest_sequence(context.manifest_id),
        "manifest_cells": manifest_public_cells(context.manifest_id),
    }


def _validate_manifest_triplet(value: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    exact_keys(value, MANIFEST_CELL_KEYS, label)
    if value != expected:
        raise ProtocolDefect(f"{label}: wrong manifest cell")


def _validate_lineage(value: Any, *, forecaster: str, horizon: str, label: str) -> None:
    if forecaster == "FAMILY-VOL":
        obj = exact_keys(value, FAMILY_LINEAGE_KEYS, label)
        if obj != {
            "quant_id": "q3_volatility",
            "formula_version": "realized-volatility-v1",
            "symbol": "COIN",
            "horizon": horizon,
        }:
            raise ProtocolDefect(f"{label}: wrong FAMILY lineage")
        return
    if forecaster != "V9-VOL":
        raise ProtocolDefect(f"{label}: unknown forecaster")
    obj = exact_keys(value, V9_LINEAGE_KEYS, label)
    spec = next(
        (
            candidate
            for candidate in CELL_BY_ORDER.values()
            if candidate.forecaster == forecaster and candidate.horizon == horizon
        ),
        None,
    )
    if spec is None:
        raise ProtocolDefect(f"{label}: noncanonical V9 cell")
    try:
        validate_lineage_identity(spec, obj)
    except ProtocolDefect as error:
        raise ProtocolDefect(f"{label}: {error}") from error


def validate_selected_lineages(manifest_id: str, value: Any) -> None:
    if type(value) is not list:
        raise ProtocolDefect("selected_lineages: array required")
    expected_cells = manifest_public_cells(manifest_id)
    if len(value) != len(expected_cells):
        raise ProtocolDefect("selected_lineages: wrong length")
    for index, (wrapper, expected) in enumerate(zip(value, expected_cells, strict=True)):
        obj = exact_keys(wrapper, SELECTED_LINEAGE_KEYS, f"selected_lineages[{index}]")
        for key in MANIFEST_CELL_KEYS:
            if obj[key] != expected[key]:
                raise ProtocolDefect(f"selected_lineages[{index}]: wrong cell")
        _validate_lineage(
            obj["lineage_identity"],
            forecaster=expected["forecaster"],
            horizon=expected["horizon"],
            label=f"selected_lineages[{index}].lineage_identity",
        )


def validate_counts(manifest_id: str, value: Any) -> None:
    if type(value) is not list:
        raise ProtocolDefect("counts: array required")
    expected_cells = manifest_public_cells(manifest_id)
    if len(value) != len(expected_cells):
        raise ProtocolDefect("counts: wrong length")
    window_keys = (
        "n_regression_windows",
        "n_unconditional_gate_windows",
        "n_seasonal_gate_windows",
    )
    session_keys = (
        "n_regression_sessions",
        "n_unconditional_gate_sessions",
        "n_seasonal_gate_sessions",
    )
    for index, (count, expected) in enumerate(zip(value, expected_cells, strict=True)):
        obj = exact_keys(count, COUNT_KEYS, f"counts[{index}]")
        for key in MANIFEST_CELL_KEYS:
            if obj[key] != expected[key]:
                raise ProtocolDefect(f"counts[{index}]: wrong cell")
        for key in window_keys:
            if require_int(obj[key], f"counts[{index}].{key}", minimum=0) < 100:
                raise ProtocolDefect(f"counts[{index}].{key}: READY minimum failed")
        for key in session_keys:
            if require_int(obj[key], f"counts[{index}].{key}", minimum=0) < 10:
                raise ProtocolDefect(f"counts[{index}].{key}: READY minimum failed")
        if require_bool(obj["all_minima_pass"], f"counts[{index}].all_minima_pass") is not True:
            raise ProtocolDefect(f"counts[{index}]: all_minima_pass must be true")


def validate_cohort_trace(
    manifest_id: str,
    value: Any,
    *,
    first_candidate_session: str,
    boundary_session: str,
    selected_lineages: Sequence[Mapping[str, Any]],
) -> None:
    if type(value) is not list:
        raise ProtocolDefect("cohort_trace: array required")
    expected_cells = manifest_public_cells(manifest_id)
    expected_by_order = {item["cell_order"]: item for item in expected_cells}
    selected_by_order = {item["cell_order"]: item["lineage_identity"] for item in selected_lineages}
    v9_orders = tuple(item["cell_order"] for item in expected_cells if item["forecaster"] == "V9-VOL")
    if not v9_orders:
        if value != []:
            raise ProtocolDefect("cohort_trace: FAMILY manifest must be empty")
        return
    prior_sort_key: tuple[str, int] | None = None
    last_lineage: dict[int, Any] = {}
    initial_seen: set[int] = set()
    for index, event in enumerate(value):
        obj = exact_keys(event, COHORT_EVENT_KEYS, f"cohort_trace[{index}]")
        order = require_int(obj["cell_order"], f"cohort_trace[{index}].cell_order")
        expected = expected_by_order.get(order)
        if expected is None or expected["forecaster"] != "V9-VOL":
            raise ProtocolDefect(f"cohort_trace[{index}]: nonmanifest/non-V9 cell")
        if obj["forecaster"] != "V9-VOL" or obj["horizon"] != expected["horizon"]:
            raise ProtocolDefect(f"cohort_trace[{index}]: wrong V9 cell")
        session = require_date(obj["candidate_session"], f"cohort_trace[{index}].candidate_session")
        if not first_candidate_session <= session <= boundary_session:
            raise ProtocolDefect(f"cohort_trace[{index}]: outside examined range")
        sort_key = (session, order)
        if prior_sort_key is not None and sort_key <= prior_sort_key:
            raise ProtocolDefect("cohort_trace: not strictly candidate/cell ordered")
        prior_sort_key = sort_key
        event_type = obj["event_type"]
        if event_type not in {"INITIAL", "ROTATION"}:
            raise ProtocolDefect(f"cohort_trace[{index}]: bad event type")
        lineage = obj["selected_lineage_identity"]
        _validate_lineage(
            lineage,
            forecaster="V9-VOL",
            horizon=expected["horizon"],
            label=f"cohort_trace[{index}].selected_lineage_identity",
        )
        if order not in initial_seen:
            if event_type != "INITIAL" or session != first_candidate_session:
                raise ProtocolDefect(f"cohort_trace[{index}]: first event must be INITIAL at first candidate")
            initial_seen.add(order)
        elif event_type != "ROTATION" or lineage == last_lineage[order]:
            raise ProtocolDefect(f"cohort_trace[{index}]: invalid/redundant rotation")
        last_lineage[order] = lineage
    if initial_seen != set(v9_orders):
        raise ProtocolDefect("cohort_trace: missing V9 INITIAL event")
    for order in v9_orders:
        if last_lineage[order] != selected_by_order[order]:
            raise ProtocolDefect("cohort_trace: final lineage mismatch")


def _validate_identity_body_fixed(value: Mapping[str, Any]) -> str:
    if value["decision_id"] != DECISION_ID or value["amendment_id"] != AMENDMENT_ID:
        raise ProtocolDefect("identity body: decision/amendment mismatch")
    if value["job_id"] != JOB_ID or value["contract_path"] != CONTRACT_PATH:
        raise ProtocolDefect("identity body: job/contract mismatch")
    if value["amendment_path"] != AMENDMENT_PATH:
        raise ProtocolDefect("identity body: amendment path mismatch")
    require_hex(value["verified_main_sha"], HEX40_RE, "identity.verified_main_sha")
    if value["v1a_merge_sha"] != V1A_MERGE_SHA:
        raise ProtocolDefect("identity body: V-1A merge mismatch")
    if value["amendment_merge_sha"] != AMENDMENT_MERGE_SHA:
        raise ProtocolDefect("identity body: Amendment 2A merge mismatch")
    if value["tls_amendment_id"] != TLS_AMENDMENT_ID or value["tls_amendment_path"] != TLS_AMENDMENT_PATH:
        raise ProtocolDefect("identity body: TLS identity mismatch")
    if value["tls_amendment_merge_sha"] != TLS_AMENDMENT_MERGE_SHA:
        raise ProtocolDefect("identity body: TLS merge mismatch")
    if value["evidence_artifacts"] != evidence_artifacts():
        raise ProtocolDefect("identity body: evidence artifacts mismatch")
    manifest_id = require_str(value["manifest_id"], "identity.manifest_id")
    if value["manifest_registry_order"] != manifest_sequence(manifest_id):
        raise ProtocolDefect("identity body: manifest order mismatch")
    if value["manifest_cells"] != manifest_public_cells(manifest_id):
        raise ProtocolDefect("identity body: manifest cells mismatch")
    require_hex(value["runtime_manifest_sha256"], HEX64_RE, "identity.runtime_manifest_sha256")
    return manifest_id


def build_readiness(
    *,
    context: IdentityContext,
    amendment_merged_at_utc: str,
    scan_started_at: str,
    first_candidate_session: str,
    boundary_session: str,
    boundary_as_of_at: str,
    selected_lineages: list[dict[str, Any]],
    cohort_trace: list[dict[str, Any]],
    counts: list[dict[str, Any]],
    semantic_ready_validator: Callable[[Mapping[str, Any]], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the A2 readiness body/object after same-snapshot earliest-boundary proof.

    ``semantic_ready_validator`` must independently recompute the complete
    candidate sequence and prove the supplied boundary is the earliest READY
    candidate.  A schema builder cannot infer that fact from the receipt fields.
    """
    validate_identity_context(context)
    require_utc_micro(amendment_merged_at_utc, "amendment_merged_at_utc")
    require_utc_micro(scan_started_at, "scan_started_at")
    require_date(first_candidate_session, "first_candidate_session")
    require_date(boundary_session, "boundary_session")
    require_utc_micro(boundary_as_of_at, "boundary_as_of_at")
    if boundary_session < first_candidate_session:
        raise ProtocolDefect("boundary precedes first candidate")
    validate_selected_lineages(context.manifest_id, selected_lineages)
    validate_counts(context.manifest_id, counts)
    validate_cohort_trace(
        context.manifest_id,
        cohort_trace,
        first_candidate_session=first_candidate_session,
        boundary_session=boundary_session,
        selected_lineages=selected_lineages,
    )
    common = _fixed_context_fields(context)
    body = {
        **common,
        "rule_version": "ATOM-V1B-MANIFEST-READINESS-1",
        "status": "READY",
        "amendment_merged_at_utc": amendment_merged_at_utc,
        "scan_started_at": scan_started_at,
        "first_candidate_session": first_candidate_session,
        "boundary_session": boundary_session,
        "boundary_as_of_at": boundary_as_of_at,
        "selected_lineages": json_clone(selected_lineages),
        "cohort_trace": json_clone(cohort_trace),
        "counts": json_clone(counts),
        "reader_identity": READER_ROLE,
        "database_identity": json_clone(dict(context.database_identity)),
        "runtime_manifest_sha256": context.runtime_manifest_sha256,
    }
    exact_keys(body, READINESS_BODY_KEYS, "readiness_identity_body")
    semantic_ready_validator(json_clone(body))
    readiness = {
        **{key: json_clone(body[key]) for key in READINESS_KEYS[:-1]},
        "readiness_identity": canonical_sha256(body),
    }
    validate_readiness(body, readiness)
    return json_clone(body), json_clone(readiness)


def validate_readiness(body_value: Any, readiness_value: Any) -> None:
    body = exact_keys(body_value, READINESS_BODY_KEYS, "readiness_identity_body")
    readiness = exact_keys(readiness_value, READINESS_KEYS, "readiness")
    manifest_id = _validate_identity_body_fixed(body)
    if body["rule_version"] != "ATOM-V1B-MANIFEST-READINESS-1" or body["status"] != "READY":
        raise ProtocolDefect("readiness: wrong rule/status")
    require_utc_micro(body["amendment_merged_at_utc"], "readiness.amendment_merged_at_utc")
    require_utc_micro(body["scan_started_at"], "readiness.scan_started_at")
    first = require_date(body["first_candidate_session"], "readiness.first_candidate_session")
    boundary = require_date(body["boundary_session"], "readiness.boundary_session")
    require_utc_micro(body["boundary_as_of_at"], "readiness.boundary_as_of_at")
    if boundary < first:
        raise ProtocolDefect("readiness: boundary precedes first candidate")
    if body["reader_identity"] != READER_ROLE:
        raise ProtocolDefect("readiness: reader mismatch")
    validate_database_identity(body["database_identity"])
    validate_selected_lineages(manifest_id, body["selected_lineages"])
    validate_counts(manifest_id, body["counts"])
    validate_cohort_trace(
        manifest_id,
        body["cohort_trace"],
        first_candidate_session=first,
        boundary_session=boundary,
        selected_lineages=body["selected_lineages"],
    )
    expected = {key: json_clone(body[key]) for key in READINESS_KEYS[:-1]}
    expected["readiness_identity"] = canonical_sha256(body)
    if readiness != expected:
        raise ProtocolDefect("readiness: body/hash projection mismatch")
    require_hex(readiness["readiness_identity"], HEX64_RE, "readiness_identity")


def build_run_identity(
    *,
    readiness_identity_body: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    validate_readiness(dict(readiness_identity_body), dict(readiness))
    rb = readiness_identity_body
    body = {
        key: json_clone(rb[key])
        for key in RUN_IDENTITY_BODY_KEYS
        if key not in {"readiness_identity", "evaluation_session", "evaluation_as_of_at"}
    }
    body["readiness_identity"] = readiness["readiness_identity"]
    body["evaluation_session"] = readiness["boundary_session"]
    body["evaluation_as_of_at"] = readiness["boundary_as_of_at"]
    exact_keys(body, RUN_IDENTITY_BODY_KEYS, "run_identity_body")
    digest = canonical_sha256(body)
    validate_run_identity(body, digest, readiness_identity_body, readiness)
    return json_clone(body), digest


def validate_run_identity(
    run_body_value: Any,
    run_identity: Any,
    readiness_body_value: Any,
    readiness_value: Any,
) -> None:
    body = exact_keys(run_body_value, RUN_IDENTITY_BODY_KEYS, "run_identity_body")
    readiness_body = exact_keys(readiness_body_value, READINESS_BODY_KEYS, "readiness_identity_body")
    readiness = exact_keys(readiness_value, READINESS_KEYS, "readiness")
    validate_readiness(readiness_body, readiness)
    _validate_identity_body_fixed(body)
    shared = set(RUN_IDENTITY_BODY_KEYS) & set(READINESS_BODY_KEYS)
    shared -= {"selected_lineages"}
    for key in shared:
        if body[key] != readiness_body[key]:
            raise ProtocolDefect(f"run identity: {key} mismatch")
    if body["readiness_identity"] != readiness["readiness_identity"]:
        raise ProtocolDefect("run identity: readiness hash mismatch")
    if body["evaluation_session"] != readiness["boundary_session"]:
        raise ProtocolDefect("run identity: evaluation session mismatch")
    if body["evaluation_as_of_at"] != readiness["boundary_as_of_at"]:
        raise ProtocolDefect("run identity: evaluation time mismatch")
    if body["selected_lineages"] != readiness["selected_lineages"]:
        raise ProtocolDefect("run identity: lineages mismatch")
    require_hex(run_identity, HEX64_RE, "run_identity")
    if run_identity != canonical_sha256(body):
        raise ProtocolDefect("run identity: digest mismatch")


SIX_TABLES = (
    "public.forecasts",
    "public.forecast_outcomes",
    "public.atom_v9_v4_forecasts",
    "public.atom_v9_v4_outcomes",
    "public.volatility_forecasts",
    "public.volatility_forecast_outcomes",
)
PROOF_FUNCTIONS = (
    "atom_v9_internal.read_forecast_commit_proof(text)",
    "atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])",
)
PROOF_DEFINITION_KEYS = (
    "oid", "owner", "language", "prokind", "prosecdef", "proleakproof",
    "proisstrict", "provolatile", "proparallel", "prorows", "proconfig",
    "definition_sha256",
)
EXPECTED_PROOF_DEFINITIONS = {
    PROOF_FUNCTIONS[0]: {
        "oid": 42475,
        "owner": "atom_v9_proof_owner",
        "language": "sql",
        "prokind": "f",
        "prosecdef": True,
        "proleakproof": False,
        "proisstrict": False,
        "provolatile": "s",
        "proparallel": "u",
        "prorows": 1000,
        "proconfig": ["search_path=pg_catalog"],
        "definition_sha256": "dd5c1d60982ab8c943482c807e1f9f9782986564fdc7430d43eef13d0e0ed877",
    },
    PROOF_FUNCTIONS[1]: {
        "oid": 49997,
        "owner": "atom_v9_proof_owner",
        "language": "sql",
        "prokind": "f",
        "prosecdef": True,
        "proleakproof": False,
        "proisstrict": False,
        "provolatile": "s",
        "proparallel": "u",
        "prorows": 65536,
        "proconfig": ["search_path=pg_catalog"],
        "definition_sha256": "076891760da2d132feccff61a2557175eff6926d7f2ecf54a5ba15f7298a7bfb",
    },
}


def _validate_bool_table_map(value: Any, label: str, expected: bool | None) -> None:
    obj = exact_keys(value, SIX_TABLES, label)
    for key in SIX_TABLES:
        observed = require_bool(obj[key], f"{label}.{key}")
        if expected is not None and observed is not expected:
            raise ProtocolDefect(f"{label}.{key}: wrong value")


def validate_authority_proof(value: Any) -> None:
    obj = exact_keys(value, AUTHORITY_PROOF_KEYS, "authority_proof")
    fixed: dict[str, Any] = {
        "current_user": READER_ROLE,
        "session_user": READER_ROLE,
        "dsn_login_user": READER_ROLE,
        "dsn_password_present": True,
        "dsn_password_fallbacks_absent": True,
        "dsn_sslmode": "verify-full",
        "dsn_sslrootcert": CA_REPOSITORY_PATH,
        "sslrootcert_sha256": CA_SHA256,
        "dsn_sslcertmode": "disable",
        "dsn_require_auth": "scram-sha-256",
        "dsn_tls_fallbacks_absent": True,
        "tls_active": True,
        "dsn_identity_overrides_absent": True,
        "current_database": "postgres",
        "database_create": False,
        "database_temporary": True,
        "database_temporary_public_only": True,
        "session_temp_schema_created": False,
        "effective_host": DIRECT_HOST,
        "effective_port": 5432,
        "project_binding_verified": True,
        "schema_public_usage": True,
        "schema_public_create": False,
        "non_system_schema_create_privilege_count": 0,
        "schema_atom_v9_internal_usage": True,
        "non_system_security_definer_execute_privilege_count": 0,
        "reader_role_memberships": [],
        "non_system_relation_write_privilege_count": 0,
        "transaction_isolation": "repeatable read",
        "read_only_transaction": True,
        "verification_status": "PASS",
    }
    for key, expected in fixed.items():
        if obj[key] != expected or (type(expected) is bool and type(obj[key]) is not bool):
            raise ProtocolDefect(f"authority_proof.{key}: wrong value")
    require_str(obj["database_owner"], "authority_proof.database_owner", nonempty=True)
    if obj["database_owner"] == READER_ROLE:
        raise ProtocolDefect("authority_proof.database_owner: reader owns database")
    if obj["proof_functions_execute"] != {key: True for key in PROOF_FUNCTIONS}:
        raise ProtocolDefect("authority_proof.proof_functions_execute mismatch")
    defs = exact_keys(obj["proof_function_definitions"], PROOF_FUNCTIONS, "proof_function_definitions")
    for signature in PROOF_FUNCTIONS:
        exact_keys(defs[signature], PROOF_DEFINITION_KEYS, f"proof_function_definitions.{signature}")
        if defs[signature] != EXPECTED_PROOF_DEFINITIONS[signature]:
            raise ProtocolDefect(f"proof_function_definitions.{signature}: mismatch")
    attrs = exact_keys(
        obj["reader_role_attributes"],
        ("rolcanlogin", "rolinherit", "rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls"),
        "reader_role_attributes",
    )
    if attrs != {
        "rolcanlogin": True,
        "rolinherit": False,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolbypassrls": False,
    }:
        raise ProtocolDefect("reader_role_attributes mismatch")
    _validate_bool_table_map(obj["six_tables_select"], "six_tables_select", True)
    _validate_bool_table_map(obj["six_tables_insert"], "six_tables_insert", False)
    _validate_bool_table_map(obj["six_tables_update"], "six_tables_update", False)
    _validate_bool_table_map(obj["six_tables_delete"], "six_tables_delete", False)
    _validate_bool_table_map(obj["six_tables_truncate"], "six_tables_truncate", False)
    _validate_bool_table_map(obj["six_tables_rls_enabled"], "six_tables_rls_enabled", None)
    _validate_bool_table_map(obj["six_tables_permissive_full_read"], "six_tables_permissive_full_read", True)
    _validate_bool_table_map(obj["six_tables_restrictive_select"], "six_tables_restrictive_select", False)


RUNTIME_ARTIFACT_KEYS = (
    "python_executable_sha256", "stdlib_tree_sha256", "dependency_tree_sha256",
    "loaded_native_tree_sha256",
)


def validate_runtime_identity(
    value: Any,
    *,
    expected_dependency_versions: Mapping[str, str],
    expected_libpq_version: int,
) -> None:
    obj = exact_keys(value, RUNTIME_IDENTITY_KEYS, "runtime_identity")
    fixed = {
        "render_service_id": "srv-daa7thgae00c73a2lmn0",
        "render_runtime": "python",
        "python_implementation": "CPython",
        "python_version_source": "PYTHON_VERSION",
        "python_version_env": "3.14.3",
        "python_version": "3.14.3",
        "python_cache_tag": "cpython-314",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "byteorder": "little",
        "libc_name": "glibc",
        "libc_version": "2.36",
        "float_radix": 2,
        "float_mant_dig": 53,
        "float_max_exp": 1024,
        "float_rounds": 1,
    }
    for key, expected in fixed.items():
        if obj[key] != expected or (type(expected) is int and type(obj[key]) is not int):
            raise ProtocolDefect(f"runtime_identity.{key}: mismatch")
    if type(expected_libpq_version) is not int or obj["libpq_version"] != expected_libpq_version or type(obj["libpq_version"]) is not int:
        raise ProtocolDefect("runtime_identity.libpq_version mismatch")
    expected_deps = dict(expected_dependency_versions)
    if obj["dependency_versions"] != expected_deps:
        raise ProtocolDefect("runtime_identity.dependency_versions mismatch")
    for key, item in exact_keys(obj["dependency_versions"], expected_deps.keys(), "dependency_versions").items():
        require_str(key, "dependency name", nonempty=True)
        require_str(item, f"dependency_versions.{key}", nonempty=True)
    components = exact_keys(obj["runtime_artifact_components"], RUNTIME_ARTIFACT_KEYS, "runtime_artifact_components")
    for key in RUNTIME_ARTIFACT_KEYS:
        require_hex(components[key], HEX64_RE, f"runtime_artifact_components.{key}")
    require_hex(obj["runtime_artifact_sha256"], HEX64_RE, "runtime_artifact_sha256")
    if obj["runtime_artifact_sha256"] != canonical_sha256(components):
        raise ProtocolDefect("runtime_artifact_sha256 mismatch")
    dispatch = exact_keys(obj["libm_dispatch"], ("exp", "log"), "libm_dispatch")
    for symbol in ("exp", "log"):
        entry = exact_keys(dispatch[symbol], ("loaded_native_path", "file_offset"), f"libm_dispatch.{symbol}")
        path = require_str(entry["loaded_native_path"], f"libm_dispatch.{symbol}.loaded_native_path", nonempty=True)
        if not os.path.isabs(path) or os.path.realpath(path) != path:
            raise ProtocolDefect(f"libm_dispatch.{symbol}: non-normalized path")
        require_int(entry["file_offset"], f"libm_dispatch.{symbol}.file_offset", minimum=0)
    require_hex(obj["libm_dispatch_sha256"], HEX64_RE, "libm_dispatch_sha256")
    if obj["libm_dispatch_sha256"] != canonical_sha256(dispatch):
        raise ProtocolDefect("libm_dispatch_sha256 mismatch")
    require_hex(obj["runtime_manifest_sha256"], HEX64_RE, "runtime_manifest_sha256")
    runtime_body = {key: json_clone(obj[key]) for key in RUNTIME_IDENTITY_KEYS if key != "runtime_manifest_sha256"}
    if obj["runtime_manifest_sha256"] != canonical_sha256(runtime_body):
        raise ProtocolDefect("runtime_manifest_sha256 mismatch")


@dataclass(frozen=True)
class SealBundle:
    canonical_bytes: bytes
    manifest_id: str
    cell_orders: tuple[int, ...]
    seal_record_sha256: str

    def record(self) -> dict[str, Any]:
        return json.loads(self.canonical_bytes[:-1].decode("utf-8"))


def build_seal(
    *,
    initial_authority_proof: Mapping[str, Any],
    readiness_identity_body: Mapping[str, Any],
    readiness: Mapping[str, Any],
    run_identity_body: Mapping[str, Any],
    run_identity: str,
) -> SealBundle:
    validate_authority_proof(dict(initial_authority_proof))
    validate_readiness(dict(readiness_identity_body), dict(readiness))
    validate_run_identity(
        dict(run_identity_body), run_identity,
        dict(readiness_identity_body), dict(readiness),
    )
    body = {
        "seal_schema_version": "ATOM-V1B-MANIFEST-SEAL-1",
        "initial_authority_proof": json_clone(initial_authority_proof),
        "readiness_identity_body": json_clone(readiness_identity_body),
        "readiness": json_clone(readiness),
        "run_identity_body": json_clone(run_identity_body),
        "run_identity": run_identity,
    }
    exact_keys(body, SEAL_BODY_KEYS, "seal_record_body")
    record = {**body, "seal_record_sha256": canonical_sha256(body)}
    return validate_seal(record, expected_manifest_id=readiness_identity_body["manifest_id"])


def validate_seal(
    record_value: Any,
    *,
    expected_manifest_id: str | None = None,
    expected_canonical_bytes: bytes | None = None,
) -> SealBundle:
    record = exact_keys(record_value, SEAL_RECORD_KEYS, "seal_record")
    if record["seal_schema_version"] != "ATOM-V1B-MANIFEST-SEAL-1":
        raise ProtocolDefect("seal_record: wrong schema version")
    validate_authority_proof(record["initial_authority_proof"])
    validate_readiness(record["readiness_identity_body"], record["readiness"])
    validate_run_identity(
        record["run_identity_body"], record["run_identity"],
        record["readiness_identity_body"], record["readiness"],
    )
    digest = require_hex(record["seal_record_sha256"], HEX64_RE, "seal_record_sha256")
    body = {key: json_clone(record[key]) for key in SEAL_BODY_KEYS}
    if digest != canonical_sha256(body):
        raise ProtocolDefect("seal_record_sha256 mismatch")
    manifest_id = record["readiness_identity_body"]["manifest_id"]
    if expected_manifest_id is not None and manifest_id != expected_manifest_id:
        raise ProtocolDefect("seal_record: manifest mismatch")
    raw = canonical_line(record)
    if expected_canonical_bytes is not None and raw != expected_canonical_bytes:
        raise ProtocolDefect("seal_record: noncanonical/original-byte mismatch")
    return SealBundle(
        canonical_bytes=raw,
        manifest_id=manifest_id,
        cell_orders=MANIFEST_REGISTRY[manifest_id][1],
        seal_record_sha256=digest,
    )


INT_CELL_KEYS = tuple(
    key for key in CELL_KEYS
    if key.startswith("n_") or key.endswith("_draws") or key == "cell_order"
)
NULLABLE_SCALAR_METRIC_KEYS = (
    "mae_bps", "rank_corr", "level_ratio", "coverage_90", "mz_a", "mz_b",
    "mz_r2", "persist_rank_corr", "enc_b", "unconditional_rank_corr",
    "seasonal_rank_corr", "qlike_candidate", "qlike_unconditional",
    "qlike_seasonal", "d_unconditional", "d_seasonal",
)
NULLABLE_INTERVAL_KEYS = (
    "enc_b_ci_0999", "enc_b_ci_095", "d_unconditional_ci_0999",
    "d_unconditional_ci_095", "d_seasonal_ci_0999", "d_seasonal_ci_095",
)

_DESCRIPTIVE_CELL_KEYS = (
    "mae_bps", "rank_corr", "level_ratio", "coverage_90", "mz_a", "mz_b",
    "mz_r2", "persist_rank_corr", "unconditional_rank_corr",
    "seasonal_rank_corr",
)
_INFERENCE_CELL_KEYS = (
    "enc_b", "enc_b_ci_0999", "enc_b_ci_095", "qlike_candidate",
    "qlike_unconditional", "qlike_seasonal", "d_unconditional",
    "d_unconditional_ci_0999", "d_unconditional_ci_095", "d_seasonal",
    "d_seasonal_ci_0999", "d_seasonal_ci_095",
)
_BOOTSTRAP_TRIPLET_KEYS = (
    (
        "bootstrap_attempted_draws",
        "bootstrap_valid_draws",
        "bootstrap_invalid_draws",
    ),
    (
        "unconditional_bootstrap_attempted_draws",
        "unconditional_bootstrap_valid_draws",
        "unconditional_bootstrap_invalid_draws",
    ),
    (
        "seasonal_bootstrap_attempted_draws",
        "seasonal_bootstrap_valid_draws",
        "seasonal_bootstrap_invalid_draws",
    ),
)
_INSUFFICIENT_REASON_CHECKS = (
    ("n_regression_windows", MIN_WINDOWS, "INSUFFICIENT_REGRESSION_WINDOWS"),
    ("n_regression_sessions", MIN_SESSIONS, "INSUFFICIENT_REGRESSION_SESSIONS"),
    (
        "n_unconditional_gate_windows",
        MIN_WINDOWS,
        "INSUFFICIENT_UNCONDITIONAL_GATE_WINDOWS",
    ),
    (
        "n_unconditional_gate_sessions",
        MIN_SESSIONS,
        "INSUFFICIENT_UNCONDITIONAL_GATE_SESSIONS",
    ),
    (
        "n_seasonal_gate_windows",
        MIN_WINDOWS,
        "INSUFFICIENT_SEASONAL_GATE_WINDOWS",
    ),
    (
        "n_seasonal_gate_sessions",
        MIN_SESSIONS,
        "INSUFFICIENT_SEASONAL_GATE_SESSIONS",
    ),
)
_RULE_ONE_INVALID_REASONS = frozenset(
    {"CELL_PROTOCOL_DEFECT", "PREINSPECTED_CONFIRMATORY_STATISTIC"}
)
_SINGLETON_INVALID_REASONS = frozenset(
    {
        "FULL_SAMPLE_OLS_RANK_DEFICIENT",
        "FULL_SAMPLE_OLS_NONFINITE",
        "QLIKE_ARITHMETIC_NONFINITE",
        "ENC_B_BOOTSTRAP_EXHAUSTED",
        "UNCONDITIONAL_GATE_BOOTSTRAP_EXHAUSTED",
        "SEASONAL_GATE_BOOTSTRAP_EXHAUSTED",
    }
)


def _finite_number_or_none(value: Any, label: str) -> None:
    if value is None:
        return
    if type(value) not in {int, float}:
        raise ProtocolDefect(f"{label}: finite number or null required")
    number = float(value)
    if not (-float("inf") < number < float("inf")):
        raise ProtocolDefect(f"{label}: nonfinite")


def _require_analytic_nulls(
    obj: Mapping[str, Any], keys: Sequence[str], label: str
) -> None:
    if any(obj[key] is not None for key in keys):
        raise ProtocolDefect(f"{label}: analytic field must be null")


def _require_analytic_values(
    obj: Mapping[str, Any], keys: Sequence[str], label: str
) -> None:
    if any(obj[key] is None for key in keys):
        raise ProtocolDefect(f"{label}: analytic field must be finite")


def _validate_interval(
    interval: Any, label: str
) -> tuple[float, float] | None:
    if interval is None:
        return None
    if type(interval) is not list or len(interval) != 2:
        raise ProtocolDefect(f"{label}: two-number interval required")
    _finite_number_or_none(interval[0], f"{label}[0]")
    _finite_number_or_none(interval[1], f"{label}[1]")
    if interval[0] is None or interval[1] is None:
        raise ProtocolDefect(f"{label}: null endpoint")
    lower = float(interval[0])
    upper = float(interval[1])
    if lower > upper:
        raise ProtocolDefect(f"{label}: inverted interval")
    return lower, upper


def _validate_interval_nesting(
    obj: Mapping[str, Any], outer_key: str, inner_key: str
) -> None:
    outer = _validate_interval(obj[outer_key], f"cell.{outer_key}")
    inner = _validate_interval(obj[inner_key], f"cell.{inner_key}")
    if (outer is None) != (inner is None):
        raise ProtocolDefect(f"cell.{outer_key}/{inner_key}: incomplete interval pair")
    if outer is not None and inner is not None:
        if not (outer[0] <= inner[0] <= inner[1] <= outer[1]):
            raise ProtocolDefect(
                f"cell.{outer_key}/{inner_key}: 0.999 interval must contain 0.95"
            )


def _validate_bootstrap_triplet(
    obj: Mapping[str, Any], keys: tuple[str, str, str]
) -> tuple[int, int, int]:
    attempted, valid, invalid = (obj[key] for key in keys)
    label = keys[0].removesuffix("_attempted_draws") or "enc_b"
    if attempted != valid + invalid:
        raise ProtocolDefect(f"cell.{label}: bootstrap counters do not reconcile")
    if attempted > BOOTSTRAP_MAX_ATTEMPTS:
        raise ProtocolDefect(f"cell.{label}: bootstrap attempt cap exceeded")
    if valid > BOOTSTRAP_RESAMPLES:
        raise ProtocolDefect(f"cell.{label}: bootstrap valid-draw target exceeded")
    return attempted, valid, invalid


def _require_zero_bootstrap(
    triplet: tuple[int, int, int], label: str
) -> None:
    if triplet != (0, 0, 0):
        raise ProtocolDefect(f"cell.{label}: bootstrap triplet must be zero")


def _require_completed_bootstrap(
    triplet: tuple[int, int, int], label: str
) -> None:
    attempted, valid, invalid = triplet
    if (
        valid != BOOTSTRAP_RESAMPLES
        or attempted < BOOTSTRAP_RESAMPLES
        or attempted > BOOTSTRAP_MAX_ATTEMPTS
        or invalid != attempted - valid
    ):
        raise ProtocolDefect(f"cell.{label}: bootstrap completion mismatch")


def _require_exhausted_bootstrap(
    triplet: tuple[int, int, int], label: str
) -> None:
    attempted, valid, invalid = triplet
    if (
        attempted != BOOTSTRAP_MAX_ATTEMPTS
        or not 0 <= valid < BOOTSTRAP_RESAMPLES
        or invalid != attempted - valid
    ):
        raise ProtocolDefect(f"cell.{label}: bootstrap exhaustion mismatch")


def _validate_population_count_semantics(
    obj: Mapping[str, Any], *, forecaster: str, sentinel: bool
) -> None:
    accounting_buckets = (
        "n_unselected_lineage_rows",
        "n_inadmissible",
        "n_non_rth",
        "n_overlap_excluded",
        "n_null_or_nonfinite_excluded",
        "n_nonpositive_prediction_excluded",
        "n_kappa_unavailable",
        "n_windows",
    )
    if obj["n_input"] != sum(obj[key] for key in accounting_buckets):
        raise ProtocolDefect("cell: §6.4 input accounting does not reconcile")
    if forecaster == "FAMILY-VOL" and obj["n_kappa_unavailable"] != 0:
        raise ProtocolDefect("cell: FAMILY kappa-unavailable count must be zero")
    if obj["n_sessions"] != len(obj["session_dates"]):
        raise ProtocolDefect("cell.n_sessions mismatch")
    if (obj["n_windows"] == 0) != (obj["n_sessions"] == 0):
        raise ProtocolDefect("cell: window/session emptiness mismatch")
    if obj["n_sessions"] > obj["n_windows"]:
        raise ProtocolDefect("cell: more sessions than windows")
    if obj["n_windows"] != (
        obj["n_persist20_unavailable"] + obj["n_regression_windows"]
    ):
        raise ProtocolDefect("cell: §8.1 persistence accounting does not reconcile")
    if obj["n_persist20_unavailable"] < min(20, obj["n_windows"]):
        raise ProtocolDefect("cell: first 20 persistence rows not unavailable")
    if (obj["n_regression_windows"] == 0) != (
        obj["n_regression_sessions"] == 0
    ):
        raise ProtocolDefect("cell: regression window/session emptiness mismatch")
    if obj["n_regression_sessions"] > min(
        obj["n_regression_windows"], obj["n_sessions"]
    ):
        raise ProtocolDefect("cell: regression session count impossible")
    if obj["n_regression_windows"] != (
        obj["n_unconditional_unavailable"]
        + obj["n_unconditional_gate_windows"]
    ):
        raise ProtocolDefect("cell: §10.3 unconditional accounting does not reconcile")
    if obj["n_regression_windows"] == 0:
        if obj["n_unconditional_unavailable"] != 0:
            raise ProtocolDefect("cell: unconditional-unavailable count without rows")
    elif obj["n_unconditional_unavailable"] < 1:
        raise ProtocolDefect("cell: first regression benchmark must be unavailable")
    if (
        obj["n_unconditional_gate_windows"]
        != obj["n_seasonal_gate_windows"]
        or obj["n_unconditional_gate_sessions"]
        != obj["n_seasonal_gate_sessions"]
    ):
        raise ProtocolDefect("cell: §10.3 gate populations differ")
    for benchmark in ("unconditional", "seasonal"):
        windows = obj[f"n_{benchmark}_gate_windows"]
        sessions = obj[f"n_{benchmark}_gate_sessions"]
        if (windows == 0) != (sessions == 0):
            raise ProtocolDefect(f"cell: {benchmark} gate emptiness mismatch")
        if sessions > min(windows, obj["n_regression_sessions"]):
            raise ProtocolDefect(f"cell: {benchmark} gate session count impossible")
    if sentinel:
        sentinel_zero_keys = (
            "n_unselected_lineage_rows",
            "n_non_rth",
            "n_overlap_excluded",
            "n_null_or_nonfinite_excluded",
            "n_nonpositive_prediction_excluded",
            "n_kappa_unavailable",
            "n_windows",
            "n_sessions",
            "n_persist20_unavailable",
            "n_regression_windows",
            "n_regression_sessions",
            "n_unconditional_unavailable",
            "n_unconditional_gate_windows",
            "n_unconditional_gate_sessions",
            "n_seasonal_gate_windows",
            "n_seasonal_gate_sessions",
        )
        if any(obj[key] != 0 for key in sentinel_zero_keys):
            raise ProtocolDefect("cell: V9 sentinel population must be empty")
        if obj["n_inadmissible"] != obj["n_input"]:
            raise ProtocolDefect("cell: V9 sentinel inputs must all be inadmissible")


def _validate_descriptive_semantics(obj: Mapping[str, Any]) -> None:
    if obj["n_windows"] == 0:
        _require_analytic_nulls(obj, _DESCRIPTIVE_CELL_KEYS, "empty cell")
        return
    _require_analytic_values(obj, ("mae_bps", "coverage_90"), "nonempty cell")
    if float(obj["mae_bps"]) < 0:
        raise ProtocolDefect("cell.mae_bps: negative")
    coverage = float(obj["coverage_90"])
    if not 0.0 <= coverage <= 1.0:
        raise ProtocolDefect("cell.coverage_90: outside [0,1]")
    if obj["level_ratio"] is not None and float(obj["level_ratio"]) <= 0:
        raise ProtocolDefect("cell.level_ratio: must be positive or null")
    if obj["n_windows"] < 2:
        _require_analytic_nulls(
            obj, ("rank_corr", "mz_a", "mz_b", "mz_r2"), "single-window cell"
        )
    if (obj["mz_a"] is None) != (obj["mz_b"] is None):
        raise ProtocolDefect("cell: Mincer-Zarnowitz coefficient pair incomplete")
    if obj["mz_a"] is None and obj["mz_r2"] is not None:
        raise ProtocolDefect("cell: Mincer-Zarnowitz R2 without fitted coefficients")
    if obj["n_regression_windows"] < 2 and obj["persist_rank_corr"] is not None:
        raise ProtocolDefect("cell.persist_rank_corr: insufficient population")
    if (
        obj["n_unconditional_gate_windows"] < 2
        and obj["unconditional_rank_corr"] is not None
    ):
        raise ProtocolDefect("cell.unconditional_rank_corr: insufficient population")
    if (
        obj["n_seasonal_gate_windows"] < 2
        and obj["seasonal_rank_corr"] is not None
    ):
        raise ProtocolDefect("cell.seasonal_rank_corr: insufficient population")


def _validate_classification_semantics(
    obj: Mapping[str, Any], triplets: Sequence[tuple[int, int, int]], *, sentinel: bool
) -> None:
    classification = obj["classification"]
    reasons = obj["reason_codes"]
    minima_reasons = sorted(
        reason
        for key, minimum, reason in _INSUFFICIENT_REASON_CHECKS
        if obj[key] < minimum
    )
    minima_pass = not minima_reasons
    expected_unconditional_gate = (
        "UNAVAILABLE" if obj["n_unconditional_gate_windows"] == 0 else "NOT_RUN"
    )
    expected_seasonal_gate = (
        "UNAVAILABLE" if obj["n_seasonal_gate_windows"] == 0 else "NOT_RUN"
    )

    if sentinel and classification != "INSUFFICIENT":
        raise ProtocolDefect("cell: V9 sentinel must be INSUFFICIENT")

    if classification == "INSUFFICIENT":
        if minima_pass or reasons != minima_reasons:
            raise ProtocolDefect("cell: INSUFFICIENT reason/minimum mismatch")
        _validate_descriptive_semantics(obj)
        _require_analytic_nulls(obj, _INFERENCE_CELL_KEYS, "INSUFFICIENT cell")
        for label, triplet in zip(
            ("enc_b", "unconditional", "seasonal"), triplets, strict=True
        ):
            _require_zero_bootstrap(triplet, label)
        if (
            obj["gate_unconditional"] != expected_unconditional_gate
            or obj["gate_seasonal"] != expected_seasonal_gate
        ):
            raise ProtocolDefect("cell: INSUFFICIENT gate status mismatch")
        return

    if classification == "INVALID":
        reason_set = frozenset(reasons)
        if not reason_set:
            raise ProtocolDefect("cell: INVALID reason required")
        if not (
            reason_set <= _RULE_ONE_INVALID_REASONS
            or (len(reason_set) == 1 and next(iter(reason_set)) in _SINGLETON_INVALID_REASONS)
        ):
            raise ProtocolDefect("cell: INVALID reason set violates precedence")
        if reason_set.isdisjoint(_RULE_ONE_INVALID_REASONS) and not minima_pass:
            raise ProtocolDefect("cell: later INVALID rule cannot bypass insufficiency")
        _require_analytic_nulls(obj, _ANALYTIC_FIELDS, "INVALID cell")
        if (
            obj["gate_unconditional"] != expected_unconditional_gate
            or obj["gate_seasonal"] != expected_seasonal_gate
        ):
            raise ProtocolDefect("cell: INVALID gate status mismatch")
        exhaustion = next(
            (
                reason
                for reason in _SINGLETON_INVALID_REASONS
                if reason.endswith("BOOTSTRAP_EXHAUSTED") and reason in reason_set
            ),
            None,
        )
        if exhaustion is None:
            for label, triplet in zip(
                ("enc_b", "unconditional", "seasonal"), triplets, strict=True
            ):
                _require_zero_bootstrap(triplet, label)
        elif exhaustion == "ENC_B_BOOTSTRAP_EXHAUSTED":
            _require_exhausted_bootstrap(triplets[0], "enc_b")
            _require_zero_bootstrap(triplets[1], "unconditional")
            _require_zero_bootstrap(triplets[2], "seasonal")
        elif exhaustion == "UNCONDITIONAL_GATE_BOOTSTRAP_EXHAUSTED":
            _require_completed_bootstrap(triplets[0], "enc_b")
            _require_exhausted_bootstrap(triplets[1], "unconditional")
            _require_zero_bootstrap(triplets[2], "seasonal")
        else:
            _require_completed_bootstrap(triplets[0], "enc_b")
            _require_completed_bootstrap(triplets[1], "unconditional")
            _require_exhausted_bootstrap(triplets[2], "seasonal")
        return

    if not minima_pass:
        raise ProtocolDefect(f"cell: {classification} cannot fail a population minimum")
    _validate_descriptive_semantics(obj)
    _require_analytic_values(
        obj,
        (
            "enc_b", "enc_b_ci_0999", "enc_b_ci_095", "qlike_candidate",
            "qlike_unconditional", "qlike_seasonal", "d_unconditional",
            "d_unconditional_ci_0999", "d_unconditional_ci_095",
            "d_seasonal", "d_seasonal_ci_0999", "d_seasonal_ci_095",
        ),
        f"{classification} cell",
    )
    for label, triplet in zip(
        ("enc_b", "unconditional", "seasonal"), triplets, strict=True
    ):
        _require_completed_bootstrap(triplet, label)
    enc_interval = obj["enc_b_ci_0999"]
    unconditional_interval = obj["d_unconditional_ci_0999"]
    seasonal_interval = obj["d_seasonal_ci_0999"]
    expected_unconditional_gate = (
        "PASS" if float(unconditional_interval[0]) > 0 else "FAIL"
    )
    expected_seasonal_gate = "PASS" if float(seasonal_interval[0]) > 0 else "FAIL"
    if (
        obj["gate_unconditional"] != expected_unconditional_gate
        or obj["gate_seasonal"] != expected_seasonal_gate
    ):
        raise ProtocolDefect("cell: completed gate status/interval mismatch")
    expected_noise_reasons = sorted(
        reason
        for condition, reason in (
            (float(enc_interval[0]) <= 0, "ENC_B_NOT_POSITIVE"),
            (expected_unconditional_gate == "FAIL", "FAILED_UNCONDITIONAL_GATE"),
            (expected_seasonal_gate == "FAIL", "FAILED_SEASONAL_GATE"),
        )
        if condition
    )
    if classification == "INFORMATIVE":
        if expected_noise_reasons or reasons != []:
            raise ProtocolDefect("cell: INFORMATIVE gate/reason mismatch")
    elif classification == "NOISE":
        if not expected_noise_reasons or reasons != expected_noise_reasons:
            raise ProtocolDefect("cell: NOISE gate/reason mismatch")
    else:
        raise ProtocolDefect("cell.classification domain")


def validate_cell(value: Any, expected_cell: Mapping[str, Any]) -> None:
    obj = exact_keys(value, CELL_KEYS, "cell")
    for key in MANIFEST_CELL_KEYS:
        if obj[key] != expected_cell[key]:
            raise ProtocolDefect(f"cell.{key}: manifest mismatch")
    _validate_lineage(
        obj["lineage_identity"],
        forecaster=expected_cell["forecaster"],
        horizon=expected_cell["horizon"],
        label="cell.lineage_identity",
    )
    if type(obj["session_dates"]) is not list:
        raise ProtocolDefect("cell.session_dates: array required")
    sessions = [require_date(item, "cell.session_dates[]") for item in obj["session_dates"]]
    if sessions != sorted(set(sessions)):
        raise ProtocolDefect("cell.session_dates: must be ascending unique")
    for key in ("evidence_min_cutoff_at", "evidence_max_cutoff_at"):
        if obj[key] is not None:
            require_utc_micro(obj[key], f"cell.{key}")
    for key in INT_CELL_KEYS:
        require_int(obj[key], f"cell.{key}", minimum=0)
    if obj["n_sessions"] != len(sessions):
        raise ProtocolDefect("cell.n_sessions mismatch")
    if obj["n_windows"] == 0:
        if sessions or obj["evidence_min_cutoff_at"] is not None or obj["evidence_max_cutoff_at"] is not None:
            raise ProtocolDefect("empty cell evidence span mismatch")
    else:
        if not sessions or obj["evidence_min_cutoff_at"] is None or obj["evidence_max_cutoff_at"] is None:
            raise ProtocolDefect("nonempty cell evidence span missing")
        if obj["evidence_min_cutoff_at"] > obj["evidence_max_cutoff_at"]:
            raise ProtocolDefect("cell evidence span inverted")
    for key in NULLABLE_SCALAR_METRIC_KEYS:
        _finite_number_or_none(obj[key], f"cell.{key}")
    _validate_interval_nesting(obj, "enc_b_ci_0999", "enc_b_ci_095")
    _validate_interval_nesting(
        obj, "d_unconditional_ci_0999", "d_unconditional_ci_095"
    )
    _validate_interval_nesting(obj, "d_seasonal_ci_0999", "d_seasonal_ci_095")
    if obj["gate_unconditional"] not in {"PASS", "FAIL", "UNAVAILABLE", "NOT_RUN"}:
        raise ProtocolDefect("cell.gate_unconditional domain")
    if obj["gate_seasonal"] not in {"PASS", "FAIL", "UNAVAILABLE", "NOT_RUN"}:
        raise ProtocolDefect("cell.gate_seasonal domain")
    if obj["classification"] not in {"INFORMATIVE", "NOISE", "INSUFFICIENT", "INVALID"}:
        raise ProtocolDefect("cell.classification domain")
    if type(obj["reason_codes"]) is not list or any(type(item) is not str for item in obj["reason_codes"]):
        raise ProtocolDefect("cell.reason_codes domain")
    if obj["reason_codes"] != sorted(set(obj["reason_codes"])):
        raise ProtocolDefect("cell.reason_codes not sorted unique")
    sentinel = (
        expected_cell["forecaster"] == "V9-VOL"
        and obj["lineage_identity"]
        == v9_sentinel_lineage(str(expected_cell["horizon"]))
    )
    _validate_population_count_semantics(
        obj, forecaster=str(expected_cell["forecaster"]), sentinel=sentinel
    )
    triplets = tuple(
        _validate_bootstrap_triplet(obj, keys) for keys in _BOOTSTRAP_TRIPLET_KEYS
    )
    _validate_classification_semantics(obj, triplets, sentinel=sentinel)


def validate_manifest_cells_against_readiness(cells: Any, readiness: Mapping[str, Any]) -> None:
    if type(cells) is not list:
        raise ProtocolDefect("cells: array required")
    manifest_id = next(
        (mid for mid in MANIFEST_REGISTRY if manifest_public_cells(mid) == [
            {key: wrapper[key] for key in MANIFEST_CELL_KEYS}
            for wrapper in readiness["selected_lineages"]
        ]),
        None,
    )
    if manifest_id is None:
        raise ProtocolDefect("cells: cannot recover fixed manifest")
    expected = manifest_public_cells(manifest_id)
    if len(cells) != len(expected):
        raise ProtocolDefect("cells: wrong manifest length")
    readiness_counts = {item["cell_order"]: item for item in readiness["counts"]}
    readiness_lineages = {item["cell_order"]: item["lineage_identity"] for item in readiness["selected_lineages"]}
    six = (
        "n_regression_windows", "n_regression_sessions",
        "n_unconditional_gate_windows", "n_unconditional_gate_sessions",
        "n_seasonal_gate_windows", "n_seasonal_gate_sessions",
    )
    for item, expected_cell in zip(cells, expected, strict=True):
        validate_cell(item, expected_cell)
        order = expected_cell["cell_order"]
        if item["lineage_identity"] != readiness_lineages[order]:
            raise ProtocolDefect("cell lineage/readiness mismatch")
        for key in six:
            if item[key] != readiness_counts[order][key]:
                raise ProtocolDefect(f"cell/readiness count mismatch: {key}")


@dataclass(frozen=True)
class ReceiptBytes:
    canonical_bytes: bytes
    filename: str
    receipt_sha256: str
    schema_version: str
    terminal: bool

    def object(self) -> dict[str, Any]:
        return json.loads(self.canonical_bytes[:-1].decode("utf-8"))


def _finish_receipt(body: Mapping[str, Any], filename: str, *, terminal: bool) -> ReceiptBytes:
    if "receipt_sha256" in body:
        raise ProtocolDefect("receipt body already contains self-hash")
    digest = canonical_sha256(body)
    obj = {**json_clone(body), "receipt_sha256": digest}
    return ReceiptBytes(
        canonical_bytes=canonical_line(obj),
        filename=filename.format(receipt_sha256=digest),
        receipt_sha256=digest,
        schema_version=obj["schema_version"],
        terminal=terminal,
    )


def _derive_overall(cells: Sequence[Mapping[str, Any]], run_protocol_defect: bool) -> tuple[str, list[str]]:
    invalid = any(cell["classification"] == "INVALID" for cell in cells)
    if invalid or run_protocol_defect:
        reasons = []
        if invalid:
            reasons.append("INVALID_CELL_PRESENT")
        if run_protocol_defect:
            reasons.append("RUN_PROTOCOL_DEFECT")
        return "INVALID", sorted(reasons)
    if any(cell["classification"] == "INFORMATIVE" for cell in cells):
        return "PASS", []
    return "FAIL", ["NO_INFORMATIVE_CELL"]


def build_evaluated_receipt(
    *,
    seal: SealBundle,
    generated_at_utc: str,
    runtime_identity: Mapping[str, Any],
    final_authority_proof: Mapping[str, Any],
    cells: list[dict[str, Any]],
    expected_dependency_versions: Mapping[str, str],
    expected_libpq_version: int,
    run_protocol_defect: bool = False,
) -> ReceiptBytes:
    require_utc_micro(generated_at_utc, "generated_at_utc")
    record = seal.record()
    validate_seal(record, expected_canonical_bytes=seal.canonical_bytes)
    validate_authority_proof(dict(final_authority_proof))
    if final_authority_proof != record["initial_authority_proof"]:
        raise ProtocolDefect("final authority proof differs from initial proof")
    validate_runtime_identity(
        dict(runtime_identity),
        expected_dependency_versions=expected_dependency_versions,
        expected_libpq_version=expected_libpq_version,
    )
    rb = record["readiness_identity_body"]
    readiness = record["readiness"]
    if runtime_identity["runtime_manifest_sha256"] != rb["runtime_manifest_sha256"]:
        raise ProtocolDefect("runtime identity differs from sealed digest")
    validate_manifest_cells_against_readiness(cells, readiness)
    overall_status, overall_reasons = _derive_overall(cells, run_protocol_defect)
    body = {
        "schema_version": "ATOM-V1B-MANIFEST-RECEIPT-1",
        "decision_id": DECISION_ID,
        "job_id": JOB_ID,
        "contract_path": CONTRACT_PATH,
        "code_version": CODE_VERSION,
        "verified_main_sha": rb["verified_main_sha"],
        "v1a_merge_sha": rb["v1a_merge_sha"],
        "run_identity": record["run_identity"],
        "evaluation_session": readiness["boundary_session"],
        "evaluation_as_of_at": readiness["boundary_as_of_at"],
        "generated_at_utc": generated_at_utc,
        "reader_identity": READER_ROLE,
        "database_identity": json_clone(rb["database_identity"]),
        "runtime_identity": json_clone(dict(runtime_identity)),
        "authority_proof": json_clone(dict(final_authority_proof)),
        "bootstrap": json_clone(BOOTSTRAP),
        "cells": json_clone(cells),
        "overall_status": overall_status,
        "overall_reason_codes": overall_reasons,
        "scouting_disclosure": list(SCOUTING_DISCLOSURE),
        "read_only": True,
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        "amendment_id": AMENDMENT_ID,
        "amendment_path": AMENDMENT_PATH,
        "amendment_merge_sha": rb["amendment_merge_sha"],
        "tls_amendment_id": TLS_AMENDMENT_ID,
        "tls_amendment_path": TLS_AMENDMENT_PATH,
        "tls_amendment_merge_sha": rb["tls_amendment_merge_sha"],
        "evidence_artifacts": evidence_artifacts(),
        "manifest_id": seal.manifest_id,
        "manifest_registry_order": manifest_sequence(seal.manifest_id),
        "manifest_cells": manifest_public_cells(seal.manifest_id),
        "readiness": json_clone(readiness),
        "seal_record_sha256": seal.seal_record_sha256,
        "result_scope": "MANIFEST_ONLY",
    }
    exact_keys({**body, "receipt_sha256": "0" * 64}, EVALUATED_KEYS, "evaluated receipt")
    filename = (
        "docs/v-1b-volatility-scorecard-receipt-"
        f"{seal.manifest_id}-{readiness['boundary_session']}-{record['run_identity']}-"
        "{receipt_sha256}.json"
    )
    result = _finish_receipt(body, filename, terminal=True)
    validate_receipt(
        result.canonical_bytes,
        result.filename,
        seal=seal,
        expected_dependency_versions=expected_dependency_versions,
        expected_libpq_version=expected_libpq_version,
    )
    return result


def _negative_amendment_fields(
    manifest_id: str,
    *,
    unverified_merge_identities: frozenset[str],
    readiness: Any,
    sealed_run_identity: Any,
    seal_record_sha256: Any,
) -> dict[str, Any]:
    if not unverified_merge_identities <= {"amendment", "tls"}:
        raise ProtocolDefect("unknown unverified merge identity")
    return {
        "amendment_id": AMENDMENT_ID,
        "amendment_path": AMENDMENT_PATH,
        "amendment_merge_sha": None if "amendment" in unverified_merge_identities else AMENDMENT_MERGE_SHA,
        "tls_amendment_id": TLS_AMENDMENT_ID,
        "tls_amendment_path": TLS_AMENDMENT_PATH,
        "tls_amendment_merge_sha": None if "tls" in unverified_merge_identities else TLS_AMENDMENT_MERGE_SHA,
        "evidence_artifacts": evidence_artifacts(),
        "manifest_id": manifest_id,
        "manifest_registry_order": manifest_sequence(manifest_id),
        "manifest_cells": manifest_public_cells(manifest_id),
        "readiness": json_clone(readiness),
        "sealed_run_identity": sealed_run_identity,
        "seal_record_sha256": seal_record_sha256,
        "result_scope": "MANIFEST_ONLY",
    }


def build_blocked_receipt(
    *,
    manifest_id: str,
    generated_at_utc: str,
    observed_main_sha: str | None,
    expected_main_sha: str | None,
    observed_v1a_merge_sha: str | None,
    observed_user: str | None,
    observed_database: str | None,
    observed_effective_host: str | None,
    project_binding_verified: bool | None,
    read_only: bool | None,
    unverified_merge_identities: frozenset[str] = frozenset(),
) -> ReceiptBytes:
    require_utc_micro(generated_at_utc, "generated_at_utc")
    for label, value in (
        ("observed_main_sha", observed_main_sha),
        ("expected_main_sha", expected_main_sha),
        ("observed_v1a_merge_sha", observed_v1a_merge_sha),
    ):
        if value is not None:
            require_hex(value, HEX40_RE, label)
    for label, value in (
        ("observed_user", observed_user),
        ("observed_database", observed_database),
        ("observed_effective_host", observed_effective_host),
    ):
        if value is not None:
            require_str(value, label)
    if project_binding_verified is not None:
        require_bool(project_binding_verified, "project_binding_verified")
    if read_only is not None:
        require_bool(read_only, "read_only")
    body = {
        "schema_version": "ATOM-V1B-MANIFEST-BLOCKED-RECEIPT-1",
        "decision_id": DECISION_ID,
        "job_id": JOB_ID,
        "contract_path": CONTRACT_PATH,
        "generated_at_utc": generated_at_utc,
        "stage": "PRE_EVALUATION_AUTHORITY",
        "reason_codes": ["PRE_EVALUATION_AUTHORITY_FAILED"],
        "observed_main_sha": observed_main_sha,
        "expected_main_sha": expected_main_sha,
        "observed_v1a_merge_sha": observed_v1a_merge_sha,
        "observed_user": observed_user,
        "observed_database": observed_database,
        "observed_effective_host": observed_effective_host,
        "project_binding_verified": project_binding_verified,
        "read_only": read_only,
        **_negative_amendment_fields(
            manifest_id,
            unverified_merge_identities=unverified_merge_identities,
            readiness=None,
            sealed_run_identity=None,
            seal_record_sha256=None,
        ),
    }
    exact_keys({**body, "receipt_sha256": "0" * 64}, BLOCKED_KEYS, "BLOCKED receipt")
    filename = f"docs/v-1b-volatility-scorecard-negative-{manifest_id}-{{receipt_sha256}}.json"
    result = _finish_receipt(body, filename, terminal=False)
    validate_receipt(result.canonical_bytes, result.filename)
    return result


def build_pre_cell_invalid_receipt(
    *,
    manifest_id: str,
    generated_at_utc: str,
    verified_main_sha: str,
    v1a_merge_sha: str | None,
    evaluation_session: str | None,
    evaluation_as_of_at: str | None,
    database_identity: Mapping[str, Any] | None,
    authority_proof: Mapping[str, Any] | None,
    seal: SealBundle | None = None,
    unverified_merge_identities: frozenset[str] = frozenset(),
) -> ReceiptBytes:
    require_utc_micro(generated_at_utc, "generated_at_utc")
    require_hex(verified_main_sha, HEX40_RE, "verified_main_sha")
    if v1a_merge_sha is not None:
        require_hex(v1a_merge_sha, HEX40_RE, "v1a_merge_sha")
    if evaluation_session is not None:
        require_date(evaluation_session, "evaluation_session")
    if evaluation_as_of_at is not None:
        require_utc_micro(evaluation_as_of_at, "evaluation_as_of_at")
    if database_identity is not None:
        validate_database_identity(dict(database_identity))
    if authority_proof is not None:
        validate_authority_proof(dict(authority_proof))
    readiness = sealed_run = seal_digest = None
    if seal is not None:
        if seal.manifest_id != manifest_id:
            raise ProtocolDefect("PRE-CELL INVALID: seal manifest mismatch")
        record = seal.record()
        validate_seal(record, expected_canonical_bytes=seal.canonical_bytes)
        rb = record["readiness_identity_body"]
        if verified_main_sha != rb["verified_main_sha"] or v1a_merge_sha != rb["v1a_merge_sha"]:
            raise ProtocolDefect("PRE-CELL INVALID: sealed revision mismatch")
        if evaluation_session != record["readiness"]["boundary_session"] or evaluation_as_of_at != record["readiness"]["boundary_as_of_at"]:
            raise ProtocolDefect("PRE-CELL INVALID: sealed boundary mismatch")
        if database_identity != rb["database_identity"]:
            raise ProtocolDefect("PRE-CELL INVALID: database identity mismatch")
        if authority_proof != record["initial_authority_proof"]:
            raise ProtocolDefect("PRE-CELL INVALID: initial authority proof required")
        readiness = record["readiness"]
        sealed_run = record["run_identity"]
        seal_digest = record["seal_record_sha256"]
    body = {
        "schema_version": "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1",
        "decision_id": DECISION_ID,
        "job_id": JOB_ID,
        "contract_path": CONTRACT_PATH,
        "verified_main_sha": verified_main_sha,
        "v1a_merge_sha": v1a_merge_sha,
        "evaluation_session": evaluation_session,
        "evaluation_as_of_at": evaluation_as_of_at,
        "generated_at_utc": generated_at_utc,
        "stage": "EVALUATION_STARTED",
        "reason_codes": ["EVALUATION_CONSTRUCTION_FAILED"],
        "reader_identity": READER_ROLE,
        "database_identity": json_clone(database_identity),
        "authority_proof": json_clone(authority_proof),
        "read_only": True,
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        **_negative_amendment_fields(
            manifest_id,
            unverified_merge_identities=unverified_merge_identities,
            readiness=readiness,
            sealed_run_identity=sealed_run,
            seal_record_sha256=seal_digest,
        ),
    }
    exact_keys({**body, "receipt_sha256": "0" * 64}, PRE_CELL_KEYS, "PRE-CELL INVALID receipt")
    filename = f"docs/v-1b-volatility-scorecard-negative-{manifest_id}-{{receipt_sha256}}.json"
    result = _finish_receipt(body, filename, terminal=seal is not None)
    validate_receipt(result.canonical_bytes, result.filename, seal=seal)
    return result


def build_post_eval_authority_invalid_receipt(
    *,
    seal: SealBundle,
    generated_at_utc: str,
    database_identity: Mapping[str, Any],
    unverified_merge_identities: frozenset[str] = frozenset(),
) -> ReceiptBytes:
    require_utc_micro(generated_at_utc, "generated_at_utc")
    validate_database_identity(dict(database_identity))
    record = seal.record()
    validate_seal(record, expected_canonical_bytes=seal.canonical_bytes)
    rb = record["readiness_identity_body"]
    readiness = record["readiness"]
    if database_identity != rb["database_identity"]:
        raise ProtocolDefect("POST-EVALUATION: database identity mismatch")
    body = {
        "schema_version": "ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1",
        "decision_id": DECISION_ID,
        "job_id": JOB_ID,
        "contract_path": CONTRACT_PATH,
        "verified_main_sha": rb["verified_main_sha"],
        "v1a_merge_sha": rb["v1a_merge_sha"],
        "run_identity": record["run_identity"],
        "evaluation_session": readiness["boundary_session"],
        "evaluation_as_of_at": readiness["boundary_as_of_at"],
        "generated_at_utc": generated_at_utc,
        "stage": "POST_EVALUATION_AUTHORITY_RECHECK",
        "reason_codes": ["FINAL_AUTHORITY_RECHECK_FAILED"],
        "reader_identity": READER_ROLE,
        "database_identity": json_clone(database_identity),
        "initial_authority_proof": json_clone(record["initial_authority_proof"]),
        "read_only": True,
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        **_negative_amendment_fields(
            seal.manifest_id,
            unverified_merge_identities=unverified_merge_identities,
            readiness=readiness,
            sealed_run_identity=record["run_identity"],
            seal_record_sha256=record["seal_record_sha256"],
        ),
    }
    exact_keys({**body, "receipt_sha256": "0" * 64}, POST_EVAL_KEYS, "POST-EVALUATION receipt")
    filename = f"docs/v-1b-volatility-scorecard-negative-{seal.manifest_id}-{{receipt_sha256}}.json"
    result = _finish_receipt(body, filename, terminal=True)
    validate_receipt(result.canonical_bytes, result.filename, seal=seal)
    return result


def parse_canonical_line(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw.endswith(b"\n"):
        raise ProtocolDefect(f"{label}: one final LF required")
    try:
        value = json.loads(raw[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolDefect(f"{label}: invalid UTF-8 JSON") from error
    if type(value) is not dict or raw != canonical_line(value):
        raise ProtocolDefect(f"{label}: noncanonical bytes")
    return value


def _validate_receipt_self_hash(obj: Mapping[str, Any]) -> str:
    digest = require_hex(obj.get("receipt_sha256"), HEX64_RE, "receipt_sha256")
    body = {key: json_clone(value) for key, value in obj.items() if key != "receipt_sha256"}
    if digest != canonical_sha256(body):
        raise ProtocolDefect("receipt_sha256 mismatch")
    return digest


def _validate_amended_common(obj: Mapping[str, Any]) -> str:
    if obj["decision_id"] != DECISION_ID or obj["job_id"] != JOB_ID or obj["contract_path"] != CONTRACT_PATH:
        raise ProtocolDefect("receipt fixed identity mismatch")
    if obj["amendment_id"] != AMENDMENT_ID or obj["amendment_path"] != AMENDMENT_PATH:
        raise ProtocolDefect("receipt Amendment 2A identity mismatch")
    if obj["tls_amendment_id"] != TLS_AMENDMENT_ID or obj["tls_amendment_path"] != TLS_AMENDMENT_PATH:
        raise ProtocolDefect("receipt TLS identity mismatch")
    for key, fixed in (
        ("amendment_merge_sha", AMENDMENT_MERGE_SHA),
        ("tls_amendment_merge_sha", TLS_AMENDMENT_MERGE_SHA),
    ):
        value = obj[key]
        if value is not None:
            require_hex(value, HEX40_RE, key)
            if value != fixed:
                raise ProtocolDefect(f"{key}: wrong verified merge")
    if obj["evidence_artifacts"] != evidence_artifacts():
        raise ProtocolDefect("receipt evidence artifacts mismatch")
    manifest_id = require_str(obj["manifest_id"], "manifest_id")
    if obj["manifest_registry_order"] != manifest_sequence(manifest_id):
        raise ProtocolDefect("receipt manifest order mismatch")
    if obj["manifest_cells"] != manifest_public_cells(manifest_id):
        raise ProtocolDefect("receipt manifest cells mismatch")
    if obj["result_scope"] != "MANIFEST_ONLY":
        raise ProtocolDefect("receipt result_scope mismatch")
    return manifest_id


def _require_zero_writes(obj: Mapping[str, Any]) -> None:
    if obj["read_only"] is not True:
        raise ProtocolDefect("receipt read_only must be true")
    for key in ("forecast_writes", "outcome_writes", "evidence_writes"):
        if type(obj[key]) is not int or obj[key] != 0:
            raise ProtocolDefect(f"receipt {key} must be integer zero")


def validate_receipt(
    raw: bytes,
    filename: str,
    *,
    seal: SealBundle | None = None,
    expected_dependency_versions: Mapping[str, str] | None = None,
    expected_libpq_version: int | None = None,
) -> ReceiptBytes:
    obj = parse_canonical_line(raw, "receipt")
    schema = obj.get("schema_version")
    schema_keys = {
        "ATOM-V1B-MANIFEST-RECEIPT-1": EVALUATED_KEYS,
        "ATOM-V1B-MANIFEST-BLOCKED-RECEIPT-1": BLOCKED_KEYS,
        "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1": PRE_CELL_KEYS,
        "ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1": POST_EVAL_KEYS,
    }
    if schema not in schema_keys:
        raise ProtocolDefect("unknown receipt schema")
    exact_keys(obj, schema_keys[schema], "receipt")
    digest = _validate_receipt_self_hash(obj)
    manifest_id = _validate_amended_common(obj)
    require_utc_micro(obj["generated_at_utc"], "generated_at_utc")
    terminal = False

    if schema == "ATOM-V1B-MANIFEST-RECEIPT-1":
        if seal is None:
            raise ProtocolDefect("evaluated receipt requires retained seal cross-check")
        if expected_dependency_versions is None or expected_libpq_version is None:
            raise ProtocolDefect("evaluated receipt requires frozen runtime literals")
        record = seal.record()
        validate_seal(record, expected_manifest_id=manifest_id, expected_canonical_bytes=seal.canonical_bytes)
        rb = record["readiness_identity_body"]
        readiness = record["readiness"]
        fixed = {
            "code_version": CODE_VERSION,
            "verified_main_sha": rb["verified_main_sha"],
            "v1a_merge_sha": rb["v1a_merge_sha"],
            "run_identity": record["run_identity"],
            "evaluation_session": readiness["boundary_session"],
            "evaluation_as_of_at": readiness["boundary_as_of_at"],
            "reader_identity": READER_ROLE,
            "seal_record_sha256": record["seal_record_sha256"],
        }
        for key, value in fixed.items():
            if obj[key] != value:
                raise ProtocolDefect(f"evaluated receipt {key} mismatch")
        if obj["readiness"] != readiness or obj["database_identity"] != rb["database_identity"]:
            raise ProtocolDefect("evaluated receipt seal binding mismatch")
        if obj["bootstrap"] != BOOTSTRAP or obj["scouting_disclosure"] != list(SCOUTING_DISCLOSURE):
            raise ProtocolDefect("evaluated receipt fixed object mismatch")
        validate_runtime_identity(
            obj["runtime_identity"],
            expected_dependency_versions=expected_dependency_versions,
            expected_libpq_version=expected_libpq_version,
        )
        if obj["runtime_identity"]["runtime_manifest_sha256"] != rb["runtime_manifest_sha256"]:
            raise ProtocolDefect("evaluated receipt runtime/seal mismatch")
        validate_authority_proof(obj["authority_proof"])
        if obj["authority_proof"] != record["initial_authority_proof"]:
            raise ProtocolDefect("evaluated receipt final authority mismatch")
        validate_manifest_cells_against_readiness(obj["cells"], readiness)
        if obj["overall_status"] not in {"PASS", "FAIL", "INVALID"}:
            raise ProtocolDefect("evaluated overall_status domain")
        if type(obj["overall_reason_codes"]) is not list or obj["overall_reason_codes"] != sorted(set(obj["overall_reason_codes"])):
            raise ProtocolDefect("evaluated overall reason ordering")
        possible = {
            ("PASS", ()),
            ("FAIL", ("NO_INFORMATIVE_CELL",)),
            ("INVALID", ("INVALID_CELL_PRESENT",)),
            ("INVALID", ("RUN_PROTOCOL_DEFECT",)),
            ("INVALID", ("INVALID_CELL_PRESENT", "RUN_PROTOCOL_DEFECT")),
        }
        if (obj["overall_status"], tuple(obj["overall_reason_codes"])) not in possible:
            raise ProtocolDefect("evaluated overall status/reason mismatch")
        any_invalid = any(cell["classification"] == "INVALID" for cell in obj["cells"])
        any_informative = any(cell["classification"] == "INFORMATIVE" for cell in obj["cells"])
        if ("INVALID_CELL_PRESENT" in obj["overall_reason_codes"]) != any_invalid:
            raise ProtocolDefect("evaluated invalid-cell reason mismatch")
        if obj["overall_status"] == "PASS" and not any_informative:
            raise ProtocolDefect("evaluated PASS lacks informative cell")
        if obj["overall_status"] == "FAIL" and (any_invalid or any_informative):
            raise ProtocolDefect("evaluated FAIL cell mismatch")
        _require_zero_writes(obj)
        expected_filename = (
            "docs/v-1b-volatility-scorecard-receipt-"
            f"{manifest_id}-{obj['evaluation_session']}-{obj['run_identity']}-{digest}.json"
        )
        terminal = True
    else:
        triple = (obj["readiness"], obj["sealed_run_identity"], obj["seal_record_sha256"])
        all_null = all(item is None for item in triple)
        all_nonnull = all(item is not None for item in triple)
        if not (all_null or all_nonnull):
            raise ProtocolDefect("negative receipt seal triple must be all-null/all-nonnull")
        if schema == "ATOM-V1B-MANIFEST-BLOCKED-RECEIPT-1":
            if not all_null or obj["stage"] != "PRE_EVALUATION_AUTHORITY" or obj["reason_codes"] != ["PRE_EVALUATION_AUTHORITY_FAILED"]:
                raise ProtocolDefect("BLOCKED route/schema mismatch")
            for key in ("observed_main_sha", "expected_main_sha", "observed_v1a_merge_sha"):
                if obj[key] is not None:
                    require_hex(obj[key], HEX40_RE, key)
            for key in ("project_binding_verified", "read_only"):
                if obj[key] is not None:
                    require_bool(obj[key], key)
        elif schema == "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1":
            if obj["stage"] != "EVALUATION_STARTED" or obj["reason_codes"] != ["EVALUATION_CONSTRUCTION_FAILED"]:
                raise ProtocolDefect("PRE-CELL route/schema mismatch")
            require_hex(obj["verified_main_sha"], HEX40_RE, "verified_main_sha")
            if obj["v1a_merge_sha"] is not None:
                require_hex(obj["v1a_merge_sha"], HEX40_RE, "v1a_merge_sha")
            if obj["evaluation_session"] is not None:
                require_date(obj["evaluation_session"], "evaluation_session")
            if obj["evaluation_as_of_at"] is not None:
                require_utc_micro(obj["evaluation_as_of_at"], "evaluation_as_of_at")
            if obj["database_identity"] is not None:
                validate_database_identity(obj["database_identity"])
            if obj["authority_proof"] is not None:
                validate_authority_proof(obj["authority_proof"])
            _require_zero_writes(obj)
            terminal = all_nonnull
        else:
            if not all_nonnull or obj["stage"] != "POST_EVALUATION_AUTHORITY_RECHECK" or obj["reason_codes"] != ["FINAL_AUTHORITY_RECHECK_FAILED"]:
                raise ProtocolDefect("POST-EVALUATION route/schema mismatch")
            require_hex(obj["verified_main_sha"], HEX40_RE, "verified_main_sha")
            require_hex(obj["v1a_merge_sha"], HEX40_RE, "v1a_merge_sha")
            require_hex(obj["run_identity"], HEX64_RE, "run_identity")
            require_date(obj["evaluation_session"], "evaluation_session")
            require_utc_micro(obj["evaluation_as_of_at"], "evaluation_as_of_at")
            validate_database_identity(obj["database_identity"])
            validate_authority_proof(obj["initial_authority_proof"])
            _require_zero_writes(obj)
            terminal = True
        if all_nonnull:
            if seal is None:
                raise ProtocolDefect("consuming negative requires retained seal cross-check")
            record = seal.record()
            validate_seal(record, expected_manifest_id=manifest_id, expected_canonical_bytes=seal.canonical_bytes)
            rb = record["readiness_identity_body"]
            readiness = record["readiness"]
            if obj["readiness"] != readiness or obj["sealed_run_identity"] != record["run_identity"] or obj["seal_record_sha256"] != record["seal_record_sha256"]:
                raise ProtocolDefect("consuming negative seal triple mismatch")
            for key in ("verified_main_sha", "v1a_merge_sha", "reader_identity", "database_identity"):
                if obj[key] != rb[key]:
                    raise ProtocolDefect(f"consuming negative {key} mismatch")
            if obj["evaluation_session"] != readiness["boundary_session"] or obj["evaluation_as_of_at"] != readiness["boundary_as_of_at"]:
                raise ProtocolDefect("consuming negative boundary mismatch")
            if schema == "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1":
                if obj["authority_proof"] != record["initial_authority_proof"]:
                    raise ProtocolDefect("consuming PRE-CELL authority mismatch")
            else:
                if obj["run_identity"] != record["run_identity"] or obj["initial_authority_proof"] != record["initial_authority_proof"]:
                    raise ProtocolDefect("POST-EVALUATION seal binding mismatch")
        expected_filename = f"docs/v-1b-volatility-scorecard-negative-{manifest_id}-{digest}.json"
    if filename != expected_filename:
        raise ProtocolDefect("official receipt filename mismatch")
    return ReceiptBytes(raw, filename, digest, schema, terminal)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA40_RE = re.compile(r"[0-9a-f]{40}\Z")
_RFC3339_US_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_GITHUB_TIME_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z\Z"
)
_HEADER_NAME_RE = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_SAFE_TARGET_RE = re.compile(rb"/[A-Za-z0-9._~!$&'()*+,;=:@%/?-]+\Z")


class GitHubAuthorityFailure(ContractError):
    """Sanitized fail-closed signal; never include response/token/raw exception."""

    def __init__(self) -> None:
        super().__init__("repository authority unavailable")


def _fail() -> NoReturn:
    raise GitHubAuthorityFailure() from None


def _noop_deadline_check() -> int:
    return 0


def _checked_sha256_bytes(
    raw: bytes | bytearray | memoryview,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    """Hash deadline-bound input without one uninterruptible large update."""

    deadline_check = _noop_deadline_check if check is None else check
    try:
        view = _cooperative_call(deadline_check, memoryview, raw)
        view = _cooperative_call(deadline_check, view.cast, "B")
    except BaseException:
        _fail()
    digest = _cooperative_call(deadline_check, hashlib.sha256)
    offset = 0
    while offset < len(view):
        deadline_check()
        end = min(
            offset + GITHUB_DEADLINE_WORK_CHUNK_BYTES,
            len(view),
        )
        chunk = _cooperative_call(
            deadline_check,
            lambda item, start, stop: item[start:stop],
            view,
            offset,
            end,
        )
        _cooperative_call(deadline_check, digest.update, chunk)
        offset = end
    return _cooperative_call(deadline_check, digest.hexdigest)


def _json_no_duplicates(
    raw: bytes,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> object:
    try:
        check()
        if len(raw) > GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES:
            _fail()
        text = _cooperative_call(check, raw.decode, "utf-8", "strict")

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            out: dict[str, object] = {}
            for key, value in _cooperative_tuple(items, check=check):
                check()
                if key in out:
                    _fail()
                out[key] = value
                check()
            return _cooperative_call(check, dict, out)

        value = _cooperative_call(
            check,
            json.loads,
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda _value: _fail(),
        )
        return value
    except GitHubAuthorityFailure:
        raise
    except BaseException:
        _fail()


def _checked_now(clock_ns: Callable[[], int], *ends_ns: int | None) -> int:
    now = clock_ns()
    if type(now) is not int or now < 0:
        _fail()
    if any(end is not None and now >= end for end in ends_ns):
        _fail()
    return now


def _deadline(start_ns: int, duration_ns: int) -> int:
    if type(start_ns) is not int or start_ns < 0:
        _fail()
    return start_ns + duration_ns


@dataclass(frozen=True, slots=True)
class GithubDeadlineContext:
    """Absolute monotonic checkpoint/pagination deadlines.

    ``pagination_end_ns`` is absent for non-paginated requests.  A caller must
    create one checkpoint context immediately before its first DNS/network
    operation and reuse it through all validation in that checkpoint.
    """

    checkpoint_end_ns: int
    pagination_end_ns: int | None = None

    @classmethod
    def begin_checkpoint(cls, clock_ns: Callable[[], int]) -> "GithubDeadlineContext":
        start = clock_ns()
        if type(start) is not int or start < 0:
            _fail()
        return cls(_deadline(start, GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS))

    def begin_pagination(
        self, clock_ns: Callable[[], int]
    ) -> "GithubDeadlineContext":
        if self.pagination_end_ns is not None:
            _fail()
        start = _checked_now(clock_ns, self.checkpoint_end_ns)
        return GithubDeadlineContext(
            self.checkpoint_end_ns,
            _deadline(start, GITHUB_PAGINATION_TOTAL_TIMEOUT_NS),
        )

    def check(self, clock_ns: Callable[[], int], *extra: int | None) -> int:
        return _checked_now(
            clock_ns, self.checkpoint_end_ns, self.pagination_end_ns, *extra
        )

    def checker(
        self,
        clock_ns: Callable[[], int],
        *extra: int | None,
    ) -> Callable[[], int]:
        def check() -> int:
            return self.check(clock_ns, *extra)

        return check

    def remaining_seconds(
        self,
        clock_ns: Callable[[], int],
        *extra: int | None,
    ) -> float:
        now = self.check(clock_ns, *extra)
        return (self.earliest(*extra) - now) / 1_000_000_000

    def earliest(self, *extra: int | None) -> int:
        values = [self.checkpoint_end_ns]
        if self.pagination_end_ns is not None:
            values.append(self.pagination_end_ns)
        values.extend(value for value in extra if value is not None)
        return min(values)


# The child source contains the only permitted host/port and accepts no argv.
# It emits at most one canonical line, closes fd 1, then waits for 0x01 + EOF.
_RESOLVER_CHILD_SOURCE = r'''
import json,os,socket,sys
def die(): os._exit(1)
try:
    f=sys.flags
    if not (f.isolated==1 and f.ignore_environment==1 and f.no_user_site==1 and f.no_site==1 and f.safe_path and sys.dont_write_bytecode and sys.pycache_prefix=="/dev/null/atom-v1b-no-pyc" and sys.version_info[:3]==(3,14,3) and os.environ.get("PYTHON_VERSION")=="3.14.3" and "ATOM_V1B_GITHUB_TOKEN" not in os.environ and "ATOM_E1_SCORECARD_READONLY_DATABASE_URL" not in os.environ): die()
    raw=socket.getaddrinfo("api.github.com",443,socket.AF_UNSPEC,socket.SOCK_STREAM,socket.IPPROTO_TCP)
    addresses=[]; seen=set()
    for family,socktype,proto,_canon,sockaddr in raw:
        if socktype!=socket.SOCK_STREAM or proto!=socket.IPPROTO_TCP: die()
        if family==socket.AF_INET:
            if len(sockaddr)!=2 or type(sockaddr[1]) is not int or sockaddr[1]!=443: die()
            packed=socket.inet_pton(socket.AF_INET,sockaddr[0]); host=socket.inet_ntop(socket.AF_INET,packed)
            entry=["AF_INET",host,443]
        elif family==socket.AF_INET6:
            if len(sockaddr)!=4 or any(type(v) is not int for v in sockaddr[1:]) or sockaddr[1]!=443: die()
            packed=socket.inet_pton(socket.AF_INET6,sockaddr[0]); host=socket.inet_ntop(socket.AF_INET6,packed)
            entry=["AF_INET6",host,443,sockaddr[2],sockaddr[3]]
        else: die()
        key=tuple(entry)
        if key in seen: continue
        seen.add(key); addresses.append(entry)
        if len(addresses)>64: die()
    if not addresses: die()
    data=json.dumps({"addresses":addresses},sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")+b"\n"
    if len(data)>16384: die()
    view=memoryview(data)
    while view:
        n=os.write(1,view)
        if n<=0: die()
        view=view[n:]
    os.close(1)
    ack=b""
    while True:
        part=os.read(0,2)
        if not part: break
        ack+=part
        if len(ack)>1: die()
    if ack!=b"\x01": die()
    os._exit(0)
except BaseException:
    die()
'''.strip()


def _unwired_ssl_context() -> NoReturn:
    # There is no production default-store fallback.  The sole context is
    # explicitly constructed from the stable-read, same-build cadata bytes.
    _fail()


def _read_exact_token() -> str:
    token = os.environ.get(GITHUB_TOKEN_ENV)
    if not isinstance(token, str) or not token:
        _fail()
    try:
        encoded = token.encode("ascii", "strict")
    except UnicodeError:
        _fail()
    if any(byte <= 0x20 or byte == 0x7F for byte in encoded):
        _fail()
    return token


@dataclass(frozen=True, slots=True)
class ResolverChildAuditBaseline:
    """Frozen, non-serialized parent membership proof for one runtime."""

    approved_executable: str
    python_executable_record: FileRecord
    native_records: Mapping[str, FileRecord]


def _resolver_child_audit_baseline(
    plan: RuntimeArtifactPlan,
    measurement: RuntimeMeasurement,
) -> ResolverChildAuditBaseline:
    """Bind exact retained records to the already frozen component hashes."""

    executable = measurement.python_executable_record
    if (
        not os.path.isabs(plan.roots.python_executable)
        or os.path.realpath(plan.roots.python_executable)
        != plan.roots.python_executable
        or executable.path != plan.roots.python_executable
        or executable.size <= 0
        or HEX64_RE.fullmatch(executable.sha256) is None
        or executable.sha256
        != measurement.components.python_executable_sha256
        or canonical_sha256(measurement.components.public())
        != measurement.runtime_artifact_sha256
        or measurement.dependency_versions != plan.dependency_versions
        or measurement.module_names != plan.module_names
    ):
        _fail()

    planned_paths = tuple(candidate.logical_path for candidate in plan.native_files)
    records = tuple(measurement.native_records)
    if (
        len(planned_paths) != len(set(planned_paths))
        or tuple(record.path for record in records) != tuple(sorted(planned_paths))
        or canonical_sha256([record.public() for record in records])
        != measurement.components.loaded_native_tree_sha256
    ):
        _fail()

    retained: dict[str, FileRecord] = {}
    for candidate, record in zip(plan.native_files, records, strict=True):
        if (
            candidate.logical_path != candidate.real_path
            or candidate.logical_path != record.path
            or not os.path.isabs(record.path)
            or os.path.realpath(record.path) != record.path
            or PurePosixPath(record.path).as_posix() != record.path
            or record.size <= 0
            or HEX64_RE.fullmatch(record.sha256) is None
            or record.path in retained
        ):
            _fail()
        retained[record.path] = record
    return ResolverChildAuditBaseline(
        approved_executable=plan.roots.python_executable,
        python_executable_record=executable,
        native_records=MappingProxyType(retained),
    )


def _assert_pidfd_live(
    pidfd: int,
    connect_end_ns: int,
    clock_ns: Callable[[], int],
) -> None:
    if type(pidfd) is not int or pidfd < 0:
        _fail()
    deadline_check = lambda: _checked_now(clock_ns, connect_end_ns)
    deadline_check()
    try:
        _cooperative_call(deadline_check, os.fstat, pidfd)
        selector = _cooperative_acquire(
            deadline_check,
            selectors.DefaultSelector,
            lambda observed: observed.close(),
        )
        try:
            _cooperative_call(
                deadline_check,
                selector.register,
                pidfd,
                selectors.EVENT_READ,
            )
            ready = _cooperative_call(deadline_check, selector.select, 0)
        finally:
            selector.close()
    except BaseException:
        _fail()
    deadline_check()
    if ready:
        _fail()


def _read_complete_proc_file(
    path: str,
    connect_end_ns: int,
    clock_ns: Callable[[], int],
) -> bytes:
    """Read one proc pseudo-file through EOF without a pathname helper."""

    deadline_check = lambda: _checked_now(clock_ns, connect_end_ns)
    deadline_check()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    descriptor = -1
    try:
        descriptor = _cooperative_acquire(
            deadline_check,
            os.open,
            os.close,
            path,
            flags,
        )
        before = _cooperative_call(deadline_check, os.fstat, descriptor)
        output = _cooperative_call(deadline_check, bytearray)
        while True:
            deadline_check()
            chunk = _cooperative_call(
                deadline_check,
                os.read,
                descriptor,
                GITHUB_DEADLINE_WORK_CHUNK_BYTES,
            )
            if not chunk:
                break
            _cooperative_call(deadline_check, output.extend, chunk)
        after = _cooperative_call(deadline_check, os.fstat, descriptor)
    except GitHubAuthorityFailure:
        raise
    except BaseException:
        _fail()
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_gid,
    ):
        _fail()
    deadline_check()
    return _cooperative_call(deadline_check, bytes, output)


def _read_child_executable(
    pid: int,
    baseline: ResolverChildAuditBaseline,
    proc_root: str,
    connect_end_ns: int,
    clock_ns: Callable[[], int],
) -> None:
    deadline_check = lambda: _checked_now(clock_ns, connect_end_ns)
    deadline_check()
    pid_text = _cooperative_call(deadline_check, str, pid)
    proc_executable = _cooperative_call(
        deadline_check,
        os.path.join,
        proc_root,
        pid_text,
        "exe",
    )
    try:
        target = _cooperative_call(deadline_check, os.readlink, proc_executable)
        resolved_target = _cooperative_call(
            deadline_check, os.path.realpath, target
        )
        resolved_proc_target = _cooperative_call(
            deadline_check, os.path.realpath, proc_executable
        )
        target_stat = _cooperative_call(
            deadline_check,
            os.stat,
            proc_executable,
            follow_symlinks=True,
        )
        approved_stat = _cooperative_call(
            deadline_check,
            os.stat,
            baseline.approved_executable,
            follow_symlinks=False,
        )
    except BaseException:
        _fail()
    deadline_check()
    if (
        not os.path.isabs(target)
        or target.endswith(" (deleted)")
        or resolved_target != baseline.approved_executable
        or resolved_proc_target != baseline.approved_executable
        or not stat.S_ISREG(target_stat.st_mode)
        or not stat.S_ISREG(approved_stat.st_mode)
        or (
            target_stat.st_dev,
            target_stat.st_ino,
            target_stat.st_mode,
            target_stat.st_size,
        )
        != (
            approved_stat.st_dev,
            approved_stat.st_ino,
            approved_stat.st_mode,
            approved_stat.st_size,
        )
    ):
        _fail()


def _strict_child_map_entries(
    raw: bytes,
    *,
    check: Callable[[], object] | None = None,
) -> tuple[ProcMapEntry, ...]:
    _cooperative_check(check)
    if not raw or not raw.endswith(b"\n") or b"\0" in raw:
        _fail()
    try:
        entries = parse_proc_maps(raw, check=check)
    except BaseException:
        _fail()
    if not entries:
        _fail()
    previous_end = -1
    for entry in entries:
        _cooperative_check(check)
        if (
            re.fullmatch(r"[r-][w-][x-][ps]", entry.permissions) is None
            or entry.start < previous_end
        ):
            _fail()
        previous_end = entry.end
    _cooperative_check(check)
    return entries


def _audit_resolver_child_maps(
    baseline: ResolverChildAuditBaseline,
    pid: int,
    pidfd: int,
    connect_end_ns: int,
    clock_ns: Callable[[], int],
    *,
    proc_root: str = "/proc",
    file_access: FileAccess | None = None,
    pidfd_liveness_check: Callable[[int, int, Callable[[], int]], None]
    | None = None,
) -> None:
    """Prove the paused resolver's executable-map subset before token read.

    The first maps observation brackets all mapped-file byte reads with the
    second.  Exact raw-byte equality is stronger than merely comparing parsed
    entries and detects a mapping change during those byte measurements.
    """

    if (
        type(pid) is not int
        or pid <= 0
        or type(pidfd) is not int
        or pidfd < 0
        or not os.path.isabs(proc_root)
    ):
        _fail()
    check_live = (
        _assert_pidfd_live
        if pidfd_liveness_check is None
        else pidfd_liveness_check
    )
    deadline_check = lambda: _checked_now(clock_ns, connect_end_ns)
    reader = (
        LocalFileAccess(check=deadline_check)
        if file_access is None
        else file_access
    )
    try:
        pidfd_before = _cooperative_call(deadline_check, os.fstat, pidfd)
    except BaseException:
        _fail()
    _cooperative_call(
        deadline_check,
        check_live,
        pidfd,
        connect_end_ns,
        clock_ns,
    )
    _read_child_executable(
        pid, baseline, proc_root, connect_end_ns, clock_ns
    )
    pid_text = _cooperative_call(deadline_check, str, pid)
    maps_path = _cooperative_call(
        deadline_check,
        os.path.join,
        proc_root,
        pid_text,
        "maps",
    )
    first_raw = _read_complete_proc_file(
        maps_path, connect_end_ns, clock_ns
    )
    first = _strict_child_map_entries(first_raw, check=deadline_check)
    _cooperative_call(
        deadline_check,
        check_live,
        pidfd,
        connect_end_ns,
        clock_ns,
    )

    # Re-read the exact approved executable bytes even if no ordinary maps
    # line happens to name it.  /proc/<pid>/exe and inode equality above bind
    # the child identity; this digest binds that identity to the frozen parent.
    try:
        deadline_check()
        observed_executable = reader.record(
            FileCandidate(
                baseline.approved_executable, baseline.approved_executable
            )
        )
        deadline_check()
    except BaseException:
        _fail()
    if observed_executable != baseline.python_executable_record:
        _fail()

    observed_files: dict[str, FileRecord] = {}
    observed_special: set[str] = set()
    for entry in _cooperative_tuple(first, check=deadline_check):
        deadline_check()
        if "x" not in entry.permissions:
            continue
        path = entry.path
        if path is None:
            _fail()
        if path.startswith("["):
            if (
                path in observed_special
                or not _is_permitted_kernel_executable_mapping(entry)
            ):
                _fail()
            observed_special.add(path)
            continue
        if (
            not os.path.isabs(path)
            or path.endswith(" (deleted)")
            or "\\" in path
            or "\0" in path
        ):
            _fail()
        resolved = _cooperative_call(deadline_check, os.path.realpath, path)
        resolved_posix = _cooperative_call(
            deadline_check,
            PurePosixPath,
            resolved,
        )
        if (
            not os.path.isabs(resolved)
            or _cooperative_call(deadline_check, resolved_posix.as_posix)
            != resolved
        ):
            _fail()
        expected = (
            baseline.python_executable_record
            if resolved == baseline.approved_executable
            else baseline.native_records.get(resolved)
        )
        if expected is None:
            _fail()
        if resolved not in observed_files:
            try:
                deadline_check()
                observed_files[resolved] = reader.record(
                    FileCandidate(resolved, resolved)
                )
                deadline_check()
            except BaseException:
                _fail()
        if observed_files[resolved] != expected:
            _fail()

    second_raw = _read_complete_proc_file(
        maps_path, connect_end_ns, clock_ns
    )
    if second_raw != first_raw:
        _fail()
    _strict_child_map_entries(second_raw, check=deadline_check)
    _read_child_executable(
        pid, baseline, proc_root, connect_end_ns, clock_ns
    )
    _cooperative_call(
        deadline_check,
        check_live,
        pidfd,
        connect_end_ns,
        clock_ns,
    )
    try:
        pidfd_after = _cooperative_call(deadline_check, os.fstat, pidfd)
    except BaseException:
        _fail()
    if (
        pidfd_before.st_dev,
        pidfd_before.st_ino,
        pidfd_before.st_mode,
    ) != (
        pidfd_after.st_dev,
        pidfd_after.st_ino,
        pidfd_after.st_mode,
    ):
        _fail()
    _checked_now(clock_ns, connect_end_ns)


def make_production_child_map_auditor(
    plan: RuntimeArtifactPlan,
    measurement: RuntimeMeasurement,
) -> Callable[[int, int, int, Callable[[], int]], None]:
    """Create the only production auditor from the frozen parent runtime."""

    baseline = _resolver_child_audit_baseline(plan, measurement)

    def audit(
        pid: int,
        pidfd: int,
        connect_end_ns: int,
        clock_ns: Callable[[], int],
    ) -> None:
        _audit_resolver_child_maps(
            baseline, pid, pidfd, connect_end_ns, clock_ns
        )

    return audit


def _unwired_child_map_auditor(
    _pid: int,
    _pidfd: int,
    _connect_end_ns: int,
    _clock_ns: Callable[[], int],
) -> None:
    # Direct test construction remains injectable, but production must use
    # GithubClient.for_frozen_runtime() below.
    _fail()


@dataclass(frozen=True, slots=True)
class GithubTransportSeams:
    """Inject only implementation/test mechanisms, never timeout values."""

    monotonic_ns: Callable[[], int] = time.monotonic_ns
    selector_factory: Callable[[], selectors.BaseSelector] = selectors.DefaultSelector
    socket_factory: Callable[[int, int, int], socket.socket] = socket.socket
    ssl_context_factory: Callable[[], ssl.SSLContext] = _unwired_ssl_context
    popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    pidfd_open: Callable[[int, int], int] = os.pidfd_open
    child_map_auditor: Callable[
        [int, int, int, Callable[[], int]], None
    ] = _unwired_child_map_auditor
    token_reader: Callable[[], str] = _read_exact_token
    # Production uses os._exit so an unproved resolver reap can never unwind
    # into scorecard routing/output.  Tests may inject a non-returning sentinel.
    fatal_termination: Callable[[int], NoReturn] = os._exit


def _selector_wait(
    seams: GithubTransportSeams,
    fileobj: object,
    events: int,
    context: GithubDeadlineContext,
    *extra_ends_ns: int | None,
) -> None:
    end = context.earliest(*extra_ends_ns)
    wait_check = lambda: context.check(
        seams.monotonic_ns,
        *extra_ends_ns,
    )
    while True:
        now = wait_check()
        timeout_seconds = (end - now) / 1_000_000_000
        selector = _cooperative_acquire(
            wait_check,
            seams.selector_factory,
            lambda observed: observed.close(),
        )
        try:
            _cooperative_call(wait_check, selector.register, fileobj, events)
            ready = _cooperative_call(
                wait_check,
                selector.select,
                timeout_seconds,
            )
        except BaseException:
            _fail()
        finally:
            try:
                selector.close()
            except BaseException:
                _fail()
        wait_check()
        if ready:
            return
        # Empty early/spurious selector returns do not reset any deadline.


def _quarantine_fatal(
    fatal_termination: Callable[[int], NoReturn],
) -> NoReturn:
    """Leave no Python unwind path after unresolved resolver cleanup."""

    fatal_termination(1)
    # A conforming fatal seam cannot return.  This fallback is unreachable in
    # production (os._exit) and deliberately remains outside scorecard-domain
    # exception types so a malformed test seam cannot manufacture acceptance.
    raise RuntimeError("fatal termination returned")


def _close_resolver_stream(stream: object | None) -> bool:
    if stream is None:
        return True
    try:
        stream.close()  # type: ignore[attr-defined]
    except BaseException:
        return False
    return True


def _kill_reap(
    proc: subprocess.Popen[bytes],
    *,
    fatal_termination: Callable[[int], NoReturn] = os._exit,
) -> None:
    """Hard-kill and synchronously prove reap, or terminate the parent."""

    try:
        pid = proc.pid
    except BaseException:
        _quarantine_fatal(fatal_termination)
    if type(pid) is not int or pid <= 0:
        _quarantine_fatal(fatal_termination)

    # Closing the acknowledgement writer is the first quarantine operation;
    # it can never send the one success byte.
    stdin_closed = _close_resolver_stream(proc.stdin)
    known_exited = False
    try:
        known_exited = proc.poll() is not None
    except BaseException:
        known_exited = False
    if not known_exited:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        except BaseException:
            # Reap remains the authority; a concurrent exit may make kill
            # report an error without leaving a live child.
            pass

    reaped = False
    while not reaped:
        try:
            proc.wait()
            reaped = True
        except InterruptedError:
            continue
        except BaseException:
            # waitpid is the only fallback and is restricted to the exact PID.
            while True:
                try:
                    waited_pid, _status = os.waitpid(pid, 0)
                except InterruptedError:
                    continue
                except ChildProcessError:
                    # ECHILD proves there is no remaining child to reap.
                    reaped = True
                    break
                except BaseException:
                    _quarantine_fatal(fatal_termination)
                if waited_pid != pid:
                    _quarantine_fatal(fatal_termination)
                reaped = True
                break

    stdout_closed = _close_resolver_stream(proc.stdout)
    if not stdin_closed or not stdout_closed:
        _quarantine_fatal(fatal_termination)


def _parse_resolver_output(
    raw: bytes,
    *,
    check: Callable[[], object] | None = None,
) -> tuple[tuple[object, ...], ...]:
    _cooperative_check(check)
    if (
        not raw
        or len(raw) > GITHUB_RESOLVER_OUTPUT_LIMIT
        or not _cooperative_call(check, raw.endswith, b"\n")
    ):
        _fail()
    if _cooperative_call(check, raw.count, b"\n") != 1:
        _fail()
    try:
        _cooperative_call(check, raw.decode, "ascii", "strict")
    except UnicodeError:
        _fail()
    body = _cooperative_call(check, lambda item: item[:-1], raw)
    value = _json_no_duplicates(body, check=check)
    if type(value) is not dict or _cooperative_call(check, set, value) != {
        "addresses"
    }:
        _fail()
    entries = _cooperative_call(check, value.__getitem__, "addresses")
    if type(entries) is not list or not 1 <= len(entries) <= 64:
        _fail()
    normalized: list[tuple[object, ...]] = []
    seen: set[tuple[object, ...]] = set()
    for item in _cooperative_tuple(entries, check=check):
        _cooperative_check(check)
        if type(item) is not list:
            _fail()
        try:
            if len(item) == 3 and item[0] == "AF_INET":
                family = socket.AF_INET
                if type(item[1]) is not str or type(item[2]) is not int or item[2] != 443:
                    _fail()
                packed = _cooperative_call(
                    check, socket.inet_pton, family, item[1]
                )
                host = _cooperative_call(
                    check, socket.inet_ntop, family, packed
                )
                normalized_item: tuple[object, ...] = ("AF_INET", host, 443)
            elif len(item) == 5 and item[0] == "AF_INET6":
                family = socket.AF_INET6
                if (
                    type(item[1]) is not str
                    or any(type(value) is not int for value in item[2:])
                    or item[2] != 443
                ):
                    _fail()
                packed = _cooperative_call(
                    check, socket.inet_pton, family, item[1]
                )
                host = _cooperative_call(
                    check, socket.inet_ntop, family, packed
                )
                normalized_item = ("AF_INET6", host, 443, item[3], item[4])
            else:
                _fail()
        except (OSError, ValueError):
            _fail()
        if tuple(item) != normalized_item or normalized_item in seen:
            _fail()
        _cooperative_call(check, seen.add, normalized_item)
        _cooperative_call(check, normalized.append, normalized_item)
    public_addresses = _cooperative_call(
        check,
        lambda: [list(item) for item in normalized],
    )
    canonical = _cooperative_call(
        check,
        canonical_json,
        {"addresses": public_addresses},
    )
    encoded = _cooperative_call(check, canonical.encode, "ascii")
    expected = _cooperative_call(check, lambda value: value + b"\n", encoded)
    if raw != expected:
        _fail()
    return _cooperative_call(check, tuple, normalized)


def _resolve_api_github_addresses(
    seams: GithubTransportSeams,
    context: GithubDeadlineContext,
    connect_end_ns: int,
    approved_executable: str,
) -> tuple[tuple[object, ...], ...]:
    """Resolve once, audit twice, acknowledge, exit, and reap before token access."""

    request_check = lambda: context.check(
        seams.monotonic_ns,
        connect_end_ns,
    )
    request_check()
    if (
        not _cooperative_call(request_check, os.path.isabs, approved_executable)
        or _cooperative_call(
            request_check, os.path.realpath, approved_executable
        )
        != approved_executable
        or _cooperative_call(request_check, os.path.realpath, sys.executable)
        != approved_executable
    ):
        _fail()
    args = (
        approved_executable,
        "-I",
        "-S",
        "-B",
        "-X",
        "pycache_prefix=/dev/null/atom-v1b-no-pyc",
        "-c",
        _RESOLVER_CHILD_SOURCE,
    )
    proc: subprocess.Popen[bytes] | None = None
    pidfd = -1
    accepted = False
    output = bytearray()
    addresses: tuple[tuple[object, ...], ...] = ()
    try:
        # Popen is deliberately not hidden inside _cooperative_call: if its
        # post-call clock observation is late we must retain the returned
        # child handle long enough to quarantine and reap that exact PID.
        request_check()
        proc = seams.popen_factory(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env={"PYTHON_VERSION": "3.14.3"},
            bufsize=0,
            text=False,
        )
        request_check()
        if proc.stdin is None or proc.stdout is None:
            _fail()
        pidfd = _cooperative_call(
            request_check,
            seams.pidfd_open,
            proc.pid,
            0,
        )
        stdout_fd = _cooperative_call(request_check, proc.stdout.fileno)
        stdin_fd = _cooperative_call(request_check, proc.stdin.fileno)
        _cooperative_call(request_check, os.set_blocking, stdout_fd, False)
        _cooperative_call(request_check, os.set_blocking, stdin_fd, False)
        _cooperative_call(request_check, os.set_blocking, pidfd, False)

        saw_eof = False
        while not saw_eof:
            _selector_wait(
                seams,
                proc.stdout,
                selectors.EVENT_READ,
                context,
                connect_end_ns,
            )
            request_check()
            try:
                chunk = _cooperative_call(
                    request_check,
                    os.read,
                    stdout_fd,
                    4096,
                )
            except BlockingIOError:
                continue
            except BaseException:
                _fail()
            if chunk:
                if len(output) + len(chunk) > GITHUB_RESOLVER_OUTPUT_LIMIT:
                    _fail()
                _cooperative_call(request_check, output.extend, chunk)
            else:
                saw_eof = True

        # At stdout EOF the child must still be the same live process blocked
        # on its private acknowledgement pipe.
        if _cooperative_call(request_check, proc.poll) is not None:
            _fail()
        selector = _cooperative_acquire(
            request_check,
            seams.selector_factory,
            lambda observed: observed.close(),
        )
        try:
            _cooperative_call(
                request_check,
                selector.register,
                pidfd,
                selectors.EVENT_READ,
            )
            if _cooperative_call(request_check, selector.select, 0):
                _fail()
        finally:
            _cooperative_call(request_check, selector.close)
        request_check()
        raw_output = _cooperative_call(request_check, bytes, output)
        addresses = _parse_resolver_output(
            raw_output,
            check=request_check,
        )
        request_check()

        # Mandatory integration hook: read /proc/<pid>/exe; read maps twice;
        # require equal canonical observations and executable-file subset of
        # the parent candidate loaded_native_tree under inherited V-1A rules.
        try:
            _cooperative_call(
                request_check,
                seams.child_map_auditor,
                proc.pid,
                pidfd,
                context.earliest(connect_end_ns),
                seams.monotonic_ns,
            )
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
        request_check()
        if _cooperative_call(request_check, proc.poll) is not None:
            _fail()

        while True:
            request_check()
            try:
                count = _cooperative_call(
                    request_check,
                    os.write,
                    stdin_fd,
                    b"\x01",
                )
            except BlockingIOError:
                _selector_wait(
                    seams,
                    proc.stdin,
                    selectors.EVENT_WRITE,
                    context,
                    connect_end_ns,
                )
                continue
            except BaseException:
                _fail()
            if count != 1:
                _fail()
            break
        _cooperative_call(request_check, proc.stdin.close)

        while _cooperative_call(request_check, proc.poll) is None:
            _selector_wait(
                seams,
                pidfd,
                selectors.EVENT_READ,
                context,
                connect_end_ns,
            )
        request_check()
        if _cooperative_call(request_check, proc.wait) != 0:
            _fail()
        _cooperative_call(request_check, proc.stdout.close)
        # Mark the pidfd released before the post-close observation so a late
        # successful close is not mistaken for an unresolved descriptor and
        # closed a second time during quarantine.
        request_check()
        os.close(pidfd)
        pidfd = -1
        request_check()
        accepted = True
    except GitHubAuthorityFailure:
        raise
    except BaseException:
        _fail()
    finally:
        if not accepted:
            # Irreversibly discard all resolver observations before cleanup.
            addresses = ()
            try:
                output.clear()
            except BaseException:
                pass
            if proc is not None:
                _kill_reap(
                    proc,
                    fatal_termination=seams.fatal_termination,
                )
        if pidfd >= 0:
            try:
                os.close(pidfd)
            except BaseException:
                _quarantine_fatal(seams.fatal_termination)
    if not accepted:
        _fail()
    return addresses


def _address_sockaddr(entry: tuple[object, ...]) -> tuple[int, tuple[object, ...]]:
    if entry[0] == "AF_INET":
        return socket.AF_INET, (entry[1], entry[2])
    if entry[0] == "AF_INET6":
        return socket.AF_INET6, (entry[1], entry[2], entry[3], entry[4])
    _fail()


def _connect_tls(
    seams: GithubTransportSeams,
    ssl_context: ssl.SSLContext,
    context: GithubDeadlineContext,
    connect_end_ns: int,
    addresses: Sequence[tuple[object, ...]],
) -> ssl.SSLSocket:
    network_check = lambda: context.check(
        seams.monotonic_ns,
        connect_end_ns,
    )
    for entry in _cooperative_tuple(addresses, check=network_check):
        network_check()
        raw: socket.socket | None = None
        tls: ssl.SSLSocket | None = None
        keep_tls = False
        try:
            family, sockaddr = _cooperative_call(
                network_check,
                _address_sockaddr,
                entry,
            )
            raw = _cooperative_acquire(
                network_check,
                seams.socket_factory,
                lambda observed: observed.close(),
                family,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
            )
            _cooperative_call(network_check, raw.setblocking, False)
            result = _cooperative_call(
                network_check,
                raw.connect_ex,
                sockaddr,
            )
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                network_check()
                continue
            if result != 0:
                _selector_wait(
                    seams,
                    raw,
                    selectors.EVENT_WRITE,
                    context,
                    connect_end_ns,
                )
                error = _cooperative_call(
                    network_check,
                    raw.getsockopt,
                    socket.SOL_SOCKET,
                    socket.SO_ERROR,
                )
                if error:
                    network_check()
                    continue
            tls = _cooperative_acquire(
                network_check,
                ssl_context.wrap_socket,
                lambda observed: observed.close(),
                raw,
                server_hostname=GITHUB_API_HOST,
                do_handshake_on_connect=False,
                suppress_ragged_eofs=False,
            )
            raw = None  # ownership moved to tls
            _cooperative_call(network_check, tls.setblocking, False)
            while True:
                try:
                    _cooperative_call(network_check, tls.do_handshake)
                    break
                except ssl.SSLWantReadError:
                    _selector_wait(
                        seams,
                        tls,
                        selectors.EVENT_READ,
                        context,
                        connect_end_ns,
                    )
                except ssl.SSLWantWriteError:
                    _selector_wait(
                        seams,
                        tls,
                        selectors.EVENT_WRITE,
                        context,
                        connect_end_ns,
                    )
            selected_alpn = _cooperative_call(
                network_check,
                tls.selected_alpn_protocol,
            )
            if selected_alpn not in (None, "http/1.1"):
                _fail()
            keep_tls = True
            network_check()
            return tls
        except GitHubAuthorityFailure:
            raise
        except (OSError, ssl.SSLError):
            pass
        except BaseException:
            _fail()
        finally:
            if raw is not None:
                try:
                    raw.close()
                except BaseException:
                    pass
            # A successful TLS socket is returned and must not be closed by
            # the return-path finally clause.
            if tls is not None and tls.fileno() >= 0:
                if not keep_tls:
                    try:
                        tls.close()
                    except BaseException:
                        pass
                    tls = None
    _fail()


def _validate_target(
    target: str,
    *,
    check: Callable[[], object] | None = None,
) -> bytes:
    _cooperative_check(check)
    if not isinstance(target, str):
        _fail()
    try:
        encoded = _cooperative_call(check, target.encode, "ascii", "strict")
    except UnicodeError:
        _fail()
    if _cooperative_call(check, _SAFE_TARGET_RE.fullmatch, encoded) is None:
        _fail()
    parsed = _cooperative_call(check, urllib.parse.urlsplit, target)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        _fail()
    if not (
        parsed.path == GITHUB_REPOSITORY_PATH
        or parsed.path.startswith(GITHUB_REPOSITORY_PATH + "/")
    ):
        _fail()
    if "//" in parsed.path or "/../" in parsed.path or "/./" in parsed.path:
        _fail()
    _cooperative_check(check)
    return encoded


def _build_request(
    target: str,
    token: str,
    *,
    check: Callable[[], object] | None = None,
) -> bytearray:
    target_bytes = _validate_target(target, check=check)
    try:
        token_bytes = _cooperative_call(check, token.encode, "ascii", "strict")
    except UnicodeError:
        _fail()
    if not token_bytes or any(byte <= 0x20 or byte == 0x7F for byte in token_bytes):
        _fail()
    request = _cooperative_call(check, bytearray)
    for part in (
        b"GET ",
        target_bytes,
        b" HTTP/1.1\r\nHost: api.github.com\r\n",
        b"Accept: application/vnd.github+json\r\n",
        b"X-GitHub-Api-Version: 2022-11-28\r\n",
        b"User-Agent: ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1\r\n",
        b"Authorization: Bearer ",
        token_bytes,
        b"\r\nConnection: close\r\n\r\n",
    ):
        _cooperative_call(check, request.extend, part)
    _cooperative_check(check)
    return request


def _send_all_nonblocking(
    tls: ssl.SSLSocket,
    request: bytearray,
    seams: GithubTransportSeams,
    context: GithubDeadlineContext,
    request_end_ns: int,
) -> None:
    network_check = lambda: context.check(seams.monotonic_ns, request_end_ns)
    view = _cooperative_call(network_check, memoryview, request)
    while view:
        try:
            sent = _cooperative_call(network_check, tls.send, view)
            if sent <= 0:
                _fail()
            view = _cooperative_call(
                network_check,
                lambda value, start: value[start:],
                view,
                sent,
            )
        except BlockingIOError:
            _selector_wait(
                seams, tls, selectors.EVENT_WRITE, context, request_end_ns
            )
        except ssl.SSLWantReadError:
            _selector_wait(
                seams, tls, selectors.EVENT_READ, context, request_end_ns
            )
        except ssl.SSLWantWriteError:
            _selector_wait(
                seams, tls, selectors.EVENT_WRITE, context, request_end_ns
            )
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
    network_check()


def _recv_to_tls_eof(
    tls: ssl.SSLSocket,
    seams: GithubTransportSeams,
    context: GithubDeadlineContext,
    request_end_ns: int,
    *,
    raw_limit_bytes: int = GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES,
) -> bytes:
    if (
        type(raw_limit_bytes) is not int
        or raw_limit_bytes <= 0
        or raw_limit_bytes > GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES
    ):
        _fail()
    idle_start = context.check(seams.monotonic_ns, request_end_ns)
    idle_end_ns = _deadline(idle_start, GITHUB_READ_IDLE_TIMEOUT_NS)
    raw = _cooperative_call(
        lambda: context.check(seams.monotonic_ns, request_end_ns, idle_end_ns),
        bytearray,
    )
    while True:
        read_check = lambda: context.check(
            seams.monotonic_ns,
            request_end_ns,
            idle_end_ns,
        )
        try:
            remaining_with_sentinel = raw_limit_bytes - len(raw) + 1
            requested = min(
                GITHUB_DEADLINE_WORK_CHUNK_BYTES,
                remaining_with_sentinel,
            )
            chunk = _cooperative_call(
                read_check,
                tls.recv,
                requested,
            )
        except BlockingIOError:
            _selector_wait(
                seams,
                tls,
                selectors.EVENT_READ,
                context,
                request_end_ns,
                idle_end_ns,
            )
            continue
        except ssl.SSLWantReadError:
            _selector_wait(
                seams,
                tls,
                selectors.EVENT_READ,
                context,
                request_end_ns,
                idle_end_ns,
            )
            continue
        except ssl.SSLWantWriteError:
            _selector_wait(
                seams,
                tls,
                selectors.EVENT_WRITE,
                context,
                request_end_ns,
                idle_end_ns,
            )
            continue
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
        delivered_at = context.check(
            seams.monotonic_ns, request_end_ns, idle_end_ns
        )
        if not isinstance(chunk, bytes):
            _fail()
        if not chunk:
            return _cooperative_call(
                lambda: context.check(seams.monotonic_ns, request_end_ns),
                bytes,
                raw,
            )
        if (
            len(chunk) > raw_limit_bytes - len(raw)
        ):
            # Refuse the entire response before growing the retained buffer;
            # never parse or accept a cap-sized prefix of an oversized body.
            _fail()
        # Reset only on at least one newly delivered response octet.
        idle_end_ns = _deadline(delivered_at, GITHUB_READ_IDLE_TIMEOUT_NS)
        _cooperative_call(
            lambda: context.check(
                seams.monotonic_ns,
                request_end_ns,
                idle_end_ns,
            ),
            raw.extend,
            chunk,
        )


def _parse_headers(
    block: bytes,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[bytes, list[bytes]]:
    check()
    lines = _cooperative_call(check, block.split, b"\r\n")
    headers: dict[bytes, list[bytes]] = {}
    for line in _cooperative_tuple(lines, check=check):
        check()
        leading = _cooperative_call(
            check,
            lambda value: value[:1],
            line,
        )
        has_colon = _cooperative_call(check, lambda value: b":" in value, line)
        if not line or leading in (b" ", b"\t") or not has_colon:
            _fail()
        name, value = _cooperative_call(check, line.split, b":", 1)
        if _cooperative_call(check, _HEADER_NAME_RE.fullmatch, name) is None:
            _fail()
        invalid_value = _cooperative_call(
            check,
            lambda item: any(
                byte < 0x20 and byte != 0x09 for byte in item
            )
            or b"\x7f" in item,
            value,
        )
        if invalid_value:
            _fail()
        key = _cooperative_call(check, name.lower)
        values = _cooperative_call(check, headers.setdefault, key, [])
        stripped = _cooperative_call(check, value.strip, b" \t")
        _cooperative_call(check, values.append, stripped)
        check()
    if b"location" in headers:
        _fail()
    check()
    return headers


def _decode_chunked(
    body: bytes,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> tuple[bytes, dict[bytes, list[bytes]]]:
    position = 0
    decoded = bytearray()
    trailers: dict[bytes, list[bytes]] = {}
    while True:
        check()
        end = _cooperative_call(check, body.find, b"\r\n", position)
        if end < 0:
            _fail()
        line = _cooperative_call(
            check,
            lambda value, start, stop: value[start:stop],
            body,
            position,
            end,
        )
        position = end + 2
        size_token, separator, extension = _cooperative_call(
            check,
            line.partition,
            b";",
        )
        if _cooperative_call(
            check,
            re.fullmatch,
            rb"[0-9A-Fa-f]+",
            size_token,
        ) is None:
            _fail()
        extension_invalid = separator and _cooperative_call(
            check,
            lambda value: any(byte < 0x20 or byte > 0x7E for byte in value),
            extension,
        )
        if extension_invalid:
            _fail()
        size = _cooperative_call(check, int, size_token, 16)
        if size == 0:
            trailer_end = _cooperative_call(
                check,
                body.find,
                b"\r\n\r\n",
                position,
            )
            if trailer_end < 0:
                # Empty trailer section is exactly one CRLF after the zero line.
                tail = _cooperative_call(
                    check,
                    lambda value, start: value[start:],
                    body,
                    position,
                )
                if tail == b"\r\n":
                    position += 2
                    break
                _fail()
            trailer_block = _cooperative_call(
                check,
                lambda value, start, stop: value[start:stop],
                body,
                position,
                trailer_end,
            )
            if trailer_block:
                trailers = _parse_headers(trailer_block, check=check)
            position = trailer_end + 4
            break
        if len(body) - position < size + 2:
            _fail()
        chunk_end = position + size
        while position < chunk_end:
            check()
            copy_end = min(
                position + GITHUB_DEADLINE_WORK_CHUNK_BYTES, chunk_end
            )
            copy = _cooperative_call(
                check,
                lambda value, start, stop: value[start:stop],
                body,
                position,
                copy_end,
            )
            _cooperative_call(check, decoded.extend, copy)
            position = copy_end
            check()
        terminator = _cooperative_call(
            check,
            lambda value, start: value[start : start + 2],
            body,
            position,
        )
        if terminator != b"\r\n":
            _fail()
        position += 2
    if position != len(body):
        _fail()
    if b"location" in trailers:
        _fail()
    return _cooperative_call(check, bytes, decoded), trailers


@dataclass(frozen=True, slots=True)
class GithubHTTPResponse:
    status: int
    headers: Mapping[bytes, tuple[bytes, ...]]
    body: bytes

    def header_values(self, name: bytes) -> tuple[bytes, ...]:
        return self.headers.get(name.lower(), ())


def _parse_http_response(
    raw: bytes,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> GithubHTTPResponse:
    check()
    if len(raw) > GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES:
        _fail()
    split = _cooperative_call(check, raw.find, b"\r\n\r\n")
    head_prefix = _cooperative_call(
        check,
        lambda value, stop: value[:stop],
        raw,
        split,
    )
    normalized_head = _cooperative_call(
        check,
        head_prefix.replace,
        b"\r\n",
        b"",
    )
    if split < 0 or b"\n" in normalized_head:
        _fail()
    head = _cooperative_call(
        check,
        lambda value, stop: value[:stop],
        raw,
        split,
    )
    wire_body = _cooperative_call(
        check,
        lambda value, start: value[start:],
        raw,
        split + 4,
    )
    first_end = _cooperative_call(check, head.find, b"\r\n")
    if first_end < 0:
        _fail()
    status_line = _cooperative_call(
        check,
        lambda value, stop: value[:stop],
        head,
        first_end,
    )
    match = _cooperative_call(
        check,
        re.fullmatch,
        rb"HTTP/1\.1 ([0-9]{3})(?: [\x20-\x7e]*)?",
        status_line,
    )
    if match is None:
        _fail()
    status_group = _cooperative_call(check, match.group, 1)
    status = _cooperative_call(check, int, status_group)
    if 300 <= status <= 399 or 100 <= status <= 199:
        _fail()
    header_block = _cooperative_call(
        check,
        lambda value, start: value[start:],
        head,
        first_end + 2,
    )
    headers = _cooperative_call(
        check,
        _parse_headers,
        header_block,
        check=check,
    )
    content_lengths = _cooperative_call(
        check,
        headers.get,
        b"content-length",
        [],
    )
    transfer_encodings = _cooperative_call(
        check,
        headers.get,
        b"transfer-encoding",
        [],
    )
    if content_lengths and transfer_encodings:
        _fail()
    if len(content_lengths) > 1 or len(transfer_encodings) > 1:
        _fail()
    if transfer_encodings:
        coding_parts = _cooperative_call(
            check,
            transfer_encodings[0].split,
            b",",
        )
        codings: list[bytes] = []
        for part in _cooperative_tuple(coding_parts, check=check):
            stripped = _cooperative_call(check, part.strip)
            lowered = _cooperative_call(check, stripped.lower)
            _cooperative_call(check, codings.append, lowered)
        if codings != [b"chunked"]:
            _fail()
        body, trailers = _cooperative_call(
            check,
            _decode_chunked,
            wire_body,
            check=check,
        )
        if b"content-length" in trailers or b"transfer-encoding" in trailers:
            _fail()
        for key, values in _cooperative_tuple(trailers.items(), check=check):
            header_values = _cooperative_call(
                check,
                headers.setdefault,
                key,
                [],
            )
            _cooperative_call(check, header_values.extend, values)
    elif content_lengths:
        value = content_lengths[0]
        if _cooperative_call(
            check,
            re.fullmatch,
            rb"0|[1-9][0-9]*",
            value,
        ) is None:
            _fail()
        if len(wire_body) != _cooperative_call(check, int, value):
            _fail()
        body = wire_body
    else:
        # The caller reads to authenticated TLS EOF, so close-delimited framing
        # is complete without treating a stall/partial close as success.
        body = wire_body
    encoding = _cooperative_call(
        check,
        headers.get,
        b"content-encoding",
        [],
    )
    normalized_encoding = (
        _cooperative_call(
            check,
            _cooperative_call(check, encoding[0].strip).lower,
        )
        if encoding
        else None
    )
    if len(encoding) > 1 or (
        encoding and normalized_encoding != b"identity"
    ):
        _fail()
    frozen_headers: dict[bytes, tuple[bytes, ...]] = {}
    for key, values in _cooperative_tuple(headers.items(), check=check):
        frozen_headers[key] = _cooperative_call(check, tuple, values)
        check()
    return _cooperative_call(
        check,
        GithubHTTPResponse,
        status=status,
        headers=frozen_headers,
        body=body,
    )


class GithubClient:
    """One fresh DNS child, TCP/TLS connection, and close per authenticated GET."""

    def __init__(
        self,
        *,
        approved_executable: str,
        seams: GithubTransportSeams,
        ssl_context: ssl.SSLContext | object | None = None,
    ) -> None:
        self._approved_executable = approved_executable
        self._seams = seams
        try:
            self._ssl_context = (
                seams.ssl_context_factory()
                if ssl_context is None
                else ssl_context
            )
        except BaseException:
            _fail()

    @classmethod
    def for_frozen_runtime(
        cls,
        *,
        plan: RuntimeArtifactPlan,
        measurement: RuntimeMeasurement,
        ssl_context: ssl.SSLContext | object,
    ) -> "GithubClient":
        """Construct production transport with the mandatory child audit.

        The ordinary constructor and ``GithubTransportSeams`` remain available
        for synthetic tests.  Runtime orchestration must use this constructor;
        it cannot replace the auditor or its frozen parent baseline.
        """

        auditor = make_production_child_map_auditor(plan, measurement)
        seams = GithubTransportSeams(child_map_auditor=auditor)
        return cls(
            approved_executable=plan.roots.python_executable,
            seams=seams,
            ssl_context=ssl_context,
        )

    def get_json(
        self,
        target: str,
        *,
        context: GithubDeadlineContext,
        allowed_statuses: frozenset[int] = frozenset({200}),
        validator: Callable[
            [
                object,
                int,
                Mapping[bytes, tuple[bytes, ...]],
                Callable[[], int],
            ],
            object,
        ]
        | None = None,
    ) -> tuple[GithubHTTPResponse, object]:
        """Perform exactly one request.  No retry occurs at any layer."""

        _validate_target(target)
        request_start = context.check(self._seams.monotonic_ns)
        request_end_ns = _deadline(request_start, GITHUB_REQUEST_TOTAL_TIMEOUT_NS)
        connect_end_ns = _deadline(request_start, GITHUB_CONNECT_TIMEOUT_NS)
        request_check = context.checker(
            self._seams.monotonic_ns, request_end_ns
        )
        addresses = _resolve_api_github_addresses(
            self._seams,
            context,
            connect_end_ns,
            self._approved_executable,
        )
        # This is intentionally the first token access in this request.  The
        # resolver has exited, been reaped, and all of its fds are closed.
        try:
            token = _cooperative_call(
                request_check,
                self._seams.token_reader,
            )
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
        if not isinstance(token, str):
            _fail()
        tls: ssl.SSLSocket | None = None
        request: bytearray | None = None
        try:
            tls = _connect_tls(
                self._seams,
                self._ssl_context,
                context,
                connect_end_ns,
                addresses,
            )
            context.check(self._seams.monotonic_ns, connect_end_ns, request_end_ns)
            request = _build_request(target, token, check=request_check)
            _send_all_nonblocking(
                tls, request, self._seams, context, request_end_ns
            )
            raw = _recv_to_tls_eof(
                tls, self._seams, context, request_end_ns
            )
            response = _cooperative_call(
                request_check,
                _parse_http_response,
                raw,
                check=request_check,
            )
            if response.status not in allowed_statuses:
                _fail()
            content_types = _cooperative_call(
                request_check,
                response.header_values,
                b"content-type",
            )
            if len(content_types) != 1:
                _fail()
            try:
                media_parts = _cooperative_call(
                    request_check,
                    content_types[0].split,
                    b";",
                    1,
                )
                media_type = _cooperative_call(
                    request_check,
                    _cooperative_call(
                        request_check,
                        media_parts[0].strip,
                    ).lower,
                )
            except BaseException:
                _fail()
            if not (
                media_type == b"application/json"
                or media_type == b"application/vnd.github+json"
                or media_type.endswith(b"+json")
            ):
                _fail()
            value = _json_no_duplicates(response.body, check=request_check)
            if validator is not None:
                value = _cooperative_call(
                    request_check,
                    validator,
                    value,
                    response.status,
                    response.headers,
                    request_check,
                )
            # Request total includes full response/framing/JSON/schema validation.
            request_check()
            return response, value
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
        finally:
            # Best-effort overwrite of our mutable Authorization-bearing copy;
            # no request, header, token, raw exception, or response enters logs.
            if request is not None:
                request[:] = b"\x00" * len(request)
            token = ""
            if tls is not None:
                try:
                    tls.close()
                except BaseException:
                    pass

    def get_paginated_json(
        self,
        collection_path: str,
        *,
        context: GithubDeadlineContext,
        page_validator: Callable[
            [object, Callable[[], int]], Sequence[object]
        ],
        collection_validator: Callable[
            [tuple[object, ...], GithubDeadlineContext], object
        ]
        | None = None,
    ) -> object:
        """Read pages 1..N under one immutable 180-second deadline."""

        if "?" in collection_path or not collection_path.startswith(GITHUB_REPOSITORY_PATH + "/"):
            _fail()
        paged = context.begin_pagination(self._seams.monotonic_ns)
        paged_check = paged.checker(self._seams.monotonic_ns)
        page = 1
        all_items: list[object] = []
        while True:
            target = f"{collection_path}?per_page={GITHUB_PAGE_SIZE}&page={page}"

            def validate_page(
                value: object,
                status: int,
                headers: Mapping[bytes, tuple[bytes, ...]],
                request_check: Callable[[], int] = paged_check,
            ) -> object:
                request_check()
                if status != 200:
                    _fail()
                page_items = _cooperative_call(
                    request_check,
                    page_validator,
                    value,
                    request_check,
                )
                validated_items: list[object] = []
                for item in _cooperative_tuple(
                    page_items,
                    check=request_check,
                ):
                    request_check()
                    _cooperative_call(
                        request_check,
                        validated_items.append,
                        item,
                    )
                items = _cooperative_call(
                    request_check,
                    tuple,
                    validated_items,
                )
                link_values = _cooperative_call(
                    request_check,
                    headers.get,
                    b"link",
                    (),
                )
                next_page = _next_page_from_link(
                    link_values,
                    collection_path,
                    page,
                    check=request_check,
                )
                request_check()
                return items, next_page

            _response, validated = self.get_json(
                target,
                context=paged,
                allowed_statuses=frozenset({200}),
                validator=validate_page,
            )
            # ``validated`` is constructed only by the exact request-local
            # closure above after its schema/link checks.  Do not postpone a
            # redundant response-shape assertion until after that page's
            # 60-second request deadline has ended.
            items, next_page = validated
            _cooperative_call(paged_check, all_items.extend, items)
            if next_page is None:
                break
            if next_page != page + 1:
                _fail()
            page = next_page

        collected = _cooperative_call(paged_check, tuple, all_items)
        if collection_validator is None:
            result: object = collected
        else:
            result = _cooperative_call(
                paged_check,
                collection_validator,
                collected,
                paged,
            )
        paged_check()
        return result


def _split_link_values(
    values: Iterable[bytes],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> tuple[bytes, ...]:
    parts: list[bytes] = []
    for value in _cooperative_tuple(values, check=check):
        check()
        current = _cooperative_call(check, bytearray)
        in_angle = False
        in_quote = False
        escaped = False
        for byte in value:
            check()
            if escaped:
                _cooperative_call(check, current.append, byte)
                escaped = False
            elif in_quote and byte == 0x5C:
                _cooperative_call(check, current.append, byte)
                escaped = True
            elif byte == 0x22:
                _cooperative_call(check, current.append, byte)
                in_quote = not in_quote
            elif not in_quote and byte == 0x3C:
                _cooperative_call(check, current.append, byte)
                in_angle = True
            elif not in_quote and byte == 0x3E:
                _cooperative_call(check, current.append, byte)
                in_angle = False
            elif not in_quote and not in_angle and byte == 0x2C:
                if not current:
                    _fail()
                materialized = _cooperative_call(check, bytes, current)
                stripped = _cooperative_call(check, materialized.strip)
                _cooperative_call(check, parts.append, stripped)
                _cooperative_call(check, current.clear)
            else:
                _cooperative_call(check, current.append, byte)
        if in_angle or in_quote or escaped or not current:
            _fail()
        materialized = _cooperative_call(check, bytes, current)
        stripped = _cooperative_call(check, materialized.strip)
        _cooperative_call(check, parts.append, stripped)
    return _cooperative_call(check, tuple, parts)


def _next_page_from_link(
    values: Iterable[bytes],
    collection_path: str,
    current_page: int,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> int | None:
    found: int | None = None
    link_parts = _cooperative_call(
        check,
        _split_link_values,
        values,
        check=check,
    )
    for part in link_parts:
        check()
        match = _cooperative_call(
            check,
            re.fullmatch,
            rb"<([^<>]+)>((?:\s*;\s*[^;]+)*)",
            part,
        )
        if match is None:
            _fail()
        try:
            url_group = _cooperative_call(check, match.group, 1)
            params_group = _cooperative_call(check, match.group, 2)
            url = _cooperative_call(
                check,
                url_group.decode,
                "ascii",
                "strict",
            )
            params_text = _cooperative_call(
                check,
                params_group.decode,
                "ascii",
                "strict",
            )
        except UnicodeError:
            _fail()
        rels: list[str] = []
        parameters = _cooperative_call(check, params_text.split, ";")
        for parameter in _cooperative_tuple(parameters, check=check):
            check()
            parameter = _cooperative_call(check, parameter.strip)
            if not parameter:
                check()
                continue
            name, separator, value = _cooperative_call(
                check,
                parameter.partition,
                "=",
            )
            if not separator:
                _fail()
            if _cooperative_call(check, name.lower) == "rel":
                if len(value) < 2 or value[0] != '"' or value[-1] != '"':
                    _fail()
                rel_value = _cooperative_call(
                    check,
                    lambda item: item[1:-1],
                    value,
                )
                rel_items = _cooperative_call(check, rel_value.split)
                _cooperative_call(check, rels.extend, rel_items)
        if "next" not in rels:
            check()
            continue
        if found is not None:
            _fail()
        parsed = _cooperative_call(check, urllib.parse.urlsplit, url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != GITHUB_API_HOST
            or parsed.path != collection_path
            or parsed.fragment
        ):
            _fail()
        try:
            pairs = _cooperative_call(
                check,
                urllib.parse.parse_qsl,
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="ascii",
                errors="strict",
            )
        except (UnicodeError, ValueError):
            _fail()
        pair_keys = _cooperative_call(
            check,
            set,
            (key for key, _value in pairs),
        )
        if len(pairs) != 2 or pair_keys != {"per_page", "page"}:
            _fail()
        query = _cooperative_call(check, dict, pairs)
        page_size_text = _cooperative_call(check, str, GITHUB_PAGE_SIZE)
        if query["per_page"] != page_size_text or _cooperative_call(
            check,
            re.fullmatch,
            r"[1-9][0-9]*",
            query["page"],
        ) is None:
            _fail()
        found = _cooperative_call(check, int, query["page"])
        if found != current_page + 1:
            _fail()
    check()
    return found


def _exact_dict(
    value: object,
    keys: frozenset[str],
    *,
    check: Callable[[], object] | None = None,
) -> dict[str, object]:
    _cooperative_check(check)
    observed_keys = (
        _cooperative_call(check, set, value)
        if type(value) is dict
        else None
    )
    if type(value) is not dict or observed_keys != keys:
        _fail()
    _cooperative_check(check)
    return value  # type: ignore[return-value]


def _string(
    value: object,
    *,
    exact: str | None = None,
    check: Callable[[], object] | None = None,
) -> str:
    _cooperative_check(check)
    invalid = (
        type(value) is not str
        or not value
        or _cooperative_call(
            check,
            lambda text: any(ord(character) < 0x20 for character in text),
            value,
        )
    )
    if invalid:
        _fail()
    if exact is not None and value != exact:
        _fail()
    _cooperative_check(check)
    return value


def _positive_int(
    value: object,
    *,
    check: Callable[[], object] | None = None,
) -> int:
    _cooperative_check(check)
    if type(value) is not int or value <= 0:
        _fail()
    _cooperative_check(check)
    return value


def _sha256(
    value: object,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    text = _string(value, check=check)
    if _cooperative_call(check, _SHA256_RE.fullmatch, text) is None:
        _fail()
    _cooperative_check(check)
    return text


def _sha40(
    value: object,
    *,
    check: Callable[[], object] | None = None,
) -> str:
    text = _string(value, check=check)
    if _cooperative_call(check, _SHA40_RE.fullmatch, text) is None:
        _fail()
    _cooperative_check(check)
    return text


def _timestamp(
    value: object,
    *,
    microseconds: bool,
    check: Callable[[], object] | None = None,
) -> str:
    text = _string(value, check=check)
    if (
        microseconds
        and _cooperative_call(check, _RFC3339_US_RE.fullmatch, text) is None
    ) or (
        not microseconds
        and _cooperative_call(check, _GITHUB_TIME_RE.fullmatch, text) is None
    ):
        _fail()
    try:
        normalized = _cooperative_call(
            check,
            lambda timestamp: timestamp[:-1] + "+00:00",
            text,
        )
        _cooperative_call(
            check,
            datetime.fromisoformat,
            normalized,
        )
    except ValueError:
        _fail()
    _cooperative_check(check)
    return text


_RULES = [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
]
_CONDITIONS = {"ref_name": {"include": ["refs/heads/main"], "exclude": []}}


def _validate_window(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    check()
    window = _exact_dict(
        value,
        frozenset(
            {
                "schema_version",
                "repository",
                "repository_id",
                "ruleset_id",
                "name",
                "target",
                "source_type",
                "source",
                "enforcement",
                "conditions",
                "rules",
                "bypass_actors",
                "created_at",
                "updated_at",
                "execution_source_sha",
                "manifest_id",
                "opened_at_utc",
            }
        ),
        check=check,
    )
    _string(
        window["schema_version"],
        exact="ATOM-V1B-NO-MAIN-UPDATE-WINDOW-1",
        check=check,
    )
    _string(window["repository"], exact=GITHUB_REPOSITORY, check=check)
    if type(window["repository_id"]) is not int or window["repository_id"] != GITHUB_REPOSITORY_ID:
        _fail()
    _positive_int(window["ruleset_id"], check=check)
    _string(
        window["name"],
        exact="ATOM-V1B-NO-MAIN-UPDATE-1",
        check=check,
    )
    _string(window["target"], exact="branch", check=check)
    _string(window["source_type"], exact="Repository", check=check)
    _string(window["source"], exact=GITHUB_REPOSITORY, check=check)
    _string(window["enforcement"], exact="active", check=check)
    observed_conditions = _cooperative_call(
        check,
        canonical_json,
        window["conditions"],
    )
    expected_conditions = _cooperative_call(check, canonical_json, _CONDITIONS)
    observed_rules = _cooperative_call(
        check,
        canonical_json,
        window["rules"],
    )
    expected_rules = _cooperative_call(check, canonical_json, _RULES)
    if (
        observed_conditions != expected_conditions
        or observed_rules != expected_rules
    ):
        _fail()
    if window["bypass_actors"] != []:
        _fail()
    check()
    _timestamp(window["created_at"], microseconds=False, check=check)
    _timestamp(window["updated_at"], microseconds=False, check=check)
    _sha40(window["execution_source_sha"], check=check)
    manifest = _string(window["manifest_id"], check=check)
    if manifest not in MANIFEST_IDS:
        _fail()
    _timestamp(window["opened_at_utc"], microseconds=True, check=check)
    check()
    return window


def _validate_github_tls_trust(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    trust = _exact_dict(
        value,
        frozenset(
            {
                "source",
                "reported_cafile_path",
                "canonical_cafile_path",
                "cafile_size_bytes",
                "cafile_sha256",
            }
        ),
        check=check,
    )
    _string(
        trust["source"],
        exact="ssl.get_default_verify_paths().cafile",
        check=check,
    )
    reported = _string(trust["reported_cafile_path"], check=check)
    canonical = _string(trust["canonical_cafile_path"], check=check)
    if (
        not _cooperative_call(check, os.path.isabs, reported)
        or not _cooperative_call(check, os.path.isabs, canonical)
        or _cooperative_call(check, os.path.normpath, canonical) != canonical
    ):
        _fail()
    _positive_int(trust["cafile_size_bytes"], check=check)
    _sha256(trust["cafile_sha256"], check=check)
    check()
    return trust


def _validate_provenance(
    value: object,
    artifact_components_validator: Callable[[object], object],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    check()
    provenance = _exact_dict(
        value,
        frozenset(
            {
                "schema_version",
                "render_service_id",
                "render_build_id",
                "render_deploy_id",
                "repository",
                "execution_source_sha",
                "build_command",
                "python_version",
                "runtime_artifact_components",
                "runtime_artifact_sha256",
                "probe_generated_at_utc",
                "github_tls_trust",
            }
        ),
        check=check,
    )
    _string(
        provenance["schema_version"],
        exact="ATOM-V1B-RUNTIME-PROVENANCE-1",
        check=check,
    )
    _string(
        provenance["render_service_id"],
        exact="srv-daa7thgae00c73a2lmn0",
        check=check,
    )
    build = _string(provenance["render_build_id"], check=check)
    if _string(provenance["render_deploy_id"], check=check) != build:
        _fail()
    _string(provenance["repository"], exact=GITHUB_REPOSITORY, check=check)
    _sha40(provenance["execution_source_sha"], check=check)
    _string(
        provenance["build_command"],
        exact="pip install -r requirements.txt",
        check=check,
    )
    _string(provenance["python_version"], exact="3.14.3", check=check)
    components = _cooperative_call(
        check,
        artifact_components_validator,
        provenance["runtime_artifact_components"],
    )
    if components != provenance["runtime_artifact_components"]:
        _fail()
    if _sha256(
        provenance["runtime_artifact_sha256"], check=check
    ) != _cooperative_canonical_sha256(components, check=check):
        _fail()
    _timestamp(
        provenance["probe_generated_at_utc"],
        microseconds=True,
        check=check,
    )
    _validate_github_tls_trust(provenance["github_tls_trust"], check=check)
    check()
    return provenance


def _validate_capacity(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    check()
    capacity = _exact_dict(
        value,
        frozenset(
            {
                "mechanism",
                "service_id",
                "recovery_transport_policy",
            }
        ),
        check=check,
    )
    _string(
        capacity["mechanism"],
        exact="Render native one-off Create job startCommand",
        check=check,
    )
    _string(
        capacity["service_id"],
        exact="srv-daa7thgae00c73a2lmn0",
        check=check,
    )
    _string(
        capacity["recovery_transport_policy"],
        exact=RECOVERY_TRANSPORT_POLICY,
        check=check,
    )
    check()
    return capacity


def _validate_legacy_capacity(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    capacity = _exact_dict(
        value,
        frozenset(
            {
                "mechanism",
                "service_id",
                "accepted_render_startCommand_limit_bytes",
                "recovery_capacity_margin_bytes",
                "vendor_evidence_reference",
                "vendor_evidence_sha256",
                "vendor_evidence_observed_at_utc",
            }
        ),
        check=check,
    )
    _string(capacity["mechanism"], exact="Render native one-off Create job startCommand", check=check)
    _string(capacity["service_id"], exact=RENDER_SERVICE_ID, check=check)
    _positive_int(capacity["accepted_render_startCommand_limit_bytes"], check=check)
    if capacity["recovery_capacity_margin_bytes"] != 4096:
        _fail()
    _string(capacity["vendor_evidence_reference"], check=check)
    _sha256(capacity["vendor_evidence_sha256"], check=check)
    _timestamp(capacity["vendor_evidence_observed_at_utc"], microseconds=True, check=check)
    return capacity


def _validate_payload(
    value: object,
    artifact_components_validator: Callable[[object], object],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object]:
    check()
    payload = _exact_dict(
        value,
        frozenset(
            {
                "schema_version",
                "provenance",
                "provenance_sha256",
                "capacity",
                "no_ref_update_window",
                "no_ref_update_window_sha256",
                "probe_job_id",
                "probe_observation_sha256",
                "control_plane_evidence_sha256",
                "pat_scope_evidence_sha256",
                "incident_record_id",
                "incident_finalization_sha256",
                "rotation_status",
                "rotation_completion_timestamp",
            }
        ),
        check=check,
    )
    schema_version = _string(payload["schema_version"], check=check)
    if schema_version not in {
        "ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-1",
        OPERATIONAL_APPROVAL_SCHEMA_VERSION,
    }:
        _fail()
    provenance = _validate_provenance(
        payload["provenance"],
        artifact_components_validator,
        check=check,
    )
    if _sha256(
        payload["provenance_sha256"], check=check
    ) != _cooperative_canonical_sha256(provenance, check=check):
        _fail()
    if schema_version == OPERATIONAL_APPROVAL_SCHEMA_VERSION:
        _validate_capacity(payload["capacity"], check=check)
    else:
        _validate_legacy_capacity(payload["capacity"], check=check)
    window = _validate_window(payload["no_ref_update_window"], check=check)
    if _sha256(
        payload["no_ref_update_window_sha256"], check=check
    ) != _cooperative_canonical_sha256(window, check=check):
        _fail()
    _string(payload["probe_job_id"], check=check)
    _sha256(payload["probe_observation_sha256"], check=check)
    _sha256(payload["control_plane_evidence_sha256"], check=check)
    _sha256(payload["pat_scope_evidence_sha256"], check=check)
    _string(
        payload["incident_record_id"],
        exact="ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06",
        check=check,
    )
    _sha256(payload["incident_finalization_sha256"], check=check)
    _string(payload["rotation_status"], exact="COMPLETED", check=check)
    _timestamp(
        payload["rotation_completion_timestamp"],
        microseconds=True,
        check=check,
    )
    if provenance["execution_source_sha"] != window["execution_source_sha"]:
        _fail()
    check()
    return payload


@dataclass(frozen=True, slots=True)
class ReviewComment:
    comment_id: int
    author_id: int
    author_login: str
    created_at: str
    canonical_body: bytes
    approval_payload_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovalComment:
    comment_id: int
    created_at: str
    canonical_body: bytes
    payload: Mapping[str, object]
    window: Mapping[str, object]
    review_comment_id: int
    reviewer_user_id: int
    reviewer_login: str

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.canonical_body).hexdigest()


def _comment_envelope(
    comment: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> tuple[dict[str, object], dict[str, object]]:
    check()
    if type(comment) is not dict:
        _fail()
    envelope: dict[str, object] = comment  # type: ignore[assignment]
    comment_id = _positive_int(
        _cooperative_call(check, envelope.get, "id"),
        check=check,
    )
    user = _cooperative_call(check, envelope.get, "user")
    if type(user) is not dict:
        _fail()
    user_dict: dict[str, object] = user  # type: ignore[assignment]
    _positive_int(
        _cooperative_call(check, user_dict.get, "id"),
        check=check,
    )
    _string(
        _cooperative_call(check, user_dict.get, "login"),
        check=check,
    )
    created = _timestamp(
        _cooperative_call(check, envelope.get, "created_at"),
        microseconds=False,
        check=check,
    )
    updated = _timestamp(
        _cooperative_call(check, envelope.get, "updated_at"),
        microseconds=False,
        check=check,
    )
    body_value = _cooperative_call(check, envelope.get, "body")
    if created != updated or type(body_value) is not str:
        _fail()
    check()
    return envelope, user_dict


def _parse_canonical_comment_body(
    body: str,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> dict[str, object] | None:
    check()
    if not _cooperative_call(check, body.endswith, "\n") or _cooperative_call(
        check,
        body.count,
        "\n",
    ) != 1:
        return None
    try:
        raw = _cooperative_call(
            check,
            lambda value: value[:-1].encode("utf-8", "strict"),
            body,
        )
    except UnicodeError:
        return None
    try:
        value = _json_no_duplicates(raw, check=check)
    except GitHubAuthorityFailure:
        return None
    check()
    canonical = (
        _cooperative_call(check, canonical_json, value) + "\n"
        if type(value) is dict
        else None
    )
    check()
    if type(value) is not dict or canonical != body:
        return None
    check()
    return value  # type: ignore[return-value]


def parse_authority_comments(
    comments: Sequence[object],
    *,
    artifact_components_validator: Callable[[object], object],
    check: Callable[[], int] = _noop_deadline_check,
) -> tuple[tuple[ApprovalComment, ...], Mapping[int, ReviewComment]]:
    check()
    approvals: list[ApprovalComment] = []
    reviews: dict[int, ReviewComment] = {}
    seen_comment_ids: set[int] = set()
    for raw_comment in _cooperative_tuple(comments, check=check):
        check()
        if type(raw_comment) is not dict:
            _fail()
        loose_envelope: dict[str, object] = raw_comment  # type: ignore[assignment]
        loose_comment_id = _positive_int(
            _cooperative_call(check, loose_envelope.get, "id"),
            check=check,
        )
        if loose_comment_id in seen_comment_ids:
            _fail()
        seen_comment_ids.add(loose_comment_id)
        loose_body = _cooperative_call(check, loose_envelope.get, "body")
        if type(loose_body) is not str:
            # GitHub issue-comment envelopes must have a string body, even if
            # the comment is unrelated to V-1B authority.
            _fail()
        body = _parse_canonical_comment_body(loose_body, check=check)
        if body is None:
            if "ATOM-V1B-OPERATIONAL-APPROVAL" in loose_body or "ATOM-V1B-OPERATIONAL-REVIEW" in loose_body:
                _fail()
            continue
        schema = _cooperative_call(check, body.get, "schema_version")
        if schema not in {
            "ATOM-V1B-OPERATIONAL-REVIEW-1",
            "ATOM-V1B-OPERATIONAL-APPROVAL-1",
        }:
            continue
        envelope, user = _comment_envelope(raw_comment, check=check)
        comment_id = _positive_int(envelope["id"], check=check)
        if comment_id != loose_comment_id:
            _fail()
        body_text = envelope["body"]
        assert isinstance(body_text, str)
        canonical_body = _cooperative_call(check, body_text.encode, "utf-8")
        if schema == "ATOM-V1B-OPERATIONAL-REVIEW-1":
            review = _exact_dict(
                body,
                frozenset(
                    {
                        "schema_version",
                        "approval_payload_sha256",
                        "verdict",
                        "material_findings",
                    }
                ),
                check=check,
            )
            _sha256(review["approval_payload_sha256"], check=check)
            _string(review["verdict"], exact="PASS", check=check)
            if type(review["material_findings"]) is not int or review["material_findings"] != 0:
                _fail()
            reviews[comment_id] = ReviewComment(
                comment_id=comment_id,
                author_id=_positive_int(user["id"], check=check),
                author_login=_string(user["login"], check=check),
                created_at=_string(envelope["created_at"], check=check),
                canonical_body=canonical_body,
                approval_payload_sha256=_sha256(
                    review["approval_payload_sha256"], check=check
                ),
            )
        elif schema == "ATOM-V1B-OPERATIONAL-APPROVAL-1":
            # A body by any other user is not authority.  A malformed Owner
            # body, however, fails closed rather than disappearing.
            if user["id"] != GITHUB_OWNER_ID or user["login"] != GITHUB_OWNER_LOGIN:
                continue
            approval = _exact_dict(
                body,
                frozenset(
                    {
                        "schema_version",
                        "payload",
                        "approval_payload_sha256",
                        "independent_review_comment_id",
                        "independent_reviewer_user_id",
                        "independent_reviewer_login",
                    }
                ),
                check=check,
            )
            payload = _validate_payload(
                approval["payload"],
                artifact_components_validator,
                check=check,
            )
            payload_hash = _cooperative_canonical_sha256(payload, check=check)
            if _sha256(
                approval["approval_payload_sha256"], check=check
            ) != payload_hash:
                _fail()
            reviewer_id = _positive_int(
                approval["independent_reviewer_user_id"], check=check
            )
            reviewer_login = _string(
                approval["independent_reviewer_login"], check=check
            )
            if reviewer_id == GITHUB_OWNER_ID or reviewer_login == GITHUB_OWNER_LOGIN:
                _fail()
            window = payload["no_ref_update_window"]
            assert isinstance(window, dict)
            approvals.append(
                ApprovalComment(
                    comment_id=comment_id,
                    created_at=_string(envelope["created_at"], check=check),
                    canonical_body=canonical_body,
                    payload=payload,
                    window=window,
                    review_comment_id=_positive_int(
                        approval["independent_review_comment_id"],
                        check=check,
                    ),
                    reviewer_user_id=reviewer_id,
                    reviewer_login=reviewer_login,
                )
            )
        check()
    check()
    return _cooperative_call(check, tuple, approvals), reviews


def _validate_linked_review(
    approval: ApprovalComment,
    reviews: Mapping[int, ReviewComment],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> ReviewComment:
    check()
    review = reviews.get(approval.review_comment_id)
    if review is None:
        _fail()
    if (
        review.author_id != approval.reviewer_user_id
        or review.author_login != approval.reviewer_login
        or review.author_id == GITHUB_OWNER_ID
        or review.author_login == GITHUB_OWNER_LOGIN
        or review.approval_payload_sha256
        != _cooperative_canonical_sha256(approval.payload, check=check)
        or not review.created_at < approval.created_at
    ):
        _fail()
    check()
    return review


def _normalize_rules(
    rules: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> list[object]:
    check()
    invalid_rules = type(rules) is not list or _cooperative_call(
        check,
        lambda items: any(type(rule) is not dict for rule in items),
        rules,
    )
    if invalid_rules:
        _fail()
    try:
        ordered = _cooperative_call(
            check,
            sorted,
            rules,
            key=lambda rule: _string(rule.get("type"), check=check),  # type: ignore[union-attr]
        )
    except BaseException:
        _fail()
    if _cooperative_call(check, canonical_json, ordered) != _cooperative_call(
        check,
        canonical_json,
        _RULES,
    ):
        _fail()
    check()
    return ordered


def validate_ruleset_projection(
    value: object,
    expected_window: Mapping[str, object],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> Mapping[str, object]:
    check()
    if type(value) is not dict:
        _fail()
    actual: dict[str, object] = value  # type: ignore[assignment]
    required = {
        "id",
        "name",
        "target",
        "source_type",
        "source",
        "enforcement",
        "conditions",
        "rules",
        "created_at",
        "updated_at",
    }
    if not _cooperative_call(check, required.issubset, actual):
        _fail()
    if (
        actual["id"] != expected_window["ruleset_id"]
        or actual["name"] != expected_window["name"]
        or actual["target"] != expected_window["target"]
        or actual["source_type"] != expected_window["source_type"]
        or actual["source"] != expected_window["source"]
        or actual["enforcement"] != expected_window["enforcement"]
        or actual["conditions"] != expected_window["conditions"]
        or actual["created_at"] != expected_window["created_at"]
        or actual["updated_at"] != expected_window["updated_at"]
    ):
        _fail()
    _normalize_rules(actual["rules"], check=check)
    if "bypass_actors" in actual and actual["bypass_actors"] != []:
        _fail()
    check()
    return actual


class ApprovalState(Enum):
    CURRENT = auto()
    HISTORICAL_CLOSED = auto()


@dataclass(frozen=True, slots=True)
class ApprovalFingerprint:
    comment_id: int
    ruleset_id: int
    state: ApprovalState
    approval_body_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovalSelection:
    current: ApprovalComment
    current_review: ReviewComment
    repository_fingerprints: tuple[ApprovalFingerprint, ...]


def classify_v1b_approvals(
    *,
    client: GithubClient,
    context: GithubDeadlineContext,
    approvals: Sequence[ApprovalComment],
    reviews: Mapping[int, ReviewComment],
    expected_execution_sha: str,
    manifest_id: str,
    initial_selection: ApprovalSelection | None = None,
) -> ApprovalSelection:
    """Query every approval's fixed ID before selecting exactly one CURRENT."""

    expected_execution_sha = _sha40(expected_execution_sha)
    if manifest_id not in MANIFEST_IDS:
        _fail()
    checkpoint_check = context.checker(client._seams.monotonic_ns)
    observations: list[tuple[ApprovalComment, int]] = []
    for approval in _cooperative_tuple(approvals, check=checkpoint_check):
        checkpoint_check()
        ruleset_id = _positive_int(
            approval.window["ruleset_id"],
            check=checkpoint_check,
        )
        target = (
            f"{GITHUB_REPOSITORY_PATH}/rulesets/{ruleset_id}?includes_parents=true"
        )
        def validate_ruleset(
            value: object,
            status: int,
            _headers: Mapping[bytes, tuple[bytes, ...]],
            request_check: Callable[[], int],
        ) -> object:
            request_check()
            if status == 200:
                return validate_ruleset_projection(
                    value, approval.window, check=request_check
                )
            if status != 404:
                _fail()
            request_check()
            return value

        response, _value = client.get_json(
            target,
            context=context,
            allowed_statuses=frozenset({200, 404}),
            validator=validate_ruleset,
        )
        _cooperative_call(
            checkpoint_check,
            observations.append,
            (approval, response.status),
        )
        checkpoint_check()  # same checkpoint; no reset

    current_candidates = _cooperative_call(
        checkpoint_check,
        lambda: [
            approval for approval, status in observations if status == 200
        ],
    )
    if len(current_candidates) != 1:
        _fail()
    current = current_candidates[0]
    if current.payload["schema_version"] != OPERATIONAL_APPROVAL_SCHEMA_VERSION:
        _fail()
    current_review = _validate_linked_review(
        current, reviews, check=checkpoint_check
    )
    if (
        current.window["repository"] != GITHUB_REPOSITORY
        or current.window["repository_id"] != GITHUB_REPOSITORY_ID
        or current.payload["provenance"]["execution_source_sha"]  # type: ignore[index]
        != expected_execution_sha
        or current.window["execution_source_sha"] != expected_execution_sha
        or current.window["manifest_id"] != manifest_id
    ):
        _fail()

    fingerprints: list[ApprovalFingerprint] = []
    current_opened = _string(
        current.window["opened_at_utc"],
        check=checkpoint_check,
    )
    seen_ruleset_ids: set[int] = set()
    for approval, status in _cooperative_tuple(
        observations,
        check=checkpoint_check,
    ):
        checkpoint_check()
        ruleset_id = _positive_int(
            approval.window["ruleset_id"],
            check=checkpoint_check,
        )
        if ruleset_id in seen_ruleset_ids:
            _fail()
        seen_ruleset_ids.add(ruleset_id)
        if status == 200:
            state = ApprovalState.CURRENT
        elif status == 404:
            # The current independently reviewed A binds the private complete
            # repository-wide closure chain via control_plane_evidence_sha256.
            # Runtime-visible chronology must independently be unambiguous.
            _validate_linked_review(
                approval, reviews, check=checkpoint_check
            )
            if not (
                _string(
                    approval.window["opened_at_utc"],
                    check=checkpoint_check,
                )
                < current_opened
                and approval.created_at < current.created_at
            ):
                _fail()
            _sha256(
                current.payload["control_plane_evidence_sha256"],
                check=checkpoint_check,
            )
            state = ApprovalState.HISTORICAL_CLOSED
        else:
            _fail()
        _cooperative_call(
            checkpoint_check,
            fingerprints.append,
            ApprovalFingerprint(
                comment_id=approval.comment_id,
                ruleset_id=ruleset_id,
                state=state,
                approval_body_sha256=_cooperative_call(
                    checkpoint_check,
                    lambda: approval.body_sha256,
                ),
            ),
        )
    ordered_fingerprints = _cooperative_call(
        checkpoint_check,
        sorted,
        fingerprints,
        key=lambda item: item.comment_id,
    )
    selection = _cooperative_call(
        checkpoint_check,
        ApprovalSelection,
        current=current,
        current_review=current_review,
        repository_fingerprints=_cooperative_call(
            checkpoint_check,
            tuple,
            ordered_fingerprints,
        ),
    )
    if initial_selection is not None:
        checkpoint_check()
        if (
            selection.current.comment_id != initial_selection.current.comment_id
            or selection.current.body_sha256 != initial_selection.current.body_sha256
            or _checked_sha256_bytes(
                selection.current_review.canonical_body,
                check=checkpoint_check,
            )
            != _checked_sha256_bytes(
                initial_selection.current_review.canonical_body,
                check=checkpoint_check,
            )
            or selection.repository_fingerprints
            != initial_selection.repository_fingerprints
        ):
            _fail()
    checkpoint_check()
    return selection


def validate_repository_metadata(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> Mapping[str, object]:
    check()
    if type(value) is not dict:
        _fail()
    repo: dict[str, object] = value  # type: ignore[assignment]
    owner = _cooperative_call(check, repo.get, "owner")
    if type(owner) is not dict:
        _fail()
    matches = _cooperative_call(
        check,
        lambda: (
            repo.get("id") == GITHUB_REPOSITORY_ID
            and repo.get("full_name") == GITHUB_REPOSITORY
            and repo.get("default_branch") == "main"
            and repo.get("private") is False
            and owner.get("login") == GITHUB_OWNER_LOGIN
        ),
    )
    if not matches:
        _fail()
    check()
    return repo


def validate_main_ref(
    value: object,
    expected_sha: str,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> Mapping[str, object]:
    check()
    expected_sha = _sha40(expected_sha, check=check)
    if type(value) is not dict:
        _fail()
    ref: dict[str, object] = value  # type: ignore[assignment]
    obj = _cooperative_call(check, ref.get, "object")
    if type(obj) is not dict:
        _fail()
    matches = _cooperative_call(
        check,
        lambda: (
            ref.get("ref") == "refs/heads/main"
            and obj.get("type") == "commit"
            and obj.get("sha") == expected_sha
        ),
    )
    if not matches:
        _fail()
    check()
    return ref


@dataclass(frozen=True, slots=True)
class GithubAuthoritySnapshot:
    selection: ApprovalSelection


def verify_github_checkpoint(
    *,
    client: GithubClient,
    expected_execution_sha: str,
    manifest_id: str,
    artifact_components_validator: Callable[[object], object],
    immutable_fact_validator: Callable[
        [GithubClient, GithubDeadlineContext, str], None
    ],
    initial_selection: ApprovalSelection | None = None,
    local_tls_trust: Mapping[str, object] | None = None,
    preflight: Callable[[GithubDeadlineContext], None] | None = None,
    finalizer: Callable[[ApprovalSelection, GithubDeadlineContext], None]
    | None = None,
) -> GithubAuthoritySnapshot:
    """Coherent repo/ref/ruleset bracket with no movement reread/retry.

    ``immutable_fact_validator`` performs the already-existing exact
    commit/PR/signature/tree/blob/receipt reads using this same client and
    deadline context.  It must never substitute a mutable ref for an immutable
    object ID and must raise immediately on a mixed observation.
    """

    sha = _sha40(expected_execution_sha)
    context = GithubDeadlineContext.begin_checkpoint(client._seams.monotonic_ns)
    if preflight is not None:
        try:
            preflight(context)
        except GitHubAuthorityFailure:
            raise
        except BaseException:
            _fail()
        context.check(client._seams.monotonic_ns)
    def validate_repository(
        value: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        if status != 200:
            _fail()
        return validate_repository_metadata(value, check=request_check)

    def validate_ref(
        value: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        if status != 200:
            _fail()
        return validate_main_ref(value, sha, check=request_check)

    def validate_comment_page(
        comments: object,
        request_check: Callable[[], int],
    ) -> Sequence[object]:
        request_check()
        if type(comments) is not list:
            _fail()
        approvals, reviews = parse_authority_comments(
            comments,
            artifact_components_validator=artifact_components_validator,
            check=request_check,
        )
        request_check()
        return (*approvals, *reviews.values())

    def validate_comment_collection(
        parsed_comments: tuple[object, ...],
        paged: GithubDeadlineContext,
    ) -> object:
        paged_check = paged.checker(client._seams.monotonic_ns)
        approvals: list[ApprovalComment] = []
        reviews: dict[int, ReviewComment] = {}
        seen_comment_ids: set[int] = set()
        for parsed in parsed_comments:
            paged_check()
            if isinstance(parsed, ApprovalComment):
                comment_id = parsed.comment_id
                approvals.append(parsed)
            elif isinstance(parsed, ReviewComment):
                comment_id = parsed.comment_id
                reviews[comment_id] = parsed
            else:
                _fail()
            if comment_id in seen_comment_ids:
                _fail()
            seen_comment_ids.add(comment_id)
        paged_check()
        return classify_v1b_approvals(
            client=client,
            context=paged,
            approvals=approvals,
            reviews=reviews,
            expected_execution_sha=sha,
            manifest_id=manifest_id,
            initial_selection=initial_selection,
        )

    selection = client.get_paginated_json(
        GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH,
        context=context,
        page_validator=validate_comment_page,
        collection_validator=validate_comment_collection,
    )
    if not isinstance(selection, ApprovalSelection):
        _fail()
    if local_tls_trust is not None:
        checkpoint_check = context.checker(client._seams.monotonic_ns)
        provenance = _cooperative_call(
            checkpoint_check,
            selection.current.payload.__getitem__,
            "provenance",
        )
        if type(provenance) is not dict:
            _fail()
        approved_trust = _cooperative_call(
            checkpoint_check,
            provenance.get,
            "github_tls_trust",
        )
        local_trust_copy = _cooperative_call(
            checkpoint_check,
            dict,
            local_tls_trust,
        )
        if type(approved_trust) is not dict or _cooperative_call(
            checkpoint_check,
            lambda: local_trust_copy == approved_trust,
        ) is not True:
            _fail()
    context.check(client._seams.monotonic_ns)

    # The approval discussion is deliberately the first logical authority
    # endpoint.  Only its complete validation and local trust correlation may
    # authorize proceeding to repository/ref or any other GitHub endpoint.
    client.get_json(
        GITHUB_REPOSITORY_PATH,
        context=context,
        validator=validate_repository,
    )
    client.get_json(
        GITHUB_MAIN_REF_PATH,
        context=context,
        validator=validate_ref,
    )

    ruleset_id = _positive_int(selection.current.window["ruleset_id"])
    ruleset_path = (
        f"{GITHUB_REPOSITORY_PATH}/rulesets/{ruleset_id}?includes_parents=true"
    )
    def validate_current_ruleset(
        value: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        if status != 200:
            _fail()
        return validate_ruleset_projection(
            value, selection.current.window, check=request_check
        )

    client.get_json(
        ruleset_path,
        context=context,
        validator=validate_current_ruleset,
    )

    try:
        immutable_fact_validator(client, context, sha)
    except GitHubAuthorityFailure:
        raise
    except BaseException:
        _fail()
    context.check(client._seams.monotonic_ns)

    client.get_json(
        ruleset_path,
        context=context,
        validator=validate_current_ruleset,
    )
    client.get_json(
        GITHUB_MAIN_REF_PATH,
        context=context,
        validator=validate_ref,
    )
    context.check(client._seams.monotonic_ns)
    if finalizer is not None:
        # The final invocation checkpoint uses this hook for the last runtime
        # byte/mapping/dispatch measurement.  It is deliberately inside the
        # coherent GitHub checkpoint, after the closing ruleset/ref bracket;
        # only deadline accounting and in-memory return construction follow.
        finalizer(selection, context)
        context.check(client._seams.monotonic_ns)
    return GithubAuthoritySnapshot(selection=selection)


class AuthorityStage(Enum):
    NEW_SEAL_BEFORE_EVIDENCE = auto()
    NEW_SEAL_AFTER_EVIDENCE_BEFORE_SEAL = auto()
    SEALED_OR_ACCEPTED_RECOVERY_BEFORE_COMPLETE_CELLS = auto()
    FINAL_AFTER_COMPLETE_TRUTHFUL_CELLS = auto()


def route_authority_failure(stage: AuthorityStage) -> str:
    """Test seam only; integration must call existing exact receipt builders."""

    if stage is AuthorityStage.NEW_SEAL_BEFORE_EVIDENCE:
        return "BLOCKED"
    if stage is AuthorityStage.NEW_SEAL_AFTER_EVIDENCE_BEFORE_SEAL:
        return "PRE-CELL INVALID (null seal)"
    if stage is AuthorityStage.SEALED_OR_ACCEPTED_RECOVERY_BEFORE_COMPLETE_CELLS:
        return "PRE-CELL INVALID (consuming)"
    if stage is AuthorityStage.FINAL_AFTER_COMPLETE_TRUTHFUL_CELLS:
        return "POST-EVALUATION AUTHORITY INVALID"
    _fail()

TLS_QUERY_VALUES = MappingProxyType(
    {
        "sslmode": "verify-full",
        "sslrootcert": CA_REPOSITORY_PATH,
        "sslcertmode": "disable",
        "require_auth": "scram-sha-256",
        "gssencmode": "disable",
    }
)
TLS_QUERY_KEYS = frozenset(TLS_QUERY_VALUES)
CONNINFO_INPUT_KEYS = frozenset(
    {
        "user",
        "password",
        "host",
        "port",
        "dbname",
        *TLS_QUERY_KEYS,
    }
)

ALTERNATE_PARAMETER_ENV = frozenset(
    {
        "PGUSER",
        "PGPASSWORD",
        "PGPASSFILE",
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGOPTIONS",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGSSLCERTMODE",
        "PGREQUIREAUTH",
        "PGGSSENCMODE",
        "PGSSLCERT",
        "PGSSLKEY",
        "PGSSLKEYLOGFILE",
        "PGSSLCRL",
        "PGSSLCRLDIR",
        "PGSSLNEGOTIATION",
        "PGREQUIRESSL",
        "PGCHANNELBINDING",
        "PGSSL_MIN_PROTOCOL_VERSION",
        "PGSSL_MAX_PROTOCOL_VERSION",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)

PROOF_BATCH_SIZE = 65_536
PROOF_METHOD = "POST_COMMIT_DB_OBSERVATION_V1"
FAMILY_FORECAST_KIND = "VOLATILITY_FORECAST"
FAMILY_OUTCOME_KIND = "VOLATILITY_OUTCOME"


class DatabaseFailureRoute(str, Enum):
    """The only receipt route a database-layer defect may select."""

    BLOCKED = "BLOCKED"
    PRE_CELL_INVALID = "PRE_CELL_INVALID"
    POST_EVALUATION_AUTHORITY_INVALID = "POST_EVALUATION_AUTHORITY_INVALID"


class DatabaseFailureStage(str, Enum):
    """Explicit caller-owned stage; no exception text is used to infer it."""

    NEW_BEFORE_EVIDENCE = "NEW_BEFORE_EVIDENCE"
    NEW_AFTER_EVIDENCE_BEFORE_SEAL = "NEW_AFTER_EVIDENCE_BEFORE_SEAL"
    SEALED_OR_RECOVERY = "SEALED_OR_RECOVERY"
    FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS = "FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS"


class DatabaseDefect(str, Enum):
    URI_INVALID = "DATABASE_URI_INVALID"
    AMBIENT_SOURCE = "DATABASE_AMBIENT_SOURCE_PRESENT"
    PINNED_CA = "PINNED_CA_INVALID"
    CONNECTION = "DATABASE_CONNECTION_FAILED"
    CONNINFO = "DATABASE_EFFECTIVE_CONNINFO_INVALID"
    SNAPSHOT = "DATABASE_SNAPSHOT_INVALID"
    AUTHORITY = "DATABASE_AUTHORITY_PROOF_FAILED"
    POPULATION = "DATABASE_EVIDENCE_POPULATION_INVALID"


def route_for_database_stage(stage: DatabaseFailureStage) -> DatabaseFailureRoute:
    if stage is DatabaseFailureStage.NEW_BEFORE_EVIDENCE:
        return DatabaseFailureRoute.BLOCKED
    if stage in {
        DatabaseFailureStage.NEW_AFTER_EVIDENCE_BEFORE_SEAL,
        DatabaseFailureStage.SEALED_OR_RECOVERY,
    }:
        return DatabaseFailureRoute.PRE_CELL_INVALID
    if stage is DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS:
        return DatabaseFailureRoute.POST_EVALUATION_AUTHORITY_INVALID
    raise TypeError("unknown database failure stage")


class DatabaseContractError(RuntimeError):
    """Safe failure carrying no URI, password, SQL parameter, or exception cause."""

    def __init__(self, stage: DatabaseFailureStage, defect: DatabaseDefect) -> None:
        self.stage = stage
        self.route = route_for_database_stage(stage)
        self.defect = defect
        super().__init__(f"{self.route.value}:{self.defect.value}")


def _database_fail(stage: DatabaseFailureStage, defect: DatabaseDefect) -> NoReturn:
    raise DatabaseContractError(stage, defect) from None


@dataclass(frozen=True, slots=True)
class ParsedDatabaseURI:
    """A validated URI whose secret-bearing original is never represented."""

    _original_uri: str = field(repr=False, compare=False)
    user: str = READER_ROLE
    host: str = DIRECT_HOST
    port: int = DIRECT_PORT
    dbname: str = DATABASE_NAME
    sslmode: str = TLS_QUERY_VALUES["sslmode"]
    sslrootcert: str = TLS_QUERY_VALUES["sslrootcert"]
    sslcertmode: str = TLS_QUERY_VALUES["sslcertmode"]
    require_auth: str = TLS_QUERY_VALUES["require_auth"]
    gssencmode: str = TLS_QUERY_VALUES["gssencmode"]
    password_present: bool = True
    password_fallbacks_absent: bool = True
    tls_fallbacks_absent: bool = True
    identity_overrides_absent: bool = True

    def _uri_for_single_connect(self) -> str:
        return self._original_uri


@dataclass(frozen=True, slots=True)
class GitBlobObservation:
    mode: str
    blob_sha1: str
    content: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class PinnedCAObservation:
    repository_path: str
    size_bytes: int
    sha256: str
    git_blob_sha1: str


def _strict_percent_decode(raw: str) -> str:
    """Decode percent escapes once, without form-style ``+`` conversion."""

    encoded = bytearray()
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "%":
            if index + 2 >= len(raw) or not re.fullmatch(
                r"[0-9A-Fa-f]{2}", raw[index + 1 : index + 3]
            ):
                raise ValueError("invalid percent escape")
            encoded.append(int(raw[index + 1 : index + 3], 16))
            index += 3
            continue
        encoded.extend(char.encode("utf-8", "strict"))
        index += 1
    return bytes(encoded).decode("utf-8", "strict")


def _probe_default_files(home_dir: Path) -> bool:
    """Return true when a forbidden default credential/certificate file exists."""

    pgpass = home_dir / ".pgpass"
    cert = home_dir / ".postgresql" / "postgresql.crt"
    key = home_dir / ".postgresql" / "postgresql.key"
    return (
        os.access(pgpass, os.R_OK)
        or os.path.lexists(cert)
        or os.path.lexists(key)
    )


def validate_database_environment(
    environ: Mapping[str, str],
    *,
    conninfo_parser: Callable[[str], Mapping[str, object]],
    home_dir: Path,
    stage: DatabaseFailureStage = DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
) -> ParsedDatabaseURI:
    """Read and validate the sole authorized URI environment value.

    ``conninfo_parser`` must be the already imported pinned
    ``psycopg.conninfo.conninfo_to_dict`` in production.  It is injected so
    tests can prove that the untouched original URI is independently parsed
    without importing psycopg or making a connection.
    """

    uri = environ.get(READONLY_URL_ENV)
    if not isinstance(uri, str) or not uri:
        _database_fail(stage, DatabaseDefect.URI_INVALID)
    for key in ALTERNATE_PARAMETER_ENV:
        value = environ.get(key)
        if value is not None and (not isinstance(value, str) or value != ""):
            _database_fail(stage, DatabaseDefect.AMBIENT_SOURCE)
    try:
        forbidden_file = _probe_default_files(Path(home_dir))
    except Exception:
        _database_fail(stage, DatabaseDefect.AMBIENT_SOURCE)
    if forbidden_file:
        _database_fail(stage, DatabaseDefect.AMBIENT_SOURCE)
    return validate_database_uri(
        uri,
        environ=environ,
        conninfo_parser=conninfo_parser,
        stage=stage,
        _default_files_verified=True,
    )


def validate_database_uri(
    uri: str,
    *,
    environ: Mapping[str, str],
    conninfo_parser: Callable[[str], Mapping[str, object]],
    stage: DatabaseFailureStage = DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
    _default_files_verified: bool = False,
) -> ParsedDatabaseURI:
    """Perform the independent raw and libpq URI parsers before connection."""

    try:
        if not isinstance(uri, str) or not uri.startswith("postgresql://"):
            raise ValueError("not the exact PostgreSQL URI form")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in uri):
            raise ValueError("raw control byte")
        remainder = uri[len("postgresql://") :]
        if remainder.count("?") != 1 or "#" in remainder:
            raise ValueError("ambiguous URI boundary")
        target, raw_query = remainder.split("?", 1)
        if target.count("/") != 1:
            raise ValueError("ambiguous database path")
        raw_authority, raw_dbname = target.split("/", 1)
        if raw_dbname != DATABASE_NAME or raw_authority.count("@") != 1:
            raise ValueError("wrong database or userinfo")
        raw_userinfo, raw_hostport = raw_authority.split("@", 1)
        if raw_userinfo.count(":") != 1 or raw_hostport.count(":") != 1:
            raise ValueError("ambiguous userinfo or host")
        raw_user, raw_password = raw_userinfo.split(":", 1)
        raw_host, raw_port = raw_hostport.split(":", 1)
        user = _strict_percent_decode(raw_user)
        password = _strict_percent_decode(raw_password)
        if (
            raw_user != READER_ROLE
            or user != READER_ROLE
            or not password
            or raw_host != DIRECT_HOST
            or raw_port != str(DIRECT_PORT)
        ):
            raise ValueError("wrong direct target")

        raw_pairs = raw_query.split("&")
        if len(raw_pairs) != len(TLS_QUERY_KEYS) or any(not item for item in raw_pairs):
            raise ValueError("wrong query cardinality")
        query: dict[str, str] = {}
        for raw_pair in raw_pairs:
            if raw_pair.count("=") != 1:
                raise ValueError("ambiguous query pair")
            raw_key, raw_value = raw_pair.split("=", 1)
            if (
                not raw_key.isascii()
                or raw_key.lower() != raw_key
                or _strict_percent_decode(raw_key) != raw_key
                or raw_key not in TLS_QUERY_KEYS
                or raw_key in query
            ):
                raise ValueError("noncanonical or duplicate query key")
            query[raw_key] = _strict_percent_decode(raw_value)
        if query != dict(TLS_QUERY_VALUES):
            raise ValueError("wrong TLS/authentication tuple")

        # The production parser is called exactly once with the untouched URI.
        parsed = conninfo_parser(uri)
        if not isinstance(parsed, Mapping) or set(parsed) != CONNINFO_INPUT_KEYS:
            raise ValueError("libpq input key mismatch")
        expected = {
            "user": READER_ROLE,
            "host": DIRECT_HOST,
            "port": str(DIRECT_PORT),
            "dbname": DATABASE_NAME,
            **dict(TLS_QUERY_VALUES),
        }
        for key, expected_value in expected.items():
            if not isinstance(parsed.get(key), str) or parsed[key] != expected_value:
                raise ValueError("libpq target mismatch")
        parsed_password = parsed.get("password")
        if not isinstance(parsed_password, str) or not parsed_password:
            raise ValueError("libpq password source missing")
        if not hmac.compare_digest(parsed_password.encode(), password.encode()):
            raise ValueError("raw/libpq password decoding mismatch")

        # Recheck alternate sources here so direct callers cannot bypass the
        # environment wrapper.  Empty strings are not effective alternatives.
        for key in ALTERNATE_PARAMETER_ENV:
            value = environ.get(key)
            if value is not None and (not isinstance(value, str) or value != ""):
                _database_fail(stage, DatabaseDefect.AMBIENT_SOURCE)
    except DatabaseContractError:
        raise
    except Exception:
        _database_fail(stage, DatabaseDefect.URI_INVALID)

    return ParsedDatabaseURI(
        uri,
        password_fallbacks_absent=_default_files_verified,
        tls_fallbacks_absent=_default_files_verified,
    )


def verify_pinned_ca(
    repository_root: Path,
    *,
    git_blob_reader: Callable[[str], GitBlobObservation],
    cwd: Path | None = None,
    stage: DatabaseFailureStage = DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
    check: Callable[[], object] | None = None,
) -> PinnedCAObservation:
    """Verify exact tracked CA bytes without following a path component symlink."""

    fd: int | None = None
    try:
        root = _cooperative_call(check, Path, repository_root)
        actual_cwd = (
            _cooperative_call(check, Path.cwd)
            if cwd is None
            else _cooperative_call(check, Path, cwd)
        )
        if not root.is_absolute() or not actual_cwd.is_absolute():
            raise ValueError("root/cwd not absolute")
        resolved_root = _cooperative_call(check, root.resolve, strict=True)
        resolved_cwd = _cooperative_call(check, actual_cwd.resolve, strict=True)
        if resolved_root != root or resolved_cwd != root:
            raise ValueError("wrong repository root")
        certs = _cooperative_call(check, root.__truediv__, "certs")
        path = _cooperative_call(check, root.__truediv__, CA_REPOSITORY_PATH)
        certs_stat = _cooperative_call(check, os.lstat, certs)
        path_stat = _cooperative_call(check, os.lstat, path)
        if not stat.S_ISDIR(certs_stat.st_mode) or stat.S_ISLNK(certs_stat.st_mode):
            raise ValueError("certs is not a real directory")
        if not stat.S_ISREG(path_stat.st_mode) or stat.S_ISLNK(path_stat.st_mode):
            raise ValueError("CA is not a real regular file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = _cooperative_acquire(check, os.open, os.close, path, flags)
        opened = _cooperative_call(check, os.fstat, fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != path_stat.st_dev
            or opened.st_ino != path_stat.st_ino
        ):
            raise ValueError("CA changed while opening")
        chunks: list[bytes] = []
        while True:
            chunk = _cooperative_call(
                check,
                os.read,
                fd,
                min(16_384, GITHUB_DEADLINE_WORK_CHUNK_BYTES),
            )
            if not chunk:
                break
            _cooperative_call(check, chunks.append, chunk)
        content = _cooperative_call(check, b"".join, chunks)
        digest = _checked_sha256_bytes(content, check=check)
        if len(content) != CA_SIZE_BYTES or digest != CA_SHA256:
            raise ValueError("CA byte mismatch")
        tracked = _cooperative_call(check, git_blob_reader, CA_REPOSITORY_PATH)
        if (
            not isinstance(tracked, GitBlobObservation)
            or tracked.mode != "100644"
            or tracked.blob_sha1 != CA_GIT_BLOB_SHA1
            or tracked.content != content
        ):
            raise ValueError("tracked CA mismatch")
    except Exception:
        _database_fail(stage, DatabaseDefect.PINNED_CA)
    finally:
        if fd is not None:
            os.close(fd)
    return PinnedCAObservation(
        CA_REPOSITORY_PATH, CA_SIZE_BYTES, CA_SHA256, CA_GIT_BLOB_SHA1
    )


def _decode_ascii(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", "strict")
    if isinstance(value, str) and value.isascii():
        return value
    raise ValueError("not ASCII")


def verify_postconnect_conninfo(
    connection: object,
    parsed: ParsedDatabaseURI,
    *,
    stage: DatabaseFailureStage,
) -> None:
    """Verify raw ``PQconninfo(PGconn*)`` options, including default-valued inputs."""

    try:
        options = getattr(getattr(connection, "pgconn"), "info")
        indexed: dict[str, object] = {}
        for option in options:
            keyword = _decode_ascii(getattr(option, "keyword"))
            if keyword in indexed:
                raise ValueError("duplicate PQconninfo keyword")
            indexed[keyword] = getattr(option, "val")
        for key in CONNINFO_INPUT_KEYS:
            if key not in indexed or indexed[key] is None:
                raise ValueError("missing effective option")
        expected = {
            "host": parsed.host,
            "port": str(parsed.port),
            "dbname": parsed.dbname,
            "user": parsed.user,
            "sslmode": parsed.sslmode,
            "sslrootcert": parsed.sslrootcert,
            "sslcertmode": parsed.sslcertmode,
            "require_auth": parsed.require_auth,
            "gssencmode": parsed.gssencmode,
        }
        for key, value in expected.items():
            if _decode_ascii(indexed[key]) != value:
                raise ValueError("effective option mismatch")
        # The password is deliberately neither decoded nor compared/rendered.
        info = getattr(connection, "info")
        if (
            getattr(info, "host") != parsed.host
            or int(getattr(info, "port")) != parsed.port
            or getattr(info, "dbname") != parsed.dbname
            or getattr(info, "user") != parsed.user
        ):
            raise ValueError("Connection.info mismatch")
    except DatabaseContractError:
        raise
    except Exception:
        _database_fail(stage, DatabaseDefect.CONNINFO)


# ---------------------------------------------------------------------------
# Exact read-only snapshot and §13.3/§15.3 authority proof
# ---------------------------------------------------------------------------

SCAN_STARTED_SQL = "SELECT pg_catalog.transaction_timestamp()"
SHOW_TRANSACTION_ISOLATION_SQL = "SHOW transaction_isolation"
SHOW_TRANSACTION_READ_ONLY_SQL = "SHOW transaction_read_only"

AUTHORITY_CORE_SQL = """
SELECT current_user::text,
       session_user::text,
       current_database()::text,
       pg_catalog.pg_get_userbyid(d.datdba)::text AS database_owner,
       pg_catalog.has_database_privilege(
           current_user, current_database(), 'CREATE') AS database_create,
       pg_catalog.has_database_privilege(
           current_user, current_database(), 'TEMPORARY') AS database_temporary,
       EXISTS (
           SELECT 1
           FROM pg_catalog.aclexplode(
               COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) AS a
           WHERE a.grantee = 0
             AND a.privilege_type = 'TEMPORARY'
       ) AS public_temporary_acl,
       EXISTS (
           SELECT 1
           FROM pg_catalog.aclexplode(
               COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) AS a
           JOIN pg_catalog.pg_roles AS direct_reader ON direct_reader.oid = a.grantee
           WHERE direct_reader.rolname = 'atom_e1_scorecard_reader'
             AND a.privilege_type = 'TEMPORARY'
       ) AS direct_reader_temporary_acl,
       pg_catalog.pg_my_temp_schema() AS session_temp_schema_oid,
       (SELECT s.ssl
          FROM pg_catalog.pg_stat_ssl AS s
         WHERE s.pid = pg_catalog.pg_backend_pid()) AS tls_active,
       pg_catalog.has_schema_privilege(
           current_user, 'public', 'USAGE') AS schema_public_usage,
       pg_catalog.has_schema_privilege(
           current_user, 'public', 'CREATE') AS schema_public_create,
       pg_catalog.has_schema_privilege(
           current_user, 'atom_v9_internal', 'USAGE')
           AS schema_atom_v9_internal_usage
FROM pg_catalog.pg_database AS d
WHERE d.datname = current_database()
"""

AUTHORITY_ROLE_SQL = """
SELECT r.oid,
       r.rolcanlogin,
       r.rolinherit,
       r.rolsuper,
       r.rolcreatedb,
       r.rolcreaterole,
       r.rolreplication,
       r.rolbypassrls
FROM pg_catalog.pg_roles AS r
WHERE r.rolname = 'atom_e1_scorecard_reader'
"""

AUTHORITY_MEMBERSHIPS_SQL = """
SELECT granted.rolname::text
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member ON member.oid = m.member
JOIN pg_catalog.pg_roles AS granted ON granted.oid = m.roleid
WHERE member.rolname = 'atom_e1_scorecard_reader'
ORDER BY pg_catalog.convert_to(granted.rolname::text, 'UTF8')
"""

AUTHORITY_SCHEMA_CREATE_COUNT_SQL = """
SELECT pg_catalog.count(*)::bigint
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname <> 'pg_catalog'
  AND n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
  AND pg_catalog.has_schema_privilege(current_user, n.oid, 'CREATE')
"""

AUTHORITY_RELATION_WRITE_COUNT_SQL = """
SELECT pg_catalog.count(*)::bigint
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
CROSS JOIN unnest(ARRAY['INSERT','UPDATE','DELETE','TRUNCATE']::text[])
    AS requested(privilege)
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname <> 'pg_catalog'
  AND n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
  AND pg_catalog.has_table_privilege(
      current_user, c.oid, requested.privilege)
"""

AUTHORITY_TABLES_SQL = """
WITH wanted(table_order, qualified) AS (
    VALUES
      (1, 'public.forecasts'),
      (2, 'public.forecast_outcomes'),
      (3, 'public.atom_v9_v4_forecasts'),
      (4, 'public.atom_v9_v4_outcomes'),
      (5, 'public.volatility_forecasts'),
      (6, 'public.volatility_forecast_outcomes')
)
SELECT w.qualified,
       c.oid,
       c.relrowsecurity,
       pg_catalog.has_table_privilege(current_user, c.oid, 'SELECT'),
       pg_catalog.has_table_privilege(current_user, c.oid, 'INSERT'),
       pg_catalog.has_table_privilege(current_user, c.oid, 'UPDATE'),
       pg_catalog.has_table_privilege(current_user, c.oid, 'DELETE'),
       pg_catalog.has_table_privilege(current_user, c.oid, 'TRUNCATE'),
       EXISTS (
           SELECT 1
           FROM pg_catalog.pg_policy AS p
           WHERE p.polrelid = c.oid
             AND p.polcmd IN ('r', '*')
             AND p.polpermissive
             AND (p.polqual IS NULL OR
                  pg_catalog.pg_get_expr(p.polqual, p.polrelid, false) = 'true')
             AND EXISTS (
                 SELECT 1
                 FROM unnest(p.polroles) AS policy_role(role_oid)
                 WHERE policy_role.role_oid = 0
                    OR pg_catalog.pg_has_role(
                        current_user, policy_role.role_oid, 'MEMBER')
             )
       ) AS permissive_full_read,
       EXISTS (
           SELECT 1
           FROM pg_catalog.pg_policy AS p
           WHERE p.polrelid = c.oid
             AND p.polcmd IN ('r', '*')
             AND NOT p.polpermissive
             AND EXISTS (
                 SELECT 1
                 FROM unnest(p.polroles) AS policy_role(role_oid)
                 WHERE policy_role.role_oid = 0
                    OR pg_catalog.pg_has_role(
                        current_user, policy_role.role_oid, 'MEMBER')
             )
       ) AS restrictive_select
FROM wanted AS w
LEFT JOIN pg_catalog.pg_class AS c
       ON c.oid = pg_catalog.to_regclass(w.qualified)
ORDER BY w.table_order
"""

AUTHORITY_FUNCTIONS_SQL = """
WITH wanted(function_order, signature) AS (
    VALUES
      (1, 'atom_v9_internal.read_forecast_commit_proof(text)'),
      (2, 'atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])')
)
SELECT w.signature,
       p.oid,
       pg_catalog.pg_get_userbyid(p.proowner)::text AS owner,
       l.lanname::text AS language,
       p.prokind::text,
       p.prosecdef,
       p.proleakproof,
       p.proisstrict,
       p.provolatile::text,
       p.proparallel::text,
       CASE WHEN p.prorows = pg_catalog.trunc(p.prorows)
            THEN p.prorows::bigint ELSE NULL END AS prorows,
       p.proconfig,
       pg_catalog.pg_get_functiondef(p.oid) AS definition,
       pg_catalog.has_function_privilege(current_user, p.oid, 'EXECUTE')
FROM wanted AS w
LEFT JOIN pg_catalog.pg_proc AS p
       ON p.oid = pg_catalog.to_regprocedure(w.signature)
LEFT JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang
ORDER BY w.function_order
"""

AUTHORITY_OTHER_SECURITY_DEFINER_COUNT_SQL = """
SELECT pg_catalog.count(*)::bigint
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname <> 'pg_catalog'
  AND n.nspname <> 'information_schema'
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
  AND NOT (p.oid = ANY(%(approved_oids)s::oid[]))
  AND pg_catalog.has_function_privilege(current_user, p.oid, 'EXECUTE')
"""


def _rows(cursor: object, sql: str, params: object | None = None) -> tuple[tuple[Any, ...], ...]:
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)
    result = cursor.fetchall()
    if not isinstance(result, Sequence):
        result = tuple(result)
    rows: list[tuple[Any, ...]] = []
    for row in result:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise ValueError("database row is not positional")
        rows.append(tuple(row))
    return tuple(rows)


def _one(cursor: object, sql: str, params: object | None = None) -> tuple[Any, ...]:
    rows = _rows(cursor, sql, params)
    if len(rows) != 1:
        raise ValueError("expected exactly one row")
    return rows[0]


def _exact_int(value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("not exact integer")
    return value


def _exact_bool(value: object) -> bool:
    if value is not True and value is not False:
        raise ValueError("not exact boolean")
    return bool(value)


def _finite_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("not a binary64 input")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("non-finite structural value")
    return converted


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp is not timezone-aware")
    converted = value.astimezone(timezone.utc)
    if converted.utcoffset() is None:
        raise ValueError("timestamp has no UTC offset")
    return converted


def _scalar_int(cursor: object, sql: str, params: object | None = None) -> int:
    row = _one(cursor, sql, params)
    if len(row) != 1:
        raise ValueError("wrong scalar shape")
    return _exact_int(row[0])


def authority_check(
    cursor: object,
    parsed: ParsedDatabaseURI,
    ca: PinnedCAObservation,
    *,
    stage: DatabaseFailureStage,
) -> dict[str, object]:
    """Construct and validate the exact amended V-1A §13.3 proof object."""

    try:
        if (
            parsed.password_present is not True
            or parsed.password_fallbacks_absent is not True
            or parsed.tls_fallbacks_absent is not True
            or parsed.identity_overrides_absent is not True
        ):
            raise ValueError("pre-connect source proof incomplete")
        core = _one(cursor, AUTHORITY_CORE_SQL)
        if len(core) != 13:
            raise ValueError("wrong core authority shape")
        (
            current_user,
            session_user,
            current_database,
            database_owner,
            database_create,
            database_temporary,
            public_temporary_acl,
            direct_reader_temporary_acl,
            session_temp_schema_oid,
            tls_active,
            schema_public_usage,
            schema_public_create,
            schema_atom_v9_internal_usage,
        ) = core
        if (
            current_user != READER_ROLE
            or session_user != READER_ROLE
            or current_database != DATABASE_NAME
            or not isinstance(database_owner, str)
            or not database_owner
            or database_owner == READER_ROLE
            or _exact_bool(database_create)
            or not _exact_bool(database_temporary)
            or not _exact_bool(public_temporary_acl)
            or _exact_bool(direct_reader_temporary_acl)
            or _exact_int(session_temp_schema_oid) != 0
            or not _exact_bool(tls_active)
            or not _exact_bool(schema_public_usage)
            or _exact_bool(schema_public_create)
            or not _exact_bool(schema_atom_v9_internal_usage)
        ):
            raise ValueError("core authority mismatch")

        role = _one(cursor, AUTHORITY_ROLE_SQL)
        if len(role) != 8:
            raise ValueError("wrong reader role shape")
        role_oid = _exact_int(role[0], minimum=1)
        role_values = tuple(_exact_bool(value) for value in role[1:])
        expected_role_values = (True, False, False, False, False, False, False)
        if role_values != expected_role_values:
            raise ValueError("reader role attributes changed")
        reader_role_attributes = dict(
            zip(
                (
                    "rolcanlogin",
                    "rolinherit",
                    "rolsuper",
                    "rolcreatedb",
                    "rolcreaterole",
                    "rolreplication",
                    "rolbypassrls",
                ),
                role_values,
                strict=True,
            )
        )

        membership_rows = _rows(cursor, AUTHORITY_MEMBERSHIPS_SQL)
        memberships: list[str] = []
        for membership in membership_rows:
            if len(membership) != 1 or not isinstance(membership[0], str):
                raise ValueError("wrong membership shape")
            memberships.append(membership[0])
        if memberships or memberships != sorted(memberships, key=lambda value: value.encode("utf-8")):
            raise ValueError("reader role membership present")

        schema_create_count = _scalar_int(cursor, AUTHORITY_SCHEMA_CREATE_COUNT_SQL)
        relation_write_count = _scalar_int(cursor, AUTHORITY_RELATION_WRITE_COUNT_SQL)
        if schema_create_count != 0 or relation_write_count != 0:
            raise ValueError("catalog-wide create/write privilege present")

        table_rows = _rows(cursor, AUTHORITY_TABLES_SQL)
        if len(table_rows) != len(SIX_TABLES):
            raise ValueError("wrong six-table row count")
        six_select: dict[str, bool] = {}
        six_insert: dict[str, bool] = {}
        six_update: dict[str, bool] = {}
        six_delete: dict[str, bool] = {}
        six_truncate: dict[str, bool] = {}
        six_rls: dict[str, bool] = {}
        six_permissive: dict[str, bool] = {}
        six_restrictive: dict[str, bool] = {}
        for expected_table, row in zip(SIX_TABLES, table_rows, strict=True):
            if len(row) != 10 or row[0] != expected_table:
                raise ValueError("wrong table proof shape/order")
            _exact_int(row[1], minimum=1)
            rls, can_select, can_insert, can_update, can_delete, can_truncate = (
                _exact_bool(value) for value in row[2:8]
            )
            permissive, restrictive = (_exact_bool(value) for value in row[8:10])
            if (
                not rls
                or not can_select
                or can_insert
                or can_update
                or can_delete
                or can_truncate
                or not permissive
                or restrictive
            ):
                raise ValueError("six-table authority mismatch")
            six_rls[expected_table] = rls
            six_select[expected_table] = can_select
            six_insert[expected_table] = can_insert
            six_update[expected_table] = can_update
            six_delete[expected_table] = can_delete
            six_truncate[expected_table] = can_truncate
            six_permissive[expected_table] = permissive
            six_restrictive[expected_table] = restrictive

        function_rows = _rows(cursor, AUTHORITY_FUNCTIONS_SQL)
        if len(function_rows) != len(PROOF_FUNCTIONS):
            raise ValueError("wrong proof-function row count")
        function_oids: list[int] = []
        function_execute: dict[str, bool] = {}
        function_definitions: dict[str, dict[str, object]] = {}
        for expected_signature, row in zip(PROOF_FUNCTIONS, function_rows, strict=True):
            if len(row) != 14 or row[0] != expected_signature:
                raise ValueError("wrong proof-function shape/order")
            (
                _, oid, owner, language, prokind, prosecdef, proleakproof,
                proisstrict, provolatile, proparallel, prorows, proconfig,
                definition, can_execute,
            ) = row
            oid = _exact_int(oid, minimum=1)
            if oid in function_oids:
                raise ValueError("proof functions resolve to one OID")
            if not isinstance(definition, str):
                raise ValueError("missing function definition")
            if not isinstance(proconfig, (list, tuple)):
                raise ValueError("wrong proconfig type")
            actual_definition = {
                "oid": oid,
                "owner": owner,
                "language": language,
                "prokind": prokind,
                "prosecdef": _exact_bool(prosecdef),
                "proleakproof": _exact_bool(proleakproof),
                "proisstrict": _exact_bool(proisstrict),
                "provolatile": provolatile,
                "proparallel": proparallel,
                "prorows": _exact_int(prorows),
                "proconfig": list(proconfig),
                "definition_sha256": hashlib.sha256(
                    definition.encode("utf-8", "strict")
                ).hexdigest(),
            }
            if actual_definition != dict(EXPECTED_PROOF_DEFINITIONS[expected_signature]):
                raise ValueError("proof function definition changed")
            if not _exact_bool(can_execute):
                raise ValueError("required proof function is not executable")
            function_oids.append(oid)
            function_execute[expected_signature] = True
            function_definitions[expected_signature] = actual_definition

        other_security_definer_count = _scalar_int(
            cursor,
            AUTHORITY_OTHER_SECURITY_DEFINER_COUNT_SQL,
            {"approved_oids": function_oids},
        )
        if other_security_definer_count != 0:
            raise ValueError("other executable SECURITY DEFINER routine present")

        isolation_row = _one(cursor, SHOW_TRANSACTION_ISOLATION_SQL)
        read_only_row = _one(cursor, SHOW_TRANSACTION_READ_ONLY_SQL)
        if (
            len(isolation_row) != 1
            or not isinstance(isolation_row[0], str)
            or isolation_row[0].lower() != "repeatable read"
            or len(read_only_row) != 1
            or not isinstance(read_only_row[0], str)
            or read_only_row[0].lower() != "on"
        ):
            raise ValueError("transaction mode mismatch")

        database_temporary_public_only = (
            database_temporary is True
            and public_temporary_acl is True
            and direct_reader_temporary_acl is False
            and not memberships
            and database_owner != READER_ROLE
        )
        if not database_temporary_public_only:
            raise ValueError("TEMPORARY authority is not PUBLIC-only")

        if (
            ca.repository_path != CA_REPOSITORY_PATH
            or ca.size_bytes != CA_SIZE_BYTES
            or ca.sha256 != CA_SHA256
            or ca.git_blob_sha1 != CA_GIT_BLOB_SHA1
        ):
            raise ValueError("CA observation mismatch")

        proof: dict[str, object] = {
            "current_user": current_user,
            "session_user": session_user,
            "dsn_login_user": parsed.user,
            "dsn_password_present": parsed.password_present,
            "dsn_password_fallbacks_absent": parsed.password_fallbacks_absent,
            "dsn_sslmode": parsed.sslmode,
            "dsn_sslrootcert": parsed.sslrootcert,
            "sslrootcert_sha256": ca.sha256,
            "dsn_sslcertmode": parsed.sslcertmode,
            "dsn_require_auth": parsed.require_auth,
            "dsn_tls_fallbacks_absent": parsed.tls_fallbacks_absent,
            "tls_active": bool(tls_active),
            "dsn_identity_overrides_absent": parsed.identity_overrides_absent,
            "current_database": current_database,
            "database_owner": database_owner,
            "database_create": bool(database_create),
            "database_temporary": bool(database_temporary),
            "database_temporary_public_only": database_temporary_public_only,
            "session_temp_schema_created": False,
            "effective_host": parsed.host,
            "effective_port": parsed.port,
            "project_binding_verified": True,
            "schema_public_usage": bool(schema_public_usage),
            "schema_public_create": bool(schema_public_create),
            "non_system_schema_create_privilege_count": schema_create_count,
            "schema_atom_v9_internal_usage": bool(schema_atom_v9_internal_usage),
            "proof_functions_execute": function_execute,
            "proof_function_definitions": function_definitions,
            "non_system_security_definer_execute_privilege_count": other_security_definer_count,
            "reader_role_attributes": reader_role_attributes,
            "reader_role_memberships": memberships,
            "six_tables_select": six_select,
            "six_tables_insert": six_insert,
            "six_tables_update": six_update,
            "six_tables_delete": six_delete,
            "six_tables_truncate": six_truncate,
            "non_system_relation_write_privilege_count": relation_write_count,
            "six_tables_rls_enabled": six_rls,
            "six_tables_permissive_full_read": six_permissive,
            "six_tables_restrictive_select": six_restrictive,
            "transaction_isolation": "repeatable read",
            "read_only_transaction": True,
            "verification_status": "PASS",
        }
        expected_keys = {
            "current_user", "session_user", "dsn_login_user",
            "dsn_password_present", "dsn_password_fallbacks_absent",
            "dsn_sslmode", "dsn_sslrootcert", "sslrootcert_sha256",
            "dsn_sslcertmode", "dsn_require_auth", "dsn_tls_fallbacks_absent",
            "tls_active", "dsn_identity_overrides_absent", "current_database",
            "database_owner", "database_create", "database_temporary",
            "database_temporary_public_only", "session_temp_schema_created",
            "effective_host", "effective_port", "project_binding_verified",
            "schema_public_usage", "schema_public_create",
            "non_system_schema_create_privilege_count",
            "schema_atom_v9_internal_usage", "proof_functions_execute",
            "proof_function_definitions",
            "non_system_security_definer_execute_privilege_count",
            "reader_role_attributes", "reader_role_memberships",
            "six_tables_select", "six_tables_insert", "six_tables_update",
            "six_tables_delete", "six_tables_truncate",
            "non_system_relation_write_privilege_count",
            "six_tables_rls_enabled", "six_tables_permissive_full_read",
            "six_tables_restrictive_select", "transaction_isolation",
            "read_only_transaction", "verification_status",
        }
        if set(proof) != expected_keys:
            raise AssertionError("authority proof key drift")
        validate_authority_proof(proof)
        return proof
    except DatabaseContractError:
        raise
    except Exception:
        _database_fail(stage, DatabaseDefect.AUTHORITY)


@dataclass(slots=True)
class SnapshotSession:
    """One already-open read-only REPEATABLE READ snapshot."""

    connection: object = field(repr=False)
    cursor: object = field(repr=False)
    parsed: ParsedDatabaseURI = field(repr=False)
    initial_ca: PinnedCAObservation
    initial_authority_proof: dict[str, object]
    scan_started_at: datetime
    recovery_started_at: datetime | None
    _ca_recheck: Callable[[DatabaseFailureStage], PinnedCAObservation] = field(repr=False)
    _ca_recheck_deadline: (
        Callable[
            [
                DatabaseFailureStage,
                GithubDeadlineContext,
                Callable[[], int],
            ],
            PinnedCAObservation,
        ]
        | None
    ) = field(default=None, repr=False)
    _transaction: object | None = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def final_authority_check(
        self,
        *,
        context: GithubDeadlineContext | None = None,
        clock_ns: Callable[[], int] | None = None,
    ) -> dict[str, object]:
        stage = DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS
        deadline_check = (
            None
            if context is None or clock_ns is None
            else context.checker(clock_ns)
        )
        try:
            if context is None and clock_ns is None:
                current_ca = self._ca_recheck(stage)
            elif (
                context is not None
                and clock_ns is not None
                and self._ca_recheck_deadline is not None
            ):
                current_ca = self._ca_recheck_deadline(
                    stage,
                    context,
                    clock_ns,
                )
            else:
                _database_fail(stage, DatabaseDefect.PINNED_CA)
        except DatabaseContractError:
            raise
        except Exception:
            _database_fail(stage, DatabaseDefect.PINNED_CA)
        _cooperative_check(deadline_check)
        proof = authority_check(self.cursor, self.parsed, current_ca, stage=stage)
        _cooperative_check(deadline_check)
        if current_ca != self.initial_ca or proof != self.initial_authority_proof:
            _database_fail(stage, DatabaseDefect.AUTHORITY)
        return proof

    def close_after_final_authority(self) -> None:
        """Commit the read-only transaction and close both database handles."""

        stage = DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS
        if self._closed or self._transaction is None:
            _database_fail(stage, DatabaseDefect.SNAPSHOT)
        try:
            suppressed = self._transaction.__exit__(None, None, None)
            if suppressed:
                raise RuntimeError("transaction exit suppressed")
            self.cursor.close()
            self.connection.close()
        except BaseException:
            _database_fail(stage, DatabaseDefect.SNAPSHOT)
        self._closed = True


@contextmanager
def open_v1b_snapshot(
    parsed: ParsedDatabaseURI,
    initial_ca: PinnedCAObservation,
    *,
    connect: Callable[[str], object],
    repeatable_read_value: object,
    ca_recheck: Callable[[DatabaseFailureStage], PinnedCAObservation],
    ca_recheck_deadline: (
        Callable[
            [
                DatabaseFailureStage,
                GithubDeadlineContext,
                Callable[[], int],
            ],
            PinnedCAObservation,
        ]
        | None
    ) = None,
    recovery_seal_accepted: bool = False,
    sealed_scan_started_at: datetime | None = None,
) -> Iterator[SnapshotSession]:
    """Connect once, locally verify PQconninfo, then enter the sole snapshot.

    The first SQL statement is exactly ``SCAN_STARTED_SQL``.  For recovery its
    value is ``recovery_started_at`` and must be strictly later than the sealed
    ``scan_started_at``; a new seal binds it directly as ``scan_started_at``.
    """

    stage = (
        DatabaseFailureStage.SEALED_OR_RECOVERY
        if recovery_seal_accepted
        else DatabaseFailureStage.NEW_BEFORE_EVIDENCE
    )
    if recovery_seal_accepted != (sealed_scan_started_at is not None):
        _database_fail(stage, DatabaseDefect.SNAPSHOT)
    connection: object | None = None
    try:
        try:
            # No keyword, option, timeout, credential, target, or TLS override.
            connection = connect(parsed._uri_for_single_connect())
        except Exception:
            _database_fail(stage, DatabaseDefect.CONNECTION)
        verify_postconnect_conninfo(connection, parsed, stage=stage)
        if getattr(connection, "autocommit", None) is not False:
            _database_fail(stage, DatabaseDefect.SNAPSHOT)
        try:
            current_ca = ca_recheck(stage)
        except DatabaseContractError:
            raise
        except Exception:
            _database_fail(stage, DatabaseDefect.PINNED_CA)
        if current_ca != initial_ca:
            _database_fail(stage, DatabaseDefect.PINNED_CA)
        try:
            setattr(connection, "read_only", True)
            setattr(connection, "isolation_level", repeatable_read_value)
            transaction = connection.transaction()
        except Exception:
            _database_fail(stage, DatabaseDefect.SNAPSHOT)
        try:
            transaction.__enter__()
        except DatabaseContractError:
            raise
        except BaseException:
            _database_fail(stage, DatabaseDefect.SNAPSHOT)
        cursor: object | None = None
        try:
            try:
                cursor = connection.cursor()
            except DatabaseContractError:
                raise
            except BaseException:
                _database_fail(stage, DatabaseDefect.SNAPSHOT)
            try:
                first = _one(cursor, SCAN_STARTED_SQL)
                if len(first) != 1:
                    raise ValueError("wrong first-operation shape")
                observed_start = _aware_utc(first[0])
                if recovery_seal_accepted:
                    sealed_start = _aware_utc(sealed_scan_started_at)
                    if not observed_start > sealed_start:
                        raise ValueError("recovery timestamp is not later")
                    scan_started_at = sealed_start
                    recovery_started_at = observed_start
                else:
                    scan_started_at = observed_start
                    recovery_started_at = None
                initial_authority = authority_check(
                    cursor, parsed, current_ca, stage=stage
                )
            except DatabaseContractError:
                raise
            except Exception:
                _database_fail(stage, DatabaseDefect.SNAPSHOT)
            session = SnapshotSession(
                connection=connection,
                cursor=cursor,
                parsed=parsed,
                initial_ca=current_ca,
                initial_authority_proof=initial_authority,
                scan_started_at=scan_started_at,
                recovery_started_at=recovery_started_at,
                _ca_recheck=ca_recheck,
                _ca_recheck_deadline=ca_recheck_deadline,
                _transaction=transaction,
            )
            yield session
        except BaseException:
            exception = sys.exc_info()
            try:
                suppressed = transaction.__exit__(*exception)
            except DatabaseContractError:
                raise
            except BaseException:
                _database_fail(stage, DatabaseDefect.SNAPSHOT)
            if suppressed:
                _database_fail(stage, DatabaseDefect.SNAPSHOT)
            if cursor is None:
                _database_fail(stage, DatabaseDefect.SNAPSHOT)
            raise
        else:
            if not session._closed:
                try:
                    suppressed = transaction.__exit__(None, None, None)
                except DatabaseContractError:
                    raise
                except BaseException:
                    _database_fail(stage, DatabaseDefect.SNAPSHOT)
                if suppressed:
                    _database_fail(stage, DatabaseDefect.SNAPSHOT)
        finally:
            if cursor is not None and not ("session" in locals() and session._closed):
                _close_quietly(cursor)
    finally:
        if connection is not None and not ("session" in locals() and session._closed):
            _close_quietly(connection)


# ---------------------------------------------------------------------------
# Evidence population loading inside the already-open snapshot
# ---------------------------------------------------------------------------

POPULATION_COUNTS_SQL = """
SELECT
  (SELECT pg_catalog.count(*)::bigint
     FROM public.volatility_forecasts AS f
    WHERE f.quant_id = 'q3_volatility'
      AND f.symbol = 'COIN'
      AND f.horizon = ANY(%(horizons)s::text[])
      AND f.maturity_epoch <= %(upper_epoch)s::double precision),
  (SELECT pg_catalog.count(*)::bigint
     FROM public.volatility_forecast_outcomes AS o
     JOIN public.volatility_forecasts AS f ON f.forecast_id = o.forecast_id
    WHERE f.quant_id = 'q3_volatility'
      AND f.symbol = 'COIN'
      AND f.horizon = ANY(%(horizons)s::text[])
      AND f.maturity_epoch <= %(upper_epoch)s::double precision),
  (SELECT pg_catalog.count(*)::bigint
     FROM public.atom_v9_v4_forecasts AS f
    WHERE f.symbol = 'COIN'
      AND f.horizon = ANY(%(horizons)s::text[])
      AND f.target_endpoint <= %(upper_as_of)s::timestamptz),
  (SELECT pg_catalog.count(*)::bigint
     FROM public.atom_v9_v4_outcomes AS o
     JOIN public.atom_v9_v4_forecasts AS f
       ON f.forecast_record_id = o.forecast_record_id
    WHERE f.symbol = 'COIN'
      AND f.horizon = ANY(%(horizons)s::text[])
      AND f.target_endpoint <= %(upper_as_of)s::timestamptz)
"""

FAMILY_STREAM_SQL = """
SELECT f.forecast_id,
       f.xmin::text::xid8::text AS forecast_inserting_xid,
       f.quant_id,
       f.formula_version,
       f.cycle_id,
       f.symbol,
       f.horizon,
       f.cutoff_epoch,
       f.maturity_epoch,
       f.cutoff_midpoint,
       f.forecast_volatility_bps,
       f.created_epoch,
       f.data_schema_version,
       f.source_spec_version,
       o.xmin::text::xid8::text AS outcome_inserting_xid,
       o.maturity_midpoint,
       o.realized_move_bps,
       o.resolved_epoch
FROM public.volatility_forecasts AS f
LEFT JOIN public.volatility_forecast_outcomes AS o
       ON o.forecast_id = f.forecast_id
WHERE f.quant_id = 'q3_volatility'
  AND f.symbol = 'COIN'
  AND f.horizon = ANY(%(horizons)s::text[])
  AND f.maturity_epoch <= %(upper_epoch)s::double precision
ORDER BY pg_catalog.array_position(%(horizons)s::text[], f.horizon),
         f.cutoff_epoch,
         f.forecast_id
"""

FAMILY_PROOF_SQL = """
SELECT p.evidence_kind,
       p.record_id,
       p.inserting_xid::text,
       p.commit_observed_at,
       p.proof_method
FROM atom_v9_internal.read_legacy_evidence_publications_for_records(
    %(kind)s::text,
    %(upper_as_of)s::timestamptz,
    %(record_ids)s::bigint[]
) AS p
ORDER BY p.record_id
"""

V9_FORECAST_STREAM_SQL = """
SELECT f.forecast_record_id,
       f.forecast_record_hash,
       f.symbol,
       f.cutoff_at,
       f.target_endpoint,
       f.horizon,
       f.cycle_id,
       f.v3_model_version,
       f.record_json,
       f.persisted_at
FROM public.atom_v9_v4_forecasts AS f
WHERE f.symbol = 'COIN'
  AND f.horizon = ANY(%(horizons)s::text[])
  AND f.target_endpoint <= %(upper_as_of)s::timestamptz
ORDER BY pg_catalog.array_position(%(horizons)s::text[], f.horizon),
         f.cutoff_at,
         f.forecast_record_id
"""

V9_OUTCOME_STREAM_SQL = """
SELECT o.outcome_record_id,
       o.outcome_record_hash,
       o.forecast_record_id,
       o.target_identity,
       o.record_json,
       o.created_at
FROM public.atom_v9_v4_outcomes AS o
JOIN public.atom_v9_v4_forecasts AS f
  ON f.forecast_record_id = o.forecast_record_id
WHERE f.symbol = 'COIN'
  AND f.horizon = ANY(%(horizons)s::text[])
  AND f.target_endpoint <= %(upper_as_of)s::timestamptz
ORDER BY o.forecast_record_id,
         o.created_at,
         o.outcome_record_id
"""

V9_FORECAST_PROOF_SQL = """
SELECT requested.request_order,
       requested.forecast_record_id,
       p.forecast_record_id,
       p.forecast_record_hash,
       p.commit_observed_at,
       p.target_endpoint,
       p.proof_eligible,
       p.proof_method
FROM unnest(%(record_ids)s::text[]) WITH ORDINALITY
     AS requested(forecast_record_id, request_order)
LEFT JOIN LATERAL
     atom_v9_internal.read_forecast_commit_proof(
         requested.forecast_record_id) AS p ON true
ORDER BY requested.request_order
"""


@dataclass(frozen=True, slots=True)
class LegacyPublicationProof:
    evidence_kind: str
    record_id: int
    inserting_xid: str
    commit_observed_at: datetime
    proof_method: str


@dataclass(frozen=True, slots=True)
class V9ForecastCommitProof:
    forecast_record_id: str
    forecast_record_hash: str
    commit_observed_at: datetime
    target_endpoint: datetime
    proof_eligible: bool
    proof_method: str


@dataclass(frozen=True, slots=True)
class FamilyEvidenceRow:
    forecast_id: int
    forecast_inserting_xid: str
    quant_id: str
    formula_version: str
    cycle_id: str
    symbol: str
    horizon: str
    cutoff_epoch: object
    maturity_epoch: object
    cutoff_midpoint: object
    forecast_volatility_bps: object
    created_epoch: object
    data_schema_version: str
    source_spec_version: str
    outcome_inserting_xid: str | None
    maturity_midpoint: object | None
    realized_move_bps: object | None
    resolved_epoch: object | None
    forecast_proof: LegacyPublicationProof | None
    outcome_proof: LegacyPublicationProof | None

    @property
    def immutable_record_identity(self) -> str:
        return str(self.forecast_id).zfill(20)


@dataclass(frozen=True, slots=True)
class V9OutcomeEnvelope:
    """Opaque durable outcome row, decoded only after lineage selection."""

    outcome_record_id: object
    outcome_record_hash: object
    forecast_record_id: str
    target_identity: object
    record_json: object = field(repr=False)
    created_at: object


@dataclass(frozen=True, slots=True)
class V9EvidenceRow:
    forecast_record_id: str
    forecast_record_hash: str
    symbol: str
    cutoff_at: datetime
    target_endpoint: datetime
    horizon: str
    cycle_id: str
    v3_model_version: str
    persisted_at: datetime
    forecast: object = field(repr=False)
    forecast_proof: V9ForecastCommitProof | None = field(repr=False)
    outcome: object | None = field(repr=False)
    outcomes: tuple[object, ...] = field(default_factory=tuple, repr=False)
    canonical_target_identity_value: str = field(default="", repr=False)
    outcome_envelopes: tuple[V9OutcomeEnvelope, ...] = field(
        default_factory=tuple, repr=False
    )

    @property
    def immutable_record_identity(self) -> str:
        return self.forecast_record_id


@dataclass(frozen=True, slots=True)
class EvidencePopulation:
    upper_as_of: datetime
    family_rows: tuple[FamilyEvidenceRow, ...]
    v9_rows: tuple[V9EvidenceRow, ...]
    source_counts: Mapping[str, int]


def _batches(items: Sequence[Any], size: int = PROOF_BATCH_SIZE) -> Iterator[Sequence[Any]]:
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= PROOF_BATCH_SIZE:
        raise ValueError("invalid proof batch size")
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _close_quietly(value: object) -> None:
    try:
        close = getattr(value, "close", None)
        if callable(close):
            close()
    except Exception:
        pass


def _stream_rows(cursor: object, batch_size: int = PROOF_BATCH_SIZE) -> Iterator[tuple[Any, ...]]:
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            return
        for row in batch:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
                raise ValueError("stream row is not positional")
            yield tuple(row)


def _load_legacy_proofs(
    cursor: object,
    *,
    kind: str,
    record_ids: Sequence[int],
    upper_as_of: datetime,
) -> dict[int, LegacyPublicationProof]:
    if kind not in {FAMILY_FORECAST_KIND, FAMILY_OUTCOME_KIND}:
        raise ValueError("wrong legacy proof kind")
    if len(record_ids) > PROOF_BATCH_SIZE or len(set(record_ids)) != len(record_ids):
        raise ValueError("invalid legacy proof request")
    if not record_ids:
        return {}
    rows = _rows(
        cursor,
        FAMILY_PROOF_SQL,
        {"kind": kind, "upper_as_of": upper_as_of, "record_ids": list(record_ids)},
    )
    requested = set(record_ids)
    found: dict[int, LegacyPublicationProof] = {}
    last_id: int | None = None
    for row in rows:
        if len(row) != 5:
            raise ValueError("wrong legacy proof row shape")
        proof_kind, raw_id, raw_xid, raw_observed, proof_method = row
        record_id = _exact_int(raw_id, minimum=1)
        observed = _aware_utc(raw_observed)
        if (
            proof_kind != kind
            or record_id not in requested
            or record_id in found
            or last_id is not None and record_id < last_id
            or not isinstance(raw_xid, str)
            or not raw_xid.isascii()
            or not raw_xid.isdecimal()
            or proof_method != PROOF_METHOD
            or observed > upper_as_of
        ):
            raise ValueError("legacy proof integrity mismatch")
        found[record_id] = LegacyPublicationProof(
            kind, record_id, raw_xid, observed, proof_method
        )
        last_id = record_id
    return found


def _load_v9_proofs(
    cursor: object,
    requested_rows: Sequence[tuple[str, str, datetime]],
) -> dict[str, V9ForecastCommitProof | None]:
    if len(requested_rows) > PROOF_BATCH_SIZE:
        raise ValueError("too many V9 proof requests")
    requested_ids = [row[0] for row in requested_rows]
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("duplicate V9 proof request")
    if not requested_ids:
        return {}
    rows = _rows(cursor, V9_FORECAST_PROOF_SQL, {"record_ids": requested_ids})
    if len(rows) != len(requested_rows):
        raise ValueError("V9 proof reader changed cardinality")
    result: dict[str, V9ForecastCommitProof | None] = {}
    for expected_order, (request, row) in enumerate(
        zip(requested_rows, rows, strict=True), start=1
    ):
        expected_id, expected_hash, expected_endpoint = request
        if len(row) != 8:
            raise ValueError("wrong V9 proof row shape")
        (
            raw_order,
            requested_id,
            proof_id,
            proof_hash,
            raw_observed,
            raw_endpoint,
            raw_eligible,
            proof_method,
        ) = row
        if _exact_int(raw_order, minimum=1) != expected_order or requested_id != expected_id:
            raise ValueError("V9 proof request ordering changed")
        proof_values = row[2:]
        if all(value is None for value in proof_values):
            result[expected_id] = None
            continue
        if any(value is None for value in proof_values):
            raise ValueError("partial V9 proof")
        observed = _aware_utc(raw_observed)
        endpoint = _aware_utc(raw_endpoint)
        eligible = _exact_bool(raw_eligible)
        if (
            proof_id != expected_id
            or proof_hash != expected_hash
            or endpoint != expected_endpoint
            or proof_method != PROOF_METHOD
            or eligible != (observed < endpoint)
        ):
            raise ValueError("V9 commit proof integrity mismatch")
        result[expected_id] = V9ForecastCommitProof(
            expected_id,
            expected_hash,
            observed,
            endpoint,
            eligible,
            proof_method,
        )
    return result


def _validate_family_row(
    row: tuple[Any, ...],
    *,
    forecast_proof: LegacyPublicationProof | None,
    outcome_proof: LegacyPublicationProof | None,
) -> FamilyEvidenceRow:
    if len(row) != 18:
        raise ValueError("wrong FAMILY row shape")
    (
        raw_id,
        forecast_xid,
        quant_id,
        formula_version,
        cycle_id,
        symbol,
        horizon,
        cutoff_epoch,
        maturity_epoch,
        cutoff_midpoint,
        forecast_volatility_bps,
        created_epoch,
        data_schema_version,
        source_spec_version,
        outcome_xid,
        maturity_midpoint,
        realized_move_bps,
        resolved_epoch,
    ) = row
    forecast_id = _exact_int(raw_id, minimum=1)
    if (
        quant_id != "q3_volatility"
        or not isinstance(formula_version, str)
        or symbol != "COIN"
        or horizon not in HORIZONS
    ):
        raise ValueError("FAMILY outer identity mismatch")
    if formula_version != "realized-volatility-v1":
        # Nonselected formula rows contribute only to n_input and
        # n_unselected_lineage_rows.  Their unrelated payload/proofs cannot
        # alter admissibility or any protected result.
        return FamilyEvidenceRow(
            forecast_id,
            forecast_xid,
            quant_id,
            formula_version,
            cycle_id,
            symbol,
            horizon,
            cutoff_epoch,
            maturity_epoch,
            cutoff_midpoint,
            forecast_volatility_bps,
            created_epoch,
            data_schema_version,
            source_spec_version,
            outcome_xid,
            maturity_midpoint,
            realized_move_bps,
            resolved_epoch,
            None,
            None,
        )
    cutoff = _finite_float(cutoff_epoch)
    if (
        not isinstance(forecast_xid, str)
        or not forecast_xid.isascii()
        or not forecast_xid.isdecimal()
    ):
        raise ValueError("FAMILY forecast XID mismatch")
    maturity = _finite_float(maturity_epoch)
    created = _finite_float(created_epoch)
    if (
        not isinstance(cycle_id, str)
        or not cycle_id
        or not isinstance(data_schema_version, str)
        or not data_schema_version
        or not isinstance(source_spec_version, str)
        or not source_spec_version
        or maturity != cutoff + HORIZON_SECONDS[horizon]
        or created > maturity
    ):
        raise ValueError("FAMILY identity/shape mismatch")
    if forecast_proof is not None and forecast_proof.inserting_xid != forecast_xid:
        raise ValueError("FAMILY forecast proof XID mismatch")
    outcome_values = (maturity_midpoint, realized_move_bps, resolved_epoch)
    if (
        outcome_xid is None and any(value is not None for value in outcome_values)
    ) or (
        outcome_xid is not None and not all(value is not None for value in outcome_values)
    ):
        # Because every outcome column is NOT NULL, a left-join row must be all
        # null or all non-null.  Partial nulls cannot be treated as absence.
        raise ValueError("partial FAMILY outcome")
    if outcome_xid is not None:
        if (
            not isinstance(outcome_xid, str)
            or not outcome_xid.isascii()
            or not outcome_xid.isdecimal()
        ):
            raise ValueError("invalid FAMILY outcome XID")
        if outcome_proof is not None and outcome_proof.inserting_xid != outcome_xid:
            raise ValueError("FAMILY outcome proof XID mismatch")
    elif outcome_proof is not None:
        raise ValueError("proof exists for absent FAMILY outcome")
    return FamilyEvidenceRow(
        forecast_id,
        forecast_xid,
        quant_id,
        formula_version,
        cycle_id,
        symbol,
        horizon,
        cutoff_epoch,
        maturity_epoch,
        cutoff_midpoint,
        forecast_volatility_bps,
        created_epoch,
        data_schema_version,
        source_spec_version,
        outcome_xid,
        maturity_midpoint,
        realized_move_bps,
        resolved_epoch,
        forecast_proof,
        outcome_proof,
    )


def _validate_v9_forecast(
    row: tuple[Any, ...],
    *,
    deserialize_forecast_record: Callable[..., object],
) -> tuple[dict[str, object], object]:
    if len(row) != 10:
        raise ValueError("wrong V9 forecast row shape")
    (
        record_id,
        record_hash,
        symbol,
        raw_cutoff,
        raw_endpoint,
        horizon,
        cycle_id,
        model_version,
        record_json,
        raw_persisted,
    ) = row
    if (
        not isinstance(record_id, str)
        or not record_id
        or not isinstance(record_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", record_hash) is None
        or symbol != "COIN"
        or horizon not in HORIZONS
        or not isinstance(cycle_id, str)
        or not cycle_id
        or not isinstance(model_version, str)
        or not model_version
    ):
        raise ValueError("V9 forecast outer identity mismatch")
    cutoff = _aware_utc(raw_cutoff)
    endpoint = _aware_utc(raw_endpoint)
    persisted = _aware_utc(raw_persisted)
    if (endpoint - cutoff).total_seconds() != HORIZON_SECONDS[horizon]:
        raise ValueError("V9 target interval differs from horizon")
    forecast = deserialize_forecast_record(record_json, expected_hash=record_hash)
    expected_attributes = {
        "forecast_record_id": record_id,
        "forecast_record_hash": record_hash,
        "symbol": symbol,
        "cutoff_at": cutoff,
        "target_endpoint": endpoint,
        "horizon": horizon,
        "cycle_id": cycle_id,
        "v3_model_version": model_version,
    }
    for name, value in expected_attributes.items():
        observed = getattr(forecast, name)
        if isinstance(value, datetime):
            observed = _aware_utc(observed)
        if observed != value:
            raise ValueError("V9 forecast outer/JSON mismatch")
    if getattr(forecast, "horizon_seconds", None) != HORIZON_SECONDS[horizon]:
        raise ValueError("V9 embedded horizon_seconds mismatch")
    validate_lineage_identity(
        CELL_BY_ORDER[len(HORIZONS) + HORIZONS.index(horizon)],
        {
            "v3_model_version": getattr(forecast, "v3_model_version", None),
            "symbol": getattr(forecast, "symbol", None),
            "horizon": getattr(forecast, "horizon", None),
            "cohort_id": getattr(forecast, "cohort_id", None),
            "cohort_hash": getattr(forecast, "cohort_hash", None),
        },
        allow_sentinel=False,
    )
    return {
        "forecast_record_id": record_id,
        "forecast_record_hash": record_hash,
        "symbol": symbol,
        "cutoff_at": cutoff,
        "target_endpoint": endpoint,
        "horizon": horizon,
        "cycle_id": cycle_id,
        "v3_model_version": model_version,
        "persisted_at": persisted,
    }, forecast


def _load_v9_outcomes(
    connection: object,
    params: Mapping[str, object],
    *,
    deserialize_outcome_record: Callable[..., object],
) -> tuple[dict[str, tuple[V9OutcomeEnvelope, ...]], int]:
    cursor = connection.cursor(name="v1b_v9_outcome_stream")
    grouped: dict[str, list[V9OutcomeEnvelope]] = {}
    count = 0
    try:
        cursor.execute(V9_OUTCOME_STREAM_SQL, params)
        for row in _stream_rows(cursor):
            count += 1
            if len(row) != 6:
                raise ValueError("wrong V9 outcome row shape")
            (
                outcome_id,
                outcome_hash,
                forecast_id,
                target_identity,
                record_json,
                raw_created,
            ) = row
            # The FK/key is needed for exact count reconciliation.  Every
            # remaining field is deliberately opaque until the forecast's
            # lineage is selected at a candidate.  In particular, neither a
            # corrupt payload nor an irrelevant metric on a losing lineage may
            # influence lineage selection or abort the population.
            if not isinstance(forecast_id, str) or not forecast_id:
                raise ValueError("V9 outcome forecast identity mismatch")
            grouped.setdefault(forecast_id, []).append(
                V9OutcomeEnvelope(
                    outcome_id,
                    outcome_hash,
                    forecast_id,
                    target_identity,
                    record_json,
                    raw_created,
                )
            )
    finally:
        _close_quietly(cursor)
    return {key: tuple(values) for key, values in grouped.items()}, count


def _select_v9_target_outcome(outcomes: Sequence[object]) -> object | None:
    """Apply the frozen E-1 target outcome choice without proof prefiltering."""

    verified = tuple(
        outcome
        for outcome in outcomes
        if getattr(outcome, "target_timing_status", None) == "VERIFIED"
    )
    if not verified:
        return None
    try:
        return min(
            verified,
            key=lambda outcome: (
                _aware_utc(getattr(outcome, "created_at")),
                str(getattr(outcome, "outcome_record_id")),
            ),
        )
    except Exception as error:
        raise ValueError("invalid V9 target outcome order") from error


def _materialize_v9_row(
    row: V9EvidenceRow,
    primitives: "V4Primitives",
    *,
    as_of: datetime | None = None,
) -> V9EvidenceRow:
    """Decode all outcomes only after this row's lineage has been selected."""

    if not row.outcome_envelopes:
        return row
    if row.outcome is not None or row.outcomes:
        raise ProtocolDefect("mixed opaque/materialized V9 outcomes")
    decoded: list[object] = []
    seen_ids: set[str] = set()
    last_order: tuple[datetime, str] | None = None
    try:
        boundary = _aware_utc(as_of) if as_of is not None else None
        for envelope in row.outcome_envelopes:
            created = _aware_utc(envelope.created_at)
            # At an earlier candidate, only the outer creation time is needed
            # to prove non-membership.  Every other field and the payload stay
            # opaque until the envelope becomes candidate-visible.
            if boundary is not None and created > boundary:
                continue
            outcome_id = envelope.outcome_record_id
            outcome_hash = envelope.outcome_record_hash
            target_identity = envelope.target_identity
            if (
                not isinstance(outcome_id, str)
                or not outcome_id
                or not isinstance(outcome_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", outcome_hash) is None
                or envelope.forecast_record_id != row.forecast_record_id
                or not isinstance(target_identity, str)
                or outcome_id in seen_ids
            ):
                raise ValueError("V9 outcome identity/duplicate mismatch")
            order = (created, outcome_id)
            if last_order is not None and order <= last_order:
                raise ValueError("V9 outcome stream is not strictly ordered")
            outcome = primitives.deserialize_outcome_record(
                envelope.record_json, expected_hash=outcome_hash
            )
            expected_attributes = {
                "outcome_record_id": outcome_id,
                "outcome_record_hash": outcome_hash,
                "forecast_record_id": row.forecast_record_id,
                "target_identity": target_identity,
                "created_at": created,
            }
            for name, value in expected_attributes.items():
                observed = getattr(outcome, name)
                if isinstance(value, datetime):
                    observed = _aware_utc(observed)
                if observed != value:
                    raise ValueError("V9 outcome outer/JSON mismatch")
            decoded.append(outcome)
            seen_ids.add(outcome_id)
            last_order = order
    except ProtocolDefect:
        raise
    except Exception as error:
        raise ProtocolDefect("selected-lineage V9 outcome invalid") from error
    outcomes = tuple(decoded)
    return replace(
        row,
        outcome=_select_v9_target_outcome(outcomes),
        outcomes=outcomes,
        outcome_envelopes=(),
    )


def load_evidence_population(
    session: SnapshotSession,
    upper_as_of: datetime,
    *,
    deserialize_forecast_record: Callable[..., object],
    deserialize_outcome_record: Callable[..., object],
    canonical_target_identity: Callable[[object], str],
    apply_forecast_commit_proof: Callable[[object, object], object],
    stage_after_first_read: DatabaseFailureStage,
) -> EvidencePopulation:
    """Load the bounded source/proof rows inside ``session``'s sole snapshot.

    The independent count is the first evidence-table read.  Therefore callers
    must pass ``NEW_AFTER_EVIDENCE_BEFORE_SEAL`` for a new count-only scan or
    ``SEALED_OR_RECOVERY`` after seal acceptance.  No failure here may route to
    pre-evidence BLOCKED.  After the first evidence-table read, failure is the
    ordinary null-seal PRE-CELL INVALID route required by Amendment 3B.
    """

    if stage_after_first_read not in {
        DatabaseFailureStage.NEW_AFTER_EVIDENCE_BEFORE_SEAL,
        DatabaseFailureStage.SEALED_OR_RECOVERY,
    }:
        _database_fail(stage_after_first_read, DatabaseDefect.POPULATION)
    try:
        upper = _aware_utc(upper_as_of)
        if not upper < session.scan_started_at:
            raise ValueError("population as-of is not completed at scan start")
        params: dict[str, object] = {
            "horizons": list(HORIZONS),
            "upper_as_of": upper,
            "upper_epoch": upper.timestamp(),
        }
        counts_row = _one(session.cursor, POPULATION_COUNTS_SQL, params)
        if len(counts_row) != 4:
            raise ValueError("wrong population-count shape")
        family_forecast_count, family_outcome_count, v9_forecast_count, v9_outcome_count = (
            _exact_int(value) for value in counts_row
        )

        lookup = session.connection.cursor()
        family_stream = session.connection.cursor(name="v1b_family_stream")
        family_rows: list[FamilyEvidenceRow] = []
        family_ids: set[int] = set()
        loaded_family_outcomes = 0
        last_family_order: tuple[int, float, int] | None = None
        try:
            family_stream.execute(FAMILY_STREAM_SQL, params)
            while True:
                batch = family_stream.fetchmany(PROOF_BATCH_SIZE)
                if not batch:
                    break
                positional = [tuple(row) for row in batch]
                record_ids = [_exact_int(row[0], minimum=1) for row in positional]
                if len(set(record_ids)) != len(record_ids) or family_ids.intersection(record_ids):
                    raise ValueError("duplicate FAMILY forecast")
                selected_record_ids = [
                    _exact_int(row[0], minimum=1)
                    for row in positional
                    if row[3] == "realized-volatility-v1"
                ]
                forecast_proofs = _load_legacy_proofs(
                    lookup,
                    kind=FAMILY_FORECAST_KIND,
                    record_ids=selected_record_ids,
                    upper_as_of=upper,
                )
                outcome_ids = [
                    _exact_int(row[0], minimum=1)
                    for row in positional
                    if row[3] == "realized-volatility-v1"
                    and row[14] is not None
                ]
                outcome_proofs = _load_legacy_proofs(
                    lookup,
                    kind=FAMILY_OUTCOME_KIND,
                    record_ids=outcome_ids,
                    upper_as_of=upper,
                )
                for row in positional:
                    record_id = _exact_int(row[0], minimum=1)
                    validated = _validate_family_row(
                        row,
                        forecast_proof=forecast_proofs.get(record_id),
                        outcome_proof=outcome_proofs.get(record_id),
                    )
                    # Only the selected formula participates in scientific
                    # ordering.  Legal nonselected formula rows may carry
                    # nonfinite/otherwise irrelevant timing payloads and must
                    # contribute solely to the two population counters.
                    if validated.formula_version == "realized-volatility-v1":
                        family_order = (
                            HORIZONS.index(validated.horizon),
                            _finite_float(validated.cutoff_epoch),
                            validated.forecast_id,
                        )
                        if (
                            last_family_order is not None
                            and family_order <= last_family_order
                        ):
                            raise ValueError("FAMILY stream is not strictly ordered")
                        last_family_order = family_order
                    family_rows.append(validated)
                    family_ids.add(record_id)
                    loaded_family_outcomes += int(validated.outcome_inserting_xid is not None)
        finally:
            _close_quietly(family_stream)

        outcomes, loaded_v9_outcomes = _load_v9_outcomes(
            session.connection,
            params,
            deserialize_outcome_record=deserialize_outcome_record,
        )
        v9_stream = session.connection.cursor(name="v1b_v9_forecast_stream")
        v9_rows: list[V9EvidenceRow] = []
        v9_ids: set[str] = set()
        last_v9_order: tuple[int, datetime, str] | None = None
        try:
            v9_stream.execute(V9_FORECAST_STREAM_SQL, params)
            while True:
                batch = v9_stream.fetchmany(PROOF_BATCH_SIZE)
                if not batch:
                    break
                validated_batch: list[tuple[dict[str, object], object]] = []
                proof_requests: list[tuple[str, str, datetime]] = []
                for raw_row in batch:
                    outer, forecast = _validate_v9_forecast(
                        tuple(raw_row),
                        deserialize_forecast_record=deserialize_forecast_record,
                    )
                    record_id = str(outer["forecast_record_id"])
                    if record_id in v9_ids or any(
                        request[0] == record_id for request in proof_requests
                    ):
                        raise ValueError("duplicate V9 forecast")
                    validated_batch.append((outer, forecast))
                    proof_requests.append(
                        (
                            record_id,
                            str(outer["forecast_record_hash"]),
                            _aware_utc(outer["target_endpoint"]),
                        )
                    )
                proofs = _load_v9_proofs(lookup, proof_requests)
                for outer, forecast in validated_batch:
                    record_id = str(outer["forecast_record_id"])
                    v9_order = (
                        HORIZONS.index(str(outer["horizon"])),
                        _aware_utc(outer["cutoff_at"]),
                        record_id,
                    )
                    if last_v9_order is not None and v9_order <= last_v9_order:
                        raise ValueError("V9 stream is not strictly ordered")
                    last_v9_order = v9_order
                    proof = proofs[record_id]
                    proof_row = (
                        None
                        if proof is None
                        else (
                            proof.forecast_record_id,
                            proof.forecast_record_hash,
                            proof.commit_observed_at,
                            proof.target_endpoint,
                            proof.proof_eligible,
                            proof.proof_method,
                        )
                    )
                    forecast = apply_forecast_commit_proof(forecast, proof_row)
                    if proof is None:
                        if getattr(forecast, "persistence_proof_eligible", None) is not False:
                            raise ValueError("V9 missing proof hydration mismatch")
                    elif (
                        _aware_utc(getattr(forecast, "persisted_at"))
                        != proof.commit_observed_at
                        or getattr(forecast, "persistence_proof_eligible", None)
                        is not proof.proof_eligible
                    ):
                        raise ValueError("V9 proof hydration mismatch")
                    forecast_outcome_envelopes = outcomes.pop(record_id, ())
                    target_identity = canonical_target_identity(forecast)
                    v9_rows.append(
                        V9EvidenceRow(
                            forecast_record_id=record_id,
                            forecast_record_hash=str(outer["forecast_record_hash"]),
                            symbol=str(outer["symbol"]),
                            cutoff_at=_aware_utc(outer["cutoff_at"]),
                            target_endpoint=_aware_utc(outer["target_endpoint"]),
                            horizon=str(outer["horizon"]),
                            cycle_id=str(outer["cycle_id"]),
                            v3_model_version=str(outer["v3_model_version"]),
                            persisted_at=_aware_utc(outer["persisted_at"]),
                            forecast=forecast,
                            forecast_proof=proof,
                            outcome=None,
                            outcomes=(),
                            canonical_target_identity_value=target_identity,
                            outcome_envelopes=forecast_outcome_envelopes,
                        )
                    )
                    v9_ids.add(record_id)
        finally:
            _close_quietly(v9_stream)
            _close_quietly(lookup)

        if outcomes:
            raise ValueError("outcome references an unloaded V9 forecast")
        if (
            len(family_rows) != family_forecast_count
            or loaded_family_outcomes != family_outcome_count
            or len(v9_rows) != v9_forecast_count
            or loaded_v9_outcomes != v9_outcome_count
        ):
            raise ValueError("stream/count reconciliation failed")
        source_counts = MappingProxyType(
            {
                "public.volatility_forecasts": family_forecast_count,
                "public.volatility_forecast_outcomes": family_outcome_count,
                "public.atom_v9_v4_forecasts": v9_forecast_count,
                "public.atom_v9_v4_outcomes": v9_outcome_count,
            }
        )
        return EvidencePopulation(upper, tuple(family_rows), tuple(v9_rows), source_counts)
    except DatabaseContractError:
        raise
    except Exception:
        _database_fail(stage_after_first_read, DatabaseDefect.POPULATION)


def family_forecast_is_admissible(row: FamilyEvidenceRow, as_of: datetime) -> bool:
    """Exact proof/timing predicate used before FAMILY lineage/RTH selection."""

    try:
        boundary = _aware_utc(as_of)
        maturity = float(row.maturity_epoch)
        proof = row.forecast_proof
        return bool(
            proof is not None
            and proof.inserting_xid == row.forecast_inserting_xid
            and proof.commit_observed_at <= boundary
            and proof.commit_observed_at.timestamp() < maturity
        )
    except Exception:
        return False


def family_outcome_is_available(row: FamilyEvidenceRow, as_of: datetime) -> bool:
    """Outcome row and matching publication proof must both be durable by as-of."""

    try:
        boundary = _aware_utc(as_of)
        proof = row.outcome_proof
        resolved = float(row.resolved_epoch)
        maturity = float(row.maturity_epoch)
        return bool(
            row.outcome_inserting_xid is not None
            and proof is not None
            and proof.inserting_xid == row.outcome_inserting_xid
            and proof.commit_observed_at <= boundary
            and math.isfinite(resolved)
            and math.isfinite(maturity)
            and maturity <= resolved <= proof.commit_observed_at.timestamp()
            and resolved <= boundary.timestamp()
        )
    except Exception:
        return False


def v9_forecast_is_admissible(row: V9EvidenceRow, as_of: datetime) -> bool:
    """Existing V4 proof seam plus decoded PRODUCTION origin, without outcomes."""

    try:
        boundary = _aware_utc(as_of)
        proof = row.forecast_proof
        return bool(
            getattr(row.forecast, "evidence_origin") == "PRODUCTION"
            and getattr(row.forecast, "persistence_proof_eligible") is True
            and proof is not None
            and proof.forecast_record_id == row.forecast_record_id
            and proof.forecast_record_hash == row.forecast_record_hash
            and proof.target_endpoint == row.target_endpoint
            and proof.proof_method == PROOF_METHOD
            and proof.proof_eligible is True
            and _aware_utc(getattr(row.forecast, "persisted_at"))
            == proof.commit_observed_at
            and row.persisted_at <= proof.commit_observed_at
            and proof.commit_observed_at <= boundary
            and row.persisted_at <= boundary
        )
    except Exception:
        return False


def v9_outcome_is_available(row: V9EvidenceRow, as_of: datetime) -> bool:
    """Existing V4 outcome proof/timing predicate at a candidate boundary."""

    try:
        boundary = _aware_utc(as_of)
        outcome = row.outcome
        if outcome is None:
            return False
        created = _aware_utc(getattr(outcome, "created_at"))
        resolved = _aware_utc(getattr(outcome, "target_resolved_at"))
        observed = _aware_utc(getattr(outcome, "endpoint_observation_at"))
        return bool(
            getattr(outcome, "forecast_record_id") == row.forecast_record_id
            and (
                not row.canonical_target_identity_value
                or getattr(outcome, "target_identity")
                == row.canonical_target_identity_value
            )
            and _aware_utc(getattr(outcome, "target_endpoint"))
            == row.target_endpoint
            and getattr(outcome, "proof_eligible") is True
            and getattr(outcome, "target_timing_status") == "VERIFIED"
            and created <= boundary
            and resolved <= boundary
            and observed <= boundary
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# V-1B invocation orchestration
# ---------------------------------------------------------------------------


USAGE_INVALID_MANIFEST = canonical_line(
    {"mode": "V1B", "reason": "INVALID_MANIFEST_ID", "status": "USAGE_ERROR"}
)
EARLY_MANIFEST_ID = "v1b-early-4"
IMPLEMENTATION_PATHS = frozenset(
    {
        "quant/volatility_scorecard.py",
        "tests/test_volatility_scorecard.py",
        "requirements.txt",
        CA_REPOSITORY_PATH,
    }
)
REUSED_PRIMITIVE_PATHS = frozenset(
    {
        "quant/v9_v1_contract.py",
        "quant/v9_v2a_dataset.py",
        "quant/v9_v2b_calibration.py",
        "quant/v9_v2c_covariance.py",
        "quant/v9_v2d_evidence_state.py",
        "quant/v9_v3_synthesis.py",
        "quant/v9_v4a_evidence.py",
        "quant/v9_v4b_accuracy.py",
        "quant/v9_v4c_predictive.py",
    }
)
CONDITIONAL_MIGRATION_PATH = (
    "migrations/033_authorize_v1_volatility_scorecard_reader.sql"
)
RECEIPT_PATH_RE = re.compile(
    r"docs/v-1b-volatility-scorecard-(?:receipt|negative)-.+\.json\Z"
)


class InvocationMode(Enum):
    NEW_SEAL = auto()
    RECOVERY = auto()


class InvocationPhase(Enum):
    INPUT = auto()
    STARTUP_VALIDATED = auto()
    INITIAL_AUTHORITY = auto()
    SNAPSHOT_OPEN = auto()
    EVIDENCE_READ = auto()
    SEALED = auto()
    TRUTHFUL_CELLS = auto()
    FINISHED = auto()


class OrchestrationFailure(ContractError):
    """Sanitized failure whose route is selected only from explicit state."""


class CapacityRefusal(OrchestrationFailure):
    """The sole post-count, pre-seal failure that remains non-consuming."""


class OutputSinkFailure(BaseException):
    """A stdout attempt may have emitted bytes; no second record is allowed."""


def _attempt_stdout(writer: Callable[[bytes], None], data: bytes) -> bool:
    """Attempt one complete record and suppress every sink-side diagnostic."""

    try:
        writer(data)
    except BaseException:
        return False
    return True


@dataclass(frozen=True, slots=True)
class Invocation:
    manifest_id: str
    recovery_path: str | None
    mode: InvocationMode


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    authorized_main_sha: str
    render_git_commit: str
    local_head_sha: str

    @property
    def sha(self) -> str:
        if not (
            HEX40_RE.fullmatch(self.authorized_main_sha)
            and self.authorized_main_sha == self.render_git_commit
            and self.authorized_main_sha == self.local_head_sha
        ):
            raise OrchestrationFailure("EXECUTION_IDENTITY_INVALID")
        return self.authorized_main_sha


@dataclass(frozen=True, slots=True)
class CalendarSession:
    session_date: date
    market_open: datetime
    market_close: datetime


@dataclass(frozen=True, slots=True)
class PriorReceipt:
    path: str
    raw: bytes
    manifest_id: str
    schema_version: str
    terminal: bool
    receipt_sha256: str
    seal_record_sha256: str | None


@dataclass(frozen=True, slots=True)
class ImmutableRepositoryFacts:
    execution_sha: str
    implementation_merge_sha: str
    amendment_merged_at_utc: str
    receipts: tuple[PriorReceipt, ...]
    history_sha256: str


@dataclass(frozen=True, slots=True)
class RepositoryCheckpoint:
    execution_sha: str
    selection: ApprovalSelection
    facts: ImmutableRepositoryFacts


@dataclass(frozen=True, slots=True)
class RuntimeState:
    plan: RuntimeArtifactPlan
    measurement: RuntimeMeasurement
    frozen: FrozenRuntime
    identity: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class V4Primitives:
    governed_accuracy_evidence: Callable[..., Sequence[tuple[object, object]]]
    apply_forecast_commit_proof: Callable[[object, object], object]
    calibration_observation: Callable[..., object]
    calibrate_scale: Callable[..., object]
    select_non_overlapping: Callable[[Iterable[tuple[object, object]]], object]
    deserialize_forecast_record: Callable[..., object]
    deserialize_outcome_record: Callable[..., object]
    canonical_target_identity: Callable[[object], str]


@dataclass(frozen=True, slots=True)
class OrchestrationDependencies:
    validate_startup: Callable[[Invocation], None]
    execution_identity: Callable[[], ExecutionIdentity]
    prepare_runtime: Callable[[], RuntimeState]
    remeasure_runtime: Callable[
        [RuntimeState, Callable[[], object] | None], RuntimeState
    ]
    repository_checkpoint: Callable[
        [
            AuthorityStage,
            str,
            str,
            RuntimeState,
            RepositoryCheckpoint | None,
            Callable[
                [GithubDeadlineContext, Callable[[], int]],
                Callable[[Callable[[], object]], None],
            ]
            | None,
        ],
        RepositoryCheckpoint,
    ]
    open_snapshot: Callable[[SealBundle | None], object]
    load_evidence: Callable[[SnapshotSession, datetime, bool], EvidencePopulation]
    calendar_sessions: Callable[[date, date], Sequence[CalendarSession]]
    primitives: V4Primitives
    emit_seal: Callable[[bytes], str]
    write_stdout: Callable[[bytes], None]
    utc_now: Callable[[], datetime]


@dataclass(slots=True)
class InvocationState:
    invocation: Invocation
    phase: InvocationPhase = InvocationPhase.INPUT
    expected_sha: str | None = None
    checkpoint: RepositoryCheckpoint | None = None
    runtime: RuntimeState | None = None
    snapshot: SnapshotSession | None = None
    seal: SealBundle | None = None
    boundary: "CandidateResult | None" = None
    terminal_exclusion_verified: bool = False

    @property
    def recovery_accepted(self) -> bool:
        return self.invocation.mode is InvocationMode.RECOVERY and self.seal is not None

    @property
    def evidence_started(self) -> bool:
        return self.phase in {
            InvocationPhase.EVIDENCE_READ,
            InvocationPhase.SEALED,
            InvocationPhase.TRUTHFUL_CELLS,
            InvocationPhase.FINISHED,
        }

    @property
    def truthful_cells(self) -> bool:
        return self.phase in {InvocationPhase.TRUTHFUL_CELLS, InvocationPhase.FINISHED}


@dataclass(frozen=True, slots=True)
class CandidateResult:
    session: CalendarSession
    selected_lineages: tuple[Mapping[str, object], ...]
    cohort_trace: tuple[Mapping[str, object], ...]
    populations: tuple[CellPopulation, ...]
    counts: tuple[ReadinessCounts, ...]


@dataclass(frozen=True, slots=True)
class ScanResult:
    first_candidate_session: date | None
    completed_candidates: tuple[CalendarSession, ...]
    boundary: CandidateResult | None


def parse_scorecard_cli(argv: Sequence[str]) -> Invocation:
    """Parse only the two frozen options, without argparse side effects."""

    if isinstance(argv, (str, bytes, bytearray)):
        raise ContractError("INVALID_MANIFEST_ID")
    words = tuple(argv)
    if any(not isinstance(word, str) for word in words):
        raise ContractError("INVALID_MANIFEST_ID")
    if len(words) not in {2, 4} or words[0] != "--manifest-id":
        raise ContractError("INVALID_MANIFEST_ID")
    manifest = words[1]
    recovery: str | None = None
    if len(words) == 4:
        if words[2] != "--recovery-seal-file":
            raise ContractError("INVALID_MANIFEST_ID")
        recovery = words[3]
    if manifest not in MANIFEST_REGISTRY:
        raise ContractError("INVALID_MANIFEST_ID")
    return Invocation(
        manifest_id=manifest,
        recovery_path=recovery,
        mode=(InvocationMode.RECOVERY if recovery is not None else InvocationMode.NEW_SEAL),
    )


def _invalid_recovery_line(manifest_id: str) -> bytes:
    return canonical_line(
        {
            "manifest_id": manifest_id,
            "mode": "V1B",
            "reason": "INVALID_RECOVERY_SEAL",
            "status": "USAGE_ERROR",
        }
    )


def _read_regular_file_no_symlinks(path: str) -> bytes:
    """Read an absolute regular file while refusing every symlink component."""

    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path == "/"
        or "\x00" in path
        or path.endswith("/")
        or "//" in path
    ):
        raise OSError("unsafe path")
    pieces = path.split("/")[1:]
    if not pieces or any(piece in {"", ".", ".."} for piece in pieces):
        raise OSError("unsafe path")
    directory_fd = os.open(
        "/",
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0),
    )
    file_fd = -1
    try:
        for piece in pieces[:-1]:
            next_fd = os.open(
                piece,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            pieces[-1],
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not regular")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, GITHUB_DEADLINE_WORK_CHUNK_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(file_fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise OSError("file changed")
        raw = b"".join(chunks)
        if len(raw) != before.st_size:
            raise OSError("short read")
        return raw
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(directory_fd)


def read_recovery_seal(invocation: Invocation) -> SealBundle | None:
    if invocation.mode is InvocationMode.NEW_SEAL:
        return None
    assert invocation.recovery_path is not None
    try:
        raw = _read_regular_file_no_symlinks(invocation.recovery_path)
        record = parse_canonical_line(raw, "recovery seal")
        return validate_seal(
            record,
            expected_manifest_id=invocation.manifest_id,
            expected_canonical_bytes=raw,
        )
    except BaseException:
        raise OrchestrationFailure("INVALID_RECOVERY_SEAL") from None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProtocolDefect("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def _epoch_utc(value: object) -> datetime:
    number = finite(value)
    if number is None:
        raise ProtocolDefect("finite epoch required")
    try:
        return datetime.fromtimestamp(number, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ProtocolDefect("epoch outside datetime range") from error


def enumerate_xnys_candidates(
    sessions: Sequence[CalendarSession],
    *,
    amendment_merged_at: datetime,
    scan_started_at: datetime,
) -> tuple[CalendarSession, ...]:
    """Return completed full-day XNYS candidates in exact ascending order."""

    anchor = _utc(amendment_merged_at)
    scan_start = _utc(scan_started_at)
    new_york = _new_york_zone()
    ordered: list[CalendarSession] = []
    previous: tuple[date, datetime, datetime] | None = None
    for row in sessions:
        if not isinstance(row, CalendarSession):
            raise ProtocolDefect("calendar row type")
        opened = _utc(row.market_open)
        closed = _utc(row.market_close)
        opened_local = opened.astimezone(new_york)
        closed_local = closed.astimezone(new_york)
        current = (row.session_date, opened, closed)
        if previous is not None and current <= previous:
            raise ProtocolDefect("calendar rows not strictly ordered")
        previous = current
        if (
            opened_local.date() != row.session_date
            or closed_local.date() != row.session_date
            or opened_local.time().replace(tzinfo=None) != datetime.min.time().replace(
                hour=9, minute=30
            )
            or closed_local.time().replace(tzinfo=None) != datetime.min.time().replace(
                hour=16
            )
            or not opened < closed
        ):
            continue
        if opened > anchor and closed < scan_start:
            ordered.append(CalendarSession(row.session_date, opened, closed))
    return tuple(ordered)


def qualifying_full_xnys_sessions(
    sessions: Sequence[CalendarSession],
) -> tuple[CalendarSession, ...]:
    """Validate/retain the complete full-day schedule used by evidence rows."""

    new_york = _new_york_zone()
    result: list[CalendarSession] = []
    previous: tuple[date, datetime, datetime] | None = None
    for row in sessions:
        if not isinstance(row, CalendarSession):
            raise ProtocolDefect("calendar row type")
        opened = _utc(row.market_open)
        closed = _utc(row.market_close)
        current = (row.session_date, opened, closed)
        if previous is not None and current <= previous:
            raise ProtocolDefect("calendar rows not strictly ordered")
        previous = current
        opened_local = opened.astimezone(new_york)
        closed_local = closed.astimezone(new_york)
        if (
            opened_local.date() == row.session_date
            and closed_local.date() == row.session_date
            and opened_local.time().replace(tzinfo=None)
            == datetime.min.time().replace(hour=9, minute=30)
            and closed_local.time().replace(tzinfo=None)
            == datetime.min.time().replace(hour=16)
            and opened < closed
        ):
            result.append(CalendarSession(row.session_date, opened, closed))
    return tuple(result)


def _session_for_target(
    cutoff: datetime,
    endpoint: datetime,
    sessions_by_date: Mapping[date, CalendarSession],
) -> date | None:
    start = _utc(cutoff)
    end = _utc(endpoint)
    local_date = start.astimezone(_new_york_zone()).date()
    session = sessions_by_date.get(local_date)
    if (
        session is None
        or end.astimezone(_new_york_zone()).date() != local_date
        or start < session.market_open
        or end > session.market_close
        or end <= start
    ):
        return None
    return local_date


def _lineage_from_v9_row(row: V9EvidenceRow) -> dict[str, str]:
    forecast = row.forecast
    identity = {
        "v3_model_version": getattr(forecast, "v3_model_version"),
        "symbol": getattr(forecast, "symbol"),
        "horizon": getattr(forecast, "horizon"),
        "cohort_id": getattr(forecast, "cohort_id"),
        "cohort_hash": getattr(forecast, "cohort_hash"),
    }
    if not all(isinstance(value, str) for value in identity.values()):
        raise ProtocolDefect("V9 lineage field type")
    return identity


def _select_lineage(
    spec: CellSpec,
    evidence: EvidencePopulation,
    as_of: datetime,
) -> dict[str, str]:
    if spec.forecaster == "FAMILY-VOL":
        return family_lineage(spec.horizon)
    candidates: list[V9LineageCandidate] = []
    for row in evidence.v9_rows:
        identity = _lineage_from_v9_row(row)
        validate_lineage_identity(
            CELL_BY_ORDER[len(HORIZONS) + HORIZONS.index(row.horizon)],
            identity,
            allow_sentinel=False,
        )
        if row.horizon != spec.horizon or row.target_endpoint > as_of:
            continue
        if not v9_forecast_is_admissible(row, as_of):
            continue
        candidates.append(
            V9LineageCandidate(
                v3_model_version=identity["v3_model_version"],
                symbol=identity["symbol"],
                horizon=identity["horizon"],
                cohort_id=identity["cohort_id"],
                cohort_hash=identity["cohort_hash"],
                cutoff_at=_utc(row.cutoff_at),
            )
        )
    return select_v9_lineage(spec.horizon, candidates, as_of)


@dataclass(frozen=True, slots=True)
class _EligibleTarget:
    session_date: date
    cutoff_at: datetime
    spacing_cutoff: float | datetime
    endpoint: datetime
    identity: str
    row: object


def _horizon_select(
    rows: Sequence[_EligibleTarget], horizon_seconds: int
) -> tuple[tuple[_EligibleTarget, ...], int]:
    ordered = sorted(
        rows,
        key=lambda item: (item.session_date, item.spacing_cutoff, item.identity),
    )
    seen: set[str] = set()
    selected: list[_EligibleTarget] = []
    excluded = 0
    last_session: date | None = None
    last_cutoff: float | datetime | None = None
    for row in ordered:
        if row.identity in seen:
            raise ProtocolDefect("duplicate immutable record identity")
        seen.add(row.identity)
        if row.session_date != last_session:
            last_session = row.session_date
            last_cutoff = None
        if last_cutoff is not None:
            if type(row.spacing_cutoff) is float and type(last_cutoff) is float:
                overlaps = row.spacing_cutoff < last_cutoff + horizon_seconds
            elif isinstance(row.spacing_cutoff, datetime) and isinstance(
                last_cutoff, datetime
            ):
                overlaps = row.spacing_cutoff < last_cutoff + timedelta(
                    seconds=horizon_seconds
                )
            else:
                raise ProtocolDefect("mixed selector cutoff representations")
            if overlaps:
                excluded += 1
                continue
        selected.append(row)
        last_cutoff = row.spacing_cutoff
    return tuple(selected), excluded


def _family_population(
    spec: CellSpec,
    lineage: Mapping[str, str],
    evidence: EvidencePopulation,
    as_of: datetime,
    sessions_by_date: Mapping[date, CalendarSession],
) -> CellPopulation:
    as_of_epoch = _utc(as_of).timestamp()
    rows = tuple(
        row
        for row in evidence.family_rows
        if row.horizon == spec.horizon
        and isinstance(row.maturity_epoch, (int, float))
        and not isinstance(row.maturity_epoch, bool)
        and row.maturity_epoch <= as_of_epoch
    )
    n_unselected = 0
    n_inadmissible = 0
    n_non_rth = 0
    eligible: list[_EligibleTarget] = []
    for row in rows:
        row_lineage = {
            "quant_id": row.quant_id,
            "formula_version": row.formula_version,
            "symbol": row.symbol,
            "horizon": row.horizon,
        }
        if row_lineage != dict(lineage):
            n_unselected += 1
            continue
        if not (
            family_forecast_is_admissible(row, as_of)
            and family_outcome_is_available(row, as_of)
        ):
            n_inadmissible += 1
            continue
        resolved = finite(row.resolved_epoch)
        maturity = finite(row.maturity_epoch)
        if (
            resolved is None
            or maturity is None
            or not maturity <= resolved <= maturity + 5.0
        ):
            n_inadmissible += 1
            continue
        cutoff = _epoch_utc(row.cutoff_epoch)
        endpoint = _epoch_utc(row.maturity_epoch)
        session_date = _session_for_target(cutoff, endpoint, sessions_by_date)
        if session_date is None:
            n_non_rth += 1
            continue
        eligible.append(
            _EligibleTarget(
                session_date,
                cutoff,
                _finite_float(row.cutoff_epoch),
                endpoint,
                row.immutable_record_identity,
                row,
            )
        )
    selected, n_overlap = _horizon_select(
        eligible, HORIZON_SECONDS[spec.horizon]
    )
    n_null = 0
    n_nonpositive = 0
    windows: list[ValidWindow] = []
    for target in selected:
        row = target.row
        prediction = finite(getattr(row, "forecast_volatility_bps"))
        realization = finite(getattr(row, "realized_move_bps"))
        if prediction is None or realization is None:
            n_null += 1
            continue
        if realization < 0:
            raise ProtocolDefect("negative FAMILY realization")
        if prediction <= 0:
            n_nonpositive += 1
            continue
        forecast_proof = getattr(row, "forecast_proof")
        outcome_proof = getattr(row, "outcome_proof")
        available = max(
            _utc(forecast_proof.commit_observed_at),
            _utc(outcome_proof.commit_observed_at),
            _epoch_utc(getattr(row, "resolved_epoch")),
        )
        windows.append(
            ValidWindow(
                target.session_date,
                target.cutoff_at,
                target.identity,
                prediction,
                realization,
                available,
            )
        )
    return assemble_cell_population(
        spec=spec,
        lineage_identity=lineage,
        n_input=len(rows),
        n_unselected_lineage_rows=n_unselected,
        n_inadmissible=n_inadmissible,
        n_non_rth=n_non_rth,
        n_overlap_excluded=n_overlap,
        n_null_or_nonfinite_excluded=n_null,
        n_nonpositive_prediction_excluded=n_nonpositive,
        n_kappa_unavailable=0,
        windows=windows,
    )


def _v9_pair_strictly_prior(
    row: V9EvidenceRow, outcome: object, cutoff: datetime
) -> bool:
    try:
        proof = row.forecast_proof
        if proof is None:
            return False
        return bool(
            v9_forecast_is_admissible(row, cutoff - timedelta(microseconds=1))
            and getattr(outcome, "forecast_record_id") == row.forecast_record_id
            and _utc(row.cutoff_at) < cutoff
            and _utc(proof.commit_observed_at) < cutoff
            and _utc(getattr(outcome, "target_resolved_at")) < cutoff
            and _utc(getattr(outcome, "created_at")) < cutoff
            and _utc(getattr(outcome, "endpoint_observation_at")) < cutoff
        )
    except Exception:
        return False


def _reconcile_v4_selected_pairs(
    governed: Sequence[tuple[object, object]],
    selection: object,
) -> tuple[tuple[object, object], ...]:
    """Recover the exact canonical pairs represented by V4A's selected IDs.

    V4A's public result carries forecast IDs, not pair objects.  Mapping those
    IDs back to every governed pair is invalid when duplicate outcomes share a
    forecast.  Reapply its unchanged canonicalization in input order, then
    require exact agreement with the returned selection.
    """

    selected_ids = tuple(getattr(selection, "selected_ids"))
    if len(selected_ids) != len(set(selected_ids)):
        raise ProtocolDefect("V9 selector identity mismatch")
    pairs = list(governed)
    supports_exact = all(
        hasattr(forecast, "logical_key")
        and hasattr(forecast, "forecast_record_hash")
        and hasattr(forecast, "forecast_record_id")
        and hasattr(forecast, "cutoff_at")
        and hasattr(forecast, "horizon_seconds")
        and hasattr(outcome, "logical_key")
        and hasattr(outcome, "outcome_record_hash")
        for forecast, outcome in pairs
    )
    if supports_exact:
        forecast_groups: dict[object, list[tuple[object, object]]] = {}
        for pair in pairs:
            forecast_groups.setdefault(pair[0].logical_key, []).append(pair)
        forecast_unconflicted = [
            pair
            for group in forecast_groups.values()
            if len({item[0].forecast_record_hash for item in group}) == 1
            for pair in group
        ]
        outcome_groups: dict[object, list[tuple[object, object]]] = {}
        for pair in forecast_unconflicted:
            outcome_groups.setdefault(pair[1].logical_key, []).append(pair)
        outcome_unconflicted = [
            pair
            for group in outcome_groups.values()
            if len({item[1].outcome_record_hash for item in group}) == 1
            for pair in group
        ]
        eligible: list[tuple[object, object]] = []
        for forecast, outcome in outcome_unconflicted:
            endpoint = getattr(forecast, "target_endpoint", None)
            observed = getattr(outcome, "endpoint_observation_at", None)
            if (
                not isinstance(endpoint, datetime)
                or endpoint.tzinfo is None
                or not isinstance(observed, datetime)
                or observed.tzinfo is None
                or getattr(outcome, "target_endpoint", None) != endpoint
            ):
                continue
            delay = (observed - endpoint).total_seconds()
            stored_delay = getattr(outcome, "endpoint_observation_delay", None)
            if (
                getattr(outcome, "proof_eligible", None) is True
                and isinstance(stored_delay, (int, float))
                and not isinstance(stored_delay, bool)
                and math.isfinite(stored_delay)
                and stored_delay == delay
                and 0.0 <= delay <= 5.0
            ):
                eligible.append((forecast, outcome))
        canonical_groups: dict[object, list[tuple[object, object]]] = {}
        for pair in eligible:
            canonical_groups.setdefault(pair[0].logical_key, []).append(pair)
        canonical: list[tuple[object, object]] = []
        for group in canonical_groups.values():
            if len({item[0].forecast_record_hash for item in group}) == 1:
                canonical.append(
                    min(group, key=lambda item: item[0].forecast_record_id)
                )
        canonical.sort(
            key=lambda item: (item[0].cutoff_at, item[0].forecast_record_id)
        )
        selected: list[tuple[object, object]] = []
        for pair in canonical:
            if (
                not selected
                or pair[0].cutoff_at
                >= selected[-1][0].cutoff_at
                + timedelta(seconds=selected[-1][0].horizon_seconds)
            ):
                selected.append(pair)
        if tuple(item[0].forecast_record_id for item in selected) != selected_ids:
            raise ProtocolDefect("V9 selector identity mismatch")
        return tuple(selected)

    # Synthetic primitive seams may expose only the stable IDs.  Preserve one
    # first-occurrence pair per ID; never expand one ID back to all outcomes.
    reconciled: list[tuple[object, object]] = []
    for selected_id in selected_ids:
        matches = [
            pair
            for pair in pairs
            if getattr(pair[0], "forecast_record_id", None) == selected_id
        ]
        if not matches:
            raise ProtocolDefect("V9 selector identity mismatch")
        reconciled.append(matches[0])
    return tuple(reconciled)


def _causal_kappa(
    target: V9EvidenceRow,
    evidence: EvidencePopulation,
    primitives: V4Primitives,
) -> float | None:
    cutoff = _utc(target.cutoff_at)
    lineage = _lineage_from_v9_row(target)
    pairs: list[tuple[object, object]] = []
    for row in evidence.v9_rows:
        if _lineage_from_v9_row(row) != lineage:
            continue
        # Outcome bytes belong to the selected lineage, but even selected-lineage
        # outcomes remain opaque until the forecast itself is inside the causal
        # calibration boundary.  A future/inadmissible forecast's unrelated bad
        # outcome may not turn a valid target into a protocol failure.
        proof = row.forecast_proof
        if (
            _utc(row.cutoff_at) >= cutoff
            or _utc(row.target_endpoint) >= cutoff
            or proof is None
            or _utc(proof.commit_observed_at) >= cutoff
            or not v9_forecast_is_admissible(
                row, cutoff - timedelta(microseconds=1)
            )
        ):
            continue
        materialized = _materialize_v9_row(
            row,
            primitives,
            as_of=cutoff - timedelta(microseconds=1),
        )
        candidates = materialized.outcomes or (
            (materialized.outcome,) if materialized.outcome is not None else ()
        )
        for outcome in candidates:
            if not _v9_pair_strictly_prior(materialized, outcome, cutoff):
                continue
            actual = finite(getattr(outcome, "actual_return_bps"))
            mean = finite(getattr(materialized.forecast, "expected_return_bps"))
            variance = finite(
                getattr(materialized.forecast, "predictive_variance_bps2")
            )
            # Preserve finite nonpositive q0 through governed filtering,
            # overlap selection, and the frozen latest-250 withholding step.
            # The unchanged calibrate_scale() is the sole q0 > 0 filter.
            if actual is None or mean is None or variance is None:
                continue
            pairs.append((materialized.forecast, outcome))
    try:
        governed = tuple(
            primitives.governed_accuracy_evidence(
                lineage["horizon"],
                lineage["cohort_id"],
                lineage["cohort_hash"],
                cutoff - timedelta(microseconds=1),
                pairs,
            )
        )
        selection = primitives.select_non_overlapping(governed)
        selected = list(_reconcile_v4_selected_pairs(governed, selection))
        selected.sort(
            key=lambda pair: (
                _utc(getattr(pair[0], "cutoff_at")),
                getattr(pair[0], "forecast_record_id"),
            )
        )
        calibration = selected[: max(0, len(selected) - 250)]
        calibration_end = (
            _utc(getattr(calibration[-1][0], "cutoff_at"))
            if calibration
            else cutoff - timedelta(microseconds=1)
        )
        observations: list[object] = []
        for forecast, outcome in calibration:
            actual = finite(getattr(outcome, "actual_return_bps"))
            mean = finite(getattr(forecast, "expected_return_bps"))
            variance = finite(getattr(forecast, "predictive_variance_bps2"))
            if actual is None or mean is None or variance is None:
                continue
            observations.append(
                primitives.calibration_observation(
                    cutoff=_utc(getattr(forecast, "cutoff_at")),
                    forecast_record_id=getattr(forecast, "forecast_record_id"),
                    actual_bps=actual,
                    mean_bps=mean,
                    q0_bps2=variance,
                    # V4C deliberately retains its latent UTC-date session
                    # identity; Amendment 2A did not replace it with XNYS
                    # local-date semantics.
                    session_id=_utc(getattr(forecast, "cutoff_at"))
                    .date()
                    .isoformat(),
                    target_resolved_at=_utc(
                        getattr(outcome, "target_resolved_at")
                    ),
                )
            )
        result = primitives.calibrate_scale(
            observations, calibration_end=calibration_end
        )
        kappa = finite(getattr(result, "kappa"))
        if getattr(result, "status") != "MATURE" or kappa is None or kappa <= 0:
            return None
        return kappa
    except ProtocolDefect:
        raise
    except Exception as error:
        raise ProtocolDefect("causal kappa reconstruction failed") from error


def _v9_population(
    spec: CellSpec,
    lineage: Mapping[str, str],
    evidence: EvidencePopulation,
    as_of: datetime,
    sessions_by_date: Mapping[date, CalendarSession],
    primitives: V4Primitives,
) -> CellPopulation:
    rows = tuple(
        row
        for row in evidence.v9_rows
        if row.horizon == spec.horizon and row.target_endpoint <= as_of
    )
    if dict(lineage) == v9_sentinel_lineage(spec.horizon):
        return assemble_cell_population(
            spec=spec,
            lineage_identity=lineage,
            n_input=len(rows),
            n_unselected_lineage_rows=0,
            n_inadmissible=len(rows),
            n_non_rth=0,
            n_overlap_excluded=0,
            n_null_or_nonfinite_excluded=0,
            n_nonpositive_prediction_excluded=0,
            n_kappa_unavailable=0,
            windows=(),
        )
    n_unselected = 0
    n_inadmissible = 0
    n_non_rth = 0
    eligible: list[_EligibleTarget] = []
    for opaque_row in rows:
        if _lineage_from_v9_row(opaque_row) != dict(lineage):
            n_unselected += 1
            continue
        # The frozen population order classifies forecast inadmissibility before
        # touching any outcome payload.  This keeps corrupt/irrelevant outcomes
        # attached to an inadmissible forecast from escalating the row.
        if not v9_forecast_is_admissible(opaque_row, as_of):
            n_inadmissible += 1
            continue
        row = _materialize_v9_row(opaque_row, primitives, as_of=as_of)
        if not v9_outcome_is_available(row, as_of):
            n_inadmissible += 1
            continue
        cutoff = _utc(row.cutoff_at)
        endpoint = _utc(row.target_endpoint)
        session_date = _session_for_target(cutoff, endpoint, sessions_by_date)
        if session_date is None:
            n_non_rth += 1
            continue
        eligible.append(
            _EligibleTarget(
                session_date,
                cutoff,
                cutoff,
                endpoint,
                row.immutable_record_identity,
                row,
            )
        )
    selected, n_overlap = _horizon_select(
        eligible, HORIZON_SECONDS[spec.horizon]
    )
    n_null = 0
    n_nonpositive = 0
    n_kappa = 0
    windows: list[ValidWindow] = []
    for target in selected:
        row = target.row
        forecast = getattr(row, "forecast")
        outcome = getattr(row, "outcome")
        variance = finite(getattr(forecast, "predictive_variance_bps2"))
        actual = finite(getattr(outcome, "actual_return_bps"))
        if variance is None or actual is None:
            n_null += 1
            continue
        if variance < 0:
            # sqrt(q0) is undefined over the frozen real-valued formula.
            n_null += 1
            continue
        if variance == 0:
            n_nonpositive += 1
            continue
        kappa = _causal_kappa(row, evidence, primitives)
        if kappa is None:
            n_kappa += 1
            continue
        try:
            prediction = kappa * math.sqrt(variance)
        except (ArithmeticError, OverflowError, ValueError):
            n_null += 1
            continue
        if not math.isfinite(prediction):
            n_null += 1
            continue
        if prediction <= 0:
            n_nonpositive += 1
            continue
        proof = getattr(row, "forecast_proof")
        available = max(
            _utc(proof.commit_observed_at),
            _utc(getattr(outcome, "target_resolved_at")),
            _utc(getattr(outcome, "created_at")),
            _utc(getattr(outcome, "endpoint_observation_at")),
        )
        windows.append(
            ValidWindow(
                target.session_date,
                target.cutoff_at,
                target.identity,
                prediction,
                abs(actual),
                available,
            )
        )
    return assemble_cell_population(
        spec=spec,
        lineage_identity=lineage,
        n_input=len(rows),
        n_unselected_lineage_rows=n_unselected,
        n_inadmissible=n_inadmissible,
        n_non_rth=n_non_rth,
        n_overlap_excluded=n_overlap,
        n_null_or_nonfinite_excluded=n_null,
        n_nonpositive_prediction_excluded=n_nonpositive,
        n_kappa_unavailable=n_kappa,
        windows=windows,
    )


def build_candidate_populations(
    manifest_id: str,
    evidence: EvidencePopulation,
    session: CalendarSession,
    full_sessions: Sequence[CalendarSession],
    primitives: V4Primitives,
) -> tuple[tuple[Mapping[str, object], ...], tuple[CellPopulation, ...]]:
    as_of = session.market_close
    sessions_by_date = {
        item.session_date: item
        for item in full_sessions
        if item.market_close <= as_of
    }
    if len(sessions_by_date) != sum(
        1 for item in full_sessions if item.market_close <= as_of
    ):
        raise ProtocolDefect("duplicate XNYS session")
    lineages: list[Mapping[str, object]] = []
    populations: list[CellPopulation] = []
    for spec in manifest_cells(manifest_id):
        lineage = _select_lineage(spec, evidence, as_of)
        lineages.append(selected_lineage_wrapper(spec, lineage))
        if spec.forecaster == "FAMILY-VOL":
            population = _family_population(
                spec, lineage, evidence, as_of, sessions_by_date
            )
        else:
            population = _v9_population(
                spec, lineage, evidence, as_of, sessions_by_date, primitives
            )
        populations.append(population)
    return tuple(lineages), tuple(populations)


def scan_manifest_candidates(
    manifest_id: str,
    evidence: EvidencePopulation,
    completed: Sequence[CalendarSession],
    full_sessions: Sequence[CalendarSession],
    primitives: V4Primitives,
) -> ScanResult:
    ordered = tuple(completed)
    if any(
        left.session_date >= right.session_date
        for left, right in zip(ordered, ordered[1:])
    ):
        raise ProtocolDefect("candidate session ordering")
    trace: list[Mapping[str, object]] = []
    prior_v9: dict[int, Mapping[str, object]] = {}
    first = ordered[0].session_date if ordered else None
    for candidate in ordered:
        lineages, populations = build_candidate_populations(
            manifest_id, evidence, candidate, full_sessions, primitives
        )
        for wrapper in lineages:
            if wrapper["forecaster"] != "V9-VOL":
                continue
            order = int(wrapper["cell_order"])
            lineage = wrapper["lineage_identity"]
            if order not in prior_v9 or prior_v9[order] != lineage:
                trace.append(
                    {
                        "cell_order": order,
                        "forecaster": "V9-VOL",
                        "horizon": wrapper["horizon"],
                        "candidate_session": candidate.session_date.isoformat(),
                        "event_type": "INITIAL" if order not in prior_v9 else "ROTATION",
                        "selected_lineage_identity": json_clone(lineage),
                    }
                )
                prior_v9[order] = json_clone(lineage)
        counts = tuple(readiness_counts(population) for population in populations)
        if manifest_is_ready(manifest_id, counts):
            return ScanResult(
                first,
                ordered,
                CandidateResult(
                    candidate,
                    lineages,
                    tuple(trace),
                    populations,
                    counts,
                ),
            )
    return ScanResult(first, ordered, None)


# ---------------------------------------------------------------------------
# Authenticated immutable repository/history proof
# ---------------------------------------------------------------------------


def _checkpoint_git_run(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    *arguments: str,
    check: bool,
) -> subprocess.CompletedProcess[bytes]:
    timeout_seconds = context.remaining_seconds(clock_ns)
    try:
        completed = subprocess.run(
            ("git", "-c", "credential.helper=", *arguments),
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=check,
            close_fds=True,
            text=False,
            timeout=timeout_seconds,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        raise OrchestrationFailure("LOCAL_GIT_PROOF_FAILED") from None
    context.check(clock_ns)
    return completed


def _git_read(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    *arguments: str,
) -> bytes:
    completed = _checkpoint_git_run(
        context, clock_ns, *arguments, check=True
    )
    if type(completed.stdout) is not bytes:
        raise OrchestrationFailure("LOCAL_GIT_PROOF_FAILED")
    return completed.stdout


def _git_ascii(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    *arguments: str,
) -> str:
    try:
        value = _git_read(
            context, clock_ns, *arguments
        ).decode("ascii", "strict").strip()
    except UnicodeError:
        raise OrchestrationFailure("LOCAL_GIT_PROOF_FAILED") from None
    context.check(clock_ns)
    return value


def _local_tree_entry(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    commit: str,
    path: str,
) -> tuple[str, str, bytes]:
    checkpoint_check = context.checker(clock_ns)
    raw = _git_read(context, clock_ns, "ls-tree", "-z", commit, "--", path)
    raw_records = _cooperative_call(checkpoint_check, raw.split, b"\0")
    records_list: list[bytes] = []
    for item in _cooperative_tuple(raw_records, check=checkpoint_check):
        if item:
            _cooperative_call(checkpoint_check, records_list.append, item)
    records = _cooperative_call(checkpoint_check, tuple, records_list)
    if len(records) != 1:
        raise OrchestrationFailure("LOCAL_TREE_PATH_INVALID")
    try:
        pieces = _cooperative_call(
            checkpoint_check,
            records[0].split,
            b"\t",
            1,
        )
        if len(pieces) != 2:
            raise ValueError
        metadata, observed_path = pieces
        metadata_text = _cooperative_call(
            checkpoint_check,
            metadata.decode,
            "ascii",
            "strict",
        )
        metadata_parts = _cooperative_call(
            checkpoint_check,
            metadata_text.split,
            " ",
        )
        if len(metadata_parts) != 3:
            raise ValueError
        mode, kind, object_id = metadata_parts
        decoded_path = _cooperative_call(
            checkpoint_check,
            observed_path.decode,
            "utf-8",
            "strict",
        )
    except (UnicodeError, ValueError):
        raise OrchestrationFailure("LOCAL_TREE_PATH_INVALID") from None
    object_id_match = _cooperative_call(
        checkpoint_check,
        re.fullmatch,
        r"[0-9a-f]{40}",
        object_id,
    )
    if (
        decoded_path != path
        or kind != "blob"
        or mode not in {"100644", "100755"}
        or object_id_match is None
    ):
        raise OrchestrationFailure("LOCAL_TREE_PATH_INVALID")
    checkpoint_check()
    content = _git_read(context, clock_ns, "cat-file", "blob", object_id)
    checkpoint_check()
    return mode, object_id, content


def _local_tree_entry_optional(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    commit: str,
    path: str,
) -> tuple[str, str, bytes] | None:
    raw = _git_read(context, clock_ns, "ls-tree", "-z", commit, "--", path)
    if raw == b"":
        context.check(clock_ns)
        return None
    return _local_tree_entry(context, clock_ns, commit, path)


def _github_blob(
    client: GithubClient,
    context: GithubDeadlineContext,
    blob_sha: str,
) -> bytes:
    def validate_blob(
        value: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        request_check()
        if status != 200 or type(value) is not dict:
            _fail()
        content = _cooperative_call(request_check, value.get, "content")
        observed_sha = _cooperative_call(request_check, value.get, "sha")
        encoding = _cooperative_call(request_check, value.get, "encoding")
        size = _cooperative_call(request_check, value.get, "size")
        if (
            observed_sha != blob_sha
            or encoding != "base64"
            or type(size) is not int
            or type(content) is not str
        ):
            _fail()
        lines = _cooperative_call(request_check, content.splitlines)
        compact = _cooperative_call(request_check, "".join, lines)
        try:
            encoded = _cooperative_call(request_check, compact.encode, "ascii")
            decoded = _cooperative_call(
                request_check,
                base64.b64decode,
                encoded,
                validate=True,
            )
        except (UnicodeError, ValueError):
            _fail()
        if _cooperative_call(
            request_check,
            lambda: len(decoded) == size,
        ) is not True:
            _fail()
        request_check()
        return decoded

    _response, decoded = client.get_json(
        f"{GITHUB_REPOSITORY_PATH}/git/blobs/{blob_sha}",
        context=context,
        validator=validate_blob,
    )
    if type(decoded) is not bytes:
        _fail()
    return decoded


def _authenticate_path(
    client: GithubClient,
    context: GithubDeadlineContext,
    execution_sha: str,
    path: str,
    *,
    require_worktree: bool,
) -> bytes:
    clock_ns = client._seams.monotonic_ns
    checkpoint_check = context.checker(clock_ns)
    mode, blob_sha, local = _local_tree_entry(
        context, clock_ns, execution_sha, path
    )
    if mode != "100644" or _github_blob(client, context, blob_sha) != local:
        raise OrchestrationFailure("SOURCE_BLOB_INVALID")
    checkpoint_check()
    if require_worktree:
        try:
            checkpoint_check()
            observed = os.lstat(path)
            checkpoint_check()
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
                raise OSError
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
                os, "O_NOFOLLOW", 0
            )
            fd = os.open(path, flags)
            try:
                checkpoint_check()
                opened = os.fstat(fd)
                checkpoint_check()
                expected_size = len(local)
                if (
                    opened.st_dev != observed.st_dev
                    or opened.st_ino != observed.st_ino
                    or opened.st_mode != observed.st_mode
                    or opened.st_size != expected_size
                    or observed.st_size != expected_size
                ):
                    raise OSError
                total = 0
                while total < expected_size:
                    checkpoint_check()
                    chunk = os.read(
                        fd,
                        min(
                            GITHUB_DEADLINE_WORK_CHUNK_BYTES,
                            expected_size - total,
                        ),
                    )
                    checkpoint_check()
                    if (
                        not chunk
                        or chunk != local[total : total + len(chunk)]
                    ):
                        raise OSError
                    total += len(chunk)
                checkpoint_check()
                if os.read(fd, 1):
                    raise OSError
                checkpoint_check()
                closed = os.fstat(fd)
                checkpoint_check()
            finally:
                os.close(fd)
            if (
                total != expected_size
                or (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mode,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                != (
                    closed.st_dev,
                    closed.st_ino,
                    closed.st_mode,
                    closed.st_size,
                    closed.st_mtime_ns,
                    closed.st_ctime_ns,
                )
            ):
                raise OSError
        except OSError:
            raise OrchestrationFailure("WORKTREE_SOURCE_INVALID") from None
    checkpoint_check()
    return local


def _authenticate_bound_path(
    client: GithubClient,
    context: GithubDeadlineContext,
    implementation_sha: str,
    execution_sha: str,
    path: str,
) -> bytes:
    clock_ns = client._seams.monotonic_ns
    implementation = _local_tree_entry(
        context, clock_ns, implementation_sha, path
    )
    execution = _local_tree_entry(context, clock_ns, execution_sha, path)
    if implementation != execution or implementation[0] != "100644":
        raise OrchestrationFailure("BOUND_SOURCE_CHANGED")
    mode, blob_sha, raw = implementation
    if mode != "100644" or _github_blob(client, context, blob_sha) != raw:
        raise OrchestrationFailure("BOUND_SOURCE_INVALID")
    return _authenticate_path(
        client, context, execution_sha, path, require_worktree=True
    )


def _github_commit(
    client: GithubClient,
    context: GithubDeadlineContext,
    commit_sha: str,
) -> Mapping[str, object]:
    def validate_commit(
        value: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        request_check()
        if status != 200 or type(value) is not dict or value.get("sha") != commit_sha:
            _fail()
        commit = value.get("commit")
        if type(commit) is not dict:
            _fail()
        verification = commit.get("verification")
        tree = commit.get("tree")
        committer = commit.get("committer")
        if (
            type(verification) is not dict
            or verification.get("verified") is not True
            or verification.get("reason") != "valid"
            or not isinstance(verification.get("signature"), str)
            or not verification.get("signature")
            or not isinstance(verification.get("payload"), str)
            or not verification.get("payload")
            or type(tree) is not dict
            or re.fullmatch(r"[0-9a-f]{40}", str(tree.get("sha"))) is None
            or type(committer) is not dict
        ):
            _fail()
        _parse_github_time(committer.get("date"), check=request_check)
        request_check()
        return value

    _response, value = client.get_json(
        f"{GITHUB_REPOSITORY_PATH}/commits/{commit_sha}",
        context=context,
        validator=validate_commit,
    )
    if type(value) is not dict:
        _fail()
    return value


def _associated_merged_pr(
    client: GithubClient,
    context: GithubDeadlineContext,
    commit_sha: str,
    *,
    expected_number: int | None,
) -> Mapping[str, object]:
    def validate_pr_page(
        value: object,
        request_check: Callable[[], int],
    ) -> Sequence[object]:
        request_check()
        if type(value) is not list:
            _fail()
        validated: list[Mapping[str, object]] = []
        for item in value:
            request_check()
            if type(item) is not dict:
                _fail()
            number = item.get("number")
            merge_sha = item.get("merge_commit_sha")
            merged_at = item.get("merged_at")
            if (
                type(number) is not int
                or number <= 0
                or merge_sha is not None
                and (
                    type(merge_sha) is not str
                    or _SHA40_RE.fullmatch(merge_sha) is None
                )
                or merged_at is not None
                and type(merged_at) is not str
            ):
                _fail()
            if merged_at is not None:
                _parse_github_time(merged_at, check=request_check)
            validated.append(item)
        request_check()
        return tuple(validated)

    def validate_pr_collection(
        items: tuple[object, ...],
        paged: GithubDeadlineContext,
    ) -> object:
        paged_check = paged.checker(client._seams.monotonic_ns)
        matches: list[Mapping[str, object]] = []
        seen_numbers: set[int] = set()
        for item in items:
            paged_check()
            if type(item) is not dict:
                _fail()
            number = item.get("number")
            if type(number) is not int or number <= 0 or number in seen_numbers:
                _fail()
            seen_numbers.add(number)
            if item.get("merge_commit_sha") == commit_sha and item.get("merged_at") is not None:
                _parse_github_time(item.get("merged_at"), check=paged_check)
                matches.append(item)
        if len(matches) != 1:
            _fail()
        summary = matches[0]
        number = summary["number"]
        if expected_number is not None and number != expected_number:
            _fail()
        paged_check()
        return number

    number = client.get_paginated_json(
        f"{GITHUB_REPOSITORY_PATH}/commits/{commit_sha}/pulls",
        context=context,
        page_validator=validate_pr_page,
        collection_validator=validate_pr_collection,
    )
    if type(number) is not int:
        raise OrchestrationFailure("MERGED_PR_INVALID")
    def validate_pr_detail(
        detail: object,
        status: int,
        _headers: Mapping[bytes, tuple[bytes, ...]],
        request_check: Callable[[], int],
    ) -> object:
        request_check()
        if status != 200 or type(detail) is not dict:
            _fail()
        base = detail.get("base")
        repository = base.get("repo") if type(base) is dict else None
        merged_by = detail.get("merged_by")
        repository_full_name = (
            repository.get("full_name") if type(repository) is dict else None
        )
        if (
            detail.get("number") != number
            or detail.get("merged") is not True
            or detail.get("merge_commit_sha") != commit_sha
            or type(base) is not dict
            or base.get("ref") != "main"
            or type(repository) is not dict
            or repository_full_name != GITHUB_REPOSITORY
            or type(merged_by) is not dict
            or merged_by.get("id") != GITHUB_OWNER_ID
            or merged_by.get("login") != GITHUB_OWNER_LOGIN
        ):
            _fail()
        _parse_github_time(detail.get("merged_at"), check=request_check)
        request_check()
        return detail

    _response, detail = client.get_json(
        f"{GITHUB_REPOSITORY_PATH}/pulls/{number}",
        context=context,
        validator=validate_pr_detail,
    )
    if type(detail) is not dict:
        _fail()
    return detail


def _commit_diff_paths(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    commit_sha: str,
) -> frozenset[str]:
    checkpoint_check = context.checker(clock_ns)
    parents_text = _git_ascii(
        context, clock_ns, "rev-list", "--parents", "-n", "1", commit_sha
    )
    parents_list = _cooperative_call(checkpoint_check, parents_text.split)
    parents = _cooperative_tuple(parents_list, check=checkpoint_check)
    if not parents or parents[0] != commit_sha or len(parents) < 2:
        raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID")
    raw = _git_read(
        context,
        clock_ns,
        "diff", "--no-renames", "--name-only", "-z", parents[1], commit_sha, "--"
    )
    try:
        raw_items = _cooperative_call(checkpoint_check, raw.split, b"\0")
        paths_list: list[str] = []
        for item in _cooperative_tuple(raw_items, check=checkpoint_check):
            if not item:
                continue
            decoded = _cooperative_call(
                checkpoint_check,
                item.decode,
                "utf-8",
                "strict",
            )
            _cooperative_call(checkpoint_check, paths_list.append, decoded)
        paths = _cooperative_call(checkpoint_check, tuple, paths_list)
    except UnicodeError:
        raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID") from None
    unique_paths = _cooperative_call(checkpoint_check, set, paths)
    if not paths or len(paths) != len(unique_paths):
        raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID")
    checkpoint_check()
    return _cooperative_call(checkpoint_check, frozenset, paths)


def _parse_github_time(
    value: object,
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> datetime:
    check()
    if not isinstance(value, str):
        raise OrchestrationFailure("GITHUB_TIMESTAMP_INVALID")
    match = _cooperative_call(
        check,
        re.fullmatch,
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value,
    )
    if match is None:
        raise OrchestrationFailure("GITHUB_TIMESTAMP_INVALID")
    try:
        naive = _cooperative_call(
            check,
            datetime.strptime,
            value,
            "%Y-%m-%dT%H:%M:%SZ",
        )
        parsed = _cooperative_call(check, naive.replace, tzinfo=timezone.utc)
    except ValueError:
        raise OrchestrationFailure("GITHUB_TIMESTAMP_INVALID") from None
    check()
    return parsed


def _reconstruct_evaluated_seal(receipt: Mapping[str, object]) -> SealBundle:
    runtime = receipt["runtime_identity"]
    if type(runtime) is not dict:
        raise ProtocolDefect("prior runtime identity type")
    context = IdentityContext(
        verified_main_sha=str(receipt["verified_main_sha"]),
        v1a_merge_sha=str(receipt["v1a_merge_sha"]),
        amendment_merge_sha=str(receipt["amendment_merge_sha"]),
        tls_amendment_merge_sha=str(receipt["tls_amendment_merge_sha"]),
        manifest_id=str(receipt["manifest_id"]),
        database_identity=receipt["database_identity"],  # type: ignore[arg-type]
        runtime_manifest_sha256=str(runtime["runtime_manifest_sha256"]),
    )
    readiness = receipt["readiness"]
    if type(readiness) is not dict:
        raise ProtocolDefect("prior readiness type")
    body = {
        **_fixed_context_fields(context),
        "rule_version": readiness["rule_version"],
        "status": readiness["status"],
        "amendment_merged_at_utc": readiness["amendment_merged_at_utc"],
        "scan_started_at": readiness["scan_started_at"],
        "first_candidate_session": readiness["first_candidate_session"],
        "boundary_session": readiness["boundary_session"],
        "boundary_as_of_at": readiness["boundary_as_of_at"],
        "selected_lineages": readiness["selected_lineages"],
        "cohort_trace": readiness["cohort_trace"],
        "counts": readiness["counts"],
        "reader_identity": READER_ROLE,
        "database_identity": receipt["database_identity"],
        "runtime_manifest_sha256": runtime["runtime_manifest_sha256"],
    }
    validate_readiness(body, readiness)
    run_body, run_digest = build_run_identity(
        readiness_identity_body=body, readiness=readiness
    )
    if run_digest != receipt["run_identity"]:
        raise ProtocolDefect("prior run identity mismatch")
    seal = build_seal(
        initial_authority_proof=receipt["authority_proof"],  # type: ignore[arg-type]
        readiness_identity_body=body,
        readiness=readiness,
        run_identity_body=run_body,
        run_identity=run_digest,
    )
    if seal.seal_record_sha256 != receipt["seal_record_sha256"]:
        raise ProtocolDefect("prior evaluated seal digest mismatch")
    return seal


def _validate_prior_readiness_time(
    readiness: object,
    *,
    expected_amendment_merged_at_utc: str,
) -> None:
    if type(readiness) is not dict:
        raise ProtocolDefect("prior readiness type")
    expected_amendment_time = require_utc_micro(
        expected_amendment_merged_at_utc,
        "authenticated amendment merge time",
    )
    amendment_time = require_utc_micro(
        readiness.get("amendment_merged_at_utc"), "prior amendment time"
    )
    if amendment_time != expected_amendment_time:
        raise ProtocolDefect("prior authenticated amendment time mismatch")
    scan_started_at = _parse_micro_utc(readiness.get("scan_started_at"))
    first = require_date(
        readiness.get("first_candidate_session"), "prior first candidate"
    )
    boundary = require_date(readiness.get("boundary_session"), "prior boundary")
    boundary_as_of_at = _parse_micro_utc(readiness.get("boundary_as_of_at"))
    amendment_at = _parse_micro_utc(amendment_time)
    boundary_local = boundary_as_of_at.astimezone(_new_york_zone())
    if (
        boundary < first
        or not amendment_at < boundary_as_of_at < scan_started_at
        or boundary_local.date().isoformat() != boundary
        or boundary_local.time().replace(tzinfo=None)
        != datetime.min.time().replace(hour=16)
    ):
        raise ProtocolDefect("prior readiness time relationship")


def _validate_terminal_negative(
    raw: bytes,
    path: str,
    value: Mapping[str, object],
    *,
    expected_amendment_merged_at_utc: str,
) -> ReceiptBytes:
    expected_amendment_time = require_utc_micro(
        expected_amendment_merged_at_utc,
        "authenticated amendment merge time",
    )
    schema = value.get("schema_version")
    if schema not in {
        "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1",
        "ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1",
    }:
        raise ProtocolDefect("not a consuming negative")
    expected_keys = PRE_CELL_KEYS if schema.endswith("PRE-CELL-INVALID-RECEIPT-1") else POST_EVAL_KEYS
    exact_keys(value, expected_keys, "prior consuming negative")
    digest = _validate_receipt_self_hash(value)
    manifest_id = _validate_amended_common(value)
    require_utc_micro(value["generated_at_utc"], "generated_at_utc")
    verified_main_sha = require_hex(
        value["verified_main_sha"], HEX40_RE, "verified_main_sha"
    )
    if verified_main_sha == "0" * 40:
        raise ProtocolDefect("prior consuming verified revision is null")
    if value["reader_identity"] != READER_ROLE:
        raise ProtocolDefect("prior consuming reader identity")
    sealed_run = require_hex(
        value["sealed_run_identity"], HEX64_RE, "sealed_run_identity"
    )
    seal_digest = require_hex(
        value["seal_record_sha256"], HEX64_RE, "seal_record_sha256"
    )
    if sealed_run == "0" * 64 or seal_digest == "0" * 64:
        raise ProtocolDefect("prior consuming seal binding is null")
    readiness = value["readiness"]
    exact_keys(readiness, READINESS_KEYS, "prior consuming readiness")
    if readiness["rule_version"] != "ATOM-V1B-MANIFEST-READINESS-1" or readiness["status"] != "READY":
        raise ProtocolDefect("prior consuming readiness status")
    _validate_prior_readiness_time(
        readiness,
        expected_amendment_merged_at_utc=expected_amendment_time,
    )
    first = require_date(readiness["first_candidate_session"], "prior first candidate")
    boundary = require_date(readiness["boundary_session"], "prior boundary")
    validate_selected_lineages(manifest_id, readiness["selected_lineages"])
    validate_counts(manifest_id, readiness["counts"])
    validate_cohort_trace(
        manifest_id,
        readiness["cohort_trace"],
        first_candidate_session=first,
        boundary_session=boundary,
        selected_lineages=readiness["selected_lineages"],
    )
    readiness_digest = require_hex(
        readiness["readiness_identity"], HEX64_RE, "readiness identity"
    )
    if readiness_digest == "0" * 64:
        raise ProtocolDefect("prior consuming readiness binding is null")
    if (
        value["evaluation_session"] != readiness["boundary_session"]
        or value["evaluation_as_of_at"] != readiness["boundary_as_of_at"]
        or value["verified_main_sha"] is None
        or value["v1a_merge_sha"] != V1A_MERGE_SHA
        or value["database_identity"] != DATABASE_IDENTITY
    ):
        raise ProtocolDefect("prior consuming receipt projection mismatch")
    if schema.startswith("ATOM-V1B-MANIFEST-PRE-CELL"):
        if (
            value["stage"] != "EVALUATION_STARTED"
            or value["reason_codes"] != ["EVALUATION_CONSTRUCTION_FAILED"]
        ):
            raise ProtocolDefect("prior PRE-CELL route")
        validate_authority_proof(value["authority_proof"])
    else:
        if (
            value["stage"] != "POST_EVALUATION_AUTHORITY_RECHECK"
            or value["reason_codes"] != ["FINAL_AUTHORITY_RECHECK_FAILED"]
        ):
            raise ProtocolDefect("prior POST route")
        if value["run_identity"] != sealed_run:
            raise ProtocolDefect("prior POST sealed run mismatch")
        validate_authority_proof(value["initial_authority_proof"])
    _require_zero_writes(value)
    expected_path = f"docs/v-1b-volatility-scorecard-negative-{manifest_id}-{digest}.json"
    if path != expected_path:
        raise ProtocolDefect("prior negative filename")
    return ReceiptBytes(raw, path, digest, str(schema), True)


def validate_prior_receipt(
    raw: bytes,
    path: str,
    *,
    expected_amendment_merged_at_utc: str,
    check: Callable[[], int] = _noop_deadline_check,
) -> PriorReceipt:
    check()
    expected_amendment_time = require_utc_micro(
        expected_amendment_merged_at_utc,
        "authenticated amendment merge time",
    )
    value = parse_canonical_line(raw, "prior receipt")
    check()
    schema = value.get("schema_version")
    if schema == "ATOM-V1B-MANIFEST-RECEIPT-1":
        seal = _reconstruct_evaluated_seal(value)
        validated = validate_receipt(
            raw,
            path,
            seal=seal,
            expected_dependency_versions=EXPECTED_DEPENDENCY_VERSIONS,
            expected_libpq_version=EXPECTED_LIBPQ_VERSION,
        )
        if value["verified_main_sha"] == "0" * 40:
            raise ProtocolDefect("prior evaluated verified revision is null")
        _validate_prior_readiness_time(
            value["readiness"],
            expected_amendment_merged_at_utc=expected_amendment_time,
        )
    elif (
        schema
        in {
            "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1",
            "ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1",
        }
        and value.get("seal_record_sha256") is not None
    ):
        validated = _validate_terminal_negative(
            raw,
            path,
            value,
            expected_amendment_merged_at_utc=expected_amendment_time,
        )
    else:
        validated = validate_receipt(raw, path)
    manifest_id = str(value["manifest_id"])
    receipt = PriorReceipt(
        path=path,
        raw=raw,
        manifest_id=manifest_id,
        schema_version=validated.schema_version,
        terminal=validated.terminal,
        receipt_sha256=validated.receipt_sha256,
        seal_record_sha256=(
            str(value["seal_record_sha256"])
            if value.get("seal_record_sha256") is not None
            else None
        ),
    )
    check()
    return receipt


def _receipt_paths_at(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    commit_sha: str,
) -> tuple[str, ...]:
    checkpoint_check = context.checker(clock_ns)
    raw = _git_read(
        context,
        clock_ns,
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        commit_sha,
        "--",
        "docs",
    )
    try:
        raw_items = _cooperative_call(checkpoint_check, raw.split, b"\0")
        keyed_paths: list[tuple[bytes, str]] = []
        for item in _cooperative_tuple(raw_items, check=checkpoint_check):
            if not item:
                continue
            decoded = _cooperative_call(
                checkpoint_check,
                item.decode,
                "utf-8",
                "strict",
            )
            matches = _cooperative_call(
                checkpoint_check,
                RECEIPT_PATH_RE.fullmatch,
                decoded,
            )
            if matches is None:
                continue
            encoded = _cooperative_call(
                checkpoint_check,
                decoded.encode,
                "utf-8",
            )
            _cooperative_call(
                checkpoint_check,
                keyed_paths.append,
                (encoded, decoded),
            )
    except UnicodeError:
        raise OrchestrationFailure("RECEIPT_TREE_INVALID") from None
    ordered = _cooperative_call(
        checkpoint_check,
        sorted,
        keyed_paths,
        key=lambda item: item[0],
    )
    paths = _cooperative_call(
        checkpoint_check,
        lambda: tuple(item[1] for item in ordered),
    )
    checkpoint_check()
    return paths


def _validate_terminal_partition(
    receipts: Sequence[PriorReceipt],
    *,
    check: Callable[[], int] = _noop_deadline_check,
) -> None:
    terminal_by_manifest: dict[str, PriorReceipt] = {}
    occupied: set[int] = set()
    paths: set[str] = set()
    digests: set[str] = set()
    for receipt in receipts:
        check()
        if receipt.path in paths or receipt.receipt_sha256 in digests:
            raise OrchestrationFailure("DUPLICATE_PRIOR_RECEIPT")
        paths.add(receipt.path)
        digests.add(receipt.receipt_sha256)
        if not receipt.terminal:
            continue
        if receipt.manifest_id in terminal_by_manifest:
            raise OrchestrationFailure("DUPLICATE_TERMINAL_MANIFEST")
        cell_orders = {cell.cell_order for cell in manifest_cells(receipt.manifest_id)}
        if occupied.intersection(cell_orders):
            raise OrchestrationFailure("INTERSECTING_TERMINAL_CELLS")
        occupied.update(cell_orders)
        terminal_by_manifest[receipt.manifest_id] = receipt
    check()


def _authenticate_fixed_merge(
    client: GithubClient,
    context: GithubDeadlineContext,
    execution_sha: str,
    merge_sha: str,
    pr_number: int,
    path: str,
    decision_id: str,
) -> datetime:
    clock_ns = client._seams.monotonic_ns
    if _checkpoint_git_run(
        context,
        clock_ns,
        "merge-base",
        "--is-ancestor",
        merge_sha,
        execution_sha,
        check=False,
    ).returncode != 0:
        raise OrchestrationFailure("REQUIRED_MERGE_NOT_ANCESTOR")
    commit = _github_commit(client, context, merge_sha)
    detail = _associated_merged_pr(
        client, context, merge_sha, expected_number=pr_number
    )
    merged_content = _authenticate_path(
        client, context, merge_sha, path, require_worktree=False
    )
    execution_content = _authenticate_path(
        client, context, execution_sha, path, require_worktree=False
    )
    if (
        merged_content != execution_content
        or decision_id.encode("utf-8") not in merged_content
    ):
        raise OrchestrationFailure("DECISION_DOCUMENT_INVALID")
    merged_at = _parse_github_time(detail.get("merged_at"))
    commit_data = commit.get("commit")
    assert isinstance(commit_data, Mapping)
    committer = commit_data.get("committer")
    if type(committer) is not dict:
        raise OrchestrationFailure("GITHUB_COMMIT_INVALID")
    committed_at = _parse_github_time(committer.get("date"))
    if merged_at != committed_at:
        raise OrchestrationFailure("MERGE_TIME_MISMATCH")
    return merged_at


def _require_first_parent_ancestor(
    context: GithubDeadlineContext,
    clock_ns: Callable[[], int],
    ancestor_sha: str,
    descendant_sha: str,
) -> None:
    chain = tuple(
        item
        for item in _git_ascii(
            context,
            clock_ns,
            "rev-list",
            "--first-parent",
            descendant_sha,
        ).splitlines()
        if item
    )
    if (
        HEX40_RE.fullmatch(ancestor_sha) is None
        or HEX40_RE.fullmatch(descendant_sha) is None
        or not chain
        or chain[0] != descendant_sha
        or ancestor_sha not in chain
    ):
        raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID")


def _authenticate_exact_amendment_merge(
    client: GithubClient,
    context: GithubDeadlineContext,
    execution_sha: str,
    *,
    predecessor_sha: str,
    merge_sha: str,
    pr_number: int,
    merged_at_text: str,
    path: str,
    decision_id: str,
    git_blob_sha1: str,
    raw_sha256: str,
) -> datetime:
    clock_ns = client._seams.monotonic_ns
    _require_first_parent_ancestor(
        context, clock_ns, predecessor_sha, merge_sha
    )
    _require_first_parent_ancestor(
        context, clock_ns, merge_sha, execution_sha
    )
    _github_commit(client, context, merge_sha)
    detail = _associated_merged_pr(
        client, context, merge_sha, expected_number=pr_number
    )
    author = detail.get("user")
    if (
        type(author) is not dict
        or author.get("id") != GITHUB_OWNER_ID
        or author.get("login") != GITHUB_OWNER_LOGIN
        or detail.get("merged_at") != merged_at_text
        or _commit_diff_paths(context, clock_ns, merge_sha)
        != frozenset({path})
    ):
        raise OrchestrationFailure("AMENDMENT_MERGE_INVALID")
    mode, blob_sha, merged_content = _local_tree_entry(
        context, clock_ns, merge_sha, path
    )
    if (
        mode != "100644"
        or blob_sha != git_blob_sha1
        or hashlib.sha256(merged_content).hexdigest() != raw_sha256
        or decision_id.encode("utf-8") not in merged_content
        or _github_blob(client, context, blob_sha) != merged_content
        or _authenticate_path(
            client,
            context,
            execution_sha,
            path,
            require_worktree=False,
        )
        != merged_content
    ):
        raise OrchestrationFailure("AMENDMENT_DOCUMENT_INVALID")
    return _parse_github_time(merged_at_text)


def _select_unique_v1b_implementation(
    chain: Sequence[str],
    changed_paths: Callable[[str], frozenset[str]],
) -> str:
    allowed = IMPLEMENTATION_PATHS | {CONDITIONAL_MIGRATION_PATH}
    after_corrective_amendment = False
    implementation_seen = False
    candidates: list[str] = []
    for commit_sha in chain:
        if HEX40_RE.fullmatch(commit_sha) is None:
            raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID")
        if commit_sha == CORRECTIVE_AMENDMENT_MERGE_SHA:
            after_corrective_amendment = True
        changed = changed_paths(commit_sha)
        if implementation_seen and changed.intersection(REUSED_PRIMITIVE_PATHS):
            raise OrchestrationFailure("REUSED_SOURCE_CHANGED_AFTER_IMPLEMENTATION")
        if not changed.intersection(allowed):
            continue
        if not after_corrective_amendment:
            raise OrchestrationFailure("PRE_AMENDMENT_IMPLEMENTATION")
        if not IMPLEMENTATION_PATHS.issubset(changed) or not changed <= allowed:
            raise OrchestrationFailure("IMPLEMENTATION_DIFF_INVALID")
        candidates.append(commit_sha)
        implementation_seen = True
    if not after_corrective_amendment:
        raise OrchestrationFailure("FIRST_PARENT_HISTORY_INVALID")
    if len(candidates) != 1:
        raise OrchestrationFailure("IMPLEMENTATION_MERGE_NOT_UNIQUE")
    return candidates[0]


def authenticate_immutable_repository_facts(
    client: GithubClient,
    context: GithubDeadlineContext,
    execution_sha: str,
) -> ImmutableRepositoryFacts:
    """Authenticate merge ancestry, exact source/tree bytes, and receipts."""

    clock_ns = client._seams.monotonic_ns
    checkpoint_check = context.checker(clock_ns)
    if _git_ascii(context, clock_ns, "rev-parse", "HEAD") != execution_sha:
        raise OrchestrationFailure("LOCAL_HEAD_MISMATCH")
    def authenticate_tree(commit_sha: str) -> None:
        checkpoint_check()
        authenticated = _github_commit(client, context, commit_sha)
        body = authenticated.get("commit")
        if type(body) is not dict or type(body.get("tree")) is not dict:
            raise OrchestrationFailure("GITHUB_COMMIT_INVALID")
        if body["tree"].get("sha") != _git_ascii(
            context,
            clock_ns,
            "rev-parse", f"{commit_sha}^{{tree}}"
        ):
            raise OrchestrationFailure("EXECUTION_TREE_MISMATCH")
        checkpoint_check()

    authenticate_tree(execution_sha)

    _authenticate_fixed_merge(
        client,
        context,
        execution_sha,
        V1A_MERGE_SHA,
        V1A_PR_NUMBER,
        CONTRACT_PATH,
        DECISION_ID,
    )
    _authenticate_fixed_merge(
        client,
        context,
        execution_sha,
        TLS_AMENDMENT_MERGE_SHA,
        TLS_AMENDMENT_PR_NUMBER,
        TLS_AMENDMENT_PATH,
        TLS_AMENDMENT_ID,
    )
    amendment_time = _authenticate_fixed_merge(
        client,
        context,
        execution_sha,
        AMENDMENT_MERGE_SHA,
        AMENDMENT_PR_NUMBER,
        AMENDMENT_PATH,
        AMENDMENT_ID,
    )
    _authenticate_fixed_merge(
        client,
        context,
        execution_sha,
        OPERATIONAL_AMENDMENT_MERGE_SHA,
        OPERATIONAL_AMENDMENT_PR_NUMBER,
        OPERATIONAL_AMENDMENT_PATH,
        OPERATIONAL_AMENDMENT_ID,
    )
    _require_first_parent_ancestor(
        context,
        clock_ns,
        V1A_MERGE_SHA,
        OPERATIONAL_AMENDMENT_MERGE_SHA,
    )
    _authenticate_exact_amendment_merge(
        client,
        context,
        execution_sha,
        predecessor_sha=OPERATIONAL_AMENDMENT_MERGE_SHA,
        merge_sha=BOOTSTRAP_AMENDMENT_MERGE_SHA,
        pr_number=BOOTSTRAP_AMENDMENT_PR_NUMBER,
        merged_at_text=BOOTSTRAP_AMENDMENT_MERGED_AT,
        path=BOOTSTRAP_AMENDMENT_PATH,
        decision_id=BOOTSTRAP_AMENDMENT_ID,
        git_blob_sha1=BOOTSTRAP_AMENDMENT_GIT_BLOB_SHA1,
        raw_sha256=BOOTSTRAP_AMENDMENT_SHA256,
    )
    corrective_time = _authenticate_exact_amendment_merge(
        client,
        context,
        execution_sha,
        predecessor_sha=BOOTSTRAP_AMENDMENT_MERGE_SHA,
        merge_sha=CORRECTIVE_AMENDMENT_MERGE_SHA,
        pr_number=CORRECTIVE_AMENDMENT_PR_NUMBER,
        merged_at_text=CORRECTIVE_AMENDMENT_MERGED_AT,
        path=CORRECTIVE_AMENDMENT_PATH,
        decision_id=CORRECTIVE_AMENDMENT_ID,
        git_blob_sha1=CORRECTIVE_AMENDMENT_GIT_BLOB_SHA1,
        raw_sha256=CORRECTIVE_AMENDMENT_SHA256,
    )

    chain_text = _git_ascii(
        context,
        clock_ns,
        "rev-list",
        "--first-parent",
        "--reverse",
        f"{V1A_MERGE_SHA}..{execution_sha}",
    )
    chain = tuple(item for item in chain_text.splitlines() if item)
    implementation_sha = _select_unique_v1b_implementation(
        chain,
        lambda commit_sha: _commit_diff_paths(
            context, clock_ns, commit_sha
        ),
    )
    _github_commit(client, context, implementation_sha)
    detail = _associated_merged_pr(
        client, context, implementation_sha, expected_number=None
    )
    author = detail.get("user")
    head = detail.get("head")
    head_sha = head.get("sha") if type(head) is dict else None
    created_at = _parse_github_time(detail.get("created_at"))
    if (
        type(author) is not dict
        or author.get("id") != GITHUB_OWNER_ID
        or author.get("login") != GITHUB_OWNER_LOGIN
        or type(head_sha) is not str
        or HEX40_RE.fullmatch(head_sha) is None
        or created_at <= corrective_time
    ):
        raise OrchestrationFailure("IMPLEMENTATION_PR_INVALID")
    _require_first_parent_ancestor(
        context,
        clock_ns,
        CORRECTIVE_AMENDMENT_MERGE_SHA,
        head_sha,
    )
    authenticate_tree(implementation_sha)

    receipt_integrations: dict[str, str] = {}
    for commit_sha in chain:
        checkpoint_check()
        for path in _commit_diff_paths(context, clock_ns, commit_sha):
            checkpoint_check()
            if RECEIPT_PATH_RE.fullmatch(path) is None:
                continue
            if path in receipt_integrations:
                raise OrchestrationFailure("RECEIPT_HISTORY_MUTATED")
            parent_sha = _git_ascii(
                context, clock_ns, "rev-parse", f"{commit_sha}^1"
            )
            if (
                _local_tree_entry_optional(context, clock_ns, parent_sha, path)
                is not None
                or _local_tree_entry_optional(context, clock_ns, commit_sha, path)
                is None
            ):
                raise OrchestrationFailure("RECEIPT_HISTORY_MUTATED")
            _associated_merged_pr(
                client, context, commit_sha, expected_number=None
            )
            _authenticate_bound_path(
                client, context, commit_sha, execution_sha, path
            )
            receipt_integrations[path] = commit_sha

    required_sources = set(IMPLEMENTATION_PATHS | REUSED_PRIMITIVE_PATHS)
    for path in sorted(required_sources, key=lambda item: item.encode("utf-8")):
        checkpoint_check()
        _authenticate_bound_path(
            client, context, implementation_sha, execution_sha, path
        )
    implementation_migration = _local_tree_entry_optional(
        context, clock_ns, implementation_sha, CONDITIONAL_MIGRATION_PATH
    )
    execution_migration = _local_tree_entry_optional(
        context, clock_ns, execution_sha, CONDITIONAL_MIGRATION_PATH
    )
    if implementation_migration != execution_migration:
        raise OrchestrationFailure("CONDITIONAL_MIGRATION_CHANGED")
    if implementation_migration is None:
        checkpoint_check()
        if os.path.lexists(CONDITIONAL_MIGRATION_PATH):
            raise OrchestrationFailure("CONDITIONAL_MIGRATION_WORKTREE_CHANGED")
        checkpoint_check()
    else:
        _authenticate_bound_path(
            client,
            context,
            implementation_sha,
            execution_sha,
            CONDITIONAL_MIGRATION_PATH,
        )
    for _role, path, size, digest in EVIDENCE_ARTIFACTS:
        checkpoint_check()
        raw = _authenticate_path(
            client, context, execution_sha, path, require_worktree=False
        )
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise OrchestrationFailure("EVIDENCE_ARTIFACT_INVALID")
        checkpoint_check()

    expected_amendment_time = timestamp_utc(amendment_time)
    receipts: list[PriorReceipt] = []
    for path in _receipt_paths_at(context, clock_ns, execution_sha):
        checkpoint_check()
        raw = _authenticate_path(
            client, context, execution_sha, path, require_worktree=False
        )
        receipts.append(
            validate_prior_receipt(
                raw,
                path,
                expected_amendment_merged_at_utc=expected_amendment_time,
                check=checkpoint_check,
            )
        )
    _validate_terminal_partition(receipts, check=checkpoint_check)
    history_projection: list[Mapping[str, object]] = []
    for receipt in receipts:
        checkpoint_check()
        history_projection.append({
            "manifest_id": receipt.manifest_id,
            "path": receipt.path,
            "receipt_sha256": receipt.receipt_sha256,
            "schema_version": receipt.schema_version,
            "seal_record_sha256": receipt.seal_record_sha256,
            "terminal": receipt.terminal,
        })
    history_sha256 = canonical_sha256(history_projection)
    checkpoint_check()
    return ImmutableRepositoryFacts(
        execution_sha=execution_sha,
        implementation_merge_sha=implementation_sha,
        amendment_merged_at_utc=timestamp_utc(amendment_time),
        receipts=tuple(receipts),
        history_sha256=history_sha256,
    )


# ---------------------------------------------------------------------------
# State machine, sealing, evaluation, and exact receipt routing
# ---------------------------------------------------------------------------


class FinalAuthorityRefusal(OrchestrationFailure):
    pass


class EvaluationConstructionRefusal(OrchestrationFailure):
    pass


def _approved_components(checkpoint: RepositoryCheckpoint) -> Mapping[str, object]:
    try:
        payload = checkpoint.selection.current.payload
        provenance = payload["provenance"]
        components = provenance["runtime_artifact_components"]
    except (KeyError, TypeError):
        raise OrchestrationFailure("APPROVED_COMPONENTS_MISSING") from None
    if type(components) is not dict or set(components) != set(RUNTIME_COMPONENT_KEYS):
        raise OrchestrationFailure("APPROVED_COMPONENTS_INVALID")
    for key in RUNTIME_COMPONENT_KEYS:
        if type(components[key]) is not str or HEX64_RE.fullmatch(components[key]) is None:
            raise OrchestrationFailure("APPROVED_COMPONENTS_INVALID")
    return components


def _validate_checkpoint(
    checkpoint: RepositoryCheckpoint,
    *,
    execution_sha: str,
    manifest_id: str,
    initial: RepositoryCheckpoint | None,
    check: Callable[[], int] = _noop_deadline_check,
) -> None:
    check()
    if (
        checkpoint.execution_sha != execution_sha
        or checkpoint.facts.execution_sha != execution_sha
        or checkpoint.selection.current.payload["provenance"]["execution_source_sha"]
        != execution_sha
        or checkpoint.selection.current.window["execution_source_sha"]
        != execution_sha
        or checkpoint.selection.current.window["manifest_id"] != manifest_id
        or checkpoint.facts.implementation_merge_sha
        in {
            OPERATIONAL_AMENDMENT_MERGE_SHA,
            BOOTSTRAP_AMENDMENT_MERGE_SHA,
            CORRECTIVE_AMENDMENT_MERGE_SHA,
        }
    ):
        raise OrchestrationFailure("REPOSITORY_CHECKPOINT_INVALID")
    require_utc_micro(
        checkpoint.facts.amendment_merged_at_utc,
        "authenticated amendment merge time",
    )
    check()
    _approved_components(checkpoint)
    _validate_terminal_partition(checkpoint.facts.receipts, check=check)
    if initial is not None:
        # Compare only already-authenticated immutable projections and their
        # collision-resistant canonical-body/history digests.  Re-walking raw
        # receipt/comment bytes here would duplicate the validated endpoint
        # work and make the deadline depend on one monolithic bytes equality.
        current = checkpoint.selection.current
        initial_current = initial.selection.current
        review = checkpoint.selection.current_review
        initial_review = initial.selection.current_review
        check()
        current_body = _checked_sha256_bytes(current.canonical_body, check=check)
        initial_current_body = _checked_sha256_bytes(
            initial_current.canonical_body, check=check
        )
        review_body = _checked_sha256_bytes(review.canonical_body, check=check)
        initial_review_body = _checked_sha256_bytes(
            initial_review.canonical_body, check=check
        )
        fingerprints = checkpoint.selection.repository_fingerprints
        initial_fingerprints = initial.selection.repository_fingerprints
        if (
            checkpoint.execution_sha != initial.execution_sha
            or checkpoint.facts.execution_sha != initial.facts.execution_sha
            or checkpoint.facts.implementation_merge_sha
            != initial.facts.implementation_merge_sha
            or checkpoint.facts.amendment_merged_at_utc
            != initial.facts.amendment_merged_at_utc
            or checkpoint.facts.history_sha256 != initial.facts.history_sha256
            or current.comment_id != initial_current.comment_id
            or current.created_at != initial_current.created_at
            or current.review_comment_id != initial_current.review_comment_id
            or current.reviewer_user_id != initial_current.reviewer_user_id
            or current.reviewer_login != initial_current.reviewer_login
            or current_body != initial_current_body
            or review.comment_id != initial_review.comment_id
            or review.author_id != initial_review.author_id
            or review.author_login != initial_review.author_login
            or review.created_at != initial_review.created_at
            or review.approval_payload_sha256
            != initial_review.approval_payload_sha256
            or review_body != initial_review_body
            or len(fingerprints) != len(initial_fingerprints)
        ):
            raise OrchestrationFailure("REPOSITORY_CHECKPOINT_CHANGED")
        for observed, expected in zip(
            fingerprints, initial_fingerprints, strict=True
        ):
            check()
            if observed != expected:
                raise OrchestrationFailure("REPOSITORY_CHECKPOINT_CHANGED")
    check()


def _terminal_receipts(facts: ImmutableRepositoryFacts) -> Mapping[str, PriorReceipt]:
    result: dict[str, PriorReceipt] = {}
    for receipt in facts.receipts:
        if receipt.terminal:
            if receipt.manifest_id in result:
                raise OrchestrationFailure("DUPLICATE_TERMINAL_MANIFEST")
            result[receipt.manifest_id] = receipt
    return MappingProxyType(result)


def _authorize_prior_history(
    invocation: Invocation,
    seal: SealBundle | None,
    checkpoint: RepositoryCheckpoint,
) -> str | None:
    terminals = _terminal_receipts(checkpoint.facts)
    target_orders = {
        cell.cell_order for cell in manifest_cells(invocation.manifest_id)
    }
    for prior_manifest in terminals:
        prior_orders = {
            cell.cell_order for cell in manifest_cells(prior_manifest)
        }
        if target_orders.intersection(prior_orders):
            raise OrchestrationFailure("MANIFEST_CELL_ALREADY_TERMINAL")
    if invocation.manifest_id != EARLY_MANIFEST_ID and EARLY_MANIFEST_ID not in terminals:
        return "WAIT_FIRST_MANIFEST"
    if seal is not None:
        for receipt in checkpoint.facts.receipts:
            if receipt.seal_record_sha256 == seal.seal_record_sha256:
                raise OrchestrationFailure("RECOVERY_ALREADY_TERMINAL")
    return None


def _runtime_identity(state: RuntimeState) -> Mapping[str, object]:
    validate_runtime_identity(
        dict(state.identity),
        expected_dependency_versions=EXPECTED_DEPENDENCY_VERSIONS,
        expected_libpq_version=EXPECTED_LIBPQ_VERSION,
    )
    if (
        state.identity["runtime_manifest_sha256"]
        != state.frozen.runtime_manifest_sha256
        or canonical_json(state.frozen.runtime_manifest_body)
        != canonical_json(
            {
                key: state.identity[key]
                for key in RUNTIME_IDENTITY_KEYS
                if key != "runtime_manifest_sha256"
            }
        )
    ):
        raise OrchestrationFailure("RUNTIME_IDENTITY_INVALID")
    return state.identity


def _verify_runtime_remeasurement(
    initial: RuntimeState,
    current: RuntimeState,
    approved: Mapping[str, object],
    *,
    check: Callable[[], object] | None = None,
) -> None:
    _cooperative_check(check)
    verify_approved_artifacts(
        current.measurement,
        approved,
        check=check,
    )
    verify_runtime_unchanged(
        initial.frozen,
        current.frozen,
        check=check,
    )
    _cooperative_call(check, _runtime_identity, current)
    initial_identity = _cooperative_call(check, canonical_json, initial.identity)
    current_identity = _cooperative_call(check, canonical_json, current.identity)
    if initial_identity != current_identity:
        raise OrchestrationFailure("RUNTIME_CHANGED")
    _cooperative_check(check)


def _parse_micro_utc(value: str) -> datetime:
    require_utc_micro(value, "UTC timestamp")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )


def _evidence_first_date(
    manifest_id: str,
    evidence: EvidencePopulation,
    completed_candidates: Sequence[CalendarSession],
    primitives: V4Primitives,
) -> date:
    if not completed_candidates:
        raise ProtocolDefect("evidence calendar requires a completed candidate")
    latest_as_of = _utc(completed_candidates[-1].market_close)
    fallback = completed_candidates[0].session_date
    cutoffs: list[datetime] = []
    specs = manifest_cells(manifest_id)
    family_horizons = {
        spec.horizon for spec in specs if spec.forecaster == "FAMILY-VOL"
    }
    for row in evidence.family_rows:
        if (
            row.horizon in family_horizons
            and row.formula_version == "realized-volatility-v1"
            and family_forecast_is_admissible(row, latest_as_of)
            and family_outcome_is_available(row, latest_as_of)
        ):
            cutoffs.append(_epoch_utc(row.cutoff_epoch))
    # V9 lineage is selected independently at every candidate.  A cohort that
    # controls an earlier candidate can rotate away by the latest candidate;
    # its valid historical sessions must still be present in the full XNYS
    # schedule used to prove that earlier boundary.
    for candidate in completed_candidates:
        candidate_as_of = _utc(candidate.market_close)
        for spec in specs:
            if spec.forecaster != "V9-VOL":
                continue
            lineage = _select_lineage(spec, evidence, candidate_as_of)
            if lineage == v9_sentinel_lineage(spec.horizon):
                continue
            for opaque_row in evidence.v9_rows:
                if (
                    opaque_row.horizon == spec.horizon
                    and _lineage_from_v9_row(opaque_row) == lineage
                ):
                    # A forecast outside this candidate's population cannot
                    # make its opaque outcome control calendar hydration.
                    if (
                        _utc(opaque_row.target_endpoint) > candidate_as_of
                        or not v9_forecast_is_admissible(
                            opaque_row, candidate_as_of
                        )
                    ):
                        continue
                    row = _materialize_v9_row(
                        opaque_row, primitives, as_of=candidate_as_of
                    )
                    if v9_outcome_is_available(row, candidate_as_of):
                        cutoffs.append(_utc(row.cutoff_at))
    if not cutoffs:
        return fallback
    return min(cutoffs).astimezone(_new_york_zone()).date()


def _readiness_parts(
    *,
    state: InvocationState,
    scan: ScanResult,
    evidence: EvidencePopulation,
    completed: Sequence[CalendarSession],
    full_sessions: Sequence[CalendarSession],
    primitives: V4Primitives,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], str]:
    checkpoint = state.checkpoint
    runtime = state.runtime
    snapshot = state.snapshot
    boundary = scan.boundary
    if checkpoint is None or runtime is None or snapshot is None or boundary is None:
        raise ProtocolDefect("incomplete READY state")
    if scan.first_candidate_session is None:
        raise ProtocolDefect("READY scan has no first candidate")
    counts = [item.public(require_ready=True) for item in boundary.counts]
    selected = [json_clone(item) for item in boundary.selected_lineages]
    trace = [json_clone(item) for item in boundary.cohort_trace]
    context = IdentityContext(
        verified_main_sha=checkpoint.execution_sha,
        v1a_merge_sha=V1A_MERGE_SHA,
        amendment_merge_sha=AMENDMENT_MERGE_SHA,
        tls_amendment_merge_sha=TLS_AMENDMENT_MERGE_SHA,
        manifest_id=state.invocation.manifest_id,
        database_identity=DATABASE_IDENTITY,
        runtime_manifest_sha256=runtime.frozen.runtime_manifest_sha256,
    )

    def semantic_validate(body: Mapping[str, object]) -> None:
        repeated = scan_manifest_candidates(
            state.invocation.manifest_id,
            evidence,
            completed,
            full_sessions,
            primitives,
        )
        candidate = repeated.boundary
        if candidate is None or repeated.first_candidate_session is None:
            raise ProtocolDefect("semantic READY reconstruction missing")
        expected = {
            "scan_started_at": timestamp_utc(snapshot.scan_started_at),
            "first_candidate_session": repeated.first_candidate_session.isoformat(),
            "boundary_session": candidate.session.session_date.isoformat(),
            "boundary_as_of_at": timestamp_utc(candidate.session.market_close),
            "selected_lineages": [json_clone(item) for item in candidate.selected_lineages],
            "cohort_trace": [json_clone(item) for item in candidate.cohort_trace],
            "counts": [item.public(require_ready=True) for item in candidate.counts],
        }
        for key, value in expected.items():
            if body[key] != value:
                raise ProtocolDefect("semantic earliest READY mismatch")

    readiness_body, readiness = build_readiness(
        context=context,
        amendment_merged_at_utc=checkpoint.facts.amendment_merged_at_utc,
        scan_started_at=timestamp_utc(snapshot.scan_started_at),
        first_candidate_session=scan.first_candidate_session.isoformat(),
        boundary_session=boundary.session.session_date.isoformat(),
        boundary_as_of_at=timestamp_utc(boundary.session.market_close),
        selected_lineages=selected,
        cohort_trace=trace,
        counts=counts,
        semantic_ready_validator=semantic_validate,
    )
    run_body, run_identity = build_run_identity(
        readiness_identity_body=readiness_body, readiness=readiness
    )
    return readiness_body, readiness, run_body, run_identity


def _verify_recovery_identity(
    state: InvocationState,
    rebuilt: tuple[dict[str, object], dict[str, object], dict[str, object], str],
) -> None:
    seal = state.seal
    snapshot = state.snapshot
    if seal is None or snapshot is None:
        raise ProtocolDefect("recovery state missing")
    record = seal.record()
    readiness_body, readiness, run_body, run_identity = rebuilt
    if (
        canonical_json(readiness_body)
        != canonical_json(record["readiness_identity_body"])
        or canonical_json(readiness) != canonical_json(record["readiness"])
        or canonical_json(run_body) != canonical_json(record["run_identity_body"])
        or run_identity != record["run_identity"]
        or snapshot.initial_authority_proof != record["initial_authority_proof"]
    ):
        raise ProtocolDefect("recovery sealed identity mismatch")
    validate_seal(
        record,
        expected_manifest_id=state.invocation.manifest_id,
        expected_canonical_bytes=seal.canonical_bytes,
    )


def _hold_line(manifest_id: str) -> bytes:
    return canonical_line(
        {"manifest_id": manifest_id, "mode": "V1B", "readiness_status": "HOLD"}
    )


def _wait_line(manifest_id: str) -> bytes:
    return canonical_line(
        {
            "manifest_id": manifest_id,
            "mode": "V1B",
            "readiness_status": "WAIT_FIRST_MANIFEST",
        }
    )


def _emit_blocked(state: InvocationState, dependencies: OrchestrationDependencies) -> int:
    checkpoint = state.checkpoint
    snapshot = state.snapshot
    parsed = snapshot.parsed if snapshot is not None else None
    proof = snapshot.initial_authority_proof if snapshot is not None else None
    receipt = build_blocked_receipt(
        manifest_id=state.invocation.manifest_id,
        generated_at_utc=timestamp_utc(dependencies.utc_now()),
        observed_main_sha=checkpoint.execution_sha if checkpoint else None,
        expected_main_sha=state.expected_sha,
        observed_v1a_merge_sha=V1A_MERGE_SHA if checkpoint else None,
        observed_user=getattr(parsed, "user", None),
        observed_database=getattr(parsed, "dbname", None),
        observed_effective_host=getattr(parsed, "host", None),
        project_binding_verified=(
            proof.get("project_binding_verified") if isinstance(proof, Mapping) else None
        ),
        read_only=(True if snapshot is not None else None),
        unverified_merge_identities=(
            frozenset() if checkpoint else frozenset({"amendment", "tls"})
        ),
    )
    _attempt_stdout(dependencies.write_stdout, receipt.canonical_bytes)
    return 1


def _emit_pre_cell(state: InvocationState, dependencies: OrchestrationDependencies) -> int:
    checkpoint = state.checkpoint
    seal = state.seal if state.recovery_accepted or state.phase in {
        InvocationPhase.SEALED,
        InvocationPhase.TRUTHFUL_CELLS,
        InvocationPhase.FINISHED,
    } else None
    if seal is not None:
        record = seal.record()
        rb = record["readiness_identity_body"]
        readiness = record["readiness"]
        verified = rb["verified_main_sha"]
        v1a = rb["v1a_merge_sha"]
        evaluation_session = readiness["boundary_session"]
        evaluation_as_of = readiness["boundary_as_of_at"]
        database_identity = rb["database_identity"]
        authority = record["initial_authority_proof"]
    else:
        verified = checkpoint.execution_sha if checkpoint else state.expected_sha
        if verified is None or HEX40_RE.fullmatch(verified) is None:
            return _emit_blocked(state, dependencies)
        v1a = V1A_MERGE_SHA if checkpoint else None
        evaluation_session = (
            state.boundary.session.session_date.isoformat()
            if state.boundary is not None
            else None
        )
        evaluation_as_of = (
            timestamp_utc(state.boundary.session.market_close)
            if state.boundary is not None
            else None
        )
        database_identity = (
            dict(DATABASE_IDENTITY) if state.snapshot is not None else None
        )
        authority = (
            state.snapshot.initial_authority_proof
            if state.snapshot is not None
            else None
        )
    receipt = build_pre_cell_invalid_receipt(
        manifest_id=state.invocation.manifest_id,
        generated_at_utc=timestamp_utc(dependencies.utc_now()),
        verified_main_sha=verified,
        v1a_merge_sha=v1a,
        evaluation_session=evaluation_session,
        evaluation_as_of_at=evaluation_as_of,
        database_identity=database_identity,
        authority_proof=authority,
        seal=seal,
    )
    _attempt_stdout(dependencies.write_stdout, receipt.canonical_bytes)
    return 1


def _emit_post_authority(
    state: InvocationState, dependencies: OrchestrationDependencies
) -> int:
    if state.seal is None:
        return _emit_pre_cell(state, dependencies)
    receipt = build_post_eval_authority_invalid_receipt(
        seal=state.seal,
        generated_at_utc=timestamp_utc(dependencies.utc_now()),
        database_identity=dict(DATABASE_IDENTITY),
    )
    _attempt_stdout(dependencies.write_stdout, receipt.canonical_bytes)
    return 1


def _ready_scan_projection(scan: ScanResult) -> Mapping[str, object]:
    """Freeze every value that can affect the selected boundary or cells."""

    boundary = scan.boundary
    if scan.first_candidate_session is None or boundary is None:
        raise ProtocolDefect("READY scan projection requires a boundary")
    populations: list[dict[str, object]] = []
    for population in boundary.populations:
        population.validate()
        populations.append(
            {
                "cell": population.spec.public(),
                "lineage_identity": json_clone(population.lineage_identity),
                "accounting": {
                    "n_input": population.n_input,
                    "n_unselected_lineage_rows": population.n_unselected_lineage_rows,
                    "n_inadmissible": population.n_inadmissible,
                    "n_non_rth": population.n_non_rth,
                    "n_overlap_excluded": population.n_overlap_excluded,
                    "n_null_or_nonfinite_excluded": population.n_null_or_nonfinite_excluded,
                    "n_nonpositive_prediction_excluded": population.n_nonpositive_prediction_excluded,
                    "n_kappa_unavailable": population.n_kappa_unavailable,
                    "n_persist20_unavailable": population.n_persist20_unavailable,
                    "n_unconditional_unavailable": population.n_unconditional_unavailable,
                    "protocol_defect": population.protocol_defect,
                },
                "windows": [
                    {
                        "session_date": window.session_date.isoformat(),
                        "cutoff_at": timestamp_utc(window.cutoff_at),
                        "record_identity": window.record_identity,
                        "predicted_volatility_bps": window.predicted_volatility_bps,
                        "realized_volatility_bps": window.realized_volatility_bps,
                        "outcome_available_at": timestamp_utc(
                            window.outcome_available_at
                        ),
                    }
                    for window in population.windows
                ],
                "regression": [
                    {
                        "record_identity": row.window.record_identity,
                        "persist_1": row.persist_1,
                        "persist_20": row.persist_20,
                        "unconditional": row.unconditional,
                        "seasonal": row.seasonal,
                    }
                    for row in population.regression
                ],
            }
        )
    return {
        "first_candidate_session": scan.first_candidate_session.isoformat(),
        "candidate_sessions": [
            {
                "session_date": item.session_date.isoformat(),
                "market_open": timestamp_utc(item.market_open),
                "market_close": timestamp_utc(item.market_close),
            }
            for item in scan.completed_candidates
        ],
        "boundary_session": boundary.session.session_date.isoformat(),
        "boundary_as_of_at": timestamp_utc(boundary.session.market_close),
        "selected_lineages": json_clone(boundary.selected_lineages),
        "cohort_trace": json_clone(boundary.cohort_trace),
        "counts": [item.public(require_ready=True) for item in boundary.counts],
        "populations": populations,
    }


def _run_snapshot(
    state: InvocationState,
    dependencies: OrchestrationDependencies,
) -> bytes:
    checkpoint = state.checkpoint
    runtime = state.runtime
    if checkpoint is None or runtime is None:
        raise OrchestrationFailure("INITIAL_STATE_MISSING")
    seal = state.seal if state.invocation.mode is InvocationMode.RECOVERY else None
    with dependencies.open_snapshot(seal) as snapshot:
        if not isinstance(snapshot, SnapshotSession):
            raise OrchestrationFailure("SNAPSHOT_TYPE_INVALID")
        state.snapshot = snapshot
        state.phase = InvocationPhase.SNAPSHOT_OPEN
        if seal is not None:
            sealed_scan = _parse_micro_utc(
                seal.record()["readiness_identity_body"]["scan_started_at"]
            )
            if snapshot.scan_started_at != sealed_scan or snapshot.recovery_started_at is None:
                raise OrchestrationFailure("RECOVERY_SNAPSHOT_INVALID")

        amendment_time = _parse_micro_utc(
            checkpoint.facts.amendment_merged_at_utc
        )
        calendar_start = amendment_time.astimezone(_new_york_zone()).date()
        calendar_end = snapshot.scan_started_at.astimezone(_new_york_zone()).date()
        candidate_schedule = dependencies.calendar_sessions(
            calendar_start, calendar_end
        )
        completed = enumerate_xnys_candidates(
            candidate_schedule,
            amendment_merged_at=amendment_time,
            scan_started_at=snapshot.scan_started_at,
        )
        if not completed:
            if seal is not None:
                raise OrchestrationFailure("RECOVERY_BOUNDARY_MISSING")
            return _hold_line(state.invocation.manifest_id)

        state.phase = InvocationPhase.EVIDENCE_READ
        evidence = dependencies.load_evidence(
            snapshot, completed[-1].market_close, seal is not None
        )
        earliest_date = _evidence_first_date(
            state.invocation.manifest_id,
            evidence,
            completed,
            dependencies.primitives,
        )
        full_schedule = qualifying_full_xnys_sessions(
            dependencies.calendar_sessions(earliest_date, completed[-1].session_date)
        )
        full_by_date = {item.session_date: item for item in full_schedule}
        if len(full_by_date) != len(full_schedule) or any(
            full_by_date.get(item.session_date) != item for item in completed
        ):
            raise ProtocolDefect("candidate/full-calendar mismatch")
        scan = scan_manifest_candidates(
            state.invocation.manifest_id,
            evidence,
            completed,
            full_schedule,
            dependencies.primitives,
        )
        if scan.boundary is None:
            if seal is not None:
                raise OrchestrationFailure("RECOVERY_BOUNDARY_NOT_READY")
            return _hold_line(state.invocation.manifest_id)
        state.boundary = scan.boundary
        frozen_scan_sha256 = canonical_sha256(_ready_scan_projection(scan))

        preseal = dependencies.repository_checkpoint(
            (
                AuthorityStage.SEALED_OR_ACCEPTED_RECOVERY_BEFORE_COMPLETE_CELLS
                if seal is not None
                else AuthorityStage.NEW_SEAL_AFTER_EVIDENCE_BEFORE_SEAL
            ),
            checkpoint.execution_sha,
            state.invocation.manifest_id,
            runtime,
            checkpoint,
            None,
        )
        _validate_checkpoint(
            preseal,
            execution_sha=checkpoint.execution_sha,
            manifest_id=state.invocation.manifest_id,
            initial=checkpoint,
        )
        measured = dependencies.remeasure_runtime(runtime, None)
        _verify_runtime_remeasurement(
            runtime, measured, _approved_components(checkpoint)
        )

        parts = _readiness_parts(
            state=state,
            scan=scan,
            evidence=evidence,
            completed=completed,
            full_sessions=full_schedule,
            primitives=dependencies.primitives,
        )
        if seal is not None:
            _verify_recovery_identity(state, parts)
            rendered = render_recovery_start_command(
                seal.manifest_id,
                seal.seal_record_sha256,
                seal.canonical_bytes,
            )
            state.phase = InvocationPhase.SEALED
        else:
            readiness_body, readiness, run_body, run_identity = parts
            candidate_seal = build_seal(
                initial_authority_proof=snapshot.initial_authority_proof,
                readiness_identity_body=readiness_body,
                readiness=readiness,
                run_identity_body=run_body,
                run_identity=run_identity,
            )
            rendered = render_recovery_start_command(
                candidate_seal.manifest_id,
                candidate_seal.seal_record_sha256,
                candidate_seal.canonical_bytes,
            )
            try:
                captured = dependencies.emit_seal(candidate_seal.canonical_bytes)
            except BaseException:
                # Some or all seal bytes may already be in the log sink.  A
                # negative receipt attempt would create ambiguous output.
                raise OutputSinkFailure() from None
            expected_capture = hashlib.sha256(candidate_seal.canonical_bytes).hexdigest()
            if captured != expected_capture:
                raise EvaluationConstructionRefusal("SEAL_CAPTURE_FAILED")
            state.seal = candidate_seal
            seal = candidate_seal
            state.phase = InvocationPhase.SEALED

        try:
            cells = [evaluate_cell(population) for population in scan.boundary.populations]
        except BaseException:
            raise EvaluationConstructionRefusal("CELL_EVALUATION_FAILED") from None
        state.phase = InvocationPhase.TRUTHFUL_CELLS

        try:
            repeated = scan_manifest_candidates(
                state.invocation.manifest_id,
                evidence,
                completed,
                full_schedule,
                dependencies.primitives,
            )
            if canonical_sha256(_ready_scan_projection(repeated)) != frozen_scan_sha256:
                raise ProtocolDefect("final population mismatch")
        except BaseException:
            raise EvaluationConstructionRefusal("FINAL_POPULATION_MISMATCH") from None

        try:
            final_authority: dict[str, object] | None = None
            final_runtime_verified = False

            def begin_final_checks_inside_checkpoint(
                final_context: GithubDeadlineContext,
                final_clock_ns: Callable[[], int],
            ) -> Callable[[Callable[[], object]], None]:
                nonlocal final_authority
                if final_authority is not None:
                    raise OrchestrationFailure("FINAL_DATABASE_AUTHORITY_REPEATED")
                # The final database authority query is step 5 of the closing
                # checkpoint: after the immutable GitHub candidate is fully
                # validated, but before closing trust/zone observations and
                # the last runtime measurement.
                check = final_context.checker(final_clock_ns)
                check()
                final_authority = snapshot.final_authority_check(
                    context=final_context,
                    clock_ns=final_clock_ns,
                )
                snapshot.close_after_final_authority()
                check()

                def finalize_runtime_inside_checkpoint(
                    runtime_check: Callable[[], object],
                ) -> None:
                    nonlocal final_runtime_verified
                    if final_runtime_verified:
                        raise OrchestrationFailure("FINAL_RUNTIME_REPEATED")
                    final_runtime = dependencies.remeasure_runtime(
                        runtime, runtime_check
                    )
                    _verify_runtime_remeasurement(
                        runtime,
                        final_runtime,
                        _approved_components(checkpoint),
                        check=runtime_check,
                    )
                    final_runtime_verified = True

                return finalize_runtime_inside_checkpoint

            final_checkpoint = dependencies.repository_checkpoint(
                AuthorityStage.FINAL_AFTER_COMPLETE_TRUTHFUL_CELLS,
                checkpoint.execution_sha,
                state.invocation.manifest_id,
                runtime,
                checkpoint,
                begin_final_checks_inside_checkpoint,
            )
            if final_authority is None or not final_runtime_verified:
                raise OrchestrationFailure("FINAL_RUNTIME_NOT_VERIFIED")
            # Production constructed and fully validated this checkpoint under
            # its shared 300-second context before invoking the runtime
            # finalizer.  Do not perform another material authority traversal
            # after that final mutable runtime observation.
            if not isinstance(final_checkpoint, RepositoryCheckpoint):
                raise OrchestrationFailure("FINAL_CHECKPOINT_MISSING")
        except BaseException:
            raise FinalAuthorityRefusal("FINAL_AUTHORITY_FAILED") from None

        try:
            if seal is None:
                raise EvaluationConstructionRefusal("SEAL_STATE_MISSING")
            # The generated timestamp is the only observation after the final
            # checkpoint's runtime measurement; receipt construction below is
            # otherwise entirely in memory.
            generated_at_utc = timestamp_utc(dependencies.utc_now())
            receipt = build_evaluated_receipt(
                seal=seal,
                generated_at_utc=generated_at_utc,
                runtime_identity=dict(_runtime_identity(runtime)),
                final_authority_proof=final_authority,
                cells=cells,
                expected_dependency_versions=EXPECTED_DEPENDENCY_VERSIONS,
                expected_libpq_version=EXPECTED_LIBPQ_VERSION,
            )
        except BaseException:
            raise EvaluationConstructionRefusal("RECEIPT_CONSTRUCTION_FAILED") from None
        state.phase = InvocationPhase.FINISHED
        return receipt.canonical_bytes


def run_scorecard(
    invocation: Invocation,
    recovery_seal: SealBundle | None,
    dependencies: OrchestrationDependencies,
) -> int:
    state = InvocationState(invocation=invocation, seal=recovery_seal)
    try:
        if (invocation.mode is InvocationMode.RECOVERY) != (
            recovery_seal is not None
        ):
            raise OrchestrationFailure("INVOCATION_RECOVERY_STATE_MISMATCH")
        dependencies.validate_startup(invocation)
        state.phase = InvocationPhase.STARTUP_VALIDATED
        execution = dependencies.execution_identity()
        state.expected_sha = execution.sha
        runtime = dependencies.prepare_runtime()
        state.runtime = runtime
        _runtime_identity(runtime)
        initial = dependencies.repository_checkpoint(
            (
                AuthorityStage.SEALED_OR_ACCEPTED_RECOVERY_BEFORE_COMPLETE_CELLS
                if recovery_seal is not None
                else AuthorityStage.NEW_SEAL_BEFORE_EVIDENCE
            ),
            execution.sha,
            invocation.manifest_id,
            runtime,
            None,
            None,
        )
        _validate_checkpoint(
            initial,
            execution_sha=execution.sha,
            manifest_id=invocation.manifest_id,
            initial=None,
        )
        state.checkpoint = initial
        state.phase = InvocationPhase.INITIAL_AUTHORITY
        verify_approved_artifacts(runtime.measurement, _approved_components(initial))
        if recovery_seal is not None:
            sealed_digest = recovery_seal.record()["readiness_identity_body"][
                "runtime_manifest_sha256"
            ]
            if runtime.frozen.runtime_manifest_sha256 != sealed_digest:
                raise OrchestrationFailure("RECOVERY_RUNTIME_MISMATCH")
        wait = _authorize_prior_history(invocation, recovery_seal, initial)
        state.terminal_exclusion_verified = True
        if wait is not None:
            if recovery_seal is not None:
                raise OrchestrationFailure("RECOVERY_FIRST_MANIFEST_MISSING")
            return (
                0
                if _attempt_stdout(
                    dependencies.write_stdout,
                    _wait_line(invocation.manifest_id),
                )
                else 1
            )
        output = _run_snapshot(state, dependencies)
        return 0 if _attempt_stdout(dependencies.write_stdout, output) else 1
    except OutputSinkFailure:
        return 1
    except CapacityRefusal:
        return _emit_blocked(state, dependencies)
    except FinalAuthorityRefusal:
        return _emit_post_authority(state, dependencies)
    except EvaluationConstructionRefusal:
        return _emit_pre_cell(state, dependencies)
    except DatabaseContractError:
        # A transaction-context exit can fail after the evaluator has produced
        # every truthful cell.  That database teardown failure is the one late
        # uncategorized path that retains POST-EVALUATION authority routing.
        if state.truthful_cells:
            return _emit_post_authority(state, dependencies)
        if (
            state.terminal_exclusion_verified and state.recovery_accepted
        ) or state.evidence_started:
            return _emit_pre_cell(state, dependencies)
        return _emit_blocked(state, dependencies)
    except BaseException:
        # Unclassified construction defects remain consuming PRE-CELL even if
        # cells happened to be present in memory; only the explicit final-
        # authority route and late database-context failure above may select
        # the POST-EVALUATION receipt.
        if (
            state.terminal_exclusion_verified and state.recovery_accepted
        ) or state.evidence_started:
            return _emit_pre_cell(state, dependencies)
        return _emit_blocked(state, dependencies)


# ---------------------------------------------------------------------------
# Production composition and strict public entry point
# ---------------------------------------------------------------------------


def _production_runtime_scalar_identity(
    *, check: Callable[[], object] | None = None
) -> Mapping[str, object]:
    """Observe every frozen scalar from the guarded, already-loaded process."""

    try:
        loaded_modules = _cooperative_call(check, getattr, sys, "modules")
        pq = _cooperative_call(
            check,
            loaded_modules.__getitem__,
            "psycopg.pq",
        )
        libpq_version = _cooperative_call(check, pq.version)
        libc_name, libc_version = _cooperative_call(check, platform.libc_ver)
        render_service_id = _cooperative_call(
            check,
            os.environ.get,
            "RENDER_SERVICE_ID",
        )
        python_version_env = _cooperative_call(
            check,
            os.environ.get,
            PYTHON_VERSION_ENV,
        )
        python_implementation = _cooperative_call(
            check,
            platform.python_implementation,
        )
        python_version = _cooperative_call(check, platform.python_version)
        platform_system = _cooperative_call(check, platform.system)
        platform_machine = _cooperative_call(check, platform.machine)
        _cooperative_check(check)
        python_cache_tag = sys.implementation.cache_tag
        _cooperative_check(check)
        byteorder = sys.byteorder
        _cooperative_check(check)
        float_radix = sys.float_info.radix
        _cooperative_check(check)
        float_mant_dig = sys.float_info.mant_dig
        _cooperative_check(check)
        float_max_exp = sys.float_info.max_exp
        _cooperative_check(check)
        float_rounds = sys.float_info.rounds
        _cooperative_check(check)
        scalar: dict[str, object] = {
            "render_service_id": render_service_id,
            "render_runtime": "python",
            "python_implementation": python_implementation,
            "python_version_source": PYTHON_VERSION_ENV,
            "python_version_env": python_version_env,
            "python_version": python_version,
            "python_cache_tag": python_cache_tag,
            "platform_system": platform_system,
            "platform_machine": platform_machine,
            "byteorder": byteorder,
            "libc_name": libc_name,
            "libc_version": libc_version,
            "float_radix": float_radix,
            "float_mant_dig": float_mant_dig,
            "float_max_exp": float_max_exp,
            "float_rounds": float_rounds,
            "libpq_version": libpq_version,
        }
        _cooperative_check(check)
    except BaseException:
        raise OrchestrationFailure("RUNTIME_SCALAR_OBSERVATION_FAILED") from None
    # Validate type/value together with the measured fields below; this early
    # comparison makes an unexpected platform fail before repository/network
    # or database access.
    expected = _cooperative_call(
        check,
        lambda: {
            "render_service_id": RENDER_SERVICE_ID,
            "render_runtime": "python",
            "python_implementation": "CPython",
            "python_version_source": PYTHON_VERSION_ENV,
            "python_version_env": EXPECTED_PYTHON_VERSION_TEXT,
            "python_version": EXPECTED_PYTHON_VERSION_TEXT,
            "python_cache_tag": "cpython-314",
            "platform_system": "Linux",
            "platform_machine": "x86_64",
            "byteorder": "little",
            "libc_name": "glibc",
            "libc_version": "2.36",
            "float_radix": 2,
            "float_mant_dig": 53,
            "float_max_exp": 1024,
            "float_rounds": 1,
            "libpq_version": EXPECTED_LIBPQ_VERSION,
        },
    )
    scalar_matches = _cooperative_call(check, lambda: scalar == expected)
    if not scalar_matches:
        raise OrchestrationFailure("RUNTIME_SCALAR_MISMATCH")
    return _cooperative_call(check, MappingProxyType, scalar)


def _runtime_state_from_measurement(
    plan: RuntimeArtifactPlan,
    measurement: RuntimeMeasurement,
    *,
    check: Callable[[], object] | None = None,
) -> RuntimeState:
    frozen = build_runtime_manifest(
        _production_runtime_scalar_identity(check=check),
        measurement,
        check=check,
    )
    _cooperative_check(check)
    identity = _cooperative_call(check, dict, frozen.runtime_manifest_body)
    identity["runtime_manifest_sha256"] = frozen.runtime_manifest_sha256
    _cooperative_check(check)
    _cooperative_call(
        check,
        validate_runtime_identity,
        identity,
        expected_dependency_versions=EXPECTED_DEPENDENCY_VERSIONS,
        expected_libpq_version=EXPECTED_LIBPQ_VERSION,
    )
    frozen_identity = _cooperative_call(check, MappingProxyType, identity)
    return _cooperative_call(
        check,
        RuntimeState,
        plan=plan,
        measurement=measurement,
        frozen=frozen,
        identity=frozen_identity,
    )


def _production_execution_identity() -> ExecutionIdentity:
    source = _production_source_identity()
    authorized = os.environ.get(AUTHORIZED_MAIN_ENV, "")
    return ExecutionIdentity(
        authorized_main_sha=authorized,
        render_git_commit=source.execution_source_sha,
        local_head_sha=source.execution_source_sha,
    )


def _as_utc_datetime(value: object) -> datetime:
    converter = getattr(value, "to_pydatetime", None)
    if callable(converter):
        value = converter()
    return _utc(value)  # type: ignore[arg-type]


def _production_calendar_reader(calendar: object) -> Callable[
    [date, date], Sequence[CalendarSession]
]:
    if getattr(calendar, "name", None) != "XNYS":
        raise OrchestrationFailure("XNYS_CALENDAR_INVALID")

    def read(start: date, end: date) -> Sequence[CalendarSession]:
        if _ZONEINFO_ISOLATION is None:
            raise OrchestrationFailure("ZONEINFO_ISOLATION_MISSING")
        _validate_zoneinfo_isolation(_ZONEINFO_ISOLATION)
        if (
            type(start) is not date
            or type(end) is not date
            or start > end
        ):
            raise OrchestrationFailure("XNYS_CALENDAR_RANGE_INVALID")
        try:
            labels = tuple(
                calendar.sessions_in_range(start.isoformat(), end.isoformat())
            )
            rows: list[CalendarSession] = []
            prior: date | None = None
            for label in labels:
                observed_date = label.date()
                if (
                    type(observed_date) is not date
                    or observed_date < start
                    or observed_date > end
                    or prior is not None
                    and observed_date <= prior
                    or calendar.is_session(label) is not True
                ):
                    raise ValueError("calendar label mismatch")
                opened = _as_utc_datetime(calendar.session_open(label))
                closed = _as_utc_datetime(calendar.session_close(label))
                if not opened < closed:
                    raise ValueError("calendar interval mismatch")
                rows.append(CalendarSession(observed_date, opened, closed))
                prior = observed_date
        except BaseException:
            raise OrchestrationFailure("XNYS_CALENDAR_READ_FAILED") from None
        return tuple(rows)

    return read


def build_production_dependencies(
    startup_observation: StartupObservation,
) -> OrchestrationDependencies:
    """Compose all production seams after the common isolation guard passes.

    This function performs local/runtime initialization only.  It performs no
    GitHub request and opens no database connection; those remain ordered by
    ``run_scorecard`` and its explicit state machine.
    """

    # Load the complete closure under the one forced tzdata source, then observe
    # the sole CPython default cafile before taking the invocation baseline.
    initialized = _initialize_runtime_for_measurement()
    xnys_calendar = initialized.xnys_calendar
    home_dir = initialized.home_dir
    v4a = initialized.v4a
    v4b = initialized.v4b
    v4c = initialized.v4c
    psycopg_module = initialized.psycopg_module
    conninfo_module = initialized.conninfo_module
    zoneinfo_isolation = initialized.zoneinfo_isolation
    github_tls_trust = observe_github_tls_trust()
    # Trust-path resolution/PEM decoding may initialize lazy stdlib modules.
    # The complete baseline begins only after those effects have occurred.
    frozen_module_names = _cooperative_module_snapshot()
    plan = collect_runtime_artifact_plan(
        EXPECTED_DEPENDENCY_VERSIONS, module_names=frozen_module_names
    )
    measurement = measure_runtime_artifacts(plan, include_dispatch=True)
    runtime = _runtime_state_from_measurement(plan, measurement)
    github_ssl_context = build_github_ssl_context(github_tls_trust)

    # The cadata-only context may initialize ssl/native internals.  Its complete
    # immediate remeasurement must remain byte-identical before the client can
    # create a resolver or read the PAT.
    post_client_plan = collect_runtime_artifact_plan(
        EXPECTED_DEPENDENCY_VERSIONS,
        module_names=_cooperative_module_snapshot(),
    )
    post_client_measurement = measure_runtime_artifacts(
        post_client_plan, include_dispatch=True
    )
    post_client_runtime = _runtime_state_from_measurement(
        post_client_plan, post_client_measurement
    )
    _verify_runtime_remeasurement(
        runtime, post_client_runtime, runtime.measurement.components.public()
    )
    github_client = GithubClient.for_frozen_runtime(
        plan=runtime.plan,
        measurement=runtime.measurement,
        ssl_context=github_ssl_context,
    )

    primitives = V4Primitives(
        governed_accuracy_evidence=v4b.governed_accuracy_evidence,
        apply_forecast_commit_proof=v4a.V4AWriter._apply_commit_proof,
        calibration_observation=v4c.CalibrationObservation,
        calibrate_scale=v4c.calibrate_scale,
        select_non_overlapping=v4a.select_non_overlapping,
        deserialize_forecast_record=v4a.deserialize_forecast_record,
        deserialize_outcome_record=v4a.deserialize_outcome_record,
        canonical_target_identity=v4a.canonical_target_identity,
    )

    def validate_startup(invocation: Invocation) -> None:
        validate_startup_observation(
            startup_observation,
            mode=(
                "recovery"
                if invocation.mode is InvocationMode.RECOVERY
                else "normal"
            ),
            manifest_id=invocation.manifest_id,
            recovery_seal_path=invocation.recovery_path,
        )

    def prepare_runtime() -> RuntimeState:
        return runtime

    def remeasure_runtime(
        _initial: RuntimeState,
        check: Callable[[], object] | None,
    ) -> RuntimeState:
        current_plan = collect_runtime_artifact_plan(
            EXPECTED_DEPENDENCY_VERSIONS,
            module_names=_cooperative_module_snapshot(check=check),
            check=check,
        )
        current_measurement = measure_runtime_artifacts(
            current_plan, include_dispatch=True, check=check
        )
        _cooperative_check(check)
        current_state = _runtime_state_from_measurement(
            current_plan, current_measurement, check=check
        )
        _cooperative_check(check)
        return current_state

    def repository_checkpoint(
        _stage: AuthorityStage,
        execution_sha: str,
        manifest_id: str,
        current_runtime: RuntimeState,
        initial: RepositoryCheckpoint | None,
        finalizer: Callable[
            [GithubDeadlineContext, Callable[[], int]],
            Callable[[Callable[[], object]], None],
        ]
        | None,
    ) -> RepositoryCheckpoint:
        facts: list[ImmutableRepositoryFacts] = []
        completed: list[RepositoryCheckpoint] = []
        local_trust_public = github_tls_trust.public()

        def approved_trust_from_selection(
            selection: ApprovalSelection,
            *,
            check: Callable[[], object] | None = None,
        ) -> Mapping[str, object]:
            provenance = _cooperative_call(
                check,
                selection.current.payload.get,
                "provenance",
            )
            if type(provenance) is not dict:
                raise OrchestrationFailure("GITHUB_TLS_TRUST_APPROVAL_INVALID")
            approved = _cooperative_call(
                check,
                provenance.get,
                "github_tls_trust",
            )
            if type(approved) is not dict:
                raise OrchestrationFailure("GITHUB_TLS_TRUST_APPROVAL_INVALID")
            _cooperative_check(check)
            return approved

        def checkpoint_preflight(context: GithubDeadlineContext) -> None:
            check = context.checker(github_client._seams.monotonic_ns)
            _validate_zoneinfo_isolation(zoneinfo_isolation, check=check)
            if initial is not None:
                observed = observe_github_tls_trust(check=check)
                verify_github_tls_trust(
                    observed,
                    approved_trust_from_selection(
                        initial.selection,
                        check=check,
                    ),
                    check=check,
                )

        def artifact_validator(value: object) -> object:
            if type(value) is not dict:
                raise OrchestrationFailure("APPROVED_COMPONENTS_INVALID")
            verify_approved_artifacts(current_runtime.measurement, value)
            return value

        def immutable_validator(
            client: GithubClient,
            context: GithubDeadlineContext,
            sha: str,
        ) -> None:
            facts.append(
                authenticate_immutable_repository_facts(client, context, sha)
            )

        def complete_checkpoint(
            selection: ApprovalSelection,
            context: GithubDeadlineContext,
        ) -> None:
            if len(facts) != 1 or completed:
                raise OrchestrationFailure("IMMUTABLE_FACTS_MISSING")
            checkpoint = RepositoryCheckpoint(
                execution_sha, selection, facts[0]
            )
            _validate_checkpoint(
                checkpoint,
                execution_sha=execution_sha,
                manifest_id=manifest_id,
                initial=initial,
                check=context.checker(github_client._seams.monotonic_ns),
            )
            checkpoint_check = context.checker(
                github_client._seams.monotonic_ns
            )
            runtime_finalizer: Callable[[Callable[[], object]], None] | None = None
            if finalizer is not None:
                # Step 5: the caller performs the existing final database
                # authority query only after the candidate checkpoint has
                # passed, and returns the step-7 runtime finalizer.
                runtime_finalizer = finalizer(
                    context,
                    github_client._seams.monotonic_ns,
                )
                if not callable(runtime_finalizer):
                    raise OrchestrationFailure("FINAL_RUNTIME_UNWIRED")
                checkpoint_check()
            closing_trust = observe_github_tls_trust(check=checkpoint_check)
            verify_github_tls_trust(
                closing_trust,
                approved_trust_from_selection(
                    selection,
                    check=checkpoint_check,
                ),
                check=checkpoint_check,
            )
            _validate_zoneinfo_isolation(
                zoneinfo_isolation,
                check=checkpoint_check,
            )
            # For the final stage this is the runtime byte/mapping/dispatch
            # remeasurement.  Repository candidate validation, the final DB
            # authority query, and closing CA/zone checks all precede it; only
            # a final monotonic check and in-memory return construction follow.
            if runtime_finalizer is not None:
                runtime_finalizer(checkpoint_check)
            context.check(github_client._seams.monotonic_ns)
            completed.append(checkpoint)

        verify_github_checkpoint(
            client=github_client,
            expected_execution_sha=execution_sha,
            manifest_id=manifest_id,
            artifact_components_validator=artifact_validator,
            immutable_fact_validator=immutable_validator,
            initial_selection=(initial.selection if initial is not None else None),
            local_tls_trust=local_trust_public,
            preflight=checkpoint_preflight,
            finalizer=complete_checkpoint,
        )
        if len(completed) != 1:
            raise OrchestrationFailure("IMMUTABLE_FACTS_MISSING")
        return completed[0]

    repository_root = Path(os.getcwd())

    def local_ca_blob(
        path: str,
        *,
        context: GithubDeadlineContext | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> GitBlobObservation:
        local_context = (
            GithubDeadlineContext.begin_checkpoint(clock_ns)
            if context is None
            else context
        )
        mode, blob, content = _local_tree_entry(
            local_context, clock_ns, "HEAD", path
        )
        return GitBlobObservation(mode, blob, content)

    @contextmanager
    def open_snapshot(seal: SealBundle | None) -> Iterator[SnapshotSession]:
        stage = (
            DatabaseFailureStage.SEALED_OR_RECOVERY
            if seal is not None
            else DatabaseFailureStage.NEW_BEFORE_EVIDENCE
        )
        parsed = validate_database_environment(
            os.environ,
            conninfo_parser=conninfo_module.conninfo_to_dict,
            home_dir=home_dir,
            stage=stage,
        )
        initial_ca = verify_pinned_ca(
            repository_root,
            git_blob_reader=local_ca_blob,
            cwd=repository_root,
            stage=stage,
        )

        def ca_recheck(
            current_stage: DatabaseFailureStage,
        ) -> PinnedCAObservation:
            return verify_pinned_ca(
                repository_root,
                git_blob_reader=local_ca_blob,
                cwd=repository_root,
                stage=current_stage,
            )

        def ca_recheck_deadline(
            current_stage: DatabaseFailureStage,
            shared_context: GithubDeadlineContext,
            shared_clock_ns: Callable[[], int],
        ) -> PinnedCAObservation:
            shared_check = shared_context.checker(shared_clock_ns)
            return verify_pinned_ca(
                repository_root,
                git_blob_reader=lambda path: local_ca_blob(
                    path,
                    context=shared_context,
                    clock_ns=shared_clock_ns,
                ),
                cwd=repository_root,
                stage=current_stage,
                check=shared_check,
            )

        sealed_scan_started_at = None
        if seal is not None:
            sealed_scan_started_at = _parse_micro_utc(
                seal.record()["readiness_identity_body"]["scan_started_at"]
            )
        with open_v1b_snapshot(
            parsed,
            initial_ca,
            connect=lambda uri: psycopg_module.connect(uri),
            repeatable_read_value=psycopg_module.IsolationLevel.REPEATABLE_READ,
            ca_recheck=ca_recheck,
            ca_recheck_deadline=ca_recheck_deadline,
            recovery_seal_accepted=seal is not None,
            sealed_scan_started_at=sealed_scan_started_at,
        ) as snapshot:
            yield snapshot

    def load_evidence(
        snapshot: SnapshotSession,
        upper_as_of: datetime,
        recovery: bool,
    ) -> EvidencePopulation:
        return load_evidence_population(
            snapshot,
            upper_as_of,
            deserialize_forecast_record=primitives.deserialize_forecast_record,
            deserialize_outcome_record=primitives.deserialize_outcome_record,
            canonical_target_identity=primitives.canonical_target_identity,
            apply_forecast_commit_proof=primitives.apply_forecast_commit_proof,
            stage_after_first_read=(
                DatabaseFailureStage.SEALED_OR_RECOVERY
                if recovery
                else DatabaseFailureStage.NEW_AFTER_EVIDENCE_BEFORE_SEAL
            ),
        )

    def emit_seal(raw: bytes) -> str:
        _write_stdout_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    return OrchestrationDependencies(
        validate_startup=validate_startup,
        execution_identity=_production_execution_identity,
        prepare_runtime=prepare_runtime,
        remeasure_runtime=remeasure_runtime,
        repository_checkpoint=repository_checkpoint,
        open_snapshot=open_snapshot,
        load_evidence=load_evidence,
        calendar_sessions=_production_calendar_reader(xnys_calendar),
        primitives=primitives,
        emit_seal=emit_seal,
        write_stdout=_write_stdout_bytes,
        utc_now=lambda: datetime.now(timezone.utc),
    )


def _write_uninitialized_blocked(invocation: Invocation, writer: Callable[[bytes], None]) -> int:
    """Emit the official pre-authority negative without inspecting a secret."""

    try:
        receipt = build_blocked_receipt(
            manifest_id=invocation.manifest_id,
            generated_at_utc=timestamp_utc(datetime.now(timezone.utc)),
            observed_main_sha=None,
            expected_main_sha=None,
            observed_v1a_merge_sha=None,
            observed_user=None,
            observed_database=None,
            observed_effective_host=None,
            project_binding_verified=None,
            read_only=None,
            unverified_merge_identities=frozenset({"amendment", "tls"}),
        )
        writer(receipt.canonical_bytes)
    except BaseException:
        # Output loss is itself an infrastructure failure.  Never improvise an
        # ad-hoc line or leak the exception/ambient environment to stderr.
        pass
    return 1


def _write_uninitialized_recovery_invalid(
    invocation: Invocation,
    seal: SealBundle,
    writer: Callable[[bytes], None],
) -> int:
    """Preserve an accepted recovery seal when common setup cannot start."""

    try:
        record = seal.record()
        readiness_body = record["readiness_identity_body"]
        readiness = record["readiness"]
        receipt = build_pre_cell_invalid_receipt(
            manifest_id=invocation.manifest_id,
            generated_at_utc=timestamp_utc(datetime.now(timezone.utc)),
            verified_main_sha=readiness_body["verified_main_sha"],
            v1a_merge_sha=readiness_body["v1a_merge_sha"],
            evaluation_session=readiness["boundary_session"],
            evaluation_as_of_at=readiness["boundary_as_of_at"],
            database_identity=readiness_body["database_identity"],
            authority_proof=record["initial_authority_proof"],
            seal=seal,
        )
        writer(receipt.canonical_bytes)
    except BaseException:
        # The retained seal remains consumed even if the output sink fails.
        pass
    return 1


def scorecard_main(
    argv: Sequence[str] | None = None,
    dependencies: OrchestrationDependencies | None = None,
) -> int:
    """Strict two-option CLI with an explicit dependency seam for tests."""

    words = tuple(sys.argv[1:] if argv is None else argv)
    writer = dependencies.write_stdout if dependencies is not None else _write_stdout_bytes
    try:
        invocation = parse_scorecard_cli(words)
    except BaseException:
        try:
            writer(USAGE_INVALID_MANIFEST)
        except BaseException:
            pass
        return 2
    try:
        recovery_seal = read_recovery_seal(invocation)
    except BaseException:
        try:
            writer(_invalid_recovery_line(invocation.manifest_id))
        except BaseException:
            pass
        return 2

    if dependencies is None:
        try:
            startup = assert_production_startup(
                mode=(
                    "recovery"
                    if invocation.mode is InvocationMode.RECOVERY
                    else "normal"
                ),
                manifest_id=invocation.manifest_id,
                recovery_seal_path=invocation.recovery_path,
            )
            dependencies = build_production_dependencies(startup)
        except BaseException:
            if recovery_seal is not None:
                # Terminal exclusion has not yet been authenticated.  Emitting
                # another official terminal object could duplicate one already
                # integrated beyond the sealed execution revision.
                return 1
            return _write_uninitialized_blocked(invocation, writer)
    return run_scorecard(invocation, recovery_seal, dependencies)


def main() -> int:
    return scorecard_main()


if __name__ == "__main__":
    raise SystemExit(main())
