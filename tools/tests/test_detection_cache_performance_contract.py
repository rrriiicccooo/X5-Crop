from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from x5crop.cache import AnalysisCache
from x5crop.cache.content_statistics import ContentColumnStatistics
from x5crop.cache.separator import cached_separator_width_profile
from x5crop.detection.candidate.execution.count_hypothesis import (
    _assess_separator_outer_plan,
)
from x5crop.detection.candidate.execution.source_candidates import (
    OuterCandidateCohort,
    SeparatorOuterCandidatePlan,
)
from x5crop.detection.candidate.proposal.outer import outer_proposal_candidates
from x5crop.detection.evidence.content.frame_support import (
    _cached_content_evidence_threshold,
    content_frame_support_detail,
)
from x5crop.detection.evidence.count_planning import count_planning_evidence
from x5crop.domain import Box, DetectionCandidate, OuterCandidate
from x5crop.formats import format_spec
from x5crop.geometry.detection_parameters import (
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from x5crop.geometry.sampling import sampling_step_for_limit
from x5crop.geometry.separator_profile import separator_profile, separator_profile_signals
from x5crop.policies.registry import get_detection_policy


def _cache(gray: np.ndarray) -> AnalysisCache:
    return AnalysisCache(
        layout="horizontal",
        gray_work=gray,
        content_evidence_work=gray,
        content_evidence_float_work=gray.astype(np.float32) / 255.0,
    )


class DetectionCachePerformanceContractTest(unittest.TestCase):
    def test_separator_profile_sampling_limit_is_a_hard_upper_bound(self) -> None:
        step = sampling_step_for_limit(999, 500)

        self.assertEqual(step, 2)
        self.assertLessEqual(len(range(0, 999, step)), 500)

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

    def test_standard_separator_profile_samples_the_short_axis(self) -> None:
        crop = np.zeros((999, 100), dtype=np.uint8)
        params = SeparatorProfileParameters(sample_short_axis_max=125)

        with patch(
            "x5crop.geometry.separator_profile.separator_profile_signals",
            wraps=separator_profile_signals,
        ) as signals:
            separator_profile(crop, params)

        sampled = signals.call_args.args[0]
        self.assertLessEqual(sampled.shape[0], 125)

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

    def test_outer_plan_assesses_every_candidate_without_gate_driven_early_stop(self) -> None:
        outer_candidates = (
            OuterCandidate("first", Box(0, 0, 100, 20), "base_outer"),
            OuterCandidate("second", Box(1, 0, 99, 20), "base_outer"),
        )
        plan = SeparatorOuterCandidatePlan(
            (OuterCandidateCohort("physical_primary", outer_candidates),),
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
        ):
            assessed = _assess_separator_outer_plan(
                gray=None,
                config=SimpleNamespace(),
                fmt=None,
                count=6,
                strip_mode="full",
                offset=0.0,
                cache=None,
                policy=None,
                plan=plan,
            )

        self.assertEqual(build.call_count, 2)
        self.assertEqual(assessed, [candidate, candidate])

    def test_content_column_statistics_match_direct_frame_measurement(self) -> None:
        evidence = np.arange(60, dtype=np.float32).reshape(6, 10) / 60.0
        outer = Box(0, 0, 10, 6)
        frames = [Box(0, 0, 4, 6), Box(4, 0, 10, 6)]
        threshold = 0.5
        params = get_detection_policy("135", "full").content.evidence
        statistics = ContentColumnStatistics.from_evidence(evidence, threshold)

        direct = content_frame_support_detail(
            evidence,
            outer,
            frames,
            evidence.shape,
            threshold=threshold,
            expected_aspect=None,
            evidence_params=params,
            composite="test",
        )
        cached = content_frame_support_detail(
            evidence,
            outer,
            frames,
            evidence.shape,
            threshold=threshold,
            expected_aspect=None,
            evidence_params=params,
            composite="test",
            column_statistics=statistics,
        )

        for direct_frame, cached_frame in zip(
            direct["frame_scores"], cached["frame_scores"], strict=True
        ):
            self.assertAlmostEqual(direct_frame["mean"], cached_frame["mean"], places=6)
            self.assertAlmostEqual(
                direct_frame["coverage"], cached_frame["coverage"], places=6
            )

    def test_count_preflight_does_not_measure_observed_width_profile(self) -> None:
        gray = np.zeros((100, 600), dtype=np.uint8)
        cache = _cache(gray)
        fmt = format_spec("120-66")
        policy = get_detection_policy("120-66", "partial")
        outer = OuterCandidate("base", Box(0, 0, 600, 100), "base_outer")

        with patch(
            "x5crop.detection.evidence.count_planning.cached_base_outer_candidates",
            return_value=[outer],
        ), patch(
            "x5crop.detection.evidence.count_planning.cached_separator_profile",
            return_value=np.zeros(600, dtype=np.float32),
        ), patch(
            "x5crop.detection.evidence.count_planning.collect_separator_outer_bands",
        ) as hard_bands, patch(
            "x5crop.detection.evidence.count_planning.cached_separator_width_profile"
        ) as width_profile:
            hard_bands.return_value = SimpleNamespace(bands=[])
            count_planning_evidence(
                gray,
                fmt,
                cache,
                outer_parameters=policy.outer.proposal.base,
                separator_profile_parameters=policy.separator.profile,
                gap_search_parameters=policy.separator.gap_search,
                separator_band_parameters=policy.outer.proposal.geometry.separator.band,
            )

        width_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
