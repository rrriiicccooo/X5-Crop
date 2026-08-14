from __future__ import annotations

import unittest

from tools.tests.test_template_cross_contract import binding
from tools.tests.test_template_phase_contract import edge, template
from tools.tests.test_template_placement_contract import _compose
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.gate_checks import GateGap, TypedAssessment
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_cross import (
    TemplateCrossInput,
    fit_template_cross,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
    select_template_source,
    withhold_lane_winner,
)
from x5crop.domain import EvidenceState


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
            GateGap.SEQUENCE_AUTHORITY_UNAVAILABLE,
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


if __name__ == "__main__":
    unittest.main()
