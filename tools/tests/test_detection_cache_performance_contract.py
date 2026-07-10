from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from x5crop.cache import AnalysisCache
from x5crop.cache.separator import cached_separator_width_profile
from x5crop.detection.candidate.execution.count_hypothesis import (
    _assess_separator_outer_plan,
)
from x5crop.detection.candidate.execution.source_candidates import (
    SeparatorOuterCandidatePlan,
)
from x5crop.detection.candidate.proposal.outer import outer_proposal_candidates
from x5crop.detection.evidence.content.frame_support import (
    _cached_content_evidence_threshold,
)
from x5crop.domain import Box, DetectionCandidate, OuterCandidate
from x5crop.formats import format_spec
from x5crop.geometry.detection_parameters import SeparatorWidthProfileSearchParameters
from x5crop.policies.registry import get_detection_policy


def _cache(gray: np.ndarray) -> AnalysisCache:
    return AnalysisCache(
        layout="horizontal",
        gray_work=gray,
        content_evidence_work=gray,
        content_evidence_float_work=gray.astype(np.float32) / 255.0,
    )


class DetectionCachePerformanceContractTest(unittest.TestCase):
    def test_separator_width_profile_is_cached_by_outer_and_parameters(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        outer = Box(0, 0, 100, 20)
        params = SeparatorWidthProfileSearchParameters()
        expected = np.arange(100, dtype=np.float32)

        with patch(
            "x5crop.cache.separator.separator_width_profile",
            return_value=expected,
        ) as measure:
            first = cached_separator_width_profile(cache, gray, outer, params)
            second = cached_separator_width_profile(cache, gray, outer, params)

        self.assertEqual(measure.call_count, 1)
        np.testing.assert_array_equal(first, expected)
        np.testing.assert_array_equal(second, expected)

    def test_content_threshold_is_cached_by_outer_and_parameters(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        outer = Box(0, 0, 100, 20)
        params = get_detection_policy("135", "full").content.evidence

        with patch(
            "x5crop.detection.evidence.content.frame_support.content_evidence_threshold",
            return_value=0.25,
        ) as measure:
            first = _cached_content_evidence_threshold(
                cache,
                cache.content_evidence_float_work,
                outer,
                params,
            )
            second = _cached_content_evidence_threshold(
                cache,
                cache.content_evidence_float_work,
                outer,
                params,
            )

        self.assertEqual(measure.call_count, 1)
        self.assertEqual(first, 0.25)
        self.assertEqual(second, 0.25)

    def test_outer_proposal_set_is_cached_across_offset_execution(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        fmt = format_spec("120-66")
        policy = get_detection_policy("120-66", "partial")
        expected = [OuterCandidate("base", Box(0, 0, 100, 20), "base_outer")]

        with patch(
            "x5crop.detection.candidate.proposal.outer.base_outer_candidates",
            return_value=expected,
        ) as base, patch(
            "x5crop.detection.candidate.proposal.outer.edge_anchored_outer_candidates",
            return_value=[],
        ), patch(
            "x5crop.detection.candidate.proposal.outer.floating_content_position_candidates",
            return_value=[],
        ), patch(
            "x5crop.detection.candidate.proposal.outer.separator_derived_outer_candidates",
            return_value=[],
        ):
            first = outer_proposal_candidates(
                gray,
                fmt,
                2,
                "partial",
                cache,
                policy=policy,
                explicit_count=False,
            )
            second = outer_proposal_candidates(
                gray,
                fmt,
                1,
                "partial",
                cache,
                policy=policy,
                explicit_count=False,
            )

        self.assertEqual(base.call_count, 1)
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)

    def test_reliable_candidate_stops_remaining_outer_plan_execution(self) -> None:
        outer_candidates = (
            OuterCandidate("first", Box(0, 0, 100, 20), "base_outer"),
            OuterCandidate("second", Box(1, 0, 99, 20), "base_outer"),
        )
        plan = SeparatorOuterCandidatePlan(
            outer_candidates,
            outer_candidates,
            {"source": "separator"},
        )
        candidate = DetectionCandidate(
            format_id="135",
            layout="horizontal",
            strip_mode="full",
            count=6,
            outer=outer_candidates[0].box,
            frames=[],
            gaps=[],
            confidence=0.9,
            detail={},
        )

        with patch(
            "x5crop.detection.candidate.execution.count_hypothesis.build_separator_candidate_for_outer",
            return_value=candidate,
        ) as build, patch(
            "x5crop.detection.candidate.execution.count_hypothesis.assess_source_candidates",
            return_value=[candidate],
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis.candidate_is_reliable_for_execution_budget",
            return_value=True,
        ):
            assessed = _assess_separator_outer_plan(
                gray=None,
                config=SimpleNamespace(confidence_threshold=0.85),
                fmt=None,
                count=6,
                strip_mode="full",
                offset=0.0,
                cache=None,
                policy=None,
                plan=plan,
                existing_candidates=(),
            )

        self.assertEqual(build.call_count, 1)
        self.assertEqual(assessed, [candidate])


if __name__ == "__main__":
    unittest.main()
