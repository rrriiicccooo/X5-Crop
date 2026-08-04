from __future__ import annotations

from dataclasses import replace
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x5crop.domain import Box
from x5crop.domain import (
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from x5crop.configuration.model import FrameCountRequest
from x5crop.detection.output_geometry import (
    output_transform_assessment,
    resolve_shared_strip_direction,
)
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryAxis,
    BoundaryRole,
    ClippedRequirement,
    FootprintSaturationFact,
    PhotoBoundaryObservation,
    SafeCropEnvelope,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.output import output_sampling_identity
from x5crop.formats import format_spec
from x5crop.export.crops import write_crops
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.geometry.convex import (
    axis_aligned_minkowski_guard,
    clip_convex_polygon_to_box,
    convex_hull,
    mapped_half_open_box,
)
from x5crop.image.transforms import sample_affine_roi
from x5crop.io.model import ImageProfile, TiffExtraTag, TiffMetadata
from x5crop.io.tiff import read_tiff
from x5crop.run_config import RunConfig


def _run_config(source: Path, output: Path, compression: str) -> RunConfig:
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        count_request=FrameCountRequest.from_user_input(
            format_spec("135"),
            "full",
            None,
        ),
        page=0,
        review_dir=None,
        copy_review_files=False,
        compression=compression,
        debug_analysis=False,
        diagnostics=False,
        overwrite=False,
        report=False,
        debug_errors=False,
        jobs=2,
    )


def _angle_observation(
    identity: str,
    angle_minimum: float,
    angle_maximum: float,
    *,
    role: BoundaryRole = BoundaryRole.TOP,
) -> PhotoBoundaryObservation:
    observation_id = ObservationId(identity)
    return PhotoBoundaryObservation(
        observation_id=observation_id,
        role=role,
        line=SourceCoordinateLine(
            normal_x=0.0,
            normal_y=1.0,
            offset_px=5.0,
            support_projection_px=FiniteInterval(0.0, 20.0),
            source_axis_long=BoundaryAxis.X,
        ),
        offset_interval_px=FiniteInterval(4.5, 5.5),
        fit_residual_px=0.1,
        angle_interval_degrees=FiniteInterval(
            angle_minimum,
            angle_maximum,
        ),
        trace_support_count=8,
        queried_trace_count=8,
        continuous_support_fraction=1.0,
        transition_ids=(ObservationId(f"{identity}:transition"),),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.BASE_GRAY,),
            description="test observed photo line",
        ),
    )


def _transform_assessment(
    observations: tuple[PhotoBoundaryObservation, ...],
):
    return output_transform_assessment(
        resolve_shared_strip_direction(observations),
        layout="horizontal",
        source_width=100,
        source_height=40,
    )


class AffineFoundationContractTest(unittest.TestCase):
    def test_continuous_footprint_primitives_are_single_path_and_ccw(
        self,
    ) -> None:
        hull = convex_hull(
            (
                (5.0, 4.0),
                (1.0, 1.0),
                (5.0, 1.0),
                (1.0, 4.0),
                (3.0, 1.0),
                (1.0, 1.0),
            )
        )
        self.assertEqual(
            hull,
            ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)),
        )
        guarded = axis_aligned_minkowski_guard(hull, 1.0)
        self.assertEqual(
            guarded,
            ((0.0, 0.0), (6.0, 0.0), (6.0, 5.0), (0.0, 5.0)),
        )
        clipped = clip_convex_polygon_to_box(guarded, Box(1, 1, 6, 5))
        self.assertEqual(
            clipped,
            ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0)),
        )

    def test_pixel_center_rounding_does_not_add_left_or_top_pixel(
        self,
    ) -> None:
        polygon = (
            (100.0, 20.0),
            (110.0, 20.0),
            (110.0, 30.0),
            (100.0, 30.0),
        )
        self.assertEqual(
            mapped_half_open_box(polygon, lambda x, y: (x, y)),
            Box(100, 20, 111, 31),
        )

    def test_continuous_polygon_maps_without_source_aabb_widening(self) -> None:
        transform = AffineCoordinateTransform.expanded_rotation(40, 30, 7.0)
        footprint = (
            (8.0, 15.0),
            (20.0, 7.0),
            (32.0, 15.0),
            (20.0, 23.0),
        )
        direct = mapped_half_open_box(footprint, transform.map_point)
        legacy = mapped_half_open_box(
            ((8.0, 7.0), (32.0, 7.0), (32.0, 23.0), (8.0, 23.0)),
            transform.map_point,
        )
        self.assertLess(direct.width * direct.height, legacy.width * legacy.height)

    def test_saturation_audit_does_not_change_sampling_equivalence(self) -> None:
        footprint = (
            (2.0, 2.0),
            (8.0, 2.0),
            (8.0, 6.0),
            (2.0, 6.0),
        )
        base = SafeCropEnvelope(
            geometry_id="geometry:test",
            lane_id="lane:0",
            lane_ordinal=1,
            placement_source_footprint=footprint,
            required_source_footprint=footprint,
            constrained_source_footprint=footprint,
            saturation_facts=(),
            sampling_authority_box=Box(0, 0, 20, 10),
            authority_profile_id="profile:test",
            mapped_output_box=Box(2, 2, 9, 7),
        )
        saturated = replace(
            base,
            saturation_facts=(
                FootprintSaturationFact(
                    AuthoritySide.LEFT,
                    (ClippedRequirement.VISIBLE_INTERPOLATION_GUARD,),
                ),
            ),
        )
        transform = AffineCoordinateTransform.identity(20, 10)
        self.assertEqual(
            output_sampling_identity(base, transform),
            output_sampling_identity(saturated, transform),
        )

    def test_expanded_rotation_has_frozen_extent_and_center_contract(self) -> None:
        width = 17
        height = 11
        guard = 1.0
        angle_degrees = 7.0
        transform = AffineCoordinateTransform.expanded_rotation(
            width,
            height,
            angle_degrees,
            guard_px=guard,
        )
        angle = math.radians(angle_degrees)
        source_center = ((width - 1) / 2.0, (height - 1) / 2.0)
        corners = (
            (0.0, 0.0),
            (float(width - 1), 0.0),
            (0.0, float(height - 1)),
            (float(width - 1), float(height - 1)),
        )
        rotated = tuple(
            (
                (x - source_center[0]) * math.cos(angle)
                - (y - source_center[1]) * math.sin(angle),
                (x - source_center[0]) * math.sin(angle)
                + (y - source_center[1]) * math.cos(angle),
            )
            for x, y in corners
        )
        expected_width = math.ceil(
            max(x for x, _ in rotated)
            - min(x for x, _ in rotated)
            + 2.0 * guard
        )
        expected_height = math.ceil(
            max(y for _, y in rotated)
            - min(y for _, y in rotated)
            + 2.0 * guard
        )
        self.assertEqual(transform.output_extent.width, expected_width)
        self.assertEqual(transform.output_extent.height, expected_height)
        mapped_center = transform.map_point(*source_center)
        self.assertAlmostEqual(
            mapped_center[0],
            (expected_width - 1) / 2.0,
        )
        self.assertAlmostEqual(
            mapped_center[1],
            (expected_height - 1) / 2.0,
        )

    def test_affine_round_trip_preserves_source_coordinates(self) -> None:
        transform = AffineCoordinateTransform.expanded_rotation(23, 19, -1.7)
        for source_point in (
            (0.0, 0.0),
            (22.0, 0.0),
            (0.0, 18.0),
            (22.0, 18.0),
            (7.25, 11.75),
        ):
            with self.subTest(source_point=source_point):
                recovered = transform.inverse_map_point(
                    *transform.map_point(*source_point)
                )
                self.assertAlmostEqual(recovered[0], source_point[0], places=12)
                self.assertAlmostEqual(recovered[1], source_point[1], places=12)

    def test_identity_is_exact_slice(self) -> None:
        array = np.arange(12 * 15 * 3, dtype=np.uint16).reshape(12, 15, 3)
        box = Box(3, 2, 11, 9)
        sampled = sample_affine_roi(
            array,
            "YXS",
            AffineCoordinateTransform.identity(15, 12),
            box,
            background_value=0,
            sampling_authority_box=Box(0, 0, 15, 12),
        )
        self.assertTrue(np.array_equal(sampled, array[2:9, 3:11]))

    def test_roi_equals_slice_of_test_owned_full_rotation(self) -> None:
        array = np.arange(9 * 13, dtype=np.uint16).reshape(9, 13)
        transform = AffineCoordinateTransform.expanded_rotation(13, 9, 7.0)
        full_box = Box(
            0,
            0,
            transform.output_extent.width,
            transform.output_extent.height,
        )
        full = sample_affine_roi(
            array,
            "YX",
            transform,
            full_box,
            background_value=65535,
            sampling_authority_box=Box(0, 0, 13, 9),
        )
        roi = Box(2, 1, transform.output_extent.width - 2, 7)
        direct = sample_affine_roi(
            array,
            "YX",
            transform,
            roi,
            background_value=65535,
            sampling_authority_box=Box(0, 0, 13, 9),
        )
        self.assertTrue(
            np.array_equal(
                direct,
                full[roi.top : roi.bottom, roi.left : roi.right],
            )
        )

    def test_expanded_canvas_preserves_bilinear_support_at_source_corners(
        self,
    ) -> None:
        array = np.ones((13, 21), dtype=np.uint16)
        transform = AffineCoordinateTransform.expanded_rotation(21, 13, 2.0)
        full = sample_affine_roi(
            array,
            "YX",
            transform,
            Box(
                0,
                0,
                transform.output_extent.width,
                transform.output_extent.height,
            ),
            background_value=0,
            sampling_authority_box=Box(0, 0, 21, 13),
        )
        for source_corner in (
            (0.0, 0.0),
            (20.0, 0.0),
            (0.0, 12.0),
            (20.0, 12.0),
        ):
            with self.subTest(source_corner=source_corner):
                mapped_x, mapped_y = transform.map_point(*source_corner)
                x0 = max(0, math.floor(mapped_x) - 1)
                x1 = min(full.shape[1], math.ceil(mapped_x) + 2)
                y0 = max(0, math.floor(mapped_y) - 1)
                y1 = min(full.shape[0], math.ceil(mapped_y) + 2)
                self.assertTrue(np.any(full[y0:y1, x0:x1] > 0))

    def test_bilinear_taps_outside_lane_use_background_without_edge_clip(
        self,
    ) -> None:
        source = np.zeros((4, 8), dtype=np.uint8)
        source[:, :4] = 20
        source[:, 4:] = 240
        transform = AffineCoordinateTransform(
            matrix=(
                (1.0, 0.0, 0.5),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            source_extent=AffineCoordinateTransform.identity(8, 4).source_extent,
            output_extent=AffineCoordinateTransform.identity(8, 4).output_extent,
        )
        sampled = sample_affine_roi(
            source,
            "YX",
            transform,
            Box(3, 1, 5, 3),
            background_value=100,
            sampling_authority_box=Box(0, 0, 4, 4),
        )
        self.assertEqual(int(sampled[0, 1]), 60)
        self.assertNotIn(240, sampled)

    def test_identity_requires_zero_in_every_observed_angle_interval(
        self,
    ) -> None:
        assessment = _transform_assessment(
            (
                _angle_observation("line:a", -0.2, 0.1),
                _angle_observation("line:b", -0.1, 0.3),
            ),
        )
        self.assertEqual(assessment.outcome, "identity")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(-0.1, 0.1),
        )

    def test_disjoint_observed_angles_make_transform_unavailable(self) -> None:
        assessment = _transform_assessment(
            (
                _angle_observation("line:a", -0.2, 0.1),
                _angle_observation("line:b", 0.2, 0.4),
            ),
        )
        self.assertEqual(assessment.outcome, "unavailable")
        self.assertEqual(
            assessment.named_gap,
            "shared_observed_rotation_interval_unavailable",
        )

    def test_nonzero_common_observed_angle_drives_rotation(self) -> None:
        assessment = _transform_assessment(
            (
                _angle_observation("line:a", 0.8, 1.2),
                _angle_observation(
                    "line:b",
                    0.9,
                    1.1,
                    role=BoundaryRole.BOTTOM,
                ),
            ),
        )
        self.assertEqual(assessment.outcome, "shared_rotation")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(0.9, 1.1),
        )
        assert assessment.applied_source_rotation_degrees is not None
        self.assertLess(assessment.applied_source_rotation_degrees, 0.0)

    def test_vertical_strip_uses_rotation_opposite_canonical_angle(self) -> None:
        direction = resolve_shared_strip_direction(
            (
                _angle_observation("line:vertical", -1.1, -0.9),
            )
        )
        assessment = output_transform_assessment(
            direction,
            layout="vertical",
            source_width=100,
            source_height=200,
        )

        self.assertEqual(assessment.outcome, "shared_rotation")
        assert assessment.applied_source_rotation_degrees is not None
        self.assertGreater(assessment.applied_source_rotation_degrees, 0.0)

    def test_nonorthogonal_start_end_does_not_widen_shared_deskew(
        self,
    ) -> None:
        assessment = _transform_assessment(
            (
                _angle_observation("line:top", -0.1, 0.2),
                _angle_observation(
                    "line:end",
                    2.0,
                    3.0,
                    role=BoundaryRole.END,
                ),
            ),
        )
        self.assertEqual(assessment.outcome, "identity")
        self.assertEqual(
            assessment.observed_angle_interval_degrees,
            FiniteInterval(-0.1, 0.2),
        )


class TiffFoundationContractTest(unittest.TestCase):
    def test_identity_export_preserves_pixels_and_profile(self) -> None:
        array = np.arange(10 * 14 * 3, dtype=np.uint16).reshape(10, 14, 3)
        source_profile = ImageProfile(
            shape=array.shape,
            dtype=str(array.dtype),
            axes="YXS",
            photometric="RGB",
            compression="NONE",
            sample_format=None,
            bits_per_sample=(16, 16, 16),
            samples_per_pixel=3,
            planar_config="CONTIG",
            resolution=(300.0, 240.0),
            resolution_unit=2,
            icc_profile=b"x5crop-test-icc",
            metadata=TiffMetadata(
                description="source-core metadata",
                datetime="2026:07:29 12:00:00",
                software="X5 Crop contract",
                extra_tags=(
                    TiffExtraTag(
                        code=269,
                        dtype="s",
                        count=0,
                        value="source-document",
                    ),
                ),
            ),
        )
        box = Box(2, 1, 12, 9)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tif"
            cases = (
                ("none", "NONE", "NONE"),
                ("same", "LZW", "LZW"),
            )
            for compression, source_compression, expected_compression in cases:
                with self.subTest(
                    compression=compression,
                    source_compression=source_compression,
                ):
                    output = root / compression
                    output.mkdir()
                    written = write_crops(
                        source,
                        array,
                        replace(
                            source_profile,
                            compression=source_compression,
                        ),
                        (box,),
                        (Box(0, 0, 14, 10),),
                        _run_config(source, output, compression),
                        AffineCoordinateTransform.identity(14, 10),
                        output,
                    )
                    self.assertEqual(len(written), 1)
                    actual, profile, warnings = read_tiff(Path(written[0]), 0)
                    self.assertEqual(warnings, [])
                    self.assertTrue(np.array_equal(actual, array[1:9, 2:12]))
                    self.assertEqual(profile.dtype, "uint16")
                    self.assertEqual(profile.axes, "YXS")
                    self.assertEqual(profile.photometric, "RGB")
                    self.assertEqual(
                        profile.compression.upper(),
                        expected_compression,
                    )
                    self.assertEqual(profile.resolution, (300.0, 240.0))
                    self.assertEqual(profile.icc_profile, b"x5crop-test-icc")
                    self.assertEqual(
                        profile.metadata.description,
                        "source-core metadata",
                    )
                    self.assertEqual(
                        profile.metadata.software,
                        "X5 Crop contract",
                    )
                    self.assertEqual(
                        profile.metadata.datetime,
                        "2026:07:29 12:00:00",
                    )
                    self.assertEqual(
                        profile.metadata.extra_tags,
                        source_profile.metadata.extra_tags,
                    )


if __name__ == "__main__":
    unittest.main()
