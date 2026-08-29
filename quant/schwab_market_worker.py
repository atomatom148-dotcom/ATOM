"""Disabled-by-default, read-only Schwab market-data worker.

This module is intentionally isolated from the live quant, evidence, UI, and
broker paths.  It can read only the frozen NDX quote and COIN NASDAQ_BOOK
surfaces and can publish only through :mod:`quant.schwab_market_bus`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from quant import schwab_market_bus


SCHWAB_WORKER_ENABLED_ENV = "ATOM_SCHWAB_MARKET_DATA_ENABLED"
SCHWAB_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_NDX_QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
SCHWAB_USER_PREFERENCE_URL = "https://api.schwabapi.com/trader/v1/userPreference"
SCHWAB_STREAMER_URL = "wss://streamer-api.schwab.com/ws"

OAUTH_STATE_LIFETIME_SECONDS = 10 * 60
ACCESS_TOKEN_REFRESH_MARGIN_SECONDS = 75
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 1_048_576

LEVEL2_SERVICE = "NASDAQ_BOOK"
LEVEL2_SYMBOL = "COIN"
LEVEL2_FIELDS = "0,1,2,3"

_STREAMER_INFO_FIELDS = (
    "streamerSocketUrl",
    "schwabClientCustomerId",
    "schwabClientCorrelId",
    "schwabClientChannel",
    "schwabClientFunctionId",
)
_SAFE_STATUSES = frozenset(
    {
        "STOPPED",
        "STARTING",
        "CONNECTING",
        "STREAMING",
        "RECONNECTING",
        "LEASE_LOST",
    }
)
_SAFE_REASONS = frozenset(
    {
        "NONE",
        "STOP_REQUESTED",
        "LEASE_UNAVAILABLE",
        "LEASE_RENEWAL_FAILED",
        "AUTHORIZATION_UNAVAILABLE",
        "TRANSPORT_UNAVAILABLE",
        "PROTOCOL_REJECTED",
    }
)


class SchwabMarketError(RuntimeError):
    """Base error whose messages never contain provider bodies or secrets."""


class SchwabConfigurationError(SchwabMarketError):
    pass


class SchwabAuthorizationError(SchwabMarketError):
    pass


class SchwabTransportError(SchwabMarketError):
    pass


class SchwabProtocolError(SchwabMarketError):
    pass


class SchwabLeaseLost(SchwabMarketError):
    pass


class _WorkerStopped(SchwabMarketError):
    pass


@dataclass(frozen=True, slots=True)
class OAuthTokenSet:
    """The private token-vault value used by the injected OAuth store."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at_epoch: float


class OAuthStore(Protocol):
    """Atomic persistence required by the OAuth boundary."""

    def save_state_digest(self, digest: str, expires_at: float) -> None: ...

    def consume_state_digest(self, digest: str, now: float) -> bool: ...

    def load_tokens(self) -> OAuthTokenSet | None: ...

    def compare_and_swap_tokens(
        self,
        expected: OAuthTokenSet | None,
        replacement: OAuthTokenSet,
    ) -> bool: ...


class Lease(Protocol):
    """Token-fenced singleton lease used by the injected runtime adapter."""

    def acquire(self, owner_token: str, ttl_seconds: float) -> bool: ...

    def renew(self, owner_token: str, ttl_seconds: float) -> bool: ...

    def release(self, owner_token: str) -> bool: ...


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any: ...


class _UrlLibResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = int(status_code)
        self._body = bytes(body)

    def json(self) -> Any:
        body = self._body
        self._body = b""
        return json.loads(body.decode("utf-8"))

    def select_streamer_info(self) -> Mapping[str, str]:
        body = self._body
        self._body = b""
        return _select_streamer_info_json(body)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Any, *args: Any, **kwargs: Any) -> None:
        return None


class _UrlLibHttp:
    """Small stdlib transport; tests and deployments may inject another one."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> _UrlLibResponse:
        target = url
        if params:
            target += ("&" if "?" in target else "?") + urlencode(dict(params))
        body = None if data is None else urlencode(dict(data)).encode("ascii")
        request = Request(
            target,
            data=body,
            headers=dict(headers or {}),
            method=str(method).upper(),
        )
        try:
            # Build lazily so importing a disabled worker does not inspect the
            # process proxy environment through urllib's default ProxyHandler.
            opener = build_opener(_NoRedirect)
            with opener.open(request, timeout=timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SchwabProtocolError("schwab_response_too_large")
                return _UrlLibResponse(response.status, body)
        except HTTPError as error:
            # Never read or retain an error body; it may contain credentials.
            status_code = error.code
            try:
                error.close()
            except Exception:
                pass
            return _UrlLibResponse(status_code, b"")


def _json_string_end(text: str, start: int) -> int:
    if start >= len(text) or text[start] != '"':
        raise SchwabProtocolError("schwab_invalid_json")
    escaped = False
    for index in range(start + 1, len(text)):
        character = text[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return index + 1
    raise SchwabProtocolError("schwab_invalid_json")


def _json_container_close(
    stack: list[str], character: str, index: int,
) -> int | None:
    if character != stack.pop():
        raise SchwabProtocolError("schwab_invalid_json")
    if stack:
        return None
    return index + 1


def _json_container_end(text: str, start: int) -> int:
    stack = ["]" if text[start] == "[" else "}"]
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == '"':
            index = _json_string_end(text, index)
            continue
        if character in "[{":
            stack.append("]" if character == "[" else "}")
        elif character in "]}":
            end = _json_container_close(stack, character, index)
            if end is not None:
                return end
        index += 1
    raise SchwabProtocolError("schwab_invalid_json")


def _json_scalar_end(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index] not in ",}]":
        index += 1
    if not text[start:index].strip():
        raise SchwabProtocolError("schwab_invalid_json")
    return index


def _json_value_end(text: str, start: int) -> int:
    if start >= len(text):
        raise SchwabProtocolError("schwab_invalid_json")
    first = text[start]
    if first == '"':
        return _json_string_end(text, start)
    if first in "[{":
        return _json_container_end(text, start)
    return _json_scalar_end(text, start)


def _skip_json_space(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _json_object_members(text: str, start: int):
    if start >= len(text) or text[start] != "{":
        raise SchwabProtocolError("schwab_invalid_json")
    limit = _json_value_end(text, start)
    index = start + 1
    while True:
        index = _skip_json_space(text, index)
        if index < limit and text[index] == "}":
            return
        key_end = _json_string_end(text, index)
        raw_key = text[index:key_end]
        index = _skip_json_space(text, key_end)
        if index >= limit or text[index] != ":":
            raise SchwabProtocolError("schwab_invalid_json")
        value_start = _skip_json_space(text, index + 1)
        value_end = _json_value_end(text, value_start)
        yield raw_key, value_start, value_end
        index = _skip_json_space(text, value_end)
        if index < limit and text[index] == ",":
            index += 1
            continue
        if index < limit and text[index] == "}":
            return
        raise SchwabProtocolError("schwab_invalid_json")


def _json_array_values(text: str, start: int):
    if start >= len(text) or text[start] != "[":
        raise SchwabProtocolError("schwab_streamer_info_invalid")
    limit = _json_value_end(text, start)
    index = start + 1
    while True:
        index = _skip_json_space(text, index)
        if index < limit and text[index] == "]":
            return
        value_end = _json_value_end(text, index)
        yield index, value_end
        index = _skip_json_space(text, value_end)
        if index < limit and text[index] == ",":
            index += 1
            continue
        if index < limit and text[index] == "]":
            return
        raise SchwabProtocolError("schwab_invalid_json")


def _decode_json_document(body: bytes) -> tuple[str, int]:
    try:
        text = body.decode("utf-8")
    except UnicodeError:
        raise SchwabProtocolError("schwab_invalid_json") from None
    root_start = _skip_json_space(text, 0)
    root_end = _json_value_end(text, root_start)
    if _skip_json_space(text, root_end) != len(text):
        raise SchwabProtocolError("schwab_invalid_json")
    return text, root_start


def _streamer_info_slice(text: str, root_start: int) -> tuple[int, int]:
    streamer_slice: tuple[int, int] | None = None
    for raw_key, value_start, value_end in _json_object_members(text, root_start):
        if raw_key == '"streamerInfo"':
            if streamer_slice is not None:
                raise SchwabProtocolError("schwab_streamer_info_invalid")
            streamer_slice = (value_start, value_end)
    if streamer_slice is None:
        raise SchwabProtocolError("schwab_streamer_info_invalid")
    return streamer_slice


def _first_streamer_info_slice(text: str, array_start: int) -> tuple[int, int]:
    first_info: tuple[int, int] | None = None
    for position, item_slice in enumerate(_json_array_values(text, array_start)):
        if position == 0:
            first_info = item_slice
    if first_info is None or text[first_info[0]] != "{":
        raise SchwabProtocolError("schwab_streamer_info_invalid")
    return first_info


def _decode_streamer_info_fields(text: str, object_start: int) -> dict[str, str]:
    wanted = {json.dumps(field): field for field in _STREAMER_INFO_FIELDS}
    selected: dict[str, str] = {}
    for raw_key, value_start, value_end in _json_object_members(text, object_start):
        field_name = wanted.get(raw_key)
        if field_name is None:
            continue
        if field_name in selected or text[value_start] != '"':
            raise SchwabProtocolError("schwab_streamer_info_invalid")
        try:
            value = json.loads(text[value_start:value_end])
        except Exception:
            raise SchwabProtocolError("schwab_streamer_info_invalid") from None
        if not isinstance(value, str) or not value.strip():
            raise SchwabProtocolError("schwab_streamer_info_invalid")
        selected[field_name] = value.strip()
    if set(selected) != set(_STREAMER_INFO_FIELDS):
        raise SchwabProtocolError("schwab_streamer_info_invalid")
    return selected


def _select_streamer_info_json(body: bytes) -> Mapping[str, str]:
    """Decode only the five frozen strings, lexically skipping every other value."""

    text, root_start = _decode_json_document(body)
    streamer_slice = _streamer_info_slice(text, root_start)
    first_info = _first_streamer_info_slice(text, streamer_slice[0])
    return _decode_streamer_info_fields(text, first_info[0])


def _require_https_url(value: str, *, callback: bool = False) -> str:
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    valid = bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )
    if callback:
        valid = valid and not parsed.query
    if not valid:
        raise SchwabConfigurationError("schwab_https_configuration_required")
    return clean


def _require_wss_url(value: str) -> str:
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    try:
        port = parsed.port
    except ValueError:
        raise SchwabProtocolError("schwab_streamer_info_invalid") from None
    if not (
        parsed.scheme == "wss"
        and parsed.hostname == "streamer-api.schwab.com"
        and port in {None, 443}
        and parsed.path == "/ws"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    ):
        raise SchwabProtocolError("schwab_streamer_info_invalid")
    return clean


def _response_status(response: Any) -> int:
    try:
        value = getattr(response, "status_code", None)
        if value is None:
            value = getattr(response, "status", 0)
        if isinstance(value, bool):
            return 0
        return int(value)
    except Exception:
        return 0


def _response_json(response: Any) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except Exception:
        raise SchwabProtocolError("schwab_invalid_json") from None
    if not isinstance(payload, Mapping):
        raise SchwabProtocolError("schwab_invalid_payload")
    return payload


def _coerce_tokens(value: Any) -> OAuthTokenSet | None:
    if value is None:
        return None
    if isinstance(value, OAuthTokenSet):
        access_token = value.access_token
        refresh_token = value.refresh_token
        expires_at = value.expires_at_epoch
    elif isinstance(value, Mapping):
        access_token = value.get("access_token")
        refresh_token = value.get("refresh_token")
        expires_at = value.get("expires_at_epoch", value.get("access_expires_at_epoch"))
    else:
        raise SchwabAuthorizationError("schwab_token_record_invalid")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise SchwabAuthorizationError("schwab_token_record_invalid")
    if isinstance(expires_at, bool):
        raise SchwabAuthorizationError("schwab_token_record_invalid")
    try:
        expiry = float(expires_at)
    except (TypeError, ValueError):
        raise SchwabAuthorizationError("schwab_token_record_invalid") from None
    if (
        not access_token.strip()
        or not refresh_token.strip()
        or not math.isfinite(expiry)
        or expiry <= 0
    ):
        raise SchwabAuthorizationError("schwab_token_record_invalid")
    return OAuthTokenSet(access_token.strip(), refresh_token.strip(), expiry)


class SchwabOAuthSession:
    """Read-only Schwab OAuth and REST surface with bounded refresh behavior."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        store: OAuthStore,
        http: HttpTransport | None = None,
        clock: Callable[[], float] = time.time,
        state_factory: Callable[[], str] | None = None,
    ) -> None:
        self._client_id = str(client_id or "").strip()
        self._client_secret = str(client_secret or "").strip()
        self._redirect_uri = _require_https_url(redirect_uri, callback=True)
        if not self._client_id or not self._client_secret:
            raise SchwabConfigurationError("schwab_oauth_configuration_incomplete")
        self._store = store
        self._http = http if http is not None else _UrlLibHttp()
        self._clock = clock
        self._state_factory = state_factory or (lambda: secrets.token_urlsafe(32))
        self._lock = threading.RLock()

    def authorize_url(self) -> str:
        raw_state = self._state_factory()
        if not isinstance(raw_state, str) or not raw_state:
            raise SchwabAuthorizationError("schwab_oauth_state_unavailable")
        digest = hashlib.sha256(raw_state.encode("utf-8")).hexdigest()
        now = float(self._clock())
        self._store.save_state_digest(
            digest,
            now + OAUTH_STATE_LIFETIME_SECONDS,
        )
        return SCHWAB_AUTHORIZE_URL + "?" + urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "state": raw_state,
            }
        )

    def handle_callback(
        self,
        *,
        code: str,
        state: str,
        callback_url: str | None = None,
    ) -> OAuthTokenSet:
        clean_code = str(code or "").strip()
        clean_state = str(state or "").strip()
        if not clean_code or not clean_state:
            raise SchwabAuthorizationError("schwab_oauth_callback_invalid")
        if callback_url is not None:
            parsed = urlparse(_require_https_url(callback_url))
            expected = urlparse(self._redirect_uri)
            if (parsed.scheme, parsed.netloc, parsed.path) != (
                expected.scheme,
                expected.netloc,
                expected.path,
            ):
                raise SchwabAuthorizationError("schwab_oauth_callback_invalid")
            query = parse_qs(parsed.query, keep_blank_values=True)
            if query.get("code", [clean_code])[0] != clean_code:
                raise SchwabAuthorizationError("schwab_oauth_callback_invalid")
            if query.get("state", [clean_state])[0] != clean_state:
                raise SchwabAuthorizationError("schwab_oauth_callback_invalid")

        digest = hashlib.sha256(clean_state.encode("utf-8")).hexdigest()
        now = float(self._clock())
        # Atomic consumption makes the callback expiring and single-use.
        if not self._store.consume_state_digest(digest, now):
            raise SchwabAuthorizationError("schwab_oauth_state_rejected")

        with self._lock:
            expected = _coerce_tokens(self._store.load_tokens())
            payload = self._token_request(
                {
                    "grant_type": "authorization_code",
                    "code": clean_code,
                    "redirect_uri": self._redirect_uri,
                }
            )
            replacement = self._tokens_from_payload(payload, previous_refresh="")
            if not self._store.compare_and_swap_tokens(expected, replacement):
                raise SchwabAuthorizationError("schwab_token_persistence_conflict")
            return replacement

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            current = _coerce_tokens(self._store.load_tokens())
            now = float(self._clock())
            if (
                not force_refresh
                and current is not None
                and current.access_token
                and current.expires_at_epoch
                > now + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
            ):
                return current.access_token
            replacement = self._refresh_locked(current)
            return replacement.access_token

    def get_ndx_payload(self) -> Mapping[str, Any]:
        return self._authorized_get(
            SCHWAB_NDX_QUOTES_URL,
            params={"symbols": "$NDX", "fields": "quote,reference"},
        )

    def get_streamer_info(self) -> Mapping[str, str]:
        response = self._authorized_response(SCHWAB_USER_PREFERENCE_URL)
        selector = getattr(response, "select_streamer_info", None)
        if not callable(selector):
            raise SchwabProtocolError("schwab_selective_response_required")
        try:
            raw = selector()
        except SchwabMarketError:
            raise
        except Exception:
            raise SchwabProtocolError("schwab_streamer_info_invalid") from None
        if not isinstance(raw, Mapping):
            raise SchwabProtocolError("schwab_streamer_info_invalid")
        sanitized: dict[str, str] = {}
        for field in _STREAMER_INFO_FIELDS:
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SchwabProtocolError("schwab_streamer_info_invalid")
            sanitized[field] = value.strip()
        _require_wss_url(sanitized["streamerSocketUrl"])
        return sanitized

    def _refresh_locked(self, current: OAuthTokenSet | None) -> OAuthTokenSet:
        if current is None or not current.refresh_token:
            raise SchwabAuthorizationError("schwab_reauthorization_required")
        payload = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": current.refresh_token,
            }
        )
        replacement = self._tokens_from_payload(
            payload,
            previous_refresh=current.refresh_token,
        )
        if self._store.compare_and_swap_tokens(current, replacement):
            return replacement
        # Another owner may have refreshed first. Use its fresh value only.
        latest = _coerce_tokens(self._store.load_tokens())
        if (
            latest is not None
            and latest.expires_at_epoch
            > float(self._clock()) + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return latest
        raise SchwabAuthorizationError("schwab_token_persistence_conflict")

    def _tokens_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        previous_refresh: str,
    ) -> OAuthTokenSet:
        access = payload.get("access_token")
        refresh = payload.get("refresh_token") or previous_refresh
        expires_in = payload.get("expires_in", 1800)
        if (
            not isinstance(access, str)
            or not access.strip()
            or not isinstance(refresh, str)
            or not refresh.strip()
            or isinstance(expires_in, bool)
        ):
            raise SchwabAuthorizationError("schwab_token_response_invalid")
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError):
            raise SchwabAuthorizationError("schwab_token_response_invalid") from None
        if not math.isfinite(lifetime) or lifetime <= 0:
            raise SchwabAuthorizationError("schwab_token_response_invalid")
        return OAuthTokenSet(
            access_token=access.strip(),
            refresh_token=refresh.strip(),
            expires_at_epoch=float(self._clock()) + lifetime,
        )

    def _token_request(self, data: Mapping[str, str]) -> Mapping[str, Any]:
        credentials = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        authorization = "Basic " + base64.b64encode(credentials).decode("ascii")
        try:
            response = self._http.request(
                "POST",
                SCHWAB_TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "Authorization": authorization,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:
            raise SchwabTransportError("schwab_token_transport_unavailable") from None
        if _response_status(response) not in {200, 201}:
            raise SchwabAuthorizationError("schwab_token_exchange_rejected")
        return _response_json(response)

    def _authorized_get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        if url != SCHWAB_NDX_QUOTES_URL:
            raise SchwabConfigurationError("schwab_market_surface_forbidden")
        return _response_json(self._authorized_response(url, params=params))

    def _authorized_response(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        if url not in {SCHWAB_NDX_QUOTES_URL, SCHWAB_USER_PREFERENCE_URL}:
            raise SchwabConfigurationError("schwab_market_surface_forbidden")
        token = self.access_token()
        response = self._resource_request(url, token=token, params=params)
        if _response_status(response) == 401:
            # Exactly one forced refresh and one retry.  A second 401 fails.
            token = self.access_token(force_refresh=True)
            response = self._resource_request(url, token=token, params=params)
        status = _response_status(response)
        if status == 401:
            raise SchwabAuthorizationError("schwab_resource_unauthorized")
        if status < 200 or status >= 300:
            raise SchwabTransportError("schwab_resource_unavailable")
        return response

    def _resource_request(
        self,
        url: str,
        *,
        token: str,
        params: Mapping[str, str] | None,
    ) -> Any:
        try:
            return self._http.request(
                "GET",
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer " + token,
                },
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception:
            raise SchwabTransportError("schwab_resource_transport_unavailable") from None


def _stream_request(
    *,
    request_id: str,
    service: str,
    command: str,
    customer_id: str,
    correl_id: str,
    parameters: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "requests": [
            {
                "service": service,
                "requestid": str(request_id),
                "command": command,
                "SchwabClientCustomerId": customer_id,
                "SchwabClientCorrelId": correl_id,
                "parameters": dict(parameters),
            }
        ]
    }


def build_login_request(
    *,
    customer_id: str,
    correl_id: str,
    channel: str,
    function_id: str,
    access_token: str,
    request_id: str = "0",
) -> dict[str, list[dict[str, Any]]]:
    return _stream_request(
        request_id=request_id,
        service="ADMIN",
        command="LOGIN",
        customer_id=customer_id,
        correl_id=correl_id,
        parameters={
            "Authorization": access_token,
            "SchwabClientChannel": channel,
            "SchwabClientFunctionId": function_id,
        },
    )


def build_book_subscription(
    *,
    customer_id: str,
    correl_id: str,
    request_id: str = "2",
) -> dict[str, list[dict[str, Any]]]:
    return _stream_request(
        request_id=request_id,
        service=LEVEL2_SERVICE,
        command="SUBS",
        customer_id=customer_id,
        correl_id=correl_id,
        parameters={"keys": LEVEL2_SYMBOL, "fields": LEVEL2_FIELDS},
    )


def validate_command_ack(
    message: Mapping[str, Any],
    *,
    request_id: str,
    service: str,
    command: str,
) -> None:
    rows = message.get("response")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise SchwabProtocolError("schwab_stream_ack_invalid")
    row = rows[0]
    content = row.get("content")
    code_value = content.get("code") if isinstance(content, Mapping) else None
    if (
        str(row.get("requestid")) != str(request_id)
        or str(row.get("service") or "").upper() != service
        or str(row.get("command") or "").upper() != command
        or not isinstance(content, Mapping)
        or isinstance(code_value, bool)
        or not isinstance(code_value, (int, float, str))
    ):
        raise SchwabProtocolError("schwab_stream_ack_invalid")
    if isinstance(code_value, float) and (
        not math.isfinite(code_value) or not code_value.is_integer()
    ):
        raise SchwabProtocolError("schwab_stream_ack_invalid")
    try:
        code = int(code_value)
    except (TypeError, ValueError):
        raise SchwabProtocolError("schwab_stream_ack_invalid") from None
    if code != 0:
        raise SchwabProtocolError("schwab_stream_ack_rejected")


def _decode_stream_message(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeError:
            raise SchwabProtocolError("schwab_stream_message_invalid") from None
    if not isinstance(raw, str) or not raw:
        raise SchwabTransportError("schwab_stream_closed")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        raise SchwabProtocolError("schwab_stream_message_invalid") from None
    if not isinstance(payload, Mapping):
        raise SchwabProtocolError("schwab_stream_message_invalid")
    return payload


def _level2_row_contents(row: object):
    if not isinstance(row, Mapping):
        return
    if str(row.get("service") or "").upper() != LEVEL2_SERVICE:
        return
    content_rows = row.get("content")
    if not isinstance(content_rows, list):
        return
    for content in content_rows:
        if isinstance(content, Mapping):
            yield content


def _level2_contents(message: Mapping[str, Any]):
    data_rows = message.get("data")
    if not isinstance(data_rows, list):
        return
    for row in data_rows:
        yield from _level2_row_contents(row)


def _is_timeout(error: Exception) -> bool:
    return any(
        item.__name__ in {"TimeoutError", "WebSocketTimeoutException"}
        for item in type(error).__mro__
    )


def _default_websocket_factory(url: str, *, timeout: float) -> Any:
    from websocket import create_connection

    return create_connection(
        url,
        timeout=timeout,
        enable_multithread=True,
        redirect_limit=0,
    )


class SchwabMarketWorker:
    """Single-owner NDX and COIN depth observer with no quant authority."""

    def __init__(
        self,
        *,
        bus: schwab_market_bus.MarketBus,
        oauth: SchwabOAuthSession,
        lease: Lease,
        websocket_factory: Callable[..., Any] | None,
        stop_event: threading.Event,
        clock: Callable[[], float] = time.time,
        owner_token: str,
        lease_ttl_seconds: float = 45.0,
        lease_renew_interval_seconds: float = 15.0,
        socket_timeout_seconds: float = 5.0,
        reconnect_min_seconds: float = 1.0,
        reconnect_max_seconds: float = 20.0,
        ndx_poll_interval_seconds: float = 1.0,
    ) -> None:
        self._bus = bus
        self._oauth = oauth
        self._lease = lease
        self._websocket_factory = websocket_factory or _default_websocket_factory
        self._stop_event = stop_event
        self._clock = clock
        if not isinstance(owner_token, str) or not owner_token:
            raise ValueError("owner_token_required")
        self._owner_token = owner_token
        self._lease_ttl = max(45.0, float(lease_ttl_seconds))
        self._lease_renew_interval = max(
            0.1,
            min(float(lease_renew_interval_seconds), self._lease_ttl / 2.0),
        )
        self._socket_timeout = max(
            0.1,
            min(float(socket_timeout_seconds), self._lease_renew_interval),
        )
        reconnect_min = float(reconnect_min_seconds)
        reconnect_max = float(reconnect_max_seconds)
        if not math.isfinite(reconnect_min) or not math.isfinite(reconnect_max):
            raise ValueError("invalid_reconnect_interval")
        self._reconnect_min = min(30.0, max(0.1, reconnect_min))
        self._reconnect_max = max(
            self._reconnect_min,
            min(30.0, reconnect_max),
        )
        self._ndx_poll_interval = max(0.1, float(ndx_poll_interval_seconds))
        self._next_renewal = 0.0
        self._owned = False
        self._lease_lost = False
        self._lease_lock = threading.Lock()
        self._active_socket: Any = None
        self._socket_lock = threading.Lock()
        self._ndx_thread: threading.Thread | None = None
        self._ndx_thread_lock = threading.Lock()
        self._status = "STOPPED"
        self._reason = "NONE"
        self._status_lock = threading.Lock()

    @property
    def status(self) -> str:
        with self._status_lock:
            return self._status

    @property
    def reason(self) -> str:
        with self._status_lock:
            return self._reason

    def run(self) -> bool:
        self._set_status("STARTING", "NONE")
        if not self._acquire_lease():
            self._set_status("STOPPED", "LEASE_UNAVAILABLE")
            return False

        try:
            self._begin_owned_run()
            self._run_stream_loop()
        finally:
            lease_lost = self._release_owned_lease()

        if lease_lost:
            self._set_status("LEASE_LOST", "LEASE_RENEWAL_FAILED")
            return False
        self._set_status("STOPPED", "STOP_REQUESTED")
        return True

    def _acquire_lease(self) -> bool:
        try:
            return bool(self._lease.acquire(self._owner_token, self._lease_ttl))
        except Exception:
            return False

    def _begin_owned_run(self) -> None:
        with self._lease_lock:
            self._owned = True
            self._next_renewal = float(self._clock()) + self._lease_renew_interval
        self._start_ndx_loop()

    def _run_stream_loop(self) -> None:
        backoff = self._reconnect_min
        while not self._stop_event.is_set() and self._owned_now():
            keep_running, reset_backoff = self._run_stream_cycle()
            if reset_backoff:
                backoff = self._reconnect_min
            if not keep_running or not self._wait_before_reconnect(backoff):
                break
            backoff = min(
                self._reconnect_max,
                max(self._reconnect_min, backoff * 2.0),
            )

    def _run_stream_cycle(self) -> tuple[bool, bool]:
        try:
            self._renew_if_due(force=True)
            self._connect_and_stream()
            outcome = (True, True)
        except SchwabLeaseLost:
            self._set_status("LEASE_LOST", "LEASE_RENEWAL_FAILED")
            outcome = (False, False)
        except _WorkerStopped:
            outcome = (False, False)
        except SchwabAuthorizationError:
            outcome = self._handle_stream_failure("AUTHORIZATION_UNAVAILABLE")
        except SchwabProtocolError:
            outcome = self._handle_stream_failure("PROTOCOL_REJECTED")
        except Exception:
            outcome = self._handle_stream_failure("TRANSPORT_UNAVAILABLE")
        finally:
            self._close_socket()
        return outcome

    def _handle_stream_failure(self, reason: str) -> tuple[bool, bool]:
        if self._set_reconnecting_if_owned(reason):
            return True, False
        self._set_status("LEASE_LOST", "LEASE_RENEWAL_FAILED")
        return False, False

    def _wait_before_reconnect(self, backoff: float) -> bool:
        if self._stop_event.is_set() or not self._owned_now():
            return False
        try:
            self._renew_if_due(force=True)
        except SchwabLeaseLost:
            self._set_status("LEASE_LOST", "LEASE_RENEWAL_FAILED")
            return False
        return not self._stop_event.wait(backoff)

    def _release_owned_lease(self) -> bool:
        self._close_socket()
        with self._lease_lock:
            release_owned = self._owned
            self._owned = False
            lease_lost = self._lease_lost
        if release_owned:
            try:
                self._lease.release(self._owner_token)
            except Exception:
                pass
        return lease_lost

    def _set_status(self, status: str, reason: str) -> None:
        if status not in _SAFE_STATUSES or reason not in _SAFE_REASONS:
            raise ValueError("unsafe_worker_status")
        with self._status_lock:
            self._status = status
            self._reason = reason

    def _owned_now(self) -> bool:
        with self._lease_lock:
            return self._owned

    def _set_reconnecting_if_owned(self, reason: str) -> bool:
        with self._lease_lock:
            if not self._owned or self._lease_lost:
                return False
            self._set_status("RECONNECTING", reason)
            return True

    def _renew_if_due(self, *, force: bool = False) -> None:
        lost = False
        with self._lease_lock:
            if not self._owned:
                raise SchwabLeaseLost("schwab_market_lease_lost")
            now = float(self._clock())
            if not force and now < self._next_renewal:
                return
            try:
                renewed = bool(self._lease.renew(self._owner_token, self._lease_ttl))
            except Exception:
                renewed = False
            if renewed:
                self._next_renewal = now + self._lease_renew_interval
                return
            self._owned = False
            self._lease_lost = True
            lost = True
        if lost:
            self._close_socket()
            raise SchwabLeaseLost("schwab_market_lease_lost")

    def _fenced_action(self, action: Callable[[], Any]) -> bool:
        """Renew and act while stop/release cannot cross the lease fence."""
        lost = False
        with self._lease_lock:
            if not self._owned:
                raise SchwabLeaseLost("schwab_market_lease_lost")
            if self._stop_event.is_set():
                return False
            try:
                renewed = bool(self._lease.renew(self._owner_token, self._lease_ttl))
            except Exception:
                renewed = False
            if renewed:
                self._next_renewal = float(self._clock()) + self._lease_renew_interval
                action()
                return True
            self._owned = False
            self._lease_lost = True
            lost = True
        if lost:
            self._close_socket()
            raise SchwabLeaseLost("schwab_market_lease_lost")
        return False

    def _publish_with_lease(self, publisher: Callable[..., Any], snapshot: Any) -> bool:
        """Renew by interval; the sink atomically validates this lease token."""

        if self._stop_event.is_set():
            return False
        self._renew_if_due()
        if self._stop_event.is_set():
            return False
        if not self._owned_now():
            raise SchwabLeaseLost("schwab_market_lease_lost")
        return bool(publisher(snapshot, owner_token=self._owner_token))

    def _activate_socket(self, stream: Any) -> None:
        with self._lease_lock:
            if not self._owned:
                rejection = "LEASE"
            elif self._stop_event.is_set():
                rejection = "STOP"
            else:
                with self._socket_lock:
                    self._active_socket = stream
                rejection = None
        if rejection is None:
            return
        try:
            stream.close()
        except Exception:
            pass
        if rejection == "STOP":
            raise _WorkerStopped("schwab_market_worker_stopped")
        raise SchwabLeaseLost("schwab_market_lease_lost")

    def _send_with_lease(self, stream: Any, payload: str) -> None:
        if not self._fenced_action(lambda: stream.send(payload)):
            raise _WorkerStopped("schwab_market_worker_stopped")

    def _start_ndx_loop(self) -> None:
        with self._ndx_thread_lock:
            if self._ndx_thread is not None:
                return
            thread = threading.Thread(
                target=self._ndx_loop,
                name="atom-schwab-ndx-observer",
                daemon=True,
            )
            thread.start()
            self._ndx_thread = thread

    def _ndx_loop(self) -> None:
        while not self._stop_event.is_set() and self._owned_now():
            try:
                # The sink performs the final atomic token check, so NDX REST
                # cannot serialize the independent websocket/book path.
                self._renew_if_due()
                payload = self._oauth.get_ndx_payload()
                snapshot = schwab_market_bus.normalize_ndx_quote(
                    payload,
                    received_at_epoch=float(self._clock()),
                )
                self._publish_with_lease(self._bus.publish_ndx, snapshot)
            except SchwabLeaseLost:
                if not self._stop_event.is_set():
                    self._set_status("LEASE_LOST", "LEASE_RENEWAL_FAILED")
                self._close_socket()
                return
            except Exception:
                pass
            if self._stop_event.wait(self._ndx_poll_interval):
                return

    def _connect_and_stream(self) -> None:
        self._set_status("CONNECTING", "NONE")
        info = self._oauth.get_streamer_info()
        token = self._oauth.access_token()
        self._renew_if_due(force=True)
        stream = self._websocket_factory(
            info["streamerSocketUrl"],
            timeout=self._socket_timeout,
        )
        self._activate_socket(stream)
        self._send_with_lease(
            stream,
            json.dumps(
                build_login_request(
                    customer_id=info["schwabClientCustomerId"],
                    correl_id=info["schwabClientCorrelId"],
                    channel=info["schwabClientChannel"],
                    function_id=info["schwabClientFunctionId"],
                    access_token=token,
                ),
                separators=(",", ":"),
            )
        )
        self._await_ack(
            stream,
            request_id="0",
            service="ADMIN",
            command="LOGIN",
        )
        self._send_with_lease(
            stream,
            json.dumps(
                build_book_subscription(
                    customer_id=info["schwabClientCustomerId"],
                    correl_id=info["schwabClientCorrelId"],
                ),
                separators=(",", ":"),
            )
        )
        self._await_ack(
            stream,
            request_id="2",
            service=LEVEL2_SERVICE,
            command="SUBS",
        )
        self._set_status("STREAMING", "NONE")

        while not self._stop_event.is_set():
            self._renew_if_due()
            try:
                raw = stream.recv()
            except Exception as error:
                if _is_timeout(error):
                    self._renew_if_due(force=True)
                    continue
                raise SchwabTransportError("schwab_stream_transport_unavailable") from None
            message = _decode_stream_message(raw)
            self._publish_book_rows(message)

    def _await_ack(
        self,
        stream: Any,
        *,
        request_id: str,
        service: str,
        command: str,
    ) -> None:
        for _ in range(64):
            if self._stop_event.is_set():
                raise SchwabTransportError("schwab_stream_stopped")
            self._renew_if_due()
            try:
                message = _decode_stream_message(stream.recv())
            except Exception as error:
                if _is_timeout(error):
                    self._renew_if_due(force=True)
                    continue
                if isinstance(error, SchwabMarketError):
                    raise
                raise SchwabTransportError("schwab_stream_transport_unavailable") from None
            if "response" not in message:
                continue
            validate_command_ack(
                message,
                request_id=request_id,
                service=service,
                command=command,
            )
            return
        raise SchwabProtocolError("schwab_stream_ack_timeout")

    def _publish_book_rows(self, message: Mapping[str, Any]) -> None:
        for content in _level2_contents(message):
            self._publish_book_content(content)

    def _publish_book_content(self, content: Mapping[str, Any]) -> None:
        try:
            snapshot = schwab_market_bus.normalize_nasdaq_book(
                content,
                received_at_epoch=float(self._clock()),
            )
            self._publish_with_lease(self._bus.publish_book, snapshot)
        except SchwabLeaseLost:
            raise
        except Exception:
            return

    def _close_socket(self) -> None:
        with self._socket_lock:
            stream = self._active_socket
            self._active_socket = None
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def worker_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(SCHWAB_WORKER_ENABLED_ENV, "")).strip().lower() == "true"


def main(
    env: Mapping[str, str] | None = None,
    worker_factory: Callable[[], SchwabMarketWorker] | None = None,
) -> int:
    """Run only through an injected composition root after explicit enablement."""

    if not worker_enabled(env):
        return 0
    if worker_factory is None:
        return 2
    try:
        worker = worker_factory()
        return 0 if worker.run() else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
