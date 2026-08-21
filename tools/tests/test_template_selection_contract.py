from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    cross_binding as binding,
    phase_edge as edge,
    phase_template as template,
    placement_compose as _compose,
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
    failure_fact,
)
from x5crop.detection.photo_geometry.detector import _shared_direction
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.content_veto_model import (
    ContentVetoAssessment,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFitStatus,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
    select_template_source,
    withhold_lane_winner,
)
from x5crop.domain import EvidenceState, FiniteInterval


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
            holder_short_axis_center_px=220.0,
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
        direction=direction,
        lane_id="lane:0",
    )
    return phase, cross, placement


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
                    "local_advance_authority",
                ),
                "dual_lane_fill": ("selected_placement",),
                "shared_strip_direction": (
                    "source_scan_geometry",
                    "selected_placement",
                ),
                "sequence_authority": ("selected_placement",),
                "cross_authority": ("selected_placement",),
                "shared_authority": ("selected_placement",),
                "slot_ordinal_assignment": ("complete_placement",),
                "selected_output_footprint": (
                    "selected_placement",
                    "dual_lane_fill",
                    "source_lane_authority",
                ),
                "direct_use_budget": ("selected_output_footprint",),
                "transform_sampling": (
                    "selected_placement",
                    "source_lane_authority",
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
            reason="non-equivalent cross fits remain",
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
            shared_direction=None,
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
            shared_direction=None,
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

    def test_direction_failure_is_preserved_before_generic_placement(self) -> None:
        phase, cross, _placement = _resolved()
        failure = failure_fact(
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE,
            detail="sequence and cross direction evidence are incompatible",
        )

        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
            direction_failure=failure,
        )

        self.assertIs(competition.failure, failure)
        self.assertEqual(
            competition.failure.gap,
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE,
        )
        source = select_template_source(
            (competition,),
            lane_ids=("lane:0",),
            shared_scan_geometry=None,
            shared_direction=None,
        )
        self.assertIs(source.failure, failure)
        facts = {
            code: TypedAssessment(EvidenceState.SUPPORTED, None)
            for code in CANDIDATE_GATE_CHECK_CODES
        }
        facts["complete_placement"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            failure.gap,
            source.failure,
        )

        candidate = candidate_gate_assessment(facts)
        complete = next(
            item
            for item in candidate.checks
            if item.code == "complete_placement"
        )

        self.assertTrue(complete.evaluated)
        self.assertIs(complete.failure, failure)
        self.assertEqual(
            complete.gap,
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE,
        )

    def test_disjoint_lane_directions_have_typed_nonunique_failure(self) -> None:
        _phase, _cross, placement = _resolved()
        left = replace(
            placement.direction,
            direction_id="direction:left",
            full_angle_interval_degrees=FiniteInterval(-0.2, -0.1),
            observed_angle_interval_degrees=FiniteInterval(-0.2, -0.1),
            canonical_angle_degrees=-0.15,
        )
        right = replace(
            placement.direction,
            direction_id="direction:right",
            full_angle_interval_degrees=FiniteInterval(0.1, 0.2),
            observed_angle_interval_degrees=FiniteInterval(0.1, 0.2),
            canonical_angle_degrees=0.15,
        )

        direction, failure = _shared_direction(
            ((left, None), (right, None))
        )

        self.assertIsNone(direction)
        assert failure is not None
        self.assertEqual(
            failure.gap,
            GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE,
        )

if __name__ == "__main__":
    unittest.main()
