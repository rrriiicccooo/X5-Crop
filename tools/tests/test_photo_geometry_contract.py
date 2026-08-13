from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.photo_geometry.boundary_fitting import (
    fit_format_bound_boundary_observation,
)
from x5crop.detection.photo_geometry.registered_measurement import (
    measure_registered_queries,
)
from x5crop.detection.photo_geometry.transition_tracking import (
    track_side_transition_regions,
)
from x5crop.detection.photo_geometry.sequence_edge_families import (
    merge_sequence_edge_families,
)
from x5crop.detection.photo_geometry.trace_support import (
    shared_independent_trace_support_count,
)
from x5crop.detection.photo_geometry.boundary_geometry import (
    canonical_boundary_line,
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
)
from x5crop.detection.photo_geometry.direction_proposals import (
    joint_chain_direction,
)
from x5crop.detection.photo_geometry.cross_conditioning import (
    conditioned_observation_direction,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    ProfileRun,
    SeparatorMaterialRegionObservation,
)
from x5crop.detection.photo_geometry.line_observations import (
    SideTransitionRegion,
)
from x5crop.detection.photo_geometry.profile_adapters import (
    cross_profile_from_regions,
)
from x5crop.detection.photo_geometry.separator_material import (
    repeated_dark_material_supported,
)
from x5crop.detection.photo_geometry.cross_pairing import (
    pair_cross_edge_families,
)
from x5crop.detection.photo_geometry.separator_observations import (
    build_format_separator_bands,
)
from x5crop.detection.photo_geometry.output_model import (
    DirectUseBudgetEdgeAssessment,
    ResolvedOutputSlots,
    SharedStripDirection,
)
from x5crop.detection.photo_geometry.fixed_frame_geometry import (
    correlated_fixed_width_intervals,
)
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.io.orientation import orientation_mapping


def _profile(shape: tuple[int, int]) -> ImageProfile:
    return ImageProfile(
        shape=shape,
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
        orientation=orientation_mapping(1, shape[1], shape[0]),
    )


def _candidate(pixels: np.ndarray):
    configuration = get_detection_configuration("135", "full", None)
    workspace = prepare_detection_workspace(
        pixels,
        _profile(tuple(int(value) for value in pixels.shape)),
        "horizontal",
        configuration,
        None,
    )
    return workspace, configuration, choose_detection(
        workspace,
        configuration,
    )


def _side_measurement_set(
    coordinates_by_trace: tuple[tuple[float, ...], ...],
    *,
    transition_half_width_px: float = 0.25,
) -> PhotoBoundaryMeasurementSet:
    traces = tuple(index * 10 for index in range(len(coordinates_by_trace)))
    query = PhotoBoundaryMeasurementQuery(
        query_id="query:side-tracking",
        registration_index=0,
        lane_id="lane:0",
        purpose=QueryPurpose.SEQUENCE_ANCHOR_TILE,
        boundary_axis=BoundaryAxis.X,
        trace_positions_px=traces,
        search_intervals_px=(FiniteInterval(0.0, 200.0),) * len(traces),
        transition_ownership_intervals_px=(FiniteInterval(0.0, 200.0),)
        * len(traces),
        expected_support_px=40.0,
        boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        measurement_halo_px=2,
        search_proposal_ids=("anchor-domain:test",),
    )
    transitions = []
    for trace_ordinal, (trace, coordinates) in enumerate(
        zip(traces, coordinates_by_trace, strict=True)
    ):
        for coordinate_ordinal, coordinate in enumerate(coordinates):
            identity = ObservationId(
                f"transition:{trace_ordinal}:{coordinate_ordinal}"
            )
            transitions.append(
                PhotoBoundaryTransition(
                    transition_id=identity,
                    query_id=query.query_id,
                    trace_ordinal=trace_ordinal,
                    trace_coordinate_px=trace,
                    canonical_coordinate_px=coordinate,
                    localization_interval_px=FiniteInterval(
                        coordinate - transition_half_width_px,
                        coordinate + transition_half_width_px,
                    ),
                    physical_position_interval_px=FiniteInterval(
                        coordinate - transition_half_width_px,
                        coordinate + transition_half_width_px,
                    ),
                    gradient_z=5.0,
                    tone_z=5.0,
                    texture_z=5.0,
                    left_tone_mean=10.0,
                    right_tone_mean=30.0,
                    left_texture_mean=1.0,
                    right_texture_mean=5.0,
                    polarity=1,
                    peak_width_px=1.0,
                    prominence=5.0,
                    local_noise=0.0,
                )
            )
    coordinate_count = len(traces) * 201
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=len(traces),
        completed_trace_count=len(traces),
        registered_coordinate_count=coordinate_count,
        completed_coordinate_count=coordinate_count,
        pixel_query_count=coordinate_count,
        streaming_block_count=1,
        peak_temporary_bytes=4096,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=tuple(transitions),
        coverage=coverage,
    )


class PhotoBoundaryMeasurementContractTest(unittest.TestCase):
    def test_duplicate_trace_fits_merge_before_role_generation(self) -> None:
        measurement = _side_measurement_set(((100.0,),) * 4)
        transitions = {
            str(item.transition_id): item for item in measurement.transitions
        }
        identities = tuple(item.transition_id for item in measurement.transitions)

        def run(name: str, selected: tuple[int, ...]) -> ProfileRun:
            chosen = tuple(identities[index] for index in selected)
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval(99.75, 100.25),
                transition_ids=chosen,
                trace_coordinates_px=tuple(
                    transitions[str(identity)].trace_coordinate_px
                    for identity in chosen
                ),
                role_hint=None,
                qualified_anchor_roles=(BoundaryRole.START,),
                support_fraction=len(chosen) / 4,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=10.0,
                pair_qualified=True,
            )

        profile = BasicAxisProfile(
            "sequence",
            200,
            (0, 10, 20, 30),
            (run("overlap:left", (0, 1, 2)), run("overlap:right", (1, 2, 3))),
        )
        merged = merge_sequence_edge_families(
            profile,
            transitions,
            reference_trace_px=15.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(len(merged.runs), 1)
        self.assertEqual(set(merged.runs[0].transition_ids), set(identities))

    def test_local_cross_segment_reaches_physical_family_merge(self) -> None:
        transition_id = ObservationId("cross:local")
        region = SideTransitionRegion(
            region_id="region:local",
            proposal_position_interval_px=FiniteInterval(99.0, 101.0),
            transition_ids=(transition_id,),
            trace_support_count=1,
            queried_trace_count=3,
            independent_support_region_count=1,
            continuous_support_fraction=0.1,
            fit_residual_px=0.0,
            mean_gradient_z=4.0,
            mean_tone_or_texture_z=4.0,
            left_background_preference_fraction=1.0,
            right_background_preference_fraction=0.0,
        )
        profile = cross_profile_from_regions(
            (region,),
            (),
            coordinate_count=200,
            transition_by_id={
                str(transition_id): SimpleNamespace(trace_coordinate_px=10)
            },
        )
        self.assertEqual(len(profile.runs), 1)
        self.assertTrue(profile.runs[0].pair_qualified)
        self.assertEqual(profile.runs[0].qualified_anchor_roles, ())

    def test_height_pair_uses_physical_direction_not_narrow_fit_overlap(
        self,
    ) -> None:
        def observation(role, name, fit_angle):
            return SimpleNamespace(
                observation_id=ObservationId(name),
                role=role,
                transition_ids=(
                    ObservationId(
                        "top:t" if role == BoundaryRole.TOP else "bottom:t"
                    ),
                ),
                line=SimpleNamespace(
                    support_projection_px=FiniteInterval(0.0, 100.0)
                ),
                angle_interval_degrees=FiniteInterval(-0.2, 0.2),
                fit_angle_interval_degrees=fit_angle,
            )

        top_run = ProfileRun(
            run_id="top",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("top:t"),),
            trace_coordinates_px=(0, 10, 90, 100),
            role_hint=BoundaryRole.TOP,
            qualified_anchor_roles=(BoundaryRole.TOP,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=1.0,
            pair_qualified=True,
        )
        bottom_run = ProfileRun(
            run_id="bottom",
            coordinate_interval_px=FiniteInterval.exact(340.0),
            transition_ids=(ObservationId("bottom:t"),),
            trace_coordinates_px=(0, 10, 90, 100),
            role_hint=BoundaryRole.BOTTOM,
            qualified_anchor_roles=(BoundaryRole.BOTTOM,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=1.0,
            pair_qualified=True,
        )
        lane = SimpleNamespace(
            height_axis=BoundaryAxis.Y,
            top_measurement_set=SimpleNamespace(
                query=SimpleNamespace(trace_positions_px=(0, 10, 90, 100))
            ),
            bottom_measurement_set=SimpleNamespace(
                query=SimpleNamespace(trace_positions_px=(0, 10, 90, 100))
            ),
        )
        height_state = SimpleNamespace(
            extent_projection_px=lambda: FiniteInterval.exact(240.0),
            retained_extent_budget_px=lambda _ratio: FiniteInterval.exact(8.0),
        )
        geometry = SimpleNamespace(
            height_state=height_state,
            frame_spec=SimpleNamespace(frame_spec_id="frame:test"),
        )
        result = pair_cross_edge_families(
            lane,
            geometry,
            (
                top_run,
                observation(
                    BoundaryRole.TOP,
                    "top:o",
                    FiniteInterval(-0.10, -0.05),
                ),
                FiniteInterval.exact(100.0),
            ),
            (
                bottom_run,
                observation(
                    BoundaryRole.BOTTOM,
                    "bottom:o",
                    FiniteInterval(0.05, 0.10),
                ),
                FiniteInterval.exact(100.0),
            ),
            FiniteInterval.exact(100.0),
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].direct_height_span_validated)

    def test_separator_material_requires_repeated_resolved_darkness(self) -> None:
        def region(index: int, minimum: float, maximum: float):
            return SeparatorMaterialRegionObservation(
                region_index=index,
                sample_count=2,
                darkness_contrast_interval=FiniteInterval(minimum, maximum),
                texture_contrast_interval=FiniteInterval.exact(0.0),
            )

        self.assertTrue(
            repeated_dark_material_supported(
                (region(0, 2.0, 4.0), region(2, 3.0, 5.0))
            )
        )
        self.assertFalse(
            repeated_dark_material_supported(
                (region(0, 2.0, 4.0), region(2, 0.0, 5.0))
            )
        )
        self.assertFalse(
            repeated_dark_material_supported(
                (region(0, 1.0, 4.0), region(2, 1.0, 5.0))
            )
        )

    def test_cross_edge_uses_joint_lane_direction_not_local_fit(self) -> None:
        direction = SharedStripDirection(
            direction_id="joint:test",
            selected_observation_ids=(ObservationId("edge:test"),),
            full_angle_interval_degrees=FiniteInterval(-0.10, 0.40),
            canonical_angle_degrees=0.22,
        )
        retained, canonical = conditioned_observation_direction(
            SimpleNamespace(
                fit_angle_interval_degrees=FiniteInterval(0.10, 0.15),
                angle_interval_degrees=FiniteInterval(0.00, 0.31),
            ),
            direction,
        )
        self.assertEqual(retained, FiniteInterval(0.00, 0.31))
        self.assertEqual(canonical, 0.22)

    def test_joint_direction_uses_both_axes_without_weighted_score(self) -> None:
        sequence_edges = tuple(
            SimpleNamespace(
                run_id=f"run:{index}",
                observation_id=ObservationId(f"sequence:{index}"),
                canonical_direction_degrees=value,
                fit_direction_interval_degrees=FiniteInterval(
                    value - 0.01,
                    value + 0.01,
                ),
                full_direction_interval_degrees=FiniteInterval(
                    value - 0.08,
                    value + 0.08,
                ),
            )
            for index, value in enumerate((0.18, 0.24, 0.26), start=1)
        )
        seed = SimpleNamespace(
            role_proposals=tuple(
                SimpleNamespace(run_id=edge.run_id)
                for edge in sequence_edges
            ),
            local_advance_proposals=(),
        )
        cross = SharedStripDirection(
            direction_id="cross:test",
            selected_observation_ids=(ObservationId("cross:edge"),),
            full_angle_interval_degrees=FiniteInterval(0.10, 0.30),
            canonical_angle_degrees=0.12,
        )
        joint = joint_chain_direction(
            SimpleNamespace(sequence_edges=sequence_edges),
            seed,
            cross,
        )
        self.assertAlmostEqual(joint.canonical_angle_degrees, 0.21)
        self.assertEqual(
            set(joint.selected_observation_ids),
            {
                ObservationId("cross:edge"),
                *(edge.observation_id for edge in sequence_edges),
            },
        )
        # The shared lane direction is the common feasible interval, not the
        # hull of every local edge direction.  Local bend may locate a boundary
        # but cannot widen the global deskew authority.
        self.assertAlmostEqual(
            joint.full_angle_interval_degrees.minimum,
            0.18,
        )
        self.assertAlmostEqual(
            joint.full_angle_interval_degrees.maximum,
            0.26,
        )

    def test_direct_cross_pair_owns_direction_after_sequence_validation(self) -> None:
        sequence_edges = tuple(
            SimpleNamespace(
                run_id=f"run:pair:{index}",
                observation_id=ObservationId(f"sequence:pair:{index}"),
                canonical_direction_degrees=value,
                fit_direction_interval_degrees=FiniteInterval(
                    value - 0.02,
                    value + 0.02,
                ),
                full_direction_interval_degrees=FiniteInterval(
                    value - 0.10,
                    value + 0.10,
                ),
            )
            for index, value in enumerate((0.19, 0.23), start=1)
        )
        seed = SimpleNamespace(
            role_proposals=tuple(
                SimpleNamespace(run_id=edge.run_id)
                for edge in sequence_edges
            ),
            local_advance_proposals=(),
        )
        cross = SharedStripDirection(
            direction_id="cross:direct-pair",
            selected_observation_ids=(
                ObservationId("cross:top"),
                ObservationId("cross:bottom"),
            ),
            full_angle_interval_degrees=FiniteInterval(0.10, 0.30),
            canonical_angle_degrees=0.20,
        )
        self.assertIs(
            joint_chain_direction(
                SimpleNamespace(sequence_edges=sequence_edges),
                seed,
                cross,
            ),
            cross,
        )

    def test_direct_pair_requires_repeated_shared_trace_regions(self) -> None:
        queried = (0, 10, 20, 30, 40, 50, 60)
        self.assertEqual(
            shared_independent_trace_support_count(
                queried,
                (0, 10, 20, 30),
                (30, 40, 50, 60),
            ),
            1,
        )
        self.assertEqual(
            shared_independent_trace_support_count(
                queried,
                (0, 10, 20, 40, 50, 60),
                (0, 10, 20, 40, 50, 60),
            ),
            3,
        )

    def test_separator_pairing_uses_material_not_gap_width(
        self,
    ) -> None:
        traces = (0, 50, 100)

        def profile_run(name: str, coordinate: float) -> ProfileRun:
            identity = ObservationId(f"transition:{name}")
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval.exact(coordinate),
                transition_ids=(identity,),
                trace_coordinates_px=traces,
                role_hint=None,
                qualified_anchor_roles=(),
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=1.0,
            )

        left_run = profile_run("left", 100.0)
        right_run = profile_run("right", 900.0)
        profile = BasicAxisProfile(
            "sequence",
            1000,
            traces,
            (left_run, right_run),
        )

        def edge(run: ProfileRun, polarity: int) -> BoundaryEdgeObservation:
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{run.run_id}"),
                run_id=run.run_id,
                coordinate_interval_px=run.coordinate_interval_px,
                transition_ids=run.transition_ids,
                trace_coordinates_px=traces,
                polarity=polarity,
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                canonical_direction_degrees=None,
                fit_direction_interval_degrees=None,
                full_direction_interval_degrees=None,
            )

        marker = mock.Mock()
        marker.observation_id = ObservationId("separator:wide")
        with mock.patch(
            "x5crop.detection.photo_geometry.separator_observations._separator_band_from_edges",
            return_value=marker,
        ) as builder:
            result = build_format_separator_bands(
                profile,
                (edge(left_run, -1), edge(right_run, 1)),
                {},
                mock.Mock(),
                BoundaryAxis.X,
            )

        self.assertEqual(result, (marker,))
        builder.assert_called_once()

    def test_polarity_ambiguous_edge_remains_an_observation(self) -> None:
        from x5crop.detection.photo_geometry.observations import (
            build_sequence_observations,
        )

        run = ProfileRun(
            run_id="mixed-polarity-edge",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("negative"), ObservationId("positive")),
            trace_coordinates_px=(0, 100),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=10.0,
        )
        profile = BasicAxisProfile("sequence", 200, (0, 100), (run,))
        transitions = {
            "negative": SimpleNamespace(
                polarity=-1,
                transition_id=ObservationId("negative"),
                trace_coordinate_px=0,
                coordinate_px=100.0,
                localization_interval_px=FiniteInterval(99.0, 101.0),
                physical_position_interval_px=FiniteInterval(99.0, 101.0),
                gradient_z=4.0,
                tone_z=4.0,
                texture_z=4.0,
            ),
            "positive": SimpleNamespace(
                polarity=1,
                transition_id=ObservationId("positive"),
                trace_coordinate_px=100,
                coordinate_px=100.0,
                localization_interval_px=FiniteInterval(99.0, 101.0),
                physical_position_interval_px=FiniteInterval(99.0, 101.0),
                gradient_z=4.0,
                tone_z=4.0,
                texture_z=4.0,
            ),
        }

        edges, bands = build_sequence_observations(
            profile,
            transitions,
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].polarity, 0)
        self.assertEqual(bands, ())

    def test_separator_material_can_span_an_internal_transition_peak(self) -> None:
        traces = (0, 50, 100)

        def run(name: str, coordinate: float) -> ProfileRun:
            identity = ObservationId(f"transition:{name}")
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval.exact(coordinate),
                transition_ids=(identity,),
                trace_coordinates_px=traces,
                role_hint=None,
                qualified_anchor_roles=(),
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=1.0,
            )

        runs = (
            run("outer-left", 100.0),
            run("inner-right", 150.0),
            run("inner-left", 160.0),
            run("outer-right", 220.0),
        )
        profile = BasicAxisProfile("sequence", 300, traces, runs)

        def edge(value: ProfileRun, polarity: int) -> BoundaryEdgeObservation:
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{value.run_id}"),
                run_id=value.run_id,
                coordinate_interval_px=value.coordinate_interval_px,
                transition_ids=value.transition_ids,
                trace_coordinates_px=traces,
                polarity=polarity,
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                canonical_direction_degrees=None,
                fit_direction_interval_degrees=None,
                full_direction_interval_degrees=None,
            )

        edges = (
            edge(runs[0], -1),
            edge(runs[1], 1),
            edge(runs[2], -1),
            edge(runs[3], 1),
        )
        markers = {}

        def material_builder(left, right, **_kwargs):
            is_outer = (
                left.run_id == "outer-left"
                and right.run_id == "outer-right"
            )
            marker = SimpleNamespace(
                observation_id=ObservationId(
                    f"separator:{left.run_id}:{right.run_id}"
                ),
                left_edge_observation_id=left.observation_id,
                right_edge_observation_id=right.observation_id,
                independent_support_region_count=3 if is_outer else 2,
                continuous_support_fraction=1.0,
                darkness_contrast_interval=FiniteInterval.exact(1.0),
                texture_contrast_interval=FiniteInterval.exact(1.0),
            )
            markers[(left.run_id, right.run_id)] = marker
            return marker

        with mock.patch(
            "x5crop.detection.photo_geometry.separator_observations._separator_band_from_edges",
            side_effect=material_builder,
        ):
            result = build_format_separator_bands(
                profile,
                edges,
                {},
                mock.Mock(),
                BoundaryAxis.X,
            )

        self.assertIn(("outer-left", "outer-right"), markers)
        self.assertIn(
            markers[("outer-left", "outer-right")],
            result,
        )

    def test_canonical_direction_keeps_rotation_equivalent_slope_sign(self) -> None:
        direction = SharedStripDirection(
            direction_id="direction:slope-sign",
            selected_observation_ids=(ObservationId("observation:slope-sign"),),
            full_angle_interval_degrees=FiniteInterval(-0.3, -0.2),
            canonical_angle_degrees=-0.25,
        )
        expected = np.tan(np.deg2rad(-0.25))

        for long_axis, cross_axis in (
            (BoundaryAxis.X, BoundaryAxis.Y),
            (BoundaryAxis.Y, BoundaryAxis.X),
        ):
            with self.subTest(long_axis=long_axis):
                self.assertAlmostEqual(
                    canonical_source_cross_axis_slope(direction, cross_axis),
                    expected,
                )
                self.assertAlmostEqual(
                    canonical_source_sequence_axis_slope(direction, long_axis),
                    -expected,
                )
                cross_line = canonical_boundary_line(
                    direction,
                    boundary_axis=cross_axis,
                    source_axis_long=long_axis,
                    trace_coordinate_px=100.0,
                    position_px=20.0,
                    support_projection_px=FiniteInterval(0.0, 200.0),
                )
                coordinate = (
                    (cross_line.offset_px - cross_line.normal_x * 150.0)
                    / cross_line.normal_y
                    if cross_axis == BoundaryAxis.Y
                    else (
                        cross_line.offset_px - cross_line.normal_y * 150.0
                    )
                    / cross_line.normal_x
                )
                self.assertAlmostEqual(
                    coordinate - 20.0,
                    expected * 50.0,
                )

    def test_vertical_strip_preserves_source_slope_sign(self) -> None:
        measurement_set = _side_measurement_set(
            tuple((10.0 - index * 0.1,) for index in range(7))
        )

        observation = fit_format_bound_boundary_observation(
            measurement_set,
            transition_ids=tuple(
                item.transition_id for item in measurement_set.transitions
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.Y,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertLess(observation.angle_interval_degrees.center, 0.0)

    def test_format_role_observation_propagates_only_robust_inliers(
        self,
    ) -> None:
        measurement_set = _side_measurement_set(
            (
                (10.0,),
                (10.0,),
                (10.0,),
                (40.0,),
                (10.0,),
                (10.0,),
                (10.0,),
            )
        )

        observation = fit_format_bound_boundary_observation(
            measurement_set,
            transition_ids=tuple(
                item.transition_id for item in measurement_set.transitions
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.Y,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.trace_support_count, 6)
        self.assertNotIn(
            ObservationId("transition:3:0"),
            observation.transition_ids,
        )

    def test_transition_width_expands_only_full_angle_safety(self) -> None:
        coordinates = tuple((10.0 + index * 0.1,) for index in range(7))
        narrow = fit_format_bound_boundary_observation(
            _side_measurement_set(
                coordinates,
                transition_half_width_px=0.25,
            ),
            transition_ids=tuple(
                ObservationId(f"transition:{index}:0")
                for index in range(7)
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        wide = fit_format_bound_boundary_observation(
            _side_measurement_set(
                coordinates,
                transition_half_width_px=4.0,
            ),
            transition_ids=tuple(
                ObservationId(f"transition:{index}:0")
                for index in range(7)
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(narrow)
        self.assertIsNotNone(wide)
        assert narrow is not None and wide is not None
        self.assertEqual(
            narrow.fit_angle_interval_degrees,
            wide.fit_angle_interval_degrees,
        )
        self.assertGreater(
            wide.angle_interval_degrees.width,
            narrow.angle_interval_degrees.width,
        )

    def test_measurement_spec_contains_only_production_values(self) -> None:
        spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
        self.assertEqual(spec.lattice_spacing_mm(12.0), 2.0)
        self.assertEqual(spec.lattice_spacing_mm(36.0), 3.0)
        self.assertEqual(spec.lattice_spacing_mm(120.0), 4.0)
        self.assertEqual(spec.local_window_mm, 0.25)
        self.assertEqual(spec.transition_gap_mm, 0.05)
        self.assertFalse(hasattr(spec, "maximum_transition_interval_mm"))
        self.assertFalse(hasattr(spec, "top_bottom_search_angle_degrees"))
        self.assertEqual(spec.maximum_measurable_line_angle_degrees, 4.0)
        self.assertEqual(spec.robust_loss_minimum_scale_mm, 0.05)
        self.assertFalse(hasattr(spec, "robust_loss_mad_multiplier"))
        self.assertEqual(spec.robust_fit_maximum_evaluations, 128)
        self.assertEqual(spec.robust_fit_tolerance, 1.0e-8)
        self.assertFalse(hasattr(spec, "huber_irls_rounds"))
        self.assertEqual(spec.maximum_streaming_block_pixels, 1_048_576)
        self.assertFalse(hasattr(spec, "nominal_calibration_sample_ids"))
        self.assertFalse(hasattr(spec, "stress_excluded_sample_id"))
        self.assertFalse(hasattr(spec, "contract_id"))

    def test_measurement_field_is_immutable_and_partial_query_is_unavailable(
        self,
    ) -> None:
        gray = np.zeros((20, 30), dtype=np.uint8)
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        self.assertFalse(field.source_gray.flags.writeable)
        query = PhotoBoundaryMeasurementQuery(
            query_id="query:test",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_TILE,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(2, 4, 6, 8),
            search_intervals_px=(FiniteInterval(0.0, 29.0),) * 4,
            transition_ownership_intervals_px=(
                FiniteInterval(0.0, 29.0),
            )
            * 4,
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            trace_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            measurement_halo_px=2,
            search_proposal_ids=("anchor-domain:test",),
        )
        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=4,
            completed_trace_count=3,
            registered_coordinate_count=120,
            completed_coordinate_count=90,
            pixel_query_count=90,
            streaming_block_count=1,
            peak_temporary_bytes=4096,
            complete=False,
        )
        measurement = PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            coverage=coverage,
        )
        self.assertEqual(measurement.state, EvidenceState.UNAVAILABLE)
        with self.assertRaises(ValueError):
            PhotoBoundaryMeasurementSet(
                query=query,
                state=EvidenceState.SUPPORTED,
                transitions=(),
                coverage=coverage,
            )

    def test_overlapping_query_halos_emit_transition_once(self) -> None:
        gray = np.zeros((4, 30), dtype=np.uint8)
        gray[:, 15:] = 255
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        common = dict(
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_TILE,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(0, 1, 2, 3),
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=10,
        )
        queries = (
            PhotoBoundaryMeasurementQuery(
                query_id="query:left",
                registration_index=0,
                search_intervals_px=(FiniteInterval(0.0, 20.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(0.0, 9.0),)
                * 4,
                search_proposal_ids=("tile:left",),
                **common,
            ),
            PhotoBoundaryMeasurementQuery(
                query_id="query:right",
                registration_index=1,
                search_intervals_px=(FiniteInterval(9.0, 29.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(10.0, 29.0),)
                * 4,
                search_proposal_ids=("tile:right",),
                **common,
            ),
        )
        measured = measure_registered_queries(field, queries)
        self.assertEqual(measured[0].transitions, ())
        self.assertEqual(
            {item.query_id for item in measured[1].transitions},
            {"query:right"},
        )

    def test_cross_corridor_preserves_opposite_physical_transitions_only(
        self,
    ) -> None:
        gray = np.full((40, 6), 200, dtype=np.uint8)
        gray[15:17, :] = 0
        field = PhotoBoundaryMeasurementField(gray, "horizontal")

        def query(purpose: QueryPurpose, registration_index: int):
            return PhotoBoundaryMeasurementQuery(
                query_id=f"query:{purpose.value}",
                registration_index=registration_index,
                lane_id="lane:0",
                purpose=purpose,
                boundary_axis=BoundaryAxis.Y,
                trace_positions_px=tuple(range(6)),
                search_intervals_px=(FiniteInterval(4.0, 34.0),) * 6,
                transition_ownership_intervals_px=(
                    FiniteInterval(4.0, 34.0),
                )
                * 6,
                expected_support_px=30.0,
                boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                measurement_halo_px=4,
                search_proposal_ids=(f"corridor:{purpose.value}",),
            )

        cross, sequence = measure_registered_queries(
            field,
            (
                query(QueryPurpose.TOP_CORRIDOR, 0),
                query(QueryPurpose.SEQUENCE_ANCHOR_TILE, 1),
            ),
        )

        cross_by_trace = {
            trace: tuple(
                item
                for item in cross.transitions
                if item.trace_coordinate_px == trace
            )
            for trace in range(6)
        }
        self.assertTrue(
            all(
                {item.polarity for item in values} == {-1, 1}
                for values in cross_by_trace.values()
            ),
            cross_by_trace,
        )
        self.assertTrue(
            all(
                len(
                    {
                        item.polarity
                        for item in sequence.transitions
                        if item.trace_coordinate_px == trace
                    }
                )
                <= 1
                for trace in range(6)
            )
        )

    def test_side_tracking_keeps_close_separator_sides_distinct(self) -> None:
        regions = track_side_transition_regions(
            (_side_measurement_set(((100.0, 104.0),) * 5),),
            reference_trace_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        self.assertEqual(len(regions), 2)
        self.assertNotEqual(regions[0].transition_ids, regions[1].transition_ids)

    def test_side_tracking_allows_one_missing_step_not_two(self) -> None:
        scale = PositiveInterval(10.0, 10.0)
        one_missing = _side_measurement_set(
            ((100.0,), (100.0,), (), (100.0,), (100.0,), (100.0,))
        )
        two_missing = _side_measurement_set(
            ((100.0,), (100.0,), (), (), (100.0,), (100.0,))
        )
        self.assertEqual(
            len(
                track_side_transition_regions(
                    (one_missing,),
                    reference_trace_px=25.0,
                    boundary_axis_scale_px_per_mm=scale,
                )
            ),
            1,
        )
        self.assertEqual(
            track_side_transition_regions(
                (two_missing,),
                reference_trace_px=25.0,
                boundary_axis_scale_px_per_mm=scale,
            ),
            (),
        )


class FixedFormatRuntimeContractTest(unittest.TestCase):
    def test_direct_start_constrains_inferred_end_through_shared_width(self) -> None:
        start, end = correlated_fixed_width_intervals(
            FiniteInterval(100.0, 102.0),
            FiniteInterval(130.0, 150.0),
            FiniteInterval(35.0, 36.0),
            start_direct=True,
            end_direct=False,
        )

        self.assertEqual(start, FiniteInterval(100.0, 102.0))
        self.assertEqual(end, FiniteInterval(135.0, 138.0))

    def test_direct_end_constrains_inferred_start_through_shared_width(self) -> None:
        start, end = correlated_fixed_width_intervals(
            FiniteInterval(80.0, 110.0),
            FiniteInterval(135.0, 137.0),
            FiniteInterval(35.0, 36.0),
            start_direct=False,
            end_direct=True,
        )

        self.assertEqual(start, FiniteInterval(99.0, 102.0))
        self.assertEqual(end, FiniteInterval(135.0, 137.0))

    def test_direct_use_limit_is_closed_and_has_no_positive_epsilon(self) -> None:
        exact = DirectUseBudgetEdgeAssessment(
            role=BoundaryRole.START,
            expansion_px=180.0,
            expansion_mm=1.8,
            limit_mm=1.8,
            within_limit=True,
            worst_placement_solution_id="placement:exact",
        )
        self.assertTrue(exact.within_limit)
        over = DirectUseBudgetEdgeAssessment(
            role=BoundaryRole.START,
            expansion_px=180.000000001,
            expansion_mm=1.80000000001,
            limit_mm=1.8,
            within_limit=False,
            worst_placement_solution_id="placement:over",
        )
        self.assertFalse(over.within_limit)

    def test_matched_holder_full_count_keeps_complete_query_coverage(self) -> None:
        pixels = np.zeros((100, 720), dtype=np.uint8)
        workspace, configuration, candidate = _candidate(pixels)
        self.assertEqual(configuration.count_request.strip_mode, "full")
        self.assertEqual(candidate.resolved_output_slots, ResolvedOutputSlots((6,)))
        lane = candidate.geometry.lane_reconstructions[0]
        tiles = tuple(
            sorted(lane.anchor_domain.tiles, key=lambda item: item.core_px.minimum)
        )
        self.assertEqual(tiles[0].core_px.minimum, 0.0)
        self.assertGreaterEqual(
            tiles[-1].core_px.maximum,
            lane.anchor_domain.long_axis_extent_px,
        )
        self.assertTrue(
            all(
                left.core_px.maximum == right.core_px.minimum
                for left, right in zip(tiles, tiles[1:])
            )
        )
        self.assertTrue(
            all(
                measurement.coverage.complete
                for measurement in lane.measurement_sets
            )
        )
        self.assertIs(
            workspace.boundary_measurement_field.source_gray,
            workspace.source_gray,
        )

    def test_zero_anchor_never_invents_blank_geometry(self) -> None:
        _workspace, _configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8)
        )
        self.assertFalse(candidate.gate.passed)
        self.assertEqual(candidate.geometry.safe_crop_envelopes, ())
        self.assertTrue(
            all(
                not lane.materialized_chains
                for lane in candidate.geometry.lane_reconstructions
            )
        )
        self.assertTrue(
            all(
                lane.lane_gap_model.lane_id == lane.lane_id
                for lane in candidate.geometry.lane_reconstructions
            )
        )


if __name__ == "__main__":
    unittest.main()
