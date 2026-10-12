from __future__ import annotations

from dataclasses import replace
import unittest
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
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
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
    CrossRetainedProposalBasis,
    CrossWinnerBasis,
    TemplateCrossInput as _TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    ApertureAspectRatioFailureKind,
)
from x5crop.formats import FramePhysicalSpec
from tools.tests.cross_fixture_support import (
    _supported_aspect_ratio,
    aspect_input,
    binding,
    template,
)


class TemplateCrossHeightContractTest(unittest.TestCase):
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
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),),
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
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),),
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
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(-1.0, 10.0),
                    FiniteInterval(40.0, 60.0),
                ),),
                top_bindings=(top,),
                bottom_bindings=(replace(wrong_bottom, role_authorized=True),),
            )
        )
        self.assertEqual(supported.status, CrossFitStatus.RESOLVED)
        assert supported.best is not None
        self.assertEqual(supported.best.independent_support_region_count, 2)
        self.assertEqual(
            supported.best.longitudinal_projection_authority.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            supported.best.longitudinal_projection_authority
            .supported_domain_ordinals_by_candidate[0],
            (1, 2),
        )

    def test_local_pair_cannot_extrapolate_beyond_observed_half(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=6),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=tuple(
                    index * 40 + 10 for index in range(6)
                ),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "left-half-top",
                        100.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "left-half-bottom",
                        340.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind
            .LONGITUDINAL_PROJECTION_AUTHORITY_UNAVAILABLE,
        )
        assert result.best is not None
        authority = result.best.longitudinal_projection_authority
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(authority.supported_domain_ordinals_by_candidate[0], (1, 2, 3))
        self.assertFalse(authority.template_extent_bracketed)
        self.assertEqual(
            authority.failure_kind,
            CrossLongitudinalProjectionFailureKind
            .TEMPLATE_EXTENT_UNBRACKETED,
        )

    def test_two_shared_domains_cannot_export_complementary_tails(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=6),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=tuple(
                    index * 40 + 10 for index in range(6)
                ),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "middle-to-right-top",
                        100.0,
                        traces=(50, 90, 130, 170, 210),
                        independent_regions=3,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "left-to-middle-bottom",
                        340.0,
                        traces=(10, 50, 90),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.failure_kind,
            CrossFailureKind
            .LONGITUDINAL_PROJECTION_AUTHORITY_UNAVAILABLE,
        )
        assert result.best is not None
        authority = result.best.longitudinal_projection_authority
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(authority.supported_domain_ordinals_by_candidate[0], (2, 3))
        self.assertEqual(
            authority.failure_kind,
            CrossLongitudinalProjectionFailureKind
            .INDEPENDENT_DOMAIN_SUPPORT_UNAVAILABLE,
        )

    def test_bracketed_pair_interpolates_across_unobserved_domains(self) -> None:
        domains = tuple(
            FiniteInterval(float(index * 40), float(index * 40 + 20))
            for index in range(6)
        )
        result = fit_template_cross(
            aspect_input(
                template=template(count=6),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=tuple(
                    index * 40 + 10 for index in range(6)
                ),
                longitudinal_support_domain_groups_px=(domains,),
                top_bindings=(
                    binding(
                        BoundaryRole.TOP,
                        "bracketed-top",
                        100.0,
                        traces=(10, 90, 210),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
                bottom_bindings=(
                    binding(
                        BoundaryRole.BOTTOM,
                        "bracketed-bottom",
                        340.0,
                        traces=(10, 90, 210),
                        independent_regions=2,
                        source_spanning=False,
                    ),
                ),
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        assert result.best is not None
        authority = result.best.longitudinal_projection_authority
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.basis,
            CrossLongitudinalProjectionBasis.BRACKETED_TEMPLATE_EXTENT,
        )
        self.assertEqual(authority.supported_domain_ordinals_by_candidate[0], (1, 3, 6))
        self.assertTrue(authority.template_extent_bracketed)

    def test_two_domain_pair_cannot_own_three_frame_shared_edges(self) -> None:
        result = fit_template_cross(
            aspect_input(
                template=template(count=3),
                fixed_height_px=240.0,
                registered_trace_coordinates_px=(0, 20, 40, 60, 80, 100),
                longitudinal_support_domain_groups_px=((
                    FiniteInterval(0.0, 20.0),
                    FiniteInterval(40.0, 60.0),
                    FiniteInterval(80.0, 100.0),
                ),),
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
                longitudinal_support_domain_groups_px=(domains,),
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
                longitudinal_support_domain_groups_px=(domains,),
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
            failure_kind=ApertureAspectRatioFailureKind.PHYSICAL_PRIOR_CONFLICT,
            failure_detail="ratio H does not intersect the physical prior",
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
                longitudinal_support_domain_groups_px=((FiniteInterval(0.0, 100.0),),),
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
