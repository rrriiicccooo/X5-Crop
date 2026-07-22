from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import get_type_hints
import unittest

import numpy as np

from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.candidate.assessment.model import (
    SEQUENCE_PROOF_PATH_CODES,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.detection.evidence.separator_sequence import SeparatorSequenceEvidence
from x5crop.detection.physical.boundary_detection import (
    _adaptive_change_points,
    _cross_section_profiles,
    _texture_image,
    boundary_measurements,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryMeasurementSet,
    EvidenceState,
    InterFrameBoundaryReference,
)
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.report.identity import REPORT_SCHEMA_REVISION
from tools.tests.physical_gate_support import candidate_fixture


class GrayAppearanceOuterContractTests(unittest.TestCase):
    def test_boundary_measurement_has_no_downstream_path_budget(self) -> None:
        parameter_fields = {item.name for item in fields(BoundaryPathParameters)}
        measurement_fields = {item.name for item in fields(BoundaryMeasurementSet)}

        self.assertNotIn("maximum_paths_per_axis", parameter_fields)
        self.assertNotIn("completeness", measurement_fields)

    def _measurements(self, gray: np.ndarray):
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        return boundary_measurements(
            gray,
            statistics,
            BoundaryPathParameters(),
            axes=(BoundaryAxis.LONG, BoundaryAxis.SHORT),
            transform_position_uncertainty_px=0.0,
        )

    def test_gray_appearance_is_the_only_canonical_pixel_observation(self) -> None:
        import x5crop.domain as domain

        self.assertTrue(hasattr(domain, "GrayAppearanceObservation"))
        self.assertFalse(hasattr(domain, "GrayMaterialObservation"))
        boundary_fields = get_type_hints(domain.GrayBoundaryPathObservation)
        separator_fields = get_type_hints(domain.SeparatorBandObservation)
        self.assertIs(boundary_fields["lower_appearance"], domain.GrayAppearanceObservation)
        self.assertIs(boundary_fields["upper_appearance"], domain.GrayAppearanceObservation)
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

    def test_separator_sequence_is_the_physical_sequence_proof(self) -> None:
        self.assertIn("separator_sequence_led", SEQUENCE_PROOF_PATH_CODES)
        self.assertNotIn("film_structure_led", SEQUENCE_PROOF_PATH_CODES)

    def test_separator_sequence_carries_no_gray_identity(self) -> None:
        names = {field.name for field in fields(SeparatorSequenceEvidence)}
        self.assertEqual(
            names,
            {
                "expected_count",
                "hard_count",
                "provisional_boundary_count",
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
            (InterFrameBoundaryReference(None, 1),),
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
        self.assertEqual(
            set(BoundaryKind.__members__),
            {
                "EDGE_ADJACENT_TRANSITION",
                "TONAL_TRANSITION",
                "TEXTURE_TRANSITION",
            },
        )

    def test_light_and_dark_holder_edges_share_one_observation_family(self) -> None:
        for holder, image in ((250, 100), (5, 150)):
            with self.subTest(holder=holder, image=image):
                gray = np.full((120, 240), holder, dtype=np.uint8)
                gray[20:100, 40:200] = image
                observations = self._measurements(gray).holder_boundaries
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

    def test_current_schema_names_frame_slot_resolution(self) -> None:
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "detection_owned_shared_short_axis",
        )

    def test_boundary_measurements_have_one_typed_canonical_model(self) -> None:
        import x5crop.domain as domain

        self.assertTrue(is_dataclass(domain.BoundaryMeasurementSet))
        annotations = get_type_hints(domain.BoundaryMeasurementSet)
        self.assertEqual(
            annotations["raw_paths"],
            tuple[domain.GrayBoundaryPathObservation, ...],
        )
        self.assertEqual(
            annotations["holder_boundaries"],
            tuple[domain.HolderBoundaryObservation, ...],
        )

    def test_holder_boundary_measurement_has_one_owner(self) -> None:
        root = Path(__file__).resolve().parents[2]
        evidence_source = (
            root / "x5crop/detection/evidence/holder_boundary.py"
        ).read_text(encoding="utf-8")
        self.assertIn("boundary_supports_holder_region", evidence_source)
        self.assertNotIn("film_base", evidence_source)

    def test_local_change_point_selection_is_not_an_execution_budget(self) -> None:
        points = _adaptive_change_points(
            np.asarray(([0.0] * 5 + [1.0] * 5) * 20, dtype=np.float32),
            replace(
                BoundaryPathParameters(),
                maximum_change_points_per_section=1,
            ),
        )

        self.assertEqual(len(points), 1)

    def test_moderate_frame_edge_survives_stronger_content_changes(self) -> None:
        signal = np.zeros(110, dtype=np.float32)
        for index in range(24):
            signal[2 + 3 * index] = 100.0
        for index in range(10):
            signal[74 + 3 * index] = 50.0

        points = _adaptive_change_points(
            signal,
            replace(
                BoundaryPathParameters(),
                change_point_percentile=45.0,
            ),
        )

        self.assertTrue(
            any(point.minimum <= 74.0 < point.maximum for point in points)
        )

    def test_change_point_selection_preserves_spatial_coverage(self) -> None:
        signal = np.zeros(1000, dtype=np.float32)
        for position in range(20, 960, 20):
            signal[position] = 100.0
        for position in (20, 40, 60, 80):
            signal[position] = 200.0
        signal[900] = 190.0

        points = _adaptive_change_points(
            signal,
            replace(
                BoundaryPathParameters(),
                change_point_percentile=99.0,
                maximum_change_points_per_section=4,
            ),
        )

        self.assertTrue(
            any(point.minimum <= 900.0 < point.maximum for point in points),
            points,
        )

    def test_sparse_transition_is_not_discarded_by_zero_change_mass(self) -> None:
        signal = np.zeros(1_000, dtype=np.float32)
        signal[800:] = 100.0

        points = _adaptive_change_points(
            signal,
            BoundaryPathParameters(),
        )

        self.assertTrue(
            any(point.minimum <= 800.0 < point.maximum for point in points),
            points,
        )

    def test_short_axis_paths_sample_the_full_long_axis_at_local_density(self) -> None:
        gray = np.zeros((100, 1_000), dtype=np.uint8)
        profiles = _cross_section_profiles(
            gray,
            _texture_image(gray),
            scan_axis=0,
            parameters=BoundaryPathParameters(),
        )

        self.assertEqual(profiles[0].orthogonal_interval.minimum, 0.0)
        self.assertEqual(profiles[-1].orthogonal_interval.maximum, 1_000.0)
        self.assertGreater(len(profiles), 5)

    def test_one_sloped_rectangle_edge_has_one_canonical_path_per_side(self) -> None:
        height, width = 120, 1_000
        gray = np.full((height, width), 255, dtype=np.uint8)
        for x in range(20, width - 20):
            top = 10 + x // 100
            bottom = 90 + x // 100
            gray[top:bottom, x] = 100

        measurements = self._measurements(gray)
        edge_paths = tuple(
            path
            for path in measurements.raw_paths
            if path.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
        )

        self.assertEqual(len(edge_paths), 4)

    def test_count_independent_measurement_keeps_supported_paths(self) -> None:
        gray = np.tile(
            np.asarray(([0] * 5 + [255] * 5) * 20, dtype=np.uint8),
            (120, 1),
        )
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        measurements = boundary_measurements(
            gray,
            statistics,
            replace(
                BoundaryPathParameters(),
                maximum_change_points_per_section=64,
            ),
            axes=(BoundaryAxis.LONG, BoundaryAxis.SHORT),
            transform_position_uncertainty_px=0.0,
        )

        long_axis_generic = tuple(
            path
            for path in measurements.raw_paths
            if path.axis == BoundaryAxis.LONG
            and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
        )
        self.assertGreater(len(long_axis_generic), 1)


if __name__ == "__main__":
    unittest.main()
