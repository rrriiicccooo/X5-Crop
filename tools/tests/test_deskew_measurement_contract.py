from __future__ import annotations

from dataclasses import fields, replace
import math
import unittest

import numpy as np

from tools.tests.photo_edge_support import photo_edge_pair_fixture
from x5crop.configuration.photo_edges import PhotoEdgeDetectionParameters
from x5crop.configuration.registry import get_detection_configuration
from x5crop.configuration.shared_short_axis import SharedShortAxisParameters
from x5crop.configuration.transform import TransformDetectionParameters
from x5crop.detection.evidence.photo_edges import (
    LocalTransitionState,
    PhotoEdgeCoordinateSpace,
    PhotoEdgeFact,
    PhotoEdgeObservation,
    PhotoEdgePairEvidence,
    PhotoEdgeSearchCorridor,
    PhotoEdgeSideStatistics,
    RegionSetRelation,
    map_photo_edge_pair_evidence,
)
from x5crop.detection.evidence.scan_canvas import (
    CanvasPixelScale,
    observe_scan_canvas,
)
from x5crop.detection.evidence.transform_geometry import TransformOutcome
from x5crop.detection.physical.photo_edge_detection import (
    observe_fixed_canvas_photo_edges,
    photo_edge_search_corridors,
)
from x5crop.detection.physical.photo_edge_geometry import (
    GeometryWorkBudget,
    _coordinate_seed_pairs,
    join_dual_lane_hypotheses,
    solve_fixed_canvas_photo_edge_geometry,
    solve_normal_region,
)
from x5crop.detection.physical.photo_edge_observation import (
    PhotoEdgeFragment,
    observe_photo_edge_fragments,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisOutcome,
    shared_short_axis_from_photo_edge_pair,
)
from x5crop.detection.workspace import _transform_geometry
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    EvidenceState,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.image.transforms import (
    BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
)


SOURCE_SHA256 = "0" * 64
CANVAS_WIDTH = 1_160
CANVAS_HEIGHT = 161
PHOTO_TOP = 20
PHOTO_BOTTOM = 140


def _provenance(identity: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(identity),
        dependencies=(MeasurementIdentity.GRAY_WORK,),
        description="current photo-edge contract fixture",
    )


def _side_statistics(value: float) -> PhotoEdgeSideStatistics:
    return PhotoEdgeSideStatistics(
        intensity_median_u8=value,
        intensity_mad_u8=1.0,
        texture_median_u8=2.0,
        gradient_median_u8=3.0,
    )


def _observation(
    identity: str,
    start: float,
    end: float,
    position: float,
    *,
    position_radius: float = 0.0,
    censored: bool = False,
) -> PhotoEdgeObservation:
    interval = PixelInterval(
        position - position_radius,
        position + position_radius,
    )
    return PhotoEdgeObservation(
        observation_id=ObservationId(identity),
        source_sha256=SOURCE_SHA256,
        long_axis_footprint=PixelInterval(start, end),
        short_axis_position_interval=interval,
        negative_side_statistics=_side_statistics(32.0),
        positive_side_statistics=_side_statistics(192.0),
        absolute_intensity_effect=160.0,
        absolute_texture_effect=4.0,
        absolute_gradient_effect=8.0,
        local_noise_u8=1.0,
        multiscale_position_interval=interval,
        state=LocalTransitionState.SUPPORTED,
        measurement_channels=("gradient", "intensity", "texture"),
        measurement_scales=(0.5, 1.0, 2.0),
        censored=censored,
        provenance=_provenance(identity),
    )


def _fragment(
    identity: str,
    positions: tuple[float, ...],
    *,
    start: float = 568.0,
    support_width: float = 8.0,
    censored: bool = False,
) -> PhotoEdgeFragment:
    observations = tuple(
        _observation(
            f"{identity}:observation:{index}",
            start + support_width * index,
            start + support_width * (index + 1),
            position,
            censored=censored,
        )
        for index, position in enumerate(positions)
    )
    return PhotoEdgeFragment(
        fragment_id=ObservationId(identity),
        observations=observations,
        censored=censored,
        provenance=_provenance(identity),
    )


def _local_strip(
    *,
    start: int = 568,
    end: int = 592,
    inside: int = 40,
    outside: int = 180,
) -> np.ndarray:
    gray = np.full(
        (CANVAS_HEIGHT, CANVAS_WIDTH),
        outside,
        dtype=np.uint8,
    )
    gray[PHOTO_TOP:PHOTO_BOTTOM, start:end] = inside
    return gray


def _fixed_canvas_evidence(
    gray: np.ndarray,
    parameters: PhotoEdgeDetectionParameters | None = None,
) -> PhotoEdgePairEvidence:
    configuration = get_detection_configuration("135", "full")
    scan_canvas = observe_scan_canvas(
        gray.shape[1],
        gray.shape[0],
        "horizontal",
        configuration.scan_canvas,
    )
    return observe_fixed_canvas_photo_edges(
        gray,
        scan_canvas,
        configuration.physical_spec.frame.frame_size_mm_options,
        parameters or configuration.photo_edges,
        source_sha256=SOURCE_SHA256,
    )


def _appearance(
    provenance: MeasurementProvenance,
) -> GrayAppearanceObservation:
    return GrayAppearanceObservation(
        intensity_median=64.0,
        intensity_mad=2.0,
        texture_median=2.0,
        gradient_median=4.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
        provenance=provenance,
    )


def _path(
    identity: str,
    intercept: float,
    slope: float,
    side: BoundarySide,
    *,
    extent: float = 1_000.0,
) -> GrayBoundaryPathObservation:
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(identity),
        dependencies=(MeasurementIdentity.GRAY_WORK,),
        description="source path used to construct a typed pair fixture",
    )
    positions = tuple(
        intercept + slope * coordinate
        for coordinate in (extent / 4.0, 3.0 * extent / 4.0)
    )
    outer = _appearance(provenance)
    inner = _appearance(provenance)
    lower, upper = (
        (outer, inner)
        if side == BoundarySide.TOP
        else (inner, outer)
    )
    return GrayBoundaryPathObservation(
        axis=BoundaryAxis.SHORT,
        kind=BoundaryKind.TONAL_TRANSITION,
        samples=(
            BoundaryPathSample(
                PixelInterval(0.0, extent / 2.0),
                PixelInterval.exact(positions[0]),
            ),
            BoundaryPathSample(
                PixelInterval(extent / 2.0, extent),
                PixelInterval.exact(positions[1]),
            ),
        ),
        lower_appearance=lower,
        upper_appearance=upper,
        provenance=provenance,
    )


class LocalPhotoEdgeObservationContractTest(unittest.TestCase):
    def test_observation_is_role_material_and_scene_agnostic(self) -> None:
        names = {field.name for field in fields(PhotoEdgeObservation)}
        self.assertEqual(
            set(LocalTransitionState),
            {
                LocalTransitionState.SUPPORTED,
                LocalTransitionState.NEUTRAL,
            },
        )
        self.assertTrue(
            {
                "negative_side_statistics",
                "positive_side_statistics",
                "absolute_intensity_effect",
                "absolute_texture_effect",
                "absolute_gradient_effect",
                "local_noise_u8",
                "multiscale_position_interval",
                "censored",
            }.issubset(names)
        )
        for forbidden in (
            "top",
            "bottom",
            "inner",
            "exterior",
            "material",
            "film_base",
            "sky",
            "black_scene",
            "positive_negative",
        ):
            self.assertFalse(any(forbidden in name for name in names))

    def test_intensity_polarity_reversal_preserves_identity(self) -> None:
        normal = _fixed_canvas_evidence(_local_strip())
        inverted = _fixed_canvas_evidence(255 - _local_strip())
        self.assertEqual(normal.state, EvidenceState.SUPPORTED)
        self.assertEqual(inverted.state, normal.state)
        self.assertEqual(
            tuple(
                fragment.canonical_observation_count
                for fragment in inverted.fragment_summaries
            ),
            tuple(
                fragment.canonical_observation_count
                for fragment in normal.fragment_summaries
            ),
        )
        self.assertEqual(
            inverted.physical_selection,
            normal.physical_selection,
        )

    def test_brightness_translation_preserves_identity(self) -> None:
        baseline = _fixed_canvas_evidence(
            _local_strip(inside=40, outside=160)
        )
        translated = _fixed_canvas_evidence(
            _local_strip(inside=70, outside=190)
        )
        self.assertEqual(baseline.state, EvidenceState.SUPPORTED)
        self.assertEqual(translated.state, baseline.state)
        self.assertEqual(
            translated.physical_selection,
            baseline.physical_selection,
        )

    def test_similar_pixels_are_neutral_not_contradicted(self) -> None:
        for intensity in (32, 224):
            measured = observe_photo_edge_fragments(
                np.full(
                    (CANVAS_HEIGHT, CANVAS_WIDTH),
                    intensity,
                    dtype=np.uint8,
                ),
                (),
                PhotoEdgeDetectionParameters(),
                source_sha256=SOURCE_SHA256,
                observation_prefix=f"neutral:{intensity}",
            )
            self.assertEqual(measured.fragments, ())
            self.assertEqual(measured.summary.supported_transition_count, 0)
            self.assertGreater(measured.summary.neutral_anchor_count, 0)

    def test_chunk_size_does_not_change_canonical_observations(self) -> None:
        gray = _local_strip(start=520, end=640)
        baseline = observe_photo_edge_fragments(
            gray,
            (),
            replace(
                PhotoEdgeDetectionParameters(),
                chunk_size_px=128,
            ),
            source_sha256=SOURCE_SHA256,
            observation_prefix="chunk",
        )
        alternate = observe_photo_edge_fragments(
            gray,
            (),
            replace(
                PhotoEdgeDetectionParameters(),
                chunk_size_px=256,
            ),
            source_sha256=SOURCE_SHA256,
            observation_prefix="chunk",
        )
        self.assertEqual(baseline.fragments, alternate.fragments)
        self.assertEqual(
            baseline.summary.canonical_observation_count,
            alternate.summary.canonical_observation_count,
        )

    def test_corridor_width_does_not_clip_measured_position(self) -> None:
        configuration = get_detection_configuration("135", "full")
        scan_canvas = observe_scan_canvas(
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            "horizontal",
            configuration.scan_canvas,
        )
        corridor = photo_edge_search_corridors(
            scan_canvas,
            configuration.physical_spec.frame.frame_size_mm_options,
            configuration.photo_edges,
        )[0]
        narrow = replace(
            corridor,
            maximum_center_offset_px=0.1,
            maximum_dimension_deviation_px=0.1,
            maximum_search_angle_degrees=0.01,
        )
        wide = replace(
            corridor,
            maximum_center_offset_px=10.0,
            maximum_dimension_deviation_px=10.0,
        )
        gray = _local_strip()
        measured = tuple(
            observe_photo_edge_fragments(
                gray,
                (candidate,),
                configuration.photo_edges,
                source_sha256=SOURCE_SHA256,
                observation_prefix="corridor",
            )
            for candidate in (narrow, wide)
        )
        self.assertEqual(measured[0].fragments, measured[1].fragments)

    def test_transition_touching_measurement_halo_is_censored(self) -> None:
        configuration = get_detection_configuration("135", "full")
        scan_canvas = observe_scan_canvas(
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            "horizontal",
            configuration.scan_canvas,
        )
        corridor = photo_edge_search_corridors(
            scan_canvas,
            configuration.physical_spec.frame.frame_size_mm_options,
            configuration.photo_edges,
        )[0]
        narrow = replace(
            corridor,
            nominal_top_px=20.0,
            nominal_bottom_px=140.0,
            maximum_center_offset_px=0.1,
            maximum_dimension_deviation_px=0.1,
            maximum_search_angle_degrees=0.01,
        )
        gray = np.full(
            (CANVAS_HEIGHT, CANVAS_WIDTH),
            180,
            dtype=np.uint8,
        )
        gray[13:133, 568:592] = 40
        measured = observe_photo_edge_fragments(
            gray,
            (narrow,),
            configuration.photo_edges,
            source_sha256=SOURCE_SHA256,
            observation_prefix="censored",
        )
        self.assertTrue(measured.fragments)
        self.assertTrue(all(fragment.censored for fragment in measured.fragments))
        self.assertEqual(
            measured.summary.censored_component_count,
            len(measured.fragments),
        )

    def test_multiscale_responses_canonicalize_to_one_observation_per_footprint(
        self,
    ) -> None:
        measured = observe_photo_edge_fragments(
            _local_strip(),
            (),
            PhotoEdgeDetectionParameters(),
            source_sha256=SOURCE_SHA256,
            observation_prefix="canonical",
        )
        self.assertEqual(len(measured.fragments), 2)
        self.assertTrue(
            all(len(fragment.observations) == 3 for fragment in measured.fragments)
        )
        self.assertTrue(
            all(
                len(observation.measurement_scales)
                == len(set(observation.measurement_scales))
                for fragment in measured.fragments
                for observation in fragment.observations
            )
        )

    def test_real_pixel_gap_splits_fragments_without_bridge(self) -> None:
        gray = _local_strip(start=480, end=520)
        gray[PHOTO_TOP:PHOTO_BOTTOM, 640:680] = 40
        measured = observe_photo_edge_fragments(
            gray,
            (),
            PhotoEdgeDetectionParameters(),
            source_sha256=SOURCE_SHA256,
            observation_prefix="gap",
        )
        top_fragments = tuple(
            fragment
            for fragment in measured.fragments
            if fragment.short_axis_position_interval.midpoint < 80.0
        )
        self.assertEqual(len(top_fragments), 2)
        self.assertLess(
            top_fragments[0].long_axis_footprint.maximum,
            top_fragments[1].long_axis_footprint.minimum,
        )

    def test_long_ridge_report_surface_is_compact(self) -> None:
        evidence = _fixed_canvas_evidence(
            _local_strip(start=30, end=1_130)
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertGreater(
            evidence.measurement_summary.canonical_observation_count,
            200,
        )
        self.assertLessEqual(len(evidence.audit_observations), 12)
        self.assertTrue(
            all(
                fragment.ordered_constraint_sha256
                for fragment in evidence.fragment_summaries
            )
        )


class JointPhotoEdgeGeometryContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.configuration = get_detection_configuration("135", "full")
        self.scan_canvas = observe_scan_canvas(
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            "horizontal",
            self.configuration.scan_canvas,
        )
        assert self.scan_canvas.pixel_scale is not None
        self.scale = self.scan_canvas.pixel_scale
        self.corridors = photo_edge_search_corridors(
            self.scan_canvas,
            self.configuration.physical_spec.frame.frame_size_mm_options,
            self.configuration.photo_edges,
        )

    def test_three_adjacent_nonoverlapping_footprints_can_support_pair(
        self,
    ) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("top", (20.0, 20.0, 20.0)),
                _fragment("bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="three",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(len(result.hypotheses), 1)
        hypothesis = result.hypotheses[0]
        self.assertEqual(hypothesis.state, EvidenceState.SUPPORTED)
        assert hypothesis.geometry is not None
        self.assertTrue(hypothesis.geometry.cells)
        self.assertTrue(
            all(
                cell.verified_witnesses
                for cell in hypothesis.geometry.cells
            )
        )

    def test_exactly_three_inconsistent_observations_are_unavailable(
        self,
    ) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("curved_top", (20.0, 26.0, 20.0)),
                _fragment("straight_bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="inconsistent",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(result.hypotheses, ())
        self.assertTrue(result.search_unavailable)

    def test_rectangle_intersection_semantics_retains_angle_uncertainty(
        self,
    ) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("rectangle_top", (20.0, 20.0, 20.0)),
                _fragment("rectangle_bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="rectangle",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        geometry = result.hypotheses[0].geometry
        assert geometry is not None
        self.assertGreater(geometry.pixel_slope_interval.width, 0.0)
        self.assertTrue(
            geometry.pixel_slope_interval.minimum
            < 0.0
            < geometry.pixel_slope_interval.maximum
        )

    def test_non_square_scale_converts_physical_to_pixel_angle(self) -> None:
        scale = CanvasPixelScale(10.0, 20.0, "x")
        long_extent = 1_000
        short_extent = 700
        physical_slope = 0.02
        pixel_slope = (
            physical_slope
            * scale.short_axis_px_per_mm
            / scale.long_axis_px_per_mm
        )
        vertical_height = (
            24.0
            * scale.short_axis_px_per_mm
            * math.sqrt(1.0 + physical_slope * physical_slope)
        )
        center = 0.5 * float(short_extent - 1)
        long_center = 0.5 * float(long_extent - 1)
        top_intercept = (
            center
            - pixel_slope * long_center
            - 0.5 * vertical_height
        )
        bottom_intercept = (
            center
            - pixel_slope * long_center
            + 0.5 * vertical_height
        )
        starts = (460.0, 480.0, 500.0)
        top = tuple(
            _observation(
                f"anisotropic_top:{index}",
                start,
                start + 8.0,
                top_intercept + pixel_slope * (start + 4.0),
                position_radius=0.25,
            )
            for index, start in enumerate(starts)
        )
        bottom = tuple(
            _observation(
                f"anisotropic_bottom:{index}",
                start,
                start + 8.0,
                bottom_intercept + pixel_slope * (start + 4.0),
                position_radius=0.25,
            )
            for index, start in enumerate(starts)
        )
        label = self.corridors[0].physical_label
        corridor = PhotoEdgeSearchCorridor(
            physical_label=label,
            work_long_axis_px=long_extent,
            work_short_axis_px=short_extent,
            nominal_top_px=top_intercept + pixel_slope * long_center,
            nominal_bottom_px=bottom_intercept + pixel_slope * long_center,
            maximum_center_offset_px=20.0,
            maximum_dimension_deviation_px=20.0,
            maximum_search_angle_degrees=4.0,
            measurement_halo_short_px=8,
            measurement_halo_long_px=4,
        )
        budget = GeometryWorkBudget(16_384, 4_096)
        geometry, state, _ = solve_normal_region(
            top,
            bottom,
            (corridor,),
            scale,
            self.configuration.photo_edges,
            budget,
            long_extent_px=long_extent,
            short_extent_px=short_extent,
        )
        self.assertEqual(state, EvidenceState.SUPPORTED)
        assert geometry is not None
        self.assertTrue(
            geometry.pixel_slope_interval.minimum
            <= pixel_slope
            <= geometry.pixel_slope_interval.maximum
        )
        self.assertAlmostEqual(
            math.degrees(math.atan(pixel_slope)),
            2.29061,
            places=5,
        )

    def test_normal_region_uses_explicit_four_way_relation(self) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("relation_top", (20.0, 20.0, 20.0)),
                _fragment("relation_bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="relation",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        geometry = result.hypotheses[0].geometry
        assert geometry is not None and geometry.normal_region is not None
        self.assertIn(
            geometry.normal_region.set_relation,
            {
                RegionSetRelation.DISJOINT,
                RegionSetRelation.SUBSET,
                RegionSetRelation.PARTIAL_INTERSECTION,
                RegionSetRelation.NUMERICALLY_INDETERMINATE,
            },
        )
        self.assertTrue(
            all(
                cell.canonical_signature
                and cell.verified_witnesses
                for cell in geometry.normal_region.cells
            )
        )

    def test_global_budget_exhaustion_is_unavailable(self) -> None:
        constrained = replace(
            self.configuration.photo_edges,
            geometry=replace(
                self.configuration.photo_edges.geometry,
                maximum_region_cells=1,
                maximum_consensus_states=8,
            ),
        )
        evidence = _fixed_canvas_evidence(
            _local_strip(start=500, end=660),
            constrained,
        )
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertIn(
            PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,
            evidence.facts,
        )

    def test_coordinate_seed_discovery_reaches_deep_counterparts(self) -> None:
        top_groups = tuple(
            (ObservationId(f"top:{index}"),)
            for index in range(2)
        )
        bottom_groups = tuple(
            (ObservationId(f"bottom:{index}"),)
            for index in range(4)
        )
        coordinates = {
            **{
                group: float(index)
                for index, group in enumerate(top_groups)
            },
            **{
                group: float(index + 7)
                for index, group in enumerate(bottom_groups)
            },
        }
        seeds, incomplete = _coordinate_seed_pairs(
            top_groups,
            bottom_groups,
            maximum_inspections=16,
            maximum_seeds=16,
            pair_is_possible=lambda top, bottom: (
                top == top_groups[0] and bottom == bottom_groups[0]
            ),
            top_discovery_coordinate=coordinates.__getitem__,
            bottom_discovery_coordinate=coordinates.__getitem__,
            top_group_order_key=lambda group: (
                coordinates[group],
            ),
            bottom_group_order_key=lambda group: (
                coordinates[group],
            ),
            paired_coordinate_sum=10.0,
            seed_order_key=lambda top, bottom: (
                top,
                bottom,
            ),
        )
        self.assertEqual(seeds, ((top_groups[0], bottom_groups[0]),))
        self.assertFalse(incomplete)

    def test_coordinate_seed_budget_never_claims_exhaustive_search(self) -> None:
        top = ((ObservationId("top"),),)
        bottom = tuple(
            (ObservationId(f"bottom:{index}"),)
            for index in range(4)
        )
        coordinates = {
            top[0]: 0.0,
            **{
                group: float(index)
                for index, group in enumerate(bottom)
            },
        }
        seeds, incomplete = _coordinate_seed_pairs(
            top,
            bottom,
            maximum_inspections=1,
            maximum_seeds=4,
            pair_is_possible=lambda _top, _bottom: True,
            top_discovery_coordinate=coordinates.__getitem__,
            bottom_discovery_coordinate=coordinates.__getitem__,
            top_group_order_key=None,
            bottom_group_order_key=None,
            paired_coordinate_sum=0.0,
            seed_order_key=None,
        )
        self.assertEqual(len(seeds), 1)
        self.assertTrue(incomplete)

    def test_fragment_order_does_not_change_canonical_region(self) -> None:
        fragments = (
            _fragment("ordered_top", (20.0, 20.0, 20.0)),
            _fragment("ordered_bottom", (140.0, 140.0, 140.0)),
        )
        results = tuple(
            solve_fixed_canvas_photo_edge_geometry(
                ordering,
                self.corridors,
                self.scale,
                self.configuration.photo_edges,
                observation_prefix="order",
                long_extent_px=CANVAS_WIDTH,
                short_extent_px=CANVAS_HEIGHT,
            )
            for ordering in (fragments, tuple(reversed(fragments)))
        )
        self.assertEqual(results[0].hypotheses, results[1].hypotheses)

    def test_conflicting_additions_create_both_maximal_branches(self) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("branch_top_a", (20.0, 20.0, 20.0)),
                _fragment("branch_top_b", (24.0, 24.0, 24.0)),
                _fragment("branch_bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="branches",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(len(result.hypotheses), 2)
        self.assertTrue(
            all(
                hypothesis.state == EvidenceState.SUPPORTED
                for hypothesis in result.hypotheses
            )
        )

    def test_contradicted_addition_does_not_hide_admissible_consensus(
        self,
    ) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment("correct_top", (20.0, 20.0, 20.0)),
                _fragment("wrong_top", (30.0, 30.0, 30.0)),
                _fragment("correct_bottom", (140.0, 140.0, 140.0)),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="admissible",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(len(result.hypotheses), 1)
        self.assertEqual(result.hypotheses[0].state, EvidenceState.SUPPORTED)
        self.assertEqual(
            result.hypotheses[0].top_fragment_ids,
            (ObservationId("correct_top"),),
        )

    def test_systematic_curvature_keeps_fragment_unavailable(self) -> None:
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                _fragment(
                    "curved_ridge",
                    (20.0, 22.0, 26.0, 26.0, 22.0, 20.0),
                ),
                _fragment(
                    "straight_ridge",
                    (140.0, 140.0, 140.0, 140.0, 140.0, 140.0),
                ),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="curve",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(result.hypotheses, ())
        self.assertTrue(result.search_unavailable)

    def test_censored_observation_does_not_poison_uncensored_fragment_support(
        self,
    ) -> None:
        original = _fragment(
            "mixed_top",
            (20.0, 20.0, 20.0, 20.0),
        )
        mixed = replace(
            original,
            observations=(
                replace(original.observations[0], censored=True),
                *original.observations[1:],
            ),
            censored=True,
        )
        result = solve_fixed_canvas_photo_edge_geometry(
            (
                mixed,
                _fragment(
                    "mixed_bottom",
                    (140.0, 140.0, 140.0),
                ),
            ),
            self.corridors,
            self.scale,
            self.configuration.photo_edges,
            observation_prefix="mixed_censoring",
            long_extent_px=CANVAS_WIDTH,
            short_extent_px=CANVAS_HEIGHT,
        )
        self.assertEqual(len(result.hypotheses), 1)
        self.assertEqual(result.hypotheses[0].state, EvidenceState.SUPPORTED)
        self.assertNotIn(
            original.observations[0].observation_id,
            {
                observation.observation_id
                for observation in result.audit_observations
            },
        )


class TransformAndSharedAxisConsumerContractTest(unittest.TestCase):
    def _transform(
        self,
        evidence: PhotoEdgePairEvidence,
        parameters: TransformDetectionParameters | None = None,
    ):
        return _transform_geometry(
            (evidence,),
            None,
            CANVAS_WIDTH,
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            "horizontal",
            parameters or TransformDetectionParameters(),
        )

    def test_pair_identity_can_succeed_before_transform(self) -> None:
        evidence = _fixed_canvas_evidence(_local_strip())
        transform = self._transform(evidence)
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            transform.outcome,
            TransformOutcome.ANGLE_ESTIMATION_UNAVAILABLE,
        )
        self.assertIsNone(transform.estimated_angle_degrees)

    def test_transform_can_succeed_before_shared_axis_projection(self) -> None:
        evidence = _fixed_canvas_evidence(
            _local_strip(start=180, end=980)
        )
        transform = self._transform(evidence)
        self.assertEqual(
            transform.outcome,
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        )
        mapped = map_photo_edge_pair_evidence(
            evidence,
            transform.coordinate_transform,
            "horizontal",
            transform.position_uncertainty_px,
        )
        plan = shared_short_axis_from_photo_edge_pair(
            mapped,
            transform,
            CANVAS_WIDTH,
            SharedShortAxisParameters(),
        )
        self.assertEqual(
            plan.outcome,
            SharedShortAxisOutcome.EXTRAPOLATION_UNCERTAINTY_TOO_LARGE,
        )
        self.assertIsNone(plan.span)

    def test_positive_and_negative_real_angles_apply_deskew(self) -> None:
        outcomes: list[float] = []
        for slope in (-0.01, 0.01):
            gray = np.full(
                (CANVAS_HEIGHT, CANVAS_WIDTH),
                180,
                dtype=np.uint8,
            )
            center = 0.5 * float(CANVAS_WIDTH - 1)
            for coordinate in range(30, CANVAS_WIDTH - 30):
                top = round(
                    PHOTO_TOP + slope * (float(coordinate) - center)
                )
                bottom = round(
                    PHOTO_BOTTOM + slope * (float(coordinate) - center)
                )
                gray[top:bottom, coordinate] = 40
            evidence = _fixed_canvas_evidence(gray)
            transform = self._transform(evidence)
            self.assertEqual(
                transform.outcome,
                TransformOutcome.DESKEW_APPLIED,
            )
            assert transform.estimated_angle_degrees is not None
            outcomes.append(transform.estimated_angle_degrees)
        self.assertLess(outcomes[0], 0.0)
        self.assertGreater(outcomes[1], 0.0)

    def test_angle_out_of_range_carries_no_failure_angle(self) -> None:
        pair = photo_edge_pair_fixture(
            _path("out_of_range_top", 20.0, 0.05, BoundarySide.TOP),
            _path(
                "out_of_range_bottom",
                140.0,
                0.05,
                BoundarySide.BOTTOM,
            ),
        )
        transform = self._transform(pair)
        self.assertEqual(
            transform.outcome,
            TransformOutcome.ANGLE_OUT_OF_RANGE,
        )
        self.assertIsNone(transform.estimated_angle_degrees)
        self.assertIsNone(transform.pixel_angle_interval_degrees)

    def test_expanded_mapping_adds_exact_interpolation_uncertainty(self) -> None:
        pair = photo_edge_pair_fixture(
            _path("mapped_top", 20.0, 0.01, BoundarySide.TOP),
            _path("mapped_bottom", 140.0, 0.01, BoundarySide.BOTTOM),
        )
        transform = AffineCoordinateTransform.expanded_rotation(
            1_000,
            200,
            -math.degrees(math.atan(0.01)),
        )
        mapped = map_photo_edge_pair_evidence(
            pair,
            transform,
            "horizontal",
            BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
        )
        geometry = mapped.selected_geometry
        assert geometry is not None
        self.assertEqual(
            geometry.interpolation_position_uncertainty_px,
            BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
        )
        self.assertEqual(
            mapped.coordinate_space,
            PhotoEdgeCoordinateSpace.MAPPED,
        )
        self.assertEqual(
            mapped.provenance.boundary_anchors,
            (pair.observation_id,),
        )
        self.assertIsNone(geometry.normal_region)
        self.assertEqual(
            tuple(
                observation.provenance.boundary_anchors
                for observation in mapped.audit_observations
            ),
            tuple(
                (observation.observation_id,)
                for observation in pair.audit_observations
            ),
        )

    def test_pixel_height_is_perpendicular_distance_between_lines(self) -> None:
        slope = 0.5
        pair = photo_edge_pair_fixture(
            _path("height_top", 20.0, slope, BoundarySide.TOP),
            _path("height_bottom", 140.0, slope, BoundarySide.BOTTOM),
        )
        geometry = pair.selected_geometry
        assert geometry is not None
        expected = 120.0 / math.sqrt(1.0 + slope * slope)
        self.assertAlmostEqual(geometry.photo_height_px.minimum, expected)
        self.assertAlmostEqual(geometry.photo_height_px.maximum, expected)

    def test_horizontal_and_vertical_mapping_follow_same_affine_chain(
        self,
    ) -> None:
        pair = photo_edge_pair_fixture(
            _path("chain_top", 20.0, 0.01, BoundarySide.TOP),
            _path("chain_bottom", 140.0, 0.01, BoundarySide.BOTTOM),
        )
        source_geometry = pair.selected_geometry
        assert source_geometry is not None
        source_witness = source_geometry.cells[0].verified_witnesses[0]
        for layout, width, height in (
            ("horizontal", 1_001, 200),
            ("vertical", 200, 1_001),
        ):
            transform = AffineCoordinateTransform.expanded_rotation(
                width,
                height,
                -1.0,
            )
            mapped = map_photo_edge_pair_evidence(
                pair,
                transform,
                layout,
                BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
            )
            mapped_geometry = mapped.selected_geometry
            assert mapped_geometry is not None
            mapped_witness = (
                mapped_geometry.cells[0].verified_witnesses[0]
            )
            for coordinate in (50.0, 500.0, 950.0):
                source_position = (
                    source_witness.pixel_slope * coordinate
                    + source_witness.top_intercept_px
                )
                source_x, source_y = (
                    (coordinate, source_position)
                    if layout == "horizontal"
                    else (source_position, coordinate)
                )
                mapped_x, mapped_y = transform.map_point(
                    source_x,
                    source_y,
                )
                mapped_long, mapped_short = (
                    (mapped_x, mapped_y)
                    if layout == "horizontal"
                    else (mapped_y, mapped_x)
                )
                self.assertAlmostEqual(
                    mapped_short,
                    (
                        mapped_witness.pixel_slope * mapped_long
                        + mapped_witness.top_intercept_px
                    ),
                    places=8,
                )


class DualLaneJointGeometryContractTest(unittest.TestCase):
    def _pair(
        self,
        prefix: str,
        height: float,
        slope: float = 0.01,
    ) -> PhotoEdgePairEvidence:
        return photo_edge_pair_fixture(
            _path(
                f"{prefix}:top",
                20.0,
                slope,
                BoundarySide.TOP,
            ),
            _path(
                f"{prefix}:bottom",
                20.0 + height,
                slope,
                BoundarySide.BOTTOM,
            ),
        )

    def test_joint_region_retains_shared_angle_and_height(self) -> None:
        first = self._pair("first", 120.0)
        second = self._pair("second", 120.0)
        joint = join_dual_lane_hypotheses(
            first.hypotheses,
            second.hypotheses,
        )
        self.assertEqual(joint.state, EvidenceState.SUPPORTED)
        self.assertIsNotNone(joint.selected_pair_ids)
        self.assertTrue(joint.cells)
        self.assertTrue(
            all(
                cell.perpendicular_height_px.minimum
                <= cell.verified_perpendicular_height_px
                <= cell.perpendicular_height_px.maximum
                for cell in joint.cells
            )
        )

    def test_joint_height_conflict_is_contradicted(self) -> None:
        first = self._pair("first_conflict", 120.0)
        second = self._pair("second_conflict", 130.0)
        joint = join_dual_lane_hypotheses(
            first.hypotheses,
            second.hypotheses,
        )
        self.assertEqual(joint.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            joint.facts,
            (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
        )


if __name__ == "__main__":
    unittest.main()
