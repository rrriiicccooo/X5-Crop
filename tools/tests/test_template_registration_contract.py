from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest

from tools.regression.report_validation import (
    _validate_cross_direct_support_regions,
    _validate_cross_fit_binding_support,
    _validate_cross_measurement_support,
)
from tools.tests.photo_geometry_support import make_side_measurement_set
from x5crop.report.read_models import typed_read_model
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
    CrossFitStatus,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from tools.tests.template_test_support import placement_template
from x5crop.detection.photo_geometry.template_model import PhaseLatticeAuthority
from x5crop.detection.photo_geometry.template_registration import (
    CrossRegistrationWorkReceipt,
    RegisteredCrossEvidence,
    project_cross_solver_bindings,
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

    def test_single_region_fragments_reach_complete_family_union(self) -> None:
        registered = self._registered_top_families(
            (100.0,) * 12,
            ((0, 1, 2), (9, 10, 11)),
        )

        self.assertEqual(registered.fit_attempt_count, 3)
        self.assertEqual(len(registered.observations), 1)
        observation = registered.observations[0]
        self.assertEqual(len(observation.transition_ids), 6)
        self.assertEqual(observation.independent_support_region_count, 2)
        self.assertEqual(len(registered.top_bindings), 1)
        self.assertEqual(registered.top_bindings[0].independent_support_region_count, 2)
        self.assertTrue(registered.top_bindings[0].role_authorized)
        self.assertEqual(project_cross_solver_bindings(registered.top_bindings), registered.top_bindings)
        family = registered.family_resolutions[0]
        self.assertEqual(family.state, EvidenceState.SUPPORTED)
        self.assertEqual(set(family.member_transition_ids), set(observation.transition_ids))
        self.assertEqual(family.final_observation_ids, (observation.observation_id,))

    def test_same_region_fragments_remain_local_when_union_lacks_independence(self) -> None:
        registered = self._registered_top_families(
            (100.0,) * 12,
            ((0, 1), (2, 3)),
        )

        self.assertEqual(registered.fit_attempt_count, 3)
        self.assertEqual(len(registered.observations), 2)
        self.assertEqual(len(registered.top_bindings), 2)
        self.assertTrue(all(
            item.independent_support_region_count == 1
            for item in registered.observations
        ))
        self.assertTrue(all(
            item.independent_support_region_count == 1
            for item in registered.top_bindings
        ))
        self.assertTrue(all(not item.role_authorized for item in registered.top_bindings))
        self.assertEqual(project_cross_solver_bindings(registered.top_bindings), ())
        self.assertEqual(registered.work_receipt, CrossRegistrationWorkReceipt(3, 2, 2))
        family = registered.family_resolutions[0]
        self.assertEqual(family.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            family.failure_kind,
            CrossBoundaryFamilyFailureKind.COMPLETE_TRANSITION_UNION_REFIT_REJECTED,
        )
        self.assertEqual(
            set(family.final_observation_ids),
            {item.observation_id for item in registered.observations},
        )

    def test_solver_projection_preserves_the_complete_local_measurement_ledger(self) -> None:
        local = self._registered_top_families((100.0,) * 12, ((0, 1, 2),))
        independent = self._registered_top_families((100.0,) * 12, ((0, 1, 2, 9, 10, 11),))
        observations = []
        by_role = {BoundaryRole.TOP: [], BoundaryRole.BOTTOM: []}
        for role, local_count, independent_count in (
            (BoundaryRole.TOP, 340, 51), (BoundaryRole.BOTTOM, 163, 20),
        ):
            for basis, count in ((local, local_count), (independent, independent_count)):
                for index in range(count):
                    identity = ObservationId(f"{role.value}:{len(observations)}")
                    observations.append(replace(basis.observations[0], observation_id=identity, role=role))
                    by_role[role].append(replace(
                        basis.top_bindings[0], role=role, run_id=str(identity),
                        observation_id=identity, source_observation_ids=(identity,),
                        role_authorized=basis is independent and index % 2 == 0,
                    ))
        registered = RegisteredCrossEvidence(
            top_bindings=tuple(by_role[BoundaryRole.TOP]),
            bottom_bindings=tuple(by_role[BoundaryRole.BOTTOM]),
            observations=tuple(observations), fit_attempt_count=576,
            registered_top_run_count=391, registered_bottom_run_count=183,
        )
        complete = (*registered.top_bindings, *registered.bottom_bindings)
        projected = project_cross_solver_bindings(complete)
        self.assertEqual(len(complete), 574)
        self.assertEqual(registered.work_receipt, CrossRegistrationWorkReceipt(576, 574, 503))
        self.assertEqual(len(projected), 71)
        self.assertTrue(any(not item.role_authorized for item in projected))
        self.assertEqual(projected, tuple(item for item in complete if item.independent_support_region_count >= 2))
        self.assertEqual(len(registered.observations), 574)

    def test_prepared_solver_input_is_exactly_the_independent_projection(self) -> None:
        from tools.tests.template_runtime_test_support import prepared_template_lane

        prepared = prepared_template_lane()
        for ordinals in ((0, 1, 2), (0, 1, 2, 9, 10, 11)):
            registered = self._registered_top_families((100.0,) * 12, (ordinals,))
            projected = project_cross_solver_bindings(registered.top_bindings)
            cross_input = replace(
                prepared.cross_input, top_bindings=projected,
                fitted_observation_count=len(projected),
            )
            valid = replace(
                prepared, top_cross_bindings=registered.top_bindings,
                raw_cross_observations=registered.observations,
                cross_registration_work=registered.work_receipt,
                cross_input=cross_input,
            )
            invalid_bindings = () if projected else registered.top_bindings
            with self.subTest(ordinals=ordinals), self.assertRaisesRegex(ValueError, "solver inputs disagree"):
                replace(valid, cross_input=replace(
                    cross_input, top_bindings=invalid_bindings,
                    fitted_observation_count=len(invalid_bindings),
                ))
            with self.assertRaisesRegex(ValueError, "registration work disagrees"):
                replace(valid, cross_registration_work=CrossRegistrationWorkReceipt(0, 0, 0))

    def test_single_point_cannot_become_a_local_cross_line(self) -> None:
        registered = self._registered_top_families((100.0,) * 12, ((0,),))
        self.assertEqual(registered.fit_attempt_count, 1)
        self.assertEqual(registered.observations, ())
        self.assertEqual(registered.top_bindings, ())
        self.assertEqual(registered.family_resolutions, ())

    def test_report_preserves_one_region_measurement_and_rejects_promoted_counts(self) -> None:
        registered = self._registered_top_families((100.0,) * 12, ((0, 1, 2),))
        self.assertEqual(len(registered.observations), 1)
        self.assertEqual(registered.observations[0].independent_support_region_count, 1)
        binding = registered.top_bindings[0]
        self.assertFalse(binding.role_authorized)
        self.assertFalse(binding.has_independent_spatial_support)
        # The physical line remains measured, but cannot yet move a crop edge.
        self.assertIsNone(binding.projected_shift_px(source_trace_px=10.0, target_trace_px=20.0))
        lane = {
            "lane_id": "lane:0",
            "cross_registration_work": typed_read_model(registered.work_receipt),
            "observations": {
                "raw_top_bottom_lines": typed_read_model(registered.observations),
                "registered_top_bottom_bindings": typed_read_model(registered.top_bindings),
            },
        }
        queries = [typed_read_model(make_side_measurement_set(((100.0,),) * 12))]
        _validate_cross_measurement_support(lane, queries)
        for keys in (
            ("raw_top_bottom_lines",),
            ("registered_top_bottom_bindings",),
            ("raw_top_bottom_lines", "registered_top_bottom_bindings"),
        ):
            invalid = deepcopy(lane)
            for key in keys:
                invalid["observations"][key][0]["independent_support_region_count"] = 3
            with self.subTest(keys=keys), self.assertRaisesRegex(ValueError, "not reproducible|changed original"):
                _validate_cross_measurement_support(invalid, queries)
        invalid_role = deepcopy(lane)
        invalid_role["observations"]["registered_top_bottom_bindings"][0]["role_authorized"] = True
        with self.assertRaisesRegex(ValueError, "not reproducible"):
            _validate_cross_measurement_support(invalid_role, queries)
        missing_raw = deepcopy(invalid_role)
        missing_raw["observations"]["raw_top_bottom_lines"] = []
        missing_raw["cross_registration_work"] = typed_read_model(CrossRegistrationWorkReceipt(1, 0, 0))
        missing_raw["observations"]["registered_top_bottom_bindings"][0]["independent_support_region_count"] = 3
        with self.assertRaisesRegex(ValueError, "observation provenance"):
            _validate_cross_measurement_support(missing_raw, queries)
        registered_report = _validate_cross_measurement_support(lane, queries)
        fit = {"direct_bindings": typed_read_model(registered.top_bindings)}
        with self.assertRaisesRegex(ValueError, "local-only"):
            _validate_cross_fit_binding_support(fit, registered_report)
        independent = self._registered_top_families((100.0,) * 12, ((0, 1, 2, 9, 10, 11),))
        independent_binding = typed_read_model(independent.top_bindings[0])
        independent_binding["role_authorized"] = False
        registered_report = {independent_binding["observation_id"]: independent_binding}
        fit = {"direct_bindings": [deepcopy(independent_binding)]}
        _validate_cross_fit_binding_support(fit, registered_report)
        fit["direct_bindings"][0]["role_authorized"] = True
        with self.assertRaisesRegex(ValueError, "original measured"):
            _validate_cross_fit_binding_support(fit, registered_report)
        summary = {
            "cross_status": "unresolved",
            "cross_height_inference_basis": "calibrated_format_height",
            "cross_longitudinal_projection_authority": {
                "supporting_observation_ids": [str(binding.observation_id)],
            },
            "cross_direct_support_regions": [{
                "observation_id": str(binding.observation_id),
                "role": "top", "independent_support_region_count": 1,
            }],
        }
        with self.assertRaisesRegex(ValueError, "independent measured"):
            _validate_cross_direct_support_regions(summary)
        summary["cross_status"] = "resolved"
        with self.assertRaisesRegex(ValueError, "independent measured"):
            _validate_cross_direct_support_regions(summary)

    def test_report_binds_extra_coarse_tracks_without_aperture_authority(self) -> None:
        tracks = [{
            "observation_id": identity,
            "trace_coordinates_px": [0.0, 50.0, 100.0],
            "independent_support_region_count": 3,
        } for identity in ("coarse-minimum", "coarse-maximum")]
        pair_id = "coarse-enclosing-pair:coarse-minimum:coarse-maximum"
        bindings = [{
            **track, "role": role, "role_authorized": False,
            "run_id": f"coarse-enclosing:{track['observation_id']}",
            "enclosing_pair_id": pair_id,
        } for role, track in zip(("top", "bottom"), tracks)]
        lane = {
            "lane_id": "lane:0",
            "cross_registration_work": typed_read_model(CrossRegistrationWorkReceipt(0, 0, 0)),
            "search": {"coarse_strip_support": {"enclosing_support": {
                "minimum_track": tracks[0], "maximum_track": tracks[1],
            }}},
            "observations": {
                "raw_top_bottom_lines": [],
                "registered_top_bottom_bindings": bindings,
            },
        }
        self.assertEqual(len(_validate_cross_measurement_support(lane, [])), 2)
        for field, value in (("role_authorized", True), ("independent_support_region_count", 2)):
            invalid = deepcopy(lane)
            invalid["observations"]["registered_top_bottom_bindings"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "coarse support"):
                _validate_cross_measurement_support(invalid, [])
        lane["observations"]["registered_top_bottom_bindings"] = []
        self.assertEqual(_validate_cross_measurement_support(lane, []), {})

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
        *,
        local_opposite: CrossRoleBinding | None = None,
    ) -> RegisteredCrossEvidence:
        top = self._top_anchor()
        measurement = self._bottom_measurement(coordinates_by_trace)
        return register_template_local_cross_refinements(
            RegisteredCrossEvidence(
                top_bindings=(top,),
                bottom_bindings=() if local_opposite is None else (local_opposite,),
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
            longitudinal_support_domain_groups_px=((
                FiniteInterval(0.0, 15.0),
                FiniteInterval(15.1, 35.0),
                FiniteInterval(35.1, 50.0),
            ),),
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
        self.assertEqual(refined.registered_bottom_run_count, 0)
        # Refinement retains the newly measured line even when the later
        # solver's finite bound rejects the complete input; no old-array refill.
        result = fit_template_cross(TemplateCrossInput(
            template=replace(placement_template(1), frame_height_px=FiniteInterval(79.0, 81.0)),
            fixed_height_px=FiniteInterval(79.0, 81.0),
            top_bindings=project_cross_solver_bindings(refined.top_bindings),
            bottom_bindings=project_cross_solver_bindings(refined.bottom_bindings),
            maximum_fitted_observations=1,
        ))
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.fitted_observation_count, 2)
        self.assertEqual(len(refined.bottom_bindings), 1)

    def test_one_region_opposite_does_not_block_independent_refinement(self) -> None:
        local = replace(
            self._top_anchor(), role=BoundaryRole.BOTTOM,
            run_id="bottom:local", observation_id=ObservationId("bottom:local"),
            source_observation_ids=(ObservationId("bottom:local"),),
            coordinate_interval_px=FiniteInterval(99.5, 100.5),
            fit_interval_px=FiniteInterval(99.5, 100.5),
            full_interval_px=FiniteInterval(99.5, 100.5),
            trace_coordinates_px=(0, 10), independent_support_region_count=1,
            source_spanning_continuous=False,
        )
        refined = self._local_cross_refinement(((100.0,),) * 6, local_opposite=local)
        self.assertEqual(refined.fit_attempt_count, 1)
        self.assertIn(local, refined.bottom_bindings)
        complete = [
            binding for binding in refined.bottom_bindings
            if binding.evidence == CrossEvidence.TEMPLATE_LOCAL_REFINEMENT
        ]
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0].independent_support_region_count, 3)

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
            longitudinal_support_domain_groups_px=((
                FiniteInterval(0.0, 15.0),
                FiniteInterval(15.1, 35.0),
                FiniteInterval(35.1, 50.0),
            ),),
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
