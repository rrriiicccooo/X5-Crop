from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import get_type_hints
import unittest

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.candidate.assessment.candidate_gate import (
    BOUNDARY_PROOF_PATH_CODES,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.detection.evidence.separator_sequence import SeparatorSequenceEvidence
from x5crop.detection.physical.boundary_detection import boundary_path_groups
from x5crop.domain import BoundaryKind, EvidenceState, FrameBoundaryReference
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.report.identity import REPORT_SCHEMA_REVISION
from tools.tests.physical_gate_support import candidate_fixture


class GrayAppearanceOuterContractTests(unittest.TestCase):
    def _groups(self, gray: np.ndarray):
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        return {
            group.source.value: group.paths
            for group in boundary_path_groups(
                gray,
                statistics,
                BoundaryPathParameters(),
            )
        }

    def test_gray_appearance_is_the_only_canonical_pixel_observation(self) -> None:
        import x5crop.domain as domain

        self.assertTrue(hasattr(domain, "GrayAppearanceObservation"))
        self.assertFalse(hasattr(domain, "GrayMaterialObservation"))
        boundary_fields = get_type_hints(domain.BoundaryPathObservation)
        separator_fields = get_type_hints(domain.SeparatorBandObservation)
        self.assertEqual(
            boundary_fields["outer_appearance"],
            domain.GrayAppearanceObservation | None,
        )
        self.assertEqual(
            boundary_fields["inner_appearance"],
            domain.GrayAppearanceObservation | None,
        )
        self.assertIs(
            separator_fields["appearance"],
            domain.GrayAppearanceObservation,
        )

    def test_candidate_evidence_owns_separator_sequence_without_material_identity(self) -> None:
        from x5crop.detection.candidate.model import CandidateEvidence

        names = {field.name for field in fields(CandidateEvidence)}
        self.assertIn("separator_sequence", names)
        self.assertIn("holder_boundary", names)
        self.assertNotIn("film_structure", names)
        self.assertNotIn("aperture_contact", names)

    def test_separator_sequence_is_the_physical_boundary_proof(self) -> None:
        self.assertIn("separator_sequence_led", BOUNDARY_PROOF_PATH_CODES)
        self.assertNotIn("film_structure_led", BOUNDARY_PROOF_PATH_CODES)

    def test_separator_sequence_carries_no_gray_identity(self) -> None:
        names = {field.name for field in fields(SeparatorSequenceEvidence)}
        self.assertEqual(
            names,
            {
                "expected_count",
                "hard_count",
                "dimension_constrained_count",
                "hard_boundaries",
                "missing_boundaries",
                "hard_tonal_evidence",
                "state",
                "reason",
            },
        )
        evidence = SeparatorSequenceEvidence(
            1,
            1,
            0,
            (FrameBoundaryReference(None, 1),),
            (),
            (0.0,),
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_separator_tonal_strength_cannot_change_gate_authority(self) -> None:
        candidate = candidate_fixture()
        built = BuiltCandidate(
            candidate.geometry,
            candidate.count_hypothesis,
            (),
        )
        evidence = candidate.assessment.evidence
        gates = tuple(
            candidate_gate_for_evidence(
                built,
                replace(
                    evidence,
                    separator_sequence=replace(
                        evidence.separator_sequence,
                        hard_tonal_evidence=(tonal_evidence,),
                    ),
                ),
            )
            for tonal_evidence in (0.0, 0.5, 1.0)
        )
        self.assertEqual(gates[0], gates[1])
        self.assertEqual(gates[1], gates[2])

    def test_active_runtime_has_no_film_base_identity(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop"
        banned = (
            "FilmBaseReference",
            "FilmBaseReferenceSource",
            "FilmBaseMaterialObservation",
            "film_base_reference",
            "film_base_material_consensus",
            "FilmStructureEvidence",
            "film_structure_evidence",
            "holder_to_film_base",
            "HOLDER_TO_FILM_BASE",
            "ApertureContactEvidence",
            "HolderMaterialEvidence",
            "holder_material",
            "GrayMaterialObservation",
            "outer_material",
            "inner_material",
            "gray_material_sequence_resolution",
        )
        offenders = {
            word: tuple(
                path.relative_to(root.parent).as_posix()
                for path in root.rglob("*.py")
                if word in path.read_text(encoding="utf-8")
            )
            for word in banned
        }
        self.assertEqual(offenders, {word: () for word in banned})

    def test_holder_boundary_has_no_fixed_gray_polarity(self) -> None:
        self.assertNotIn("WHITE_HOLDER_TRANSITION", BoundaryKind.__members__)
        self.assertIn("HOLDER_BOUNDARY_TRANSITION", BoundaryKind.__members__)

    def test_light_and_dark_holder_edges_share_one_observation_family(self) -> None:
        for holder, image in ((250, 100), (5, 150)):
            with self.subTest(holder=holder, image=image):
                gray = np.full((120, 240), holder, dtype=np.uint8)
                gray[20:100, 40:200] = image
                observations = self._groups(gray)["holder_boundary"]
                self.assertEqual(
                    {observation.side.value for observation in observations},
                    {"leading", "trailing", "top", "bottom"},
                )

    def test_gray_appearance_carries_no_color_or_identity_semantics(self) -> None:
        import x5crop.domain as domain

        names = {field.name for field in fields(domain.GrayAppearanceObservation)}
        self.assertFalse(
            names
            & {
                "color",
                "chroma",
                "hue",
                "material",
                "film_base",
                "holder",
                "side",
                "edge_adjacent",
            }
        )

    def test_detection_runtime_has_no_color_or_perforation_model(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop"
        allowed = {
            "x5crop/image/gray.py",
            "x5crop/io/model.py",
            "x5crop/io/tiff.py",
            "x5crop/debug/analysis.py",
        }
        offenders: list[str] = []
        banned = ("chroma", "hue", "perforation", "sprocket")
        for path in root.rglob("*.py"):
            relative = path.relative_to(root.parent).as_posix()
            if relative in allowed:
                continue
            source = path.read_text(encoding="utf-8").lower()
            if any(word in source for word in banned):
                offenders.append(relative)
        self.assertEqual(offenders, [])

    def test_current_schema_names_gray_sequence_resolution(self) -> None:
        self.assertEqual(REPORT_SCHEMA_REVISION, "gray_sequence_resolution")

    def test_boundary_path_groups_have_one_typed_canonical_model(self) -> None:
        import x5crop.domain as domain

        self.assertTrue(is_dataclass(domain.BoundaryPathGroup))
        self.assertTrue(issubclass(domain.BoundaryPathSource, str))
        annotations = get_type_hints(domain.BoundaryPathGroup)
        self.assertIs(annotations["source"], domain.BoundaryPathSource)

    def test_holder_boundary_measurement_has_one_owner(self) -> None:
        root = Path(__file__).resolve().parents[2]
        evidence_source = (
            root / "x5crop/detection/evidence/holder_boundary.py"
        ).read_text(encoding="utf-8")
        self.assertIn("boundary_supports_holder_region", evidence_source)
        self.assertNotIn("film_base", evidence_source)


if __name__ == "__main__":
    unittest.main()
