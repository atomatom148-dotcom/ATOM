"""Phase D3 proofs for deterministic evidence-usability combination."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.blocking as blocking
from quant.blocking import BlockingEvidence, assess_blocking
from quant.staleness import StalenessEvidence
from quant.structure import StructureEvidence
from quant.vol_friction import VolFrictionEvidence


def stale(
    usable: bool = True,
    reasons: tuple[str, ...] = (),
) -> StalenessEvidence:
    return StalenessEvidence(usable, 0.0, reasons)


def friction(
    usable: bool = True,
    reasons: tuple[str, ...] = (),
) -> VolFrictionEvidence:
    return VolFrictionEvidence(usable, 0.01, 0.001, 0.009, reasons)


def structure(
    usable: bool = True,
    reasons: tuple[str, ...] = (),
) -> StructureEvidence:
    return StructureEvidence(usable, 0.0, 150.0, 0.0, 0.5, reasons)


class PhaseD3BlockingTests(unittest.TestCase):
    def assess(
        self,
        *,
        staleness: StalenessEvidence | None = None,
        vol_friction: VolFrictionEvidence | None = None,
        structure_evidence: StructureEvidence | None = None,
    ) -> BlockingEvidence:
        return assess_blocking(
            staleness=staleness or stale(),
            vol_friction=vol_friction or friction(),
            structure=structure_evidence or structure(),
        )

    def test_all_three_usable_is_not_blocked_without_reasons(self) -> None:
        self.assertEqual(
            self.assess(),
            BlockingEvidence(False, ()),
        )

    def test_staleness_independently_blocks(self) -> None:
        self.assertEqual(
            self.assess(staleness=stale(False, ("SNAPSHOT_TOO_OLD",))),
            BlockingEvidence(True, ("STALENESS:SNAPSHOT_TOO_OLD",)),
        )

    def test_vol_friction_independently_blocks(self) -> None:
        self.assertEqual(
            self.assess(
                vol_friction=friction(False, ("MISSING_BID",))
            ),
            BlockingEvidence(True, ("VOL_FRICTION:MISSING_BID",)),
        )

    def test_structure_independently_blocks(self) -> None:
        self.assertEqual(
            self.assess(
                structure_evidence=structure(False, ("ASK_BELOW_BID",))
            ),
            BlockingEvidence(True, ("STRUCTURE:ASK_BELOW_BID",)),
        )

    def test_multiple_blocks_use_frozen_source_and_internal_order(self) -> None:
        self.assertEqual(
            self.assess(
                staleness=stale(False, ("STALE_FIRST", "STALE_SECOND")),
                vol_friction=friction(False, ("VOL_FIRST", "VOL_SECOND")),
                structure_evidence=structure(
                    False, ("STRUCTURE_FIRST", "STRUCTURE_SECOND")
                ),
            ),
            BlockingEvidence(
                True,
                (
                    "STALENESS:STALE_FIRST",
                    "STALENESS:STALE_SECOND",
                    "VOL_FRICTION:VOL_FIRST",
                    "VOL_FRICTION:VOL_SECOND",
                    "STRUCTURE:STRUCTURE_FIRST",
                    "STRUCTURE:STRUCTURE_SECOND",
                ),
            ),
        )

    def test_usable_source_reasons_are_ignored(self) -> None:
        self.assertEqual(
            self.assess(
                staleness=stale(True, ("STALE_WARNING",)),
                vol_friction=friction(True, ("RANGE_UNAVAILABLE",)),
                structure_evidence=structure(True, ("ZERO_QUOTE_WIDTH",)),
            ),
            BlockingEvidence(False, ()),
        )

    def test_each_unusable_source_without_reasons_still_blocks(self) -> None:
        cases = (
            ({"staleness": stale(False)}, "STALENESS"),
            ({"vol_friction": friction(False)}, "VOL_FRICTION"),
            ({"structure_evidence": structure(False)}, "STRUCTURE"),
        )
        for supplied, prefix in cases:
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    self.assess(**supplied),
                    BlockingEvidence(
                        True, (f"{prefix}:UNUSABLE_WITHOUT_REASON",)
                    ),
                )

    def test_supplied_evidence_is_not_mutated(self) -> None:
        supplied = (
            stale(False, ("SNAPSHOT_TOO_OLD",)),
            friction(False, ("MISSING_BID",)),
            structure(True, ("ZERO_QUOTE_WIDTH",)),
        )
        before = deepcopy(supplied)

        assess_blocking(
            staleness=supplied[0],
            vol_friction=supplied[1],
            structure=supplied[2],
        )

        self.assertEqual(supplied, before)

    def test_public_contract_is_exactly_d3(self) -> None:
        self.assertEqual(
            tuple(BlockingEvidence.__dataclass_fields__),
            ("blocked", "reason_codes"),
        )
        self.assertEqual(
            blocking.__all__,
            ["BlockingEvidence", "assess_blocking"],
        )


if __name__ == "__main__":
    unittest.main()
