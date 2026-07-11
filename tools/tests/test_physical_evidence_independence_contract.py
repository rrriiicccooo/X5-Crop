from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.domain import EvidenceState


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PhysicalEvidenceIndependenceContractTest(unittest.TestCase):
    def test_shared_root_measurement_is_contradicted(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            sequence_provenance=replace(
                candidate.geometry.sequence_provenance,
                root_measurement="separator_profile",
            ),
        )
        evidence = evidence_independence_evidence(geometry)
        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)

    def test_sequence_root_reused_by_separator_dependency_is_contradicted(self) -> None:
        candidate = candidate_fixture()
        original_assignment = candidate.geometry.separator_assignments[0]
        observation = replace(
            original_assignment.observation,
            provenance=replace(
                original_assignment.observation.provenance,
                root_measurement="focused_separator_profile",
                dependencies=("holder_boundary_profile",),
            ),
        )
        assignment = replace(original_assignment, observation=observation)
        boundary = replace(
            candidate.geometry.frame_boundaries[0],
            assignment=assignment,
            provenance=observation.provenance,
        )
        geometry = replace(
            candidate.geometry,
            separator_observations=(observation,),
            separator_assignments=(assignment,),
            frame_boundaries=(boundary,),
        )

        evidence = evidence_independence_evidence(geometry)

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)

    def test_distinct_sequence_and_separator_roots_are_supported(self) -> None:
        evidence = evidence_independence_evidence(candidate_fixture().geometry)
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_non_separator_candidate_is_not_applicable(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(candidate.geometry, source="content")
        self.assertEqual(
            evidence_independence_evidence(geometry).state,
            EvidenceState.NOT_APPLICABLE,
        )

    def test_dimensions_and_sequence_boundaries_can_be_independent_without_hard_separator(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            separator_assignments=(),
            frame_boundaries=(),
        )
        self.assertEqual(
            evidence_independence_evidence(geometry).state,
            EvidenceState.SUPPORTED,
        )

    def test_separator_width_variation_is_not_gate_language(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection/candidate/assessment").rglob("*.py")
        )
        self.assertNotIn("separator_width_unstable", source)
        self.assertNotIn("separator_width_cv >", source)


if __name__ == "__main__":
    unittest.main()
