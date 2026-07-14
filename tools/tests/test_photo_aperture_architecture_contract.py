from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import re
import unittest

from tools.tests.architecture_contracts import source_modules
from x5crop import domain
from x5crop.detection.candidate import model as candidate_model
from x5crop.detection.evidence.content import external_boundaries
from x5crop.detection.physical import model
from x5crop.output import model as output_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PhotoApertureArchitectureContractTest(unittest.TestCase):
    def test_canonical_photo_aperture_types_exist(self) -> None:
        expected_domain_types = {
            "GrayBoundaryPathObservation",
            "HolderBoundaryObservation",
            "PhotoApertureEdgeAssignment",
            "SeparatorBandAssignment",
            "PhotoApertureBoundaryResolution",
            "PhotoAperture",
            "InterPhotoSpacing",
            "FrameCropEnvelope",
            "ContainmentFallback",
        }
        expected_physical_types = {
            "PhotoSequenceSolution",
        }

        self.assertEqual(
            {
                name
                for name in expected_domain_types
                if not hasattr(domain, name)
            },
            set(),
        )
        self.assertEqual(
            {
                name
                for name in expected_physical_types
                if not hasattr(model, name)
            },
            set(),
        )

    def test_solution_stores_apertures_not_partition_frames(self) -> None:
        solution_fields = {
            field.name for field in fields(model.PhotoSequenceSolution)
        }

        self.assertIn("photo_apertures", solution_fields)
        self.assertIn("inter_photo_spacings", solution_fields)
        self.assertNotIn("frames", solution_fields)
        self.assertNotIn("visible_sequence_span", solution_fields)
        self.assertNotIn("crop_envelope", solution_fields)
        self.assertNotIn("frame_boundaries", solution_fields)

    def test_separator_band_midpoint_is_derived_from_its_endpoints(self) -> None:
        observation_fields = {
            field.name for field in fields(domain.SeparatorBandObservation)
        }

        self.assertNotIn("center", observation_fields)
        self.assertNotIn("midpoint", observation_fields)
        self.assertIsInstance(
            domain.SeparatorBandObservation.midpoint,
            property,
        )

    def test_architecture_keeps_cross_axis_support_candidate_specific(self) -> None:
        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "跨短轴测量只存在于 candidate-specific `SeparatorBandCrossAxisSupport`",
            architecture,
        )
        self.assertNotIn(
            "tonal measurement、cross-axis measurements 与 provenance",
            architecture,
        )

    def test_output_geometry_uses_per_photo_crop_envelopes(self) -> None:
        output_fields = {field.name for field in fields(output_model.OutputGeometry)}

        self.assertIn("frame_crop_envelopes", output_fields)
        self.assertNotIn("crop_envelope", output_fields)

    def test_content_preservation_has_one_local_boundary_model(self) -> None:
        evidence_fields = {
            field.name for field in fields(candidate_model.CandidateEvidence)
        }

        self.assertIn("photo_aperture_coverage", evidence_fields)
        self.assertIn("external_aperture_preservation", evidence_fields)
        self.assertNotIn("aperture_coverage", evidence_fields)
        self.assertNotIn("aperture_content_alignment", evidence_fields)
        self.assertTrue(
            hasattr(
                external_boundaries,
                "ExternalAperturePreservationEvidence",
            )
        )

    def test_superseded_geometry_types_are_absent_from_active_source(self) -> None:
        banned = {
            "VisibleSequenceSpan",
            "SequenceHypothesis",
            "SequenceSolution",
            "FrameBoundary",
            "DimensionConstrainedBoundary",
        }
        offenders: dict[str, list[str]] = {}
        for module_name, module in source_modules().items():
            source = module.path.read_text(encoding="utf-8")
            found = sorted(
                name
                for name in banned
                if re.search(rf"\b{re.escape(name)}\b", source)
            )
            if found:
                offenders[module_name] = found

        self.assertEqual(offenders, {})

    def test_sequence_envelope_coverage_vocabulary_is_absent(self) -> None:
        offenders: list[str] = []
        for module_name, module in source_modules().items():
            source = module.path.read_text(encoding="utf-8")
            if "photo sequence coverage" in source.lower():
                offenders.append(module_name)

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
