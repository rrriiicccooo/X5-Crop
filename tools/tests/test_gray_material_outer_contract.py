from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import get_type_hints

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.physical.boundary_detection import boundary_path_groups
from x5crop.domain import BoundaryKind
from x5crop.detection.candidate.assessment.candidate_gate import (
    BOUNDARY_PROOF_PATH_CODES,
)
from x5crop.detection.evidence.film_structure import (
    ApertureContactOutcome,
    ApertureContactSideEvidence,
    aperture_contact_outcome,
)
from x5crop.domain import BoundarySide, EvidenceState
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.report.identity import REPORT_SCHEMA_REVISION


class GrayMaterialOuterContractTests(unittest.TestCase):
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

    def test_holder_identity_is_gray_material_not_white_polarity(self) -> None:
        self.assertNotIn("WHITE_HOLDER_TRANSITION", BoundaryKind.__members__)
        self.assertTrue(hasattr(BoundaryKind, "HOLDER_MATERIAL_TRANSITION"))

    def test_light_and_dark_holder_edges_share_one_observation_family(self) -> None:
        for holder, image in ((250, 100), (5, 150)):
            with self.subTest(holder=holder, image=image):
                gray = np.full((120, 240), holder, dtype=np.uint8)
                gray[20:100, 40:200] = image
                observations = self._groups(gray)["holder_material"]
                self.assertEqual(
                    {observation.side for observation in observations},
                    {"leading", "trailing", "top", "bottom"},
                )

    def test_gray_material_observations_do_not_carry_color_semantics(self) -> None:
        import x5crop.domain as domain

        observation = getattr(domain, "GrayMaterialObservation")
        names = {field.name for field in fields(observation)}
        self.assertFalse(names & {"color", "chroma", "hue", "side", "edge_adjacent"})

    def test_gray_material_tail_is_typed_not_a_boolean_claim(self) -> None:
        import x5crop.domain as domain

        self.assertTrue(hasattr(domain, "GrayIntensityTail"))
        names = {field.name for field in fields(domain.GrayMaterialObservation)}
        self.assertIn("intensity_tail", names)
        self.assertNotIn("tail_supported", names)

    def test_boundary_and_separator_share_one_gray_material_type(self) -> None:
        import x5crop.domain as domain

        boundary_fields = get_type_hints(domain.BoundaryPathObservation)
        separator_fields = get_type_hints(domain.SeparatorBandObservation)
        self.assertEqual(
            boundary_fields["outer_material"],
            domain.GrayMaterialObservation | None,
        )
        self.assertEqual(
            boundary_fields["inner_material"],
            domain.GrayMaterialObservation | None,
        )
        self.assertEqual(
            separator_fields["material"],
            domain.GrayMaterialObservation,
        )
        self.assertNotIn("holder_material", boundary_fields)

    def test_boundary_proof_uses_film_structure_identity(self) -> None:
        self.assertIn("film_structure_led", BOUNDARY_PROOF_PATH_CODES)
        self.assertNotIn("separator_led", BOUNDARY_PROOF_PATH_CODES)

    def test_film_structure_proof_names_only_its_owned_evidence(self) -> None:
        from tools.tests.physical_gate_support import candidate_fixture

        candidate = candidate_fixture()
        gate = candidate.assessment.gate
        self.assertIsNotNone(gate)
        path = next(
            item for item in gate.proof_paths if item.code == "film_structure_led"
        )
        self.assertEqual(
            path.supporting_evidence,
            (
                "complete_hard_separator_sequence",
                "cross_axis_separator_pixel_paths",
                "film_base_material_consensus",
            ),
        )

    def test_film_structure_is_owned_by_evidence_not_candidate_assessment(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertTrue(
            (root / "x5crop/detection/evidence/film_structure.py").is_file()
        )
        self.assertFalse(
            (
                root
                / "x5crop/detection/candidate/assessment/film_structure.py"
            ).exists()
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

    def test_current_schema_names_the_gray_material_model(self) -> None:
        self.assertEqual(REPORT_SCHEMA_REVISION, "gray_material_sequence_resolution")

    def test_missing_boundary_path_is_unavailable_aperture_contact(self) -> None:
        evidence = ApertureContactSideEvidence(
            BoundarySide.LEADING,
            ApertureContactOutcome.UNRESOLVED,
            None,
        )
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)

    def test_low_texture_tail_without_material_consensus_is_not_film_base(self) -> None:
        from tools.tests.physical_gate_support import boundary_path_fixture
        from x5crop.domain import MeasurementIdentity, MeasurementProvenance, PixelInterval

        provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
            "single_tail_region",
            (MeasurementIdentity.GRAY_WORK,),
        )
        path = boundary_path_fixture(
            BoundarySide.TOP,
            PixelInterval.exact(20.0),
            BoundaryKind.HOLDER_MATERIAL_TRANSITION,
            provenance,
        )

        self.assertEqual(
            aperture_contact_outcome(path, 1.0),
            ApertureContactOutcome.UNRESOLVED,
        )

    def test_high_texture_inner_material_cannot_be_a_film_base_track(self) -> None:
        from dataclasses import replace

        from tools.tests.physical_gate_support import candidate_fixture
        from x5crop.detection.evidence.film_structure import film_base_reference
        from x5crop.detection.evidence.holder_material import HolderMaterialEvidence

        candidate = candidate_fixture()
        paths = tuple(
            replace(
                path,
                inner_material=replace(path.inner_material, texture_median=2.0),
            )
            for path in candidate.geometry.boundary_paths
            if path.side in {BoundarySide.TOP, BoundarySide.BOTTOM}
            and path.inner_material is not None
        )
        reference = film_base_reference(
            candidate.geometry,
            HolderMaterialEvidence(paths),
            edge_texture_limit=1.0,
        )

        self.assertEqual(reference.state, EvidenceState.UNAVAILABLE)

    def test_film_base_consensus_requires_distinct_typed_locations(self) -> None:
        from tools.tests.physical_gate_support import boundary_path_fixture
        from x5crop.detection.evidence.film_structure import (
            FilmBaseMaterialObservation,
            FilmBaseReference,
            FilmBaseReferenceSource,
        )
        from x5crop.domain import (
            GrayIntensityTail,
            MeasurementIdentity,
            MeasurementProvenance,
            PixelInterval,
        )

        provenance = MeasurementProvenance(
            MeasurementIdentity.HOLDER_MATERIAL_PROFILE,
            "track_material",
            (MeasurementIdentity.GRAY_WORK,),
        )
        path = boundary_path_fixture(
            BoundarySide.TOP,
            PixelInterval.exact(20.0),
            BoundaryKind.HOLDER_MATERIAL_TRANSITION,
            provenance,
        )
        sample = FilmBaseMaterialObservation(
            BoundarySide.TOP,
            path.inner_material,
        )

        with self.assertRaises(ValueError):
            FilmBaseReference(
                FilmBaseReferenceSource.VISIBLE_FILM_BASE_TRACKS,
                GrayIntensityTail.LOW,
                (sample, sample),
                1.0,
            )

    def test_film_base_reference_enforces_source_location_and_cardinality(self) -> None:
        from tools.tests.physical_gate_support import separator_observation
        from x5crop.detection.evidence.film_structure import (
            FilmBaseMaterialObservation,
            FilmBaseReference,
            FilmBaseReferenceSource,
        )
        from x5crop.domain import (
            FrameBoundaryReference,
            GrayIntensityTail,
        )

        separator_material = separator_observation(100.0).material
        internal = FilmBaseMaterialObservation(
            FrameBoundaryReference(None, 1),
            separator_material,
        )
        with self.assertRaises(ValueError):
            FilmBaseReference(
                FilmBaseReferenceSource.VISIBLE_FILM_BASE_TRACKS,
                GrayIntensityTail.LOW,
                (internal,),
                1.0,
            )
        with self.assertRaises(ValueError):
            FilmBaseReference(
                FilmBaseReferenceSource.INTERNAL_SEPARATOR_CONSENSUS,
                GrayIntensityTail.LOW,
                (internal,),
                1.0,
            )

    def test_film_base_reference_enforces_adaptive_texture_limit(self) -> None:
        from dataclasses import replace

        from tools.tests.physical_gate_support import separator_observation
        from x5crop.detection.evidence.film_structure import (
            FilmBaseMaterialObservation,
            FilmBaseReference,
            FilmBaseReferenceSource,
        )
        from x5crop.domain import FrameBoundaryReference, GrayIntensityTail

        material = replace(
            separator_observation(100.0).material,
            texture_median=2.0,
        )
        observations = tuple(
            FilmBaseMaterialObservation(
                FrameBoundaryReference(None, index),
                material,
            )
            for index in (1, 2)
        )

        self.assertIn("texture_limit", FilmBaseReference.__dataclass_fields__)

        with self.assertRaises(ValueError):
            FilmBaseReference(
                FilmBaseReferenceSource.INTERNAL_SEPARATOR_CONSENSUS,
                GrayIntensityTail.LOW,
                observations,
                texture_limit=1.0,
            )

    def test_high_texture_separators_cannot_establish_film_base_consensus(self) -> None:
        from dataclasses import replace
        from types import SimpleNamespace

        from tools.tests.physical_gate_support import (
            separator_constraints,
            separator_observation,
        )
        from x5crop.detection.evidence.film_structure import film_base_reference
        from x5crop.detection.evidence.holder_material import HolderMaterialEvidence
        from x5crop.detection.physical.separator.assignment import (
            assign_observation_to_boundary,
        )
        from x5crop.domain import PixelInterval

        assignments = []
        for index, center in enumerate((100.0, 200.0), start=1):
            observation = separator_observation(center)
            observation = replace(
                observation,
                material=replace(observation.material, texture_median=2.0),
            )
            assignment = assign_observation_to_boundary(
                index,
                observation,
                *separator_constraints(
                    index,
                    PixelInterval(center - 20.0, center + 20.0),
                ),
            )
            assignments.append(replace(assignment, used_for_boundary=True))

        reference = film_base_reference(
            SimpleNamespace(separator_assignments=tuple(assignments)),
            HolderMaterialEvidence(()),
            edge_texture_limit=1.0,
        )

        self.assertEqual(reference.state, EvidenceState.UNAVAILABLE)

    def test_boundary_path_groups_have_one_typed_canonical_model(self) -> None:
        import x5crop.domain as domain

        group_type = getattr(domain, "BoundaryPathGroup")
        source_type = getattr(domain, "BoundaryPathSource")
        self.assertTrue(is_dataclass(group_type))
        self.assertTrue(issubclass(source_type, str))
        annotations = get_type_hints(group_type)
        self.assertIs(annotations["source"], source_type)

    def test_deleted_boundary_observation_field_cannot_return(self) -> None:
        root = Path(__file__).resolve().parents[2] / "x5crop"
        offenders = [
            path.relative_to(root.parent).as_posix()
            for path in root.rglob("*.py")
            if "boundary_observations" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_holder_material_classification_has_one_owner(self) -> None:
        root = Path(__file__).resolve().parents[2]
        evidence_source = (
            root / "x5crop/detection/evidence/holder_material.py"
        ).read_text(encoding="utf-8")
        self.assertIn("boundary_supports_holder_material", evidence_source)
        self.assertNotIn("texture_median <=", evidence_source)


if __name__ == "__main__":
    unittest.main()
