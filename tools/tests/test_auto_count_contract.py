from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from x5crop.detection.candidate.assessment.count_hypothesis import (
    CountHypothesisEvaluation,
    physical_count_resolution,
)
from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
from x5crop.detection.candidate.plan.count_hypotheses import CountHypothesis
from x5crop.detection.evidence.count_planning import CountPlanningEvidence
from x5crop.detection.guidance.count_placement import content_count_placement_guidance
from x5crop.detection.candidate.execution.count_hypothesis import (
    evaluate_count_hypothesis,
)
from x5crop.detection.candidate.selection.count_hypothesis import (
    count_selection_detail,
)
from x5crop.domain import Box, DetectionCandidate
from x5crop.formats import format_spec
from x5crop.policies.registry import get_detection_policy


def _candidate(format_id: str, count: int) -> DetectionCandidate:
    return DetectionCandidate(
        format_id=format_id,
        layout="horizontal",
        strip_mode="partial",
        count=count,
        outer=Box(0, 0, 100, 20),
        frames=[],
        gaps=[],
        confidence=0.9,
        detail={},
    )


class AutoCountContractTest(unittest.TestCase):
    def _plan(self, format_id: str, requested_count: int | None = None):
        fmt = format_spec(format_id)
        policy = get_detection_policy(format_id, "partial")
        return count_hypothesis_plan(
            strip_mode="partial",
            requested_count=requested_count,
            fmt=fmt,
            partial_offsets=policy.partial_count_offsets,
            planning_evidence=CountPlanningEvidence.unavailable(),
        )

    def test_partial_auto_searches_largest_count_first(self) -> None:
        self.assertEqual(
            [hypothesis.count for hypothesis in self._plan("135").hypotheses],
            [5, 4, 3, 2, 1],
        )

    def test_complete_underfilled_formats_include_nominal_count(self) -> None:
        self.assertEqual(
            [hypothesis.count for hypothesis in self._plan("xpan").hypotheses],
            [3, 2, 1],
        )
        self.assertEqual(
            [hypothesis.count for hypothesis in self._plan("120-66").hypotheses],
            [3, 2, 1],
        )

    def test_nominal_count_has_one_placement_because_offset_cannot_change_it(self) -> None:
        for format_id in ("xpan", "120-66"):
            hypothesis = self._plan(format_id).hypotheses[0]
            self.assertEqual(hypothesis.count, format_spec(format_id).default_count)
            self.assertEqual(hypothesis.offsets, (0.0,))

    def test_requested_count_produces_one_nonautomatic_hypothesis(self) -> None:
        plan = self._plan("135", requested_count=3)
        self.assertFalse(plan.automatic)
        self.assertEqual([hypothesis.count for hypothesis in plan.hypotheses], [3])
        self.assertEqual(plan.hypotheses[0].source, "requested_count")

    def test_invalid_requested_count_is_an_assembly_error(self) -> None:
        with self.assertRaises(ValueError):
            self._plan("120-66", requested_count=4)

    def test_count_selection_names_largest_supported_hypothesis(self) -> None:
        plan = self._plan("135")
        evaluation = CountHypothesisEvaluation(
            hypothesis=plan.hypotheses[0],
            candidates=(_candidate("135", 5),),
            count_resolved=True,
            placement_resolved=True,
            candidate_auto_ready=False,
            resolved_offsets=(0.0,),
            resolution_checks=(),
        )
        detail = count_selection_detail(
            evaluation.candidates[0],
            plan,
            [evaluation],
        )
        self.assertEqual(detail["selected_count"], 5)
        self.assertEqual(detail["reason"], "largest_physically_supported_count")
        self.assertEqual(detail["physical_search_stopped_after_count"], 5)
        self.assertNotIn("search_satisfied", evaluation.report_detail())
        self.assertNotIn("supporting_offsets", evaluation.report_detail())

    def test_physically_resolved_offset_stops_remaining_placement_search(self) -> None:
        hypothesis = CountHypothesis(
            count=2,
            strip_mode="partial",
            offsets=(0.0, 0.5, 1.0),
            placement_source="configured_partial_offsets",
            placement_detail={"used": True},
            source="physical_count_evidence",
            physically_supported=True,
        )
        with patch(
            "x5crop.detection.candidate.execution.count_hypothesis._assessed_candidates_for_offset",
            side_effect=[[_candidate("135", 2)]],
        ) as assessed, patch(
            "x5crop.detection.candidate.execution.count_hypothesis.physical_count_resolution",
            return_value=physical_count_resolution(
                _physically_resolved_candidate("135", 2),
                hypothesis,
            ),
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis.select_source_candidate",
            return_value=_candidate("135", 2),
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis.candidate_is_reliable_for_execution_budget",
            return_value=False,
        ):
            evaluation = evaluate_count_hypothesis(
                gray=None,
                config=SimpleNamespace(confidence_threshold=0.85),
                fmt=None,
                hypothesis=hypothesis,
                cache=None,
                policy=None,
            )

        self.assertEqual(assessed.call_count, 1)
        self.assertTrue(evaluation.count_resolved)
        self.assertTrue(evaluation.placement_resolved)
        self.assertFalse(evaluation.candidate_auto_ready)
        self.assertEqual(evaluation.resolved_offsets, (0.0,))
        resolution_check = evaluation.report_detail()["resolution_checks"][0]
        self.assertTrue(resolution_check["evidence"]["hard_separator_complete"])

    def test_physical_resolution_does_not_read_candidate_gate_or_confidence(self) -> None:
        hypothesis = CountHypothesis(
            3,
            "partial",
            (0.0,),
            "hard_separator_bands",
            {"used": True},
            "physical_count_evidence",
            True,
        )
        candidate = _physically_resolved_candidate("120-66", 3)
        candidate.confidence = 0.01
        candidate.detail["candidate_assessment"]["candidate_gate"] = {"passed": False}

        resolution = physical_count_resolution(candidate, hypothesis)

        self.assertTrue(resolution.count_resolved)
        self.assertTrue(resolution.placement_resolved)
        self.assertNotIn("candidate_gate", resolution.evidence)
        self.assertNotIn("confidence", resolution.evidence)

    def test_physical_count_evidence_orders_without_pruning_alternatives(self) -> None:
        fmt = format_spec("135")
        policy = get_detection_policy("135", "partial")
        evidence = CountPlanningEvidence(
            supported_count=3,
            source_outer=Box(0, 0, 600, 100),
            hard_bands=(),
            placement_offsets=((3, (0.37,)),),
            detail={"source": "hard_separator_bands"},
        )

        plan = count_hypothesis_plan(
            strip_mode="partial",
            requested_count=None,
            fmt=fmt,
            partial_offsets=policy.partial_count_offsets,
            planning_evidence=evidence,
        )

        self.assertEqual([item.count for item in plan.hypotheses], [3, 5, 4, 2, 1])
        self.assertEqual(plan.hypotheses[0].offsets, (0.37,))
        self.assertTrue(plan.hypotheses[0].physically_supported)
        self.assertFalse(plan.hypotheses[1].physically_supported)

    def test_single_frame_auto_count_defers_fixed_offsets_to_guidance(self) -> None:
        hypothesis = self._plan("135").hypotheses[-1]

        self.assertEqual(hypothesis.count, 1)
        self.assertEqual(hypothesis.offsets, ())

    def test_unresolved_multi_frame_count_defers_placement_measurement(self) -> None:
        hypothesis = next(
            item for item in self._plan("135").hypotheses if item.count == 2
        )

        self.assertEqual(hypothesis.offsets, ())
        self.assertEqual(hypothesis.placement_source, "deferred")

    def test_single_frame_guidance_uses_content_position_not_fixed_offset_grid(self) -> None:
        from x5crop.cache import AnalysisCache
        import numpy as np

        gray = np.zeros((100, 600), dtype=np.uint8)
        cache = AnalysisCache(
            layout="horizontal",
            gray_work=gray,
            content_evidence_work=gray,
            content_evidence_float_work=gray.astype(np.float32),
        )
        policy = get_detection_policy("135", "partial")
        with patch(
            "x5crop.detection.guidance.count_placement.content_mask_region_detail",
            return_value={"used": True, "outer": {"left": 180, "top": 0, "right": 420, "bottom": 100}},
        ):
            guidance = content_count_placement_guidance(
                cache,
                format_spec("135"),
                1,
                Box(0, 0, 600, 100),
                policy.content,
            )

        self.assertTrue(guidance.offsets)
        self.assertLess(len(guidance.offsets), 5)
        self.assertEqual(guidance.source, "content_position_guidance")

    def test_content_position_guidance_supports_multi_frame_span(self) -> None:
        from x5crop.cache import AnalysisCache
        import numpy as np

        gray = np.zeros((100, 900), dtype=np.uint8)
        cache = AnalysisCache(
            layout="horizontal",
            gray_work=gray,
            content_evidence_work=gray,
            content_evidence_float_work=gray.astype(np.float32),
        )
        policy = get_detection_policy("135", "partial")
        with patch(
            "x5crop.detection.guidance.count_placement.content_mask_region_detail",
            return_value={"used": True, "outer": {"left": 200, "top": 0, "right": 700, "bottom": 100}},
        ):
            guidance = content_count_placement_guidance(
                cache,
                format_spec("135"),
                4,
                Box(0, 0, 900, 100),
                policy.content,
            )

        self.assertTrue(guidance.offsets)
        self.assertLess(len(guidance.offsets), 5)
        self.assertEqual(guidance.detail["count"], 4)


def _physically_resolved_candidate(format_id: str, count: int) -> DetectionCandidate:
    candidate = _candidate(format_id, count)
    candidate.detail.update(
        {
            "frame_topology_evidence": {
                "frame_extent_valid": True,
                "frame_order_valid": True,
                "frame_overlap_absent": True,
            },
            "separator_cross_axis_continuity": {"ok": True},
            "photo_width_stability": {"used": True, "unstable": False},
            "candidate_assessment": {
                "separator_support": {
                    "ok": True,
                    "hard_gaps": count - 1,
                }
            },
        }
    )
    return candidate


if __name__ == "__main__":
    unittest.main()
