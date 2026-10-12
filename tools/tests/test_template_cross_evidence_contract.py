from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from tools.tests.template_test_support import placement_direction
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFailureKind,
    CrossFitStatus,
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    CrossLongitudinalProjectionBasis,
    CrossPairSupportMode,
    CrossRetainedProposalBasis,
    CrossWinnerBasis,
    CrossRoleBinding,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.trace_support import source_spanning_continuous_trace_support
from tools.tests.cross_fixture_support import aspect_input, binding, template


class TemplateCrossEvidenceContractTest(unittest.TestCase):
    def test_source_direction_rejects_a_locally_fitted_wrong_slope(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(236.0, 244.0),
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "direction-matched-top",
                        100.0,
                        angle=-0.1,
                        angle_interval=FiniteInterval(-0.15, -0.05),
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "wrong-fit-wide-full-top",
                        104.0,
                        angle=0.4,
                        angle_interval=FiniteInterval(0.3, 0.5),
                        full_angle_interval=FiniteInterval(-0.1, 0.5),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "direction-matched-bottom",
                        340.0,
                        angle=-0.1,
                        angle_interval=FiniteInterval(-0.15, -0.05),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.bound_observation_ids,
            (
                ObservationId("observation:direction-matched-top"),
                ObservationId("observation:direction-matched-bottom"),
            ),
        )

    def test_touching_frame_domains_are_valid_but_overlap_is_not(self) -> None:
        aspect_input(
            template=template(count=2),
            fixed_height_px=240.0,
            longitudinal_support_domain_groups_px=((
                FiniteInterval(0.0, 100.0),
                FiniteInterval(100.0, 200.0),
            ),),
        )
        with self.assertRaisesRegex(
            ValueError,
            "longitudinal support domains",
        ):
            aspect_input(
                template=template(count=2),
                fixed_height_px=240.0,
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(0.0, 101.0),
                    FiniteInterval(100.0, 200.0),
                ),),
            )

    def test_source_spanning_reaches_both_registered_domain_ends(self) -> None:
        queried = tuple(range(0, 101, 10))
        self.assertTrue(
            source_spanning_continuous_trace_support(
                queried,
                tuple(range(10, 91, 10)),
                spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
        )
        self.assertFalse(
            source_spanning_continuous_trace_support(
                queried,
                tuple(range(30, 71, 10)),
                spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
        )

    def test_measurement_registration_transfers_support_provenance(self) -> None:
        run = SimpleNamespace(
            role_hint=BoundaryRole.TOP,
            run_id="run:registered",
            trace_coordinates_px=(0, 50, 100),
            support_fraction=0.9,
            continuous_support_fraction=0.8,
        )
        observation = SimpleNamespace(
            role=BoundaryRole.TOP,
            observation_id=ObservationId("observation:registered"),
            coordinate_interval_px=FiniteInterval(99.0, 101.0),
            fit_residual_px=0.4,
            canonical_direction_degrees=0.1,
            fit_angle_interval_degrees=FiniteInterval(-0.1, 0.2),
            full_direction_interval_degrees=FiniteInterval(-0.2, 0.3),
            physical_line_region=None,
            independent_support_region_count=2,
            source_spanning_continuous=True,
            left_background_preference_fraction=0.0,
            right_background_preference_fraction=0.0,
        )
        registered = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=0.0,
        )
        self.assertEqual(registered.independent_support_region_count, 2)
        self.assertTrue(registered.source_spanning_continuous)

    def test_conditional_family_cannot_resolve_or_disambiguate_other_pairs(self) -> None:
        domains = (FiniteInterval(0, 20), FiniteInterval(40, 60), FiniteInterval(80, 100))
        def edge(role, name, position, traces):
            return binding(role, name, position, traces=traces,
                           independent_regions=2, source_spanning=False)
        a1 = edge(BoundaryRole.TOP, "a1", 100, (50, 90))
        a2 = edge(BoundaryRole.TOP, "a2", 200, (50, 90))
        b1 = edge(BoundaryRole.BOTTOM, "b1", 340, (10, 15))
        b2 = edge(BoundaryRole.BOTTOM, "b2", 440, (10, 15))
        conditional = replace(edge(BoundaryRole.TOP, "conditional", 95, (10, 15)),
                              conditional_family_ids=("conditional-family",))
        base = aspect_input(
            template=template(count=3), fixed_height_px=FiniteInterval(230, 250),
            registered_trace_coordinates_px=(10, 15, 50, 90),
            longitudinal_support_domain_groups_px=(domains,),
            top_bindings=(a1, a2), bottom_bindings=(b1, b2),
        )
        for value in (base, replace(base, top_bindings=(a1, a2, conditional))):
            result = fit_template_cross(value)
            self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
            self.assertEqual(result.failure_kind, CrossFailureKind.NON_EQUIVALENT_FITS)
        result = fit_template_cross(replace(
            base, top_bindings=(replace(a1, conditional_family_ids=("family",)),),
            bottom_bindings=(b1,),
        ))
        self.assertIsNotNone(result.best)
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.conditional_proposal)
        self.assertEqual(result.conditional_proposal_failure_kind, CrossFailureKind.FAMILY_ASSIGNMENT_UNRESOLVED)
        with self.assertRaisesRegex(ValueError, "conditional Cross family|complete support ledger"):
            replace(result, best=result.conditional_proposal, status=CrossFitStatus.RESOLVED,
                    winner_basis=CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT, failure_kind=None)

    def test_conditional_view_preserves_canonical_result_and_enumerates_pairs_once(self) -> None:
        from x5crop.detection.photo_geometry import template_cross as owner

        top = binding(BoundaryRole.TOP, "canonical-top", 100)
        bottom = binding(BoundaryRole.BOTTOM, "canonical-bottom", 340)
        base = aspect_input(
            template=template(), fixed_height_px=FiniteInterval(230, 250),
            top_bindings=(top,), bottom_bindings=(bottom,),
        )
        canonical = fit_template_cross(base)
        conditional = replace(
            binding(BoundaryRole.TOP, "conditional-top", 95),
            conditional_family_ids=("family",),
        )
        with patch.object(owner, "_direct_candidate", wraps=owner._direct_candidate) as pairs:
            result = fit_template_cross(replace(base, top_bindings=(top, conditional)))
        identities = [(call.args[0].observation_id, call.args[1].observation_id)
                      for call in pairs.call_args_list]
        self.assertEqual(len(identities), 2)
        self.assertEqual(len(set(identities)), 2)
        self.assertEqual(replace(
            result, receipt=canonical.receipt, conditional_proposal=None,
            conditional_proposal_failure_kind=None,
            conditional_fit_groups=(),
        ), canonical)
        self.assertGreater(result.receipt.evaluated_fit_count, canonical.receipt.evaluated_fit_count)
        bounded = replace(base, maximum_fitted_observations=2)
        self.assertEqual(fit_template_cross(bounded).status, canonical.status)
        exceeded = fit_template_cross(replace(bounded, top_bindings=(top, conditional)))
        self.assertEqual(exceeded.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertIsNone(exceeded.best)
        self.assertIsNone(exceeded.conditional_proposal)

    def test_all_supported_cross_groups_survive_display_truncation(self) -> None:
        tops = tuple(binding(BoundaryRole.TOP, f"top-{i}", 100 + i) for i in range(4))
        conditional = replace(binding(BoundaryRole.TOP, "conditional", 104),
                              conditional_family_ids=("family",))
        inputs = aspect_input(
            template=template(), fixed_height_px=FiniteInterval(230, 250),
            top_bindings=(*tops, conditional),
            bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340),),
        )
        result = fit_template_cross(inputs)
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, CrossFailureKind.NON_EQUIVALENT_FITS)
        self.assertEqual(len(result.fit_groups), 4)
        self.assertEqual(len(result.conditional_fit_groups), 5)
        self.assertTrue(all(g.independently_supported for g in (*result.fit_groups, *result.conditional_fit_groups)))
        self.assertEqual({g.fit.direct_bindings[0].observation_id for g in result.fit_groups},
                         {b.observation_id for b in tops})
        self.assertTrue(any(g.fit not in (result.best, result.runner_up)
                            for g in result.fit_groups))
        self.assertEqual(sum(bool(g.fit.conditional_family_ids) for g in result.conditional_fit_groups), 1)
        exceeded = fit_template_cross(replace(inputs, maximum_evaluated_fits=4))
        self.assertEqual(exceeded.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(exceeded.fit_groups, ())
        self.assertEqual(exceeded.conditional_fit_groups, ())

    def test_retained_cross_groups_do_not_upgrade_missing_coverage(self) -> None:
        inputs = aspect_input(
            template=template(count=3), fixed_height_px=FiniteInterval(230, 250),
            registered_trace_coordinates_px=(10, 15, 50, 90),
            longitudinal_support_domain_groups_px=((FiniteInterval(0, 20), FiniteInterval(40, 60), FiniteInterval(80, 100)),),
            top_bindings=tuple(binding(BoundaryRole.TOP, f"local-{i}", 100 + i,
                traces=(10, 15), independent_regions=2, source_spanning=False) for i in range(3)),
            bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340,
                traces=(10, 15), independent_regions=2, source_spanning=False),),
        )
        result = fit_template_cross(inputs)
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(len(result.fit_groups), 3)
        self.assertFalse(any(g.independently_supported for g in result.fit_groups))
        with self.assertRaisesRegex(ValueError, "repeats a binding group"):
            replace(result, fit_groups=(*result.fit_groups, result.fit_groups[0]))

    def test_cross_group_report_rejects_lost_or_upgraded_group_evidence(self) -> None:
        from copy import deepcopy
        from tools.regression.report_validation import _validate_cross_fit_groups
        from x5crop.report.read_models import typed_read_model

        result = fit_template_cross(aspect_input(
            template=template(), fixed_height_px=FiniteInterval(230, 250),
            top_bindings=tuple(binding(BoundaryRole.TOP, f"top-{i}", 100 + i) for i in range(3)),
            bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340),),
        ))
        record = typed_read_model(result)
        self.assertEqual(len(_validate_cross_fit_groups(record)), 3)
        invalid = deepcopy(record)
        del invalid["fit_groups"]
        with self.assertRaisesRegex(ValueError, "group list"):
            _validate_cross_fit_groups(invalid)
        invalid = deepcopy(record)
        invalid["fit_groups"].append(deepcopy(invalid["fit_groups"][0]))
        with self.assertRaisesRegex(ValueError, "repeats a binding group"):
            _validate_cross_fit_groups(invalid)
        invalid = deepcopy(record)
        invalid["fit_groups"][0]["fit"]["longitudinal_projection_authority"]["state"] = "unavailable"
        with self.assertRaisesRegex(ValueError, "independent spatial coverage"):
            _validate_cross_fit_groups(invalid)
        invalid = deepcopy(record)
        invalid["status"] = CrossFitStatus.BOUND_EXCEEDED.value
        with self.assertRaisesRegex(ValueError, "partial group set"):
            _validate_cross_fit_groups(invalid)

    def test_unique_direct_pair_wins(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT,
        )
        self.assertIsNotNone(result.best)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(result.best.boundary_use, OutputBoundaryUse.APERTURE_PAIR)
        self.assertEqual(result.best.bound_observation_ids, (
            ObservationId("observation:top"),
            ObservationId("observation:bottom"),
        ))
        self.assertEqual(result.receipt.compatible_pair_count, 1)
        self.assertEqual(
            result.best.line_projection_basis,
            CrossLineProjectionBasis.COMPLETE_PHYSICAL_DIRECTION,
        )
        self.assertEqual(
            result.best.height_projection_basis,
            CrossHeightProjectionBasis.COMPLETE_PHYSICAL_INTERVAL,
        )
        with self.assertRaisesRegex(
            ValueError,
            "resolved cross requires complete physical line projection",
        ):
            replace(
                result,
                best=replace(
                    result.best,
                    line_projection_basis=(
                        CrossLineProjectionBasis
                        .RETAINED_REVIEW_STATISTICAL_FIT
                    ),
                ),
            )

    def test_complementary_domains_close_unique_direct_pair(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 55, 90),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "complementary-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "complementary-bottom",
                        340.0,
                        traces=(55, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.pair_support_mode,
            CrossPairSupportMode.COMPLEMENTARY_DOMAINS,
        )
        self.assertEqual(result.best.shared_trace_support_count, 0)
        self.assertEqual(
            result.best.longitudinal_projection_authority.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            result.best.longitudinal_projection_authority.basis,
            CrossLongitudinalProjectionBasis.COMPLETE_TEMPLATE_DOMAINS,
        )
        self.assertEqual(
            result.best.longitudinal_projection_authority
            .supported_domain_ordinals_by_candidate[0],
            (1, 2, 3),
        )

    def test_inward_local_alternative_does_not_block_outer_complementary_pair(
            self,
        ) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                registered_trace_coordinates_px=(10, 15, 50, 55, 90),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "outer-complementary-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "outer-complementary-bottom",
                        340.0,
                        traces=(55, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "inward-local-bottom",
                        335.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.bound_observation_ids,
            (
                ObservationId("observation:outer-complementary-top"),
                ObservationId("observation:outer-complementary-bottom"),
            ),
        )

    def test_outward_local_alternative_blocks_complementary_pair(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                registered_trace_coordinates_px=(10, 15, 50, 90),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "inward-complementary-top",
                        100.0,
                        traces=(50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "outward-local-top",
                        95.0,
                        traces=(10, 15),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "shared-bottom",
                        340.0,
                        traces=(10, 15),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE,
        )

    def test_source_spanning_side_preserves_an_already_authorized_shared_pair(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        traces = (10, 50, 90, 130, 170, 210)
        for spanning, whole_role, partial_traces in (
            (spanning, role, partial)
            for spanning in (False, True)
            for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM)
            for partial in ((90, 130, 170, 210), (90, 170))
        ):
            with self.subTest(spanning=spanning, whole_role=whole_role, partial=partial_traces):
                result = fit_template_cross(
                    aspect_input(
                        template=template(count=6),
                        fixed_height_px=FiniteInterval(230.0, 250.0),
                        canonical_fixed_height_px=245.0,
                        registered_trace_coordinates_px=traces,
                        longitudinal_support_domain_groups_px=(domains,),
                        top_bindings=(binding(
                            BoundaryRole.TOP, "whole-top", 100.0,
                            traces=traces if whole_role == BoundaryRole.TOP else partial_traces,
                            independent_regions=3 if whole_role == BoundaryRole.TOP else 2,
                            source_spanning=spanning and whole_role == BoundaryRole.TOP,
                        ),),
                        bottom_bindings=(binding(
                            BoundaryRole.BOTTOM, "shared-bottom", 338.0,
                            traces=traces if whole_role == BoundaryRole.BOTTOM else partial_traces,
                            independent_regions=3 if whole_role == BoundaryRole.BOTTOM else 2,
                            source_spanning=spanning and whole_role == BoundaryRole.BOTTOM,
                        ),),
                    )
                )
                self.assertEqual(result.status, CrossFitStatus.RESOLVED)
                self.assertIsNotNone(result.best)
                self.assertTrue(result.best.direct_pair)
                self.assertEqual(result.best.pair_support_mode, CrossPairSupportMode.SHARED_TRACES)
                self.assertEqual(result.best.shared_trace_support_count, len(partial_traces))
                self.assertEqual(result.best.longitudinal_projection_authority.state, EvidenceState.SUPPORTED)
                self.assertAlmostEqual(result.best.bottom_canonical_px - result.best.top_canonical_px, 238.0)

    def test_source_spanning_side_keeps_competing_authorized_shared_pairs(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        traces = (10, 50, 90, 130, 170, 210)
        result = fit_template_cross(aspect_input(
            template=template(count=6), fixed_height_px=FiniteInterval(230.0, 250.0),
            registered_trace_coordinates_px=traces,
            longitudinal_support_domain_groups_px=(domains,),
            top_bindings=(binding(BoundaryRole.TOP, "whole-top", 100.0,
                                  traces=traces, independent_regions=3, source_spanning=True),),
            bottom_bindings=tuple(
                binding(BoundaryRole.BOTTOM, f"shared-bottom:{coordinate}", coordinate,
                        traces=(90, 130, 170, 210), independent_regions=2, source_spanning=False)
                for coordinate in (338.0, 342.0)
            ),
        ))
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, CrossFailureKind.NON_EQUIVALENT_FITS)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        self.assertTrue(result.best.direct_pair)
        self.assertTrue(result.runner_up.direct_pair)
        self.assertNotEqual(result.best.bound_observation_ids, result.runner_up.bound_observation_ids)

    def test_shared_pair_with_spanning_side_keeps_outward_local_counterevidence(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        registered_traces = (10, 15, 50, 90, 130, 170, 210)
        for whole_role in (BoundaryRole.TOP, BoundaryRole.BOTTOM):
            for shared_count in (1, 2):
                with self.subTest(whole_role=whole_role, shared_count=shared_count):
                    whole = binding(
                        whole_role, "whole-side",
                        100.0 if whole_role == BoundaryRole.TOP else 342.0,
                        traces=(
                            registered_traces if shared_count == 2
                            else (10, 50, 90, 130, 170, 210)
                        ),
                        independent_regions=3, source_spanning=True,
                    )
                    opposite_role = (
                        BoundaryRole.BOTTOM if whole_role == BoundaryRole.TOP
                        else BoundaryRole.TOP
                    )
                    opposites = (
                        binding(
                            opposite_role, "shared-opposite",
                            338.0 if whole_role == BoundaryRole.TOP else 104.0,
                            traces=(90, 130, 170, 210),
                            independent_regions=2, source_spanning=False,
                        ),
                        binding(
                            opposite_role, "outer-local-opposite",
                            342.0 if whole_role == BoundaryRole.TOP else 100.0,
                            traces=(10, 15),
                            independent_regions=2, source_spanning=False,
                        ),
                    )
                    result = fit_template_cross(aspect_input(
                        template=template(count=6),
                        fixed_height_px=FiniteInterval(230.0, 250.0),
                        registered_trace_coordinates_px=registered_traces,
                        longitudinal_support_domain_groups_px=(domains,),
                        top_bindings=(whole,) if whole_role == BoundaryRole.TOP else opposites,
                        bottom_bindings=opposites if whole_role == BoundaryRole.TOP else (whole,),
                    ))
                    self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                    self.assertEqual(
                        result.failure_kind,
                        CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE,
                    )

    def test_source_spanning_pairs_remain_alternatives_not_local_counterevidence(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        traces = (10, 50, 90, 130, 170, 210)
        for opposite_spanning in (False, True):
            with self.subTest(opposite_spanning=opposite_spanning):
                result = fit_template_cross(aspect_input(
                    template=template(count=6),
                    fixed_height_px=FiniteInterval(230.0, 250.0),
                    registered_trace_coordinates_px=traces,
                    longitudinal_support_domain_groups_px=(domains,),
                    top_bindings=(binding(
                        BoundaryRole.TOP, "whole-top", 100.0,
                        traces=traces, independent_regions=3, source_spanning=True,
                    ),),
                    bottom_bindings=tuple(
                        binding(
                            BoundaryRole.BOTTOM, f"whole-bottom:{coordinate}", coordinate,
                            traces=traces, independent_regions=3,
                            source_spanning=opposite_spanning,
                        )
                        for coordinate in (338.0, 342.0)
                    ),
                ))
                self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                self.assertEqual(result.failure_kind, CrossFailureKind.NON_EQUIVALENT_FITS)
                self.assertTrue(result.best.direct_pair)
                self.assertTrue(result.runner_up.direct_pair)

    def test_source_spanning_side_does_not_export_local_opposite(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=245.0,
                registered_trace_coordinates_px=(10, 15, 50, 90),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "source-spanning-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=3,
                        source_spanning=True,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-opposite-bottom",
                        338.0,
                        traces=(10, 15),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.bound_observation_ids,
            (ObservationId("observation:source-spanning-top"),),
        )
        self.assertAlmostEqual(
            result.best.bottom_canonical_px - result.best.top_canonical_px,
            240.0,
        )

    def test_complementary_domains_require_complete_union(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 55, 60),
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "incomplete-complementary-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "incomplete-complementary-bottom",
                        340.0,
                        traces=(55, 60),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNone(result.runner_up)
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE,
        )
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE,
        )
        assert result.best is not None
        self.assertEqual(
            result.best.line_projection_basis,
            CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT,
        )
        self.assertEqual(
            result.best.height_projection_basis,
            CrossHeightProjectionBasis.RETAINED_REVIEW_CANONICAL_HEIGHT,
        )
        with self.assertRaisesRegex(
            ValueError,
            "retained cross proposal has invalid height projection",
        ):
            replace(
                result,
                best=replace(
                    result.best,
                    height_projection_basis=(
                        CrossHeightProjectionBasis
                        .COMPLETE_PHYSICAL_INTERVAL
                    ),
                ),
            )
        with self.assertRaisesRegex(
            ValueError,
            "retained cross proposal requires statistical-fit projection",
        ):
            replace(
                result,
                best=replace(
                    result.best,
                    line_projection_basis=(
                        CrossLineProjectionBasis
                        .COMPLETE_PHYSICAL_DIRECTION
                    ),
                ),
            )

    def test_multiple_complementary_domain_pairs_remain_unresolved(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(239.0, 241.0),
                registered_trace_coordinates_px=(10, 50, 55, 90),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "ambiguous-complementary-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "ambiguous-complementary-bottom-a",
                        339.0,
                        traces=(55, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "ambiguous-complementary-bottom-b",
                        341.0,
                        traces=(55, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.NON_EQUIVALENT_FITS,
        )
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(
            result.best.pair_support_mode,
            CrossPairSupportMode.COMPLEMENTARY_DOMAINS,
        )
        self.assertEqual(
            result.runner_up.pair_support_mode,
            CrossPairSupportMode.COMPLEMENTARY_DOMAINS,
        )
        self.assertIsNone(result.retained_proposal_basis)
