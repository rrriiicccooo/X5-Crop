from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest
from unittest.mock import patch

from tools.regression.report_validation import (
    _validate_cross_direct_support_regions,
    _validate_cross_fit_binding_support,
    _validate_cross_measurement_support,
)
from tools.tests.photo_geometry_support import make_side_measurement_set
from x5crop.report.read_models import typed_read_model
from x5crop.run_local_identity import source_identity_scope
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementSet
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    ProfileRun,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossBoundaryFamilyFailureKind,
    CrossBoundaryFamilyUse,
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
        return TemplateRegistrationContractTest._register_top_transition_groups(
            measurement,
            tuple(tuple(ObservationId(f"transition:{index}:0") for index in group)
                  for group in groups),
        )

    @staticmethod
    def _register_top_transition_groups(
        measurement: PhotoBoundaryMeasurementSet,
        groups: tuple[tuple[ObservationId, ...], ...],
    ) -> RegisteredCrossEvidence:
        transitions = {item.transition_id: item for item in measurement.transitions}
        runs = tuple(
            ProfileRun(
                run_id=f"top-family:{group_ordinal}",
                coordinate_interval_px=FiniteInterval(
                    min(transitions[identity].canonical_coordinate_px for identity in group) - 0.25,
                    max(transitions[identity].canonical_coordinate_px for identity in group) + 0.25,
                ),
                transition_ids=group,
                trace_coordinates_px=tuple(
                    transitions[identity].trace_coordinate_px for identity in group
                ),
                role_hint=BoundaryRole.TOP,
                qualified_anchor_roles=(BoundaryRole.TOP,),
                support_fraction=len(group) / len(measurement.query.trace_positions_px),
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
            tuple(sorted(runs, key=lambda item: (item.coordinate_interval_px.center, item.run_id))),
        )
        return register_cross_evidence(
            profile=profile,
            top_measurement=measurement,
            bottom_measurement=measurement,
            width_axis=BoundaryAxis.Y,
            height_axis=BoundaryAxis.X,
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
            lane_reference_trace_px=(
                measurement.query.trace_positions_px[0]
                + measurement.query.trace_positions_px[-1]
            ) / 2.0,
        )

    @staticmethod
    def _separated_track_measurement(coordinates: tuple[float, ...]) -> PhotoBoundaryMeasurementSet:
        measurement = make_side_measurement_set((coordinates,) * 9)
        traces = (0, 1, 2, 500, 501, 502, 1000, 1001, 1002)
        return replace(
            measurement, query=replace(measurement.query, trace_positions_px=traces),
            transitions=tuple(replace(item, trace_coordinate_px=traces[item.trace_ordinal])
                              for item in measurement.transitions),
        )

    def test_incompatible_local_track_does_not_block_one_complete_cross_family(self) -> None:
        measurement = self._separated_track_measurement((100.0, 120.0))
        groups = (
            tuple(ObservationId(f"transition:{index}:0") for index in range(3, 9)),
            tuple(ObservationId(f"transition:{index}:0") for index in range(3)),
            tuple(ObservationId(f"transition:{index}:1") for index in range(2)),
        )
        registered = self._register_top_transition_groups(measurement, groups)
        self.assertEqual(len(registered.observations), 2)
        complete = next(item for item in registered.observations if len(item.transition_ids) == 9)
        self.assertEqual(complete.independent_support_region_count, 3)
        self.assertEqual(complete.trace_coordinates_px, measurement.query.trace_positions_px)
        self.assertEqual(set(complete.transition_ids), set(groups[0] + groups[1]))
        other = next(item for item in registered.observations if item != complete)
        self.assertEqual(set(other.transition_ids), set(groups[2]))
        self.assertEqual(other.independent_support_region_count, 1)
        self.assertGreater(registered.work_receipt.family_compatibility_evaluation_count, 0)
        self.assertEqual(set().union(*(set(item.transition_ids) for item in registered.observations)),
                         set().union(*map(set, groups)))

    def test_fragment_compatible_with_two_cross_anchors_remains_independent(self) -> None:
        measurement = self._separated_track_measurement((100.0, 101.5, 103.0))
        groups = (
            tuple(ObservationId(f"transition:{index}:0") for index in range(3, 9)),
            tuple(ObservationId(f"transition:{index}:2") for index in range(3, 9)),
            tuple(ObservationId(f"transition:{index}:1") for index in range(3)),
        )
        registered = self._register_top_transition_groups(measurement, groups)
        conditional_ids = {item.observation_id for item in registered.top_bindings
                           if item.conditional_family_ids}
        self.assertEqual({frozenset(item.transition_ids) for item in registered.observations
                          if item.observation_id not in conditional_ids},
                         set(map(frozenset, groups)))
        self.assertEqual(sorted(item.independent_support_region_count
                                for item in registered.observations
                                if item.observation_id not in conditional_ids), [1, 2, 2])
        self.assertEqual({frozenset(item.transition_ids) for item in registered.observations
                          if item.observation_id in conditional_ids},
                         {frozenset(groups[0] + groups[2]), frozenset(groups[1] + groups[2])})
        self.assertEqual(len(conditional_ids), 2)
        self.assertTrue(all(item.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL
                            for item in registered.family_resolutions))
        with self.assertRaisesRegex(ValueError, "conditional family permission"):
            replace(registered, top_bindings=tuple(
                replace(item, conditional_family_ids=()) for item in registered.top_bindings
            ))
        atom = next(item for item in registered.observations
                    if item.observation_id not in conditional_ids)
        with self.assertRaisesRegex(ValueError, "canonical atom"):
            replace(registered, observations=tuple(item for item in registered.observations if item != atom))
        lane = {
            "lane_id": "lane:0",
            "cross_registration_work": typed_read_model(registered.work_receipt),
            "observations": {
                "cross_boundary_family_resolutions": typed_read_model(registered.family_resolutions),
                "raw_top_bottom_lines": typed_read_model(registered.observations),
                "registered_top_bottom_bindings": typed_read_model(registered.top_bindings),
            },
        }
        queries = [typed_read_model(measurement)]
        # External reports retain run-local identities; validation must not
        # recreate their ordinal allocation in a different process scope.
        with source_identity_scope():
            lane['cross_competition'] = {'receipt': {
                'registered_top_run_count': registered.registered_top_run_count,
                'registered_bottom_run_count': registered.registered_bottom_run_count}}
            _validate_cross_measurement_support(lane, queries)
        invalid = deepcopy(lane)
        invalid["observations"]["cross_boundary_family_resolutions"][0]["member_transition_groups"][0].pop()
        with self.assertRaises(ValueError):
            _validate_cross_measurement_support(invalid, queries)
        invalid = deepcopy(lane)
        for item in invalid["observations"]["registered_top_bottom_bindings"]:
            item["conditional_family_ids"] = []
        with self.assertRaisesRegex(ValueError, "conditional family permission"):
            _validate_cross_measurement_support(invalid, queries)
        for item in invalid["observations"]["cross_boundary_family_resolutions"]:
            item["use"] = CrossBoundaryFamilyUse.CANONICAL_REGISTRATION.value
        with self.assertRaisesRegex(ValueError, "did not consume its members"):
            _validate_cross_measurement_support(invalid, queries)

    def test_unique_cross_fragments_cannot_be_cherry_picked_after_union_failure(self) -> None:
        measurement = self._separated_track_measurement((98.0, 100.0, 102.0))
        groups = (
            tuple(ObservationId(f"transition:{index}:1") for index in range(3, 9)),
            tuple(ObservationId(f"transition:{index}:0") for index in range(3)),
            tuple(ObservationId(f"transition:{index}:2") for index in range(3)),
        )
        registered = self._register_top_transition_groups(measurement, groups)
        self.assertEqual({frozenset(item.transition_ids) for item in registered.observations},
                         set(map(frozenset, groups)))
        self.assertEqual(len(registered.family_resolutions), 1)
        family = registered.family_resolutions[0]
        self.assertEqual(family.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(set(family.member_transition_ids), set().union(*map(set, groups)))

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
        self.assertEqual(replace(registered.work_receipt, membership=None), CrossRegistrationWorkReceipt(3, 2, 2, 2))
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
                registered_top_run_count=registered.registered_top_run_count,
                registered_bottom_run_count=registered.registered_bottom_run_count,
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

    def test_original_observation_cannot_be_relabelled_as_unperformed_refinement(self) -> None:
        registered = self._registered_top_families((100.0,) * 12, ((0, 1, 2),))
        self.assertEqual(registered.fit_attempt_count, 1)
        self.assertIsNotNone(registered.membership_receipt)
        with self.assertRaisesRegex(ValueError, 'actual refinement work'):
            replace(registered,
                    top_bindings=tuple(replace(binding, evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT)
                                       for binding in registered.top_bindings),
                    membership_receipt=replace(registered.membership_receipt, original_observation_ids=()))

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
                "cross_boundary_family_resolutions": typed_read_model(registered.family_resolutions),
                "raw_top_bottom_lines": typed_read_model(registered.observations),
                "registered_top_bottom_bindings": typed_read_model(registered.top_bindings),
            },
        }
        queries = [typed_read_model(make_side_measurement_set(((100.0,),) * 12))]
        lane['cross_competition'] = {'receipt': {
            'registered_top_run_count': registered.registered_top_run_count,
            'registered_bottom_run_count': registered.registered_bottom_run_count}}
        _validate_cross_measurement_support(lane, queries)
        self.assertIsNotNone(registered.observations[0].physical_line_region)
        altered = replace(binding, physical_line_region=None)
        with self.assertRaisesRegex(ValueError, 'measured line region'):
            replace(registered, top_bindings=(altered,))
        for replacement in (None, {'reference_trace_px': 0.0, 'vertices': [[100.0, 0.0]]}):
            invalid_region = deepcopy(lane)
            for key in ('raw_top_bottom_lines', 'registered_top_bottom_bindings'):
                invalid_region['observations'][key][0]['physical_line_region'] = replacement
            with self.subTest(region=replacement), self.assertRaisesRegex(ValueError, 'not reproducible'):
                _validate_cross_measurement_support(invalid_region, queries)
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
        for field, value in (
            ('trace_position_intervals_px', []),
            ('fit_interval_px', {'minimum': 100.0, 'maximum': 100.0}),
            ('fit_direction_interval_degrees', {'minimum': 0.0, 'maximum': 0.0}),
            ('observed_direction_interval_degrees', {'minimum': -4.0, 'maximum': 4.0}),
            ('physical_line_region', None),
        ):
            altered_fit = deepcopy(fit)
            self.assertNotEqual(altered_fit['direct_bindings'][0][field], value)
            altered_fit['direct_bindings'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'original measured'):
                _validate_cross_fit_binding_support(altered_fit, registered_report)
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
            "trace_position_intervals_px": [{"minimum": 20.0, "maximum": 21.0}] * 3,
            "full_position_interval_px": {"minimum": 20.0, "maximum": 21.0},
            "fit_position_interval_px": {"minimum": 20.5, "maximum": 20.5},
            "fit_residual_px": 0.0,
            "source_spanning_continuous": True,
            "canonical_direction_degrees": 0.0,
            "fit_direction_interval_degrees": {"minimum": -0.05, "maximum": 0.05},
            "full_direction_interval_degrees": {"minimum": -0.1, "maximum": 0.1},
            "observed_direction_interval_degrees": observed,
        } for identity, observed in (
            ("coarse-minimum", {"minimum": -0.2, "maximum": 0.3}),
            ("coarse-maximum", {"minimum": -0.4, "maximum": 0.2}),
        )]
        pair_id = "coarse-enclosing-pair:coarse-minimum:coarse-maximum"
        bindings = [{
            **track, "role": role, "role_authorized": False,
            "coordinate_interval_px": track["full_position_interval_px"],
            "full_interval_px": track["full_position_interval_px"],
            "fit_interval_px": track["fit_position_interval_px"],
            "run_id": f"coarse-enclosing:{track['observation_id']}",
            "enclosing_pair_id": pair_id,
            "conditional_family_ids": [],
        } for role, track in zip(("top", "bottom"), tracks)]
        lane = {
            "lane_id": "lane:0",
            "cross_registration_work": typed_read_model(CrossRegistrationWorkReceipt(0, 0, 0)),
            "search": {"coarse_strip_support": {
                "enclosing_support": {"minimum_track": tracks[0], "maximum_track": tracks[1]},
                "shared_direction": {
                    **{field: tracks[0][field] for field in (
                        "trace_coordinates_px", "canonical_direction_degrees",
                        "fit_direction_interval_degrees", "full_direction_interval_degrees")},
                    "observation_ids": [track["observation_id"] for track in tracks],
                    "observed_direction_interval_degrees": {"minimum": -0.4, "maximum": 0.3},
                },
            }},
            "observations": {
                "cross_boundary_family_resolutions": [],
                "raw_top_bottom_lines": [],
                "registered_top_bottom_bindings": bindings,
            },
        }
        self.assertEqual(len(_validate_cross_measurement_support(lane, [])), 2)
        invalid = deepcopy(lane)
        invalid["search"]["coarse_strip_support"]["shared_direction"]["trace_coordinates_px"].append(150.0)
        with self.assertRaisesRegex(ValueError, "side provenance"):
            _validate_cross_measurement_support(invalid, [])
        for observed in (
            {"minimum": -0.2, "maximum": 0.3},
            {"minimum": -0.5, "maximum": 0.4},
        ):
            invalid = deepcopy(lane)
            invalid["search"]["coarse_strip_support"]["shared_direction"][
                "observed_direction_interval_degrees"
            ] = observed
            with self.subTest(summary=observed), self.assertRaisesRegex(ValueError, "side provenance"):
                _validate_cross_measurement_support(invalid, [])
        for observed in (
            {"minimum": -0.1, "maximum": 0.1},
            tracks[1]["observed_direction_interval_degrees"],
            {"minimum": -0.4, "maximum": 0.3},
        ):
            invalid = deepcopy(lane)
            invalid["observations"]["registered_top_bottom_bindings"][0][
                "observed_direction_interval_degrees"
            ] = observed
            with self.subTest(observed=observed), self.assertRaisesRegex(ValueError, "coarse support"):
                _validate_cross_measurement_support(invalid, [])
        for field, value in (("role_authorized", True), ("independent_support_region_count", 2),
                             ("trace_position_intervals_px", [{"minimum": 19.0, "maximum": 22.0}] * 3),
                             ("full_interval_px", {"minimum": 20.2, "maximum": 20.8}),
                             ("full_direction_interval_degrees", {"minimum": -0.08, "maximum": 0.08})):
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

        self.assertEqual(len(registered.top_bindings), 3)
        self.assertEqual(len(registered.observations), 3)
        self.assertEqual(len(registered.family_resolutions), 2)
        original = next(item for item in registered.family_resolutions
                        if item.use == CrossBoundaryFamilyUse.CANONICAL_REGISTRATION)
        conditional = next(item for item in registered.family_resolutions
                           if item.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL)
        self.assertEqual(
            original.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertEqual(
            original.failure_kind,
            CrossBoundaryFamilyFailureKind
            .COMPLETE_TRANSITION_UNION_REFIT_REJECTED,
        )
        self.assertEqual(original.use, CrossBoundaryFamilyUse.CANONICAL_REGISTRATION)
        self.assertEqual(conditional.use, CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL)
        self.assertEqual(conditional.state, EvidenceState.SUPPORTED)
        self.assertEqual(original.member_transition_ids, conditional.member_transition_ids)
        self.assertEqual(original.refit_receipt, conditional.refit_receipt)
        self.assertEqual(len(original.refit_receipt.robust_retained_transition_ids), 8)
        self.assertEqual(len(conditional.member_transition_ids), 12)
        self.assertEqual(registered.work_receipt.constrained_fit_attempt_count, 1)
        self.assertGreater(registered.work_receipt.constrained_fit_edge_count, 0)
        self.assertEqual(sum(not item.conditional_family_ids for item in registered.top_bindings), 2)

    def test_complete_constrained_family_report_preserves_authority_and_work(self) -> None:
        coordinates = (100.0,) * 9 + (102.0,) * 2
        measurement = make_side_measurement_set(tuple((value,) for value in coordinates))
        groups = tuple(tuple(ObservationId(f"transition:{i}:0") for i in indices)
                       for indices in (range(9), range(9, 11)))
        registered = self._register_top_transition_groups(measurement, groups)
        original = next(item for item in registered.family_resolutions
                        if item.use == CrossBoundaryFamilyUse.CANONICAL_REGISTRATION)
        conditional = next(item for item in registered.family_resolutions
                           if item.use == CrossBoundaryFamilyUse.CONDITIONAL_PROPOSAL)
        self.assertEqual(len(original.refit_receipt.robust_retained_transition_ids), 9)
        self.assertEqual(len(registered.observations), 3)
        self.assertEqual(registered.work_receipt.constrained_fit_attempt_count, 1)
        with self.assertRaisesRegex(ValueError, "numerical acceptance authority"):
            replace(conditional, use=CrossBoundaryFamilyUse.CANONICAL_REGISTRATION)
        lane = {
            "lane_id": "lane:0",
            "cross_registration_work": typed_read_model(registered.work_receipt),
            "observations": {
                "cross_boundary_family_resolutions": typed_read_model(registered.family_resolutions),
                "raw_top_bottom_lines": typed_read_model(registered.observations),
                "registered_top_bottom_bindings": typed_read_model(registered.top_bindings),
            },
        }
        queries = [typed_read_model(measurement)]
        lane['cross_competition'] = {'receipt': {
            'registered_top_run_count': registered.registered_top_run_count,
            'registered_bottom_run_count': registered.registered_bottom_run_count}}
        _validate_cross_measurement_support(lane, queries)
        for field in ("constrained_fit_attempt_count", "constrained_fit_edge_count", "constrained_fit_event_count"):
            invalid = deepcopy(lane)
            invalid["cross_registration_work"][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                _validate_cross_measurement_support(invalid, queries)
        for field in ("cost", "optimality_gap", "intercept"):
            invalid = deepcopy(lane)
            for family in invalid["observations"]["cross_boundary_family_resolutions"]:
                family["refit_receipt"]["constrained_evaluation"]["solution"][field] += 0.01
            with self.subTest(field=field), self.assertRaises(ValueError):
                _validate_cross_measurement_support(invalid, queries)
        invalid = deepcopy(lane)
        for family in invalid["observations"]["cross_boundary_family_resolutions"]:
            del family["refit_receipt"]["constrained_evaluation"]["work"]["event_count"]
        with self.assertRaisesRegex(ValueError, "work is incomplete"):
            _validate_cross_measurement_support(invalid, queries)

    def test_complete_constrained_family_keeps_empty_domain_failure(self) -> None:
        registered = self._registered_top_families(
            (100.0,) * 9 + (103.0,) * 2, (tuple(range(9)), (9, 10)),
        )
        self.assertEqual(len(registered.observations), 2)
        self.assertEqual(len(registered.family_resolutions), 0)
        self.assertEqual(registered.work_receipt.constrained_fit_attempt_count, 0)
        from x5crop.detection.photo_geometry.boundary_fitting import (
            fit_boundary_family, complete_boundary_family_proposal,
        )
        measurement = make_side_measurement_set(tuple((v,) for v in (100.0,) * 9 + (103.0,) * 2))
        family = fit_boundary_family(
            measurement, transition_ids=tuple(item.transition_id for item in measurement.transitions),
            role=BoundaryRole.TOP, source_axis_long=BoundaryAxis.Y,
            boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        proposal, receipt = complete_boundary_family_proposal(family)
        self.assertIsNone(proposal)
        evaluation = receipt.constrained_evaluation
        self.assertIsNone(evaluation.solution)
        self.assertEqual(evaluation.failure_kind.value, "physical_region_unavailable")
        self.assertGreater(evaluation.work.polygon_clip_count, 0)
        self.assertEqual(evaluation.work.edge_count, 0)

    def test_constrained_family_keeps_original_observation_and_run_id_allocation(self) -> None:
        from x5crop.detection.photo_geometry.physical_identity import physical_fact_id
        from x5crop.detection.photo_geometry import template_registration as owner

        def run():
            registered = self._registered_top_families(
                (100.0,) * 9 + (102.0,) * 2, (tuple(range(9)), (9, 10)),
            )
            later = tuple(physical_fact_id(prefix, "later") for prefix in (
                "format-role-bound-line", "registered-cross-run", "cross-boundary-family",
            ))
            originals = tuple(item for item in registered.top_bindings if not item.conditional_family_ids)
            return originals, later

        with source_identity_scope():
            actual = run()
        with source_identity_scope(), patch.object(
            owner, "complete_boundary_family_proposal", side_effect=lambda family: (None, family.receipt),
        ):
            original = run()
        self.assertEqual(actual, original)

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
