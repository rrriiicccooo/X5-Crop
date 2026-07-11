from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_fixture, separator_observation
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.evidence.state import EvidenceState


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

    def test_outer_root_reused_by_separator_dependency_is_contradicted(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            sequence_provenance=replace(
                candidate.geometry.sequence_provenance,
                root_measurement="separator_profile",
            ),
            separators=tuple(
                replace(
                    observation,
                    provenance=replace(
                        observation.provenance,
                        root_measurement="edge_refine_profiles",
                        dependencies=("separator_profile",),
                    ),
                )
                for observation in candidate.geometry.separators
            ),
        )

        evidence = evidence_independence_evidence(geometry)

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)

    def test_distinct_outer_and_separator_roots_are_supported(self) -> None:
        evidence = evidence_independence_evidence(candidate_fixture().geometry)
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_non_separator_candidate_is_not_applicable(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(candidate.geometry, source="content")
        self.assertEqual(
            evidence_independence_evidence(geometry).state,
            EvidenceState.NOT_APPLICABLE,
        )

    def test_missing_hard_measurement_is_unavailable(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            separators=(separator_observation(1, 100.0, method="equal"),),
        )
        self.assertEqual(
            evidence_independence_evidence(geometry).state,
            EvidenceState.UNAVAILABLE,
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
