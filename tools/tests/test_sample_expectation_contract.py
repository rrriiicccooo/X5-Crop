from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.regression.frame_slot_reference import (
    FrameSlotIntervalReference,
    FrameSlotReference,
    SharedShortAxisReference,
)
from tools.regression.sample_expectations import (
    DatasetIntent,
    DatasetRole,
    DecisionExpectation,
    ObservationProofExpectation,
    SampleScenario,
    load_sample_expectations,
    sample_expectation_from_record,
    validate_sample_dataset,
)
from x5crop.domain import PixelInterval


def _record(
    *,
    source: str = "Test/135/full/pass_X5_00001.tif",
    dataset_intent: str = "pass",
    automatic_decision_expectation: str = "pass_required",
    observation_proof_expectation: str = "independent_proof_expected",
    geometry_reference: str | None = "Test/135/full/pass_X5_00001.tif",
    review_basis: list[str] | None = None,
    dataset_role: str = "calibration",
    expected_count: int | None = 6,
) -> dict:
    return {
        "schema_id": "sample_expectation",
        "schema_revision": "independent_geometry_proof_decision",
        "source": source,
        "dataset_intent": dataset_intent,
        "format_id": "135",
        "strip_mode": "full",
        "requested_count": None,
        "automatic_decision_expectation": automatic_decision_expectation,
        "observation_proof_expectation": observation_proof_expectation,
        "scenario": "standard",
        "dataset_role": dataset_role,
        "expected_count": expected_count,
        "geometry_reference": geometry_reference,
        "review_basis": [] if review_basis is None else review_basis,
    }


def _reference(source: str) -> FrameSlotReference:
    return FrameSlotReference(
        source=source,
        format_id="135",
        strip_mode="full",
        layout="horizontal",
        shared_short_axis=SharedShortAxisReference(
            top=PixelInterval(10.0, 12.0),
            bottom=PixelInterval(88.0, 90.0),
        ),
        frame_slots=(
            FrameSlotIntervalReference(
                index=1,
                leading=PixelInterval(20.0, 22.0),
                trailing=PixelInterval(118.0, 120.0),
            ),
        ),
        notes=(),
    )


class SampleExpectationContractTest(unittest.TestCase):
    def test_current_record_has_three_independent_authorities(self) -> None:
        expectation = sample_expectation_from_record(_record())

        self.assertEqual(
            expectation.automatic_decision_expectation,
            DecisionExpectation.PASS_REQUIRED,
        )
        self.assertEqual(expectation.dataset_intent, DatasetIntent.PASS)
        self.assertEqual(
            expectation.observation_proof_expectation,
            ObservationProofExpectation.INDEPENDENT_PROOF_EXPECTED,
        )
        self.assertEqual(
            expectation.geometry_reference,
            "Test/135/full/pass_X5_00001.tif",
        )
        self.assertEqual(expectation.scenario, SampleScenario.STANDARD)
        self.assertEqual(expectation.dataset_role, DatasetRole.CALIBRATION)
        self.assertEqual(expectation.expected_count, 6)

    def test_filename_prefix_only_owns_dataset_intent(self) -> None:
        cases = (
            (_record(), True),
            (
                _record(
                    source="Test/135/full/review_X5_00001.tif",
                    dataset_intent="review",
                    automatic_decision_expectation="review_required",
                    observation_proof_expectation="independent_proof_unavailable",
                    geometry_reference=None,
                    review_basis=["human_boundary_ambiguous"],
                    dataset_role="validation",
                ),
                True,
            ),
            (
                _record(
                    source="Test/135/full/unknown_X5_00001.tif",
                    dataset_intent="unknown",
                    automatic_decision_expectation="pass_preferred",
                    geometry_reference="Test/135/full/unknown_X5_00001.tif",
                    dataset_role="validation",
                ),
                True,
            ),
            (
                _record(
                    source="Test/135/full/unkown_X5_00001.tif",
                    dataset_intent="unknown",
                    automatic_decision_expectation="pass_preferred",
                    geometry_reference="Test/135/full/unkown_X5_00001.tif",
                    dataset_role="validation",
                ),
                False,
            ),
            (
                _record(dataset_intent="review"),
                False,
            ),
            (
                _record(
                    automatic_decision_expectation="review_required",
                    observation_proof_expectation="independent_proof_unavailable",
                    geometry_reference=None,
                    review_basis=["allowed_gray_observations_insufficient"],
                    dataset_role="validation",
                ),
                True,
            ),
        )
        for record, accepted in cases:
            with self.subTest(source=record["source"]):
                if accepted:
                    sample_expectation_from_record(record)
                else:
                    with self.assertRaises(ValueError):
                        sample_expectation_from_record(record)

    def test_pass_targets_require_manual_geometry_reference(self) -> None:
        with self.assertRaises(ValueError):
            sample_expectation_from_record(
                _record(
                    source="Test/135/full/pass_X5_00001.tif",
                    automatic_decision_expectation="pass_required",
                    geometry_reference=None,
                    dataset_role="calibration",
                )
            )

    def test_unreferenced_unknown_can_prefer_pass_without_requiring_review(
        self,
    ) -> None:
        expectation = sample_expectation_from_record(
            _record(
                source="Test/135/partial/unknown_X5_00009.tif",
                dataset_intent="unknown",
                automatic_decision_expectation="pass_preferred",
                geometry_reference=None,
                dataset_role="validation",
            )
        )

        self.assertIsNone(expectation.geometry_reference)

    def test_review_requires_a_physical_review_basis(self) -> None:
        with self.assertRaises(ValueError):
            sample_expectation_from_record(
                _record(
                    source="Test/135/full/review_X5_00001.tif",
                    dataset_intent="review",
                    automatic_decision_expectation="review_required",
                    observation_proof_expectation="independent_proof_unavailable",
                    geometry_reference=None,
                    dataset_role="validation",
                )
            )

    def test_proof_unavailable_can_remain_a_pass_capability_target(self) -> None:
        expectation = sample_expectation_from_record(
            _record(
                automatic_decision_expectation="pass_required",
                observation_proof_expectation="independent_proof_unavailable",
            )
        )

        self.assertEqual(
            expectation.automatic_decision_expectation,
            DecisionExpectation.PASS_REQUIRED,
        )
        self.assertEqual(
            expectation.observation_proof_expectation,
            ObservationProofExpectation.INDEPENDENT_PROOF_UNAVAILABLE,
        )

    def test_loader_rejects_duplicate_sources(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample_expectations.jsonl"
            line = json.dumps(_record(), sort_keys=True)
            path.write_text(f"{line}\n{line}\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_sample_expectations(path)

    def test_dataset_requires_one_expectation_and_reference_per_sample(self) -> None:
        expectation = sample_expectation_from_record(_record(expected_count=1))
        source = Path(expectation.source)
        reference = _reference(expectation.source)

        validate_sample_dataset((expectation,), (reference,), (source,))
        with self.assertRaises(ValueError):
            validate_sample_dataset((expectation,), (), (source,))
        with self.assertRaises(ValueError):
            validate_sample_dataset((expectation,), (reference,), (source, Path("extra.tif")))

    def test_dataset_identity_resolves_relative_records_against_workspace(self) -> None:
        workspace_root = Path("/project")
        expectation = sample_expectation_from_record(_record(expected_count=1))
        reference = _reference(expectation.source)

        validate_sample_dataset(
            (expectation,),
            (reference,),
            (workspace_root / expectation.source,),
            workspace_root=workspace_root,
        )


if __name__ == "__main__":
    unittest.main()
