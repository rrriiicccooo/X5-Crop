from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.configuration.path_sampling import (
    BoundaryPathSamplingParameters,
)
from tools.tests.frame_slot_solver_support import path as _path
from x5crop.detection.physical.boundary_detection import (
    _LocalPathSample,
    _adaptive_change_points,
    _cluster_samples,
    _cross_section_profiles,
    _holder_boundary,
    _window_statistics,
    boundary_measurements,
    short_axis_boundary_path_pairs,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    MeasurementIdentity,
    PixelInterval,
)
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)


def _measure(
    gray: np.ndarray,
    *,
    transform_position_uncertainty_px: float = 0.0,
):
    return boundary_measurements(
        gray,
        image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        ),
        BoundaryPathParameters(),
        axes=(BoundaryAxis.LONG, BoundaryAxis.SHORT),
        transform_position_uncertainty_px=transform_position_uncertainty_px,
    )


class BoundaryDetectionTests(unittest.TestCase):
    def test_requested_axis_is_the_only_cross_section_measured(self) -> None:
        gray = np.zeros((40, 80), dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )

        with patch(
            "x5crop.detection.physical.boundary_detection._cross_section_profiles",
            wraps=_cross_section_profiles,
        ) as profiles:
            boundary_measurements(
                gray,
                statistics,
                BoundaryPathParameters(),
                axes=(BoundaryAxis.SHORT,),
                transform_position_uncertainty_px=0.0,
            )

        self.assertEqual(
            [call.kwargs["scan_axis"] for call in profiles.call_args_list],
            [0],
        )

    def test_change_point_spatial_bins_do_not_call_scalar_numpy_mean(self) -> None:
        signal = np.asarray(
            [0.0, 0.0, 3.0, 3.0, 1.0, 1.0, 4.0, 4.0],
            dtype=np.float32,
        )

        with patch(
            "x5crop.detection.physical.boundary_detection.np.mean",
            side_effect=AssertionError("run midpoint is scalar geometry"),
        ):
            points = _adaptive_change_points(
                signal,
                BoundaryPathParameters().path_sampling,
            )

        self.assertTrue(points)

    def test_boundary_appearance_window_computes_gradient_once(self) -> None:
        intensity = np.asarray([0.0, 1.0, 3.0, 6.0], dtype=np.float32)
        texture = np.asarray([0.0, 1.0, 1.0, 2.0], dtype=np.float32)

        with patch.object(np, "diff", wraps=np.diff) as difference:
            _window_statistics(intensity, texture, 0, len(intensity))

        self.assertEqual(difference.call_count, 1)

    def test_boundary_appearance_reuses_each_exact_profile_window(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        measured_windows: set[tuple[object, ...]] = set()
        repeated_windows: list[tuple[object, ...]] = []

        def record_window(
            intensity: np.ndarray,
            texture: np.ndarray,
            start: int,
            end: int,
        ) -> tuple[float, float, float, float]:
            key = (
                intensity.__array_interface__["data"][0],
                intensity.strides,
                texture.__array_interface__["data"][0],
                texture.strides,
                start,
                end,
            )
            if key in measured_windows:
                repeated_windows.append(key)
            measured_windows.add(key)
            return _window_statistics(intensity, texture, start, end)

        with patch(
            "x5crop.detection.physical.boundary_detection._window_statistics",
            side_effect=record_window,
        ):
            _measure(gray)

        self.assertTrue(measured_windows)
        self.assertEqual(repeated_windows, [])

    def test_transform_uncertainty_expands_measured_path_intervals(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120

        exact = {
            item.side: item.position for item in _measure(gray).holder_boundaries
        }
        transformed = {
            item.side: item.position
            for item in _measure(
                gray,
                transform_position_uncertainty_px=3.0,
            ).holder_boundaries
        }

        for side in BoundarySide:
            with self.subTest(side=side.value):
                self.assertEqual(
                    transformed[side],
                    PixelInterval(
                        exact[side].minimum - 3.0,
                        exact[side].maximum + 3.0,
                    ),
                )

    def test_nearby_distinct_raw_paths_are_not_merged_by_cluster_tolerance(
        self,
    ) -> None:
        samples = tuple(
            _LocalPathSample(
                section_index=section_index,
                orthogonal_interval=PixelInterval(
                    float(section_index * 10),
                    float((section_index + 1) * 10),
                ),
                position=PixelInterval.exact(position),
                lower_intensity=20.0,
                lower_mad=0.0,
                lower_texture=0.0,
                lower_gradient=0.0,
                upper_intensity=200.0,
                upper_mad=0.0,
                upper_texture=0.0,
                upper_gradient=0.0,
            )
            for section_index in range(5)
            for position in (100.0, 103.0)
        )

        clusters = _cluster_samples(
            samples,
            extent=1_000,
            section_count=5,
            parameters=BoundaryPathParameters().path_sampling,
            minimum_path_support_ratio=(
                BoundaryPathParameters().minimum_path_support_ratio
            ),
        )

        self.assertEqual(
            {tuple(sample.position for sample in cluster) for cluster in clusters},
            {
                (PixelInterval.exact(100.0),) * 5,
                (PixelInterval.exact(103.0),) * 5,
            },
        )

    def test_short_axis_pair_tracking_rejects_unpaired_transitions_before_paths(
        self,
    ) -> None:
        gray = np.full((200, 500), 230, dtype=np.uint8)
        for top, bottom, value in (
            (20, 50, 30),
            (50, 80, 180),
            (80, 120, 60),
            (120, 150, 200),
            (150, 180, 80),
        ):
            gray[top:bottom, :] = value
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )

        pairs = short_axis_boundary_path_pairs(
            gray,
            statistics,
            BoundaryPathSamplingParameters(),
            minimum_path_samples=3,
            matching_constraint_ids=(
                lambda _coordinate, top, bottom: (
                    ("physical_pair",)
                    if 45.0 <= top <= 55.0
                    and 145.0 <= bottom <= 155.0
                    else ()
                )
            ),
            observation_prefix="fixture",
        )

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].constraint_id, "physical_pair")
        self.assertGreaterEqual(len(pairs[0].top_path.samples), 5)
        self.assertGreaterEqual(len(pairs[0].bottom_path.samples), 5)
        self.assertTrue(
            all(
                45.0 <= sample.position.midpoint <= 55.0
                for sample in pairs[0].top_path.samples
            )
        )
        self.assertTrue(
            all(
                145.0 <= sample.position.midpoint <= 155.0
                for sample in pairs[0].bottom_path.samples
            )
        )

    def test_edge_adjacent_paths_locate_all_four_holder_contacts(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120

        measured = _measure(gray)

        self.assertEqual(
            {item.side for item in measured.holder_boundaries},
            set(BoundarySide),
        )
        self.assertEqual(
            {
                item.side: item.position.midpoint
                for item in measured.holder_boundaries
            },
            {
                BoundarySide.LEADING: 40.5,
                BoundarySide.TRAILING: 200.5,
                BoundarySide.TOP: 20.5,
                BoundarySide.BOTTOM: 100.5,
            },
        )
        self.assertTrue(
            all(
                path.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                for item in measured.holder_boundaries
                for path in item.supporting_paths
            )
        )

    def test_holder_boundary_ignores_isolated_edge_region_defects(self) -> None:
        gray = np.full((160, 500), 255, dtype=np.uint8)
        gray[24:136, 50:450] = 80
        section_edges = np.linspace(0, gray.shape[1], 6, dtype=int)
        for section_index, (left, right) in enumerate(
            zip(section_edges[:-1], section_edges[1:], strict=True)
        ):
            top_defect = 2 + section_index * 3
            bottom_defect = gray.shape[0] - 3 - section_index * 3
            gray[top_defect, left:right] = 32
            gray[bottom_defect, left:right] = 32

        measured = _measure(gray)
        by_side = {item.side: item for item in measured.holder_boundaries}

        self.assertEqual(set(by_side), set(BoundarySide))
        self.assertLessEqual(by_side[BoundarySide.TOP].position.minimum, 24.0)
        self.assertGreaterEqual(by_side[BoundarySide.TOP].position.maximum, 24.0)
        self.assertLessEqual(by_side[BoundarySide.BOTTOM].position.minimum, 136.0)
        self.assertGreaterEqual(by_side[BoundarySide.BOTTOM].position.maximum, 136.0)
        self.assertTrue(
            all(
                path.position.maximum > path.position.minimum
                for item in measured.holder_boundaries
                for path in item.supporting_paths
            )
        )

    def test_curved_holder_edges_preserve_measured_path_uncertainty(self) -> None:
        height, width = 160, 1_200
        gray = np.full((height, width), 255, dtype=np.uint8)
        for x in range(width):
            curve = int(round(8.0 * np.sin(float(x) / 115.0)))
            top = 24 + curve
            bottom = 136 + curve
            gray[top:bottom, x] = 80

        measured = _measure(gray)
        by_side = {item.side: item for item in measured.holder_boundaries}

        self.assertIn(BoundarySide.TOP, by_side)
        self.assertIn(BoundarySide.BOTTOM, by_side)
        self.assertGreater(
            by_side[BoundarySide.TOP].position.maximum,
            by_side[BoundarySide.TOP].position.minimum,
        )
        self.assertGreater(
            by_side[BoundarySide.BOTTOM].position.maximum,
            by_side[BoundarySide.BOTTOM].position.minimum,
        )

    def test_gray_polarity_does_not_change_boundary_topology(self) -> None:
        positions = []
        for holder, aperture in ((255, 32), (0, 224)):
            gray = np.full((120, 240), holder, dtype=np.uint8)
            gray[20:100, 40:200] = aperture
            positions.append(
                tuple(
                    (item.side, item.position)
                    for item in _measure(gray).holder_boundaries
                )
            )

        self.assertEqual(positions[0], positions[1])

    def test_textured_underexposed_photo_stops_holder_adjacency(self) -> None:
        gray = np.full((120, 600), 20, dtype=np.uint8)
        checker = (np.indices((80, 250)).sum(axis=0) % 2) * 20
        gray[20:100, 50:300] = (10 + checker).astype(np.uint8)
        gray[20:100, 300:320] = 0
        gray[20:100, 320:550] = (10 + checker[:, :230]).astype(np.uint8)

        measured = _measure(gray)
        leading = next(
            boundary
            for boundary in measured.holder_boundaries
            if boundary.side == BoundarySide.LEADING
        )

        self.assertLess(leading.position.maximum, 100.0)

    def test_canvas_rim_outliers_do_not_hide_the_first_photo_boundary(self) -> None:
        gray = np.full((120, 1_000), 255, dtype=np.uint8)
        gray[:, :2] = 10
        gray[20:100, 200:500] = 80
        gray[20:100, 500:520] = 0
        gray[20:100, 520:800] = 120

        measured = _measure(gray)
        leading = next(
            boundary
            for boundary in measured.holder_boundaries
            if boundary.side == BoundarySide.LEADING
        )

        self.assertLess(leading.position.maximum, 250.0)

    def test_uniform_canvas_has_no_invented_physical_boundary(self) -> None:
        for value in (0, 128, 255):
            with self.subTest(value=value):
                measured = _measure(
                    np.full((120, 240), value, dtype=np.uint8)
                )
                self.assertEqual(measured.raw_paths, ())
                self.assertEqual(measured.holder_boundaries, ())

    def test_full_canvas_is_only_a_containment_fallback(self) -> None:
        measured = _measure(np.full((120, 240), 128, dtype=np.uint8))

        self.assertEqual(measured.containment_fallback.box, Box(0, 0, 240, 120))
        self.assertNotIn(
            measured.containment_fallback,
            measured.raw_paths,
        )

    def test_boundary_path_preserves_raw_gray_appearances(self) -> None:
        gray = np.full((120, 240), 240, dtype=np.uint8)
        gray[20:100, 40:200] = 80

        measured = _measure(gray)

        self.assertTrue(measured.raw_paths)
        for path in measured.raw_paths:
            self.assertEqual(path.lower_appearance.provenance, path.provenance)
            self.assertEqual(path.upper_appearance.provenance, path.provenance)

    def test_short_axis_paths_remain_unassigned_gray_observations(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 80
        gray[45:55, 40:200] = 160
        gray[70:80, 40:200] = 20

        measured = _measure(gray)

        self.assertTrue(measured.raw_paths)
        self.assertTrue(
            any(
                path.axis == BoundaryAxis.SHORT
                and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
                for path in measured.raw_paths
            )
        )
        self.assertTrue(
            all(
                path.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                for boundary in measured.holder_boundaries
                for path in boundary.supporting_paths
            )
        )

    def test_raw_paths_do_not_claim_holder_identity_before_assignment(self) -> None:
        gray = np.full((120, 240), 240, dtype=np.uint8)
        gray[20:100, 40:200] = 80

        measured = _measure(gray)

        self.assertTrue(measured.raw_paths)
        self.assertTrue(
            all(
                path.provenance.root_measurement
                == MeasurementIdentity.BOUNDARY_PATHS
                for path in measured.raw_paths
            )
        )
        self.assertNotIn("HOLDER_BOUNDARY_PROFILE", MeasurementIdentity.__members__)
        parameters = BoundaryPathParameters()
        self.assertTrue(
            hasattr(parameters, "edge_reference_mad_multiplier")
        )
        self.assertFalse(hasattr(parameters, "holder_reference_percentile"))

    def test_holder_boundary_requires_one_shared_position_interval(self) -> None:
        broad = _path(
            BoundaryAxis.SHORT,
            10.0,
            "broad_holder_path",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        broad = replace(
            broad,
            samples=(
                BoundaryPathSample(
                    broad.orthogonal_extent,
                    PixelInterval(10.0, 20.0),
                ),
            ),
        )
        leading_alternative = _path(
            BoundaryAxis.SHORT,
            10.0,
            "leading_holder_alternative",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        trailing_alternative = _path(
            BoundaryAxis.SHORT,
            20.0,
            "trailing_holder_alternative",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )

        self.assertIsNone(
            _holder_boundary(
                BoundarySide.TOP,
                (broad, leading_alternative, trailing_alternative),
                PixelInterval(0.0, 1_000_000.0),
            )
        )

    def test_holder_boundary_preserves_the_shared_interval_and_all_paths(self) -> None:
        first = _path(
            BoundaryAxis.SHORT,
            10.0,
            "first_overlapping_holder_path",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        first = replace(
            first,
            samples=(
                BoundaryPathSample(
                    first.orthogonal_extent,
                    PixelInterval(10.0, 20.0),
                ),
            ),
        )
        second = _path(
            BoundaryAxis.SHORT,
            15.0,
            "second_overlapping_holder_path",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        second = replace(
            second,
            samples=(
                BoundaryPathSample(
                    second.orthogonal_extent,
                    PixelInterval(15.0, 25.0),
                ),
            ),
        )

        boundary = _holder_boundary(
            BoundarySide.TOP,
            (first, second),
            PixelInterval(0.0, 1_000_000.0),
        )

        self.assertIsNotNone(boundary)
        assert boundary is not None
        self.assertEqual(boundary.position, PixelInterval(15.0, 20.0))
        self.assertEqual(boundary.supporting_paths, (first, second))
        self.assertEqual(
            boundary.provenance.boundary_anchors,
            (
                first.provenance.observation_id,
                second.provenance.observation_id,
            ),
        )

    def test_holder_boundary_role_is_clamped_to_the_workspace_extent(self) -> None:
        measured = _path(
            BoundaryAxis.SHORT,
            1.0,
            "holder_path_crossing_canvas",
            kind=BoundaryKind.EDGE_ADJACENT_TRANSITION,
        )
        measured = replace(
            measured,
            samples=(
                BoundaryPathSample(
                    measured.orthogonal_extent,
                    PixelInterval(-4.0, 2.0),
                ),
            ),
        )

        boundary = _holder_boundary(
            BoundarySide.TOP,
            (measured,),
            PixelInterval(0.0, 120.0),
        )

        self.assertIsNotNone(boundary)
        assert boundary is not None
        self.assertEqual(boundary.position, PixelInterval(0.0, 2.0))


if __name__ == "__main__":
    unittest.main()
