from __future__ import annotations

from inspect import signature
from pathlib import Path
import unittest

from x5crop.entry.cli import build_parser
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions
from x5crop.detection.candidate.assessment.separator_support import (
    separator_support_assessment,
)
from x5crop.detection.candidate.selection.choose import select_detection_candidate
from x5crop.detection.evidence.state import EvidenceState
from x5crop.domain import Box, DetectionCandidate
from x5crop.policies.registry import get_detection_policy
from x5crop.policies.reporting import detection_policy_report_detail


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _candidate(
    confidence: float,
    *,
    offset: int = 0,
    gate_passed: bool = True,
) -> DetectionCandidate:
    frames = [
        Box(offset, 0, offset + 90, 100),
        Box(offset + 105, 0, offset + 195, 100),
        Box(offset + 210, 0, offset + 300, 100),
    ]
    return DetectionCandidate(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=3,
        outer=Box(offset, 0, offset + 300, 100),
        frames=frames,
        gaps=[],
        confidence=confidence,
        detail={
            "candidate_assessment": {
                "source": "separator",
                "candidate_gate": {
                    "passed": gate_passed,
                    "checks": (
                        []
                        if gate_passed
                        else [
                            {
                                "code": "boundary_proof",
                                "state": "contradicted",
                                "blocks": True,
                            }
                        ]
                    ),
                    "proof_paths": [],
                    "failed_checks": [] if gate_passed else ["boundary_proof"],
                    "diagnostics": [],
                },
            },
        },
    )


class PhysicalGateModelContractTest(unittest.TestCase):
    def test_evidence_state_has_explicit_non_failure_states(self) -> None:
        self.assertEqual(
            {state.value for state in EvidenceState},
            {"supported", "contradicted", "unavailable", "not_applicable"},
        )
        self.assertEqual(
            EvidenceState.__module__,
            "x5crop.detection.evidence.state",
        )

    def test_separator_support_does_not_accept_candidate_confidence(self) -> None:
        self.assertNotIn("threshold", signature(separator_support_assessment).parameters)

    def test_selection_does_not_accept_format_spec(self) -> None:
        self.assertNotIn("fmt", signature(select_detection_candidate).parameters)

    def test_equivalent_candidate_geometry_is_consensus_not_competition(self) -> None:
        policy = get_detection_policy("135", "full")
        selected = select_detection_candidate(
            [_candidate(0.90), _candidate(0.90)],
            selection_policy=policy.candidate_selection,
        )

        consensus = selected.detail["selection_geometry_consensus"]
        self.assertTrue(consensus["agreed"])
        self.assertEqual(consensus["cluster_count"], 1)
        self.assertNotIn("candidate_competition", selected.detail)

    def test_failed_candidate_does_not_create_geometry_disagreement(self) -> None:
        policy = get_detection_policy("135", "full")
        selected = select_detection_candidate(
            [
                _candidate(0.80),
                _candidate(0.99, offset=200, gate_passed=False),
            ],
            selection_policy=policy.candidate_selection,
        )

        consensus = selected.detail["selection_geometry_consensus"]
        self.assertFalse(consensus["geometry_disagreement"])
        self.assertEqual(consensus["eligible_cluster_count"], 1)

    def test_gate_flow_has_no_confidence_caps_or_generic_signal_fallback(self) -> None:
        candidate_source = (
            PROJECT_ROOT / "x5crop/detection/candidate/assessment/candidate.py"
        ).read_text(encoding="utf-8")
        gate_source = (
            PROJECT_ROOT / "x5crop/detection/candidate/assessment/candidate_gate.py"
        ).read_text(encoding="utf-8")
        decision_source = (
            PROJECT_ROOT / "x5crop/detection/decision/decision_gate.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("apply_confidence_cap", candidate_source)
        self.assertNotIn("candidate_signal_gate_checks", gate_source)
        self.assertNotIn("confidence_floor", decision_source)
        self.assertNotIn('code="candidate_gate"', decision_source)
        self.assertNotIn("apply_confidence_cap", decision_source)

    def test_low_content_support_is_not_named_as_content_damage(self) -> None:
        active_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )

        self.assertNotIn("content_integrity_failed", active_source)
        self.assertNotIn("content_containment_ok", active_source)

    def test_runtime_has_no_automatic_processing_confidence_threshold(self) -> None:
        self.assertNotIn("confidence_threshold", RunConfig.__dataclass_fields__)
        self.assertNotIn("confidence_threshold", RuntimeOptions.__dataclass_fields__)
        self.assertNotIn("--confidence-threshold", build_parser().format_help())

    def test_policy_report_has_evidence_and_output_without_decision_policy(self) -> None:
        detail = detection_policy_report_detail(
            get_detection_policy("135", "full")
        )
        self.assertIn("evidence_runtime", detail)
        self.assertIn("output_runtime", detail)
        self.assertNotIn("decision_runtime", detail)
        self.assertNotIn(
            "exposure_overlap_protection",
            detail["evidence_runtime"],
        )

    def test_final_reason_vocabulary_is_physical_and_finite(self) -> None:
        from x5crop.constants import FINAL_REVIEW_REASONS

        self.assertEqual(
            FINAL_REVIEW_REASONS,
            frozenset(
                {
                    "frame_topology_invalid",
                    "content_preservation_unresolved",
                    "boundary_evidence_insufficient",
                    "photo_geometry_contradicted",
                    "evidence_independence_failed",
                    "selection_geometry_disagreement",
                    "output_protection_unresolved",
                    "transform_geometry_uncertain",
                    "automatic_processing_not_supported",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
