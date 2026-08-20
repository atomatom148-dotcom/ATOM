"""Phase D5 proofs for deterministic operational consistency certification."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.certification as certification
from quant.blocking import BlockingEvidence
from quant.certification import OperationalCertification, certify_operations
from quant.hydration import HydratedState
from quant.ledger import Ledger
from quant.recovery import RecoveryStatus
from quant.resolver import Resolver
from quant.staleness import StalenessEvidence


def recovery(
    ledger_records: int = 0,
    resolved_outcomes: int = 0,
    *,
    recoverable: bool = True,
) -> RecoveryStatus:
    return RecoveryStatus(
        ledger_records,
        resolved_outcomes,
        recoverable,
        (),
    )


def hydrated(
    ledger_records: int = 0,
    resolved_outcomes: int = 0,
    *,
    ledger: Ledger | None = None,
    resolver: Resolver | None = None,
) -> HydratedState:
    return HydratedState(
        ledger or Ledger(),
        resolver or Resolver(),
        ledger_records,
        resolved_outcomes,
    )


def certify(
    *,
    recovery_evidence: RecoveryStatus | None = None,
    staleness: StalenessEvidence | None = None,
    blocking: BlockingEvidence | None = None,
    hydration: HydratedState | None = None,
) -> OperationalCertification:
    return certify_operations(
        recovery=recovery_evidence or recovery(),
        staleness=staleness or StalenessEvidence(True, 0.0, ()),
        blocking=blocking or BlockingEvidence(False, ()),
        hydrated=hydration or hydrated(),
    )


class PhaseD5CertificationTests(unittest.TestCase):
    def test_clean_empty_startup_certifies(self) -> None:
        self.assertEqual(
            certify(),
            OperationalCertification(True, 0, 0, ()),
        )

    def test_hydrated_evidence_matching_recovery_counts_certifies(self) -> None:
        ledger = Ledger()
        resolver = Resolver()
        state = hydrated(
            ledger.count(), resolver.count(), ledger=ledger, resolver=resolver
        )

        self.assertEqual(
            certify(
                recovery_evidence=recovery(0, 0, recoverable=False),
                hydration=state,
            ),
            OperationalCertification(True, 0, 0, ()),
        )

    def test_stale_evidence_fails_with_reasons_or_fallback(self) -> None:
        cases = (
            (
                StalenessEvidence(False, 31.0, ("SNAPSHOT_TOO_OLD",)),
                ("STALENESS:SNAPSHOT_TOO_OLD",),
            ),
            (
                StalenessEvidence(False, None, ()),
                ("STALENESS:UNUSABLE_WITHOUT_REASON",),
            ),
        )
        for evidence, reasons in cases:
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    certify(staleness=evidence),
                    OperationalCertification(False, 0, 0, reasons),
                )

    def test_blocked_evidence_fails_with_reasons_or_fallback(self) -> None:
        cases = (
            (
                BlockingEvidence(True, ("STRUCTURE:MISSING_BID",)),
                ("BLOCKING:STRUCTURE:MISSING_BID",),
            ),
            (
                BlockingEvidence(True, ()),
                ("BLOCKING:BLOCKED_WITHOUT_REASON",),
            ),
        )
        for evidence, reasons in cases:
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    certify(blocking=evidence),
                    OperationalCertification(False, 0, 0, reasons),
                )

    def test_ledger_count_mismatch_fails(self) -> None:
        self.assertEqual(
            certify(hydration=hydrated(1, 0)),
            OperationalCertification(
                False, 1, 0, ("HYDRATION:LEDGER_COUNT_MISMATCH",)
            ),
        )

    def test_resolver_count_mismatch_fails(self) -> None:
        self.assertEqual(
            certify(hydration=hydrated(0, 1)),
            OperationalCertification(
                False, 0, 1, ("HYDRATION:RESOLVER_COUNT_MISMATCH",)
            ),
        )

    def test_missing_restored_ledger_evidence_fails(self) -> None:
        self.assertEqual(
            certify(
                recovery_evidence=recovery(1, 0, recoverable=False),
            ),
            OperationalCertification(
                False,
                0,
                0,
                ("RECOVERY:LEDGER_EVIDENCE_NOT_RESTORED",),
            ),
        )

    def test_missing_restored_resolver_evidence_fails(self) -> None:
        self.assertEqual(
            certify(
                recovery_evidence=recovery(0, 1, recoverable=False),
            ),
            OperationalCertification(
                False,
                0,
                0,
                ("RECOVERY:RESOLVED_EVIDENCE_NOT_RESTORED",),
            ),
        )

    def test_multiple_failures_preserve_exact_required_order(self) -> None:
        result = certify(
            recovery_evidence=recovery(3, 4, recoverable=False),
            staleness=StalenessEvidence(False, 40.0, ("OLD", "LATE")),
            blocking=BlockingEvidence(True, ("FIRST", "SECOND")),
            hydration=hydrated(1, 2),
        )

        self.assertEqual(
            result,
            OperationalCertification(
                False,
                1,
                2,
                (
                    "STALENESS:OLD",
                    "STALENESS:LATE",
                    "BLOCKING:FIRST",
                    "BLOCKING:SECOND",
                    "HYDRATION:LEDGER_COUNT_MISMATCH",
                    "HYDRATION:RESOLVER_COUNT_MISMATCH",
                    "RECOVERY:LEDGER_EVIDENCE_NOT_RESTORED",
                    "RECOVERY:RESOLVED_EVIDENCE_NOT_RESTORED",
                ),
            ),
        )

    def test_usable_and_nonblocking_warnings_are_ignored(self) -> None:
        self.assertEqual(
            certify(
                staleness=StalenessEvidence(True, 1.0, ("WARNING",)),
                blocking=BlockingEvidence(False, ("WARNING",)),
            ),
            OperationalCertification(True, 0, 0, ()),
        )

    def test_result_counts_come_only_from_hydrated_count_fields(self) -> None:
        result = certify(
            recovery_evidence=recovery(91, 92, recoverable=True),
            hydration=hydrated(7, 8),
        )

        self.assertEqual((result.ledger_records, result.resolved_outcomes), (7, 8))

    def test_inputs_remain_unchanged(self) -> None:
        supplied = (
            recovery(2, 3, recoverable=False),
            StalenessEvidence(False, 5.0, ("STALE",)),
            BlockingEvidence(True, ("BLOCKED",)),
            hydrated(1, 1),
        )
        before = deepcopy(supplied[:3])
        ledger = supplied[3].ledger
        resolver = supplied[3].resolver
        counts_before = (ledger.count(), resolver.count())

        certify_operations(
            recovery=supplied[0],
            staleness=supplied[1],
            blocking=supplied[2],
            hydrated=supplied[3],
        )

        self.assertEqual(supplied[:3], before)
        self.assertIs(supplied[3].ledger, ledger)
        self.assertIs(supplied[3].resolver, resolver)
        self.assertEqual((ledger.count(), resolver.count()), counts_before)

    def test_public_contract_is_exactly_d5(self) -> None:
        self.assertEqual(
            tuple(OperationalCertification.__dataclass_fields__),
            ("certified", "ledger_records", "resolved_outcomes", "reason_codes"),
        )
        self.assertEqual(
            certification.__all__,
            ["OperationalCertification", "certify_operations"],
        )


if __name__ == "__main__":
    unittest.main()
