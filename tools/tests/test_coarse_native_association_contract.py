from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import math
import unittest

from x5crop.detection.photo_geometry.coarse_enclosing_model import (
    CoarseEnclosingMeasurementBasis,
    CoarseEnclosingSupport,
    CoarseSupportSide,
)
from x5crop.detection.photo_geometry.coarse_enclosing_support import _fit_track
from x5crop.detection.photo_geometry.coarse_native_association import (
    associate_coarse_native_lines,
)
from x5crop.detection.photo_geometry.robust_line_fit import physical_line_region
from x5crop.detection.photo_geometry.line_observations import (
    PhotoBoundaryObservation,
    PhysicalLineRegion,
    RobustLineFitReceipt,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.template_coarse_sides import coarse_enclosing_binding
from x5crop.detection.photo_geometry.template_output import (
    _support_cross_outward_departure_px,
    _support_direction_departure_px,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.template_family_membership import MembershipState
from x5crop.detection.photo_geometry.transition_peak_capture import TransitionPeakCapture
from x5crop.detection.photo_geometry.transition_peak_source import (
    TransitionPeakGroupSource,
    TransitionPeakReference,
    TransitionPeakTraceSource,
)
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval, WorkspaceExtent


class CoarseNativeAssociationContractTest(unittest.TestCase):
    _COARSE_TRACES = (10, 20, 30)
    _NATIVE_TRACES = (10, 20, 30, 40)

    def _query(
        self,
        query_id: str,
        purpose: QueryPurpose,
        traces: tuple[int, ...],
        *,
        domain: tuple[float, float] = (4.0, 123.0),
    ):
        return PhotoBoundaryMeasurementQuery(
            query_id=query_id,
            registration_index=0,
            lane_id="lane:synthetic",
            purpose=purpose,
            boundary_axis=BoundaryAxis.Y,
            trace_positions_px=traces,
            search_intervals_px=(FiniteInterval(*domain),) * len(traces),
            transition_ownership_intervals_px=(FiniteInterval(*domain),) * len(traces),
            expected_support_px=50.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=5,
            registration_provenance_ids=(f"registered:{query_id}",),
        )

    def _source(self, role: BoundaryRole, trace: int, signal: str | None = None):
        return TransitionPeakTraceSource(
            source_id="synthetic-field",
            source_extent=WorkspaceExtent(width=64, height=128),
            boundary_axis=BoundaryAxis.Y,
            trace_coordinate_px=trace,
            normalization_domain_px=(4, 123),
            window_px=3,
            gap_px=1,
            gradient_z_minimum=3.0,
            tone_or_texture_z_minimum=3.0,
            signal_sha256=signal or "a" * 64,
        )

    def _group(
        self,
        role: BoundaryRole,
        trace: int,
        *,
        view: tuple[int, int],
        signal: str | None = None,
        credible_group_domain: tuple[int, int] | None = None,
    ) -> TransitionPeakGroupSource:
        center = 50 if role == BoundaryRole.TOP else 80
        sign = 1 if role == BoundaryRole.TOP else -1
        domain = credible_group_domain or (center - 2, center + 2)
        return TransitionPeakGroupSource(
            source=self._source(role, trace, signal),
            measurement_domain_px=view,
            credible_group_domain_px=domain,
            reliable_gradient_partitions=((sign, tuple(range(domain[0], domain[1] + 1))),),
            candidate_peak_coordinates_px=(center,),
            selection_basis="gradient",
            split_gradient_reversals=False,
        )

    def _reference(self, group: TransitionPeakGroupSource) -> TransitionPeakReference:
        center = group.candidate_peak_coordinates_px[0]
        sign = group.reliable_gradient_partitions[0][0]
        return TransitionPeakReference(group.primitive_id, 0, center, sign)

    def _transition(
        self,
        query_id: str,
        role: BoundaryRole,
        trace_ordinal: int,
        trace: int,
        group: TransitionPeakGroupSource,
        *,
        interval: FiniteInterval | None = None,
        transition_id: str | None = None,
    ) -> PhotoBoundaryTransition:
        center = float(group.candidate_peak_coordinates_px[0])
        physical = interval or FiniteInterval(
            group.credible_group_domain_px[0] - 0.5,
            group.credible_group_domain_px[1] + 0.5,
        )
        polarity = group.reliable_gradient_partitions[0][0]
        return PhotoBoundaryTransition(
            transition_id=ObservationId(
                transition_id or f"{query_id}:{role.value}:{trace}"
            ),
            query_id=query_id,
            trace_ordinal=trace_ordinal,
            trace_coordinate_px=trace,
            canonical_coordinate_px=center,
            localization_interval_px=physical,
            physical_position_interval_px=physical,
            gradient_z=8.0,
            tone_z=6.0,
            texture_z=6.0,
            left_tone_mean=10.0,
            right_tone_mean=30.0,
            left_texture_mean=1.0,
            right_texture_mean=5.0,
            polarity=polarity,
            peak_width_px=1.0,
            prominence=8.0,
            local_noise=0.0,
            texture_sample_coordinate_px=int(center),
            peak_source=self._reference(group),
        )

    def _observation(
        self,
        query: PhotoBoundaryMeasurementQuery,
        role: BoundaryRole,
        transitions: tuple[PhotoBoundaryTransition, ...],
        *,
        observation_id: str,
        transition_ids: tuple[ObservationId, ...] | None = None,
    ) -> PhotoBoundaryObservation:
        intervals = tuple(item.physical_position_interval_px for item in transitions)
        center = float(transitions[0].canonical_coordinate_px)
        line = SourceCoordinateLine(
            normal_x=0.0,
            normal_y=1.0,
            offset_px=center,
            support_projection_px=FiniteInterval(
                float(min(item.trace_coordinate_px for item in transitions)),
                float(max(item.trace_coordinate_px for item in transitions)),
            ),
            source_axis_long=BoundaryAxis.X,
        )
        return PhotoBoundaryObservation(
            observation_id=ObservationId(observation_id),
            role=role,
            line=line,
            offset_interval_px=FiniteInterval(center - 0.5, center + 0.5),
            fit_residual_px=0.0,
            angle_interval_degrees=FiniteInterval(-0.5, 0.5),
            trace_support_count=len(transitions),
            queried_trace_count=len(query.trace_positions_px),
            independent_support_region_count=3,
            continuous_support_fraction=1.0,
            transition_ids=transition_ids or tuple(item.transition_id for item in transitions),
            fit_receipt=RobustLineFitReceipt(
                method="scipy_least_squares_huber",
                converged=True,
                status=1,
                evaluation_count=1,
                cost=0.0,
                optimality=0.0,
            ),
            left_background_preference_fraction=(0.9 if role == BoundaryRole.TOP else 0.1),
            right_background_preference_fraction=(0.1 if role == BoundaryRole.TOP else 0.9),
            source_spanning_continuous=True,
            trace_coordinates_px=tuple(item.trace_coordinate_px for item in transitions),
            trace_position_intervals_px=intervals,
            physical_line_region=physical_line_region(
                tuple(
                    (float(item.trace_coordinate_px), item.physical_position_interval_px)
                    for item in transitions
                ),
                math.tan(math.radians(
                    PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_measurable_line_angle_degrees
                )),
                20.0,
            ),
        )

    def _binding(
        self,
        observation: PhotoBoundaryObservation,
        *,
        conditional: bool = False,
    ) -> CrossRoleBinding:
        return CrossRoleBinding(
            role=observation.role,
            run_id=f"run:{observation.role.value}:{observation.observation_id}",
            observation_id=observation.observation_id,
            coordinate_interval_px=observation.offset_interval_px,
            trace_coordinates_px=observation.trace_coordinates_px,
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            fit_interval_px=observation.offset_interval_px,
            full_interval_px=observation.offset_interval_px,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.5, 0.5),
            full_direction_interval_degrees=FiniteInterval(-0.5, 0.5),
            evidence=CrossEvidence.DIRECT,
            independent_support_region_count=3,
            source_spanning_continuous=True,
            role_authorized=True,
            trace_position_intervals_px=observation.trace_position_intervals_px,
            observed_direction_interval_degrees=FiniteInterval(-0.5, 0.5),
            conditional_family_ids=("family:conditional",) if conditional else (),
            physical_line_region=observation.physical_line_region,
        )

    def _measurement(
        self,
        query: PhotoBoundaryMeasurementQuery,
        groups: tuple[TransitionPeakGroupSource, ...],
        transitions: tuple[PhotoBoundaryTransition, ...],
    ):
        return SimpleNamespace(
            query=query,
            transitions=transitions,
            peak_source_groups=groups,
            coverage=SimpleNamespace(
                query_id=query.query_id,
                complete=True,
                peak_source_bound_exceeded=False,
            ),
        )

    def _ns_replace(self, value, **changes):
        fields = vars(value).copy()
        fields.update(changes)
        return SimpleNamespace(**fields)

    def _roles(self, proofs):
        return {proof.native_observation.role for proof in proofs}

    def _case(
        self,
        *,
        native_top_signal: str | None = None,
        native_top_view: tuple[int, int] = (8, 60),
        native_top_transitions: tuple[PhotoBoundaryTransition, ...] | None = None,
        native_top_groups: tuple[TransitionPeakGroupSource, ...] | None = None,
        extra_top_observation: PhotoBoundaryObservation | None = None,
        top_bindings_override: tuple[CrossRoleBinding, ...] | None = None,
        family_resolutions: tuple[object, ...] = (),
        membership=None,
        conditional_top: bool = False,
    ):
        coarse_query = self._query(
            "query:coarse-short",
            QueryPurpose.COARSE_STRIP_SHORT,
            self._COARSE_TRACES,
            domain=(4.0, 123.0),
        )
        top_query = self._query(
            "query:top-corridor",
            QueryPurpose.TOP_CORRIDOR,
            self._NATIVE_TRACES,
            domain=tuple(map(float, native_top_view)),
        )
        bottom_query = self._query(
            "query:bottom-corridor",
            QueryPurpose.BOTTOM_CORRIDOR,
            self._NATIVE_TRACES,
            domain=(70.0, 119.0),
        )

        coarse_top_groups = tuple(
            self._group(BoundaryRole.TOP, trace, view=(4, 123))
            for trace in self._COARSE_TRACES
        )
        coarse_bottom_groups = tuple(
            self._group(BoundaryRole.BOTTOM, trace, view=(4, 123))
            for trace in self._COARSE_TRACES
        )
        native_top_groups = native_top_groups or tuple(
            self._group(
                BoundaryRole.TOP,
                trace,
                view=native_top_view,
                signal=native_top_signal,
                credible_group_domain=(
                    (46, 54)
                    if trace == 40 and native_top_view == (8, 60)
                    else None
                ),
            )
            for trace in self._NATIVE_TRACES
        )
        native_bottom_groups = tuple(
            self._group(BoundaryRole.BOTTOM, trace, view=(70, 119))
            for trace in self._NATIVE_TRACES
        )

        coarse_top_transitions = tuple(
            self._transition(
                coarse_query.query_id,
                BoundaryRole.TOP,
                ordinal,
                trace,
                group,
            )
            for ordinal, (trace, group) in enumerate(
                zip(self._COARSE_TRACES, coarse_top_groups, strict=True)
            )
        )
        coarse_bottom_transitions = tuple(
            self._transition(
                coarse_query.query_id,
                BoundaryRole.BOTTOM,
                ordinal,
                trace,
                group,
            )
            for ordinal, (trace, group) in enumerate(
                zip(self._COARSE_TRACES, coarse_bottom_groups, strict=True)
            )
        )
        coarse_top_track = _fit_track(
            coarse_query,
            side=CoarseSupportSide.MINIMUM,
            measurement_basis=CoarseEnclosingMeasurementBasis.SHARP_TRANSITION,
            transitions=coarse_top_transitions,
            reference_trace_px=20.0,
        )
        coarse_bottom_track = _fit_track(
            coarse_query,
            side=CoarseSupportSide.MAXIMUM,
            measurement_basis=CoarseEnclosingMeasurementBasis.SHARP_TRANSITION,
            transitions=coarse_bottom_transitions,
            reference_trace_px=20.0,
        )
        self.assertIsNotNone(coarse_top_track)
        self.assertIsNotNone(coarse_bottom_track)
        assert coarse_top_track is not None and coarse_bottom_track is not None
        # The two synthetic flat tracks are intentionally the same physical
        # direction.  Reuse the exact top-side floating-point receipt so the
        # typed enclosing pair does not turn harmless signed-zero roundoff
        # into a fixture disagreement.
        coarse_bottom_track = replace(
            coarse_bottom_track,
            canonical_direction_degrees=coarse_top_track.canonical_direction_degrees,
            fit_direction_interval_degrees=coarse_top_track.fit_direction_interval_degrees,
            full_direction_interval_degrees=coarse_top_track.full_direction_interval_degrees,
            observed_direction_interval_degrees=coarse_top_track.observed_direction_interval_degrees,
        )
        support = CoarseEnclosingSupport(
            coarse_top_track,
            coarse_bottom_track,
            FiniteInterval(
                coarse_bottom_track.full_position_interval_px.minimum
                - coarse_top_track.full_position_interval_px.maximum,
                coarse_bottom_track.full_position_interval_px.maximum
                - coarse_top_track.full_position_interval_px.minimum,
            ),
            3,
        )

        top_intervals = (
            FiniteInterval(47.5, 52.5),
            FiniteInterval(47.5, 52.5),
            FiniteInterval(47.5, 52.5),
            FiniteInterval(45.5, 54.5),
        )
        bottom_intervals = (
            FiniteInterval(77.5, 82.5),
            FiniteInterval(77.5, 82.5),
            FiniteInterval(77.5, 82.5),
            FiniteInterval(75.5, 84.5),
        )
        native_top_transitions = native_top_transitions or tuple(
            self._transition(
                top_query.query_id,
                BoundaryRole.TOP,
                ordinal,
                trace,
                group,
                interval=top_intervals[ordinal],
            )
            for ordinal, (trace, group) in enumerate(
                zip(self._NATIVE_TRACES, native_top_groups, strict=True)
            )
        )
        native_bottom_transitions = tuple(
            self._transition(
                bottom_query.query_id,
                BoundaryRole.BOTTOM,
                ordinal,
                trace,
                group,
                interval=bottom_intervals[ordinal],
            )
            for ordinal, (trace, group) in enumerate(
                zip(self._NATIVE_TRACES, native_bottom_groups, strict=True)
            )
        )
        top_observation = self._observation(
            top_query,
            BoundaryRole.TOP,
            native_top_transitions,
            observation_id="native:top",
        )
        bottom_observation = self._observation(
            bottom_query,
            BoundaryRole.BOTTOM,
            native_bottom_transitions,
            observation_id="native:bottom",
        )
        coarse_measurement = self._measurement(
            coarse_query,
            (*coarse_top_groups, *coarse_bottom_groups),
            (*coarse_top_transitions, *coarse_bottom_transitions),
        )
        top_measurement = self._measurement(
            top_query,
            native_top_groups,
            native_top_transitions,
        )
        bottom_measurement = self._measurement(
            bottom_query,
            native_bottom_groups,
            native_bottom_transitions,
        )
        top_binding = self._binding(top_observation, conditional=conditional_top)
        bottom_binding = self._binding(bottom_observation)
        base = SimpleNamespace(
            observations=(
                top_observation,
                bottom_observation,
                *((extra_top_observation,) if extra_top_observation is not None else ()),
            ),
            top_bindings=top_bindings_override or (top_binding,),
            bottom_bindings=(bottom_binding,),
            family_resolutions=family_resolutions,
            membership_receipt=membership or SimpleNamespace(
                state=MembershipState.COMPLETE,
                scopes=(),
            ),
            local_refinement_scope_count=0,
            local_refinement_scopes=(),
        )
        return (
            SimpleNamespace(enclosing_support=support),
            (coarse_measurement, top_measurement, bottom_measurement),
            base,
            top_observation,
            bottom_observation,
            native_top_transitions,
        )

    def _associate(self, case, *, maximum_value_visits=10**9, maximum_temporary_bytes=10**9):
        coarse_support, measurements, base, *_ = case
        return associate_coarse_native_lines(
            coarse_support,
            measurements,
            base,
            maximum_value_visits=maximum_value_visits,
            maximum_temporary_bytes=maximum_temporary_bytes,
        )

    def test_complete_same_peak_cross_view_keeps_intervals_and_raw_direction(self) -> None:
        case = self._case()
        proofs, work = self._associate(case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.TOP, BoundaryRole.BOTTOM})
        self.assertFalse(work.bound_exceeded)
        self.assertTrue(all(len(proof.correspondences) == 3 for proof in proofs))
        top = next(
            proof
            for proof in proofs
            if proof.native_observation.role == BoundaryRole.TOP
        )
        native = case[3]
        self.assertEqual(
            top.coarse_track.retained_transitions,
            tuple(item.coarse_transition for item in top.correspondences),
        )
        self.assertEqual(top.constraint.trace_coordinates_px, native.trace_coordinates_px)
        self.assertEqual(top.constraint.trace_position_intervals_px, native.trace_position_intervals_px)
        self.assertEqual(top.constraint.observed_direction_interval_degrees, native.angle_interval_degrees)
        for trace, interval in zip(native.trace_coordinates_px, native.trace_position_intervals_px, strict=True):
            projected = top.constraint.physical_line_region.project(trace)
            # The compiled region is the intersection of coarse and native
            # physical states: it must stay inside every native raw interval,
            # while the proof keeps those complete intervals verbatim above.
            self.assertGreaterEqual(projected.minimum, interval.minimum)
            self.assertLessEqual(projected.maximum, interval.maximum)

    def test_source_signal_mismatch_blocks_only_that_role(self) -> None:
        proofs, _ = self._associate(self._case(native_top_signal="c" * 64))
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_potential_alias_in_opposite_corridor_cannot_be_ignored(self) -> None:
        case = self._case()
        coarse, top, bottom = case[1]
        alias = replace(top.transitions[0], query_id=bottom.query.query_id,
                        transition_id=ObservationId("opposite-corridor:alias"))
        widened = replace(bottom.query,
            search_intervals_px=(FiniteInterval(8.0, 119.0),) * len(bottom.query.trace_positions_px),
            transition_ownership_intervals_px=(FiniteInterval(8.0, 119.0),) * len(bottom.query.trace_positions_px))
        changed = self._ns_replace(bottom, query=widened, transitions=(*bottom.transitions, alias),
            peak_source_groups=tuple(replace(group, measurement_domain_px=(8, 119))
                                     for group in (*bottom.peak_source_groups, top.peak_source_groups[0])))
        changed_case = (case[0], (coarse, top, changed), case[2], *case[3:])
        proofs, _ = self._associate(changed_case)
        self.assertNotIn(BoundaryRole.TOP, self._roles(proofs))

    def test_truncated_complete_view_is_not_a_same_peak_proof(self) -> None:
        proofs, _ = self._associate(self._case(native_top_view=(48, 54)))
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_missing_or_duplicate_native_mapping_blocks_that_role(self) -> None:
        case = self._case()
        _, measurements, base, *_ = case
        coarse, top, bottom = measurements
        missing = self._ns_replace(
            top,
            transitions=top.transitions[:1] + top.transitions[2:],
        )
        missing_case = (case[0], (coarse, missing, bottom), base, *case[3:])
        proofs, _ = self._associate(missing_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

        duplicate = self._ns_replace(
            top,
            transitions=(
                top.transitions[0],
                replace(top.transitions[1], transition_id=ObservationId("native:top:duplicate")),
                top.transitions[1],
                *top.transitions[2:],
            ),
        )
        duplicate_case = (case[0], (coarse, duplicate, bottom), base, *case[3:])
        proofs, _ = self._associate(duplicate_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_same_three_points_with_competing_continuation_observation_blocks(self) -> None:
        case = self._case()
        top = case[3]
        alternate = replace(
            top,
            observation_id=ObservationId("native:top:alternate"),
            transition_ids=tuple(item.transition_id for item in case[5][:3]),
        )
        alternate_binding = self._binding(alternate)
        changed_base = self._ns_replace(
            case[2],
            top_bindings=(case[2].top_bindings[0], alternate_binding),
            observations=(*case[2].observations, alternate),
        )
        changed_case = (case[0], case[1], changed_base, *case[3:])
        proofs, _ = self._associate(changed_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_failed_family_shorter_union_blocks_original_peak_proof(self) -> None:
        case = self._case()
        top = case[3]
        family = SimpleNamespace(
            family_id="family:failed",
            role=BoundaryRole.TOP,
            member_observation_ids=(ObservationId("family:member"),),
            member_transition_ids=tuple(item.transition_id for item in case[5][:3]),
            member_transition_groups=(tuple(item.transition_id for item in case[5][:3]),),
        )
        changed_base = self._ns_replace(
            case[2],
            family_resolutions=(family,),
        )
        changed_case = (case[0], case[1], changed_base, *case[3:])
        proofs, _ = self._associate(changed_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_short_original_atom_cannot_be_hidden_by_a_complete_family_union(self) -> None:
        case = self._case()
        family = SimpleNamespace(
            family_id="family:complete-union",
            role=BoundaryRole.TOP,
            member_observation_ids=(ObservationId("family:extra"), ObservationId("family:member")),
            member_transition_ids=tuple(item.transition_id for item in case[5]),
            # The total is complete; its indivisible three-point member still
            # permits a shorter continuation and cannot be hidden by the union.
            member_transition_groups=(
                (case[5][3].transition_id,),
                tuple(item.transition_id for item in case[5][:3]),
            ),
        )
        changed_base = self._ns_replace(case[2], family_resolutions=(family,))
        changed_case = (case[0], case[1], changed_base, *case[3:])
        proofs, _ = self._associate(changed_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_membership_union_shorter_than_native_observation_blocks(self) -> None:
        case = self._case()
        family = SimpleNamespace(
            family_id="family:member",
            role=BoundaryRole.TOP,
            member_observation_ids=(ObservationId("family:member"),),
            member_transition_ids=tuple(item.transition_id for item in case[5][:3]),
            member_transition_groups=(tuple(item.transition_id for item in case[5][:3]),),
        )
        scope = SimpleNamespace(
            parent_family_id="family:member",
            role=BoundaryRole.TOP,
            state=MembershipState.COMPLETE,
            raw_transition_count=3,
            maximal_member_groups=((ObservationId("family:member"),),),
        )
        membership = SimpleNamespace(
            state=MembershipState.COMPLETE,
            scopes=(scope,),
        )
        changed_base = self._ns_replace(
            case[2],
            family_resolutions=(family,),
            membership_receipt=membership,
        )
        changed_case = (case[0], case[1], changed_base, *case[3:])
        proofs, _ = self._associate(changed_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

    def test_conditional_native_binding_and_incomplete_membership_do_not_authorize(self) -> None:
        conditional_case = self._case(conditional_top=True)
        proofs, _ = self._associate(conditional_case)
        self.assertEqual(self._roles(proofs), {BoundaryRole.BOTTOM})

        incomplete_membership = SimpleNamespace(
            state=MembershipState.SEARCH_BOUND_EXCEEDED,
            scopes=(),
        )
        case = self._case(membership=incomplete_membership)
        proofs, _ = self._associate(case)
        self.assertEqual(proofs, ())

    def test_budget_overflow_discards_all_proof_prefixes(self) -> None:
        proofs, work = self._associate(self._case(), maximum_value_visits=1)
        self.assertEqual(proofs, ())
        self.assertTrue(work.bound_exceeded)
        self.assertEqual(work.retained_bytes, 0)

    def test_consumer_departure_uses_native_continuation_and_wider_endpoint(self) -> None:
        case = self._case()
        proofs, _ = self._associate(case)
        top = next(
            proof
            for proof in proofs
            if proof.native_observation.role == BoundaryRole.TOP
        )
        coarse_binding = coarse_enclosing_binding(
            top.coarse_track,
            BoundaryRole.TOP,
            pair_id="pair:consumer",
        )
        original_interval = coarse_binding.full_interval_px
        original_direction = coarse_binding.observed_direction_interval_degrees
        associated_binding = replace(
            coarse_binding,
            coarse_native_constraint=top.constraint,
        )
        self.assertEqual(coarse_binding.full_interval_px, original_interval)
        self.assertEqual(coarse_binding.observed_direction_interval_degrees, original_direction)

        continuous_native_span = FiniteInterval(10.0, 35.0)
        coarse_departure = _support_direction_departure_px(
            coarse_binding,
            0.0,
            continuous_native_span,
        )
        native_departure = _support_direction_departure_px(
            associated_binding,
            0.0,
            continuous_native_span,
        )
        self.assertGreater(coarse_departure, 0.0)
        self.assertEqual(native_departure, 0.0)

        outside_span = FiniteInterval(0.0, 50.0)
        outside_departure = _support_direction_departure_px(
            associated_binding,
            0.0,
            outside_span,
        )
        direction_hull = FiniteInterval(
            min(
                original_direction.minimum,
                top.constraint.observed_direction_interval_degrees.minimum,
            ),
            max(
                original_direction.maximum,
                top.constraint.observed_direction_interval_degrees.maximum,
            ),
        )
        expected_direction_departure = max(
            abs(math.tan(math.radians(direction_hull.minimum))),
            abs(math.tan(math.radians(direction_hull.maximum))),
        ) * 10.0
        self.assertAlmostEqual(outside_departure, expected_direction_departure)

        placement = SimpleNamespace(
            cross_fit=SimpleNamespace(direct_bindings=(coarse_binding,)),
        )
        associated_placement = SimpleNamespace(
            cross_fit=SimpleNamespace(direct_bindings=(associated_binding,)),
        )
        frame = SimpleNamespace(
            top=SimpleNamespace(reference_trace_px=20.0),
            bottom=SimpleNamespace(reference_trace_px=20.0),
        )
        state = SimpleNamespace(
            top_at_lane_reference_px=50.0,
            bottom_at_lane_reference_px=80.0,
            enclosing_support_slope=0.0,
        )
        support_departure = _support_cross_outward_departure_px(
            placement,
            frame,
            state,
            BoundaryRole.TOP,
            FiniteInterval(10.0, 40.0),
        )
        associated_support_departure = _support_cross_outward_departure_px(
            associated_placement,
            frame,
            state,
            BoundaryRole.TOP,
            FiniteInterval(10.0, 40.0),
        )
        endpoint_interval = top.native_observation.trace_position_intervals_px[-1]
        self.assertLess(support_departure, associated_support_departure)
        self.assertAlmostEqual(
            associated_support_departure,
            state.top_at_lane_reference_px - endpoint_interval.minimum,
        )

    def test_zero_peak_capture_is_incomplete_before_any_group_is_retained(self) -> None:
        capture = TransitionPeakCapture(0)
        self.assertFalse(capture.complete)
        self.assertEqual(capture.groups, {})


if __name__ == "__main__":
    unittest.main()
