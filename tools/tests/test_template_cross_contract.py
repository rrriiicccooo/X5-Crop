from __future__ import annotations

from dataclasses import replace
import unittest
from types import SimpleNamespace

from tools.tests.template_test_support import (
    cross_binding as binding,
    cross_template as template,
    placement_direction,
)
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import (
    calibrate_source_frame_height,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFitStatus,
    CrossHeightInferenceBasis,
    CrossPairSupportMode,
    CrossRetainedProposalBasis,
    CrossWinnerBasis,
    CrossRoleBinding,
    TemplateCrossInput as _TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    ApertureAspectRatioAuthority,
    ApertureAspectRatioFailureKind,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.trace_support import (
    source_spanning_continuous_trace_support,
)
from x5crop.formats import FramePhysicalSpec


def _interval(value: FiniteInterval | float) -> FiniteInterval:
    return value if isinstance(value, FiniteInterval) else FiniteInterval.exact(value)


def _supported_aspect_ratio(
    height: FiniteInterval | float,
) -> ApertureAspectRatioAuthority:
    interval = _interval(height)
    return ApertureAspectRatioAuthority(
        authority_id="test-aspect-ratio",
        state=EvidenceState.SUPPORTED,
        calibration_id="test-aspect-ratio-calibration",
        axis_guard_calibration_id="test-axis-guard-calibration",
        raw_width_over_height=PositiveInterval.exact(1.0),
        guarded_width_over_height=PositiveInterval.exact(1.0),
        width_guard_mm=0.1,
        height_guard_mm=0.1,
        width_guard_ratio=0.01,
        height_guard_ratio=0.01,
        scale_height_over_width=PositiveInterval.exact(1.0),
        source_width_px=interval,
        inferred_height_px=interval,
        effective_height_px=interval,
        canonical_height_px=interval.center,
        width_observation_ids=tuple(
            ObservationId(f"test-width:{index}") for index in range(4)
        ),
        minimum_output_expansion_mm=0.0,
        output_expansion_limit_mm=1.0,
        failure_kind=None,
        failure_detail=None,
    )


def aspect_input(**values) -> _TemplateCrossInput:
    height = values.get("fixed_height_px")
    if height is None:
        template_spec = values["template"]
        height = template_spec.frame_height_px
    values["aperture_aspect_ratio_authority"] = _supported_aspect_ratio(height)
    return _TemplateCrossInput(**values)


class TemplateCrossContractTest(unittest.TestCase):
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
            longitudinal_support_domains_px=(
                FiniteInterval(0.0, 100.0),
                FiniteInterval(100.0, 200.0),
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "longitudinal support domains",
        ):
            aspect_input(
                template=template(count=2),
                fixed_height_px=240.0,
                longitudinal_support_domains_px=(
                    FiniteInterval(0.0, 101.0),
                    FiniteInterval(100.0, 200.0),
                ),
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
            independent_support_region_count=2,
            source_spanning_continuous=True,
        )
        registered = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=0.0,
        )
        self.assertEqual(registered.independent_support_region_count, 2)
        self.assertTrue(registered.source_spanning_continuous)

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
                longitudinal_support_domains_px=domains,
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
        self.assertEqual(result.best.longitudinal_support_domain_count, 3)
        self.assertEqual(
            result.best.role_authorized_pair_support_domain_count,
            3,
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
                longitudinal_support_domains_px=domains,
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
                longitudinal_support_domains_px=domains,
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
                longitudinal_support_domains_px=domains,
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
                longitudinal_support_domains_px=(
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),
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
                longitudinal_support_domains_px=domains,
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

    def test_template_local_refinement_cannot_close_complementary_domains(
        self,
    ) -> None:
        bottom = replace(
            binding(
                BoundaryRole.BOTTOM,
                "refined-complementary-bottom",
                340.0,
                traces=(55, 90),
                independent_regions=2,
                source_spanning=False,
            ),
            evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 55, 90),
                longitudinal_support_domains_px=(
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "refined-complementary-top",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(bottom,),
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

    def test_physical_direction_intervals_close_disjoint_local_fits(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "budget-top",
            100.0,
            angle=-0.15,
            angle_interval=FiniteInterval(-0.18, -0.12),
            full_angle_interval=FiniteInterval(-0.3, 0.1),
        )
        bottom = binding(
            BoundaryRole.BOTTOM,
            "budget-bottom",
            340.0,
            angle=0.05,
            angle_interval=FiniteInterval(0.02, 0.08),
            full_angle_interval=FiniteInterval(-0.2, 0.2),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.3, 0.2),
        )

    def test_spanning_direction_safety_contains_canonical_angle(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "spanning-direction-top",
            100.0,
            angle=0.05,
            angle_interval=FiniteInterval(-0.05, 0.05),
            full_angle_interval=FiniteInterval(-0.05, 0.05),
        )
        bottom = binding(
            BoundaryRole.BOTTOM,
            "local-direction-bottom",
            340.0,
            angle=0.16,
            angle_interval=FiniteInterval(-0.05, 0.2),
            full_angle_interval=FiniteInterval(-0.2, 0.2),
            source_spanning=False,
        )
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.selected_direction is not None
        self.assertEqual(
            result.best.selected_direction.full_angle_interval_degrees,
            FiniteInterval(-0.05, 0.05),
        )
        self.assertEqual(
            result.best.selected_direction.canonical_angle_degrees,
            0.05,
        )

    def test_two_region_pair_requires_both_outside_role_authorities(self) -> None:
        top = binding(
            BoundaryRole.TOP,
            "role-top",
            100.0,
            traces=(0, 50),
            independent_regions=2,
            source_spanning=False,
        )
        wrong_bottom = binding(
            BoundaryRole.BOTTOM,
            "wrong-role-bottom",
            340.0,
            traces=(0, 50),
            independent_regions=2,
            source_spanning=False,
            role_authorized=False,
        )
        rejected = fit_template_cross(
            aspect_input(
                template=template(count=2),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),
                top_bindings=(top,),
                bottom_bindings=(wrong_bottom,),
            )
        )
        self.assertEqual(rejected.status, CrossFitStatus.UNRESOLVED)

        supported = fit_template_cross(
            aspect_input(
                template=template(count=2),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),
                top_bindings=(top,),
                bottom_bindings=(replace(wrong_bottom, role_authorized=True),),
            )
        )
        self.assertEqual(supported.status, CrossFitStatus.RESOLVED)
        assert supported.best is not None
        self.assertEqual(supported.best.independent_support_region_count, 2)
        self.assertEqual(supported.best.longitudinal_support_domain_count, 2)
        self.assertEqual(
            supported.best.role_authorized_pair_support_domain_count,
            2,
        )

    def test_two_domain_pair_cannot_own_three_frame_shared_edges(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-three-frame-top",
                        100.0,
                        traces=(10, 50),
                        source_spanning=False,
                        independent_regions=2,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-three-frame-bottom",
                        340.0,
                        traces=(10, 50),
                        source_spanning=False,
                        independent_regions=2,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)

    def test_direct_pairs_keep_native_height_inside_source_authority(self) -> None:
        fixed_template = replace(
            template(count=2),
            frame_height_px=FiniteInterval(230.0, 250.0),
        )
        domains = (FiniteInterval(0.0, 60.0), FiniteInterval(100.0, 160.0))
        local_top = binding(
            BoundaryRole.TOP,
            "local-height-top",
            100.0,
            traces=(10, 130),
            independent_regions=2,
            source_spanning=False,
        )
        local_bottom = binding(
            BoundaryRole.BOTTOM,
            "local-height-bottom",
            338.0,
            traces=(10, 130),
            independent_regions=2,
            source_spanning=False,
        )
        local = fit_template_cross(
            aspect_input(
                template=fixed_template,
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=245.0,
                top_bindings=(local_top,),
                bottom_bindings=(local_bottom,),
                longitudinal_support_domains_px=domains,
                registered_trace_coordinates_px=(10, 130),
            )
        )
        self.assertEqual(local.status, CrossFitStatus.RESOLVED)
        assert local.best is not None
        self.assertAlmostEqual(
            local.best.bottom_canonical_px - local.best.top_canonical_px,
            238.0,
        )
        spanning = fit_template_cross(
            aspect_input(
                template=fixed_template,
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=245.0,
                top_bindings=(
                    replace(local_top, source_spanning_continuous=True),
                ),
                bottom_bindings=(local_bottom,),
                longitudinal_support_domains_px=domains,
                registered_trace_coordinates_px=(10, 130),
            )
        )
        self.assertEqual(spanning.status, CrossFitStatus.RESOLVED)
        assert spanning.best is not None
        self.assertAlmostEqual(
            spanning.best.bottom_canonical_px - spanning.best.top_canonical_px,
            238.0,
        )

    def test_single_side_infers_opposite_fixed_height(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.height_inference_basis,
            CrossHeightInferenceBasis.APERTURE_ASPECT_RATIO,
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)
        self.assertEqual(result.best.inferred_bindings[0].evidence, CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED)
        self.assertEqual(
            result.best.inferred_bindings[0].source_observation_ids,
            (ObservationId("observation:top"),),
        )
        self.assertEqual(
            result.best.inferred_bindings[0].independent_support_region_count,
            3,
        )
        self.assertEqual(
            result.best.selected_direction.selected_observation_ids,
            (ObservationId("observation:top"),),
        )
        self.assertEqual(result.receipt.single_side_inference_count, 1)

    def test_single_side_uses_calibrated_format_height_without_source_w(
        self,
    ) -> None:
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "nominal-height-top", 100.0),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT,
        )
        assert result.best is not None
        self.assertEqual(
            result.best.height_inference_basis,
            CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT,
        )
        self.assertEqual(
            result.best.inferred_bindings[0].evidence,
            CrossEvidence.CALIBRATED_FORMAT_HEIGHT_INFERRED,
        )
        self.assertEqual(
            result.best.bottom_full_interval_px,
            FiniteInterval(338.0, 342.0),
        )
        self.assertEqual(
            result.aperture_aspect_ratio_authority.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertFalse(
            result.aperture_aspect_ratio_authority.blocks_cross_resolution
        )

    def test_weak_single_side_retains_proposal_without_authority(
        self,
    ) -> None:
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-nominal-height-top",
                        100.0,
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
            CrossFailureKind.INDEPENDENT_SUPPORT_UNAVAILABLE,
        )
        self.assertFalse(
            result.aperture_aspect_ratio_authority.blocks_cross_resolution
        )

    def test_ratio_counterevidence_keeps_nominal_height_proposal_unresolved(
        self,
    ) -> None:
        contradicted_ratio = replace(
            _supported_aspect_ratio(FiniteInterval(238.0, 242.0)),
            state=EvidenceState.CONTRADICTED,
            minimum_output_expansion_mm=2.0,
            output_expansion_limit_mm=1.0,
            failure_kind=ApertureAspectRatioFailureKind.BUDGET_EXHAUSTED,
            failure_detail="ratio H uncertainty exceeds the output budget",
        )
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "blocked-nominal-top", 100.0),
                ),
                aperture_aspect_ratio_authority=contradicted_ratio,
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.APERTURE_ASPECT_RATIO_CONFLICT,
        )
        assert result.best is not None
        self.assertEqual(
            result.best.height_inference_basis,
            CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT,
        )
        self.assertTrue(
            result.aperture_aspect_ratio_authority.blocks_cross_resolution
        )

    def test_multiple_nominal_height_anchors_retain_runner_without_winner(
        self,
    ) -> None:
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "nominal-top-a", 100.0),
                    binding(BoundaryRole.TOP, "nominal-top-b", 104.0),
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
        self.assertIsNone(result.winner_basis)

    def test_single_side_does_not_recalibrate_fixed_height(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(binding(BoundaryRole.TOP, "top-offset", 105.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertAlmostEqual(result.best.top_canonical_px, 105.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 345.0)
        self.assertEqual(
            result.best.height_compatibility_px,
            FiniteInterval(238.0, 242.0),
        )
        self.assertEqual(
            result.best.top_full_interval_px,
            FiniteInterval.exact(105.0),
        )
        self.assertEqual(
            result.best.bottom_full_interval_px,
            FiniteInterval(343.0, 347.0),
        )

    def test_two_region_fragment_cannot_supply_single_side_direction(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "two-region-fragment",
                        100.0,
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)

    def test_local_discrete_single_sides_retain_bounded_proposals(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "top-a",
                        96.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "top-b",
                        104.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE,
        )

    def test_three_region_direct_pair_narrows_fixed_height(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                longitudinal_support_domains_px=(FiniteInterval(0.0, 100.0),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "fragmented-top",
                        100.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragmented-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(
            result.best.height_compatibility_px,
            FiniteInterval.exact(240.0),
        )

        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        calibrated = calibrate_source_frame_height(source, result)
        self.assertEqual(
            calibrated.height_state.extent_projection_px(),
            FiniteInterval.exact(240.0),
        )
        self.assertEqual(
            calibrated.height_state.observation_ids,
            (
                ObservationId("observation:fragmented-bottom"),
                ObservationId("observation:fragmented-top"),
            ),
        )

    def test_shared_anchor_does_not_merge_distinct_opposite_boundaries(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domains_px=(FiniteInterval(0.0, 100.0),),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "shared-top",
                        100.0,
                        traces=(0, 20, 50, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "front-bottom",
                        340.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "back-bottom",
                        340.0,
                        traces=(50, 100),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        assert result.best is not None
        self.assertIsNotNone(result.runner_up)
        self.assertTrue(result.best.direct_pair)
        self.assertIn("non-equivalent", result.reason or "")

    def test_selection_does_not_own_exact_subset_family_identity(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "exact-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=2,
                        source_spanning=False,
                        angle=-0.2,
                        angle_interval=FiniteInterval(-0.3, -0.1),
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "exact-local-top",
                        104.0,
                        traces=(40, 60, 80),
                        independent_regions=2,
                        source_spanning=False,
                        angle=0.2,
                        angle_interval=FiniteInterval(0.1, 0.3),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "exact-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                        angle=0.0,
                        angle_interval=FiniteInterval(-0.4, 0.4),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_selection_does_not_own_staggered_family_identity(self) -> None:
        domains = (
            FiniteInterval(-1.0, 21.0),
            FiniteInterval(39.0, 61.0),
            FiniteInterval(79.0, 101.0),
        )
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "staggered-local-top",
                        104.0,
                        traces=(50, 70, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(result.receipt.compatible_pair_count, 2)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)

    def test_equal_domain_side_tracks_remain_discrete(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "equal-domain-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "equal-domain-local-top",
                        104.0,
                        traces=(10, 30, 50, 70, 90),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "equal-domain-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_disjoint_side_track_extents_remain_discrete(self) -> None:
        registered = tuple(range(0, 111, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=4),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(29.0, 51.0),
                    FiniteInterval(59.0, 81.0),
                    FiniteInterval(89.0, 111.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "disjoint-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 70),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "disjoint-local-top",
                        104.0,
                        traces=(80, 90, 100, 110),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "disjoint-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_disconnected_broader_side_track_cannot_dominate(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "disconnected-broader-top",
                        100.0,
                        traces=(0, 50, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "inside-connected-local-top",
                        104.0,
                        traces=(30, 50, 70, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "disconnected-broader-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)

    def test_disconnected_local_side_track_cannot_be_discarded(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "connected-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "disconnected-inside-local-top",
                        104.0,
                        traces=(10, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "disconnected-local-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)

    def test_different_opposite_bindings_remain_discrete(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "different-opposite-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "different-opposite-local-top",
                        104.0,
                        traces=(50, 70, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "different-opposite-broad-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "different-opposite-local-bottom",
                        344.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_direction_disjoint_side_tracks_remain_discrete(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "direction-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                        angle=-0.2,
                        angle_interval=FiniteInterval(-0.3, -0.1),
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "direction-local-top",
                        104.0,
                        traces=(50, 70, 90),
                        independent_regions=2,
                        source_spanning=False,
                        angle=0.2,
                        angle_interval=FiniteInterval(0.1, 0.3),
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "direction-shared-bottom",
                        340.0,
                        traces=registered,
                        independent_regions=3,
                        source_spanning=False,
                        angle=0.0,
                        angle_interval=FiniteInterval(-0.4, 0.4),
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)

    def test_two_domain_side_cannot_gain_global_dominance(self) -> None:
        registered = tuple(range(0, 101, 10))
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=registered,
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "two-domain-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "one-domain-local-top",
                        104.0,
                        traces=(30, 50),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "two-domain-shared-bottom",
                        340.0,
                        traces=(0, 20, 30, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_under_supported_local_side_cannot_be_discarded(self) -> None:
        registered = tuple(range(0, 101, 10))
        domains = (
            FiniteInterval(-1.0, 21.0),
            FiniteInterval(39.0, 61.0),
            FiniteInterval(79.0, 101.0),
            FiniteInterval(109.0, 131.0),
        )
        local_cases = (
            ("one-region-ledger", (50, 70, 90), 1, (0, 20, 50, 70)),
        )
        for name, local_traces, local_regions, bottom_traces in local_cases:
            with self.subTest(name=name):
                result = fit_template_cross(
                    aspect_input(
                        template=template(count=4),
                        fixed_height_px=FiniteInterval(236.0, 240.0),
                        registered_trace_coordinates_px=registered,
                        longitudinal_support_domains_px=domains,
                        top_bindings=(
                            binding(
                                BoundaryRole.TOP,
                                f"{name}-broader-top",
                                100.0,
                                traces=(0, 20, 40, 60, 80, 100),
                                independent_regions=3,
                                source_spanning=False,
                            ),
                            binding(
                                BoundaryRole.TOP,
                                f"{name}-local-top",
                                104.0,
                                traces=local_traces,
                                independent_regions=local_regions,
                                source_spanning=False,
                            ),
                        ),
                        bottom_bindings=(
                            binding(
                                BoundaryRole.BOTTOM,
                                f"{name}-shared-bottom",
                                340.0,
                                traces=bottom_traces,
                                independent_regions=2,
                                source_spanning=False,
                            ),
                        ),
                    )
                )

                self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                self.assertIsNotNone(result.best)
                self.assertIsNotNone(result.runner_up)

    def test_selection_does_not_own_one_domain_family_identity(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=4),
                fixed_height_px=FiniteInterval(236.0, 240.0),
                registered_trace_coordinates_px=tuple(range(0, 101, 10)),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 21.0),
                    FiniteInterval(39.0, 61.0),
                    FiniteInterval(79.0, 101.0),
                    FiniteInterval(109.0, 131.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "one-domain-broader-top",
                        100.0,
                        traces=(0, 20, 40, 60, 80, 100),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "one-domain-local-top",
                        104.0,
                        traces=(30, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "one-domain-shared-bottom",
                        340.0,
                        traces=(0, 20, 30, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)

    def test_missing_or_unregistered_lattice_cannot_authorize_dominance(self) -> None:
        domains = (
            FiniteInterval(-1.0, 21.0),
            FiniteInterval(39.0, 61.0),
            FiniteInterval(79.0, 101.0),
        )
        for name, registered in (
            ("missing", ()),
            ("local-off-lattice", (0, 20, 40, 60, 80, 100)),
        ):
            with self.subTest(name=name):
                result = fit_template_cross(
                    aspect_input(
                        template=template(count=3),
                        fixed_height_px=FiniteInterval(236.0, 240.0),
                        registered_trace_coordinates_px=registered,
                        longitudinal_support_domains_px=domains,
                        top_bindings=(
                            binding(
                                BoundaryRole.TOP,
                                f"{name}-broader-top",
                                100.0,
                                traces=(0, 20, 40, 60, 80, 100),
                                independent_regions=3,
                                source_spanning=False,
                            ),
                            binding(
                                BoundaryRole.TOP,
                                f"{name}-local-top",
                                104.0,
                                traces=(50, 70, 90),
                                independent_regions=2,
                                source_spanning=False,
                            ),
                        ),
                        bottom_bindings=(
                            binding(
                                BoundaryRole.BOTTOM,
                                f"{name}-shared-bottom",
                                340.0,
                                traces=tuple(range(0, 101, 10)),
                                independent_regions=3,
                                source_spanning=False,
                            ),
                        ),
                    )
                )

                self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
                self.assertIsNotNone(result.best)
                self.assertIsNotNone(result.runner_up)

    def test_disconnected_local_pairs_remain_discrete_answers(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "front-top",
                        100.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "back-top",
                        100.0,
                        traces=(80, 100),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "front-bottom",
                        340.0,
                        traces=(0, 20),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "back-bottom",
                        340.0,
                        traces=(80, 100),
                        independent_regions=1,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertTrue(
            set(result.best.direct_provenance_ids).isdisjoint(
                result.runner_up.direct_provenance_ids
            )
        )

    def test_spanning_side_infers_opposite_without_fragment_authority(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-a",
                        500.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-b",
                        700.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            set(result.best.direct_provenance_ids),
            {
                ObservationId("observation:spanning-top"),
            },
        )

    def test_spanning_side_infers_when_local_closures_are_ambiguous(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom-a",
                        339.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "local-bottom-b",
                        341.0,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:spanning-top"),),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_spanning_side_does_not_export_local_role_closure(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom",
                        339.0,
                        source_spanning=False,
                        role_authorized=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "authorized-bottom",
                        340.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:spanning-top"),),
        )

    def test_template_wide_side_infers_opposite_without_local_fragment_authority(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-wide-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom-a",
                        340.0,
                        traces=(10,),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-role-bottom-b",
                        341.0,
                        traces=(90,),
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:template-wide-top"),),
        )

    def test_domain_complete_role_anchor_resolves_with_two_regions(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-two-region-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:domain-complete-two-region-top"),),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_domain_complete_role_anchor_owns_fixed_height_inference(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-no-center-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_domain_complete_side_owns_over_one_local_direct_closure(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 51, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-top",
                        100.0,
                        traces=(50, 51),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "domain-complete-bottom",
                        340.0,
                        traces=(10, 50, 51, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:domain-complete-bottom"),),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)
        self.assertAlmostEqual(result.best.bottom_canonical_px, 340.0)

    def test_domain_complete_anchor_requires_at_least_three_domains(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=2),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-complete-two-domain-top",
                        100.0,
                        traces=(10, 50),
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

    def test_domain_complete_anchor_requires_every_frame_domain(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-incomplete-top",
                        100.0,
                        traces=(10, 50),
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

    def test_domain_complete_anchor_requires_complete_direction(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-no-direction-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                        angle=None,
                        angle_interval=None,
                        full_angle_interval=None,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_domain_complete_anchor_requires_role_authority(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-unauthorized-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                        role_authorized=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)

    def test_disconnected_fragments_cannot_combine_domain_coverage(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(10, 50, 90),
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "domain-fragment-front",
                        100.0,
                        traces=(10, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "domain-fragment-back",
                        100.0,
                        traces=(50, 90),
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

    def test_template_wide_anchor_cannot_promote_role_unknown_opposite_line(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=240.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-refine-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "near-bottom",
                        342.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "far-bottom",
                        347.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertEqual(
            result.best.inferred_bindings[0].evidence,
            CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED,
        )

    def test_role_unknown_outer_lines_do_not_compete_with_fixed_height(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=240.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "ambiguous-refine-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "lower-near",
                        338.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "upper-near",
                        342.0,
                        traces=(10, 50),
                        source_spanning=False,
                        role_authorized=False,
                        independent_regions=2,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertFalse(result.best.direct_pair)
        self.assertIsNone(result.runner_up)

    def test_role_authorized_direct_pair_precedes_single_side_inference(self) -> None:
        domains = (
            FiniteInterval(0.0, 20.0),
            FiniteInterval(40.0, 60.0),
            FiniteInterval(80.0, 100.0),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                longitudinal_support_domains_px=domains,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "template-wide-paired-top",
                        100.0,
                        traces=(10, 50, 90),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "two-domain-bottom",
                        340.0,
                        traces=(10, 50),
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertTrue(result.best.direct_pair)
        self.assertEqual(len(result.best.direct_bindings), 2)

    def test_fragment_only_group_cannot_compete_with_spanning_closure(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "spanning-top", 100.0),
                    binding(
                        BoundaryRole.TOP,
                        "fragment-top",
                        500.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "spanning-bottom-fragment",
                        340.0,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "fragment-bottom",
                        740.0,
                        source_spanning=False,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertIn(
            ObservationId("observation:spanning-top"),
            result.best.direct_provenance_ids,
        )

    def test_equally_strong_non_equivalent_fits_keep_runner_up_unresolved(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0),
                    binding(BoundaryRole.TOP, "top-b", 500.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 740.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)

    def test_cross_grid_proposal_survives_pair_support_failure(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(236.0, 244.0),
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "proposal-top",
                        100.0,
                        traces=(0, 10),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "proposal-bottom",
                        342.0,
                        traces=(90, 100),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE,
        )
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE,
        )
        assert result.best is not None and result.runner_up is not None
        self.assertTrue(result.best.single_side_inferred)
        self.assertEqual(
            result.best.direct_provenance_ids,
            (ObservationId("observation:proposal-top"),),
        )
        self.assertEqual(
            result.runner_up.direct_provenance_ids,
            (ObservationId("observation:proposal-bottom"),),
        )
        self.assertEqual(result.receipt.single_side_inference_count, 2)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)

    def test_cross_grid_proposal_keeps_direction_counterevidence(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(236.0, 244.0),
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "wrong-direction-top",
                        100.0,
                        angle=0.6,
                        angle_interval=FiniteInterval(0.5, 0.7),
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "wrong-direction-bottom",
                        340.0,
                        angle=0.6,
                        angle_interval=FiniteInterval(0.5, 0.7),
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.DIRECTION_INCOMPATIBLE,
        )
        self.assertIsNotNone(result.best)
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE,
        )
        self.assertIsNone(result.winner_basis)

    def test_cross_grid_proposal_requires_registered_direction(self) -> None:
        without_direction = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "weak-top",
                        100.0,
                        traces=(0,),
                        independent_regions=1,
                        source_spanning=False,
                        angle=None,
                        angle_interval=None,
                    ),
                ),
            )
        )

        self.assertEqual(without_direction.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(without_direction.best)
        self.assertIsNone(without_direction.retained_proposal_basis)

    def test_cross_grid_retains_spatially_complete_role_hypothesis(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "unqualified-top",
                        100.0,
                        role_authorized=False,
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
        )
        self.assertEqual(
            result.retained_proposal_basis,
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_REGISTERED_ROLE_HYPOTHESIS,
        )
        assert result.best is not None
        self.assertTrue(result.best.single_side_inferred)
        self.assertFalse(result.best.direct_bindings[0].role_authorized)
        self.assertIsNone(result.runner_up)
        self.assertIsNone(result.winner_basis)

    def test_cross_grid_rejects_local_role_hypothesis(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-unqualified-top",
                        100.0,
                        role_authorized=False,
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
        )
        self.assertIsNone(result.best)
        self.assertIsNone(result.retained_proposal_basis)

    def test_cross_grid_proposal_respects_evaluated_fit_bound(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(236.0, 244.0),
                source_direction=placement_direction(),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "bounded-top",
                        100.0,
                        traces=(0, 10),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bounded-bottom",
                        342.0,
                        traces=(90, 100),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                maximum_evaluated_fits=1,
            )
        )

        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED,
        )
        self.assertIsNone(result.best)
        self.assertIsNone(result.retained_proposal_basis)

    def test_nearby_exact_pairs_remain_discrete_without_shared_identity(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0, role_authorized=False),
                    binding(BoundaryRole.TOP, "top-b", 104.0, role_authorized=False),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0, role_authorized=False),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 344.0, role_authorized=False),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertTrue(
            result.best is None
            or result.best.boundary_use != OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        )

    def test_role_authorized_line_can_join_one_uniform_enclosing_pair(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "aperture-or-support-top",
                        100.0,
                        enclosing_pair_id="support:one",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom",
                        350.0,
                        enclosing_pair_id="support:one",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        self.assertIsNotNone(result.best.enclosing_support_pair)
        self.assertFalse(result.best.single_side_inferred)
        self.assertFalse(
            result.aperture_aspect_ratio_authority.consumed_for_cross_inference
        )
        source = SourceScanGeometry.create(
            FramePhysicalSpec(10.0, 24.0, None),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        self.assertEqual(
            calibrate_source_frame_height(source, result),
            source,
        )

    def test_preclosed_enclosing_pair_uses_fixed_height_without_ratio_authority(
        self,
    ) -> None:
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:fixed-height",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom",
                        350.0,
                        role_authorized=False,
                        enclosing_pair_id="support:fixed-height",
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertEqual(
            result.winner_basis,
            CrossWinnerBasis.UNIQUE_ENCLOSING_SUPPORT,
        )
        assert result.best is not None
        self.assertEqual(
            result.best.fixed_height_px,
            FiniteInterval(238.0, 242.0),
        )
        self.assertEqual(
            result.best.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        self.assertEqual(
            result.aperture_aspect_ratio_authority.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertFalse(
            result.aperture_aspect_ratio_authority.blocks_cross_resolution
        )

    def test_multiple_preclosed_enclosing_pairs_remain_unresolved(self) -> None:
        result = fit_template_cross(
            _TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top-a",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "support-top-b",
                        101.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-a",
                        350.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-b",
                        351.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.winner_basis)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)

    def test_enclosing_support_evaluations_share_the_cross_fit_bound(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                maximum_evaluated_fits=1,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top-a",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "support-top-b",
                        101.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-a",
                        345.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-b",
                        346.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.BOUND_EXCEEDED)
        self.assertEqual(result.receipt.evaluated_fit_count, 2)
        self.assertEqual(result.receipt.evaluated_fit_bound, 1)

    def test_preclosed_enclosing_pair_cannot_detach_and_recombine(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                canonical_fixed_height_px=240.0,
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "support-top-a",
                        100.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-a",
                        350.0,
                        role_authorized=False,
                        enclosing_pair_id="support:a",
                    ),
                    binding(
                        BoundaryRole.BOTTOM,
                        "support-bottom-b",
                        349.0,
                        role_authorized=False,
                        enclosing_pair_id="support:b",
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.direct_provenance_ids,
            (
                ObservationId("observation:support-top-a"),
                ObservationId("observation:support-bottom-a"),
            ),
        )
        self.assertEqual(result.receipt.evaluated_fit_count, 1)

    def test_enclosing_support_records_straight_model_residual(self) -> None:
        top = replace(
            binding(
                BoundaryRole.TOP,
                "bent-support-top",
                100.0,
                role_authorized=False,
                enclosing_pair_id="support:bent",
            ),
            trace_position_intervals_px=(
                FiniteInterval.exact(100.0),
                FiniteInterval.exact(104.0),
                FiniteInterval.exact(100.0),
            ),
        )
        bottom = replace(
            binding(
                BoundaryRole.BOTTOM,
                "bent-support-bottom",
                350.0,
                role_authorized=False,
                enclosing_pair_id="support:bent",
            ),
            trace_position_intervals_px=(
                FiniteInterval.exact(350.0),
                FiniteInterval.exact(346.0),
                FiniteInterval.exact(350.0),
            ),
        )
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                canonical_fixed_height_px=240.0,
                top_bindings=(top,),
                bottom_bindings=(bottom,),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        assert result.best.enclosing_support_pair is not None
        self.assertEqual(
            result.best.enclosing_support_pair.top_straight_model_residual_px,
            4.0,
        )
        self.assertEqual(
            result.best.enclosing_support_pair.bottom_straight_model_residual_px,
            4.0,
        )

    def test_local_role_line_cannot_compete_with_source_wide_support(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=FiniteInterval(235.0, 245.0),
                canonical_fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 50, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(-1.0, 1.0),
                    FiniteInterval(49.0, 51.0),
                    FiniteInterval(99.0, 101.0),
                ),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "local-role-top",
                        75.0,
                        traces=(0, 50),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "whole-support-top",
                        80.0,
                        source_spanning=False,
                        role_authorized=False,
                        enclosing_pair_id="support:whole",
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "whole-support-bottom",
                        330.0,
                        source_spanning=False,
                        role_authorized=False,
                        enclosing_pair_id="support:whole",
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        assert result.best.enclosing_support_pair is not None
        self.assertEqual(
            result.best.enclosing_support_pair.top_provenance_ids,
            (ObservationId("observation:whole-support-top"),),
        )

    def test_distinct_exact_bindings_are_not_hulled_into_uncertainty(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "top-a", 100.0, traces=(0, 50)),
                    binding(BoundaryRole.TOP, "top-b", 100.25, traces=(50, 100)),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom-a", 340.0, traces=(0, 50)),
                    binding(BoundaryRole.BOTTOM, "bottom-b", 340.5, traces=(50, 100)),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(result.best.top_full_interval_px.width, 0.0)
        self.assertEqual(result.best.bottom_full_interval_px.width, 0.0)

    def test_two_sided_spanning_closure_excludes_local_false_pair(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(
                    binding(BoundaryRole.TOP, "true-top", 100.0),
                    binding(
                        BoundaryRole.TOP,
                        "local-top",
                        70.0,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "true-bottom", 340.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.direct_provenance_ids,
            (
                ObservationId("observation:true-top"),
                ObservationId("observation:true-bottom"),
            ),
        )
        self.assertAlmostEqual(result.best.top_canonical_px, 100.0)

    def test_far_groups_are_not_hulled_and_keep_runner_up(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "near-top", 100.0),
                    binding(BoundaryRole.TOP, "far-top", 500.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "near-bottom", 340.0),
                    binding(BoundaryRole.BOTTOM, "far-bottom", 740.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.runner_up)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(
            result.best.top_full_interval_px,
            FiniteInterval.exact(100.0),
        )
        self.assertEqual(
            result.runner_up.top_full_interval_px,
            FiniteInterval.exact(500.0),
        )

    def test_discrete_direct_aperture_pairs_remain_unresolved(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "normal-top", 100.0),
                    binding(BoundaryRole.TOP, "clutter-top", 300.0),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "normal-bottom", 340.0),
                    binding(BoundaryRole.BOTTOM, "clutter-bottom", 540.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        assert result.best is not None
        assert result.runner_up is not None
        self.assertEqual(result.best.bound_observation_ids[0], ObservationId("observation:normal-top"))
        self.assertEqual(
            result.runner_up.bound_observation_ids[0],
            ObservationId("observation:clutter-top"),
        )

    def test_unique_direct_aperture_pair_owns_measured_offset(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "top", 300.0),),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "bottom", 540.0),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNone(result.runner_up)
        assert result.best is not None
        self.assertEqual(result.best.top_canonical_px, 300.0)
        self.assertEqual(result.best.bottom_canonical_px, 540.0)

    def test_direct_height_contradiction_does_not_recalibrate_or_resolve(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval.exact(240.0),
                top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 500.0),),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNone(result.best)
        self.assertEqual(result.receipt.compatible_pair_count, 0)

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

    def test_registration_overflow_is_a_typed_cross_result(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(),
                fixed_height_px=240.0,
                registered_top_run_count=513,
                registered_bottom_run_count=0,
                maximum_registered_runs_per_role=512,
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
                    ),
                    binding(
                        BoundaryRole.TOP,
                        "low-support-top",
                        500.0,
                        support=0.2,
                        residual=10.0,
                    ),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "high-support-bottom", 340.0),
                    binding(
                        BoundaryRole.BOTTOM,
                        "low-support-bottom",
                        740.0,
                        support=0.2,
                        residual=10.0,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertIsNotNone(result.runner_up)

    def test_support_across_three_template_frames_rejects_local_runner(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=4),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domains_px=(
                    FiniteInterval(5.0, 20.0),
                    FiniteInterval(25.0, 40.0),
                    FiniteInterval(45.0, 60.0),
                    FiniteInterval(65.0, 80.0),
                ),
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


if __name__ == "__main__":
    unittest.main()
