from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.tests.template_test_support import placement_direction
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
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
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


from tools.tests.cross_fixture_support import (
    _supported_aspect_ratio,
    aspect_input,
    binding,
    template,
)

class TemplateCrossDomainContractTest(unittest.TestCase):
    def test_resolved_model_cannot_replace_raw_regions_with_effective_count(self) -> None:
            result = fit_template_cross(aspect_input(
                template=template(), fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "measured-top", 100.0),),
                bottom_bindings=(binding(BoundaryRole.BOTTOM, "measured-bottom", 340.0),),
            ))
            self.assertEqual(result.status, CrossFitStatus.RESOLVED)
            invalid_fit = replace(
                result.best,
                direct_bindings=(
                    replace(result.best.direct_bindings[0], independent_support_region_count=1),
                    result.best.direct_bindings[1],
                ),
                independent_support_region_count=3,
            )
            with self.assertRaisesRegex(ValueError, "independent measured"):
                replace(result, best=invalid_fit)

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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
                    longitudinal_support_domain_groups_px=(domains,),
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
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 4)

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
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 3)

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
