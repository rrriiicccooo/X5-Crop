from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from x5crop.configuration.model import FrameCountMode
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.photo_geometry.measurement import (
    fit_template_bound_boundary_observation,
    measure_registered_queries,
    track_side_transition_regions,
)
from x5crop.detection.photo_geometry.boundary_geometry import (
    canonical_boundary_line,
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
)
from x5crop.detection.photo_geometry.template_first import (
    reference_role_transition_ids,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    DirectUseBudgetEdgeAssessment,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
    QueryPurpose,
    ResolvedOutputSlots,
    SharedStripDirection,
)
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
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
    configuration = get_detection_configuration("135", "partial", None)
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
        None,
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
                    coordinate_interval_px=FiniteInterval(
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
                    provenance=MeasurementProvenance(
                        root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
                        observation_id=identity,
                        dependencies=(MeasurementIdentity.BASE_GRAY,),
                        description="test side transition",
                    ),
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

        observation = fit_template_bound_boundary_observation(
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

    def test_template_bound_observation_propagates_only_robust_inliers(
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

        observation = fit_template_bound_boundary_observation(
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
        narrow = fit_template_bound_boundary_observation(
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
        wide = fit_template_bound_boundary_observation(
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

    def test_reference_role_binding_omits_equivalent_nearest_transitions(
        self,
    ) -> None:
        measurement_set = _side_measurement_set(
            (
                (10.0, 30.0),
                (10.0, 12.0),
                (9.0, 25.0),
                (11.0, 28.0),
                (10.5, 40.0),
            )
        )

        identities = reference_role_transition_ids(
            measurement_set,
            target_coordinate_px=11.0,
            equivalence_px=0.1,
        )

        self.assertEqual(len(identities), 4)
        self.assertNotIn(ObservationId("transition:1:0"), identities)
        self.assertNotIn(ObservationId("transition:1:1"), identities)
        self.assertEqual(
            {str(identity) for identity in identities},
            {
                "transition:0:0",
                "transition:2:0",
                "transition:3:0",
                "transition:4:0",
            },
        )

    def test_measurement_spec_contains_only_production_values(self) -> None:
        spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
        self.assertEqual(spec.lattice_spacing_mm(12.0), 2.0)
        self.assertEqual(spec.lattice_spacing_mm(36.0), 3.0)
        self.assertEqual(spec.lattice_spacing_mm(120.0), 4.0)
        self.assertEqual(spec.local_window_mm, 0.25)
        self.assertEqual(spec.transition_gap_mm, 0.05)
        self.assertEqual(spec.maximum_transition_interval_mm, 1.0)
        self.assertEqual(spec.huber_irls_rounds, 4)
        self.assertEqual(spec.maximum_streaming_block_pixels, 1_048_576)
        self.assertFalse(hasattr(spec, "nominal_calibration_sample_ids"))
        self.assertFalse(hasattr(spec, "stress_excluded_sample_id"))
        self.assertTrue(spec.contract_id.startswith("sha256:"))

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


class TemplateRuntimeContractTest(unittest.TestCase):
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

    def test_non_equivalent_directions_never_share_output_geometry(self) -> None:
        directions = (
            SharedStripDirection(
                direction_id="direction:a",
                selected_observation_ids=(ObservationId("top:a"),),
                full_angle_interval_degrees=FiniteInterval(-0.1, 0.1),
                canonical_angle_degrees=0.0,
            ),
            SharedStripDirection(
                direction_id="direction:b",
                selected_observation_ids=(ObservationId("top:b"),),
                full_angle_interval_degrees=FiniteInterval(0.9, 1.1),
                canonical_angle_degrees=1.0,
            ),
        )
        with mock.patch(
            "x5crop.detection.photo_geometry.detector."
            "shared_source_direction_classes",
            return_value=directions,
        ):
            _workspace, _configuration, candidate = _candidate(
                np.zeros((100, 720), dtype=np.uint8)
            )
        self.assertEqual(candidate.safe_crop_envelopes, ())
        self.assertEqual(
            candidate.geometry.direct_use_budget_assessments,
            (),
        )
        direction = candidate.geometry.assessment_facts[
            "shared_strip_direction"
        ]
        self.assertEqual(direction.gap, GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE)
        self.assertFalse(candidate.gate.passed)

    def test_capacity_auto_keeps_slots_and_complete_query_coverage(self) -> None:
        pixels = np.zeros((100, 720), dtype=np.uint8)
        workspace, configuration, candidate = _candidate(pixels)
        self.assertEqual(configuration.count_request.mode, FrameCountMode.AUTO)
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

    def test_zero_anchor_never_uses_grid_as_blank_geometry(self) -> None:
        _workspace, _configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8)
        )
        self.assertFalse(candidate.gate.passed)
        self.assertEqual(candidate.geometry.safe_crop_envelopes, ())
        self.assertTrue(
            all(
                not lane.retained_placements
                for lane in candidate.geometry.lane_reconstructions
            )
        )


if __name__ == "__main__":
    unittest.main()
