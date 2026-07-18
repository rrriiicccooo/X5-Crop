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
    DatasetRole,
    DecisionExpectation,
    SampleScenario,
    load_sample_expectations,
    sample_expectation_from_record,
    validate_sample_dataset,
)
from x5crop.domain import PixelInterval


def _record(
    *,
    source: str = "Test/135/full/pass_X5_00001.tif",
    decision_expectation: str = "pass_required",
    geometry_reference: str | None = "Test/135/full/pass_X5_00001.tif",
    review_basis: list[str] | None = None,
    dataset_role: str = "calibration",
    expected_count: int | None = 6,
) -> dict:
    return {
        "schema_id": "sample_expectation",
        "schema_revision": "frame_slot_sequence_resolution",
        "source": source,
        "format_id": "135",
        "strip_mode": "full",
        "requested_count": None,
        "decision_expectation": decision_expectation,
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
    def test_current_record_has_typed_expectation_scenario_and_role(self) -> None:
        expectation = sample_expectation_from_record(_record())

        self.assertEqual(
            expectation.decision_expectation,
            DecisionExpectation.PASS_REQUIRED,
        )
        self.assertEqual(expectation.scenario, SampleScenario.STANDARD)
        self.assertEqual(expectation.dataset_role, DatasetRole.CALIBRATION)
        self.assertEqual(expectation.expected_count, 6)

    def test_filename_prefix_is_the_decision_oracle(self) -> None:
        cases = (
            (_record(), True),
            (
                _record(
                    source="Test/135/full/review_X5_00001.tif",
                    decision_expectation="review_required",
                    geometry_reference=None,
                    review_basis=["human_boundary_ambiguous"],
                    dataset_role="validation",
                ),
                True,
            ),
            (
                _record(
                    source="Test/135/full/unknown_X5_00001.tif",
                    decision_expectation="pass_preferred",
                    geometry_reference="Test/135/full/unknown_X5_00001.tif",
                    dataset_role="validation",
                ),
                True,
            ),
            (
                _record(
                    source="Test/135/full/unkown_X5_00001.tif",
                    decision_expectation="pass_preferred",
                    geometry_reference="Test/135/full/unkown_X5_00001.tif",
                    dataset_role="validation",
                ),
                False,
            ),
            (
                _record(decision_expectation="review_required"),
                False,
            ),
        )
        for record, accepted in cases:
            with self.subTest(source=record["source"]):
                if accepted:
                    sample_expectation_from_record(record)
                else:
                    with self.assertRaises(ValueError):
                        sample_expectation_from_record(record)

    def test_pass_and_unknown_require_manual_geometry_reference(self) -> None:
        for source, expectation in (
            ("Test/135/full/pass_X5_00001.tif", "pass_required"),
            ("Test/135/full/unknown_X5_00001.tif", "pass_preferred"),
        ):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    sample_expectation_from_record(
                        _record(
                            source=source,
                            decision_expectation=expectation,
                            geometry_reference=None,
                            dataset_role=(
                                "validation"
                                if expectation == "pass_preferred"
                                else "calibration"
                            ),
                        )
                    )

    def test_review_requires_a_physical_review_basis(self) -> None:
        with self.assertRaises(ValueError):
            sample_expectation_from_record(
                _record(
                    source="Test/135/full/review_X5_00001.tif",
                    decision_expectation="review_required",
                    geometry_reference=None,
                    dataset_role="validation",
                )
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


if __name__ == "__main__":
    unittest.main()
