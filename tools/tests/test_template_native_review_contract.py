from __future__ import annotations

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from tools.tests.template_runtime_test_support import prepared_template_lane
from tools.tests.template_test_support import (
    placement_binding,
    placement_cross,
    placement_sequence,
    placement_template,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    unavailable_aperture_aspect_ratio_authority,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFitCompetition,
    CrossFitStatus,
    CrossSearchReceipt,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.template_phase_review import (
    IndependentPhaseReviewFailure,
    IndependentPhaseReviewFailureKind,
    IndependentPhaseReviewWorkReceipt,
    IndependentPhaseReviewPortfolio,
    build_independent_phase_review,
    independent_phase_cross_input,
)
from x5crop.detection.photo_geometry.template_measurement_plan_model import (
    MAX_CROSS_PAIRS,
)
from x5crop.detection.photo_geometry.template_native_retention import (
    select_native_phase_retention,
)
from x5crop.detection.photo_geometry.template_phase_candidates import _BoundFit
from x5crop.detection.photo_geometry.template_phase_model import (
    NativeEndpointPhaseDiagnostic,
    NativeEndpointSelectionBasis,
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectedBinding,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
)
from x5crop.detection.photo_geometry.template_placement import (
    resolved_cross_support_domains_px,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.formats import FramePhysicalSpec


class NativeReviewContractTests(TestCase):
    def _retained_lane(self):
        lane = prepared_template_lane()
        fit = placement_sequence(lane.template_spec)
        facts = tuple(
            DirectRoleAuthorityFact(
                role_index=role_index,
                lane_ordinal=role_index // 2 + 1,
                role=(
                    BoundaryRole.START
                    if role_index % 2 == 0
                    else BoundaryRole.END
                ),
                observation_id=binding.observation_id,
                evidence_group_id=binding.evidence_group_id,
                independent_support_region_count=3,
                bases=(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,),
                blocking_material_conflict_ids=(),
                state=EvidenceState.SUPPORTED,
            )
            for role_index, binding in enumerate(fit.role_bindings)
            if binding is not None
        )
        authority = DirectRoleBindingAuthority(
            state=EvidenceState.SUPPORTED,
            facts=facts,
            unsupported_role_indices=(),
            reason=None,
        )
        projection = PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
            basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
            projected_out_bindings=(),
            retained_direct_constraint_rank=3,
            reason=None,
        )
        diagnostic = NativeEndpointPhaseDiagnostic(
            fit=fit,
            projection=projection,
            residual_compatible=True,
            terminal_role_indices=tuple(item.role_index for item in facts),
            selection_basis=NativeEndpointSelectionBasis.INTRINSIC_TERMINAL,
        )
        retention = select_native_phase_retention(
            (
                (
                    _BoundFit(fit, True),
                    _BoundFit(fit, True),
                    projection,
                ),
            ),
        )
        self.assertIsNotNone(retention.diagnostics[0])
        self.assertIs(retention.diagnostics[0].fit, fit)
        source = SourceScanGeometry.create(
            lane.source_scan_geometry.frame_spec,
            width_scale_px_per_mm=lane.lane.scan_canvas.axis_scales.width_axis_px_per_mm,
            height_scale_px_per_mm=lane.lane.scan_canvas.axis_scales.height_axis_px_per_mm,
        )
        height = source.height_state.extent_projection_px()
        phase = replace(
            lane.phase_competition,
            registered_direct_observation_ids=fit.bound_observation_ids,
            _native_phase_retention=retention,
        )
        lane = replace(
            lane,
            cross_input=replace(
                lane.cross_input,
                fixed_height_px=height,
                canonical_fixed_height_px=height.center,
            ),
            phase_competition=phase,
        )
        # The generic prepared-lane fixture intentionally has no registered
        # Cross bindings.  This focused builder fixture supplies the exact
        # direct IDs consumed by the patched Cross owner after preparation.
        object.__setattr__(
            lane,
            "cross_input",
            replace(
                lane.cross_input,
                top_bindings=(placement_binding(BoundaryRole.TOP, "top", 10.0),),
                bottom_bindings=(
                    placement_binding(BoundaryRole.BOTTOM, "bottom", 250.0),
                ),
                fitted_observation_count=2,
            ),
        )
        return lane

    def _build_single_review(self, lane):
        portfolio = build_independent_phase_review(lane)
        self.assertEqual(len(portfolio.reviews), 1)
        return portfolio.reviews[0]

    def _portfolio(self, lane, review):
        return IndependentPhaseReviewPortfolio(
            lane.phase_competition._native_phase_retention, (review,),
        )

    def _cross_competition(self, lane):
        source = SourceScanGeometry.create(
            lane.source_scan_geometry.frame_spec,
            width_scale_px_per_mm=lane.lane.scan_canvas.axis_scales.width_axis_px_per_mm,
            height_scale_px_per_mm=lane.lane.scan_canvas.axis_scales.height_axis_px_per_mm,
        )
        height = source.height_state.extent_projection_px()
        cross = placement_cross(lane.template_spec)
        bottom = cross.top_canonical_px + height.center
        cross = replace(
            cross,
            fixed_height_px=height,
            bottom_canonical_px=bottom,
            bottom_fit_interval_px=FiniteInterval.exact(bottom),
            bottom_full_interval_px=FiniteInterval.exact(bottom),
        )
        receipt = CrossSearchReceipt(
            registered_top_run_count=0,
            registered_bottom_run_count=0,
            fitted_observation_count=2,
            compatible_pair_count=0,
            single_side_inference_count=0,
            evaluated_fit_count=1,
            registered_run_bound_per_role=256,
            fitted_observation_bound=256,
            compatible_pair_bound=MAX_CROSS_PAIRS,
            evaluated_fit_bound=MAX_CROSS_PAIRS,
        )
        return CrossFitCompetition(
            template_id=lane.template_spec.template_id,
            best=cross,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            winner_basis=None,
            reason="review-only synthetic retained fit",
            failure_kind=CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
            receipt=receipt,
            aperture_aspect_ratio_authority=unavailable_aperture_aspect_ratio_authority(),
        )

    def test_no_private_phase_retention_means_no_review(self):
        self.assertIsNone(build_independent_phase_review(prepared_template_lane()))

    def test_role_class_attempts_preserve_each_failure_and_count_work_once(self):
        lane = self._retained_lane()
        original = lane.phase_competition._native_phase_retention.diagnostics[0]
        records = []
        for intrinsic_role in (0, 1):
            facts = tuple(replace(
                fact,
                bases=(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,)
                if fact.role_index == intrinsic_role else (),
                state=EvidenceState.SUPPORTED
                if fact.role_index == intrinsic_role else EvidenceState.UNAVAILABLE,
            ) for fact in original.projection.input_direct_role_authority.facts)
            authority = DirectRoleBindingAuthority(
                state=EvidenceState.UNAVAILABLE, facts=facts,
                unsupported_role_indices=(1 - intrinsic_role,),
                reason="one endpoint role remains unsupported",
            )
            projection = PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
                basis=None, projected_out_bindings=tuple(
                    PhaseCandidateProjectedBinding(fact.role_index, fact.observation_id)
                    for fact in facts if fact.state == EvidenceState.UNAVAILABLE
                ),
                retained_direct_constraint_rank=1,
                reason="diagnostic input only",
            )
            records.append((_BoundFit(original.fit, True), None, projection))
        retention = select_native_phase_retention(tuple(records))
        self.assertEqual(len(retention.diagnostics), 2)
        # This focused fixture has synthetic Cross IDs installed after the
        # prepared-lane registration checks, as in _retained_lane above.
        object.__setattr__(lane, "phase_competition", replace(
            lane.phase_competition, _native_phase_retention=retention,
        ))
        competition = self._cross_competition(lane)
        before = (lane.source_scan_geometry, lane.phase_competition.best,
                  lane.phase_competition.runner_up, lane.cross_competition)
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            side_effect=(competition, replace(competition, best=None)),
        ) as cross:
            portfolio = build_independent_phase_review(lane)
        self.assertEqual(cross.call_count, 2)
        self.assertEqual(tuple(item.phase_diagnostic for item in portfolio.reviews),
                         retention.diagnostics)
        self.assertEqual(sum(item.work.cross_call_count for item in portfolio.reviews), 2)
        self.assertEqual(sum(item.work.compose_call_count for item in portfolio.reviews), 1)
        self.assertEqual(portfolio.reviews[0].proposal.state.value, "generated")
        self.assertEqual(portfolio.reviews[1].failure.kind,
                         IndependentPhaseReviewFailureKind.CROSS_BEST_UNAVAILABLE)
        self.assertGreater(portfolio.peak_temporary_bytes,
                           max(item.work.peak_temporary_bytes for item in portfolio.reviews))
        self.assertEqual(before, (lane.source_scan_geometry, lane.phase_competition.best,
                                  lane.phase_competition.runner_up, lane.cross_competition))
        with self.assertRaisesRegex(ValueError, "complete class representatives"):
            replace(portfolio, reviews=portfolio.reviews[::-1])
        with self.assertRaisesRegex(ValueError, "complete class representatives"):
            replace(portfolio, reviews=portfolio.reviews[:1])

    def test_report_replays_original_holder_axes_before_canonical_scale_intersection(self):
        from tools.regression.report_validation import _validate_independent_phase_review
        from x5crop.detection.evidence.scan_canvas import MatchedHolder
        from x5crop.report.read_models import typed_read_model
        from x5crop.domain import WorkspaceExtent

        lane = self._retained_lane()
        canvas = lane.lane.scan_canvas
        scales = canvas.axis_scales
        # Different holder-axis intervals can produce the same shared scale.
        # Their original source identity must survive canonical intersection.
        original_scales = replace(
            scales,
            width_axis_px_per_mm=PositiveInterval(
                scales.width_axis_px_per_mm.minimum * 0.99,
                scales.width_axis_px_per_mm.maximum * 1.01,
            ),
        )
        competition = replace(self._cross_competition(lane), best=None)
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=competition,
        ):
            review = self._build_single_review(lane)
        self.assertIsNone(review.placement)
        original_source = SourceScanGeometry.create(
            review.source_scan_geometry.frame_spec,
            width_scale_px_per_mm=original_scales.width_axis_px_per_mm,
            height_scale_px_per_mm=original_scales.height_axis_px_per_mm,
        )
        review = replace(review, source_scan_geometry=replace(
            original_source, geometry_id="source-scan-geometry:999",
        ))
        source = review.source_scan_geometry
        canonical_initial = SourceScanGeometry.create(
            source.frame_spec,
            width_scale_px_per_mm=source.width_state.scale_authority,
            height_scale_px_per_mm=source.height_state.scale_authority,
        )
        self.assertEqual(source.width_state, canonical_initial.width_state)
        self.assertNotEqual(source.geometry_id, canonical_initial.geometry_id)
        holder = MatchedHolder(
            profile=canvas.selected_profile, full_count=lane.template_spec.count,
            aspect_error_ratio=canvas.matches[0].aspect_error_ratio,
            axis_scales=original_scales,
        )
        record = {
            "independent_phase_review": typed_read_model(self._portfolio(lane, review)),
            "source_scan_geometry": typed_read_model(canonical_initial),
            "template_id": lane.template_spec.template_id,
            "lane_id": lane.lane.domain.lane_id,
            "placement_proposal": {"placement_id": None},
            "alternative_placement_proposals": [],
            "selected_placement_id": None, "runner_up_placement_id": None,
            "conditional_proposal_placement_id": None, "common_h_output": None,
        }
        self.assertEqual(_validate_independent_phase_review(
            record, expected_source_extent=WorkspaceExtent(2320, 322),
            matched_holder=holder,
        ).reviews[0], review)
        with self.assertRaisesRegex(ValueError, "scan-canvas scale authority"):
            _validate_independent_phase_review(
                record, expected_source_extent=WorkspaceExtent(2320, 322),
                matched_holder=None,
            )
        with self.assertRaisesRegex(ValueError, "inherited calibrated"):
            center_scale = 0.5 * (
                scales.width_axis_px_per_mm.minimum + scales.width_axis_px_per_mm.maximum
            )
            narrowed_scales = replace(
                scales,
                width_axis_px_per_mm=PositiveInterval.exact(center_scale),
                height_axis_px_per_mm=PositiveInterval.exact(center_scale),
            )
            _validate_independent_phase_review(
                record, expected_source_extent=WorkspaceExtent(2320, 322),
                matched_holder=replace(holder, axis_scales=narrowed_scales),
            )

    def test_cross_input_reconstructs_direct_only_and_rejects_initial_h_drift(self):
        template = placement_template(1)
        source = SourceScanGeometry.create(
            FramePhysicalSpec(36.0, 24.0, 2.0),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            height_scale_px_per_mm=PositiveInterval.exact(10.0),
        )
        fit = placement_sequence(template)
        top = placement_binding(BoundaryRole.TOP, "top", 10.0)
        local = replace(
            placement_binding(BoundaryRole.TOP, "local", 11.0),
            evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        )
        conditional = replace(
            placement_binding(BoundaryRole.TOP, "conditional", 12.0),
            conditional_family_ids=("family:review",),
        )
        bottom = placement_binding(BoundaryRole.BOTTOM, "bottom", 250.0)
        original = TemplateCrossInput(
            template=template,
            fixed_height_px=source.height_state.extent_projection_px(),
            canonical_fixed_height_px=source.height_state.extent_projection_px().center,
            top_bindings=(top, local, conditional),
            bottom_bindings=(bottom,),
        )
        rebuilt = independent_phase_cross_input(original, source, fit)
        self.assertEqual(rebuilt.top_bindings, (top, conditional))
        self.assertEqual(rebuilt.bottom_bindings, (bottom,))
        self.assertEqual(rebuilt.longitudinal_support_domain_groups_px, ())
        self.assertEqual(
            rebuilt.review_support_domain_groups_px,
            (resolved_cross_support_domains_px(fit),),
        )
        self.assertEqual(rebuilt.fitted_observation_count, 3)
        self.assertEqual(
            rebuilt.maximum_evaluated_fits,
            original.maximum_evaluated_fits,
        )
        self.assertEqual(
            rebuilt.aperture_aspect_ratio_authority.state,
            EvidenceState.UNAVAILABLE,
        )
        mismatched_source = SourceScanGeometry.create(
            source.frame_spec,
            width_scale_px_per_mm=PositiveInterval.exact(9.9),
            height_scale_px_per_mm=PositiveInterval.exact(9.9),
        )
        with self.assertRaises(ValueError):
            independent_phase_cross_input(original, mismatched_source, fit)
        with self.assertRaises(ValueError):
            independent_phase_cross_input(
                replace(
                    original,
                    maximum_evaluated_fits=MAX_CROSS_PAIRS + 1,
                ),
                source,
                fit,
            )

    def test_conditional_direct_context_stays_unresolved_review_only(self):
        lane = self._retained_lane()
        conditional_binding = replace(
            lane.cross_input.top_bindings[0],
            conditional_family_ids=("family:review",),
        )
        object.__setattr__(
            lane,
            "cross_input",
            replace(
                lane.cross_input,
                top_bindings=(conditional_binding,),
                fitted_observation_count=2,
            ),
        )
        base = self._cross_competition(lane)
        conditional_best = replace(
            base.best,
            direct_bindings=tuple(
                replace(item, conditional_family_ids=("family:review",))
                for item in base.best.direct_bindings
            ),
        )
        conditional_competition = replace(
            base,
            best=conditional_best,
            failure_kind=CrossFailureKind.FAMILY_ASSIGNMENT_UNRESOLVED,
        )
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=conditional_competition,
        ):
            review = self._build_single_review(lane)
        self.assertEqual(review.cross_status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            review.cross_input.top_bindings[0].conditional_family_ids,
            ("family:review",),
        )
        self.assertEqual(
            review.cross_best.conditional_family_ids,
            ("family:review",),
        )

    def test_build_runs_one_cross_one_projection_and_keeps_review_only_ids(self):
        lane = self._retained_lane()
        competition = self._cross_competition(lane)
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=competition,
        ) as fit_cross:
            review = self._build_single_review(lane)
        self.assertIsNone(review.failure)
        self.assertIsNotNone(review.placement)
        self.assertEqual(fit_cross.call_count, 1)
        self.assertEqual(review.work.cross_call_count, 1)
        self.assertEqual(review.work.compose_call_count, 1)
        self.assertEqual(review.work.placement_projection_count, 1)
        self.assertEqual(review.work.output_count, lane.template_spec.count)
        self.assertEqual(review.work.budget_evaluation_count, lane.template_spec.count)
        self.assertEqual(review.work.feature_evaluation_count, 28)
        self.assertTrue(
            review.placement.placement_id.startswith(
                "native-endpoint-review-placement"
            )
        )
        self.assertIsNone(review.placement.global_lattice_authority)
        self.assertEqual(review.placement.width_authority_px, lane.width_authority_px)
        self.assertEqual(review.placement.height_authority_px, lane.height_authority_px)
        self.assertEqual(review.proposal.state.value, "generated")

        from tools.regression.report_validation import _validate_independent_phase_review
        from x5crop.detection.evidence.scan_canvas import MatchedHolder
        from x5crop.report.read_models import typed_read_model
        canvas = lane.lane.scan_canvas
        holder = MatchedHolder(
            canvas.selected_profile, lane.template_spec.count,
            canvas.matches[0].aspect_error_ratio, canvas.axis_scales,
        )
        record = {
            "independent_phase_review": typed_read_model(self._portfolio(lane, review)),
            "source_scan_geometry": typed_read_model(lane.source_scan_geometry),
            "template_id": lane.template_spec.template_id,
            "lane_id": lane.lane.domain.lane_id,
            "placement_proposal": {"placement_id": None},
            "alternative_placement_proposals": [],
            "selected_placement_id": None, "runner_up_placement_id": None,
            "conditional_proposal_placement_id": None, "common_h_output": None,
        }
        authority = review.placement.enclosing_support_aperture_authority
        with patch(
            "x5crop.detection.photo_geometry.template_placement.derive_enclosing_support_aperture_authority",
            return_value=replace(authority, authority_id="replayed-authority:999"),
        ):
            self.assertEqual(_validate_independent_phase_review(
                record, expected_source_extent=review.proposal.output_footprints[0].source_extent,
                matched_holder=holder,
            ).reviews[0], review)

    def test_cross_owner_programming_error_is_not_typed_as_review_failure(self):
        lane = self._retained_lane()
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            side_effect=TypeError("owner programming error"),
        ):
            with self.assertRaises(TypeError):
                build_independent_phase_review(lane)

    def test_typed_support_domain_failure_stays_in_review_failure_slot(self):
        lane = self._retained_lane()
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.resolved_cross_support_domains_px",
            side_effect=ValueError("typed support domain unavailable"),
        ):
            review = self._build_single_review(lane)
        self.assertEqual(
            review.failure.kind,
            IndependentPhaseReviewFailureKind.CROSS_INPUT_UNAVAILABLE,
        )
        self.assertEqual(review.work.cross_call_count, 0)

    def test_bound_cross_failure_does_not_fall_through_to_another_fit(self):
        lane = self._retained_lane()
        base = self._cross_competition(lane)
        bound = replace(
            base,
            best=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            winner_basis=None,
            reason="review Cross bound",
            failure_kind=CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED,
            receipt=replace(
                base.receipt,
                evaluated_fit_count=base.receipt.evaluated_fit_bound + 1,
            ),
        )
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=bound,
        ) as fit_cross:
            review = self._build_single_review(lane)
        self.assertEqual(fit_cross.call_count, 1)
        self.assertEqual(
            review.failure.kind,
            IndependentPhaseReviewFailureKind.CROSS_BOUND_EXCEEDED,
        )
        self.assertIsNone(review.placement)
        self.assertEqual(review.work.compose_call_count, 0)
        self.assertGreater(
            review.work.cross_evaluated_fit_count,
            review.cross_input.maximum_evaluated_fits,
        )

    def test_build_h_guard_returns_typed_failure_before_cross(self):
        lane = self._retained_lane()
        object.__setattr__(
            lane,
            "cross_input",
            replace(
                lane.cross_input,
                fixed_height_px=240.0,
                canonical_fixed_height_px=240.0,
            ),
        )
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
        ) as fit_cross:
            review = self._build_single_review(lane)
        self.assertEqual(
            review.failure.kind,
            IndependentPhaseReviewFailureKind.INITIAL_HEIGHT_DEPENDENCY_UNAVAILABLE,
        )
        self.assertEqual(fit_cross.call_count, 0)
        self.assertEqual(review.work.cross_call_count, 0)

    def test_compose_failure_requires_a_call_and_replays_the_actual_failure(self):
        from tools.regression.report_validation import _validate_independent_phase_attempt_context
        from x5crop.detection.photo_geometry.template_source_domain import PhaseSourceDomain
        from x5crop.detection.photo_geometry.model import BoundaryAxis
        from x5crop.domain import Box, WorkspaceExtent
        from x5crop.report.read_models import typed_read_model

        lane = self._retained_lane()
        competition = self._cross_competition(lane)
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=competition,
        ), patch(
            "x5crop.detection.photo_geometry.template_phase_review.compose_format_placement",
            side_effect=ValueError("invented compose failure"),
        ):
            portfolio = build_independent_phase_review(lane)
        review = portfolio.reviews[0]
        self.assertEqual(len(portfolio.intrinsic_refits), 1)
        self.assertEqual(review.failure.kind, IndependentPhaseReviewFailureKind.COMPOSE_UNAVAILABLE)
        with self.assertRaisesRegex(ValueError, "bounded stage"):
            replace(review, work=replace(review.work, compose_call_count=0))
        context = {
            "phase_competition": typed_read_model(lane.phase_competition),
            "cross_input": typed_read_model(lane.cross_input),
            "lane_id": lane.lane.domain.lane_id,
        }
        domain = PhaseSourceDomain(lane.lane.domain.lane_id, Box(0, 0, 500, 400),
                                   WorkspaceExtent(500, 400), BoundaryAxis.X)
        with patch("tools.regression.report_validation.fit_template_cross", return_value=competition):
            with self.assertRaisesRegex(ValueError, "invented its compose failure"):
                _validate_independent_phase_attempt_context(context, typed_read_model(review), source_domain=domain)

    def test_typed_work_and_failure_cannot_claim_generated_output(self):
        with self.assertRaises(ValueError):
            IndependentPhaseReviewWorkReceipt(
                cross_call_count=1,
                cross_evaluated_fit_count=1,
                compose_call_count=1,
                placement_projection_count=1,
                extreme_evaluation_count=200,
                output_evaluation_count=1,
                output_count=1,
                budget_evaluation_count=1,
                feature_evaluation_count=28,
                output_slot_count=1,
                peak_temporary_bytes=1,
            )
        with self.assertRaises(ValueError):
            IndependentPhaseReviewWorkReceipt(
                cross_call_count=1,
                cross_evaluated_fit_count=1,
                compose_call_count=0,
                placement_projection_count=0,
                extreme_evaluation_count=0,
                output_evaluation_count=1,
                output_count=0,
                budget_evaluation_count=2,
                feature_evaluation_count=0,
                output_slot_count=1,
                peak_temporary_bytes=1,
            )
        lane = self._retained_lane()
        competition = self._cross_competition(lane)
        with patch(
            "x5crop.detection.photo_geometry.template_phase_review.fit_template_cross",
            return_value=competition,
        ):
            review = self._build_single_review(lane)
        with self.assertRaises(ValueError):
            replace(
                review,
                failure=IndependentPhaseReviewFailure(
                    IndependentPhaseReviewFailureKind.OUTPUT_UNAVAILABLE,
                    "forced",
                ),
            )
        with self.assertRaises(ValueError):
            replace(
                review,
                work=replace(review.work, peak_temporary_bytes=0),
            )
        with self.assertRaises(ValueError):
            replace(
                review,
                cross_receipt=replace(
                    review.cross_receipt,
                    evaluated_fit_count=MAX_CROSS_PAIRS + 1,
                ),
                work=replace(
                    review.work,
                    cross_evaluated_fit_count=MAX_CROSS_PAIRS + 1,
                ),
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
