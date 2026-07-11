from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.cache import MeasurementCache
from x5crop.cache.content_statistics import ContentColumnStatistics
from x5crop.cache.separator import (
    cached_separator_evidence_crop,
    cached_separator_width_profile,
)
from x5crop.detection.evidence.content.frame_support import (
    _cached_content_evidence_threshold,
)
from x5crop.detection.evidence.count_planning import count_planning_evidence
from x5crop.detection.candidate.execution.count_hypothesis import (
    _candidates_for_offset,
    evaluate_count_hypothesis,
)
from x5crop.detection.candidate.plan.count_hypotheses import CountHypothesis
from x5crop.detection.physical.outer.types import SequenceHypothesis
from x5crop.domain import Box, MeasurementProvenance
from x5crop.formats import format_spec
from x5crop.geometry.detection_parameters import (
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from x5crop.geometry.sampling import sampling_step_for_limit
from x5crop.geometry.separator_profile import (
    separator_profile,
    separator_profile_signals,
)
from x5crop.policies.registry import get_detection_policy
from x5crop.units import ScanCalibration
from tools.tests.physical_gate_support import candidate_fixture, selection_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cache(gray: np.ndarray) -> MeasurementCache:
    return MeasurementCache(
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

    def test_separator_width_profile_is_cached_by_exact_outer_and_parameters(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        outer = Box(0, 0, 100, 20)
        parameters = SeparatorWidthProfileSearchParameters()
        expected = np.arange(100, dtype=np.float32)

        with patch(
            "x5crop.cache.separator.separator_width_profile",
            return_value=expected,
        ) as measure:
            first = cached_separator_width_profile(cache, outer, parameters)
            second = cached_separator_width_profile(cache, outer, parameters)

        self.assertEqual(measure.call_count, 1)
        np.testing.assert_array_equal(first, expected)
        np.testing.assert_array_equal(second, expected)

    def test_separator_evidence_is_cached_by_exact_parameters(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        outer = Box(0, 0, 100, 20)
        first_parameters = get_detection_policy(
            "135",
            "full",
        ).preprocess.separator_evidence_image
        second_parameters = replace(
            first_parameters,
            local_weight=first_parameters.local_weight + 0.01,
        )
        first_expected = np.zeros_like(gray)
        second_expected = np.ones_like(gray)

        with patch(
            "x5crop.cache.separator.make_separator_evidence_gray",
            side_effect=(first_expected, second_expected),
        ) as measure:
            first = cached_separator_evidence_crop(
                cache,
                outer,
                first_parameters,
            )
            second = cached_separator_evidence_crop(
                cache,
                outer,
                second_parameters,
            )

        self.assertEqual(measure.call_count, 2)
        np.testing.assert_array_equal(first, first_expected)
        np.testing.assert_array_equal(second, second_expected)

    def test_standard_separator_profile_samples_the_short_axis(self) -> None:
        crop = np.zeros((999, 100), dtype=np.uint8)
        parameters = SeparatorProfileParameters(sample_short_axis_max=125)

        with patch(
            "x5crop.geometry.separator_profile.separator_profile_signals",
            wraps=separator_profile_signals,
        ) as signals:
            separator_profile(crop, parameters)

        sampled = signals.call_args.args[0]
        self.assertLessEqual(sampled.shape[0], 125)

    def test_content_threshold_is_cached_by_exact_outer_and_parameters(self) -> None:
        gray = np.zeros((20, 100), dtype=np.uint8)
        cache = _cache(gray)
        outer = Box(0, 0, 100, 20)
        parameters = get_detection_policy("135", "full").content.evidence

        with patch(
            "x5crop.detection.evidence.content.frame_support.content_evidence_threshold",
            return_value=0.25,
        ) as measure:
            first = _cached_content_evidence_threshold(
                cache,
                cache.content_evidence_float_work,
                outer,
                parameters,
            )
            second = _cached_content_evidence_threshold(
                cache,
                cache.content_evidence_float_work,
                outer,
                parameters,
            )

        self.assertEqual(measure.call_count, 1)
        self.assertEqual(first, 0.25)
        self.assertEqual(second, 0.25)

    def test_measurement_cache_contains_only_detection_measurements(self) -> None:
        fields = set(MeasurementCache.__dataclass_fields__)
        for lifecycle_term in (
            "candidate",
            "proposal",
            "assessment",
            "gate",
            "decision",
            "selection",
        ):
            self.assertFalse(
                any(lifecycle_term in field for field in fields),
                lifecycle_term,
            )
        self.assertFalse(
            {"preview_rgb_cache", "panel_label_cache"} & fields,
            "debug rendering cache must not live in the detection measurement cache",
        )
        self.assertNotIn(
            "content_region_runs",
            fields,
            "count-dependent candidate guidance must not be cached as a root measurement",
        )

    def test_measurement_cache_is_mandatory_for_cached_helpers(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/cache/separator.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Optional[MeasurementCache]", source)
        self.assertNotIn("MeasurementCache | None", source)
        self.assertNotIn("if cache is None", source)

    def test_geometry_resolution_not_candidate_gate_controls_execution_stop(self) -> None:
        source = (
            PROJECT_ROOT
            / "x5crop/detection/candidate/execution/count_hypothesis.py"
        ).read_text(encoding="utf-8")
        evaluation_source = (
            PROJECT_ROOT / "x5crop/detection/candidate/execution/model.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("candidate_gate", source)
        self.assertNotIn(".gate", source)
        self.assertIn("geometry_resolution", evaluation_source)

    def test_geometry_resolution_stops_remaining_offsets(self) -> None:
        candidate = candidate_fixture()
        resolved = selection_fixture(candidate)
        offset_result = SimpleNamespace(
            candidates=(candidate,),
            selection=resolved,
            geometry_resolved=True,
        )
        hypothesis = CountHypothesis(
            2,
            "partial",
            (0.0, 0.5),
            "test_offsets",
            "test",
            True,
        )
        context = SimpleNamespace(
            policy=SimpleNamespace(candidate_selection=object()),
        )

        with patch(
            "x5crop.detection.candidate.execution.count_hypothesis._candidates_for_offset",
            return_value=offset_result,
        ) as evaluate_offset:
            evaluation = evaluate_count_hypothesis(
                context,
                hypothesis,
                larger_counts_evaluated=True,
            )

        self.assertEqual(evaluate_offset.call_count, 1)
        self.assertEqual(evaluation.candidates, (candidate,))

    def test_resolved_primary_candidates_skip_extension_families(self) -> None:
        candidate = candidate_fixture()
        policy = get_detection_policy("135", "partial")
        identity = SimpleNamespace()
        plan = SimpleNamespace(
            proposals=(),
            comparison_proposals=(),
            count_hypothesis=identity,
        )
        hypothesis = CountHypothesis(
            2,
            "partial",
            (0.0,),
            "test_offset",
            "test",
            True,
        )
        context = SimpleNamespace(
            request=SimpleNamespace(
                layout="horizontal",
                strip_mode="partial",
                requested_count=None,
            ),
            physical_spec=format_spec("135"),
            measurement_cache=_cache(np.zeros((100, 200), dtype=np.uint8)),
            scan_calibration=ScanCalibration(None, None, "unavailable", False),
            policy=policy,
        )

        with patch(
            "x5crop.detection.candidate.execution.count_hypothesis.separator_primary_sequence_plan",
            return_value=plan,
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis._assess_sequence_plan",
            return_value=[candidate],
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis.select_candidates",
            return_value=selection_fixture(candidate),
        ), patch(
            "x5crop.detection.candidate.execution.count_hypothesis.separator_extension_sequence_plan",
            return_value=plan,
        ) as extension, patch(
            "x5crop.detection.candidate.execution.count_hypothesis.content_separator_guidance_for_count",
            return_value=None,
        ):
            result = _candidates_for_offset(context, hypothesis, 0.0)

        extension.assert_not_called()
        self.assertTrue(result.geometry_resolved)

    def test_content_column_statistics_match_direct_measurement(self) -> None:
        evidence = np.arange(60, dtype=np.float32).reshape(6, 10) / 60.0
        threshold = 0.5
        statistics = ContentColumnStatistics.from_evidence(evidence, threshold)

        mean, coverage = statistics.interval(2, 8)
        direct = evidence[:, 2:8]

        self.assertAlmostEqual(mean, float(direct.mean()), places=6)
        self.assertAlmostEqual(
            coverage,
            float((direct >= threshold).mean()),
            places=6,
        )

    def test_count_preflight_does_not_measure_observed_width_profile(self) -> None:
        gray = np.zeros((100, 600), dtype=np.uint8)
        cache = _cache(gray)
        fmt = format_spec("120-66")
        policy = get_detection_policy("120-66", "partial")
        outer = SequenceHypothesis.from_box_hypothesis(
            "base",
            Box(0, 0, 600, 100),
            "boundary_led",
            MeasurementProvenance("holder_boundary", "test", ("gray",)),
        )

        with patch(
            "x5crop.detection.evidence.count_planning.base_sequence_span_candidates",
            return_value=[outer],
        ), patch(
            "x5crop.detection.evidence.count_planning.cached_separator_profile",
            return_value=np.zeros(600, dtype=np.float32),
        ), patch(
            "x5crop.detection.evidence.count_planning.collect_separator_outer_bands",
            return_value=SimpleNamespace(bands=[]),
        ), patch(
            "x5crop.detection.evidence.count_planning.cached_separator_width_profile"
        ) as width_profile:
            count_planning_evidence(
                gray,
                fmt,
                cache,
                outer_parameters=policy.outer.proposal.base,
                separator_profile_parameters=policy.separator.profile,
                gap_search_parameters=policy.separator.gap_search,
                separator_band_parameters=policy.outer.proposal.geometry.separator.band,
                calibration=ScanCalibration(
                    None,
                    None,
                    "unavailable",
                    False,
                ),
                long_axis="x",
            )

        width_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
