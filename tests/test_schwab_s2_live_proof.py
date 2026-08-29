"""Regression tests for the bounded Schwab S2 live-source proof."""

from __future__ import annotations

import json
import threading
import time
import unittest

from quant import schwab_market_bus, schwab_market_worker
import schwab_s2_live_proof as s2


NOW = 1_700_000_001.0


def ndx_payload() -> dict[str, object]:
    return {
        "$NDX": {
            "symbol": "$NDX",
            "quote": {
                "lastPrice": 15_000.0,
                "mark": 15_000.0,
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


class Response:
    def __init__(
        self,
        status_code: int,
        *,
        payload: object | None = None,
        streamer_info: object | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._streamer_info = streamer_info

    def json(self) -> object:
        return self._payload

    def select_streamer_info(self) -> object:
        return self._streamer_info


class ProofHTTP:
    def __init__(self, *, ndx_status: int = 200) -> None:
        self.ndx_status = ndx_status
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def request(self, method: str, url: str, **kwargs: object) -> Response:
        with self._lock:
            self.calls.append((method, url, dict(kwargs)))
        if url == schwab_market_worker.SCHWAB_USER_PREFERENCE_URL:
            return Response(
                200,
                streamer_info={
                    "streamerSocketUrl": schwab_market_worker.SCHWAB_STREAMER_URL,
                    "schwabClientCustomerId": "customer-id",
                    "schwabClientCorrelId": "correl-id",
                    "schwabClientChannel": "channel",
                    "schwabClientFunctionId": "function-id",
                },
            )
        if url == schwab_market_worker.SCHWAB_NDX_QUOTES_URL:
            return Response(self.ndx_status, payload=ndx_payload())
        raise AssertionError(f"unexpected live surface: {url}")


class ScriptedSocket:
    def __init__(self, frames: list[str]) -> None:
        self.frames = list(frames)
        self.sent: list[str] = []
        self.close_calls = 0

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        if self.frames:
            return self.frames.pop(0)
        time.sleep(0.002)
        raise TimeoutError("no more frames")

    def close(self) -> None:
        self.close_calls += 1


class SchwabS2ProofTests(unittest.TestCase):
    def test_live_like_pair_passes_through_merged_s1_and_emits_no_values(self) -> None:
        http = ProofHTTP()
        socket = ScriptedSocket(
            [
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
                book_frame(),
            ]
        )
        factory_calls: list[tuple[str, dict[str, object]]] = []

        def socket_factory(url: str, **kwargs: object) -> ScriptedSocket:
            factory_calls.append((url, dict(kwargs)))
            return socket

        receipt = s2.run_live_proof(
            "live-access-token",
            duration_seconds=0.5,
            http=http,
            websocket_factory=socket_factory,
            wall_clock=lambda: NOW,
        )

        self.assertEqual(receipt.status, "PASS")
        self.assertEqual(receipt.reason, "NONE")
        self.assertTrue(receipt.ndx_observed)
        self.assertTrue(receipt.coin_level2_observed)
        self.assertEqual(receipt.ndx_publications, 1)
        self.assertEqual(receipt.coin_level2_publications, 1)
        self.assertEqual(receipt.streamer_connection_attempts, 1)
        self.assertTrue(receipt.helper_stopped)
        self.assertEqual(
            factory_calls,
            [(schwab_market_worker.SCHWAB_STREAMER_URL, {"timeout": 5.0})],
        )
        sent = [json.loads(value)["requests"][0] for value in socket.sent]
        self.assertEqual(
            [(row["service"], row["command"]) for row in sent],
            [("ADMIN", "LOGIN"), ("NASDAQ_BOOK", "SUBS")],
        )
        self.assertEqual(
            sent[1]["parameters"],
            {"keys": "COIN", "fields": "0,1,2,3"},
        )
        requested_urls = {url for _, url, _ in http.calls}
        self.assertEqual(
            requested_urls,
            {
                schwab_market_worker.SCHWAB_NDX_QUOTES_URL,
                schwab_market_worker.SCHWAB_USER_PREFERENCE_URL,
            },
        )
        serialized = receipt.to_json()
        self.assertNotIn("live-access-token", serialized)
        self.assertNotIn("15000", serialized)
        self.assertNotIn("200.1", serialized)
        self.assertNotIn("bids", serialized)
        self.assertNotIn("asks", serialized)
        self.assertEqual(json.loads(serialized)["coin_level2_authority"], "OBSERVER_ONLY")

    def test_missing_book_fails_after_short_deadline(self) -> None:
        socket = ScriptedSocket(
            [
                ack("ADMIN", "LOGIN", "0"),
                ack("NASDAQ_BOOK", "SUBS", "2"),
            ]
        )
        receipt = s2.run_live_proof(
            "live-access-token",
            duration_seconds=0.05,
            http=ProofHTTP(),
            websocket_factory=lambda url, **kwargs: socket,
            wall_clock=lambda: NOW,
        )

        self.assertEqual(receipt.status, "FAIL")
        self.assertEqual(receipt.reason, "COIN_LEVEL2_NOT_OBSERVED")
        self.assertTrue(receipt.ndx_observed)
        self.assertFalse(receipt.coin_level2_observed)
        self.assertEqual(receipt.streamer_connection_attempts, 1)
        self.assertLess(receipt.elapsed_seconds, 1.0)

    def test_protocol_rejection_is_retained_in_the_sanitized_receipt(self) -> None:
        socket = ScriptedSocket([ack("ADMIN", "LOGIN", "wrong-id")])
        receipt = s2.run_live_proof(
            "live-access-token",
            duration_seconds=0.05,
            http=ProofHTTP(),
            websocket_factory=lambda url, **kwargs: socket,
            wall_clock=lambda: NOW,
        )

        self.assertEqual(receipt.status, "FAIL")
        self.assertEqual(receipt.reason, "PROTOCOL_REJECTED")
        self.assertEqual(receipt.worker_reason, "PROTOCOL_REJECTED")
        self.assertNotIn("live-access-token", receipt.to_json())

    def test_static_access_session_never_refreshes_or_uses_token_store(self) -> None:
        http = ProofHTTP(ndx_status=401)
        session = s2.StaticAccessSchwabSession(
            "live-access-token",
            http=http,
            clock=lambda: NOW,
        )

        with self.assertRaisesRegex(
            schwab_market_worker.SchwabAuthorizationError,
            "schwab_s2_refresh_forbidden",
        ):
            session.get_ndx_payload()

        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0][1], schwab_market_worker.SCHWAB_NDX_QUOTES_URL)
        self.assertEqual(
            http.calls[0][2]["headers"]["Authorization"],
            "Bearer live-access-token",
        )

    def test_sink_keeps_only_counts_and_requires_exact_fenced_s1_shapes(self) -> None:
        now = time.monotonic()
        lease = s2.BoundedProofLease(deadline=now + 5.0, clock=time.monotonic)
        stop_event = threading.Event()
        sink = s2.ProofSink(lease=lease, stop_event=stop_event)
        self.assertTrue(lease.acquire("owner", 45.0))
        ndx = {
            "provider_epoch": NOW - 1,
            "quote_time_epoch": NOW - 1,
            "received_at_epoch": NOW,
            "price": 15_000.0,
            "symbol": "NDX",
            "trade_time_epoch": NOW - 1,
        }
        levels = [
            {"count": 1, "price": 200.0 + index, "size": 10.0}
            for index in range(3)
        ]
        book = {
            "asks": levels,
            "bids": levels,
            "provider_epoch": NOW - 1,
            "received_at_epoch": NOW,
            "source_sequence": 1,
            "symbol": "COIN",
        }

        self.assertFalse(
            sink.publish("atom:forbidden", "{}", 15, "owner")
        )
        self.assertTrue(
            sink.publish(
                schwab_market_bus.NDX_KEY,
                json.dumps(ndx),
                schwab_market_bus.SNAPSHOT_TTL_SECONDS,
                "owner",
            )
        )
        self.assertFalse(stop_event.is_set())
        self.assertTrue(
            sink.publish(
                schwab_market_bus.BOOK_KEY,
                json.dumps(book),
                schwab_market_bus.SNAPSHOT_TTL_SECONDS,
                "owner",
            )
        )
        self.assertTrue(stop_event.is_set())
        self.assertEqual(sink.counts(), (1, 1))

    def test_single_connection_factory_blocks_a_second_live_attempt(self) -> None:
        stop_event = threading.Event()
        calls: list[str] = []

        def factory(url: str, **kwargs: object) -> object:
            calls.append(url)
            return object()

        one = s2.SingleConnectionFactory(factory, stop_event=stop_event)
        self.assertIsNotNone(one("wss://streamer-api.schwab.com/ws", timeout=5.0))
        with self.assertRaisesRegex(
            schwab_market_worker.SchwabProtocolError,
            "schwab_s2_single_connection_only",
        ):
            one("wss://streamer-api.schwab.com/ws", timeout=5.0)
        self.assertEqual(calls, ["wss://streamer-api.schwab.com/ws"])
        self.assertEqual(one.attempts, 1)
        self.assertTrue(stop_event.is_set())

    def test_disabled_entrypoint_reads_no_secret_and_constructs_no_runner(self) -> None:
        class GateOnly(dict[str, str]):
            def get(self, key: str, default: object = None) -> object:
                if key != s2.PROOF_ENABLE_ENV:
                    raise AssertionError(f"read forbidden environment key: {key}")
                return default

        output: list[str] = []

        def forbidden_runner(*args: object, **kwargs: object) -> s2.ProofReceipt:
            raise AssertionError("disabled S2 constructed the live proof")

        self.assertEqual(
            s2.main(GateOnly(), runner=forbidden_runner, emit=output.append),
            2,
        )
        self.assertEqual(json.loads(output[0])["reason"], "S2_NOT_AUTHORIZED")

    def test_enabled_entrypoint_passes_token_without_printing_it(self) -> None:
        output: list[str] = []
        received: list[tuple[str, float]] = []

        def runner(token: str, *, duration_seconds: float) -> s2.ProofReceipt:
            received.append((token, duration_seconds))
            return s2.ProofReceipt(
                status="PASS",
                reason="NONE",
                ndx_observed=True,
                coin_level2_observed=True,
                ndx_publications=1,
                coin_level2_publications=1,
                streamer_connection_attempts=1,
                worker_status="STOPPED",
                worker_reason="STOP_REQUESTED",
                helper_stopped=True,
                elapsed_seconds=1.0,
            )

        code = s2.main(
            {
                s2.PROOF_ENABLE_ENV: "true",
                s2.PROOF_ACCESS_TOKEN_ENV: "live-access-token",
                s2.PROOF_SECONDS_ENV: "10",
            },
            runner=runner,
            emit=output.append,
        )

        self.assertEqual(code, 0)
        self.assertEqual(received, [("live-access-token", 10.0)])
        self.assertEqual(json.loads(output[0])["status"], "PASS")
        self.assertNotIn("live-access-token", output[0])


if __name__ == "__main__":
    unittest.main()
