from datetime import datetime, timezone
import unittest

from quant import web


class V2StateStartupTests(unittest.TestCase):
    def test_startup_restores_without_starting_historical_rebuild_worker(self):
        database_url = "postgresql://unused"
        restored_at = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
        metrics = object()
        builder = object()
        store = object()
        lifecycle = []
        constructed = {}

        def builder_factory(actual_url):
            constructed["builder_url"] = actual_url
            return builder

        def store_factory(actual_url):
            constructed["store_url"] = actual_url
            return store

        class Provider:
            def restore(self, cutoff_at):
                lifecycle.append(("restore", cutoff_at))

            def start(self):
                lifecycle.append(("start", None))

        provider = Provider()

        def provider_factory(actual_builder, *, store, metrics, utc_clock):
            constructed["provider_args"] = (
                actual_builder, store, metrics, utc_clock,
            )
            return provider

        def utc_clock():
            lifecycle.append(("clock", None))
            return restored_at

        result = web._start_v2(
            database_url,
            metrics,
            builder_factory=builder_factory,
            store_factory=store_factory,
            provider_factory=provider_factory,
            utc_clock=utc_clock,
        )

        self.assertIs(result, provider)
        self.assertEqual(constructed, {
            "builder_url": database_url,
            "store_url": database_url,
            "provider_args": (builder, store, metrics, utc_clock),
        })
        self.assertEqual(lifecycle, [
            ("clock", None),
            ("restore", restored_at),
        ])


if __name__ == "__main__":
    unittest.main()

