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

class TemplateCrossEnclosingContractTest(unittest.TestCase):
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
                        replace(binding(
                            BoundaryRole.TOP,
                            "aperture-or-support-top",
                            100.0,
                        ), trace_position_intervals_px=(FiniteInterval.exact(100.0),) * 3),
                    ),
                    bottom_bindings=(
                        replace(binding(
                            BoundaryRole.BOTTOM,
                            "support-bottom",
                            350.0,
                        ), trace_position_intervals_px=(FiniteInterval.exact(350.0),) * 3),
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

    def test_unique_direct_pair_keeps_measured_height_and_complete_raw_support(self) -> None:
            inputs = aspect_input(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 260.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(replace(
                    binding(BoundaryRole.TOP, "top", 100.0),
                    trace_position_intervals_px=(FiniteInterval.exact(100.0),) * 3,
                ),),
                bottom_bindings=(replace(
                    binding(BoundaryRole.BOTTOM, "bottom", 350.0),
                    trace_position_intervals_px=(FiniteInterval.exact(350.0),) * 3,
                ),),
            )
            result = fit_template_cross(inputs)
            self.assertEqual(result.status, CrossFitStatus.RESOLVED)
            self.assertEqual(result.winner_basis, CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT)
            assert result.best is not None
            self.assertEqual(result.best.boundary_use, OutputBoundaryUse.APERTURE_PAIR)
            self.assertIsNone(result.best.enclosing_support_pair)
            self.assertEqual(result.best.top_full_interval_px, FiniteInterval.exact(100.0))
            self.assertEqual(result.best.bottom_full_interval_px, FiniteInterval.exact(350.0))
            self.assertEqual(result.best.height_compatibility_px, FiniteInterval.exact(250.0))
            self.assertEqual(result.best.fixed_height_px, FiniteInterval.exact(250.0))
            self.assertFalse(result.aperture_aspect_ratio_authority.consumed_for_cross_inference)
            self.assertEqual(result.receipt.evaluated_fit_count, 1)

            bounded = fit_template_cross(replace(inputs, maximum_evaluated_fits=1))
            self.assertEqual(bounded.status, CrossFitStatus.RESOLVED)
            self.assertEqual(bounded.receipt.evaluated_fit_count, 1)

            top = inputs.top_bindings[0]
            extra_trace = max(top.trace_coordinates_px) + 10
            complete_top = replace(top, trace_coordinates_px=(*top.trace_coordinates_px, extra_trace),
                trace_position_intervals_px=(*top.trace_position_intervals_px, FiniteInterval.exact(103.0)))
            complete = fit_template_cross(replace(inputs, top_bindings=(complete_top,)))
            assert complete.best is not None
            self.assertEqual(complete.best.boundary_use, OutputBoundaryUse.APERTURE_PAIR)
            self.assertEqual(complete.best.direct_bindings[0], complete_top)
            self.assertEqual(complete.best.shared_trace_support_count, result.best.shared_trace_support_count)

    def test_different_enclosing_pair_does_not_replace_unique_aperture(self) -> None:
            result = fit_template_cross(aspect_input(
                template=template(),
                fixed_height_px=240.0,
                top_bindings=(
                    binding(BoundaryRole.TOP, "aperture-top", 100.0),
                    binding(BoundaryRole.TOP, "support-top", 95.0,
                            role_authorized=False, enclosing_pair_id="support:outer"),
                ),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "aperture-bottom", 340.0),
                    binding(BoundaryRole.BOTTOM, "support-bottom", 350.0,
                            role_authorized=False, enclosing_pair_id="support:outer"),
                ),
            ))
            self.assertEqual(result.status, CrossFitStatus.RESOLVED)
            self.assertEqual(result.winner_basis, CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT)
            assert result.best is not None
            self.assertEqual(result.best.boundary_use, OutputBoundaryUse.APERTURE_PAIR)
            self.assertEqual(result.best.bound_observation_ids, (
                ObservationId("observation:aperture-top"),
                ObservationId("observation:aperture-bottom"),
            ))
            self.assertEqual(result.receipt.evaluated_fit_count, 1)

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
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 4)

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
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 1)
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
            # Every attempted support proof, including rejected pairs, is charged.
            self.assertEqual(result.receipt.evaluated_fit_count, 2)

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
                    longitudinal_support_domain_groups_px=((
                        FiniteInterval(0.0, 1.0),
                        FiniteInterval(49.0, 51.0),
                        FiniteInterval(99.0, 100.0),
                    ),),
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

    def test_non_spanning_support_must_bracket_extent_with_each_raw_side(self) -> None:
            for top_traces, bottom_traces, expected in (
                ((50, 170, 250), (50, 170, 250), CrossFitStatus.UNRESOLVED),
                ((0, 50, 170, 250), (50, 170, 250, 340), CrossFitStatus.UNRESOLVED),
                ((0, 170, 340), (0, 170, 340), CrossFitStatus.RESOLVED),
            ):
                with self.subTest(top=top_traces, bottom=bottom_traces):
                    result = fit_template_cross(aspect_input(
                        template=template(count=3), fixed_height_px=240.0,
                        registered_trace_coordinates_px=(0, 50, 170, 250, 340),
                        longitudinal_support_domain_groups_px=((
                            FiniteInterval(0.0, 100.0), FiniteInterval(120.0, 220.0), FiniteInterval(240.0, 340.0),
                        ),),
                        top_bindings=(binding(BoundaryRole.TOP, "top", 100.0, traces=top_traces,
                                              source_spanning=False, role_authorized=False, enclosing_pair_id="outer"),),
                        bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 350.0, traces=bottom_traces,
                                                 source_spanning=False, role_authorized=False, enclosing_pair_id="outer"),),
                    ))
                    self.assertEqual(result.status, expected)

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
