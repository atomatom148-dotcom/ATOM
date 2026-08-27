from dataclasses import replace
import json
import math
import unittest

from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS,
    HORIZON_SECONDS,
    FamilyLineage,
    RawFamilyObservation,
    RawTarget,
    TargetIdentity,
    build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b
from quant.v9_v2c_covariance import build_v2c_covariance
from quant.v9_v2d_evidence_state import (
    ComponentHash,
    DirectionalCalibrationState,
    HorizonEvidenceState,
    Q3MagnitudeState,
    V2EvidenceState,
    _canonical,
    _digest,
    build_v2d_evidence_state,
    deserialize_v2_evidence_state,
    serialize_v2_evidence_state,
    v2d_state_hash,
)


def _component(horizon: str = "30S"):
    seconds = HORIZON_SECONDS[horizon]
    targets = []
    observations = []
    for index, (x, y) in enumerate(zip((0.0, 1.0, 3.0, 6.0),
                                       (2.0, 5.0, 9.0, 14.0))):
        cutoff = float(index * seconds)
        identity = TargetIdentity(f"{horizon}-{index}", cutoff, cutoff + seconds)
        targets.append(RawTarget(
            index, identity.cycle_id, "COIN", "target", "ts1", "target-src1",
            horizon, cutoff, cutoff + seconds, cutoff + seconds, y,
        ))
        observations.append(RawFamilyObservation(
            index, identity, "COIN", "q1_momentum", "q1-f1", "qs1", "q-src1",
            horizon, DIRECTIONAL_BPS, x, cutoff, cutoff, cutoff, "FRESH",
        ))
    dataset = build_v2a_dataset(
        state_as_of=10_000.0,
        horizon=horizon,
        target_spec_id="target",
        target_data_schema_version="ts1",
        target_source_spec_version="target-src1",
        family_versions=(
            ("q1_momentum", "q1-f1", "qs1", "q-src1"),
            ("q3_volatility", "q3-f1", "qs1", "q-src1"),
        ),
        targets=targets,
        observations=observations,
    )
    calibration = calibrate_v2b((dataset,))
    calibration = replace(
        calibration,
        directional=(replace(calibration.directional[0], status="MATURE"),),
    )
    covariance = build_v2c_covariance(dataset, calibration)
    return dataset, calibration, covariance


def _state() -> V2EvidenceState:
    dataset, calibration, covariance = _component()
    return build_v2d_evidence_state(
        state_as_of=10_000.0,
        datasets=(dataset,),
        calibrations=(calibration,),
        covariances=(covariance,),
    )


def _reidentify(state: V2EvidenceState) -> V2EvidenceState:
    shell = replace(state, state_hash="", state_id="")
    digest = v2d_state_hash(shell)
    return replace(shell, state_hash=digest, state_id="v9v2:" + digest)


def _wire(state: V2EvidenceState) -> str:
    return json.dumps(_canonical(state), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


class V2EvidenceStateCodecTests(unittest.TestCase):
    def test_round_trip_rehydrates_every_nested_type_and_tuple(self):
        state = _state()
        encoded = serialize_v2_evidence_state(state)

        self.assertEqual(deserialize_v2_evidence_state(encoded), state)
        self.assertEqual(deserialize_v2_evidence_state(json.loads(encoded)), state)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True,
                                             separators=(",", ":"),
                                             ensure_ascii=True))

        decoded = deserialize_v2_evidence_state(encoded)
        slot = decoded.horizon_state_tuple[0]
        self.assertIsInstance(decoded, V2EvidenceState)
        self.assertIsInstance(decoded.component_hash_tuple[0], ComponentHash)
        self.assertIsInstance(slot, HorizonEvidenceState)
        self.assertIsInstance(slot.directional_calibrations[0],
                              DirectionalCalibrationState)
        self.assertIsInstance(slot.family_lineage[0], FamilyLineage)
        self.assertIsInstance(slot.q3, Q3MagnitudeState)
        self.assertIs(type(slot.q3.calibration_alpha), int)
        self.assertEqual(slot.q3.calibration_alpha, 0)
        self.assertIsInstance(slot.pair_support_boolean_matrix, tuple)
        self.assertIsInstance(slot.pair_support_boolean_matrix[0], tuple)
        self.assertIs(type(slot.pair_support_boolean_matrix[0][0]), bool)
        self.assertIsInstance(slot.stabilized_covariance_matrix, tuple)

    def test_missing_unknown_nested_and_identity_tampering_fail_closed(self):
        encoded = serialize_v2_evidence_state(_state())
        mutations = []

        missing = json.loads(encoded)
        missing.pop("symbol")
        mutations.append(missing)

        unknown = json.loads(encoded)
        unknown["unknown"] = None
        mutations.append(unknown)

        nested_missing = json.loads(encoded)
        nested_missing["horizon_state_tuple"][0]["q3"].pop("status")
        mutations.append(nested_missing)

        nested_unknown = json.loads(encoded)
        nested_unknown["horizon_state_tuple"][0]["family_lineage"][0]["unknown"] = 1
        mutations.append(nested_unknown)

        bad_hash = json.loads(encoded)
        bad_hash["state_hash"] = "f" * 64
        mutations.append(bad_hash)

        bad_id = json.loads(encoded)
        bad_id["state_id"] = "v9v2:" + "f" * 64
        mutations.append(bad_id)

        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                deserialize_v2_evidence_state(payload)

    def test_only_exact_canonical_json_values_are_accepted(self):
        encoded = serialize_v2_evidence_state(_state())
        mutations = []

        raw_float = json.loads(encoded)
        raw_float["state_as_of"] = 10_000.0
        mutations.append(raw_float)

        short_float_token = json.loads(encoded)
        short_float_token["state_as_of"] = {"$float64": "0x1.388p+13"}
        mutations.append(short_float_token)

        nonfinite = json.loads(encoded)
        nonfinite["state_as_of"] = {"$float64": "nan"}
        mutations.append(nonfinite)

        malformed_wrapper = json.loads(encoded)
        malformed_wrapper["state_as_of"] = {
            "$float64": float(10_000.0).hex(), "extra": None,
        }
        mutations.append(malformed_wrapper)

        bool_as_int = json.loads(encoded)
        bool_as_int["horizon_state_tuple"][0]["horizon_seconds"] = True
        mutations.append(bool_as_int)

        int_as_bool = json.loads(encoded)
        int_as_bool["horizon_state_tuple"][0]["pair_support_boolean_matrix"][0][0] = 1
        mutations.append(int_as_bool)

        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                deserialize_v2_evidence_state(payload)

        duplicate = encoded.replace(
            '"state_schema_version":',
            '"state_schema_version":"duplicate","state_schema_version":',
            1,
        )
        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(duplicate)

    def test_rehashed_semantic_forgeries_are_rejected(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        for forged in (
            replace(state, state_schema_version="forged"),
            replace(state, horizon_state_tuple=(
                replace(first, horizon_seconds=31),
                *state.horizon_state_tuple[1:],
            )),
            replace(state, horizon_state_tuple=(
                replace(first, range_score_count=1),
                *state.horizon_state_tuple[1:],
            )),
            replace(state, top_level_status="MATURE"),
            replace(state, evidence_manifest_hash="f" * 64),
        ):
            forged = _reidentify(forged)
            with self.subTest(forged=forged), self.assertRaises(ValueError):
                deserialize_v2_evidence_state(_wire(forged))
            with self.assertRaises(ValueError):
                serialize_v2_evidence_state(forged)

    def test_rehashed_duplicate_horizon_layer_component_is_rejected(self):
        state = _state()
        components = tuple(sorted((
            *state.component_hash_tuple,
            ComponentHash("30S", "V2B", "f" * 64),
        )))
        forged = replace(
            state,
            component_hash_tuple=components,
            evidence_manifest_hash=_digest(tuple(
                (item.horizon, item.layer, item.digest) for item in components
            )),
        )
        forged = _reidentify(forged)

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_legacy_q3_integer_defaults_are_only_valid_for_no_evidence(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        q3 = replace(
            first.q3,
            status="PROVISIONAL",
            reason_codes=("HYPERPRIOR_UNIDENTIFIABLE",),
            calibration_alpha=0,
            calibration_beta=1,
            effective_n=0,
            magnitude_residual_variance=0,
            magnitude_mae=0,
            magnitude_rmse=0,
        )
        horizon = replace(
            first,
            q3=q3,
            reason_codes=tuple(
                reason for reason in first.reason_codes if reason != "NO_EVIDENCE"
            ),
        )
        forged = _reidentify(replace(
            state,
            horizon_state_tuple=(horizon, *state.horizon_state_tuple[1:]),
            reason_code_tuple=tuple(
                reason for reason in state.reason_code_tuple
                if reason != "NO_EVIDENCE"
            ),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_no_evidence_q3_rejects_float_wrapper_identity_alias(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        forged = _reidentify(replace(
            state,
            horizon_state_tuple=(
                replace(
                    first,
                    q3=replace(
                        first.q3,
                        calibration_alpha=0.0,
                        calibration_beta=1.0,
                        effective_n=0.0,
                        magnitude_residual_variance=0.0,
                        magnitude_mae=0.0,
                        magnitude_rmse=0.0,
                    ),
                ),
                *state.horizon_state_tuple[1:],
            ),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_rehashed_noncanonical_absent_q3_is_rejected(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        q3 = Q3MagnitudeState("MATURE", ("FORGED",))
        reasons = tuple(sorted({
            *(reason for item in first.directional_calibrations
              for reason in item.reason_codes),
            *first.covariance_reason_codes,
            *q3.reason_codes,
        }))
        forged = _reidentify(replace(
            state,
            horizon_state_tuple=(
                replace(
                    first,
                    status="MATURE",
                    reason_codes=reasons,
                    family_lineage=tuple(
                        item for item in first.family_lineage
                        if item.quant_id != "q3_volatility"
                    ),
                    q3=q3,
                ),
                *state.horizon_state_tuple[1:],
            ),
            reason_code_tuple=tuple(sorted({
                *(reason for item in state.horizon_state_tuple[1:]
                  for reason in item.reason_codes),
                *reasons,
            })),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_rehashed_covariance_support_forgery_is_rejected(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        forged = _reidentify(replace(
            state,
            horizon_state_tuple=(
                replace(
                    first,
                    covariance_status="MATURE",
                    pair_support_boolean_matrix=((False,),),
                ),
                *state.horizon_state_tuple[1:],
            ),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_rehashed_calibration_covariance_forgeries_are_rejected(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        for horizon in (
            replace(
                first,
                q3=replace(
                    first.q3,
                    parameter_covariance_2x2=((1.0, 2.0), (3.0, 4.0)),
                ),
            ),
            replace(
                first,
                q3=replace(
                    first.q3,
                    parameter_covariance_2x2=((1.0, 0.0), (0.0, 1.0)),
                ),
            ),
            replace(
                first,
                directional_calibrations=(replace(
                    first.directional_calibrations[0],
                    calibration_parameter_covariance_2x2=(
                        (1.0, 2.0), (3.0, 4.0),
                    ),
                ),),
            ),
        ):
            forged = _reidentify(replace(
                state,
                horizon_state_tuple=(horizon, *state.horizon_state_tuple[1:]),
            ))
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                deserialize_v2_evidence_state(_wire(forged))
            with self.assertRaises(ValueError):
                serialize_v2_evidence_state(forged)

    def test_directional_no_evidence_sentinel_rejects_arbitrary_scalars(self):
        state = _state()
        first = state.horizon_state_tuple[0]
        no_evidence = replace(
            first.directional_calibrations[0],
            calibration_intercept=0.0,
            calibration_slope=1.0,
            calibration_parameter_covariance_2x2=((0.0, 0.0), (0.0, 0.0)),
            effective_n=0.0,
            residual_variance=0.0,
            residual_standard_deviation=0.0,
            status="UNAVAILABLE",
            reason_codes=("NO_EVIDENCE",),
        )
        horizon = replace(
            first,
            status="UNAVAILABLE",
            reason_codes=("NO_EVIDENCE",),
            directional_calibrations=(no_evidence,),
        )
        sentinel = _reidentify(replace(
            state,
            horizon_state_tuple=(horizon, *state.horizon_state_tuple[1:]),
            top_level_status="UNAVAILABLE",
            reason_code_tuple=tuple(sorted({
                *(reason for item in state.horizon_state_tuple[1:]
                  for reason in item.reason_codes),
                "NO_EVIDENCE",
            })),
        ))
        serialize_v2_evidence_state(sentinel)

        forged_horizon = replace(
            horizon,
            directional_calibrations=(replace(
                no_evidence,
                calibration_intercept=999.0,
            ),),
        )
        forged = _reidentify(replace(
            sentinel,
            horizon_state_tuple=(
                forged_horizon,
                *sentinel.horizon_state_tuple[1:],
            ),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_component_free_horizon_reason_is_whitelisted(self):
        state = _state()
        unavailable = state.horizon_state_tuple[1]
        horizon = replace(unavailable, reason_codes=("FORGED_REASON",))
        forged = _reidentify(replace(
            state,
            horizon_state_tuple=(
                state.horizon_state_tuple[0],
                horizon,
                *state.horizon_state_tuple[2:],
            ),
            reason_code_tuple=tuple(sorted({
                *(reason for item in state.horizon_state_tuple
                  for reason in item.reason_codes),
                "FORGED_REASON",
            })),
        ))

        with self.assertRaises(ValueError):
            deserialize_v2_evidence_state(_wire(forged))
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(forged)

    def test_serializer_rejects_wrong_type_and_stale_identity(self):
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(object())  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            serialize_v2_evidence_state(replace(_state(), top_level_status="MATURE"))

    def test_signed_zero_has_one_wire_representation(self):
        positive = build_v2d_evidence_state(
            state_as_of=0.0, datasets=(), calibrations=(), covariances=())
        negative = build_v2d_evidence_state(
            state_as_of=-0.0, datasets=(), calibrations=(), covariances=())

        self.assertEqual(positive.state_hash, negative.state_hash)
        self.assertEqual(serialize_v2_evidence_state(positive),
                         serialize_v2_evidence_state(negative))
        decoded = deserialize_v2_evidence_state(
            serialize_v2_evidence_state(negative))
        self.assertEqual(decoded.state_as_of, 0.0)
        self.assertEqual(math.copysign(1.0, decoded.state_as_of), 1.0)

    def test_non_object_and_malformed_json_are_rejected(self):
        for payload in ("not json", "[]", "null", '{"x":NaN}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                deserialize_v2_evidence_state(payload)


if __name__ == "__main__":
    unittest.main()
