from __future__ import annotations

import math
import unittest

import numpy as np

from x5crop.detection.output_deskew import (
    DeskewEdgeFit,
    DeskewSkipReason,
    LightweightDeskewObservation,
    disabled_lightweight_deskew_observation,
    observe_lightweight_deskew,
)
from x5crop.domain import EvidenceState


def _strip(
    *,
    width: int = 2800,
    height: int = 240,
    top: np.ndarray | None = None,
    bottom: np.ndarray | None = None,
) -> np.ndarray:
    top_values = (
        np.full(width, 40.0, dtype=np.float64) if top is None else top
    )
    bottom_values = (
        np.full(width, 190.0, dtype=np.float64) if bottom is None else bottom
    )
    if top_values.shape != (width,) or bottom_values.shape != (width,):
        raise ValueError("synthetic strip edges must span the image width")
    rows = np.arange(height, dtype=np.int32)[:, np.newaxis]
    top_rows = np.rint(top_values).astype(np.int32)
    bottom_rows = np.rint(bottom_values).astype(np.int32)
    dark = (rows >= top_rows[np.newaxis, :]) & (
        rows <= bottom_rows[np.newaxis, :]
    )
    return np.where(dark, 0, 255).astype(np.uint8)


def _parallel_strip(angle_degrees: float, **kwargs: int) -> np.ndarray:
    width = kwargs.get("width", 2800)
    xs = np.arange(width, dtype=np.float64)
    slope = math.tan(math.radians(angle_degrees))
    return _strip(
        top=40.0 + slope * xs,
        bottom=190.0 + slope * xs,
        **kwargs,
    )


class OutputDeskewContractTest(unittest.TestCase):
    def test_horizontal_parallel_outer_edges_produce_supported_angle(self) -> None:
        observation = observe_lightweight_deskew(
            _parallel_strip(0.6),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertAlmostEqual(float(observation.angle_degrees), 0.6, delta=0.02)
        self.assertIsNotNone(observation.top_fit)
        self.assertIsNotNone(observation.bottom_fit)
        self.assertIsNone(observation.skip_reason)

    def test_vertical_layout_returns_existing_canonical_strip_angle_sign(self) -> None:
        canonical_work = _parallel_strip(0.7)
        observation = observe_lightweight_deskew(
            np.ascontiguousarray(canonical_work.T),
            "vertical",
        )

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertAlmostEqual(float(observation.angle_degrees), -0.7, delta=0.02)
        self.assertAlmostEqual(
            float(observation.top_fit.angle_degrees),
            0.7,
            delta=0.02,
        )

    def test_conflicting_outer_edge_slopes_are_typed_skip_without_zero(self) -> None:
        width = 2800
        xs = np.arange(width, dtype=np.float64)
        observation = observe_lightweight_deskew(
            _strip(
                width=width,
                top=40.0 + 0.001 * xs,
                bottom=180.0 + 0.010 * xs,
            ),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.EDGE_SLOPE_CONFLICT,
        )
        self.assertIsNotNone(observation.top_fit)
        self.assertIsNotNone(observation.bottom_fit)

    def test_one_outer_side_with_fewer_than_four_points_is_unavailable(self) -> None:
        width = 2800
        height = 240
        gray = np.full((height, width), 255, dtype=np.uint8)
        gray[150:191, :] = 0
        trace_count = max(6, width // 350)
        traces = np.linspace(0, width - 1, num=trace_count).astype(int)
        for trace in traces[:3]:
            left = max(0, int(trace) - 16)
            right = min(width, int(trace) + 17)
            gray[50:150, left:right] = 0

        observation = observe_lightweight_deskew(gray, "horizontal")

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.INSUFFICIENT_EDGE_POINTS,
        )
        self.assertIsNone(observation.top_fit)
        self.assertIsNotNone(observation.bottom_fit)

    def test_high_edge_residual_is_typed_skip(self) -> None:
        width = 2800
        traces = np.linspace(0, width - 1, num=8).astype(int)
        boundaries = (traces[:-1] + traces[1:]) / 2.0
        block = np.searchsorted(boundaries, np.arange(width))
        offsets = np.array(
            [10.0, -10.0, -10.0, 10.0, 10.0, -10.0, -10.0, 10.0]
        )
        observation = observe_lightweight_deskew(
            _strip(
                width=width,
                top=50.0 + offsets[block],
                bottom=np.full(width, 190.0),
            ),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.EDGE_RESIDUAL_TOO_HIGH,
        )
        self.assertGreater(float(observation.top_fit.median_residual_px), 3.0)

    def test_empty_dark_support_is_unavailable_without_fabricated_zero(self) -> None:
        for fill in (0, 255):
            with self.subTest(fill=fill):
                observation = observe_lightweight_deskew(
                    np.full((200, 1000), fill, dtype=np.uint8),
                    "horizontal",
                )

                self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
                self.assertIsNone(observation.angle_degrees)
                self.assertEqual(
                    observation.skip_reason,
                    DeskewSkipReason.NO_DARK_SUPPORT,
                )
                self.assertEqual(observation.sample_trace_count, 0)
                self.assertIsNone(observation.top_fit)
                self.assertIsNone(observation.bottom_fit)

    def test_release_minimum_outer_width_is_preserved(self) -> None:
        observation = observe_lightweight_deskew(
            _parallel_strip(0.1, width=99),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.OUTER_SUPPORT_TOO_SHORT,
        )
        self.assertEqual(observation.sample_trace_count, 0)

    def test_release_minimum_dark_content_per_trace_is_preserved(self) -> None:
        gray = np.full((240, 2800), 255, dtype=np.uint8)
        gray[100:105, :] = 0

        observation = observe_lightweight_deskew(gray, "horizontal")

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.INSUFFICIENT_EDGE_POINTS,
        )
        self.assertIsNone(observation.top_fit)
        self.assertIsNone(observation.bottom_fit)

    def test_release_outer_and_trace_thresholds_are_inclusive(self) -> None:
        gray = np.full((200, 100), 255, dtype=np.uint8)
        gray[100:110, :] = 0

        observation = observe_lightweight_deskew(gray, "horizontal")

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(observation.angle_degrees, 0.0)
        self.assertEqual(observation.sample_trace_count, 6)

    def test_zero_extent_is_typed_empty_source(self) -> None:
        observation = observe_lightweight_deskew(
            np.empty((0, 100), dtype=np.uint8),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.EMPTY_SOURCE,
        )

    def test_trace_work_is_capped_at_twenty_four(self) -> None:
        observation = observe_lightweight_deskew(
            _parallel_strip(0.1, width=10_000, height=240),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(observation.sample_trace_count, 24)
        self.assertLessEqual(observation.top_fit.sample_count, 24)
        self.assertLessEqual(observation.bottom_fit.sample_count, 24)

    def test_parallel_angle_above_two_degrees_is_typed_skip(self) -> None:
        observation = observe_lightweight_deskew(
            _parallel_strip(2.5, width=2800, height=400),
            "horizontal",
        )

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.ANGLE_OUT_OF_RANGE,
        )

    def test_valid_zero_angle_is_distinct_from_an_unavailable_measurement(
        self,
    ) -> None:
        supported = observe_lightweight_deskew(
            _parallel_strip(0.0),
            "horizontal",
        )
        self.assertEqual(supported.state, EvidenceState.SUPPORTED)
        self.assertEqual(supported.angle_degrees, 0.0)

        fit = DeskewEdgeFit(0.0, 0.0, 6, 6, 0.0)
        with self.assertRaises(ValueError):
            LightweightDeskewObservation(
                state=EvidenceState.UNAVAILABLE,
                angle_degrees=0.0,
                top_fit=fit,
                bottom_fit=fit,
                sample_trace_count=6,
                skip_reason=DeskewSkipReason.EDGE_RESIDUAL_TOO_HIGH,
            )

    def test_rotation_not_needed_uses_the_canonical_skip_enum(self) -> None:
        self.assertEqual(
            DeskewSkipReason.ROTATION_NOT_NEEDED.value,
            "rotation_not_needed",
        )

    def test_user_disabled_is_a_typed_unattempted_observation(self) -> None:
        observation = disabled_lightweight_deskew_observation()

        self.assertEqual(observation.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            observation.skip_reason,
            DeskewSkipReason.USER_DISABLED,
        )
        self.assertIsNone(observation.angle_degrees)
        self.assertEqual(observation.sample_trace_count, 0)


if __name__ == "__main__":
    unittest.main()
