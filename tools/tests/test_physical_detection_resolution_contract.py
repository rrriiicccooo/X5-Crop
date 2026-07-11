from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from x5crop.detection.candidate.assessment.candidate import _boundary_proof_paths
from x5crop.detection.candidate.assessment.candidate_gate import BoundaryProofPath
from x5crop.detection.candidate.assessment.count_hypothesis import physical_count_resolution
from x5crop.detection.candidate.build.separator_sources import (
    InitialSeparatorGapResult,
    select_geometry_equal_model_gaps,
)
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    count_hypothesis_plan,
)
from x5crop.detection.evidence.content.preservation import content_preservation_evidence
from x5crop.detection.evidence.count_planning import CountPlanningEvidence
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.physical.photo_size import photo_size_consistency_from_gap_edges
from x5crop.domain import Box, DetectionCandidate, Gap
from x5crop.formats import format_spec
from x5crop.geometry.frame_fit import frame_boxes_from_gaps


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _coverage(state: EvidenceState) -> FrameCoverageEvidence:
    return FrameCoverageEvidence(
        state=state,
        reason="test",
        holder_interval=(0, 100),
        film_interval=(0, 100),
        frame_intervals=((0, 100),),
        content_runs=((0, 100),),
        uncovered_content=(),
    )


def _resolved_candidate(count: int) -> DetectionCandidate:
    gaps = [
        Gap(index=index, center=float(index * 100), score=1.0, method="detected", start=index * 100 - 5, end=index * 100 + 5)
        for index in range(1, count)
    ]
    return DetectionCandidate(
        format_id="135",
        layout="horizontal",
        strip_mode="partial",
        count=count,
        outer=Box(0, 0, count * 100, 60),
        frames=[Box(index * 100, 0, (index + 1) * 100, 60) for index in range(count)],
        gaps=gaps,
        confidence=1.0,
        detail={
            "frame_topology_evidence": {
                "frame_extent_valid": True,
                "frame_order_valid": True,
                "frame_overlap_absent": True,
            },
            "photo_width_stability": {"used": True, "unstable": False},
            "candidate_assessment": {
                "separator_support": {
                    "ok": True,
                    "expected_gaps": max(0, count - 1),
                    "hard_gaps": max(0, count - 1),
                    "grid_gaps": 0,
                    "equal_gaps": 0,
                }
            },
        },
    )


class PhysicalDetectionResolutionContractTest(unittest.TestCase):
    def test_frame_coverage_contradiction_prevents_count_resolution(self) -> None:
        candidate = _resolved_candidate(2)
        candidate.detail["frame_coverage_evidence"] = {
            "state": EvidenceState.CONTRADICTED.value,
            "unexplained_trailing_content": True,
        }
        hypothesis = CountHypothesis(
            count=2,
            strip_mode="partial",
            offsets=(0.0,),
            placement_source="hard_separator_bands",
            placement_detail={"used": True},
            source="physical_count_evidence",
            physically_supported=True,
        )

        resolution = physical_count_resolution(candidate, hypothesis)

        self.assertFalse(resolution.count_resolved)
        self.assertFalse(resolution.placement_resolved)

    def test_single_frame_has_no_separator_or_geometry_proof_by_default(self) -> None:
        candidate = _resolved_candidate(1)
        candidate.detail["separator_cross_axis_continuity"] = {"used": False, "ok": True}

        paths = _boundary_proof_paths(
            candidate,
            "separator",
            {
                "ok": True,
                "expected_gaps": 0,
                "hard_gaps": 0,
                "grid_gaps": 0,
                "equal_gaps": 0,
            },
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            EvidenceState.NOT_APPLICABLE,
            {"state": EvidenceState.SUPPORTED.value, "boundary_support": False},
        )

        supported = [path.code for path in paths if path.state == EvidenceState.SUPPORTED]
        self.assertEqual(supported, [])

    def test_incomplete_hard_separator_sequence_has_no_separator_led_proof(self) -> None:
        candidate = _resolved_candidate(3)
        candidate.gaps = candidate.gaps[:1]
        candidate.detail["separator_cross_axis_continuity"] = {
            "used": True,
            "ok": True,
            "weak_gap_indexes": [],
        }

        paths = _boundary_proof_paths(
            candidate,
            "separator",
            {
                "ok": True,
                "expected_gaps": 2,
                "hard_gaps": 1,
                "grid_gaps": 0,
                "equal_gaps": 1,
            },
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            {"state": EvidenceState.NOT_APPLICABLE.value},
        )

        separator_led = next(path for path in paths if path.code == "separator_led")
        self.assertEqual(separator_led.state, EvidenceState.UNAVAILABLE)

    def test_single_frame_pitch_is_not_measured_photo_size(self) -> None:
        evidence = photo_size_consistency_from_gap_edges([], 0.0, 100.0, 1)

        self.assertFalse(evidence.used)
        self.assertEqual(evidence.reason, "single_frame_requires_independent_boundaries")

    def test_complete_underfilled_strip_never_suppresses_confirmed_undercrop(self) -> None:
        evidence = content_preservation_evidence(
            {"content_boundary_contact": True, "frame_content_support_available": True},
            {"used": True, "ok": False, "confirmed_undercrop": True},
            {"preservation_failures": [], "complete_underfilled_strip": True},
            _coverage(EvidenceState.SUPPORTED),
        )

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(evidence.reason, "content_undercrop_confirmed")

    def test_partial_auto_count_order_remains_largest_first(self) -> None:
        fmt = format_spec("135")
        planning = CountPlanningEvidence(
            supported_count=2,
            source_outer=Box(0, 0, 600, 100),
            hard_bands=(),
            placement_offsets=((2, (0.0,)),),
            detail={"used": True},
        )

        plan = count_hypothesis_plan(
            strip_mode="partial",
            requested_count=None,
            fmt=fmt,
            partial_offsets=(0.0, 0.5, 1.0),
            planning_evidence=planning,
        )

        self.assertEqual([hypothesis.count for hypothesis in plan.hypotheses], [5, 4, 3, 2, 1])
        self.assertTrue(next(item for item in plan.hypotheses if item.count == 2).physically_supported)

    def test_equal_model_fills_missing_indexes_without_replacing_hard_gaps(self) -> None:
        hard = Gap(index=3, center=300.0, score=1.2, method="detected", start=295.0, end=305.0)
        result = select_geometry_equal_model_gaps(
            InitialSeparatorGapResult(
                gaps=[hard],
                standard_gap_search_detail={"detected_count": 1},
            ),
            np.zeros(600, dtype=np.float32),
            format_spec("135"),
            count=6,
            strip_mode="full",
            origin=0.0,
            pitch=100.0,
            gap_max_width_ratio_override=None,
        )

        self.assertEqual(len(result.gaps), 5)
        self.assertIs(next(gap for gap in result.gaps if gap.index == 3), hard)
        self.assertEqual(sum(gap.method == "detected" for gap in result.gaps), 1)

    def test_frame_fit_does_not_replace_irregular_separator_cuts_with_equal_pitch(self) -> None:
        frames = frame_boxes_from_gaps(
            Box(0, 0, 360, 100),
            [
                Gap(1, 90.0, 1.0, "detected", 85.0, 95.0),
                Gap(2, 230.0, 1.0, "detected", 225.0, 235.0),
            ],
            3,
            360,
            100,
            0,
            0,
            origin=0.0,
            pitch=120.0,
        )

        self.assertEqual([(frame.left, frame.right) for frame in frames], [(0, 90), (90, 230), (230, 360)])

    def test_execution_budget_does_not_read_candidate_gate_reliability(self) -> None:
        source = (PROJECT_ROOT / "x5crop/detection/candidate/execution/count_hypothesis.py").read_text()

        self.assertNotIn("candidate_is_reliable_for_execution_budget", source)


if __name__ == "__main__":
    unittest.main()
