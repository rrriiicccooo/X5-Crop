from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    cross_binding as binding,
    phase_edge as edge,
    phase_template as template,
    placement_compose as _compose,
    placement_cross,
)
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.gate_checks import (
    GATE_CHECK_DEPENDENCIES,
    GateGap,
    MinimumMissingFact,
    TypedAssessment,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.content_veto_model import (
    ContentVetoAssessment,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFit,
    CrossFailureKind,
    CrossFitStatus,
    EnclosingSupportPair,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from x5crop.detection.photo_geometry.output_model import (
    OutputBoundaryUse,
    SharedStripDirection,
)
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
    select_template_source,
    withhold_lane_winner,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId


def _resolved():
    spec = template(1)
    phase = fit_template_phase(
        (edge("edge:start", 40.0), edge("edge:end", 140.0)),
        spec,
    )
    cross = fit_template_cross(
        TemplateCrossInput(
            template=spec,
            fixed_height_px=240.0,
            top_bindings=(binding(BoundaryRole.TOP, "top", 100.0),),
            bottom_bindings=(binding(BoundaryRole.BOTTOM, "bottom", 340.0),),
        )
    )
    assert phase.best is not None and cross.best is not None
    direction = cross.best.selected_direction
    assert direction is not None
    placement = _compose(
        spec,
        phase.best,
        cross.best,
        lane_id="lane:0",
    )
    return phase, cross, placement


def _with_partial_height_role_authority(
    phase,
    *,
    traces: tuple[int, ...] = (150, 300),
):
    authority = DirectRoleBindingAuthority(
        state=EvidenceState.SUPPORTED,
        facts=(
            DirectRoleAuthorityFact(
                role_index=0,
                lane_ordinal=1,
                role=BoundaryRole.START,
                observation_id=ObservationId("edge:start"),
                evidence_group_id=ObservationId("evidence-group:start"),
                independent_support_region_count=2,
                bases=(
                    DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,
                ),
                blocking_material_conflict_ids=(),
                state=EvidenceState.SUPPORTED,
                trace_coordinates_px=traces,
            ),
        ),
        unsupported_role_indices=(),
        reason=None,
    )
    return replace(phase, direct_role_binding_authority=authority)


def _enclosing_cross_fit(spec) -> CrossFit:
    top = binding(
        BoundaryRole.TOP,
        "holder-top",
        90.0,
        role_authorized=False,
        enclosing_pair_id="holder-pair",
    )
    bottom = binding(
        BoundaryRole.BOTTOM,
        "holder-bottom",
        350.0,
        role_authorized=False,
        enclosing_pair_id="holder-pair",
    )
    direction = SharedStripDirection(
        direction_id="direction:holder-pair",
        selected_observation_ids=(
            top.observation_id,
            bottom.observation_id,
        ),
        full_angle_interval_degrees=FiniteInterval(-0.2, 0.2),
        observed_angle_interval_degrees=FiniteInterval(-0.2, 0.2),
        canonical_angle_degrees=0.0,
    )
    support = EnclosingSupportPair(
        top_canonical_px=90.0,
        bottom_canonical_px=350.0,
        top_full_interval_px=FiniteInterval.exact(90.0),
        bottom_full_interval_px=FiniteInterval.exact(350.0),
        top_provenance_ids=(top.observation_id,),
        bottom_provenance_ids=(bottom.observation_id,),
        observed_span_px=FiniteInterval.exact(260.0),
        reference_trace_px=0.0,
        trace_coordinates_px=top.trace_coordinates_px,
        top_trace_intervals_px=top.trace_position_intervals_px,
        bottom_trace_intervals_px=bottom.trace_position_intervals_px,
    )
    return CrossFit(
        template_id=spec.template_id,
        lane_reference_trace_px=0.0,
        fixed_height_px=FiniteInterval.exact(240.0),
        top_canonical_px=100.0,
        bottom_canonical_px=340.0,
        top_fit_interval_px=FiniteInterval.exact(100.0),
        bottom_fit_interval_px=FiniteInterval.exact(340.0),
        top_full_interval_px=FiniteInterval.exact(100.0),
        bottom_full_interval_px=FiniteInterval.exact(340.0),
        direct_bindings=(top, bottom),
        inferred_bindings=(),
        selected_direction=direction,
        direct_pair=True,
        shared_trace_support_count=3,
        continuous_support_fraction=1.0,
        residual_sum_px=0.0,
        boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        pair_support_mode=None,
        enclosing_support_pair=support,
    )


class TemplateSelectionContractTest(unittest.TestCase):
    def test_gate_dependency_graph_remains_current_contract(self) -> None:
        self.assertEqual(
            GATE_CHECK_DEPENDENCIES,
            {
                "source_scan_geometry": (
                    "scan_canvas_authority",
                    "observation_completeness",
                ),
                "complete_placement": (
                    "output_slot_count",
                    "observation_completeness",
                    "source_scan_geometry",
                    "producer_coverage",
                ),
                "content_protection": ("complete_placement",),
                "selected_placement": (
                    "complete_placement",
                    "content_protection",
                    "adjacency_relation_authority",
                ),
                "dual_lane_fill": ("selected_placement",),
                "selected_output_footprint": (
                    "selected_placement",
                    "dual_lane_fill",
                    "source_lane_authority",
                ),
                "calibrated_nominal_grid_authority": (
                    "selected_output_footprint",
                ),
                "direct_use_budget": (
                    "selected_output_footprint",
                    "calibrated_nominal_grid_authority",
                ),
            },
        )

    def test_resolved_fits_publish_one_selected_placement(self) -> None:
        phase, cross, placement = _resolved()

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.SUPPORTED)
        self.assertEqual(competition.selected_placement_id, placement.placement_id)
        self.assertIsNone(competition.failure)

    def test_adjacency_topology_counterevidence_has_one_typed_gate_reason(
        self,
    ) -> None:
        phase, cross, placement = _resolved()
        phase = replace(
            phase,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "ordinary positive separator is contradicted"
            ),
            failure_kind=PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
            winner_basis=None,
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        assert competition.failure is not None
        self.assertEqual(
            competition.failure.gap,
            GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED,
        )
        facts = {
            code: TypedAssessment(EvidenceState.SUPPORTED, None)
            for code in CANDIDATE_GATE_CHECK_CODES
        }
        facts["adjacency_relation_authority"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED,
            competition.failure,
        )
        decision = apply_decision_gate(candidate_gate_assessment(facts))
        self.assertEqual(
            decision.final_review_reasons,
            ("adjacency_topology_unresolved",),
        )

    def test_competing_contact_topologies_keep_the_topology_gate_reason(
        self,
    ) -> None:
        phase, cross, placement = _resolved()
        phase = replace(
            phase,
            status=PhaseFitStatus.AMBIGUOUS,
            ambiguity_reason="multiple contact ordinals remain legal",
            failure_kind=PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
            winner_basis=None,
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        assert competition.failure is not None
        self.assertEqual(
            competition.failure.gap,
            GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED,
        )

    def test_adjacency_continuity_failure_has_one_typed_gate_reason(
        self,
    ) -> None:
        phase, cross, placement = _resolved()
        phase = replace(
            phase,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="separator material is unresolved",
            failure_kind=(
                PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
            ),
            winner_basis=None,
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        assert competition.failure is not None
        self.assertEqual(
            competition.failure.gap,
            GateGap.ADJACENCY_CONTINUITY_UNRESOLVED,
        )
        facts = {
            code: TypedAssessment(EvidenceState.SUPPORTED, None)
            for code in CANDIDATE_GATE_CHECK_CODES
        }
        facts["adjacency_relation_authority"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.ADJACENCY_CONTINUITY_UNRESOLVED,
            competition.failure,
        )
        decision = apply_decision_gate(candidate_gate_assessment(facts))
        self.assertEqual(
            decision.final_review_reasons,
            ("adjacency_continuity_unresolved",),
        )

    def test_partial_height_role_accepts_a_direct_aperture_pair(self) -> None:
        phase, cross, placement = _resolved()
        phase = _with_partial_height_role_authority(phase)

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.SUPPORTED)
        self.assertEqual(competition.selected_placement_id, placement.placement_id)
        authority = competition.direct_role_aperture_domain_authority
        assert authority is not None
        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            authority.facts[0].basis.value,
            "direct_aperture_pair",
        )

    def test_partial_height_role_accepts_a_unique_enclosing_aperture(self) -> None:
        phase, cross, _placement = _resolved()
        phase = _with_partial_height_role_authority(phase)
        assert phase.best is not None
        enclosing_fit = _enclosing_cross_fit(phase.template)
        enclosing_cross = replace(cross, best=enclosing_fit)
        placement = _compose(
            phase.template,
            phase.best,
            enclosing_fit,
            lane_id="lane:0",
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=enclosing_cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.SUPPORTED)
        authority = competition.direct_role_aperture_domain_authority
        assert authority is not None
        self.assertEqual(
            authority.facts[0].basis.value,
            "enclosing_support_aperture",
        )

    def test_partial_height_role_outside_aperture_is_counterevidence(self) -> None:
        phase, cross, placement = _resolved()
        phase = _with_partial_height_role_authority(
            phase,
            traces=(50, 300),
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.CONTRADICTED)
        assert competition.failure is not None
        self.assertEqual(
            competition.failure.gap,
            GateGap.DIRECT_ROLE_APERTURE_DOMAIN_CONFLICT,
        )
        authority = competition.direct_role_aperture_domain_authority
        assert authority is not None
        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)

    def test_partial_height_role_rejects_a_collapsed_aperture_domain(self) -> None:
        phase, cross, _placement = _resolved()
        phase = _with_partial_height_role_authority(phase)
        assert phase.best is not None and cross.best is not None
        direction = cross.best.selected_direction
        assert direction is not None
        wide_direction = replace(
            direction,
            full_angle_interval_degrees=FiniteInterval(-80.0, 80.0),
            observed_angle_interval_degrees=FiniteInterval(-80.0, 80.0),
        )
        collapsed_fit = replace(
            cross.best,
            selected_direction=wide_direction,
        )
        collapsed_cross = replace(cross, best=collapsed_fit)
        placement = _compose(
            phase.template,
            phase.best,
            collapsed_fit,
            lane_id="lane:0",
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=collapsed_cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.CONTRADICTED)
        authority = competition.direct_role_aperture_domain_authority
        assert authority is not None
        self.assertEqual(
            authority.facts[0].failure_kind.value,
            "aperture_domain_collapsed",
        )

    def test_partial_height_role_rejects_an_inferred_aperture_side(self) -> None:
        phase, cross, _placement = _resolved()
        phase = _with_partial_height_role_authority(phase)
        assert phase.best is not None
        inferred_cross_fit = placement_cross(
            phase.template,
            one_sided=True,
        )
        inferred_cross = replace(cross, best=inferred_cross_fit)
        placement = _compose(
            phase.template,
            phase.best,
            inferred_cross_fit,
            lane_id="lane:0",
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=inferred_cross,
            content_assessment=None,
        )

        self.assertEqual(competition.state, EvidenceState.UNAVAILABLE)
        assert competition.failure is not None
        self.assertEqual(
            competition.failure.gap,
            GateGap.DIRECT_ROLE_APERTURE_DOMAIN_UNAVAILABLE,
        )
        self.assertEqual(
            competition.failure.minimum_missing_fact,
            MinimumMissingFact.DIRECT_APERTURE_DOMAIN,
        )
        authority = competition.direct_role_aperture_domain_authority
        assert authority is not None
        self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)

    def test_unresolved_phase_has_one_typed_minimum_missing_fact(self) -> None:
        _phase, cross, _placement = _resolved()
        unresolved = fit_template_phase((), template(1))

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=unresolved,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(
            competition.failure.gap,
            GateGap.PHASE_ANCHOR_UNAVAILABLE,
        )
        self.assertEqual(
            competition.failure.minimum_missing_fact,
            MinimumMissingFact.ABSOLUTE_PHASE_ANCHOR,
        )

    def test_phase_mismatch_reports_pitch_closure_as_the_missing_fact(self) -> None:
        _phase, cross, _placement = _resolved()
        mismatch = fit_template_phase(
            (edge("outside-holder", 1000.0),),
            template(1),
            holder_span_px=FiniteInterval(0.0, 400.0),
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=mismatch,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(competition.failure.gap, GateGap.PHASE_TEMPLATE_MISMATCH)
        self.assertEqual(
            competition.failure.minimum_missing_fact,
            MinimumMissingFact.PITCH_CLOSURE,
        )

    def test_inferred_adjacency_failures_keep_distinct_typed_facts(self) -> None:
        phase, cross, _placement = _resolved()
        cases = (
            (
                PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
                GateGap.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE,
                MinimumMissingFact.GLOBAL_LATTICE_AUTHORITY,
            ),
            (
                PhaseFailureKind.CALIBRATED_NOMINAL_GRID_CONFLICT,
                GateGap.CALIBRATED_NOMINAL_GRID_CONFLICT,
                MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            ),
            (
                PhaseFailureKind.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE,
                GateGap.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE,
                MinimumMissingFact.ADJACENCY_OBSERVATION_COVERAGE,
            ),
            (
                PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
                GateGap.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
                MinimumMissingFact.DIRECT_ROLE_BINDING_AUTHORITY,
            ),
            (
                PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT,
                GateGap.SEPARATOR_MATERIAL_CONFLICT,
                MinimumMissingFact.SEPARATOR_MATERIAL_AUTHORITY,
            ),
            (
                PhaseFailureKind.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE,
                GateGap.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE,
                MinimumMissingFact.OUTER_FRAME_OBSERVATION_AUTHORITY,
            ),
            (
                PhaseFailureKind.SOURCE_FRAME_WIDTH_CONFLICT,
                GateGap.SOURCE_FRAME_WIDTH_CONFLICT,
                MinimumMissingFact.SOURCE_PHYSICAL_COMPATIBILITY,
            ),
        )
        for failure_kind, expected_gap, expected_fact in cases:
            with self.subTest(failure_kind=failure_kind.value):
                unresolved = replace(
                    phase,
                    status=PhaseFitStatus.UNRESOLVED,
                    ambiguity_reason=failure_kind.value,
                    failure_kind=failure_kind,
                    winner_basis=None,
                )
                competition = select_lane_template_placement(
                    lane_id="lane:0",
                    best=None,
                    runner_up=None,
                    phase=unresolved,
                    cross=cross,
                    content_assessment=None,
                )
                assert competition.failure is not None
                self.assertEqual(competition.failure.gap, expected_gap)
                self.assertEqual(
                    competition.failure.minimum_missing_fact,
                    expected_fact,
                )

    def test_discrete_phase_runner_reports_unique_placement(self) -> None:
        _phase, cross, _placement = _resolved()
        ambiguous = fit_template_phase(
            tuple(
                edge(f"ambiguous:{index}", coordinate)
                for index, coordinate in enumerate((40.0, 140.0, 200.0, 300.0))
            ),
            template(2),
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=ambiguous,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(
            competition.failure.gap,
            GateGap.PHASE_PLACEMENT_AMBIGUOUS,
        )
        self.assertEqual(
            competition.failure.minimum_missing_fact,
            MinimumMissingFact.UNIQUE_PLACEMENT,
        )

    def test_content_cannot_assess_an_unresolved_placement(self) -> None:
        phase, cross, placement = _resolved()
        unresolved_cross = replace(
            cross,
            status=CrossFitStatus.UNRESOLVED,
            winner_basis=None,
            reason="non-equivalent cross fits remain",
            failure_kind=CrossFailureKind.NON_EQUIVALENT_FITS,
        )
        assessment = ContentVetoAssessment(
            assessment_id="content:unresolved",
            placement_id=placement.placement_id,
            facts=(),
        )

        with self.assertRaisesRegex(ValueError, "unique fitted placement"):
            select_lane_template_placement(
                lane_id="lane:0",
                best=placement,
                runner_up=None,
                phase=phase,
                cross=unresolved_cross,
                content_assessment=assessment,
            )

    def test_source_withholding_preserves_the_exact_failure_fact(self) -> None:
        phase, cross, placement = _resolved()
        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )
        source = select_template_source(
            (competition,),
            lane_ids=("lane:0",),
            shared_scan_geometry=None,
        )
        assert source.failure is not None

        withheld = withhold_lane_winner(
            competition,
            failure=source.failure,
        )

        self.assertIs(withheld.failure, source.failure)
        self.assertEqual(source.failure.gap, GateGap.SHARED_AUTHORITY_UNAVAILABLE)

    def test_candidate_and_decision_gate_preserve_failure_without_selecting(self) -> None:
        failure = select_template_source(
            (
                select_lane_template_placement(
                    lane_id="lane:0",
                    best=None,
                    runner_up=None,
                    phase=fit_template_phase((), template(1)),
                    cross=_resolved()[1],
                    content_assessment=None,
                ),
            ),
            lane_ids=("lane:0",),
            shared_scan_geometry=None,
        ).failure
        assert failure is not None
        facts = {
            code: TypedAssessment(EvidenceState.SUPPORTED, None)
            for code in CANDIDATE_GATE_CHECK_CODES
        }
        facts["selected_placement"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            failure.gap,
            failure,
        )

        candidate = candidate_gate_assessment(facts)
        decision = apply_decision_gate(candidate)
        candidate_fact = next(
            item for item in candidate.checks if item.code == "selected_placement"
        )
        decision_fact = next(
            item for item in decision.checks if item.code == "selected_placement"
        )

        self.assertIs(candidate_fact.failure, failure)
        self.assertIs(decision_fact.failure, failure)
        self.assertIsNone(candidate_fact.final_review_reason)
        self.assertIsNotNone(decision_fact.final_review_reason)

    def test_source_selection_allows_lane_local_directions_to_differ(self) -> None:
        phase, cross, left_placement = _resolved()
        assert cross.best is not None and cross.best.selected_direction is not None
        right_direction = replace(
            cross.best.selected_direction,
            direction_id="direction:right",
            full_angle_interval_degrees=FiniteInterval(0.1, 0.2),
            observed_angle_interval_degrees=FiniteInterval(0.1, 0.2),
            canonical_angle_degrees=0.15,
        )
        assert phase.best is not None
        right_cross_fit = replace(
            cross.best,
            selected_direction=right_direction,
        )
        right_cross = replace(cross, best=right_cross_fit)
        right_placement = _compose(
            phase.template,
            phase.best,
            right_cross_fit,
            lane_id="lane:1",
        )
        left = select_lane_template_placement(
            lane_id="lane:0",
            best=left_placement,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )
        right = select_lane_template_placement(
            lane_id="lane:1",
            best=right_placement,
            runner_up=None,
            phase=phase,
            cross=right_cross,
            content_assessment=None,
        )
        source = select_template_source(
            (left, right),
            lane_ids=("lane:0", "lane:1"),
            shared_scan_geometry=left_placement.source_scan_geometry,
        )

        self.assertEqual(source.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            source.selected_placement_ids,
            (left_placement.placement_id, right_placement.placement_id),
        )

if __name__ == "__main__":
    unittest.main()
