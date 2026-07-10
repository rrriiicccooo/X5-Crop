from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from x5crop.policies.parameters.aggregate import FormatParameters


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ArchitectureResidualContractTest(unittest.TestCase):
    def test_format_parameters_expose_only_fixed_parameter_groups(self) -> None:
        field_names = [field.name for field in fields(FormatParameters)]
        self.assertEqual(
            field_names,
            [
                "preprocess",
                "content",
                "outer",
                "separator",
                "candidate",
                "decision",
                "output",
                "diagnostics",
            ],
        )
        old_flat_fields = (
            "content_profile",
            "outer_strategy",
            "separator_support",
            "partial_counts",
            "decision_review",
            "output_overlap",
            "deskew",
        )
        for field_name in old_flat_fields:
            self.assertNotIn(field_name, field_names)

    def test_policy_assembly_does_not_use_reported_physical_note_strings(self) -> None:
        banned = (
            "known_physical_notes",
            "_has_physical_risk",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_policy_assembly_receives_resolved_format_specs(self) -> None:
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in ("FORMATS[", "preset.format_id"):
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_frame_geometry_classification_has_one_physical_owner(self) -> None:
        from x5crop.formats import FORMATS

        self.assertFalse((PROJECT_ROOT / "x5crop" / "formats" / "traits.py").exists())
        expected = {
            "135": "standard_35mm",
            "135-dual": "dual_lane",
            "half": "dense_half",
            "xpan": "panoramic_35mm",
            "120-645": "medium_rectangle",
            "120-66": "medium_square",
            "120-67": "medium_wide",
        }
        self.assertEqual(
            {
                format_id: spec.frame_geometry_profile
                for format_id, spec in FORMATS.items()
            },
            expected,
        )

        duplicate_classifiers = (
            "_is_standard_35mm_strip",
            "_is_dense_half_frame",
            "_is_panorama_35mm",
            "_is_panorama_frame",
            "_is_panorama_strip",
            "_is_medium_rectangle",
            "_is_medium_square",
            "_is_medium_square_strip",
            "_is_square_medium_frame",
            "_is_medium_wide",
            "_is_medium_wide_strip",
            "_is_landscape_medium_frame",
            "_is_dense_geometry_supported_strip",
        )
        offenders: list[str] = []
        for root in (
            PROJECT_ROOT / "x5crop" / "policies",
            PROJECT_ROOT / "x5crop" / "formats",
        ):
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for name in duplicate_classifiers:
                    if f"def {name}" in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{name}")
        self.assertEqual(offenders, [])

    def test_format_policy_modules_expose_only_unified_build_entry(self) -> None:
        banned = (
            "def full_policy",
            "def partial_policy",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "policies" / "formats"
        self.assertTrue(source_root.is_dir())
        for path in source_root.glob("format_*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_destructive_cleanup_removes_legacy_policy_and_import_hooks(self) -> None:
        banned = (
            "source_parameters",
            "import_format_module",
            "format_module_name",
            "RuntimePolicyContext",
            "policy_context.py",
            "PARAMETER_FACTORIES",
            "FORMAT_OVERRIDE_PARAMETER_PATHS",
            "split_format_parameter_overrides",
            "source orchestration",
            "FormatParameterViews",
            "parameters.views",
            "decision_contract_for(",
            "default_content_evidence_image_parameters",
            "default_separator_evidence_image_parameters",
            "default_deskew_fallback_evidence_parameters",
            "export.paths",
            "robust_grid",
            "RobustGrid",
            "ROBUST_GRID",
            "candidate_gate_passed",
            "partial_safe_extra_frames",
            "safe_extra_frames",
            "EVIDENCE_POLICY_OVERRIDES",
            "EVIDENCE_POLICY_MODE_OVERRIDES",
            "evidence_policy_values",
            "unacceptable_wrong_pass",
            "risky_regression",
        )
        offenders: list[str] = []
        for root in (PROJECT_ROOT / "x5crop",):
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                if path == Path(__file__).resolve():
                    continue
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_format_preset_assembly_does_not_own_profiles_or_descriptions(self) -> None:
        text = (
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "format_presets.py"
        ).read_text(encoding="utf-8")
        banned = (
            "FrameFitPolicy(",
            "SeparatorEdgePairPolicy(",
            "safe extra",
            "def _notes",
            "def _role",
        )
        offenders = [term for term in banned if term in text]
        self.assertEqual(offenders, [])

    def test_approved_geometry_adjustment_is_output_adjacent(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "final" / "geometry.py").exists()
        )
        self.assertTrue(
            (PROJECT_ROOT / "x5crop" / "output" / "geometry_adjustment.py").is_file()
        )

    def test_workflow_does_not_create_output_directory_before_io(self) -> None:
        text = (PROJECT_ROOT / "x5crop" / "runtime" / "workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("output_dir.mkdir", text)
        self.assertIn("output_surface_for_input", text)

    def test_regression_tools_use_current_final_reason_field(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "tools" / "regression").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"review_reasons"' in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_regression_tools_are_diff_auditors_not_parity_gates(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "tools" / "regression" / "historical_compare.py").exists()
        )
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "tools" / "regression").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "fail-on-diff" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_crop_and_decision_thresholds_have_explicit_policy_owners(self) -> None:
        from x5crop.policies.runtime.candidate import BaseDetectionScorePolicy, ScoringPolicy
        from x5crop.policies.runtime.content import ContentProfilePolicy
        from x5crop.policies.runtime.content import ContentPolicy
        from x5crop.policies.runtime.decision import RuntimeDecisionPolicy
        from x5crop.policies.runtime.outer import (
            EdgeAnchoredContentPositionPolicy,
            FloatingContentPositionPolicy,
            LongAxisGeometryCorrectionPolicy,
            SeparatorOuterBandPolicy,
        )
        from x5crop.geometry.detection_parameters import (
            EdgePairParameters,
            NearbySeparatorRefinementParameters,
            SeparatorWidthProfileSearchParameters,
        )

        required_fields = {
            ScoringPolicy: {
                "dual_lane_below_threshold_cap",
                "dual_lane_frame_count_mismatch_cap",
            },
            RuntimeDecisionPolicy: {"outer_candidate_disagreement_min_spread_ratio"},
            FloatingContentPositionPolicy: {
                "content_bbox_min_fraction",
                "min_short_axis_px",
                "min_short_axis_ratio",
                "min_width_px",
            },
            EdgeAnchoredContentPositionPolicy: {
                "content_bbox_min_fraction",
                "min_short_axis_px",
                "min_short_axis_ratio",
                "min_width_px",
            },
            LongAxisGeometryCorrectionPolicy: {
                "min_corrected_width_ratio",
                "min_corrected_width_px",
            },
            ContentProfilePolicy: {
                "percentiles",
                "smooth_min_px",
                "min_run_width_px",
            },
            ContentPolicy: {"support_missing_aspect_score"},
            BaseDetectionScorePolicy: {
                "image_quality_percentiles",
                "hard_support_floor_min_expected_gaps",
                "hard_gap_floor_min_count",
                "model_gap_overuse_min_count",
                "partial_ambiguous_count_max",
                "partial_dense_strip_min_default_count",
            },
            SeparatorOuterBandPolicy: {
                "band_to_peak_ratio",
                "pair_candidate_expansion",
            },
            NearbySeparatorRefinementParameters: {
                "candidate_threshold_percentile",
                "candidate_threshold_floor",
            },
            SeparatorWidthProfileSearchParameters: {
                "normalization_percentiles",
            },
            EdgePairParameters: {
                "candidate_peak_percentile",
                "candidate_peak_min_distance_px",
            },
        }
        for policy_type, fields in required_fields.items():
            self.assertTrue(fields.issubset(policy_type.__dataclass_fields__))

    def test_foundation_normalization_helpers_require_explicit_percentiles(self) -> None:
        from x5crop.geometry.edge_refine_profile import normalize_profile
        from x5crop.image.evidence import normalize_score_image

        self.assertIsNone(normalize_profile.__defaults__)
        self.assertIsNone(normalize_score_image.__defaults__)

    def test_active_interfaces_do_not_discard_unused_parameters(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.lstrip().startswith("del "):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}")
        self.assertEqual(offenders, [])

    def test_leading_grid_tail_boundary_is_derived_from_policy(self) -> None:
        source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "assessment"
            / "separator_support.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("min(hard_indexes) >= 4", source)
        self.assertIn("policy.leading_count + 1", source)

    def test_foundation_helpers_require_explicit_parameters(self) -> None:
        banned = (
            "params=None",
            "params: None",
            "config=None",
            "config: None",
            "policy=None",
            "policy: None",
        )
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "geometry",
            PROJECT_ROOT / "x5crop" / "cache",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
        )
        offenders: list[str] = []
        for root in checked_roots:
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

        frame_fit_source = (
            PROJECT_ROOT / "x5crop" / "geometry" / "frame_fit.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("geometry_config", frame_fit_source)
        self.assertNotIn("frame_fit: FrameFitParameters | None = None", frame_fit_source)

    def test_foundation_physical_evidence_and_guidance_do_not_accept_full_detection_policy(self) -> None:
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "geometry",
            PROJECT_ROOT / "x5crop" / "image",
            PROJECT_ROOT / "x5crop" / "io",
            PROJECT_ROOT / "x5crop" / "cache",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
        )
        offenders: list[str] = []
        for root in checked_roots:
            self.assertTrue(root.is_dir())
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if "DetectionPolicy" in text:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
