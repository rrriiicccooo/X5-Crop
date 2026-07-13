from __future__ import annotations

from dataclasses import fields, replace
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.model import CandidateAssessment
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.domain import (
    EvidenceState,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoApertureEdgeSource,
)


class CandidateEvidenceQualityContractTest(unittest.TestCase):
    def test_candidate_assessment_has_no_scalar_scores(self) -> None:
        self.assertEqual(
            {field.name for field in fields(CandidateAssessment)},
            {"evidence", "gate"},
        )

    def test_dimension_only_aperture_edges_do_not_become_separator_proof(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            ObservationId("dimension_only_internal_boundary"),
            (MeasurementIdentity.FRAME_DIMENSIONS,),
            "dimension-only internal boundary",
        )
        first = replace(
            geometry.photo_apertures[0],
            trailing=replace(
                geometry.photo_apertures[0].trailing,
                state=EvidenceState.UNAVAILABLE,
                source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                provenance=provenance,
            ),
        )
        second = replace(
            geometry.photo_apertures[1],
            leading=replace(
                geometry.photo_apertures[1].leading,
                state=EvidenceState.UNAVAILABLE,
                source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
                provenance=provenance,
            ),
        )
        provisional = replace(
            geometry,
            photo_apertures=(first, second),
            separator_assignments=(),
            inter_photo_spacings=(
                replace(
                    geometry.inter_photo_spacings[0],
                    basis=InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS,
                    provenance=provenance,
                ),
            ),
        )

        evidence = separator_sequence_evidence(provisional)

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.hard_count, 0)
        self.assertEqual(evidence.provisional_boundary_count, 1)


if __name__ == "__main__":
    unittest.main()
