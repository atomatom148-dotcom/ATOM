from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from collections import deque
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from quant.schwab_market_worker import (
    MAX_RESPONSE_BYTES,
    SCHWAB_AUTHORIZE_URL,
    SCHWAB_NDX_QUOTES_URL,
    SCHWAB_TOKEN_URL,
    SCHWAB_USER_PREFERENCE_URL,
    OAuthTokenSet,
    _NoRedirect,
    _UrlLibHttp,
    _UrlLibResponse,
    _decode_stream_message,
    _default_websocket_factory,
    SchwabAuthorizationError,
    SchwabProtocolError,
    SchwabTransportError,
    SchwabMarketWorker,
    SchwabOAuthSession,
    build_book_subscription,
    build_login_request,
    main,
    validate_command_ack,
    worker_enabled,
)


class MutableClock:
    def __init__(self, now: float = 1_000.0, step: float = 0.0) -> None:
        self.now = float(now)
        self.step = float(step)

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class MemoryOAuthStore:
    """Small in-memory implementation of the worker's persistence boundary."""

    def __init__(self, tokens: OAuthTokenSet | None = None) -> None:
        self.state_digests: dict[str, float] = {}
        self.tokens = tokens
        self.saved_state_calls: list[tuple[str, float]] = []
        self.consumed_state_calls: list[tuple[str, float]] = []
        self.cas_calls: list[tuple[OAuthTokenSet | None, OAuthTokenSet]] = []

    def save_state_digest(self, digest: str, expires_at_epoch: float) -> None:
        self.saved_state_calls.append((digest, expires_at_epoch))
        self.state_digests[digest] = expires_at_epoch

    def consume_state_digest(self, digest: str, now_epoch: float) -> bool:
        self.consumed_state_calls.append((digest, now_epoch))
        expires_at = self.state_digests.pop(digest, None)
        return expires_at is not None and expires_at > now_epoch

    def load_tokens(self) -> OAuthTokenSet | None:
        return self.tokens

    def compare_and_swap_tokens(
        self,
        expected: OAuthTokenSet | None,
        replacement: OAuthTokenSet,
    ) -> bool:
        self.cas_calls.append((expected, replacement))
        if self.tokens != expected:
            return False
        self.tokens = replacement
        return True


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = int(status_code)
        self._payload = payload
        self.text = json.dumps(payload, separators=(",", ":"))

    def json(self) -> object:
        return self._payload

    def select_streamer_info(self) -> object:
        if not isinstance(self._payload, dict):
            raise TypeError("payload is not a mapping")
        rows = self._payload.get("streamerInfo")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise KeyError("streamerInfo")
        allowed = {
            "streamerSocketUrl",
            "schwabClientCustomerId",
            "schwabClientCorrelId",
            "schwabClientChannel",
            "schwabClientFunctionId",
        }
        return {key: value for key, value in rows[0].items() if key in allowed}


class ScriptedHTTP:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((method, url, dict(kwargs)))
        if not self.responses:
            raise AssertionError(f"Unexpected HTTP call: {method} {url}")
        return self.responses.popleft()


def oauth_session(
    *,
    store: MemoryOAuthStore,
    http: ScriptedHTTP,
    clock: MutableClock | None = None,
) -> SchwabOAuthSession:
    return SchwabOAuthSession(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://atom.example/schwab/callback",
        store=store,
        http=http,
        clock=clock or MutableClock(),
        state_factory=lambda: "plaintext-state",
    )


class DisabledEntrypointTests(unittest.TestCase):
    def test_disabled_is_default_and_does_not_construct_worker(self) -> None:
        created: list[object] = []

        def factory(*_args: object, **_kwargs: object) -> object:
            created.append(object())
            raise AssertionError("disabled main must not construct a worker")

        self.assertFalse(worker_enabled({}))
        self.assertEqual(main(env={}, worker_factory=factory), 0)
        self.assertEqual(created, [])

    def test_disabled_main_does_not_read_secret_environment(self) -> None:
        class GuardedEnvironment(dict[str, str]):
            def get(self, key: str, default: object = None) -> object:
                if key != "ATOM_SCHWAB_MARKET_DATA_ENABLED":
                    raise AssertionError(f"disabled path read secret {key}")
                return super().get(key, default)

        env = GuardedEnvironment(ATOM_SCHWAB_MARKET_DATA_ENABLED="false")
        self.assertEqual(main(env=env, worker_factory=lambda: None), 0)

    def test_enabled_without_injected_factory_fails_closed(self) -> None:
        env = {"ATOM_SCHWAB_MARKET_DATA_ENABLED": "true"}
        self.assertNotEqual(main(env=env, worker_factory=None), 0)

    def test_disabled_fresh_import_does_not_inspect_proxy_environment(self) -> None:
        code = """
import urllib.request
def forbidden_proxy_read():
    raise AssertionError('disabled import inspected proxy environment')
urllib.request.getproxies = forbidden_proxy_read
from quant.schwab_market_worker import main
assert main(env={}) == 0
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class OAuthBoundaryTests(unittest.TestCase):
    def test_token_repr_never_contains_secret_values(self) -> None:
        tokens = OAuthTokenSet(
            "ACCESS_TOKEN_SENTINEL",
            "REFRESH_TOKEN_SENTINEL",
            10_000.0,
        )
        rendered = repr(tokens)
        self.assertNotIn("ACCESS_TOKEN_SENTINEL", rendered)
        self.assertNotIn("REFRESH_TOKEN_SENTINEL", rendered)

    def test_invalid_dataclass_token_record_is_rejected(self) -> None:
        store = MemoryOAuthStore(OAuthTokenSet("", "refresh-token", 10_000.0))
        session = oauth_session(store=store, http=ScriptedHTTP())
        with self.assertRaises(SchwabAuthorizationError):
            session.access_token()

    def test_oauth_state_is_digest_only_expiring_and_single_use(self) -> None:
        clock = MutableClock(1_000.0)
        store = MemoryOAuthStore()
        http = ScriptedHTTP(
            FakeResponse(
                200,
                {
                    "access_token": "access-one",
                    "refresh_token": "refresh-one",
                    "expires_in": 1_800,
                },
            )
        )
        session = oauth_session(store=store, http=http, clock=clock)

        authorization_url = session.authorize_url()
        parsed = urlsplit(authorization_url)
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            SCHWAB_AUTHORIZE_URL,
        )
        self.assertEqual(parse_qs(parsed.query)["state"], ["plaintext-state"])
        expected_digest = hashlib.sha256(b"plaintext-state").hexdigest()
        self.assertEqual(store.saved_state_calls, [(expected_digest, 1_600.0)])
        self.assertEqual(store.state_digests, {expected_digest: 1_600.0})
        self.assertNotIn("plaintext-state", repr(store.state_digests))

        with self.assertRaises(SchwabAuthorizationError):
            session.handle_callback(code="auth-code", state="wrong-state")
        self.assertEqual(http.calls, [])

        tokens = session.handle_callback(code="auth-code", state="plaintext-state")
        self.assertEqual(tokens.access_token, "access-one")
        self.assertEqual(len(http.calls), 1)

        with self.assertRaises(SchwabAuthorizationError):
            session.handle_callback(code="auth-code-replay", state="plaintext-state")
        self.assertEqual(len(http.calls), 1, "replayed state must not reach Schwab")

    def test_expired_state_does_not_make_http_request(self) -> None:
        clock = MutableClock(2_000.0)
        store = MemoryOAuthStore()
        http = ScriptedHTTP()
        session = oauth_session(store=store, http=http, clock=clock)
        session.authorize_url()
        clock.now = 2_601.0

        with self.assertRaises(SchwabAuthorizationError):
            session.handle_callback(code="auth-code", state="plaintext-state")
        self.assertEqual(http.calls, [])

    def test_callback_url_is_bound_to_redirect_code_and_state(self) -> None:
        store = MemoryOAuthStore()
        http = ScriptedHTTP(
            FakeResponse(
                200,
                {
                    "access_token": "access-one",
                    "refresh_token": "refresh-one",
                    "expires_in": 1_800,
                },
            )
        )
        session = oauth_session(
            store=store,
            http=http,
            clock=MutableClock(1_000.0),
        )
        session.authorize_url()

        invalid_callbacks = (
            "https://atom.example/other?code=auth-code&state=plaintext-state",
            "https://atom.example/schwab/callback?code=other&state=plaintext-state",
            "https://atom.example/schwab/callback?code=auth-code&state=other",
        )
        for callback_url in invalid_callbacks:
            with self.subTest(callback_url=callback_url):
                with self.assertRaises(SchwabAuthorizationError):
                    session.handle_callback(
                        code="auth-code",
                        state="plaintext-state",
                        callback_url=callback_url,
                    )
        self.assertEqual(store.consumed_state_calls, [])
        self.assertEqual(http.calls, [])

        tokens = session.handle_callback(
            code="auth-code",
            state="plaintext-state",
            callback_url=(
                "https://atom.example/schwab/callback"
                "?code=auth-code&state=plaintext-state"
            ),
        )
        self.assertEqual(tokens.access_token, "access-one")
        self.assertEqual(len(http.calls), 1)

    def test_callback_cas_does_not_overwrite_token_changed_during_exchange(self) -> None:
        clock = MutableClock(1_000.0)
        store = MemoryOAuthStore()

        class ConcurrentRefreshHTTP(ScriptedHTTP):
            def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
                store.tokens = OAuthTokenSet("other-access", "other-refresh", 9_000.0)
                return super().request(method, url, **kwargs)

        http = ConcurrentRefreshHTTP(
            FakeResponse(
                200,
                {
                    "access_token": "callback-access",
                    "refresh_token": "callback-refresh",
                    "expires_in": 1_800,
                },
            )
        )
        session = oauth_session(store=store, http=http, clock=clock)
        session.authorize_url()

        with self.assertRaises(SchwabAuthorizationError):
            session.handle_callback(code="auth-code", state="plaintext-state")
        self.assertEqual(store.tokens.access_token, "other-access")

    def test_authorization_code_requires_refresh_token_before_persistence(self) -> None:
        for refresh_value in (None, "   "):
            with self.subTest(refresh_token=refresh_value):
                store = MemoryOAuthStore()
                payload: dict[str, object] = {
                    "access_token": "access-one",
                    "expires_in": 1_800,
                }
                if refresh_value is not None:
                    payload["refresh_token"] = refresh_value
                http = ScriptedHTTP(FakeResponse(200, payload))
                session = oauth_session(
                    store=store,
                    http=http,
                    clock=MutableClock(1_000.0),
                )
                session.authorize_url()

                with self.assertRaises(SchwabAuthorizationError):
                    session.handle_callback(
                        code="auth-code",
                        state="plaintext-state",
                    )
                self.assertEqual(len(http.calls), 1)
                self.assertEqual(store.cas_calls, [])
                self.assertIsNone(store.tokens)

    def test_refresh_preserves_omitted_refresh_token_and_exact_post_surface(self) -> None:
        old = OAuthTokenSet(
            access_token="access-old",
            refresh_token="refresh-keep",
            expires_at_epoch=1_010.0,
        )
        store = MemoryOAuthStore(old)
        http = ScriptedHTTP(
            FakeResponse(200, {"access_token": "access-new", "expires_in": 1_800})
        )
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))

        self.assertEqual(session.access_token(), "access-new")
        self.assertIsNotNone(store.tokens)
        self.assertEqual(store.tokens.refresh_token, "refresh-keep")
        self.assertEqual(len(http.calls), 1)
        method, url, kwargs = http.calls[0]
        self.assertEqual((method, url), ("POST", SCHWAB_TOKEN_URL))
        self.assertEqual(
            kwargs.get("data"),
            {"grant_type": "refresh_token", "refresh_token": "refresh-keep"},
        )
        expected_basic = base64.b64encode(b"client-id:client-secret").decode("ascii")
        headers = kwargs.get("headers")
        self.assertIsInstance(headers, dict)
        self.assertEqual(headers.get("Authorization"), f"Basic {expected_basic}")
        self.assertEqual(headers.get("Content-Type"), "application/x-www-form-urlencoded")

    def test_refresh_cas_uses_only_fresh_winner(self) -> None:
        winners = (
            (OAuthTokenSet("winner", "winner-refresh", 9_000.0), "winner"),
            (OAuthTokenSet("stale", "stale-refresh", 1_001.0), None),
        )
        for winner, expected_access in winners:
            with self.subTest(expected_access=expected_access):
                initial = OAuthTokenSet("old", "old-refresh", 1_001.0)
                store = MemoryOAuthStore(initial)

                class RacingHTTP(ScriptedHTTP):
                    def request(
                        self,
                        method: str,
                        url: str,
                        **kwargs: object,
                    ) -> FakeResponse:
                        store.tokens = winner
                        return super().request(method, url, **kwargs)

                http = RacingHTTP(
                    FakeResponse(
                        200,
                        {
                            "access_token": "candidate",
                            "refresh_token": "candidate-refresh",
                            "expires_in": 1_800,
                        },
                    )
                )
                session = oauth_session(
                    store=store,
                    http=http,
                    clock=MutableClock(1_000.0),
                )

                if expected_access is None:
                    with self.assertRaises(SchwabAuthorizationError):
                        session.access_token()
                else:
                    self.assertEqual(session.access_token(), expected_access)
                self.assertEqual(store.tokens, winner)
                self.assertEqual(len(http.calls), 1)

    def test_ndx_get_retries_one_401_after_one_refresh(self) -> None:
        store = MemoryOAuthStore(
            OAuthTokenSet("access-old", "refresh-old", 10_000.0)
        )
        quote_payload = {
            "$NDX": {
                "symbol": "$NDX",
                "quote": {"lastPrice": 19_500.0, "quoteTime": 1_700_000_000_000},
            }
        }
        http = ScriptedHTTP(
            FakeResponse(401, {"error": "expired"}),
            FakeResponse(200, {"access_token": "access-new", "expires_in": 1_800}),
            FakeResponse(200, quote_payload),
        )
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))

        self.assertEqual(session.get_ndx_payload(), quote_payload)
        self.assertEqual([call[0] for call in http.calls], ["GET", "POST", "GET"])
        get_calls = [call for call in http.calls if call[0] == "GET"]
        self.assertEqual(len(get_calls), 2)
        for _, url, kwargs in get_calls:
            self.assertEqual(url, SCHWAB_NDX_QUOTES_URL)
            self.assertEqual(
                kwargs.get("params"),
                {"symbols": "$NDX", "fields": "quote,reference"},
            )
        self.assertEqual(get_calls[0][2]["headers"]["Authorization"], "Bearer access-old")
        self.assertEqual(get_calls[1][2]["headers"]["Authorization"], "Bearer access-new")

    def test_second_401_is_not_retried_again(self) -> None:
        store = MemoryOAuthStore(
            OAuthTokenSet("access-old", "refresh-old", 10_000.0)
        )
        http = ScriptedHTTP(
            FakeResponse(401, {"error": "expired"}),
            FakeResponse(200, {"access_token": "access-new", "expires_in": 1_800}),
            FakeResponse(401, {"error": "still unauthorized"}),
        )
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))

        with self.assertRaises(SchwabAuthorizationError):
            session.get_ndx_payload()
        self.assertEqual([call[0] for call in http.calls], ["GET", "POST", "GET"])

    def test_streamer_info_is_allowlisted_and_exact_get_only(self) -> None:
        store = MemoryOAuthStore(
            OAuthTokenSet("access-token", "refresh-token", 10_000.0)
        )
        raw_info = {
            "streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
            "schwabClientCustomerId": "customer-id",
            "schwabClientCorrelId": "correl-id",
            "schwabClientChannel": "channel",
            "schwabClientFunctionId": "function-id",
            "subscriptionKey": "must-not-escape",
            "clientSecret": "must-not-escape",
        }
        http = ScriptedHTTP(
            FakeResponse(
                200,
                {
                    "accounts": [{"accountNumber": "123456789"}],
                    "streamerInfo": [raw_info],
                    "refresh_token": "injected-refresh-token",
                },
            )
        )
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))

        info = session.get_streamer_info()
        self.assertEqual(
            info,
            {
                "streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
                "schwabClientCustomerId": "customer-id",
                "schwabClientCorrelId": "correl-id",
                "schwabClientChannel": "channel",
                "schwabClientFunctionId": "function-id",
            },
        )
        serialized = json.dumps(info)
        for forbidden in (
            "accounts",
            "accountNumber",
            "123456789",
            "subscriptionKey",
            "must-not-escape",
            "clientSecret",
            "refresh_token",
            "injected-refresh-token",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(len(http.calls), 1)
        method, url, _ = http.calls[0]
        self.assertEqual((method, url), ("GET", SCHWAB_USER_PREFERENCE_URL))

    def test_streamer_info_lexically_skips_poison_account_value(self) -> None:
        store = MemoryOAuthStore(
            OAuthTokenSet("access-token", "refresh-token", 10_000.0)
        )
        raw = b"""{
          "accounts":{"poison":"ACCOUNT_VALUE_MUST_NOT_BE_DECODED"},
          "streamerInfo":[{
            "streamerSocketUrl":"wss://streamer-api.schwab.com/ws",
            "schwabClientCustomerId":"customer-id",
            "schwabClientCorrelId":"correl-id",
            "schwabClientChannel":"channel",
            "schwabClientFunctionId":"function-id",
            "subscriptionKey":"SUBSCRIPTION_KEY_MUST_NOT_BE_DECODED",
            "clientSecret":"CLIENT_SECRET_MUST_NOT_BE_DECODED"
          }],
          "offers":{"poison":"OTHER_VALUE_MUST_NOT_BE_DECODED"}
        }"""
        response = _UrlLibResponse(200, raw)
        http = ScriptedHTTP(response)
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))
        real_loads = json.loads
        decoded_slices: list[str] = []

        def guarded_loads(value: object, *args: object, **kwargs: object) -> object:
            text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
            if "MUST_NOT_BE_DECODED" in text:
                raise AssertionError("non-streamer top-level value was decoded")
            decoded_slices.append(text)
            return real_loads(value, *args, **kwargs)

        with patch("quant.schwab_market_worker.json.loads", side_effect=guarded_loads):
            info = session.get_streamer_info()

        self.assertEqual(info["streamerSocketUrl"], "wss://streamer-api.schwab.com/ws")
        self.assertEqual(len(decoded_slices), 5)
        self.assertEqual(
            {real_loads(value) for value in decoded_slices},
            {
                "wss://streamer-api.schwab.com/ws",
                "customer-id",
                "correl-id",
                "channel",
                "function-id",
            },
        )
        decoded = " ".join(decoded_slices)
        for forbidden in ("accounts", "subscriptionKey", "clientSecret", "MUST_NOT"):
            self.assertNotIn(forbidden, decoded)
        self.assertEqual(response._body, b"")

    def test_streamer_url_rejects_redirectable_private_and_confusable_hosts(self) -> None:
        invalid_urls = (
            "ws://streamer-api.schwab.com/ws",
            "wss://evil.example/ws",
            "wss://127.0.0.1/ws",
            "wss://streamer-api.schwab.com.evil.example/ws",
            "wss://streamer-api.schwab.com@evil.example/ws",
            "wss://streamer-api.schwab.com:8443/ws",
            "wss://streamer-api.schwab.com/private",
            "wss://streamer-api.schwab.com/ws?redirect=evil",
            "wss://streamer-apі.schwab.com/ws",
        )
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                store = MemoryOAuthStore(
                    OAuthTokenSet("access-token", "refresh-token", 10_000.0)
                )
                http = ScriptedHTTP(
                    FakeResponse(
                        200,
                        {
                            "streamerInfo": [
                                {
                                    "streamerSocketUrl": invalid_url,
                                    "schwabClientCustomerId": "customer-id",
                                    "schwabClientCorrelId": "correl-id",
                                    "schwabClientChannel": "channel",
                                    "schwabClientFunctionId": "function-id",
                                }
                            ]
                        },
                    )
                )
                session = oauth_session(store=store, http=http)
                with self.assertRaises(SchwabProtocolError):
                    session.get_streamer_info()

    def test_http_and_websocket_transports_disable_redirects(self) -> None:
        self.assertIsNone(_NoRedirect().redirect_request(object()))
        create_connection = Mock()
        with patch.dict(
            sys.modules,
            {"websocket": SimpleNamespace(create_connection=create_connection)},
        ):
            _default_websocket_factory(
                "wss://streamer-api.schwab.com/ws",
                timeout=5.0,
            )
        create_connection.assert_called_once_with(
            "wss://streamer-api.schwab.com/ws",
            timeout=5.0,
            enable_multithread=True,
            redirect_limit=0,
        )

    def test_stdlib_http_transport_bounds_and_discards_bodies(self) -> None:
        class OpenedResponse:
            def __init__(self, body: bytes, status: int = 200) -> None:
                self.body = body
                self.status = status
                self.read_limits: list[int] = []

            def __enter__(self) -> OpenedResponse:
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

            def read(self, limit: int) -> bytes:
                self.read_limits.append(limit)
                return self.body

        class Opener:
            def __init__(self, result: OpenedResponse | Exception) -> None:
                self.result = result
                self.calls: list[tuple[object, object]] = []

            def open(self, request: object, timeout: object = None) -> OpenedResponse:
                self.calls.append((request, timeout))
                if isinstance(self.result, Exception):
                    raise self.result
                return self.result

        opened = OpenedResponse(b'{"ok":true}', status=201)
        opener = Opener(opened)
        with patch(
            "quant.schwab_market_worker.build_opener",
            return_value=opener,
        ):
            response = _UrlLibHttp().request(
                "get",
                "https://example.test/path?prior=1",
                headers={"X-Test": "value"},
                data={"form": "value"},
                params={"symbols": "$NDX"},
                timeout=3.0,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(response._body, b"")
        self.assertEqual(opened.read_limits, [MAX_RESPONSE_BYTES + 1])
        request, timeout = opener.calls[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.data, b"form=value")
        self.assertIn("symbols=%24NDX", request.full_url)
        self.assertEqual(timeout, 3.0)

        oversized = OpenedResponse(b"x" * (MAX_RESPONSE_BYTES + 1))
        with patch(
            "quant.schwab_market_worker.build_opener",
            return_value=Opener(oversized),
        ):
            with self.assertRaises(SchwabProtocolError):
                _UrlLibHttp().request("GET", "https://example.test")

        redirect = HTTPError(
            "https://example.test",
            307,
            "redirect rejected",
            None,
            None,
        )
        with patch(
            "quant.schwab_market_worker.build_opener",
            return_value=Opener(redirect),
        ):
            rejected = _UrlLibHttp().request("GET", "https://example.test")
        self.assertEqual(rejected.status_code, 307)
        self.assertEqual(rejected._body, b"")

    def test_stream_protocol_rejects_invalid_ack_and_frames(self) -> None:
        valid_ack = {
            "response": [
                {
                    "requestid": "0",
                    "service": "ADMIN",
                    "command": "LOGIN",
                    "content": {"code": 0},
                }
            ]
        }
        validate_command_ack(
            valid_ack,
            request_id="0",
            service="ADMIN",
            command="LOGIN",
        )
        invalid_acks = (
            {},
            {
                "response": [
                    {
                        "requestid": "9",
                        "service": "ADMIN",
                        "command": "LOGIN",
                        "content": {"code": 0},
                    }
                ]
            },
            {
                "response": [
                    {
                        "requestid": "0",
                        "service": "ADMIN",
                        "command": "LOGIN",
                        "content": {"code": True},
                    }
                ]
            },
            {
                "response": [
                    {
                        "requestid": "0",
                        "service": "ADMIN",
                        "command": "LOGIN",
                        "content": {"code": "bad"},
                    }
                ]
            },
            {
                "response": [
                    {
                        "requestid": "0",
                        "service": "ADMIN",
                        "command": "LOGIN",
                        "content": {"code": 7},
                    }
                ]
            },
        )
        for invalid_ack in invalid_acks:
            with self.subTest(invalid_ack=invalid_ack):
                with self.assertRaises(SchwabProtocolError):
                    validate_command_ack(
                        invalid_ack,
                        request_id="0",
                        service="ADMIN",
                        command="LOGIN",
                    )

        self.assertEqual(_decode_stream_message(b'{"data":[]}'), {"data": []})
        invalid_frames = (
            (b"\xff", SchwabProtocolError),
            ("", SchwabTransportError),
            ("{", SchwabProtocolError),
            ("[]", SchwabProtocolError),
        )
        for frame, error_type in invalid_frames:
            with self.subTest(frame=frame):
                with self.assertRaises(error_type):
                    _decode_stream_message(frame)

    def test_http_surface_contains_only_authorized_s1_endpoints(self) -> None:
        store = MemoryOAuthStore(
            OAuthTokenSet("access-token", "refresh-token", 10_000.0)
        )
        http = ScriptedHTTP(
            FakeResponse(200, {"$NDX": {"quote": {"lastPrice": 19_500.0}}}),
            FakeResponse(
                200,
                {
                    "streamerInfo": [
                        {
                            "streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
                            "schwabClientCustomerId": "customer-id",
                            "schwabClientCorrelId": "correl-id",
                            "schwabClientChannel": "channel",
                            "schwabClientFunctionId": "function-id",
                        }
                    ]
                },
            ),
        )
        session = oauth_session(store=store, http=http, clock=MutableClock(1_000.0))

        session.get_ndx_payload()
        session.get_streamer_info()
        self.assertEqual(
            [(method, url) for method, url, _ in http.calls],
            [
                ("GET", SCHWAB_NDX_QUOTES_URL),
                ("GET", SCHWAB_USER_PREFERENCE_URL),
            ],
        )
        surface = " ".join(url.lower() for _, url, _ in http.calls)
        for forbidden in ("/accounts", "/orders", "/transactions"):
            self.assertNotIn(forbidden, surface)


class ScriptedLease:
    def __init__(self, acquire: bool = True, renew: tuple[bool, ...] = (True,)) -> None:
        self.acquire_result = acquire
        self.renew_results = deque(renew)
        self.acquire_calls: list[tuple[str, float]] = []
        self.renew_calls: list[tuple[str, float]] = []
        self.release_calls: list[str] = []

    def acquire(self, owner_token: str, ttl_seconds: float) -> bool:
        self.acquire_calls.append((owner_token, ttl_seconds))
        return self.acquire_result

    def renew(self, owner_token: str, ttl_seconds: float) -> bool:
        self.renew_calls.append((owner_token, ttl_seconds))
        if self.renew_results:
            return self.renew_results.popleft()
        return True

    def release(self, owner_token: str) -> None:
        self.release_calls.append(owner_token)


class FakeBus:
    def __init__(self, *, stop_when_both: threading.Event | None = None) -> None:
        self.ndx: list[object] = []
        self.books: list[object] = []
        self.ndx_published = threading.Event()
        self.book_published = threading.Event()
        self.stop_when_both = stop_when_both
        self.owner_tokens: list[str] = []

    def _stop_if_complete(self) -> None:
        if (
            self.stop_when_both is not None
            and self.ndx_published.is_set()
            and self.book_published.is_set()
        ):
            self.stop_when_both.set()

    def publish_ndx(self, payload: object, *, owner_token: str) -> bool:
        self.ndx.append(payload)
        self.owner_tokens.append(owner_token)
        self.ndx_published.set()
        self._stop_if_complete()
        return True

    def publish_book(self, payload: object, *, owner_token: str) -> bool:
        self.books.append(payload)
        self.owner_tokens.append(owner_token)
        self.book_published.set()
        self._stop_if_complete()
        return True


class FakeOAuth:
    def __init__(self) -> None:
        self.streamer_info_calls = 0
        self.access_token_calls = 0
        self.ndx_calls = 0

    def get_streamer_info(self) -> dict[str, str]:
        self.streamer_info_calls += 1
        return {
            "streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
            "schwabClientCustomerId": "customer-id",
            "schwabClientCorrelId": "correl-id",
            "schwabClientChannel": "channel",
            "schwabClientFunctionId": "function-id",
        }

    def access_token(self, force_refresh: bool = False) -> str:
        self.access_token_calls += 1
        return "stream-access-token"

    def get_ndx_payload(self) -> dict[str, object]:
        self.ndx_calls += 1
        return {
            "$NDX": {
                "symbol": "$NDX",
                "quote": {
                    "lastPrice": 19_500.0,
                    "quoteTime": 1_700_000_000_000,
                    "tradeTime": 1_700_000_000_000,
                },
            }
        }


def ack(service: str, command: str, request_id: str) -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": service,
                    "command": command,
                    "requestid": request_id,
                    "content": {"code": 0, "msg": "OK"},
                }
            ]
        }
    )


def book_frame() -> str:
    return json.dumps(
        {
            "data": [
                {
                    "service": "NASDAQ_BOOK",
                    "timestamp": 1_700_000_000_100,
                    "content": [
                        {
                            "0": "COIN",
                            "1": 1_700_000_000_000,
                            "2": [
                                {"0": 200.0, "1": 30.0},
                                {"0": 199.9, "1": 20.0},
                                {"0": 199.8, "1": 10.0},
                            ],
                            "3": [
                                {"0": 200.1, "1": 20.0},
                                {"0": 200.2, "1": 15.0},
                                {"0": 200.3, "1": 10.0},
                            ],
                        }
                    ],
                }
            ]
        }
    )


class ScriptedSocket:
    def __init__(
        self,
        frames: tuple[str, ...],
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.frames = deque(frames)
        self.stop_event = stop_event
        self.sent: list[str] = []
        self.close_calls = 0

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        if self.frames:
            value = self.frames.popleft()
            if value == "__STOP__":
                if self.stop_event is not None:
                    self.stop_event.set()
                raise TimeoutError("scripted stop")
            return value
        raise TimeoutError("no scripted frame")

    def close(self) -> None:
        self.close_calls += 1


class SocketFactory:
    def __init__(self, socket: ScriptedSocket | None = None, error: Exception | None = None) -> None:
        self.socket = socket
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, url: str, **kwargs: object) -> ScriptedSocket:
        self.calls.append((url, dict(kwargs)))
        if self.error is not None:
            raise self.error
        if self.socket is None:
            raise AssertionError("no scripted socket")
        return self.socket


class StoppingEvent:
    def __init__(self) -> None:
        self.stopped = False
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, seconds: float) -> bool:
        if threading.current_thread().name == "atom-schwab-ndx-observer":
            return True
        self.waits.append(seconds)
        self.stopped = True
        return True


class WorkerLeaseAndStreamTests(unittest.TestCase):
    def test_clock_failure_after_acquire_releases_once_and_clears_ownership(self) -> None:
        class FailingClock:
            def __call__(self) -> float:
                raise RuntimeError("clock unavailable")

        bus = FakeBus()
        oauth = FakeOAuth()
        lease = ScriptedLease()
        socket_factory = SocketFactory(error=AssertionError("must not connect"))
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=oauth,
            lease=lease,
            websocket_factory=socket_factory,
            stop_event=threading.Event(),
            clock=FailingClock(),
            owner_token="owner-one",
        )

        with self.assertRaisesRegex(RuntimeError, "clock unavailable"):
            worker.run()

        self.assertEqual(lease.release_calls, ["owner-one"])
        self.assertFalse(worker._owned)
        self.assertIsNone(worker._ndx_thread)
        self.assertEqual(oauth.streamer_info_calls, 0)
        self.assertEqual(oauth.access_token_calls, 0)
        self.assertEqual(oauth.ndx_calls, 0)
        self.assertEqual(socket_factory.calls, [])
        self.assertEqual(bus.ndx, [])
        self.assertEqual(bus.books, [])

    def test_thread_start_failure_releases_once_and_clears_ownership(self) -> None:
        bus = FakeBus()
        oauth = FakeOAuth()
        lease = ScriptedLease()
        socket_factory = SocketFactory(error=AssertionError("must not connect"))
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=oauth,
            lease=lease,
            websocket_factory=socket_factory,
            stop_event=threading.Event(),
            clock=MutableClock(1_700_000_001.0),
            owner_token="owner-one",
        )

        with patch(
            "quant.schwab_market_worker.threading.Thread.start",
            side_effect=RuntimeError("thread unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
                worker.run()

        self.assertEqual(lease.release_calls, ["owner-one"])
        self.assertFalse(worker._owned)
        self.assertIsNone(worker._ndx_thread)
        self.assertEqual(oauth.streamer_info_calls, 0)
        self.assertEqual(oauth.access_token_calls, 0)
        self.assertEqual(oauth.ndx_calls, 0)
        self.assertEqual(socket_factory.calls, [])
        self.assertEqual(bus.ndx, [])
        self.assertEqual(bus.books, [])

    def test_ndx_publishes_when_streamer_is_unavailable(self) -> None:
        stop_event = threading.Event()

        class StreamerUnavailableOAuth(FakeOAuth):
            def get_streamer_info(self) -> dict[str, str]:
                self.streamer_info_calls += 1
                raise SchwabProtocolError("streamer unavailable")

        class NdxStoppingBus(FakeBus):
            def publish_ndx(self, payload: object, *, owner_token: str) -> bool:
                result = super().publish_ndx(payload, owner_token=owner_token)
                stop_event.set()
                return result

        bus = NdxStoppingBus()
        socket_factory = SocketFactory(error=AssertionError("must not connect"))
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=StreamerUnavailableOAuth(),
            lease=ScriptedLease(),
            websocket_factory=socket_factory,
            stop_event=stop_event,
            clock=MutableClock(1_700_000_001.0),
            owner_token="one-lease-owner",
            reconnect_min_seconds=0.1,
        )

        self.assertTrue(worker.run())
        self.assertEqual(len(bus.ndx), 1)
        self.assertEqual(bus.books, [])
        self.assertEqual(bus.owner_tokens, ["one-lease-owner"])
        self.assertEqual(socket_factory.calls, [])

    def test_multiple_book_rows_do_not_renew_lease_per_row(self) -> None:
        clock = MutableClock(1_700_000_001.0)
        lease = ScriptedLease()
        bus = FakeBus()
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=FakeOAuth(),
            lease=lease,
            websocket_factory=SocketFactory(error=AssertionError("unused")),
            stop_event=threading.Event(),
            clock=clock,
            owner_token="one-lease-owner",
        )
        with worker._lease_lock:
            worker._owned = True
            worker._next_renewal = clock.now + 15.0
        first = json.loads(book_frame())["data"][0]["content"][0]
        second = json.loads(json.dumps(first))
        second["1"] += 1_000
        message = {
            "data": [
                {
                    "service": "NASDAQ_BOOK",
                    "content": [first, second],
                }
            ]
        }

        worker._publish_book_rows(message)
        self.assertEqual(len(bus.books), 2)
        self.assertEqual(lease.renew_calls, [])
        self.assertEqual(bus.owner_tokens, ["one-lease-owner", "one-lease-owner"])

    def test_request_builders_allow_only_login_and_coin_book(self) -> None:
        login = build_login_request(
            customer_id="customer-id",
            correl_id="correl-id",
            channel="channel",
            function_id="function-id",
            access_token="access-token",
        )
        subscription = build_book_subscription(
            customer_id="customer-id",
            correl_id="correl-id",
        )
        self.assertEqual(
            login,
            {
                "requests": [
                    {
                        "service": "ADMIN",
                        "requestid": "0",
                        "command": "LOGIN",
                        "SchwabClientCustomerId": "customer-id",
                        "SchwabClientCorrelId": "correl-id",
                        "parameters": {
                            "Authorization": "access-token",
                            "SchwabClientChannel": "channel",
                            "SchwabClientFunctionId": "function-id",
                        },
                    }
                ]
            },
        )
        self.assertEqual(
            subscription,
            {
                "requests": [
                    {
                        "service": "NASDAQ_BOOK",
                        "requestid": "2",
                        "command": "SUBS",
                        "SchwabClientCustomerId": "customer-id",
                        "SchwabClientCorrelId": "correl-id",
                        "parameters": {"keys": "COIN", "fields": "0,1,2,3"},
                    }
                ]
            },
        )
        serialized = json.dumps([login, subscription])
        self.assertNotIn("ACCT_ACTIVITY", serialized)

    def test_nonowner_opens_no_oauth_socket_or_publish_path(self) -> None:
        bus = FakeBus()
        oauth = FakeOAuth()
        lease = ScriptedLease(acquire=False)
        socket_factory = SocketFactory(error=AssertionError("must not connect"))
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=oauth,
            lease=lease,
            websocket_factory=socket_factory,
            stop_event=threading.Event(),
            owner_token="owner-one",
        )

        self.assertFalse(worker.run())
        self.assertEqual(oauth.streamer_info_calls, 0)
        self.assertEqual(oauth.access_token_calls, 0)
        self.assertEqual(oauth.ndx_calls, 0)
        self.assertEqual(socket_factory.calls, [])
        self.assertEqual(bus.ndx, [])
        self.assertEqual(bus.books, [])
        self.assertEqual(lease.release_calls, [])

    def test_stream_sends_exactly_login_then_coin_book_subscription(self) -> None:
        stop_event = threading.Event()
        socket = ScriptedSocket(
            (
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
                book_frame(),
            ),
            stop_event=stop_event,
        )
        bus = FakeBus(stop_when_both=stop_event)
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=FakeOAuth(),
            lease=ScriptedLease(),
            websocket_factory=SocketFactory(socket=socket),
            stop_event=stop_event,
            clock=MutableClock(1_700_000_001.0),
            owner_token="owner-one",
        )

        self.assertTrue(worker.run())
        sent = [json.loads(payload) for payload in socket.sent]
        self.assertEqual(len(sent), 2)
        first = sent[0]["requests"][0]
        second = sent[1]["requests"][0]
        self.assertEqual((first["service"], first["command"]), ("ADMIN", "LOGIN"))
        self.assertEqual((first["requestid"], second["requestid"]), ("0", "2"))
        self.assertEqual(
            (second["service"], second["command"]),
            ("NASDAQ_BOOK", "SUBS"),
        )
        self.assertEqual(second["parameters"], {"keys": "COIN", "fields": "0,1,2,3"})
        self.assertNotIn("ACCT_ACTIVITY", json.dumps(sent))
        self.assertEqual(len(bus.ndx), 1)
        self.assertEqual(len(bus.books), 1)
        self.assertEqual(set(bus.owner_tokens), {"owner-one"})
        self.assertGreaterEqual(socket.close_calls, 1)

    def test_slow_ndx_does_not_delay_first_book_or_leave_nondaemon_helper(self) -> None:
        stop_event = threading.Event()
        ndx_started = threading.Event()
        release_ndx = threading.Event()

        class BlockingNdxOAuth(FakeOAuth):
            def get_ndx_payload(self) -> dict[str, object]:
                ndx_started.set()
                if not release_ndx.wait(2.0):
                    raise AssertionError("test did not release blocked NDX request")
                return super().get_ndx_payload()

        socket = ScriptedSocket(
            (
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
                book_frame(),
            )
        )
        bus = FakeBus()
        worker = SchwabMarketWorker(
            bus=bus,
            oauth=BlockingNdxOAuth(),
            lease=ScriptedLease(),
            websocket_factory=SocketFactory(socket=socket),
            stop_event=stop_event,
            clock=MutableClock(1_700_000_001.0),
            owner_token="owner-one",
        )
        runner = threading.Thread(target=worker.run, name="test-schwab-worker")
        runner.start()
        try:
            self.assertTrue(ndx_started.wait(1.0))
            self.assertTrue(
                bus.book_published.wait(0.5),
                "a blocked NDX GET delayed the first COIN book",
            )
            helper = worker._ndx_thread
            self.assertIsNotNone(helper)
            self.assertTrue(helper.daemon)
        finally:
            stop_event.set()
            release_ndx.set()
            runner.join(2.0)
        self.assertFalse(runner.is_alive())
        helper = worker._ndx_thread
        if helper is not None:
            helper.join(1.0)
            self.assertFalse(helper.is_alive())
        self.assertFalse(
            any(
                thread.name == "atom-schwab-ndx-observer" and not thread.daemon
                for thread in threading.enumerate()
            )
        )

    def test_lease_loss_closes_socket_without_reconnect(self) -> None:
        socket = ScriptedSocket(
            (
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
            )
        )
        class MainLosingLease(ScriptedLease):
            def __init__(self) -> None:
                super().__init__()
                self.main_renewals = 0

            def renew(self, owner_token: str, ttl_seconds: float) -> bool:
                self.renew_calls.append((owner_token, ttl_seconds))
                if threading.current_thread().name != "atom-schwab-ndx-observer":
                    self.main_renewals += 1
                    return self.main_renewals < 4
                return True

        lease = MainLosingLease()
        factory = SocketFactory(socket=socket)
        worker = SchwabMarketWorker(
            bus=FakeBus(),
            oauth=FakeOAuth(),
            lease=lease,
            websocket_factory=factory,
            stop_event=threading.Event(),
            clock=MutableClock(1_000.0, step=1.0),
            owner_token="owner-one",
            lease_renew_interval_seconds=0.1,
        )

        self.assertFalse(worker.run())
        self.assertEqual(len(factory.calls), 1)
        self.assertGreaterEqual(socket.close_calls, 1)
        self.assertEqual(lease.main_renewals, 4)

    def test_poll_lease_loss_during_reconnect_sends_no_new_login(self) -> None:
        ndx_entered = threading.Event()
        release_ndx = threading.Event()
        poll_close_done = threading.Event()

        clock = MutableClock(1_700_000_001.0)

        class BlockingNdxOAuth(FakeOAuth):
            def get_ndx_payload(self) -> dict[str, object]:
                ndx_entered.set()
                if not release_ndx.wait(2.0):
                    raise AssertionError("test did not release NDX")
                clock.now += 20.0
                return super().get_ndx_payload()

        class PollLosingLease(ScriptedLease):
            def __init__(self) -> None:
                super().__init__()
                self.poll_renewals = 0

            def renew(self, owner_token: str, ttl_seconds: float) -> bool:
                self.renew_calls.append((owner_token, ttl_seconds))
                if threading.current_thread().name == "atom-schwab-ndx-observer":
                    self.poll_renewals += 1
                    return False
                return True

        class DisconnectingSocket(ScriptedSocket):
            def recv(self) -> str:
                if not self.frames:
                    raise ConnectionError("first stream disconnected")
                return super().recv()

        first = DisconnectingSocket(
            (
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
            )
        )
        second = ScriptedSocket(())
        stop_event = threading.Event()

        class ReconnectFactory:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, url: str, **kwargs: object) -> ScriptedSocket:
                self.calls += 1
                if self.calls == 1:
                    return first
                self.assert_second_call()
                return second

            @staticmethod
            def assert_second_call() -> None:
                if not ndx_entered.wait(2.0):
                    stop_event.set()
                    raise AssertionError("NDX poll did not enter")
                release_ndx.set()
                if not poll_close_done.wait(2.0):
                    stop_event.set()
                    raise AssertionError("poll lease loss did not close")

        factory = ReconnectFactory()
        worker = SchwabMarketWorker(
            bus=FakeBus(),
            oauth=BlockingNdxOAuth(),
            lease=PollLosingLease(),
            websocket_factory=factory,
            stop_event=stop_event,
            clock=clock,
            owner_token="owner-one",
            reconnect_min_seconds=0.1,
        )
        original_close = worker._close_socket

        def observed_close() -> None:
            original_close()
            if threading.current_thread().name == "atom-schwab-ndx-observer":
                poll_close_done.set()

        worker._close_socket = observed_close
        results: list[bool] = []
        runner = threading.Thread(target=lambda: results.append(worker.run()))
        runner.start()
        runner.join(3.0)
        if runner.is_alive():
            stop_event.set()
            release_ndx.set()
            runner.join(2.0)
        self.assertFalse(runner.is_alive(), "lease-loss regression test hung")
        self.assertEqual(results, [False])
        self.assertEqual(worker.status, "LEASE_LOST")
        self.assertEqual(factory.calls, 2)
        self.assertEqual(second.sent, [])
        self.assertGreaterEqual(second.close_calls, 1)

    def test_stop_event_bounds_reconnect_backoff(self) -> None:
        stop_event = StoppingEvent()
        lease = ScriptedLease()
        factory = SocketFactory(error=ConnectionError("offline"))
        worker = SchwabMarketWorker(
            bus=FakeBus(),
            oauth=FakeOAuth(),
            lease=lease,
            websocket_factory=factory,
            stop_event=stop_event,
            owner_token="owner-one",
            reconnect_min_seconds=0.25,
            reconnect_max_seconds=1.0,
        )

        self.assertTrue(worker.run())
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(stop_event.waits, [0.25])
        self.assertEqual(lease.release_calls, ["owner-one"])

    def test_reconnect_backoff_clamps_large_values_to_hard_bound(self) -> None:
        stop_event = StoppingEvent()
        worker = SchwabMarketWorker(
            bus=FakeBus(),
            oauth=FakeOAuth(),
            lease=ScriptedLease(),
            websocket_factory=SocketFactory(error=ConnectionError("offline")),
            stop_event=stop_event,
            owner_token="owner-one",
            reconnect_min_seconds=120.0,
            reconnect_max_seconds=240.0,
        )

        self.assertTrue(worker.run())
        self.assertEqual(stop_event.waits, [30.0])

    def test_nonfinite_reconnect_backoff_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SchwabMarketWorker(
                bus=FakeBus(),
                oauth=FakeOAuth(),
                lease=ScriptedLease(),
                websocket_factory=SocketFactory(error=ConnectionError("offline")),
                stop_event=threading.Event(),
                owner_token="owner-one",
                reconnect_min_seconds=float("inf"),
            )


if __name__ == "__main__":
    unittest.main()
