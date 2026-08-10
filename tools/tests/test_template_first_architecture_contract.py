from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest import mock

from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import (
    FRAME_DIMENSION_TOLERANCE_SPEC,
    FramePhysicalSpec,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    PhotoBoundaryObservation,
    SharedStripDirection,
    SideTransitionRegion,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.measurement import (
    provisional_cross_projection_interval,
)
from x5crop.detection.photo_geometry.template_first import (
    _cross_pair_seed_qualified,
    _template_bound_opposite_run,
    _retain_component_placements,
    build_template_sequence_seeds,
    local_advance_delta_from_observed_gap,
    local_advance_prefix,
    materialize_source_placements,
    merge_sampling_equivalent_direction_classes,
    provisional_height_templates,
    shared_source_direction_classes,
)
from x5crop.detection.photo_geometry.template_model import (
    ComponentTemplateProposal,
    EnhancedQueryRegistry,
    LocalAdvanceKind,
    LocalAdvanceRelation,
    TemplateLaneInput,
    TemplateWorkReceipt,
)
from x5crop.detection.photo_geometry.template_profiles import (
    BasicAxisProfile,
    PhaseGroupingWork,
    PhaseVote,
    ProfileRun,
    TemplatePhaseGroup,
    TemplateRole,
    build_phase_groups,
    cross_profile_from_regions,
    group_support_exclusion_authorized,
    ordered_template_roles,
)
from x5crop.detection.photo_geometry.source_geometry import (
    JointAxisGeometry,
    LaneGapModel,
    SourceFrameGeometry,
)


def _measurement_set_for_cross_edge(
    coordinate: float,
    *,
    polarity: int,
):
    transitions = tuple(
        SimpleNamespace(
            transition_id=ObservationId(f"cross:{coordinate}:{trace}"),
            trace_coordinate_px=trace,
            coordinate_px=coordinate,
            coordinate_interval_px=FiniteInterval(
                coordinate - 0.25,
                coordinate + 0.25,
            ),
            polarity=polarity,
            gradient_z=5.0,
            tone_z=5.0,
            texture_z=5.0,
        )
        for trace in (10, 20, 30, 40)
    )
    return SimpleNamespace(
        query=SimpleNamespace(trace_positions_px=(10, 20, 30, 40)),
        transitions=transitions,
    )


def _profile_run_for_measurement(
    measurement,
    *,
    role: BoundaryRole,
) -> ProfileRun:
    return ProfileRun(
        run_id=f"{role.value}-run",
        coordinate_interval_px=FiniteInterval(
            measurement.transitions[0].coordinate_px - 0.25,
            measurement.transitions[0].coordinate_px + 0.25,
        ),
        transition_ids=tuple(
            item.transition_id for item in measurement.transitions
        ),
        trace_coordinates_px=measurement.query.trace_positions_px,
        role_hint=role,
        qualified_anchor_roles=(role,),
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        evidence_strength=10.0,
        pair_qualified=True,
    )


def _cross_observation(
    transition_ids: tuple[ObservationId, ...],
    *,
    role: BoundaryRole,
    coordinate: float,
) -> PhotoBoundaryObservation:
    identity = ObservationId(f"{role.value}-observation")
    return PhotoBoundaryObservation(
        observation_id=identity,
        role=role,
        line=SourceCoordinateLine(
            normal_x=0.0,
            normal_y=1.0,
            offset_px=coordinate,
            support_projection_px=FiniteInterval(10.0, 40.0),
            source_axis_long=BoundaryAxis.X,
        ),
        offset_interval_px=FiniteInterval(
            coordinate - 0.25,
            coordinate + 0.25,
        ),
        fit_residual_px=0.0,
        angle_interval_degrees=FiniteInterval(-0.05, 0.05),
        trace_support_count=4,
        queried_trace_count=4,
        continuous_support_fraction=1.0,
        transition_ids=transition_ids,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
            observation_id=identity,
            dependencies=(MeasurementIdentity.BASE_GRAY,),
            description="synthetic cross edge",
        ),
    )


def _template_lane_for_cross_pair(
    top_measurement,
    bottom_measurement,
    top_run: ProfileRun,
) -> TemplateLaneInput:
    return TemplateLaneInput(
        lane_id="lane:0",
        output_slot_count=3,
        measurement_slot_count=3,
        width_axis=BoundaryAxis.X,
        height_axis=BoundaryAxis.Y,
        width_authority_px=FiniteInterval(0.0, 1199.0),
        height_authority_px=FiniteInterval(0.0, 319.0),
        width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        sequence_profile=BasicAxisProfile("sequence", 1200, (), ()),
        cross_profile=BasicAxisProfile(
            "cross",
            320,
            top_measurement.query.trace_positions_px,
            (top_run,),
        ),
        sequence_measurement_sets=(),
        top_measurement_set=top_measurement,
        bottom_measurement_set=bottom_measurement,
        transition_by_id={
            str(item.transition_id): item
            for item in (
                *top_measurement.transitions,
                *bottom_measurement.transitions,
            )
        },
    )


class TemplateFirstArchitectureContractTest(unittest.TestCase):
    def test_cross_pair_seed_does_not_claim_single_edge_authority(self) -> None:
        run = ProfileRun(
            run_id="pair-seed",
            coordinate_interval_px=FiniteInterval(39.0, 41.0),
            transition_ids=tuple(
                ObservationId(f"pair:{index}") for index in range(4)
            ),
            trace_coordinates_px=(10, 20, 30, 40),
            role_hint=BoundaryRole.TOP,
            qualified_anchor_roles=(),
            support_fraction=0.75,
            continuous_support_fraction=0.75,
            fit_residual_px=1.0,
            evidence_strength=10.0,
            pair_qualified=False,
        )

        self.assertTrue(_cross_pair_seed_qualified(run))
        self.assertFalse(run.anchor_qualified_for(BoundaryRole.TOP))

    def test_opposite_cross_edge_requires_opposite_transition_polarity(
        self,
    ) -> None:
        top_measurement = _measurement_set_for_cross_edge(40.0, polarity=-1)
        bottom_measurement = _measurement_set_for_cross_edge(
            280.0,
            polarity=1,
        )
        top_run = _profile_run_for_measurement(
            top_measurement,
            role=BoundaryRole.TOP,
        )
        top_observation = _cross_observation(
            top_run.transition_ids,
            role=BoundaryRole.TOP,
            coordinate=40.0,
        )
        lane = _template_lane_for_cross_pair(
            top_measurement,
            bottom_measurement,
            top_run,
        )
        geometry = SourceFrameGeometry.create(
            FramePhysicalSpec(
                "test",
                36.0,
                24.0,
                1.5,
            ),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        opposite = _template_bound_opposite_run(
            lane,
            geometry,
            top_run,
            top_observation,
        )

        self.assertIsNotNone(opposite)
        assert opposite is not None
        self.assertEqual(
            opposite.transition_ids,
            tuple(
                item.transition_id for item in bottom_measurement.transitions
            ),
        )

    def test_complete_pairs_exclude_compatible_singleton_phase(self) -> None:
        geometry = mock.Mock()
        authorized = tuple(
            mock.Mock(
                canonical_sequence=SimpleNamespace(
                    exclusion_authorized=True,
                    observed_role_count=2,
                    observed_opposite_pair_count=1,
                    local_advance_relations=(),
                ),
                source_frame_geometry=geometry,
            )
            for _index in range(2)
        )
        singleton = mock.Mock(
            canonical_sequence=SimpleNamespace(
                exclusion_authorized=False,
                observed_role_count=1,
                observed_opposite_pair_count=0,
                local_advance_relations=(
                    SimpleNamespace(kind=LocalAdvanceKind.NOMINAL),
                ),
            ),
            source_frame_geometry=geometry,
        )

        retained = _retain_component_placements((*authorized, singleton))

        self.assertEqual(retained, authorized)

    def test_strict_transition_superset_excludes_shifted_same_count_phase(
        self,
    ) -> None:
        geometry = mock.Mock()
        geometry.intersect_source_state.return_value = geometry
        component = SimpleNamespace(component_id="36x24mm")

        def placement(name: str, identities: tuple[str, ...]):
            return SimpleNamespace(
                placement_id=name,
                output_slot_count=3,
                component=component,
                canonical_sequence=SimpleNamespace(
                    exclusion_authorized=True,
                    safety_support_transition_ids=(
                        tuple(ObservationId(value) for value in identities),
                        (),
                        (),
                        (),
                        (),
                        (),
                    ),
                    observed_role_count=2,
                    observed_opposite_pair_count=1,
                    local_advance_relations=(),
                ),
                source_frame_geometry=geometry,
            )

        complete = placement("complete", ("a", "b", "c"))
        shifted = placement("shifted", ("a", "b"))
        unrelated = placement("unrelated", ("x", "y"))

        retained = _retain_component_placements(
            (complete, shifted, unrelated)
        )

        self.assertEqual(retained, (complete, unrelated))

    def test_basic_lane_does_not_consume_registered_role_enhancement(
        self,
    ) -> None:
        component = mock.sentinel.component
        lane = mock.Mock(components=(component,))
        placement = mock.Mock(
            sequence_placements=(mock.Mock(exclusion_authorized=True),)
        )
        direction = mock.sentinel.direction

        with mock.patch(
            "x5crop.detection.photo_geometry.template_first.replace",
            return_value=lane,
        ), mock.patch(
            "x5crop.detection.photo_geometry.template_first."
            "_refine_component_phase_groups",
            return_value=(component, 0),
        ), mock.patch(
            "x5crop.detection.photo_geometry.template_first."
            "materialize_lane_placements",
            return_value=(placement,),
        ), mock.patch(
            "x5crop.detection.photo_geometry.template_first."
            "_bind_registered_sequence_roles",
        ) as bind_registered:
            materialization = materialize_source_placements(
                (lane,),
                direction,
            )

        bind_registered.assert_not_called()
        self.assertEqual(materialization.placements_by_lane, ((placement,),))
        self.assertEqual(materialization.enhanced_query_counts_by_lane, (0,))

    def test_single_lane_source_consumes_one_lane_direction_owner(self) -> None:
        direction = SharedStripDirection(
            direction_id="lane-direction",
            selected_observation_ids=(
                ObservationId("top"),
                ObservationId("bottom"),
            ),
            full_angle_interval_degrees=FiniteInterval(0.05, 0.12),
            canonical_angle_degrees=0.08,
        )
        lane = mock.Mock(direction_classes=(direction,))

        self.assertEqual(shared_source_direction_classes((lane,)), (direction,))

    def test_one_reliable_cross_role_builds_complete_height_proposal(self) -> None:
        transition_ids = tuple(
            ObservationId(f"top:{index}") for index in range(4)
        )
        run = ProfileRun(
            run_id="top-run",
            coordinate_interval_px=FiniteInterval(39.0, 41.0),
            transition_ids=transition_ids,
            trace_coordinates_px=(10, 20, 30, 40),
            role_hint=BoundaryRole.TOP,
            qualified_anchor_roles=(BoundaryRole.TOP,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=8.0,
        )
        lane = TemplateLaneInput(
            lane_id="lane:0",
            output_slot_count=3,
            measurement_slot_count=3,
            width_axis=BoundaryAxis.X,
            height_axis=BoundaryAxis.Y,
            width_authority_px=FiniteInterval(0.0, 1199.0),
            height_authority_px=FiniteInterval(0.0, 299.0),
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            sequence_profile=BasicAxisProfile("sequence", 1200, (), ()),
            cross_profile=BasicAxisProfile(
                "cross",
                300,
                (10, 20, 30, 40),
                (run,),
            ),
            sequence_measurement_sets=(),
            top_measurement_set=mock.sentinel.top_measurement,
            bottom_measurement_set=mock.sentinel.bottom_measurement,
            transition_by_id={},
        )
        component = FramePhysicalSpec(
            "test",
            36.0,
            24.0,
            1.5,
        )
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        observation = PhotoBoundaryObservation(
            observation_id=ObservationId("top-line"),
            role=BoundaryRole.TOP,
            line=SourceCoordinateLine(
                normal_x=0.0,
                normal_y=1.0,
                offset_px=40.0,
                support_projection_px=FiniteInterval(10.0, 40.0),
                source_axis_long=BoundaryAxis.X,
            ),
            offset_interval_px=FiniteInterval(39.5, 40.5),
            fit_residual_px=0.1,
            angle_interval_degrees=FiniteInterval(-0.1, 0.1),
            trace_support_count=4,
            queried_trace_count=4,
            continuous_support_fraction=1.0,
            transition_ids=transition_ids,
            provenance=MeasurementProvenance(
                root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
                observation_id=ObservationId("top-line"),
                dependencies=(MeasurementIdentity.BASE_GRAY,),
                description="synthetic top anchor",
            ),
        )
        with mock.patch(
            "x5crop.detection.photo_geometry.template_first."
            "fit_template_bound_boundary_observation",
            return_value=observation,
        ), mock.patch(
            "x5crop.detection.photo_geometry.template_first."
            "_inlier_profile_run",
            return_value=run,
        ):
            templates = provisional_height_templates(lane, geometry)
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].observed_runs, (run,))
        self.assertEqual(templates[0].raw_observations, (observation,))

    def test_cross_anchor_uses_its_typed_trace_fraction_contract(self) -> None:
        transition_ids = tuple(
            ObservationId(f"cross:{index}") for index in range(5)
        )
        region = SideTransitionRegion(
            region_id="cross-region",
            proposal_position_interval_px=FiniteInterval(20.0, 21.0),
            transition_ids=transition_ids,
            trace_support_count=5,
            queried_trace_count=10,
            continuous_support_fraction=0.8,
            fit_residual_px=0.1,
            mean_gradient_z=5.0,
            mean_tone_or_texture_z=5.0,
            background_side_support_fraction=1.0,
            left_background_preference_fraction=1.0,
            right_background_preference_fraction=1.0,
        )
        profile = cross_profile_from_regions(
            (region,),
            (),
            coordinate_count=100,
            transition_by_id={
                str(identity): SimpleNamespace(trace_coordinate_px=index)
                for index, identity in enumerate(transition_ids)
            },
        )
        self.assertEqual(
            profile.runs[0].qualified_anchor_roles,
            (BoundaryRole.TOP,),
        )

    def test_source_geometry_consumes_the_single_tolerance_owner(self) -> None:
        component = FramePhysicalSpec(
            "test",
            36.0,
            24.0,
            1.5,
        )
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=PositiveInterval(10.0, 11.0),
            height_scale_px_per_mm=PositiveInterval(12.0, 13.0),
        )
        tolerance = FRAME_DIMENSION_TOLERANCE_SPEC
        self.assertEqual(
            geometry.width_state.factor_authority,
            PositiveInterval(
                1.0 - tolerance.frame_width_tolerance_ratio,
                1.0 + tolerance.frame_width_tolerance_ratio,
            ),
        )
        self.assertEqual(
            geometry.height_state.factor_authority,
            PositiveInterval(
                1.0 - tolerance.frame_height_tolerance_ratio,
                1.0 + tolerance.frame_height_tolerance_ratio,
            ),
        )

    def test_group_supported_local_delta_moves_phase_once(self) -> None:
        component = FramePhysicalSpec(
            "test",
            36.0,
            24.0,
            1.5,
        )
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            height_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        roles = ordered_template_roles(3)

        def vote(role_index: int, phase: FiniteInterval) -> PhaseVote:
            role = roles[role_index]
            return PhaseVote(
                vote_id=f"vote:{role_index}",
                run_id=f"run:{role_index}",
                role=role,
                phase_interval_px=phase,
                transition_ids=(ObservationId(f"transition:{role_index}"),),
                template_coordinate_px=(
                    role.lane_ordinal - 1
                ) * 375.0 + (360.0 if role.role == BoundaryRole.END else 0.0),
            )

        upstream_votes = (vote(0, FiniteInterval(99.0, 101.0)), vote(1, FiniteInterval(99.0, 101.0)))
        downstream_votes = tuple(
            vote(index, FiniteInterval(109.0, 111.0))
            for index in (2, 3, 4, 5)
        )
        groups = (
            TemplatePhaseGroup(
                "upstream",
                FiniteInterval(99.0, 101.0),
                upstream_votes,
                (),
                True,
            ),
            TemplatePhaseGroup(
                "downstream",
                FiniteInterval(109.0, 111.0),
                downstream_votes,
                (),
                True,
            ),
        )
        proposal = ComponentTemplateProposal(
            component=component,
            initial_source_geometry=geometry,
            roles=roles,
            phase_votes=tuple((*upstream_votes, *downstream_votes)),
            phase_groups=groups,
            enhanced_phase_queries=(),
            registered_sequence_role_queries=(),
            height_templates=(),
            grouping_work=PhaseGroupingWork(0, 0),
        )
        seed = next(
            item
            for item in build_template_sequence_seeds(proposal)
            if item.phase_group_ids == ("upstream", "downstream")
        )
        self.assertEqual(
            seed.local_advance_relations[0].delta_interval_px,
            FiniteInterval(8.0, 12.0),
        )
        self.assertEqual(
            local_advance_prefix(seed.local_advance_relations, lane_ordinal=2)[0],
            FiniteInterval(8.0, 12.0),
        )
        self.assertEqual(
            local_advance_prefix(seed.local_advance_relations, lane_ordinal=3)[0],
            FiniteInterval(8.0, 12.0),
        )

    def test_only_sampling_equivalent_direction_classes_merge(self) -> None:
        directions = (
            SharedStripDirection(
                direction_id="zero-a",
                selected_observation_ids=(ObservationId("a"),),
                full_angle_interval_degrees=FiniteInterval(-0.2, 0.1),
                canonical_angle_degrees=0.0,
            ),
            SharedStripDirection(
                direction_id="zero-b",
                selected_observation_ids=(ObservationId("b"),),
                full_angle_interval_degrees=FiniteInterval(-0.1, 0.3),
                canonical_angle_degrees=0.0,
            ),
            SharedStripDirection(
                direction_id="rotated",
                selected_observation_ids=(ObservationId("c"),),
                full_angle_interval_degrees=FiniteInterval(0.9, 1.1),
                canonical_angle_degrees=1.0,
            ),
        )
        merged = merge_sampling_equivalent_direction_classes(directions)
        self.assertEqual(len(merged), 2)
        zero = next(item for item in merged if item.canonical_angle_degrees == 0.0)
        self.assertEqual(
            zero.selected_observation_ids,
            (ObservationId("a"), ObservationId("b")),
        )
        self.assertEqual(
            zero.full_angle_interval_degrees,
            FiniteInterval(-0.2, 0.3),
        )

    def test_group_support_requires_spatial_separation_or_opposite_pair(self) -> None:
        transitions = (
            (ObservationId("left"),),
            (ObservationId("right"),),
        )
        self.assertFalse(
            group_support_exclusion_authorized(
                role_coordinates_px=(100.0, 104.0),
                role_identities=(
                    (1, BoundaryRole.START),
                    (2, BoundaryRole.START),
                ),
                transition_id_sets=transitions,
                frame_width_lower_px=900.0,
            )
        )
        self.assertTrue(
            group_support_exclusion_authorized(
                role_coordinates_px=(100.0, 1000.0),
                role_identities=(
                    (1, BoundaryRole.START),
                    (2, BoundaryRole.START),
                ),
                transition_id_sets=transitions,
                frame_width_lower_px=900.0,
            )
        )
        self.assertTrue(
            group_support_exclusion_authorized(
                role_coordinates_px=(100.0, 104.0),
                role_identities=(
                    (1, BoundaryRole.START),
                    (1, BoundaryRole.END),
                ),
                transition_id_sets=transitions,
                frame_width_lower_px=900.0,
            )
        )

    def test_group_support_cannot_mix_independence_and_distance_pairs(self) -> None:
        self.assertFalse(
            group_support_exclusion_authorized(
                role_coordinates_px=(0.0, 1000.0, 1.0),
                role_identities=(
                    (1, BoundaryRole.START),
                    (2, BoundaryRole.START),
                    (3, BoundaryRole.START),
                ),
                transition_id_sets=(
                    (ObservationId("left"),),
                    (ObservationId("left"), ObservationId("right")),
                    (ObservationId("right"),),
                ),
                frame_width_lower_px=900.0,
            )
        )

    def test_provisional_cross_projection_is_monotone_in_angle_allowance(self) -> None:
        narrow = provisional_cross_projection_interval(
            FiniteInterval(40.0, 41.0),
            trace_coordinate_px=500.0,
            reference_trace_px=100.0,
            maximum_angle_degrees=1.0,
            numeric_uncertainty_px=0.5,
        )
        wide = provisional_cross_projection_interval(
            FiniteInterval(40.0, 41.0),
            trace_coordinate_px=500.0,
            reference_trace_px=100.0,
            maximum_angle_degrees=4.0,
            numeric_uncertainty_px=0.5,
        )
        self.assertLessEqual(wide.minimum, narrow.minimum)
        self.assertGreaterEqual(wide.maximum, narrow.maximum)

    def test_cross_profile_preserves_trace_runs_instead_of_lane_average(self) -> None:
        profile = BasicAxisProfile(
            axis_name="cross",
            coordinate_count=200,
            trace_coordinates_px=(10, 20),
            runs=(
                ProfileRun(
                    run_id="r1",
                    coordinate_interval_px=FiniteInterval(40.0, 41.0),
                    transition_ids=(ObservationId("a"),),
                    trace_coordinates_px=(10,),
                    role_hint=BoundaryRole.TOP,
                    qualified_anchor_roles=(BoundaryRole.TOP,),
                    support_fraction=1.0,
                    continuous_support_fraction=1.0,
                    fit_residual_px=0.0,
                    evidence_strength=6.0,
                ),
                ProfileRun(
                    run_id="r2",
                    coordinate_interval_px=FiniteInterval(60.0, 61.0),
                    transition_ids=(ObservationId("b"),),
                    trace_coordinates_px=(20,),
                    role_hint=BoundaryRole.TOP,
                    qualified_anchor_roles=(BoundaryRole.TOP,),
                    support_fraction=1.0,
                    continuous_support_fraction=1.0,
                    fit_residual_px=0.0,
                    evidence_strength=6.0,
                ),
            ),
        )
        self.assertEqual(profile.runs_at_trace(10)[0].run_id, "r1")
        self.assertEqual(profile.runs_at_trace(20)[0].run_id, "r2")
        self.assertEqual(len(profile.runs), 2)

    def test_sequence_anchor_qualification_is_role_specific(self) -> None:
        run = ProfileRun(
            run_id="sequence-role-specific",
            coordinate_interval_px=FiniteInterval(40.0, 41.0),
            transition_ids=(ObservationId("sequence"),),
            trace_coordinates_px=(10,),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=6.0,
        )
        self.assertTrue(run.anchor_qualified_for(BoundaryRole.START))
        self.assertFalse(run.anchor_qualified_for(BoundaryRole.END))

    def test_joint_geometry_keeps_factor_and_scale_correlated(self) -> None:
        state = JointAxisGeometry.create(
            axis_name="width",
            design_extent_mm=36.0,
            scale_interval_px_per_mm=PositiveInterval(95.0, 105.0),
            factor_interval=PositiveInterval(0.9875, 1.0125),
        ).intersect_observed_extent(
            FiniteInterval(3554.0, 3556.0),
            observation_ids=(ObservationId("pair"),),
        )
        scale = state.feasible_scale_interval()
        extent = state.extent_projection_px()
        factor = state.factor_projection()
        self.assertGreaterEqual(scale.minimum, 95.0)
        self.assertLessEqual(scale.maximum, 105.0)
        self.assertLessEqual(extent.minimum, 3554.0)
        self.assertGreaterEqual(extent.maximum, 3556.0)
        self.assertGreaterEqual(factor.minimum, 0.9875)
        self.assertLessEqual(factor.maximum, 1.0125)
        for s, q in state.vertices:
            self.assertGreaterEqual(q, 0.9875 * s - 1.0e-9)
            self.assertLessEqual(q, 1.0125 * s + 1.0e-9)

    def test_lane_gap_requires_two_compatible_direct_pitch_segments(self) -> None:
        state = JointAxisGeometry.create(
            axis_name="width",
            design_extent_mm=36.0,
            scale_interval_px_per_mm=PositiveInterval(100.0, 100.0),
            factor_interval=PositiveInterval(1.0, 1.0),
        )
        gap = LaneGapModel.from_edge_families(
            state,
            lane_id="lane:0",
            edge_families=(
                (
                    (FiniteInterval.exact(0.0), (ObservationId("edge:0"),)),
                    (FiniteInterval.exact(3800.0), (ObservationId("edge:1"),)),
                    (FiniteInterval.exact(7600.0), (ObservationId("edge:2"),)),
                ),
            ),
            format_gap_prior_mm=2.0,
        )
        self.assertEqual(gap.state, EvidenceState.SUPPORTED)
        self.assertEqual(gap.gap_interval_px, FiniteInterval.exact(200.0))
        self.assertEqual(
            gap.placement_pitch_interval_px,
            FiniteInterval.exact(3800.0),
        )
        second_lane = LaneGapModel.from_edge_families(
            state,
            lane_id="lane:1",
            edge_families=(
                (
                    (FiniteInterval.exact(0.0), (ObservationId("edge:3"),)),
                    (FiniteInterval.exact(3800.0), (ObservationId("edge:4"),)),
                    (FiniteInterval.exact(7600.0), (ObservationId("edge:5"),)),
                ),
            ),
            format_gap_prior_mm=2.0,
        )
        self.assertEqual(second_lane.gap_interval_px, gap.gap_interval_px)
        self.assertNotEqual(second_lane.gap_model_id, gap.gap_model_id)
        contradicted = LaneGapModel.from_edge_families(
            state,
            lane_id="lane:0",
            edge_families=(
                (
                    (FiniteInterval.exact(0.0), (ObservationId("edge:6"),)),
                    (FiniteInterval.exact(3800.0), (ObservationId("edge:7"),)),
                    (FiniteInterval.exact(7900.0), (ObservationId("edge:8"),)),
                ),
            ),
            format_gap_prior_mm=2.0,
        )
        self.assertEqual(contradicted.state, EvidenceState.CONTRADICTED)
        self.assertIsNone(contradicted.gap_interval_px)
        self.assertEqual(
            state.retained_extent_budget_px(0.05),
            FiniteInterval(
                state.extent_projection_px().minimum * 0.05,
                state.extent_projection_px().maximum * 0.05,
            ),
        )

    def test_local_advance_observation_must_intersect_format_gap_authority(
        self,
    ) -> None:
        component = FramePhysicalSpec(
            "test",
            36.0,
            24.0,
            1.5,
        )
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=PositiveInterval(100.0, 100.0),
            height_scale_px_per_mm=PositiveInterval(100.0, 100.0),
        )
        self.assertIsNone(
            local_advance_delta_from_observed_gap(
                FiniteInterval(4000.0, 4010.0),
                geometry,
            )
        )
        self.assertEqual(
            local_advance_delta_from_observed_gap(
                FiniteInterval(195.0, 205.0),
                geometry,
            ),
            FiniteInterval(45.0, 55.0),
        )
        self.assertEqual(
            local_advance_delta_from_observed_gap(
                FiniteInterval(145.0, 155.0),
                geometry,
            ),
            FiniteInterval.exact(0.0),
        )

    def test_phase_assignment_is_indexed_and_each_vote_matches_once(self) -> None:
        roles = (
            TemplateRole(0, 1, BoundaryRole.START),
            TemplateRole(1, 1, BoundaryRole.END),
        )
        votes = (
            PhaseVote(
                vote_id="a",
                run_id="run-a",
                role=roles[0],
                phase_interval_px=FiniteInterval(9.0, 11.0),
                transition_ids=(ObservationId("a"),),
                template_coordinate_px=0.0,
            ),
            PhaseVote(
                vote_id="b",
                run_id="run-b",
                role=roles[1],
                phase_interval_px=FiniteInterval(9.5, 10.5),
                transition_ids=(ObservationId("b"),),
                template_coordinate_px=1.0,
            ),
        )
        groups, work = build_phase_groups(votes, roles)
        self.assertTrue(groups)
        self.assertLessEqual(
            work.template_role_lookup_count,
            len(groups) * len(roles),
        )
        self.assertLessEqual(work.template_role_match_count, len(votes))
        matched = [vote.vote_id for group in groups for vote in group.votes]
        self.assertEqual(len(matched), len(set(matched)))

    def test_work_receipt_uses_current_bounded_units_only(self) -> None:
        receipt = TemplateWorkReceipt(
            measurement_query_count=4,
            pixel_query_count=100,
            basic_profile_coordinate_count=300,
            basic_profile_run_count=4,
            phase_vote_count=8,
            template_group_count=2,
            template_role_lookup_count=8,
            template_role_match_count=6,
            local_relation_evaluation_count=4,
            enhanced_query_count=0,
            materialized_frame_geometry_count=6,
            shared_measurement_reuse_count=4,
            domain_pixels=20000,
            peak_temporary_bytes=4096,
        )
        self.assertNotIn("dp_states", receipt.__dict__)
        self.assertNotIn("template_role_evaluation_count", receipt.__dict__)
        receipt.validate_bounds(
            ordered_role_count=4,
            slot_count=3,
            registered_enhanced_query_count=0,
        )
        with self.assertRaises(ValueError):
            replace(receipt, enhanced_query_count=1).validate_bounds(
                ordered_role_count=4,
                slot_count=3,
                registered_enhanced_query_count=0,
            )

    def test_enhanced_queries_are_preregistered_and_execute_once(self) -> None:
        registry = EnhancedQueryRegistry(("missing-role:1", "angle:1"))
        self.assertTrue(registry.consume("missing-role:1"))
        self.assertFalse(registry.consume("missing-role:1"))
        with self.assertRaises(KeyError):
            registry.consume("selected-placement:new-window")

    def test_local_delta_moves_following_phase_once(self) -> None:
        relations = (
            LocalAdvanceRelation(
                relation_ordinal=1,
                kind=LocalAdvanceKind.WIDE,
                delta_interval_px=FiniteInterval(8.0, 10.0),
                canonical_delta_px=9.0,
                observation_ids=(ObservationId("gap:1"),),
            ),
            LocalAdvanceRelation(
                relation_ordinal=2,
                kind=LocalAdvanceKind.NOMINAL,
                delta_interval_px=FiniteInterval.exact(0.0),
                canonical_delta_px=0.0,
                observation_ids=(),
            ),
        )
        self.assertEqual(
            local_advance_prefix(relations, lane_ordinal=1),
            (FiniteInterval.exact(0.0), 0.0),
        )
        self.assertEqual(
            local_advance_prefix(relations, lane_ordinal=2),
            (FiniteInterval(8.0, 10.0), 9.0),
        )
        self.assertEqual(
            local_advance_prefix(relations, lane_ordinal=3),
            (FiniteInterval(8.0, 10.0), 9.0),
        )


if __name__ == "__main__":
    unittest.main()
