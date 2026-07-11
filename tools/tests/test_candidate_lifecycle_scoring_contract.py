from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_evidence_fixture
from x5crop.detection.candidate.assessment.scoring import candidate_scores
from x5crop.detection.physical.photo_size import photo_size_consistency_from_gap_edges
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
            "separator",
            0.5,
            policy.scoring,
            policy.content.support,
        )
        variable_dimensions = replace(
            evidence.frame_dimensions,
            separator_width_cv=0.95,
            separator_widths_px=(2.0, 20.0),
        )
        variable = candidate_scores(
            replace(evidence, frame_dimensions=variable_dimensions),
            "separator",
            0.5,
            policy.scoring,
            policy.content.support,
        )
        self.assertEqual(stable, variable)

    def test_model_gaps_receive_less_credit_than_hard_separators(self) -> None:
        policy = get_detection_policy("135", "full")
        evidence = candidate_evidence_fixture()
        hard = candidate_scores(
            evidence,
            "separator",
            0.0,
            policy.scoring,
            policy.content.support,
        )
        model_sequence = replace(
            evidence.separator_sequence,
            hard_count=0,
            model_count=1,
            hard_indexes=(),
            hard_scores=(),
        )
        model = candidate_scores(
            replace(evidence, separator_sequence=model_sequence),
            "separator",
            0.0,
            policy.scoring,
            policy.content.support,
        )
        self.assertGreater(hard.separator, model.separator)

    def test_photo_size_uses_separator_edges_not_center_pitch(self) -> None:
        from tools.tests.physical_gate_support import separator_observation

        result = photo_size_consistency_from_gap_edges(
            [
                separator_observation(1, 100.0, start=90.0, end=110.0),
                separator_observation(2, 230.0, start=220.0, end=240.0),
            ],
            0.0,
            120.0,
            3,
        )
        self.assertEqual(result.photo_widths, (90.0, 110.0, 120.0))


if __name__ == "__main__":
    unittest.main()
