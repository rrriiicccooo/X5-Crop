from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.physical.separator.assignment import (
    dimension_constrained_boundary,
)
from x5crop.domain import EvidenceState, MeasurementIdentity


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PhysicalEvidenceIndependenceContractTest(unittest.TestCase):
    def test_measurement_authority_comparisons_use_typed_identities(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                text = ast.unparse(node)
                if "root_measurement" not in text:
                    continue
                if any(
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    for comparator in node.comparators
                    for child in ast.walk(comparator)
                ):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}"
                    )
        self.assertEqual(offenders, [])

    def test_shared_root_measurement_is_contradicted(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            sequence_provenance=replace(
                candidate.geometry.sequence_provenance,
                root_measurement=MeasurementIdentity.SEPARATOR_PROFILE,
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
                dependencies=(MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,),
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

    def test_non_automatic_candidate_is_not_applicable(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            automatic_processing_supported=False,
        )
        evidence = evidence_independence_evidence(geometry)
        self.assertEqual(evidence.state, EvidenceState.NOT_APPLICABLE)
        self.assertEqual(evidence.reason, "automatic_processing_not_supported")

    def test_dimension_prior_is_not_independent_measurement_evidence(self) -> None:
        candidate = candidate_fixture()
        boundary = dimension_constrained_boundary(
            1,
            candidate.geometry.frame_boundaries[0].position,
            candidate.geometry.frame_dimension_prior.provenance,
        )
        geometry = replace(
            candidate.geometry,
            separator_assignments=(),
            frame_boundaries=(boundary,),
        )
        evidence = evidence_independence_evidence(geometry)
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.supporting_root_measurements, ())

    def test_separator_width_variation_is_not_gate_language(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection/candidate/assessment").rglob("*.py")
        )
        self.assertNotIn("separator_width_unstable", source)
        self.assertNotIn("separator_width_cv >", source)


if __name__ == "__main__":
    unittest.main()
