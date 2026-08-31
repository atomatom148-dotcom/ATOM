"""One-shot live proof for the frozen read-only Schwab S1 boundary.

The proof is deliberately outside the production quant runtime graph. It opens
at most one streamer connection, keeps normalized snapshots only in memory,
emits only a value-free receipt, and stops after one fresh NDX/COIN-book pair
or a short deadline. It has no V9, evidence, UI, database, account, or order
path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import json
import math
import os
import secrets
import threading
import time
from typing import Any

from quant import schwab_market_bus, schwab_market_worker


PROOF_ENABLE_ENV = "ATOM_SCHWAB_S2_LIVE_PROOF"
PROOF_ACCESS_TOKEN_ENV = "ATOM_SCHWAB_S2_ACCESS_TOKEN"
PROOF_SECONDS_ENV = "ATOM_SCHWAB_S2_SECONDS"
DEFAULT_PROOF_SECONDS = 45.0
MIN_PROOF_SECONDS = 10.0
MAX_PROOF_SECONDS = 45.0

_SCHEMA = "ATOM_SCHWAB_S2_LIVE_PROOF_V1"


@dataclass(frozen=True, slots=True)
class ProofReceipt:
    """Sanitized operational receipt; it contains no market values or secrets."""

    status: str
    reason: str
    ndx_observed: bool
    coin_level2_observed: bool
    ndx_publications: int
    coin_level2_publications: int
    streamer_connection_attempts: int
    worker_status: str
    worker_reason: str
    helper_stopped: bool
    elapsed_seconds: float

    def to_json(self) -> str:
        payload = asdict(self)
        payload.update(
            {
                "coin_level2_authority": "OBSERVER_ONLY",
                "elapsed_seconds": round(self.elapsed_seconds, 3),
                "ndx_seam": "INDEPENDENT",
                "read_only": True,
                "schema": _SCHEMA,
            }
        )
        return json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class _NoTokenStore:
    """Fail-closed store proving that S2 neither reads nor rotates tokens."""

    def __getattr__(self, name: str) -> Any:
        raise schwab_market_worker.SchwabAuthorizationError(
            "schwab_s2_token_store_forbidden"
        )


class StaticAccessSchwabSession(schwab_market_worker.SchwabOAuthSession):
    """S1 REST session constrained to one pre-authorized access token."""

    def __init__(
        self,
        access_token: str,
        *,
        http: schwab_market_worker.HttpTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        clean = _access_token(access_token)
        self.__proof_access_token = clean
        super().__init__(
            client_id="s2-live-proof",
            client_secret="s2-live-proof",
            redirect_uri="https://127.0.0.1/schwab-s2-live-proof",
            store=_NoTokenStore(),
            http=http,
            clock=clock,
        )

    def access_token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            raise schwab_market_worker.SchwabAuthorizationError(
                "schwab_s2_refresh_forbidden"
            )
        return self.__proof_access_token


class BoundedProofLease:
    """Single-process deadline lease shared by S1 and the transient proof sink."""

    def __init__(self, *, deadline: float, clock: Callable[[], float]) -> None:
        self._deadline = float(deadline)
        self._clock = clock
        self._owner: str | None = None
        self._lock = threading.Lock()

    def acquire(self, owner_token: str, ttl_seconds: float) -> bool:
        with self._lock:
            if self._owner is not None or self._expired():
                return False
            self._owner = owner_token
            return True

    def renew(self, owner_token: str, ttl_seconds: float) -> bool:
        with self._lock:
            return self._owner == owner_token and not self._expired()

    def release(self, owner_token: str) -> bool:
        with self._lock:
            if self._owner != owner_token:
                return False
            self._owner = None
            return True

    def owns(self, owner_token: str) -> bool:
        with self._lock:
            return self._owner == owner_token and not self._expired()

    def _expired(self) -> bool:
        return float(self._clock()) >= self._deadline


class ProofSink:
    """Value-discarding sink for exactly the two frozen transient S1 keys."""

    def __init__(
        self,
        *,
        lease: BoundedProofLease,
        stop_event: threading.Event,
    ) -> None:
        self._lease = lease
        self._stop_event = stop_event
        self._ndx_publications = 0
        self._book_publications = 0
        self._lock = threading.Lock()

    def publish(
        self,
        key: str,
        payload_json: str,
        ttl_seconds: int,
        owner_token: str,
    ) -> bool:
        if (
            self._stop_event.is_set()
            or ttl_seconds != schwab_market_bus.SNAPSHOT_TTL_SECONDS
            or not self._lease.owns(owner_token)
        ):
            return False
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError):
            return False
        expected_symbol = {
            schwab_market_bus.NDX_KEY: "NDX",
            schwab_market_bus.BOOK_KEY: "COIN",
        }.get(key)
        if (
            expected_symbol is None
            or not isinstance(payload, Mapping)
            or payload.get("symbol") != expected_symbol
        ):
            return False

        with self._lock:
            if self._stop_event.is_set() or not self._lease.owns(owner_token):
                return False
            if key == schwab_market_bus.NDX_KEY:
                self._ndx_publications += 1
            else:
                self._book_publications += 1
            complete = self._ndx_publications > 0 and self._book_publications > 0
        if complete:
            self._stop_event.set()
        return True

    def counts(self) -> tuple[int, int]:
        with self._lock:
            return self._ndx_publications, self._book_publications


class SingleConnectionFactory:
    """Permit one streamer connection attempt and fail closed thereafter."""

    def __init__(
        self,
        factory: Callable[..., Any],
        *,
        stop_event: threading.Event,
    ) -> None:
        self._factory = factory
        self._stop_event = stop_event
        self._connections = 0
        self._lock = threading.Lock()

    @property
    def attempts(self) -> int:
        with self._lock:
            return self._connections

    def __call__(self, url: str, **kwargs: object) -> Any:
        with self._lock:
            if self._connections != 0:
                self._stop_event.set()
                raise schwab_market_worker.SchwabProtocolError(
                    "schwab_s2_single_connection_only"
                )
            self._connections = 1
        return self._factory(url, **kwargs)


def _access_token(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("schwab_s2_access_token_required")
    clean = value.strip()
    if not clean or clean != value or len(clean) > 16_384:
        raise ValueError("schwab_s2_access_token_required")
    return clean


def _duration(value: object, *, cli: bool) -> float:
    if isinstance(value, bool):
        raise ValueError("schwab_s2_duration_invalid")
    try:
        duration = float(value)
    except (TypeError, ValueError):
        raise ValueError("schwab_s2_duration_invalid") from None
    minimum = MIN_PROOF_SECONDS if cli else 0.01
    if not math.isfinite(duration) or duration < minimum or duration > MAX_PROOF_SECONDS:
        raise ValueError("schwab_s2_duration_invalid")
    return duration


def _failure_reason(
    *,
    worker_ok: bool,
    ndx_publications: int,
    book_publications: int,
    streamer_connection_attempts: int,
    helper_stopped: bool,
    worker_failure_reason: str,
) -> str:
    if not helper_stopped:
        return "HELPER_STOP_TIMEOUT"
    if streamer_connection_attempts != 1:
        return "STREAM_NOT_OPENED"
    if worker_failure_reason != "NONE":
        return worker_failure_reason
    if ndx_publications == 0 and book_publications == 0:
        return "LIVE_PAIR_NOT_OBSERVED"
    if ndx_publications == 0:
        return "NDX_NOT_OBSERVED"
    if book_publications == 0:
        return "COIN_LEVEL2_NOT_OBSERVED"
    if not worker_ok:
        return "WORKER_REJECTED"
    return "NONE"


class ProofWorker(schwab_market_worker.SchwabMarketWorker):
    """S1 worker retaining only its last allowlisted failure reason."""

    def __init__(self, **kwargs: Any) -> None:
        self.last_failure_reason = "NONE"
        super().__init__(**kwargs)

    def _set_status(self, status: str, reason: str) -> None:
        if reason not in {"NONE", "STOP_REQUESTED"}:
            self.last_failure_reason = reason
        super()._set_status(status, reason)


def run_live_proof(
    access_token: str,
    *,
    duration_seconds: float = DEFAULT_PROOF_SECONDS,
    http: schwab_market_worker.HttpTransport | None = None,
    websocket_factory: Callable[..., Any] | None = None,
    wall_clock: Callable[[], float] = time.time,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> ProofReceipt:
    """Run one bounded S1 source proof and return a value-free receipt."""

    duration = _duration(duration_seconds, cli=False)
    started = float(monotonic_clock())
    deadline = started + duration
    stop_event = threading.Event()
    # The stop timer owns the observation deadline. A one-second lease cleanup
    # grace prevents that planned stop from being mislabeled as lease loss.
    lease = BoundedProofLease(deadline=deadline + 1.0, clock=monotonic_clock)
    sink = ProofSink(lease=lease, stop_event=stop_event)
    bus = schwab_market_bus.MarketBus(sink, clock=wall_clock)
    oauth = StaticAccessSchwabSession(
        access_token,
        http=http,
        clock=wall_clock,
    )
    base_factory = (
        websocket_factory
        if websocket_factory is not None
        else schwab_market_worker._default_websocket_factory
    )
    one_connection = SingleConnectionFactory(base_factory, stop_event=stop_event)
    worker = ProofWorker(
        bus=bus,
        oauth=oauth,
        lease=lease,
        websocket_factory=one_connection,
        stop_event=stop_event,
        clock=wall_clock,
        owner_token=secrets.token_urlsafe(32),
        reconnect_min_seconds=duration,
        reconnect_max_seconds=duration,
    )
    timer = threading.Timer(duration, stop_event.set)
    timer.daemon = True
    timer.start()
    worker_ok = False
    try:
        worker_ok = bool(worker.run())
    except Exception:
        worker_ok = False
    finally:
        stop_event.set()
        timer.cancel()

    helper = worker._ndx_thread
    if helper is not None:
        helper.join(schwab_market_worker.REQUEST_TIMEOUT_SECONDS + 1.0)
    helper_stopped = helper is None or not helper.is_alive()
    ndx_publications, book_publications = sink.counts()
    reason = _failure_reason(
        worker_ok=worker_ok,
        ndx_publications=ndx_publications,
        book_publications=book_publications,
        streamer_connection_attempts=one_connection.attempts,
        helper_stopped=helper_stopped,
        worker_failure_reason=worker.last_failure_reason,
    )
    return ProofReceipt(
        status="PASS" if reason == "NONE" else "FAIL",
        reason=reason,
        ndx_observed=ndx_publications > 0,
        coin_level2_observed=book_publications > 0,
        ndx_publications=ndx_publications,
        coin_level2_publications=book_publications,
        streamer_connection_attempts=one_connection.attempts,
        worker_status=worker.status,
        worker_reason=(
            worker.last_failure_reason
            if worker.last_failure_reason != "NONE"
            else worker.reason
        ),
        helper_stopped=helper_stopped,
        elapsed_seconds=max(0.0, float(monotonic_clock()) - started),
    )


def proof_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(PROOF_ENABLE_ENV, "")).strip().lower() == "true"


def _terminal_receipt(reason: str) -> ProofReceipt:
    return ProofReceipt(
        status="FAIL",
        reason=reason,
        ndx_observed=False,
        coin_level2_observed=False,
        ndx_publications=0,
        coin_level2_publications=0,
        streamer_connection_attempts=0,
        worker_status="STOPPED",
        worker_reason="NONE",
        helper_stopped=True,
        elapsed_seconds=0.0,
    )


def main(
    env: Mapping[str, str] | None = None,
    *,
    runner: Callable[..., ProofReceipt] = run_live_proof,
    emit: Callable[[str], None] = print,
) -> int:
    source = os.environ if env is None else env
    if not proof_enabled(source):
        emit(_terminal_receipt("S2_NOT_AUTHORIZED").to_json())
        return 2
    try:
        access_token = _access_token(source.get(PROOF_ACCESS_TOKEN_ENV))
        duration = _duration(
            source.get(PROOF_SECONDS_ENV, str(DEFAULT_PROOF_SECONDS)),
            cli=True,
        )
        receipt = runner(access_token, duration_seconds=duration)
    except Exception:
        receipt = _terminal_receipt("S2_CONFIGURATION_OR_RUNTIME_REJECTED")
    emit(receipt.to_json())
    return 0 if receipt.status == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
