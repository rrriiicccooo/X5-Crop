from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
import unittest

from tools.tests.architecture_contracts import (
    duplicate_dataclass_models,
    translated_parameter_models,
)
from x5crop.policies.parameters.aggregate import FormatParameters


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ArchitectureResidualContractTest(unittest.TestCase):
    def test_inactive_safety_candidate_lifecycle_does_not_exist(self) -> None:
        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop"
                / "detection"
                / "candidate"
                / "assessment"
                / "safety.py"
            ).exists()
        )
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )
        self.assertNotIn("CANDIDATE_SOURCE_SAFETY", source)

    def test_hard_safety_has_one_named_source_and_no_shadow_gate_flag(self) -> None:
        proposal = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "proposal"
        self.assertFalse((proposal / "safety.py").exists())
        source = (proposal / "hard_safety.py").read_text(encoding="utf-8")
        self.assertNotIn("candidate_gate_eligible", source)

    def test_outer_execution_has_no_fake_supplemental_phase(self) -> None:
        from x5crop.policies.runtime.outer import SeparatorGeometryProposalPolicy

        self.assertNotIn(
            "width_profile_family",
            SeparatorGeometryProposalPolicy.__dataclass_fields__,
        )
        source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "source_candidates.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("include_supplemental_outer", source)

    def test_preprocess_constructor_is_inlined_in_central_factory(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "preprocess.py").exists()
        )

    def test_policy_assembly_has_no_single_use_constructor_modules(self) -> None:
        assembly = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
        obsolete = {
            "common.py",
            "content.py",
            "diagnostics.py",
            "finalization.py",
            "output.py",
        }

        self.assertEqual(
            sorted(path.name for path in assembly.glob("*.py") if path.name in obsolete),
            [],
        )

    def test_decision_contract_uses_canonical_parameter_objects(self) -> None:
        from x5crop.policies.decision import contract

        self.assertFalse(hasattr(contract, "DecisionPolicy"))
        self.assertFalse(hasattr(contract, "decision_policy_for"))
        self.assertIn(
            "candidate_selection",
            contract.DetectionDecisionContract.__dataclass_fields__,
        )

    def test_separator_model_gap_has_no_singleton_policy_selector(self) -> None:
        from x5crop.policies.runtime import separator

        self.assertFalse(hasattr(separator, "SeparatorModelGapProposalPolicy"))
        self.assertNotIn(
            "model_gap_proposal",
            separator.SeparatorPolicy.__dataclass_fields__,
        )

    def test_static_schema_and_gap_taxonomy_are_not_runtime_policy_fields(self) -> None:
        from x5crop.policies.runtime.policy import DetectionPolicy
        from x5crop.policies.runtime.separator import SeparatorPolicy

        self.assertNotIn("report", DetectionPolicy.__dataclass_fields__)
        self.assertNotIn("hard_methods", SeparatorPolicy.__dataclass_fields__)
        self.assertNotIn("model_methods", SeparatorPolicy.__dataclass_fields__)
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "policies" / "runtime" / "report.py").exists()
        )
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "report.py").exists()
        )

    def test_contract_test_modules_stay_below_single_responsibility_size_limit(self) -> None:
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in (PROJECT_ROOT / "tools" / "tests").glob("test_*_contract.py")
            if len(path.read_text(encoding="utf-8").splitlines()) > 800
        ]
        self.assertEqual(offenders, [])

    def test_policy_parameters_do_not_duplicate_foundation_parameter_models(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.geometry.detection_parameters",
                "x5crop.policies.parameters",
            ),
            [],
        )

    def test_runtime_policy_does_not_translate_parameter_models_by_suffix(self) -> None:
        self.assertEqual(translated_parameter_models(), [])

    def test_parameter_and_runtime_policy_layers_do_not_duplicate_models(self) -> None:
        self.assertEqual(
            duplicate_dataclass_models(
                "x5crop.policies.parameters",
                "x5crop.policies.runtime",
            ),
            [],
        )

    def test_report_read_models_are_not_named_as_schema_sections(self) -> None:
        self.assertFalse((PROJECT_ROOT / "x5crop" / "report" / "sections.py").exists())
        self.assertTrue((PROJECT_ROOT / "x5crop" / "report" / "read_models.py").exists())

    def test_partial_holder_has_one_runtime_eligibility_field(self) -> None:
        from x5crop.policies.parameters.candidate import PartialHolderParameters
        from x5crop.policies.runtime.candidate import PartialHolderPolicy

        for field_name in (
            "enabled",
            "leading_content_check",
            "frame_content_check",
        ):
            self.assertNotIn(field_name, PartialHolderParameters.__dataclass_fields__)
        self.assertIn("enabled", PartialHolderPolicy.__dataclass_fields__)
        for field_name in (
            "allow_empty_holder_frames",
            "checks_leading_content",
            "checks_frame_content",
        ):
            self.assertNotIn(field_name, PartialHolderPolicy.__dataclass_fields__)

    def test_regression_tools_have_no_historical_reference_classifier(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "tools" / "regression" / "reference_classify.py").exists()
        )

    def test_decision_policy_owns_thresholds_not_identity_reasons_or_descriptions(self) -> None:
        from x5crop.policies.decision import contract
        from x5crop.policies.parameters.decision import DecisionReviewParameters

        self.assertFalse(hasattr(contract, "ModePolicy"))
        self.assertIn(
            "strip_mode",
            contract.DetectionDecisionContract.__dataclass_fields__,
        )
        self.assertNotIn(
            "mode",
            contract.DetectionDecisionContract.__dataclass_fields__,
        )
        banned = {
            "policy_id",
            "suppress_close_competition_when_partial_edge_safe",
            "outer_candidate_disagreement_review_reason",
            "deskew_uncertain_review_reason",
            "separator_incomplete_reason",
            "geometry_unstable_reason",
            "outer_content_mismatch_reason",
            "candidate_competition_close_reason",
            "exposure_overlap_unresolved_reason",
            "content_only_evidence_reason",
            "content_evidence_insufficient_reason",
            "partial_edge_uncertain_reason",
            "decision_insufficient_reason",
        }
        self.assertTrue(banned.isdisjoint(DecisionReviewParameters.__dataclass_fields__))

    def test_candidate_plan_policy_contains_parameters_not_static_labels(self) -> None:
        from x5crop.policies.runtime import candidate
        from x5crop.policies.parameters import candidate as candidate_parameters
        from x5crop.policies.parameters.content import ContentCandidateParameters

        for class_name in (
            "SafetyCandidatePolicy",
            "PartialStopPolicy",
            "ContentCandidatePlanPolicy",
        ):
            self.assertFalse(hasattr(candidate, class_name))
        self.assertTrue(
            {
                "content_guided_separator",
                "separator_full_width_competition",
                "execution_budget",
                "evidence_independence",
            }.issuperset(candidate_parameters.CandidatePlanParameters.__dataclass_fields__)
        )
        banned_fields = {
            candidate_parameters.ContentGuidedSeparatorCandidateParameters: {
                "proposal_role",
                "guidance_source",
                "requires_hard_separator_signal",
            },
            candidate_parameters.SeparatorFullWidthCompetitionParameters: {
                "content_outer_max_median_aspect_strategies",
                "content_outer_max_median_aspect_strip_modes",
            },
            candidate_parameters.CandidateExecutionBudgetParameters: {"requires_content_support"},
            candidate_parameters.EvidenceIndependenceParameters: {
                "dependent_outer_strategies",
                "dependent_gap_sources",
                "require_content_support",
                "candidate_signal",
            },
        }
        for policy_type, fields in banned_fields.items():
            self.assertTrue(fields.isdisjoint(policy_type.__dataclass_fields__))
        self.assertTrue(
            {
                "candidate_contract",
                "proposal_role",
                "model_gap_evidence_kind",
            }.isdisjoint(ContentCandidateParameters.__dataclass_fields__)
        )

    def test_review_only_detector_is_derived_only_for_dual_lane_partial(self) -> None:
        from x5crop.policies.registry import get_detection_policy

        for format_id, strip_mode in (
            ("135", "full"),
            ("135", "partial"),
            ("135-dual", "full"),
        ):
            with self.subTest(format_id=format_id, strip_mode=strip_mode):
                self.assertNotEqual(
                    get_detection_policy(format_id, strip_mode).detector_kind,
                    "review_only",
                )
        self.assertEqual(
            get_detection_policy("135-dual", "partial").detector_kind,
            "review_only",
        )

    def test_separator_width_capability_has_no_format_preset_or_boolean_switch(self) -> None:
        from x5crop.policies.parameters.outer import SeparatorOuterBandParameters
        from x5crop.policies.runtime.outer import SeparatorGeometryProposalPolicy
        from x5crop.policies.runtime.separator import SeparatorWidthProfilePolicy

        self.assertNotIn(
            "separator_width_profile",
            SeparatorWidthProfilePolicy.__dataclass_fields__,
        )
        self.assertNotIn(
            "separator_outer_allow_oversized_band",
            SeparatorGeometryProposalPolicy.__dataclass_fields__,
        )
        self.assertIn(
            "oversized_band_max_short_axis_ratio",
            SeparatorOuterBandParameters.__dataclass_fields__,
        )

    def test_separator_geometry_support_has_no_static_runtime_switch(self) -> None:
        from x5crop.policies.runtime.separator import SeparatorPolicy

        self.assertNotIn(
            "separator_geometry_support_modes",
            SeparatorPolicy.__dataclass_fields__,
        )

    def test_review_only_mode_does_not_claim_selection_ownership(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            if "selection_override" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_evidence_cache_keys_preserve_exact_inputs(self) -> None:
        from inspect import Parameter, signature

        from x5crop.detection.evidence.evidence_cache_keys import content_detail_cache_key

        paths = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "evidence"
            / "evidence_cache_keys.py",
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "evidence"
            / "nearby_separator_diagnostics.py",
        )
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for path in paths
            if "round(" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])
        self.assertIs(
            signature(content_detail_cache_key).parameters["policy_key"].default,
            Parameter.empty,
        )

    def test_policy_assembly_does_not_own_tuning_literals(self) -> None:
        allowed_numeric_owners = {"presets.py", "profile_presets.py", "registry.py"}
        offenders: list[str] = []
        assembly_root = PROJECT_ROOT / "x5crop" / "policies" / "assembly"
        for path in assembly_root.glob("*.py"):
            if path.name in allowed_numeric_owners:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant):
                    continue
                value = node.value
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if value in (0, 1):
                    continue
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}: {value}"
                )

        self.assertEqual(offenders, [])

    def test_short_axis_correction_owns_its_expand_limit(self) -> None:
        from x5crop.policies.parameters.outer import ShortAxisGeometryCorrectionParameters

        self.assertIn(
            "max_expand_ratio",
            ShortAxisGeometryCorrectionParameters.__dataclass_fields__,
        )

    def test_runtime_confidence_threshold_has_one_entry_owned_default(self) -> None:
        from x5crop.policies.runtime.candidate import ScoringPolicy

        self.assertNotIn("confidence_threshold_default", ScoringPolicy.__dataclass_fields__)
        consistency_source = (
            PROJECT_ROOT / "x5crop" / "policies" / "consistency.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("confidence_threshold_default", consistency_source)

    def test_partial_candidate_parameters_use_physical_sequence_terms(self) -> None:
        from x5crop.policies.parameters.candidate import PartialHolderParameters
        from x5crop.policies.parameters.scoring import BaseDetectionScoreParameters

        self.assertIn("minimum_observed_frame_count", PartialHolderParameters.__dataclass_fields__)
        self.assertNotIn("min_count_35mm", PartialHolderParameters.__dataclass_fields__)
        self.assertNotIn("min_count_small", PartialHolderParameters.__dataclass_fields__)
        self.assertIn(
            "partial_two_frame_dense_sequence_cap",
            BaseDetectionScoreParameters.__dataclass_fields__,
        )
        self.assertIn(
            "partial_dense_sequence_min_nominal_count",
            BaseDetectionScoreParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "partial_two_35mm_cap",
            BaseDetectionScoreParameters.__dataclass_fields__,
        )
        self.assertNotIn(
            "partial_dense_strip_min_default_count",
            BaseDetectionScoreParameters.__dataclass_fields__,
        )

        assessment_root = PROJECT_ROOT / "x5crop" / "detection" / "candidate" / "assessment"
        offenders = []
        for path in assessment_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in ("35mm", "min_count_small"):
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
        self.assertEqual(offenders, [])

    def test_runtime_has_no_ambiguous_profile_layout_wrapper(self) -> None:
        self.assertFalse((PROJECT_ROOT / "x5crop" / "runtime" / "profile.py").exists())

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
        source_path = (
            PROJECT_ROOT
            / "x5crop"
            / "policies"
            / "assembly"
            / "factory.py"
        )
        text = source_path.read_text(encoding="utf-8")
        for term in banned:
            if term in text:
                offenders.append(f"{source_path.relative_to(PROJECT_ROOT)}: {term}")

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

    def test_policy_assembly_does_not_own_profiles_or_descriptions(self) -> None:
        text = (
            PROJECT_ROOT / "x5crop" / "policies" / "assembly" / "factory.py"
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

    def test_entry_surfaces_share_one_canonical_default_source(self) -> None:
        from x5crop.entry.options import (
            DEFAULT_CONFIDENCE_THRESHOLD,
            DEFAULT_DESKEW_MAX_ANGLE_DEGREES,
            DEFAULT_DESKEW_MIN_ANGLE_DEGREES,
        )
        from x5crop.runtime.limits import DIAGNOSTICS_JOB_LIMIT, STANDARD_JOB_LIMIT

        self.assertEqual(DEFAULT_DESKEW_MIN_ANGLE_DEGREES, 0.03)
        self.assertEqual(DEFAULT_DESKEW_MAX_ANGLE_DEGREES, 2.0)
        self.assertEqual(DEFAULT_CONFIDENCE_THRESHOLD, 0.85)
        self.assertEqual(STANDARD_JOB_LIMIT, 2)
        self.assertEqual(DIAGNOSTICS_JOB_LIMIT, 4)
        for relative_path in ("entry/cli.py", "entry/interactive.py"):
            text = (PROJECT_ROOT / "x5crop" / relative_path).read_text(encoding="utf-8")
            for literal in ("default=0.03", "default=0.85", "deskew_min_angle=0.03", "confidence_threshold=0.85"):
                self.assertNotIn(literal, text)

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
        from x5crop.policies.parameters.scoring import (
            BaseDetectionScoreParameters,
            ScoringCalibrationParameters,
        )
        from x5crop.policies.parameters.content import (
            ContentProfileParameters,
            ContentSupportParameters,
        )
        from x5crop.policies.parameters.outer import (
            EdgeAnchoredContentPositionParameters,
            FloatingContentPositionParameters,
            LongAxisGeometryCorrectionParameters,
            SeparatorOuterBandParameters,
        )
        from x5crop.policies.parameters.decision import DecisionReviewParameters
        from x5crop.geometry.detection_parameters import (
            EdgePairParameters,
            NearbySeparatorRefinementParameters,
            SeparatorWidthProfileSearchParameters,
        )

        required_fields = {
            ScoringCalibrationParameters: {
                "dual_lane_below_threshold_cap",
                "dual_lane_frame_count_mismatch_cap",
            },
            DecisionReviewParameters: {"outer_candidate_disagreement_min_spread_ratio"},
            FloatingContentPositionParameters: {
                "content_bbox_min_fraction",
                "min_short_axis_px",
                "min_short_axis_ratio",
                "min_width_px",
            },
            EdgeAnchoredContentPositionParameters: {
                "content_bbox_min_fraction",
                "min_short_axis_px",
                "min_short_axis_ratio",
                "min_width_px",
            },
            LongAxisGeometryCorrectionParameters: {
                "min_corrected_width_ratio",
                "min_corrected_width_px",
            },
            ContentProfileParameters: {
                "percentiles",
                "smooth_min_px",
                "min_run_width_px",
            },
            ContentSupportParameters: {"missing_aspect_score"},
            BaseDetectionScoreParameters: {
                "image_quality_percentiles",
                "hard_support_floor_min_expected_gaps",
                "hard_gap_floor_min_count",
                "model_gap_overuse_min_count",
                "partial_ambiguous_count_max",
                "partial_dense_sequence_min_nominal_count",
            },
            SeparatorOuterBandParameters: {
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
