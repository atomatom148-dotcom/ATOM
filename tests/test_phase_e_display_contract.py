import unittest

from quant.evidence import PhaseECohortMetrics
from quant.v9_production import FORMULA_VERSION_MAP
from quant.web import dashboard_data, dashboard_page


class PhaseEDisplayContractTests(unittest.TestCase):
    def test_bounded_sample_and_directional_columns_are_labeled_truthfully(self):
        cohort = PhaseECohortMetrics(
            "q3_volatility",
            FORMULA_VERSION_MAP["q3_volatility"],
            "COIN",
            "30S",
            256,
            256,
            128,
            0.5,
            10.0,
            None,
            8.0,
            1.0,
            64,
            True,
        )

        page = dashboard_page(
            dashboard_data(phase_e_cohorts=(cohort,))
        ).decode()

        self.assertIn("PROOF N≤64", page)
        self.assertIn("N≥20", page)
        self.assertIn("DIR ACC", page)


if __name__ == "__main__":
    unittest.main()
