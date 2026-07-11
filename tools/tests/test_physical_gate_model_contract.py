from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.separator_support import separator_sequence_evidence
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.evidence.state import EvidenceState
from x5crop.entry.cli import build_parser
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PhysicalGateModelContractTest(unittest.TestCase):
    def test_evidence_state_has_explicit_non_failure_states(self) -> None:
        self.assertEqual(
            {state.value for state in EvidenceState},
            {"supported", "contradicted", "unavailable", "not_applicable"},
        )

    def test_separator_support_does_not_accept_confidence(self) -> None:
        self.assertNotIn("confidence", signature(separator_sequence_evidence).parameters)

    def test_selection_does_not_accept_format_spec(self) -> None:
        self.assertNotIn("fmt", signature(select_candidates).parameters)

    def test_equivalent_geometry_is_consensus(self) -> None:
        candidate = candidate_fixture()
        result = select_candidates(
            (candidate, candidate),
            get_detection_policy("135", "full").candidate_selection,
            larger_counts_evaluated=True,
        )
        self.assertEqual(result.consensus, "agreed")
        self.assertEqual(len(result.clusters), 1)

    def test_failed_candidate_does_not_create_equal_rank_disagreement(self) -> None:
        good = candidate_fixture(confidence=0.80)
        bad = candidate_fixture(
            confidence=0.99,
            failed_candidate_check="boundary_proof",
        )
        bad = replace(
            bad,
            geometry=replace(
                bad.geometry,
                film_span=replace(
                    bad.geometry.film_span,
                    box=bad.geometry.film_span.box.expand(20, 0, 240, 100),
                ),
            ),
        )
        result = select_candidates(
            (good, bad),
            get_detection_policy("135", "full").candidate_selection,
            larger_counts_evaluated=True,
        )
        self.assertNotEqual(result.consensus, "disagreed")

    def test_gate_flow_has_no_confidence_caps_or_generic_fallback(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py")
        )
        for forbidden in (
            "apply_confidence_cap",
            "confidence_floor",
            "candidate_signal_gate_checks",
            "candidate_gate_failed",
        ):
            self.assertNotIn(forbidden, source)

    def test_runtime_has_no_auto_confidence_threshold(self) -> None:
        self.assertNotIn("confidence_threshold", RunConfig.__dataclass_fields__)
        self.assertNotIn("confidence_threshold", RuntimeOptions.__dataclass_fields__)
        self.assertNotIn("--confidence-threshold", build_parser().format_help())

    def test_final_reason_vocabulary_is_finite_and_physical(self) -> None:
        from x5crop.constants import FINAL_REVIEW_REASONS

        self.assertEqual(len(FINAL_REVIEW_REASONS), 9)
        self.assertIn("content_preservation_unresolved", FINAL_REVIEW_REASONS)
        self.assertIn("boundary_evidence_insufficient", FINAL_REVIEW_REASONS)


if __name__ == "__main__":
    unittest.main()
