from __future__ import annotations

from dataclasses import fields
import unittest

from tools.tests.support.architecture import (
    PROJECT_ROOT,
    duplicate_dataclass_models,
    duplicate_top_level_symbols,
)


class ArchitectureOwnershipContractTest(unittest.TestCase):
    def test_top_level_symbol_identity_is_unique_per_module(self) -> None:
        self.assertEqual(duplicate_top_level_symbols(), [])

    def test_image_statistics_expose_only_consumed_named_measurements(self) -> None:
        from x5crop.image.statistics import (
            ImageMeasurementStatistics,
            ImageMeasurementStatisticsParameters,
        )

        self.assertEqual(
            tuple(field.name for field in fields(ImageMeasurementStatistics)),
            (
                "intensity_low",
                "intensity_median",
                "intensity_high",
                "intensity_mad",
                "gradient_baseline",
                "gradient_signal",
                "gradient_mad",
                "texture_signal",
                "texture_mad",
                "edge_texture_limit",
            ),
        )
        parameter_fields = tuple(
            field.name for field in fields(ImageMeasurementStatisticsParameters)
        )
        self.assertNotIn("intensity_percentiles", parameter_fields)
        self.assertNotIn("noise_percentiles", parameter_fields)
        self.assertNotIn("edge_texture_percentiles", parameter_fields)

    def test_frame_topology_is_a_geometry_invariant_not_duplicate_evidence(self) -> None:
        from x5crop.detection.candidate.assessment.model import (
            CANDIDATE_GATE_CHECK_CODES,
        )
        from x5crop.detection.candidate.model import CandidateEvidence

        self.assertFalse(
            (PROJECT_ROOT / "x5crop/detection/evidence/frame_topology.py").exists()
        )
        self.assertNotIn("frame_topology", CandidateEvidence.__dataclass_fields__)
        self.assertNotIn("frame_topology_integrity", CANDIDATE_GATE_CHECK_CODES)

    def test_content_preservation_is_a_gate_projection_not_duplicate_evidence(self) -> None:
        from x5crop.detection.candidate.model import CandidateEvidence

        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop/detection/evidence/content/preservation.py"
            ).exists()
        )
        self.assertNotIn("content_preservation", CandidateEvidence.__dataclass_fields__)

    def test_sequence_conservation_is_a_geometry_invariant_not_duplicate_evidence(self) -> None:
        from x5crop.detection.candidate.assessment.model import (
            CANDIDATE_GATE_CHECK_CODES,
        )
        from x5crop.detection.candidate.model import CandidateEvidence

        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop/detection/evidence/aperture_sequence.py"
            ).exists()
        )
        self.assertNotIn("sequence_conservation", CandidateEvidence.__dataclass_fields__)
        self.assertNotIn("frame_sequence_conservation", CANDIDATE_GATE_CHECK_CODES)

    def test_automatic_processing_authority_is_not_physical_geometry(self) -> None:
        from x5crop.detection.candidate.assessment.evidence_independence import (
            EvidenceIndependenceEvidence,
        )
        from x5crop.detection.physical.model import (
            DualLaneFrameSolution,
            FrameSequenceSolution,
            ReviewOnlyContainment,
        )

        for model in (
            FrameSequenceSolution,
            DualLaneFrameSolution,
            ReviewOnlyContainment,
            EvidenceIndependenceEvidence,
        ):
            with self.subTest(model=model.__name__):
                self.assertNotIn(
                    "automatic_processing_supported",
                    model.__dataclass_fields__,
                )
        self.assertFalse(
            hasattr(DualLaneFrameSolution, "automatic_processing_supported")
        )

    def test_removed_architecture_surfaces_do_not_exist(self) -> None:
        removed = (
            "x5crop/gap_methods.py",
            "x5crop/debug/gaps.py",
            "x5crop/detection/evidence/count_planning.py",
            "x5crop/detection/evidence/exposure_overlap.py",
            "x5crop/detection/candidate/assessment/physical_evidence.py",
            "x5crop/detection/physical/outer",
            "x5crop/detection/candidate/extension",
            "x5crop/output/geometry_adjustment.py",
            "x5crop/output/protection.py",
            "x5crop/runtime/output_protection.py",
            "x5crop/configuration/profiles.py",
            "x5crop/configuration/assembly.py",
            "x5crop/constants.py",
        )
        self.assertEqual(
            [relative for relative in removed if (PROJECT_ROOT / relative).exists()],
            [],
        )

    def test_runtime_configuration_has_current_physical_groups_only(self) -> None:
        from x5crop.configuration.model import DetectionConfiguration

        self.assertEqual(
            tuple(DetectionConfiguration.__dataclass_fields__),
            (
                "physical_spec",
                "strip_mode",
                "preprocess",
                "scan_canvas",
                "photo_edges",
                "transform",
                "shared_short_axis",
                "boundary_path",
                "separator",
                "content",
                "candidate_plan",
                "diagnostics",
            ),
        )
        self.assertIsInstance(DetectionConfiguration.detector_kind, property)

    def test_candidate_plan_contains_budget_parameters_not_source_labels(self) -> None:
        from x5crop.configuration.candidate import CandidatePlanParameters

        self.assertEqual(
            tuple(CandidatePlanParameters.__dataclass_fields__),
            ("sequence_solver", "dual_lane_divider"),
        )

    def test_configuration_identity_is_derived_from_format_and_mode(self) -> None:
        from x5crop.configuration.model import DetectionConfiguration

        self.assertNotIn(
            "configuration_id",
            DetectionConfiguration.__dataclass_fields__,
        )
        self.assertIsInstance(
            DetectionConfiguration.configuration_id,
            property,
        )

    def test_legacy_policy_topology_is_absent(self) -> None:
        self.assertFalse((PROJECT_ROOT / "x5crop/policies").exists())

    def test_configuration_does_not_duplicate_foundation_models(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.image.separator_profile",
                "x5crop.configuration",
            ),
            [],
        )

    def test_evidence_cache_keys_include_parameters_and_exact_geometry(self) -> None:
        from x5crop.cache import (
            MeasurementRegionKey,
            ThresholdedMeasurementRegionKey,
        )
        from x5crop.domain import Box

        self.assertEqual(
            tuple(field.name for field in fields(MeasurementRegionKey)),
            ("parameters", "region"),
        )
        self.assertEqual(
            tuple(
                field.name for field in fields(ThresholdedMeasurementRegionKey)
            ),
            ("parameters", "region", "threshold"),
        )
        with self.assertRaises(TypeError):
            MeasurementRegionKey(("not", "parameters"), Box(0, 0, 1, 1))

    def test_configuration_registry_is_the_only_builder(self) -> None:
        root = PROJECT_ROOT / "x5crop/configuration"
        self.assertTrue((root / "registry.py").is_file())
        for obsolete in ("profiles.py", "assembly.py", "aggregate.py"):
            self.assertFalse((root / obsolete).exists())

    def test_physical_aggregation_has_one_canonical_owner(self) -> None:
        dual_lane = (
            PROJECT_ROOT / "x5crop/detection/candidate/composition/dual_lane.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("def _width_cv", dual_lane)
        self.assertNotIn("width_coefficient_of_variation", dual_lane)

    def test_regression_tools_are_current_schema_diff_auditors(self) -> None:
        source = (
            PROJECT_ROOT / "tools/regression/compare.py"
        ).read_text(encoding="utf-8")
        self.assertIn("final_review_reasons", source)
        for forbidden in ("parity_gate", "golden_oracle", "reference_classify"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
