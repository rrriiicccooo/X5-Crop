from __future__ import annotations

import unittest
from unittest.mock import patch

from x5crop.detection.candidate.assessment.count_hypothesis import (
    CountHypothesisEvaluation,
)
from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
from x5crop.detection.candidate.plan.count_hypotheses import CountHypothesis
from x5crop.detection.evidence.count_planning import CountPlanningEvidence
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
            search_satisfied=True,
            supporting_offsets=(0.0,),
        )
        detail = count_selection_detail(
            evaluation.candidates[0],
            plan,
            [evaluation],
        )
        self.assertEqual(detail["selected_count"], 5)
        self.assertEqual(detail["reason"], "largest_physically_supported_count")
        self.assertEqual(detail["search_stopped_after_count"], 5)

    def test_supported_offset_stops_remaining_equivalent_placement_search(self) -> None:
        hypothesis = CountHypothesis(
            count=2,
            strip_mode="partial",
            offsets=(0.0, 0.5, 1.0),
            source="automatic_count",
            physically_supported=False,
        )
        with patch(
            "x5crop.detection.candidate.execution.count_hypothesis._assessed_candidates_for_offset",
            side_effect=[([], True), ([], False), ([], False)],
        ) as assessed:
            evaluation = evaluate_count_hypothesis(
                gray=None,
                config=None,
                fmt=None,
                hypothesis=hypothesis,
                cache=None,
                policy=None,
            )

        self.assertEqual(assessed.call_count, 1)
        self.assertTrue(evaluation.search_satisfied)
        self.assertEqual(evaluation.supporting_offsets, (0.0,))

    def test_physical_count_evidence_orders_without_pruning_alternatives(self) -> None:
        fmt = format_spec("135")
        policy = get_detection_policy("135", "partial")
        evidence = CountPlanningEvidence(
            supported_count=3,
            hard_separator_count=2,
            observed_separator_centers=(120.0, 220.0),
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


if __name__ == "__main__":
    unittest.main()
