from __future__ import annotations

from dataclasses import fields, replace
import unittest

from tools.tests.physical_gate_support import (
    _candidate_geometry,
    candidate_evidence_fixture,
    candidate_fixture,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
)
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.domain import EvidenceState


class CandidateEvidenceQualityContractTest(unittest.TestCase):
    def test_candidate_assessment_has_no_scalar_scores(self) -> None:
        self.assertEqual(
            {field.name for field in fields(CandidateAssessment)},
            {"evidence", "gate"},
        )

    def test_gate_projection_is_not_counted_as_duplicate_physical_evidence(
        self,
    ) -> None:
        quality = candidate_fixture().evidence_quality

        self.assertNotIn("content_preservation", quality.supported)
        self.assertNotIn("content_preservation", quality.contradicted)
        self.assertNotIn("content_preservation", quality.unavailable)

        geometry = replace(_candidate_geometry(), strip_mode="partial")
        evidence = candidate_evidence_fixture(geometry=geometry)
        hypothesis = CountHypothesis(
            geometry.count,
            "partial",
            CountHypothesisSource.AUTOMATIC,
        )
        built = BuiltCandidate(geometry, hypothesis, ())
        partial = AssessedCandidate(
            geometry,
            hypothesis,
            CandidateAssessment(
                evidence,
                candidate_gate_for_evidence(built, evidence),
            ),
        )
        partial_quality = partial.evidence_quality
        self.assertNotIn("partial_edge_safety", partial_quality.supported)
        self.assertNotIn("partial_edge_safety", partial_quality.contradicted)
        self.assertNotIn("partial_edge_safety", partial_quality.unavailable)

    def test_dimension_only_frame_boundaries_do_not_become_separator_proof(
        self,
    ) -> None:
        evidence = separator_sequence_evidence(
            _candidate_geometry(boundary_proof_supported=False)
        )

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.hard_count, 0)
        self.assertEqual(evidence.provisional_boundary_count, 1)


if __name__ == "__main__":
    unittest.main()
