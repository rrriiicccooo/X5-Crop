from __future__ import annotations

import unittest

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.physical.boundary_detection import boundary_measurements
from x5crop.domain import BoundaryKind, BoundarySide, Box
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
                item.path.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                for item in measured.holder_boundaries
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


if __name__ == "__main__":
    unittest.main()
