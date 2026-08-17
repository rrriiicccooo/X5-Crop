from __future__ import annotations

import ast
from pathlib import Path
import unittest

from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_model import PhaseLatticeAuthority
from x5crop.detection.photo_geometry.template_registration import (
    template_spec_from_physical_authority,
)


def _source(frame: FramePhysicalSpec) -> SourceScanGeometry:
    return SourceScanGeometry.create(
        frame,
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )


def _lattice() -> PhaseLatticeAuthority:
    return PhaseLatticeAuthority(
        period_px=380.0,
        cycle_origin_px=0.0,
        minimum_slot_offset=-1,
        maximum_slot_offset=20,
    )


class TemplateRegistrationContractTest(unittest.TestCase):
    def test_source_scale_evidence_intersects_without_lane_identity(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        first = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(9.0, 10.0),
        )
        second = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(9.5, 10.5),
            height_scale_px_per_mm=PositiveInterval(9.25, 10.25),
        )

        shared = first.intersect_source_state(second)

        self.assertEqual(
            shared.width_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )
        self.assertEqual(
            shared.height_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )
        self.assertFalse(hasattr(shared, "lane_id"))

    def test_width_observation_does_not_recalibrate_source_height(self) -> None:
        frame = FramePhysicalSpec(70.0, 56.0, None)
        geometry = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval(64.0, 69.0),
            height_scale_px_per_mm=PositiveInterval(64.0, 69.0),
        )
        original_height = geometry.height_state.extent_projection_px()
        narrowed_width = geometry.width_state.intersect_observed_extent(
            FiniteInterval(4520.0, 4560.0),
            observation_ids=(ObservationId("observed-width"),),
        )

        refined = SourceScanGeometry.from_axis_states(
            frame,
            narrowed_width,
            geometry.height_state,
        )

        self.assertEqual(
            refined.height_state.extent_projection_px(),
            original_height,
        )
        self.assertNotEqual(
            refined.width_state.extent_projection_px(),
            geometry.width_state.extent_projection_px(),
        )

    def test_registration_uses_direct_phase_and_format_gap(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        template = template_spec_from_physical_authority(
            frame_spec=frame,
            source_geometry=_source(frame),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            count=6,
            phase_lattice_authority=_lattice(),
        )
        self.assertFalse(hasattr(template, "phase_authority"))
        self.assertEqual(template.count, 6)
        self.assertEqual(template.nominal_gap_px.minimum, 20.0)
        self.assertEqual(template.nominal_gap_px.maximum, 20.0)

    def test_explicit_count_equal_to_capacity_gets_no_center_authority(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        template = template_spec_from_physical_authority(
            frame_spec=frame,
            source_geometry=_source(frame),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            count=6,
            phase_lattice_authority=_lattice(),
        )
        self.assertFalse(hasattr(template, "phase_authority"))
        self.assertEqual(template.count, 6)

    def test_registration_does_not_import_retired_candidate_modules(self) -> None:
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_registration.py"
        )
        tree = ast.parse(path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", ())
        ]
        self.assertFalse(
            any(
                token in name
                for name in imports
                for token in ("proposal", "materialization", "chain", "cache")
            )
        )


if __name__ == "__main__":
    unittest.main()
