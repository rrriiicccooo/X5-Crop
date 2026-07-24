from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.physical_gates import (
    boundary_path_fixture,
    candidate_fixture,
)
from x5crop.debug.separators import (
    _selected_boundary_paths,
    _selected_separator_observations,
)
from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


class DebugObservationVisibilityContractTest(unittest.TestCase):
    def test_overlay_excludes_unselected_raw_measurements(self) -> None:
        geometry = candidate_fixture().geometry
        unused_path = boundary_path_fixture(
            BoundarySide.LEADING,
            PixelInterval.exact(75.0),
            BoundaryKind.TONAL_TRANSITION,
            MeasurementProvenance(
                MeasurementIdentity.BOUNDARY_PATHS,
                ObservationId("unused_debug_boundary_path"),
                (MeasurementIdentity.GRAY_WORK,),
                "unselected raw path retained only in the report",
            ),
        )
        geometry = replace(
            geometry,
            raw_boundary_paths=(*geometry.raw_boundary_paths, unused_path),
        )

        selected_paths = _selected_boundary_paths(geometry)
        selected_separators = _selected_separator_observations(geometry)

        self.assertNotIn(unused_path, selected_paths)
        self.assertEqual(
            {item.provenance.observation_id for item in selected_paths},
            {
                *(
                    path.provenance.observation_id
                    for boundary in geometry.holder_safety.boundaries
                    for path in boundary.supporting_paths
                ),
                *(
                    assignment.observation.provenance.observation_id
                    for assignment in geometry.long_axis_assignments
                ),
            },
        )
        self.assertEqual(
            selected_separators,
            tuple(
                assignment.observation
                for assignment in geometry.separator_assignments
            ),
        )


if __name__ == "__main__":
    unittest.main()
