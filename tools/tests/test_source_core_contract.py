from __future__ import annotations

from dataclasses import fields, replace
import math
import unittest

import numpy as np

from x5crop.configuration.registry import get_detection_configuration
from x5crop.configuration.scan_canvas import ScanCanvasDetectionConfiguration
from x5crop.detection.evidence.scan_canvas import (
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.photo_geometry.corridors import (
    build_top_bottom_search_corridors,
    frame_physical_pixel_intervals,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.detection.source_core import (
    SourceLaneEvidence,
)
from x5crop.domain import (
    PositiveInterval,
)
from x5crop.formats import FRAME_DIMENSION_TOLERANCE_SPEC, format_spec
from x5crop.formats.scan_canvas import (
    SCAN_CANVAS_PHYSICAL_SPECS,
    ScanCanvasPhysicalSpec,
    scan_canvas_specs_for_format,
)
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.io.orientation import orientation_mapping


class PhysicalAuthorityContractTest(unittest.TestCase):
    def test_design_apertures_count_and_tolerance_are_typed(self) -> None:
        expected = {
            "135": ((36.0, 24.0), 6, True),
            "135-dual": ((36.0, 24.0), 12, False),
            "half": ((18.0, 24.0), 12, True),
            "xpan": ((65.0, 24.0), 3, True),
            "120-645": ((42.0, 56.0), 4, True),
            "120-66": ((56.0, 56.0), 3, True),
            "120-67": ((70.0, 56.0), 3, True),
        }
        for format_id, values in expected.items():
            spec = format_spec(format_id)
            self.assertEqual(
                tuple(
                    (item.frame_width_mm, item.frame_height_mm)
                    for item in spec.frame_components
                ),
                values[:-2],
            )
            self.assertEqual(spec.strip.default_count, values[-2])
            self.assertEqual(spec.strip.partial_mode_supported, values[-1])
            self.assertFalse(hasattr(spec, "aperture_tolerance"))
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
            0.0125,
        )
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
            0.0040,
        )

    def test_aperture_pixel_interval_propagates_scale_and_tolerance(
        self,
    ) -> None:
        spec = format_spec("135")
        aperture = spec.frame_components[0]
        intervals = frame_physical_pixel_intervals(
            aperture,
            PositiveInterval(10.0, 11.0),
            PositiveInterval(9.0, 10.0),
        )
        self.assertAlmostEqual(intervals.frame_width_px.minimum, 355.5)
        self.assertAlmostEqual(intervals.frame_width_px.maximum, 400.95)
        self.assertAlmostEqual(intervals.frame_height_px.minimum, 215.136)
        self.assertAlmostEqual(intervals.frame_height_px.maximum, 240.96)
        self.assertNotEqual(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm,
            aperture.frame_width_mm
            * FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
        )
        self.assertEqual(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC
            .angle_endpoint_uncertainty_multiplier,
            2.0,
        )

    def test_scan_canvas_is_the_only_scale_owner_with_typed_interval(
        self,
    ) -> None:
        profile = ScanCanvasPhysicalSpec(
            "only",
            short_axis_mm=10.0,
            long_axis_mm=50.0,
        )
        scan_configuration = ScanCanvasDetectionConfiguration((profile,))
        evidence = observe_scan_canvas(
            500,
            100,
            "horizontal",
            scan_configuration,
        )
        self.assertEqual(evidence.outcome, ScanCanvasOutcome.SUPPORTED)
        assert evidence.axis_scales is not None
        self.assertTrue(
            math.isclose(
                evidence.axis_scales.width_axis_px_per_mm.minimum,
                500.0
                / (
                    50.0
                    * (1.0 + scan_configuration.physical_extent_tolerance_ratio)
                ),
            )
        )
        self.assertTrue(
            math.isclose(
                evidence.axis_scales.width_axis_px_per_mm.maximum,
                500.0
                / (
                    50.0
                    * (1.0 - scan_configuration.physical_extent_tolerance_ratio)
                ),
            )
        )
        self.assertEqual(
            tuple(item.name for item in fields(SourceLaneEvidence)),
            ("domain", "scan_canvas"),
        )

    def test_holder_catalog_is_not_filtered_by_requested_count(self) -> None:
        self.assertEqual(len(SCAN_CANVAS_PHYSICAL_SPECS), 7)
        self.assertIn(
            "120_wide_188_5",
            tuple(
                item.profile_id
                for item in scan_canvas_specs_for_format("120-67")
            ),
        )

    def test_holder_match_precedes_full_count_resolution(self) -> None:
        configuration = get_detection_configuration("120-67", "full")
        pixels = np.zeros((1000, 2972), dtype=np.uint8)
        workspace = prepare_detection_workspace(
            pixels,
            ImageProfile(
                shape=pixels.shape,
                dtype="uint8",
                axes="YX",
                photometric="MINISBLACK",
                compression="NONE",
                sample_format=None,
                bits_per_sample=(8,),
                samples_per_pixel=1,
                planar_config=None,
                resolution=None,
                resolution_unit=None,
                icc_profile=None,
                metadata=TiffMetadata(None, None, None, ()),
                orientation=orientation_mapping(1, 2972, 1000),
            ),
            "horizontal",
            configuration,
            None,
        )
        holder = workspace.source_core.matched_holder
        resolved = workspace.source_core.resolved_slot_count
        assert holder is not None and resolved is not None
        self.assertEqual(holder.profile.profile_id, "120_wide_188_5")
        self.assertEqual(holder.full_count, 2)
        self.assertEqual(resolved.output_count, 2)
        self.assertEqual(resolved.authority.value, "matched_holder_full_count")

    def test_competing_holder_counts_remain_unresolved(self) -> None:
        configuration = get_detection_configuration("120-67", "full")
        same_aspect_profiles = (
            ScanCanvasPhysicalSpec("120_standard", 60.0, 180.0),
            ScanCanvasPhysicalSpec("120_wide_188_5", 60.0, 180.0),
        )
        configuration = replace(
            configuration,
            scan_canvas=ScanCanvasDetectionConfiguration(same_aspect_profiles),
        )
        pixels = np.zeros((100, 300), dtype=np.uint8)
        workspace = prepare_detection_workspace(
            pixels,
            ImageProfile(
                shape=pixels.shape,
                dtype="uint8",
                axes="YX",
                photometric="MINISBLACK",
                compression="NONE",
                sample_format=None,
                bits_per_sample=(8,),
                samples_per_pixel=1,
                planar_config=None,
                resolution=None,
                resolution_unit=None,
                icc_profile=None,
                metadata=TiffMetadata(None, None, None, ()),
                orientation=orientation_mapping(1, 300, 100),
            ),
            "horizontal",
            configuration,
            None,
        )
        self.assertIsNone(workspace.source_core.matched_holder)
        self.assertIsNone(workspace.source_core.resolved_slot_count)
        self.assertIn(
            "holder_full_count_unresolved",
            workspace.source_core.incomplete_reasons,
        )
        candidate = choose_detection(workspace, configuration, None)
        self.assertEqual(
            candidate.gate.checks[0].gap,
            GateGap.HOLDER_FULL_COUNT_UNRESOLVED,
        )
        explicit = get_detection_configuration("120-67", "partial", 2)
        self.assertEqual(explicit.count_request.strip_mode, "partial")
        self.assertEqual(explicit.count_request.user_count, 2)
        self.assertIn(
            "120_wide_188_5",
            tuple(item.profile_id for item in explicit.scan_canvas.profiles),
        )

    def test_top_bottom_corridor_has_narrow_core_and_complete_halo(
        self,
    ) -> None:
        configuration = get_detection_configuration(
            "135",
            "full",
            None,
        )
        pixels = np.zeros((100, 720), dtype=np.uint8)
        workspace = prepare_detection_workspace(
            pixels,
            ImageProfile(
                shape=pixels.shape,
                dtype="uint8",
                axes="YX",
                photometric="MINISBLACK",
                compression="NONE",
                sample_format=None,
                bits_per_sample=(8,),
                samples_per_pixel=1,
                planar_config=None,
                resolution=None,
                resolution_unit=None,
                icc_profile=None,
                metadata=TiffMetadata(None, None, None, ()),
                orientation=orientation_mapping(
                    1,
                    pixels.shape[1],
                    pixels.shape[0],
                ),
            ),
            "horizontal",
            configuration,
            None,
        )
        lane = workspace.source_core.lanes[0]
        scan = lane.scan_canvas
        assert scan.axis_scales is not None
        aperture = configuration.physical_spec.frame_components[0]
        physical = frame_physical_pixel_intervals(
            aperture,
            scan.axis_scales.width_axis_px_per_mm,
            scan.axis_scales.height_axis_px_per_mm,
        )
        top, bottom = build_top_bottom_search_corridors(
            lane,
            layout="horizontal",
            aperture_pixels=physical,
        )
        self.assertEqual((top.role, bottom.role), (
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
        ))
        self.assertEqual(top.trace_positions_px, bottom.trace_positions_px)
        self.assertGreater(top.measurement_halo_px, 0)
        for corridor in (top, bottom):
            self.assertTrue(
                all(
                    measurement.minimum <= core.minimum
                    and measurement.maximum >= core.maximum
                    for core, measurement in zip(
                        corridor.core_intervals_px,
                        corridor.measurement_intervals_px,
                        strict=True,
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
