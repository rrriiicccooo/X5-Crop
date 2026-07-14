from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from tools.tests.photo_aperture_solver_support import path as _path
from x5crop.detection.physical.boundary_detection import (
    _LocalPathSample,
    _cluster_samples,
    _holder_boundary,
    boundary_measurements,
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


def _measure(gray: np.ndarray):
    return boundary_measurements(
        gray,
        image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        ),
        BoundaryPathParameters(),
    )


class BoundaryDetectionTests(unittest.TestCase):
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

        clusters, budget_exhausted = _cluster_samples(
            samples,
            extent=1_000,
            section_count=5,
            parameters=BoundaryPathParameters(),
        )

        self.assertFalse(budget_exhausted)
        self.assertEqual(
            {tuple(sample.position for sample in cluster) for cluster in clusters},
            {
                (PixelInterval.exact(100.0),) * 5,
                (PixelInterval.exact(103.0),) * 5,
            },
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
                BoundarySide.LEADING: 40.0,
                BoundarySide.TRAILING: 201.0,
                BoundarySide.TOP: 20.0,
                BoundarySide.BOTTOM: 101.0,
            },
        )
        self.assertTrue(
            all(
                path.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                for item in measured.holder_boundaries
                for path in item.supporting_paths
            )
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
        self.assertTrue(hasattr(parameters, "edge_reference_percentile"))
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

        boundary = _holder_boundary(BoundarySide.TOP, (first, second))

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


if __name__ == "__main__":
    unittest.main()
