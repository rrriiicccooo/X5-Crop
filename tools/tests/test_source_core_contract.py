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
from x5crop.detection.evidence.content_occupancy import observe_content_occupancy
from x5crop.detection.evidence.content_occupancy_model import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.photo_geometry.corridors import (
    build_top_bottom_search_corridors,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
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
    Box,
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
from x5crop.image.gray import BaseGrayParameters, make_base_gray_u8


class PhysicalAuthorityContractTest(unittest.TestCase):
    def test_registered_gray_matches_full_array_reference(self) -> None:
        rng = np.random.default_rng(42)
        yxs = rng.integers(0, 65536, size=(257, 131, 3), dtype=np.uint16)
        params = BaseGrayParameters(maximum_percentile_samples=10_000)

        rgb = yxs.astype(np.float32)
        reference = (
            params.red_weight * rgb[..., 0]
            + params.green_weight * rgb[..., 1]
            + params.blue_weight * rgb[..., 2]
        )
        sampled = reference.reshape(-1)[::4]
        lo, hi = np.percentile(
            sampled,
            [params.low_percentile, params.high_percentile],
        )
        expected = np.clip(
            (reference - lo) * (255.0 / (hi - lo)),
            0,
            255,
        ).astype(np.uint8)

        self.assertTrue(
            np.array_equal(
                make_base_gray_u8(yxs, "YXS", "RGB", params),
                expected,
            )
        )
        self.assertTrue(
            np.array_equal(
                make_base_gray_u8(
                    np.moveaxis(yxs, -1, 0),
                    "SYX",
                    "RGB",
                    params,
                ),
                expected,
            )
        )

    def test_design_apertures_count_and_tolerance_are_typed(self) -> None:
        expected = {
            "135": ((36.0, 24.0), 6),
            "135-dual": ((36.0, 24.0), 12),
            "half": ((18.0, 24.0), 12),
            "xpan": ((65.0, 24.0), 3),
            "120-645": ((42.0, 56.0), 4),
            "120-66": ((56.0, 56.0), 3),
            "120-67": ((70.0, 56.0), 3),
        }
        for format_id, values in expected.items():
            spec = format_spec(format_id)
            self.assertEqual(
                ((spec.frame.frame_width_mm, spec.frame.frame_height_mm),),
                values[:-1],
            )
            self.assertEqual(spec.maximum_full_count, values[-1])
            self.assertFalse(hasattr(spec, "partial_mode_supported"))
            self.assertFalse(hasattr(spec, "aperture_tolerance"))
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
            0.0125,
        )
        self.assertEqual(
            FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
            0.0040,
        )

    def test_source_geometry_propagates_shared_scale_and_tolerance(
        self,
    ) -> None:
        spec = format_spec("135")
        geometry = SourceScanGeometry.create(
            spec.frame,
            width_scale_px_per_mm=PositiveInterval(10.0, 11.0),
            height_scale_px_per_mm=PositiveInterval(9.0, 10.0),
        )
        width = geometry.width_state.extent_projection_px()
        height = geometry.height_state.extent_projection_px()
        self.assertAlmostEqual(width.minimum, 355.5)
        self.assertAlmostEqual(width.maximum, 364.5)
        self.assertAlmostEqual(height.minimum, 239.04)
        self.assertAlmostEqual(height.maximum, 240.96)
        self.assertFalse(
            hasattr(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                "dimension_search_allowance_mm",
            )
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

    def test_scan_canvas_chooses_nearest_compatible_physical_profile(
        self,
    ) -> None:
        configuration = get_detection_configuration(
            "120-66",
            3,
        )
        evidence = observe_scan_canvas(
            9899,
            2797,
            "vertical",
            configuration.scan_canvas,
        )

        self.assertEqual(evidence.outcome, ScanCanvasOutcome.SUPPORTED)
        self.assertGreater(len(evidence.matches), 1)
        assert evidence.selected_profile is not None
        self.assertEqual(
            evidence.selected_profile.profile_id,
            "120_wide_224_5",
        )
        self.assertEqual(
            evidence.selected_profile.profile_id,
            min(
                evidence.matches,
                key=lambda item: (
                    item.aspect_error_ratio,
                    item.profile.profile_id,
                ),
            ).profile.profile_id,
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
        configuration = get_detection_configuration("120-67")
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
        )
        holder = workspace.source_core.matched_holder
        resolved = workspace.source_core.resolved_slot_count
        assert holder is not None and resolved is not None
        self.assertEqual(holder.profile.profile_id, "120_wide_188_5")
        self.assertEqual(holder.full_count, 2)
        self.assertEqual(resolved.output_count, 2)
        self.assertEqual(resolved.authority.value, "matched_holder_default_count")

    def test_dual_explicit_nondefault_count_is_typed_review_without_lane_guess(
        self,
    ) -> None:
        configuration = get_detection_configuration("135-dual", 10)
        pixels = np.zeros((634, 2320), dtype=np.uint8)
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
                orientation=orientation_mapping(1, 2320, 634),
            ),
            "horizontal",
            configuration,
        )
        resolved = workspace.source_core.resolved_slot_count
        assert resolved is not None
        self.assertEqual(resolved.output_count, 10)
        self.assertIn(
            "unsupported_dual_count",
            workspace.source_core.incomplete_reasons,
        )
        candidate = choose_detection(workspace, configuration)
        output_slot_check = next(
            item
            for item in candidate.gate.checks
            if item.code == "output_slot_count"
        )
        self.assertEqual(output_slot_check.gap, GateGap.UNSUPPORTED_DUAL_COUNT)
        self.assertIsNone(candidate.geometry.resolved_output_slots)
        self.assertEqual(candidate.geometry.lane_reconstructions, ())

    def test_content_occupancy_is_candidate_independent_and_deterministic(
        self,
    ) -> None:
        configuration = get_detection_configuration("135")
        pixels = np.zeros((100, 720), dtype=np.uint8)
        rows, columns = np.indices((60, 60))
        pixels[20:80, 300:360] = (
            ((rows // 3 + columns // 3) % 2) * 255
        ).astype(np.uint8)
        profile = ImageProfile(
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
            orientation=orientation_mapping(1, 720, 100),
        )
        first = prepare_detection_workspace(
            pixels,
            profile,
            "horizontal",
            configuration,
        ).source_core.content_occupancy[0]
        second = prepare_detection_workspace(
            pixels,
            profile,
            "horizontal",
            configuration,
        ).source_core.content_occupancy[0]
        self.assertTrue(first.observations)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(item.name for item in fields(ContentOccupancyObservation)),
            (
                "observation_id",
                "lane_id",
                "source_box",
                "source_cells",
                "reliability",
            ),
        )

    def test_content_measurement_does_not_promote_a_single_edge(self) -> None:
        pixels = np.zeros((85, 85), dtype=np.uint8)
        pixels[:, 51:] = 200
        observations = observe_content_occupancy(
            pixels,
            lane_id="lane:0",
            lane_work_box=Box(0, 0, 85, 85),
            layout="horizontal",
            long_step_px=17,
            cross_step_px=17,
        )
        self.assertFalse(observations.observations)
        self.assertEqual(observations.occupied_cell_count, 0)
        self.assertEqual(
            tuple(item.name for item in fields(ContentOccupancyObservationSet)),
            (
                "lane_id",
                "observations",
                "long_step_px",
                "cross_step_px",
                "long_sample_count",
                "cross_sample_count",
                "occupied_cell_count",
                "long_support_depth_px",
                "cross_support_depth_px",
            ),
        )

    def test_content_measurement_does_not_spread_texture_across_photo_edge(
        self,
    ) -> None:
        pixels = np.zeros((102, 102), dtype=np.uint8)
        rows, columns = np.indices((51, 102))
        pixels[51:, :] = (
            ((rows // 3 + columns // 3) % 2) * 255
        ).astype(np.uint8)
        observations = observe_content_occupancy(
            pixels,
            lane_id="lane:0",
            lane_work_box=Box(0, 0, 102, 102),
            layout="horizontal",
            long_step_px=17,
            cross_step_px=17,
        )
        self.assertTrue(observations.observations)
        self.assertTrue(
            all(
                cell.top >= 51
                for observation in observations.observations
                for cell in observation.source_cells
            )
        )

    def test_competing_holder_counts_remain_unresolved(self) -> None:
        configuration = get_detection_configuration("120-67")
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
        )
        self.assertIsNone(workspace.source_core.matched_holder)
        self.assertIsNone(workspace.source_core.resolved_slot_count)
        self.assertIn(
            "holder_full_count_unresolved",
            workspace.source_core.incomplete_reasons,
        )
        candidate = choose_detection(workspace, configuration)
        self.assertEqual(
            candidate.gate.checks[0].gap,
            GateGap.HOLDER_FULL_COUNT_UNRESOLVED,
        )
        explicit = get_detection_configuration("120-67", 2)
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
        )
        lane = workspace.source_core.lanes[0]
        scan = lane.scan_canvas
        assert scan.axis_scales is not None
        aperture = configuration.physical_spec.frame
        plan = compile_template_measurement_plan(
            format_spec=configuration.physical_spec,
            frame_spec=aperture,
            count=6,
            full_count=6,
            holder_full_count=6,
            lane_authority=lane.domain,
            layout="horizontal",
            scale_authority=scan.axis_scales,
        )
        top, bottom = build_top_bottom_search_corridors(
            lane,
            layout="horizontal",
            measurement_plan=plan,
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
