from __future__ import annotations

from dataclasses import fields, replace
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
)
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.evidence.content.internal_boundaries import (
    internal_boundary_preservation_evidence,
)
from x5crop.detection.evidence.holder_occupancy import strip_completeness_evidence
from x5crop.formats import format_spec
from x5crop.detection.physical.separator.assignment import (
    dimension_constrained_boundary,
)
from x5crop.domain import (
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)


class CandidateEvidenceQualityContractTest(unittest.TestCase):
    def test_candidate_assessment_has_no_scalar_scores(self) -> None:
        self.assertEqual(
            {field.name for field in fields(CandidateAssessment)},
            {"evidence", "gate"},
        )

    def test_dimension_constrained_boundaries_do_not_become_supported_proof(self) -> None:
        candidate = candidate_fixture()
        evidence = candidate.assessment.evidence
        geometry = replace(
            candidate.geometry,
            separator_assignments=(),
            frame_boundaries=(
                dimension_constrained_boundary(
                    1,
                    PixelInterval.exact(100.0),
                    MeasurementProvenance(
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        "dimension_constrained_test",
                        (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                    ),
                ),
            ),
        )
        updated_evidence = replace(
            evidence,
            frame_dimensions=replace(
                evidence.frame_dimensions,
                separator_widths_px=(),
            ),
            separator_sequence=separator_sequence_evidence(geometry),
            holder_occupancy=replace(
                evidence.holder_occupancy,
                strip_completeness=strip_completeness_evidence(
                    count=geometry.count,
                    frames=geometry.frames,
                    frame_boundaries=geometry.frame_boundaries,
                    separator_assignments=geometry.separator_assignments,
                    physical_spec=format_spec(geometry.format_id),
                ),
            ),
            partial_edge_safety=partial_edge_safety_evidence(
                geometry,
                evidence.frame_coverage,
                replace(
                    evidence.frame_dimensions,
                    separator_widths_px=(),
                ),
                evidence.frame_content,
            ),
            internal_boundary_preservation=internal_boundary_preservation_evidence(
                geometry.count,
                geometry.frame_boundaries,
                geometry.inter_frame_spacings,
                evidence.frame_content,
            ),
            independence=evidence_independence_evidence(geometry),
        )
        built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
        candidate = AssessedCandidate(
            geometry,
            candidate.count_hypothesis,
            CandidateAssessment(
                updated_evidence,
                candidate_gate_for_evidence(
                    built,
                    updated_evidence,
                ),
            ),
        )
        quality = candidate.evidence_quality
        self.assertNotIn("separator_sequence", quality.supported)
        self.assertIn("separator_sequence", quality.unavailable)


if __name__ == "__main__":
    unittest.main()
