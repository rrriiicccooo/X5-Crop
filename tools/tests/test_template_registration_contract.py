from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.photo_geometry_support import make_side_measurement_set
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    ProfileRun,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossBoundaryFamilyFailureKind,
    CrossEvidence,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.template_model import PhaseLatticeAuthority
from x5crop.detection.photo_geometry.template_registration import (
    RegisteredCrossEvidence,
    register_cross_evidence,
    register_template_local_cross_refinements,
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
    @staticmethod
    def _role_scoped_registration(
        roles: tuple[BoundaryRole, ...],
        *,
        maximum_runs_per_role: int,
    ) -> RegisteredCrossEvidence:
        measurement = make_side_measurement_set(
            tuple(
                ((100.0 if index < 6 else 340.0),)
                for index in range(12)
            )
        )
        transitions = {
            item.trace_ordinal: item for item in measurement.transitions
        }
        role_ordinals = {
            BoundaryRole.TOP: iter(((0, 1), (2, 3), (4, 5))),
            BoundaryRole.BOTTOM: iter(((6, 7), (8, 9), (10, 11))),
        }
        runs = []
        for index, role in enumerate(roles):
            group = next(role_ordinals[role])
            selected = tuple(transitions[ordinal] for ordinal in group)
            coordinate = 100.0 if role == BoundaryRole.TOP else 340.0
            runs.append(
                ProfileRun(
                    run_id=f"{role.value}:{index}",
                    coordinate_interval_px=FiniteInterval(
                        coordinate - 0.25,
                        coordinate + 0.25,
                    ),
                    transition_ids=tuple(
                        item.transition_id for item in selected
                    ),
                    trace_coordinates_px=tuple(
                        item.trace_coordinate_px for item in selected
                    ),
                    role_hint=role,
                    qualified_anchor_roles=(role,),
                    support_fraction=2.0 / 12.0,
                    continuous_support_fraction=0.2,
                    fit_residual_px=0.0,
                    evidence_strength=10.0,
                    pair_qualified=True,
                )
            )
        profile = BasicAxisProfile(
            "cross",
            400,
            measurement.query.trace_positions_px,
            tuple(
                sorted(
                    runs,
                    key=lambda item: (
                        item.coordinate_interval_px.center,
                        item.run_id,
                    ),
                )
            ),
        )
        return register_cross_evidence(
            profile=profile,
            top_measurement=measurement,
            bottom_measurement=measurement,
            width_axis=BoundaryAxis.Y,
            height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
            lane_reference_trace_px=55.0,
            maximum_runs_per_role=maximum_runs_per_role,
        )

    def test_top_and_bottom_registration_use_independent_run_bounds(self) -> None:
        registered = self._role_scoped_registration(
            (
                BoundaryRole.TOP,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
                BoundaryRole.BOTTOM,
            ),
            maximum_runs_per_role=2,
        )

        self.assertEqual(registered.registered_top_run_count, 2)
        self.assertEqual(registered.registered_bottom_run_count, 2)
        self.assertGreater(registered.fit_attempt_count, 0)

    def test_one_cross_role_cannot_consume_the_other_role_bound(self) -> None:
        registered = self._role_scoped_registration(
            (
                BoundaryRole.TOP,
                BoundaryRole.TOP,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            ),
            maximum_runs_per_role=2,
        )

        self.assertEqual(registered.registered_top_run_count, 3)
        self.assertEqual(registered.registered_bottom_run_count, 1)
        self.assertEqual(registered.fit_attempt_count, 0)
        self.assertEqual(registered.observations, ())

    @staticmethod
    def _registered_top_families(
        coordinates_px: tuple[float, ...],
        groups: tuple[tuple[int, ...], ...],
    ) -> RegisteredCrossEvidence:
        measurement = make_side_measurement_set(
            tuple((coordinate,) for coordinate in coordinates_px)
        )
        transitions_by_ordinal = {
            item.trace_ordinal: item for item in measurement.transitions
        }
        runs = tuple(
            ProfileRun(
                run_id=f"top-family:{group_ordinal}",
                coordinate_interval_px=FiniteInterval(
                    min(coordinates_px[index] for index in group) - 0.25,
                    max(coordinates_px[index] for index in group) + 0.25,
                ),
                transition_ids=tuple(
                    transitions_by_ordinal[index].transition_id
                    for index in group
                ),
                trace_coordinates_px=tuple(
                    transitions_by_ordinal[index].trace_coordinate_px
                    for index in group
                ),
                role_hint=BoundaryRole.TOP,
                qualified_anchor_roles=(BoundaryRole.TOP,),
                support_fraction=len(group) / len(coordinates_px),
                continuous_support_fraction=0.5,
                fit_residual_px=0.0,
                evidence_strength=10.0,
                pair_qualified=True,
            )
            for group_ordinal, group in enumerate(groups)
        )
        profile = BasicAxisProfile(
            "cross",
            200,
            measurement.query.trace_positions_px,
            runs,
        )
        return register_cross_evidence(
            profile=profile,
            top_measurement=measurement,
            bottom_measurement=measurement,
            width_axis=BoundaryAxis.Y,
            height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
            lane_reference_trace_px=55.0,
        )

    def test_cross_family_merges_disconnected_complete_union(self) -> None:
        registered = self._registered_top_families(
            (100.0,) * 12,
            ((0, 2, 4), (7, 9, 11)),
        )

        self.assertEqual(len(registered.top_bindings), 1)
        self.assertEqual(len(registered.observations), 1)
        self.assertEqual(len(registered.observations[0].transition_ids), 6)
        self.assertEqual(len(registered.family_resolutions), 1)
        self.assertEqual(
            registered.family_resolutions[0].state,
            EvidenceState.SUPPORTED,
        )
        self.assertIsNone(registered.family_resolutions[0].failure_kind)

    def test_cross_family_rejects_partial_union_refit(self) -> None:
        registered = self._registered_top_families(
            tuple(100.0 if index % 2 == 0 else 102.0 for index in range(12)),
            (
                (0, 2, 4, 6, 8, 10),
                (1, 3, 5, 7, 9, 11),
            ),
        )

        self.assertEqual(len(registered.top_bindings), 2)
        self.assertEqual(len(registered.observations), 2)
        self.assertEqual(len(registered.family_resolutions), 1)
        self.assertEqual(
            registered.family_resolutions[0].state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            registered.family_resolutions[0].failure_kind,
            CrossBoundaryFamilyFailureKind
            .COMPLETE_TRANSITION_UNION_REFIT_REJECTED,
        )

    @staticmethod
    def _top_anchor() -> CrossRoleBinding:
        return CrossRoleBinding(
            role=BoundaryRole.TOP,
            run_id="top:source-wide",
            observation_id=ObservationId("top:source-wide"),
            coordinate_interval_px=FiniteInterval(19.5, 20.5),
            trace_coordinates_px=(0, 10, 20, 30, 40, 50),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.05, 0.05),
            full_direction_interval_degrees=FiniteInterval(-0.1, 0.1),
            independent_support_region_count=3,
            source_spanning_continuous=True,
            role_authorized=True,
        )

    @staticmethod
    def _bottom_measurement(
        coordinates_by_trace: tuple[tuple[float, ...], ...],
    ):
        measurement = make_side_measurement_set(coordinates_by_trace)
        return replace(
            measurement,
            transitions=tuple(
                replace(
                    item,
                    left_texture_mean=5.0,
                    right_texture_mean=1.0,
                )
                for item in measurement.transitions
            ),
        )

    def _local_cross_refinement(
        self,
        coordinates_by_trace: tuple[tuple[float, ...], ...],
    ) -> RegisteredCrossEvidence:
        top = self._top_anchor()
        measurement = self._bottom_measurement(coordinates_by_trace)
        return register_template_local_cross_refinements(
            RegisteredCrossEvidence(
                top_bindings=(top,),
                bottom_bindings=(),
                observations=(),
                fit_attempt_count=0,
            ),
            top_measurement=measurement,
            bottom_measurement=measurement,
            width_axis=BoundaryAxis.Y,
            height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
            lane_reference_trace_px=25.0,
            fixed_height_px=FiniteInterval(79.0, 81.0),
            canonical_height_px=80.0,
            longitudinal_support_domains_px=(
                FiniteInterval(0.0, 15.0),
                FiniteInterval(15.1, 35.0),
                FiniteInterval(35.1, 50.0),
            ),
            maximum_bindings=8,
        )

    def test_template_local_cross_refines_real_opposite_transitions(self) -> None:
        refined = self._local_cross_refinement(((100.0,),) * 6)

        self.assertEqual(len(refined.bottom_bindings), 1)
        self.assertEqual(
            refined.bottom_bindings[0].evidence,
            CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )
        self.assertTrue(refined.bottom_bindings[0].role_authorized)
        self.assertEqual(refined.fit_attempt_count, 1)
        self.assertEqual(len(refined.observations), 1)

    def test_template_local_cross_does_not_break_equal_nearest_tie(self) -> None:
        refined = self._local_cross_refinement(((99.0, 101.0),) * 6)

        self.assertEqual(refined.bottom_bindings, ())
        self.assertEqual(refined.fit_attempt_count, 0)

    def test_template_local_cross_ignores_transitions_outside_corridor(self) -> None:
        refined = self._local_cross_refinement(((120.0,),) * 6)

        self.assertEqual(refined.bottom_bindings, ())
        self.assertEqual(refined.fit_attempt_count, 0)

    def test_template_local_cross_does_not_duplicate_direct_closure(self) -> None:
        top = self._top_anchor()
        bottom = CrossRoleBinding(
            role=BoundaryRole.BOTTOM,
            run_id="bottom:direct",
            observation_id=ObservationId("bottom:direct"),
            coordinate_interval_px=FiniteInterval(99.5, 100.5),
            trace_coordinates_px=(0, 10, 20, 30, 40, 50),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval(-0.05, 0.05),
            full_direction_interval_degrees=FiniteInterval(-0.1, 0.1),
            independent_support_region_count=3,
            source_spanning_continuous=True,
            role_authorized=True,
        )
        measurement = self._bottom_measurement(((100.0,),) * 6)

        refined = register_template_local_cross_refinements(
            RegisteredCrossEvidence(
                top_bindings=(top,),
                bottom_bindings=(bottom,),
                observations=(),
                fit_attempt_count=0,
            ),
            top_measurement=measurement,
            bottom_measurement=measurement,
            width_axis=BoundaryAxis.Y,
            height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
            lane_reference_trace_px=25.0,
            fixed_height_px=FiniteInterval(79.0, 81.0),
            canonical_height_px=80.0,
            longitudinal_support_domains_px=(
                FiniteInterval(0.0, 15.0),
                FiniteInterval(15.1, 35.0),
                FiniteInterval(35.1, 50.0),
            ),
            maximum_bindings=8,
        )

        self.assertEqual(refined.top_bindings, (top,))
        self.assertEqual(refined.bottom_bindings, (bottom,))
        self.assertEqual(refined.fit_attempt_count, 0)
        self.assertEqual(refined.observations, ())

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

if __name__ == "__main__":
    unittest.main()
