from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_evidence_fixture
from x5crop.detection.candidate.assessment.scoring import candidate_scores
from x5crop.domain import EvidenceState
from x5crop.policies.registry import get_detection_policy


class CandidateLifecycleScoringContractTest(unittest.TestCase):
    def test_scoring_does_not_branch_on_format_identity(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop/detection/candidate/assessment"
        offenders = [
            str(path)
            for path in root.rglob("*.py")
            if "format_id ==" in path.read_text() or "format_id in" in path.read_text()
        ]
        self.assertEqual(offenders, [])

    def test_separator_width_variation_is_not_a_scoring_input(self) -> None:
        policy = get_detection_policy("120-645", "full")
        evidence = candidate_evidence_fixture()
        stable = candidate_scores(
            evidence,
            0.5,
            policy.scoring,
            policy.content.support,
        )
        variable = candidate_scores(
            replace(
                evidence,
                frame_dimensions=replace(
                    evidence.frame_dimensions,
                    separator_width_cv=0.95,
                    separator_widths_px=(2.0, 20.0),
                ),
            ),
            0.5,
            policy.scoring,
            policy.content.support,
        )
        self.assertEqual(stable, variable)

    def test_dimension_constrained_boundaries_do_not_gain_separator_credit(self) -> None:
        policy = get_detection_policy("135", "full")
        evidence = candidate_evidence_fixture()
        hard = candidate_scores(
            evidence,
            0.0,
            policy.scoring,
            policy.content.support,
        )
        constrained = replace(
            evidence.separator_sequence,
            state=EvidenceState.UNAVAILABLE,
            hard_count=0,
            dimension_constrained_count=1,
            hard_boundary_indexes=(),
            missing_boundary_indexes=(1,),
            hard_scores=(),
        )
        modeled = candidate_scores(
            replace(evidence, separator_sequence=constrained),
            0.0,
            policy.scoring,
            policy.content.support,
        )
        self.assertGreater(hard.separator, modeled.separator)


if __name__ == "__main__":
    unittest.main()
