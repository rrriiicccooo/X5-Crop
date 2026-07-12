from __future__ import annotations

from dataclasses import fields, replace
import unittest

from tools.tests.physical_gate_support import candidate_evidence_fixture
from x5crop.detection.candidate.assessment.quality import evidence_quality
from x5crop.detection.candidate.model import CandidateAssessment
from x5crop.domain import EvidenceState, FrameBoundaryReference


class CandidateEvidenceQualityContractTest(unittest.TestCase):
    def test_candidate_assessment_has_no_scalar_scores(self) -> None:
        self.assertEqual(
            {field.name for field in fields(CandidateAssessment)},
            {"evidence", "gate"},
        )

    def test_separator_width_variation_does_not_change_evidence_quality(self) -> None:
        evidence = candidate_evidence_fixture()
        stable = evidence_quality(evidence, (), residuals=None)
        variable = evidence_quality(
            replace(
                evidence,
                frame_dimensions=replace(
                    evidence.frame_dimensions,
                    separator_width_cv=0.95,
                    separator_widths_px=(2.0, 20.0),
                ),
            ),
            (),
            residuals=None,
        )
        self.assertEqual(stable, variable)

    def test_dimension_constrained_boundaries_do_not_become_supported_proof(self) -> None:
        evidence = candidate_evidence_fixture()
        constrained = replace(
            evidence.separator_sequence,
            state=EvidenceState.UNAVAILABLE,
            hard_count=0,
            dimension_constrained_count=1,
            hard_boundaries=(),
            missing_boundaries=(FrameBoundaryReference(None, 1),),
            hard_tonal_evidence=(),
        )
        quality = evidence_quality(
            replace(evidence, separator_sequence=constrained),
            (),
            residuals=None,
        )
        self.assertNotIn("separator_sequence", quality.supported)
        self.assertIn("separator_sequence", quality.unavailable)


if __name__ == "__main__":
    unittest.main()
