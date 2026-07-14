from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from tools.tests.physical_gate_support import candidate_evidence_fixture, candidate_fixture
from x5crop.detection.candidate.model import boundary_proof_paths_for_geometry
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoApertureEdgeSource,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _geometry_with_measured_internal_edges():
    geometry = candidate_fixture().geometry
    left_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId("measured_internal_trailing_edge"),
        (MeasurementIdentity.GRAY_WORK,),
        "measured internal trailing edge",
    )
    right_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId("measured_internal_leading_edge"),
        (MeasurementIdentity.GRAY_WORK,),
        "measured internal leading edge",
    )
    left = replace(
        geometry.photo_apertures[0],
        trailing=replace(
            geometry.photo_apertures[0].trailing,
            source=PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
            provenance=left_provenance,
        ),
    )
    right = replace(
        geometry.photo_apertures[1],
        leading=replace(
            geometry.photo_apertures[1].leading,
            source=PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
            provenance=right_provenance,
        ),
    )
    return replace(
        geometry,
        photo_apertures=(left, right),
        separator_assignments=(),
    )


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
        provenance = replace(
            original_assignment.observation.provenance,
            dependencies=(candidate.geometry.sequence_provenance.root_measurement,),
        )
        observation = replace(
            original_assignment.observation,
            appearance=replace(
                original_assignment.observation.appearance,
                provenance=provenance,
            ),
            provenance=provenance,
        )
        preceding = replace(
            original_assignment.preceding_trailing_edge,
            provenance=provenance,
        )
        following = replace(
            original_assignment.following_leading_edge,
            provenance=provenance,
        )
        assignment = replace(
            original_assignment,
            observation=observation,
            preceding_trailing_edge=preceding,
            following_leading_edge=following,
        )
        first = replace(candidate.geometry.photo_apertures[0], trailing=preceding)
        second = replace(candidate.geometry.photo_apertures[1], leading=following)
        geometry = replace(
            candidate.geometry,
            separator_observations=(observation,),
            separator_assignments=(assignment,),
            photo_apertures=(first, second),
            inter_photo_spacings=(
                replace(
                    candidate.geometry.inter_photo_spacings[0],
                    provenance=provenance,
                ),
            ),
        )

        evidence = evidence_independence_evidence(geometry)

        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)

    def test_distinct_sequence_and_separator_roots_are_supported(self) -> None:
        evidence = evidence_independence_evidence(candidate_fixture().geometry)
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_dimension_prior_is_not_independent_measurement_evidence(self) -> None:
        candidate = candidate_fixture()
        geometry = replace(
            candidate.geometry,
            separator_assignments=(),
        )
        evidence = evidence_independence_evidence(geometry)
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.supporting_root_measurements, ())

    def test_measured_internal_photo_edges_are_independent_boundary_evidence(self) -> None:
        measured_geometry = _geometry_with_measured_internal_edges()

        evidence = evidence_independence_evidence(measured_geometry)

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            evidence.supporting_root_measurements,
            (MeasurementIdentity.PHOTO_EDGES,),
        )

    def test_geometry_proof_accepts_an_independent_internal_photo_edge_anchor(self) -> None:
        geometry = _geometry_with_measured_internal_edges()
        evidence = candidate_evidence_fixture(geometry=geometry)

        paths = boundary_proof_paths_for_geometry(geometry, evidence)
        geometry_path = next(path for path in paths if path.code == "geometry_led")

        self.assertEqual(geometry_path.state, EvidenceState.SUPPORTED)
        self.assertIn("independent_internal_photo_edge_anchor", geometry_path.supporting_evidence)

    def test_separator_width_variation_is_not_gate_language(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection/candidate/assessment").rglob("*.py")
        )
        self.assertNotIn("separator_width_unstable", source)
        self.assertNotIn("separator_width_cv >", source)


if __name__ == "__main__":
    unittest.main()
