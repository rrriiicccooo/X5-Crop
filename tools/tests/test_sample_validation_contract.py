from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from tools.regression.frame_slot_reference import frame_slot_reference_from_record
from tools.regression.sample_expectations import sample_expectation_from_record
from tools.regression.sample_validation import (
    SampleContractOutcome,
    SampleContractReason,
    evaluate_sample_dataset,
    evaluate_sample_contract,
)
from tools.tests.test_frame_slot_reference_contract import (
    _reference_record,
    _unresolved_record,
)
from tools.tests.test_output_read_model_contract import _record


def _expectation_record(
    source: str,
    *,
    dataset_intent: str = "pass",
    automatic_decision_expectation: str = "pass_required",
    observation_proof_expectation: str = "independent_proof_expected",
    geometry_reference: str | None = None,
    review_basis: list[str] | None = None,
) -> dict:
    return {
        "schema_id": "sample_expectation",
        "schema_revision": "independent_geometry_proof_decision",
        "source": source,
        "dataset_intent": dataset_intent,
        "format_id": "135",
        "strip_mode": "partial",
        "requested_count": "auto",
        "automatic_decision_expectation": automatic_decision_expectation,
        "observation_proof_expectation": observation_proof_expectation,
        "scenario": "standard",
        "dataset_role": "validation",
        "expected_count": None,
        "geometry_reference": (
            source if geometry_reference is None and dataset_intent != "review"
            else geometry_reference
        ),
        "review_basis": [] if review_basis is None else review_basis,
    }


def _reference(source: str):
    return frame_slot_reference_from_record(_reference_record(_record(source)))


class SampleValidationContractTest(unittest.TestCase):
    def test_dataset_evaluation_joins_absolute_reports_to_relative_truth(self) -> None:
        workspace_root = Path("/project")
        relative_source = "Test/135/partial/pass_X5_99989.tif"
        expectation = sample_expectation_from_record(
            _expectation_record(relative_source)
        )
        absolute_source = str(workspace_root / relative_source)
        reference_record = _reference_record(_record(absolute_source))
        reference_record["source"] = relative_source

        results = evaluate_sample_dataset(
            (expectation,),
            (frame_slot_reference_from_record(reference_record),),
            (_record(absolute_source),),
            workspace_root=workspace_root,
        )

        self.assertEqual(
            results,
            (
                evaluate_sample_contract(
                    expectation,
                    frame_slot_reference_from_record(reference_record),
                    _record(absolute_source),
                    workspace_root=workspace_root,
                ),
            ),
        )

    def test_dataset_evaluation_reports_missing_and_rejects_extra_reports(self) -> None:
        source = "Test/135/partial/pass_X5_99988.tif"
        expectation = sample_expectation_from_record(_expectation_record(source))
        reference = _reference(source)

        results = evaluate_sample_dataset((expectation,), (reference,), ())

        self.assertEqual(
            results[0].reasons,
            (SampleContractReason.CURRENT_REPORT_MISSING,),
        )
        with self.assertRaises(ValueError):
            evaluate_sample_dataset(
                (expectation,),
                (reference,),
                (_record(source), _record("Test/135/partial/pass_X5_extra.tif")),
            )

    def test_resolved_matching_pass_target_conforms(self) -> None:
        source = "Test/135/partial/pass_X5_99991.tif"
        result = evaluate_sample_contract(
            sample_expectation_from_record(_expectation_record(source)),
            _reference(source),
            _record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.CONFORMING)
        self.assertEqual(result.reasons, ())

    def test_resolved_geometry_outside_manual_reference_is_a_violation(self) -> None:
        source = "Test/135/partial/pass_X5_99992.tif"
        reference_record = _reference_record(_record(source))
        reference_record["frame_slots"][0]["leading"] = {
            "minimum": 10.0,
            "maximum": 20.0,
        }

        result = evaluate_sample_contract(
            sample_expectation_from_record(_expectation_record(source)),
            frame_slot_reference_from_record(reference_record),
            _record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.VIOLATION)
        self.assertIn(
            SampleContractReason.RESOLVED_GEOMETRY_OUTSIDE_REFERENCE,
            result.reasons,
        )

    def test_pass_target_with_honest_unresolved_geometry_is_a_capability_gap(self) -> None:
        source = "Test/135/partial/pass_X5_99993.tif"
        result = evaluate_sample_contract(
            sample_expectation_from_record(_expectation_record(source)),
            _reference(source),
            _unresolved_record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.CAPABILITY_GAP)
        self.assertEqual(
            result.reasons,
            (SampleContractReason.PASS_REQUIRED_NOT_APPROVED,),
        )

    def test_pass_target_beyond_allowed_proof_reports_an_explicit_conflict(self) -> None:
        source = "Test/135/partial/pass_X5_99994.tif"
        expectation = sample_expectation_from_record(
            _expectation_record(
                source,
                observation_proof_expectation="independent_proof_unavailable",
            )
        )

        result = evaluate_sample_contract(
            expectation,
            _reference(source),
            _unresolved_record(source),
        )

        self.assertEqual(
            result.outcome,
            SampleContractOutcome.EVIDENCE_CONTRACT_CONFLICT,
        )
        self.assertEqual(
            result.reasons,
            (SampleContractReason.PASS_TARGET_EXCEEDS_PROOF_EXPECTATION,),
        )

    def test_unavailable_proof_cannot_be_overridden_by_a_supported_geometry(self) -> None:
        source = "Test/135/partial/pass_X5_99995.tif"
        result = evaluate_sample_contract(
            sample_expectation_from_record(
                _expectation_record(
                    source,
                    observation_proof_expectation="independent_proof_unavailable",
                )
            ),
            _reference(source),
            _record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.VIOLATION)
        self.assertIn(
            SampleContractReason.PROOF_UNAVAILABLE_BUT_GEOMETRY_RESOLVED,
            result.reasons,
        )

    def test_review_required_stays_review_and_not_exportable(self) -> None:
        source = "Test/135/partial/review_X5_99996.tif"
        expectation = sample_expectation_from_record(
            _expectation_record(
                source,
                dataset_intent="review",
                automatic_decision_expectation="review_required",
                observation_proof_expectation="independent_proof_unavailable",
                review_basis=["human_boundary_ambiguous"],
            )
        )

        result = evaluate_sample_contract(
            expectation,
            None,
            _unresolved_record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.CONFORMING)
        self.assertEqual(result.reasons, ())

        unsafe = evaluate_sample_contract(expectation, None, _record(source))
        self.assertEqual(unsafe.outcome, SampleContractOutcome.VIOLATION)
        self.assertIn(
            SampleContractReason.REVIEW_REQUIRED_NOT_REVIEW,
            unsafe.reasons,
        )

    def test_pass_preferred_allows_honest_review(self) -> None:
        source = "Test/135/partial/unknown_X5_99997.tif"
        result = evaluate_sample_contract(
            sample_expectation_from_record(
                _expectation_record(
                    source,
                    dataset_intent="unknown",
                    automatic_decision_expectation="pass_preferred",
                )
            ),
            _reference(source),
            _unresolved_record(source),
        )

        self.assertEqual(result.outcome, SampleContractOutcome.CONFORMING)
        self.assertEqual(result.reasons, ())

    def test_missing_or_invalid_current_report_is_a_runtime_schema_violation(self) -> None:
        source = "Test/135/partial/pass_X5_99998.tif"
        expectation = sample_expectation_from_record(_expectation_record(source))
        missing = evaluate_sample_contract(expectation, _reference(source), None)
        invalid_report = deepcopy(_record(source))
        invalid_report["schema_revision"] = "obsolete"
        invalid = evaluate_sample_contract(
            expectation,
            _reference(source),
            invalid_report,
        )

        self.assertEqual(missing.outcome, SampleContractOutcome.VIOLATION)
        self.assertEqual(
            missing.reasons,
            (SampleContractReason.CURRENT_REPORT_MISSING,),
        )
        self.assertEqual(invalid.outcome, SampleContractOutcome.VIOLATION)
        self.assertEqual(
            invalid.reasons,
            (SampleContractReason.CURRENT_REPORT_INVALID,),
        )


if __name__ == "__main__":
    unittest.main()
