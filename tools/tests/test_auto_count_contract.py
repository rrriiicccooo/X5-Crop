from __future__ import annotations

import unittest

from x5crop.detection.candidate.assessment.count_hypothesis import (
    CountHypothesisEvaluation,
)
from x5crop.detection.candidate.plan.count_hypotheses import count_hypothesis_plan
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


if __name__ == "__main__":
    unittest.main()
