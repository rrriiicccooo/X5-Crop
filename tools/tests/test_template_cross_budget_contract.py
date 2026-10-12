from __future__ import annotations

import unittest
from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFailureKind,
    CrossFitStatus,
    CrossRetainedProposalBasis,
)
from tools.tests.cross_fixture_support import aspect_input, binding, template


class TemplateCrossBudgetContractTest(unittest.TestCase):
    def test_receipt_bound_overflow_is_explicit(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340.0),),
                maximum_fitted_observations=1,
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        with self.assertRaises(ValueError):
            result.receipt.__class__(
                **{
                    **result.receipt.__dict__,
                    "evaluated_fit_count": result.receipt.evaluated_fit_bound + 1,
                }
            ).validate_bounds()

    def test_solver_limit_keeps_all_512_inputs_and_counts_added_coarse_pair(self) -> None:
        originals = tuple(binding(
            BoundaryRole.TOP, f"measured-{index}", 100.0,
            role_authorized=False,
        ) for index in range(512))
        options = dict(
            template=template(), fixed_height_px=240.0,
            maximum_registered_runs_per_role=512,
            maximum_fitted_observations=512,
        )
        exact = fit_template_cross(aspect_input(**options, top_bindings=originals))
        self.assertNotEqual(exact.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(exact.receipt.fitted_observation_count, 512)
        coarse_top = binding(BoundaryRole.TOP, "coarse-top", 100.0, role_authorized=False)
        coarse_bottom = binding(BoundaryRole.BOTTOM, "coarse-bottom", 340.0, role_authorized=False)
        overflow = fit_template_cross(aspect_input(
            **options, top_bindings=(*originals[:511], coarse_top), bottom_bindings=(coarse_bottom,),
        ))
        self.assertEqual(overflow.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(overflow.receipt.fitted_observation_count, 513)
        self.assertIsNone(overflow.best)
        self.assertEqual(overflow.receipt.registered_top_run_count, 512)

    def test_registration_overflow_is_a_typed_cross_result(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                registered_top_run_count=513,
                registered_bottom_run_count=0,
                maximum_registered_runs_per_role=512,
                top_bindings=(binding(BoundaryRole.TOP, "one-retained", 100.0),),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.reason, "cross registration bound exceeded")
        self.assertEqual(result.receipt.registered_top_run_count, 513)
        self.assertEqual(result.receipt.registered_bottom_run_count, 0)
        self.assertEqual(result.receipt.registered_run_bound_per_role, 512)

    def test_independent_cross_roles_do_not_share_registration_quota(
            self,
        ) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top", 100.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom", 340.0),
                ),
                registered_top_run_count=393,
                registered_bottom_run_count=185,
                maximum_registered_runs_per_role=512,
            )
        )

        self.assertNotEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.registered_top_run_count, 393)
        self.assertEqual(result.receipt.registered_bottom_run_count, 185)
        self.assertEqual(result.receipt.total_registered_run_count, 578)

    def test_input_receipt_includes_late_registered_bindings(self) -> None:
        cross_input = aspect_input(
            template=template(),
            fixed_height_px=240.0,
            top_bindings=(binding(BoundaryRole.TOP, "coarse-top", 100.0),),
            registered_top_run_count=0,
            registered_bottom_run_count=0,
            fitted_observation_count=0,
        )

        self.assertEqual(cross_input.registered_top_run_count, 1)
        self.assertEqual(cross_input.registered_bottom_run_count, 0)
        self.assertEqual(cross_input.fitted_observation_count, 1)

    def test_direction_provenance_retains_selected_observations_and_interval(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top",
                        100.0,
                        angle=0.05,
                        angle_interval=FiniteInterval(-0.2, 0.2),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bottom",
                        340.0,
                        angle=0.1,
                        angle_interval=FiniteInterval(-0.1, 0.3),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        direction = result.best.selected_direction
        self.assertEqual(
            set(direction.selected_observation_ids),
            {
                ObservationId("observation:top"),
                ObservationId("observation:bottom"),
            },
        )
        self.assertEqual(direction.full_angle_interval_degrees, FiniteInterval(-0.2, 0.3))
        self.assertEqual(
            result.best.direction_provenance_ids,
            (
                ObservationId("observation:top"),
                ObservationId("observation:bottom"),
            ),
        )

    def test_local_opposite_edge_does_not_expand_source_direction(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "spanning-top",
                        100.0,
                        angle=-0.15,
                        angle_interval=FiniteInterval(-0.2, -0.1),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        340.0,
                        angle=-0.1,
                        angle_interval=FiniteInterval(-1.0, 0.2),
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.2, -0.1),
        )

    def test_missing_direction_cannot_resolve(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top-no-direction",
                        100.0,
                        angle=None,
                        angle_interval=None,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bottom-no-direction",
                        340.0,
                        angle=None,
                        angle_interval=None,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.reason, "cross direction unavailable")

    def test_single_side_requires_spanning_independent_regions(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "isolated-top",
                        100.0,
                        independent_regions=1,
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

    def test_support_and_residual_do_not_choose_discrete_groups(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "high-support-top",
                        100.0,
                        support=1.0,
                        residual=0.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "low-support-top",
                        500.0,
                        support=0.2,
                        residual=10.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "high-support-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "low-support-bottom",
                        740.0,
                        support=0.2,
                        residual=10.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .OUTERMOST_ADMISSIBLE_REGISTERED_ROLE_PAIR,
        )
        assert result.best is not None
        assert result.runner_up is not None
        self.assertTrue(result.best.direct_pair)
        self.assertTrue(result.runner_up.direct_pair)
        self.assertEqual(
            result.best.bound_observation_ids,
            (
                ObservationId("observation:high-support-top"),
                ObservationId("observation:high-support-bottom"),
            ),
        )
        self.assertEqual(
            result.runner_up.bound_observation_ids,
            (
                ObservationId("observation:low-support-top"),
                ObservationId("observation:low-support-bottom"),
            ),
        )
        self.assertEqual(result.receipt.single_side_inference_count, 0)
        # Every attempted support proof, including rejected pairs, is charged.
        self.assertEqual(result.receipt.evaluated_fit_count, 4)

    def test_unowned_local_pairs_refine_retained_grid_by_calibrated_height(
            self,
        ) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(239.0, 241.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "outer-top",
                        100.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "nearest-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "runner-bottom",
                        341.0,
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
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .OUTERMOST_ADMISSIBLE_REGISTERED_ROLE_PAIR,
        )
        assert result.best is not None
        assert result.runner_up is not None
        self.assertTrue(result.best.direct_pair)
        self.assertFalse(result.best.single_side_inferred)
        self.assertEqual(
            result.best.bound_observation_ids,
            (
                ObservationId("observation:outer-top"),
                ObservationId("observation:nearest-bottom"),
            ),
        )
        self.assertEqual(
            result.runner_up.bound_observation_ids,
            (
                ObservationId("observation:outer-top"),
                ObservationId("observation:runner-bottom"),
            ),
        )
        self.assertEqual(result.receipt.single_side_inference_count, 0)
        # Every attempted support proof, including rejected pairs, is charged.
        self.assertEqual(result.receipt.evaluated_fit_count, 4)

    def test_outermost_top_precedes_smaller_calibrated_height_shift(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "parallel-top",
                        98.0,
                        angle=0.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "exact-height-wrong-slope-top",
                        100.0,
                        angle=0.15,
                        angle_interval=FiniteInterval(-0.05, 0.25),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "shared-bottom",
                        340.0,
                        angle=0.0,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .OUTERMOST_ADMISSIBLE_REGISTERED_ROLE_PAIR,
        )
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(
            result.best.bound_observation_ids,
            (
                ObservationId("observation:parallel-top"),
                ObservationId("observation:shared-bottom"),
            ),
        )
        self.assertEqual(
            result.runner_up.bound_observation_ids,
            (
                ObservationId(
                    "observation:exact-height-wrong-slope-top"
                ),
                ObservationId("observation:shared-bottom"),
            ),
        )

    def test_support_across_three_template_frames_rejects_local_runner(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=4),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(5.0, 20.0),
                    FiniteInterval(25.0, 40.0),
                    FiniteInterval(45.0, 60.0),
                    FiniteInterval(65.0, 80.0),
                ),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "whole-top",
                        100.0,
                        traces=(10, 35, 55, 75),
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "local-top",
                        104.0,
                        traces=(35, 55),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "whole-bottom",
                        340.0,
                        traces=(10, 35, 55, 75),
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom",
                        344.0,
                        traces=(35, 55),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(result.best.independent_support_region_count, 3)
        self.assertEqual(
            set(result.best.bound_observation_ids),
            {
                ObservationId("observation:whole-top"),
                ObservationId("observation:whole-bottom"),
            },
        )

    def test_all_h_compatible_pairs_are_retained_until_bound(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(240.0, 242.0),
                maximum_compatible_pairs=2,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "wide-top",
                        100.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-a",
                        340.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-b",
                        341.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wide-bottom-c",
                        342.0,
                        angle_interval=FiniteInterval(-1.0, 1.0),
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.compatible_pair_count, 3)

    def test_staggered_trace_lattices_can_share_independent_regions(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top", 100.0, traces=(0, 50, 100)),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom", 340.0, traces=(1, 51, 101)),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertGreaterEqual(result.best.shared_trace_support_count, 2)
