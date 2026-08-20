import unittest

from quant.ledger import Ledger
from quant.models import ExactSixBundle, HORIZONS, HorizonForecast, SetupState


class MultiQuantEvidenceContractTests(unittest.TestCase):
    def test_evidence_survives_construction_serialization_and_commit(self) -> None:
        cutoff = 1_700_000_000.0
        forecast_values = [1.0, -2.0, 3.5, None, 0.0, 8.25]
        rows = [
            HorizonForecast(
                horizon=horizon,
                setup_state=SetupState.NO_SETUP,
                cutoff_epoch=cutoff,
                maturity_epoch=cutoff + seconds,
                forecast_bps=forecast_bps,
            )
            for horizon, seconds, forecast_bps in zip(
                HORIZONS, (30, 60, 300, 900, 1800, 3600), forecast_values
            )
        ]
        bundle = ExactSixBundle(
            cycle_id="cycle-evidence",
            symbol="SPY",
            cutoff_epoch=cutoff,
            snapshot_hash="snapshot-hash",
            policy_version="policy-v1",
            rows=rows,
            quant_id="quant-alpha",
            formula_version="midpoint-log-return-bps-v1",
        )

        self.assertEqual(bundle.quant_id, "quant-alpha")
        self.assertEqual(bundle.formula_version, "midpoint-log-return-bps-v1")
        self.assertEqual(bundle.cycle_id, "cycle-evidence")
        self.assertEqual(bundle.policy_version, "policy-v1")
        self.assertEqual([row.forecast_bps for row in bundle.rows], forecast_values)
        self.assertEqual(tuple(row.horizon for row in bundle.rows), HORIZONS)

        serialized = bundle.to_dict()
        self.assertEqual(serialized["quant_id"], "quant-alpha")
        self.assertEqual(
            serialized["formula_version"], "midpoint-log-return-bps-v1"
        )
        self.assertEqual(
            [row["forecast_bps"] for row in serialized["rows"]], forecast_values
        )

        committed = Ledger().commit(bundle, committed_at_epoch=cutoff + 1)
        self.assertEqual(committed.bundle.quant_id, "quant-alpha")
        self.assertEqual(
            committed.bundle.formula_version, "midpoint-log-return-bps-v1"
        )
        self.assertEqual(
            [row.forecast_bps for row in committed.bundle.rows], forecast_values
        )
        self.assertEqual(
            tuple(row.horizon for row in committed.bundle.rows), HORIZONS
        )


if __name__ == "__main__":
    unittest.main()
