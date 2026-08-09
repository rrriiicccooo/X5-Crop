from __future__ import annotations

import contextlib
from hashlib import sha256
import io
from dataclasses import fields
from pathlib import Path
import sys
import unittest
from unittest import mock

from tools.release.manifest import RELEASE_FILES, RELEASE_PATHS
from tools.release.standalone import read_sources
from x5crop.configuration.model import (
    FrameCountMode,
    FrameCountRequest,
)
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.candidate.assessment.model import (
    CANDIDATE_GATE_CHECK_CODES,
)
from x5crop.detection.gate_checks import TypedAssessment
from x5crop.domain import EvidenceState
from x5crop.entry.cli import build_parser, options_from_args
from x5crop.entry.interactive import interactive_options
from x5crop.formats import format_spec
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
)
from x5crop.report.read_models import gate_check_read_model
from x5crop.run_config import RunConfig
from x5crop.runtime.bootstrap import runtime_invocation_from_options
from x5crop.runtime.limits import (
    STANDARD_JOB_DEFAULT,
    STANDARD_JOB_LIMIT,
)
from x5crop.runtime.options import RuntimeOptions
from x5crop.runtime.detection_snapshot import implementation_sha256


ROOT = Path(__file__).resolve().parents[2]


class CurrentOnlyContractTest(unittest.TestCase):
    def test_obsolete_detector_files_are_absent(self) -> None:
        forbidden_paths = (
            "x5crop/detection/physical",
            "x5crop/detection/evidence/photo_edges.py",
            "x5crop/detection/evidence/separator_sequence.py",
            "x5crop/detection/evidence/transform_geometry.py",
            "x5crop/detection/output_preparation.py",
            "x5crop/output/frame_bleed.py",
            "x5crop/image/separator_profile.py",
            "x5crop/configuration/grid.py",
            "x5crop/configuration/content.py",
            "x5crop/detection/grid",
            "x5crop/detection/evidence/separator.py",
            "x5crop/detection/protection.py",
            "x5crop/image/crop_pixels.py",
            "x5crop/image/evidence.py",
        )
        for relative in forbidden_paths:
            with self.subTest(path=relative):
                target = ROOT / relative
                if target.is_dir():
                    self.assertFalse(tuple(target.rglob("*.py")))
                else:
                    self.assertFalse(target.exists())

    def test_active_runtime_has_no_replaced_schema_or_placeholder_vocabulary(
        self,
    ) -> None:
        forbidden = (
            "source_core_grid_authority",
            "source_core_review",
            "resolved_frame_count",
            "allowed_partial_counts",
            "complete_strip_can_be_underfilled",
            "frame_grid_authority_unavailable",
            "source_content_measurement_unavailable",
            "no_independent_phase_authority",
            "not_applicable_frame_grid_unavailable",
            "not_applicable_core_unavailable",
            "FrameGridEvidence",
            "PhotoContainmentEvidence",
            "VisualDeskewOutcome",
            "write_crops_if_allowed",
            "copy_for_review_if_needed",
            "candidate_counts",
            "selected_count",
            "FrameCountDominanceAssessment",
            "DominanceRelation",
            "G_MAX",
            "automatic_count_unresolved",
            "bounded_safe_crop_grid",
            "bounded_ordered_grid_v4",
            "x5crop_run_manifest_v1",
            "x5crop_production_performance_v3",
            "x5crop_fixed_sample_profile_v1",
            "work_by_count_component",
            "lane_global_proposal_limit",
            "count_dominance",
            "SourceContentComponent",
            "ContentRowRunTable",
            "ContentConfiguration",
            "query_dp_memory",
            "unresolved_codes",
            "slot_ownership",
            "output_protection",
            "allow_grid_blank_identity",
            "grid_blank_no_photo_geometry",
            "format_physical_templates",
            "dp_states",
            "dp_transitions",
        )
        active_paths = tuple((ROOT / "x5crop").rglob("*.py")) + tuple(
            path
            for path in (ROOT / "tools").rglob("*.py")
            if "tests" not in path.relative_to(ROOT / "tools").parts
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in active_paths
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, combined)

    def test_diagnostic_verifier_wraps_the_production_cli(self) -> None:
        diagnostic = (
            ROOT / "tools/regression/diagnostic_cohort.py"
        ).read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        self.assertIn('str(PROJECT_ROOT / "X5_Crop.py")', diagnostic)
        self.assertIn("subprocess.run(", diagnostic)
        self.assertNotIn("runtime_invocation_from_options", diagnostic)
        self.assertNotIn("process_one", diagnostic)
        self.assertNotIn("diagnostics=True", diagnostic)
        self.assertIn(
            '"$PYTHON" -m tools.regression.diagnostic_cohort\n',
            verifier,
        )
        self.assertNotIn(
            "diagnostic_cohort --identity-only",
            verifier,
        )

    def test_input_mapping_is_frozen_without_parallel_auto_switch(self) -> None:
        partial = format_spec("135")
        auto = FrameCountRequest.from_user_input(partial, "partial", None)
        explicit = FrameCountRequest.from_user_input(partial, "partial", 3)
        fixed = FrameCountRequest.from_user_input(partial, "full", 6)
        self.assertEqual(auto.mode, FrameCountMode.AUTO)
        self.assertIsNone(auto.authoritative_count)
        self.assertEqual(explicit.mode, FrameCountMode.EXPLICIT)
        self.assertEqual(explicit.authoritative_count, 3)
        self.assertEqual(fixed.mode, FrameCountMode.FIXED_FULL)
        self.assertEqual(fixed.authoritative_count, 6)
        parser = build_parser()
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--auto-count", option_strings)
        parsed = parser.parse_args(
            ["input.tif", "--format", "135", "--strip", "partial", "--count", "auto"]
        )
        self.assertIsNone(options_from_args(parsed).requested_count)
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(
                ["input.tif", "--format", "135", "--auto-count"]
            )

    def test_only_current_debug_analysis_cli_and_runtime_surface_remain(
        self,
    ) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--debug", option_strings)
        self.assertIn("--debug-analysis", option_strings)
        self.assertIn("--preview", option_strings)
        self.assertNotIn("--debug-errors", option_strings)
        self.assertNotIn("--diagnostics", option_strings)
        self.assertNotIn("--overwrite", option_strings)
        self.assertIn("--allow-best-effort-output", option_strings)
        normalized_help = " ".join(help_text.split())
        self.assertIn(
            "three-panel JPG comparing detected and selected TOP/BOTTOM, "
            "detected and selected START/END, and final safe output envelopes",
            normalized_help,
        )
        self.assertIn(
            "SHA-bound detection snapshot, but no official TIFFs or review copies",
            normalized_help,
        )
        preview_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135", "--preview"])
        )
        self.assertTrue(preview_options.preview)
        self.assertTrue(preview_options.debug_analysis)
        for runtime_type in (RuntimeOptions, RunConfig):
            with self.subTest(runtime_type=runtime_type.__name__):
                self.assertNotIn(
                    "debug",
                    {field.name for field in fields(runtime_type)},
                )
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(
                ["input.tif", "--format", "135", "--debug"]
            )
        for removed in ("--diagnostics", "--overwrite", "--debug-errors"):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                parser.parse_args(["input.tif", "--format", "135", removed])

    def test_standard_job_default_and_caps_are_distinct(self) -> None:
        self.assertEqual(STANDARD_JOB_DEFAULT, 1)
        self.assertEqual(STANDARD_JOB_LIMIT, 3)

        parser = build_parser()
        default_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135"])
        )
        explicit_two_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--jobs", "2"]
            )
        )
        normal_four_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--jobs", "4"]
            )
        )
        self.assertEqual(default_options.jobs, 1)

        with (
            mock.patch(
                "x5crop.runtime.bootstrap.iter_input_files",
                return_value=[Path("input.tif")],
            ),
        ):
            self.assertEqual(
                runtime_invocation_from_options(default_options).config.jobs,
                1,
            )
            self.assertEqual(
                runtime_invocation_from_options(explicit_two_options).config.jobs,
                2,
            )
            self.assertEqual(
                runtime_invocation_from_options(normal_four_options).config.jobs,
                3,
            )

    def test_strip_handling_has_one_current_contract(self) -> None:
        for format_id in ("135", "half", "xpan", "120-645", "120-66", "120-67"):
            strip = format_spec(format_id).strip
            self.assertEqual(
                strip.partial_count_range,
                tuple(range(1, strip.default_count + 1)),
            )
        self.assertFalse(
            format_spec("135-dual").strip.partial_mode_supported
        )
        self.assertEqual(
            format_spec("135-dual").strip.partial_count_range,
            (),
        )

    def test_interactive_dual_format_never_enters_partial_count_prompt(
        self,
    ) -> None:
        with (
            mock.patch("builtins.input", side_effect=("dual", "n", "n")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            options = interactive_options()
        self.assertEqual(options.format_id, "135-dual")
        self.assertEqual(options.strip_mode, "full")
        self.assertIsNone(options.requested_count)

    def test_schema_and_two_gate_status_authority_are_current(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "x5crop_detection_report_v5")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "x5crop_v5_current_2",
        )
        candidate = candidate_gate_assessment(
            {
                code: TypedAssessment(EvidenceState.SUPPORTED, None)
                for code in CANDIDATE_GATE_CHECK_CODES
            }
        )
        self.assertTrue(
            all(check.final_review_reason is None for check in candidate.checks)
        )
        self.assertEqual(
            tuple(gate_check_read_model(candidate.checks[0])),
            (
                "code",
                "stage",
                "state",
                "gap",
                "final_review_reason",
                "blocks",
            ),
        )
        decision = apply_decision_gate(candidate, FrameCountMode.AUTO)
        self.assertEqual(decision.status, "approved_auto")
        self.assertEqual(decision.final_review_reasons, ())

    def test_runtime_dependency_surface_is_pinned_and_shared(self) -> None:
        contract_path = ROOT / "tools/install/dependencies.toml"
        self.assertTrue(contract_path.is_file())
        self.assertFalse((ROOT / "tools/install/requirements.txt").exists())
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/install/dependency_manager.py", workflow)
        self.assertIn("tools/install/dependencies.toml", workflow)
        for relative in (
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
        ):
            with self.subTest(installer=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("dependency_manager.py", text)
                self.assertIn(" check", text)
                self.assertNotIn("pip install --user -U", text)
                self.assertNotIn("ensurepip --upgrade", text)
        for relative in ("X5_Crop_Mac.command", "X5_Crop_win.bat"):
            launcher = (ROOT / relative).read_text()
            self.assertIn("dependency_manager.py", launcher)
            self.assertIn("dependencies.toml", launcher)
            self.assertIn(" check", launcher)
            self.assertNotIn("REQUIRED_IMPORTS", launcher)

    def test_repository_layout_and_release_manifest_are_current(self) -> None:
        for relative in (
            "ARCHITECTURE.md",
            "CHANGELOG.md",
            "PROJECT_MEMORY.md",
            "install",
            "X5_Crop_Mac_diagnostics.command",
            "tools/regression/golden_baseline.py",
            "tools/regression/safe_crop_acceptance.py",
            "tools/regression/gold_comparator.py",
            "tools/regression/gold_accuracy.py",
            "tools/regression/non_detection_freeze.py",
            "tools/regression/contracts/non_detection_freeze_v1.json",
            "tools/regression/contracts/non_detection_protected_paths_v1.txt",
            "tools/tests/test_bounded_grid_contract.py",
            "tools/tests/test_non_detection_freeze_contract.py",
        ):
            with self.subTest(absent=relative):
                self.assertFalse((ROOT / relative).exists())
        for relative in (
            "LICENSE",
            "docs/ARCHITECTURE.md",
            "docs/CHANGELOG.md",
            "docs/PROJECT_MEMORY.md",
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
            "tools/install/X5_Crop_Mac_uninstall.command",
            "tools/install/X5_Crop_win_uninstall.bat",
            "tools/install/dependency_manager.py",
            "tools/install/dependencies.toml",
            "tools/tests/test_photo_geometry_contract.py",
        ):
            with self.subTest(present=relative):
                self.assertTrue((ROOT / relative).is_file())

        release_sources = dict(RELEASE_FILES)
        self.assertIn("LICENSE", RELEASE_PATHS)
        self.assertEqual(
            release_sources["install/X5_Crop_Mac_install.command"],
            "tools/install/X5_Crop_Mac_install.command",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_win_install.bat"],
            "tools/install/X5_Crop_win_install.bat",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_Mac_uninstall.command"],
            "tools/install/X5_Crop_Mac_uninstall.command",
        )
        self.assertEqual(
            release_sources["install/X5_Crop_win_uninstall.bat"],
            "tools/install/X5_Crop_win_uninstall.bat",
        )
        self.assertEqual(
            release_sources["install/dependency_manager.py"],
            "tools/install/dependency_manager.py",
        )
        self.assertEqual(
            release_sources["install/dependencies.toml"],
            "tools/install/dependencies.toml",
        )

        project_memory = (ROOT / "docs/PROJECT_MEMORY.md").read_text(
            encoding="utf-8"
        )
        for obsolete in (
            "source_core_grid_authority",
            "frame_grid_authority_unavailable",
            "NO_INDEPENDENT_PHASE_AUTHORITY",
        ):
            with self.subTest(obsolete_memory=obsolete):
                self.assertNotIn(obsolete, project_memory)

    def test_public_docs_expose_user_behavior_not_internal_architecture(
        self,
    ) -> None:
        public_docs = (
            ROOT / "README.md",
            ROOT / "docs/quick-start.zh-CN.md",
            ROOT / "docs/quick-start.en.md",
            ROOT / "docs/user-guide.zh-CN.md",
            ROOT / "docs/user-guide.en.md",
        )
        forbidden = (
            "CandidateGate",
            "DecisionGate",
            "schema_revision",
            "SourceFrameGeometry",
            "NominalPitch",
            "template_group_count",
            "gold_accuracy",
            "S062",
            "0fdb90dc",
            "dirty tree",
            "dirty 开发树",
        )
        for path in public_docs:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)

        architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        for retired in (
            "FrameGeometryState",
            "GridInferredBlankOutputGeometry",
            "lane-local ordered DP",
            "source_coordinate_photo_geometry",
            "non-detection",
        ):
            with self.subTest(retired_architecture=retired):
                self.assertNotIn(retired, architecture)

    def test_documents_keep_their_single_current_responsibility(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        changelog = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
        memory = (ROOT / "docs/PROJECT_MEMORY.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("当前源码检查点是 `X5_Crop.py` V4.9", agents)
        self.assertIn("仓库只有一条 V5 current-only production path", agents)
        for task_state in (
            "当前完成边界",
            "S051/explicit",
            "S062/explicit",
            "S109/explicit",
            "精确下一步",
        ):
            with self.subTest(changelog_task_state=task_state):
                self.assertNotIn(task_state, changelog)
        for stale_memory in (
            "当前源码和 [ARCHITECTURE.md](ARCHITECTURE.md) 仍是 V4.9",
            "V5 runtime、唯一 schema",
            "第一条端到端 slice",
        ):
            with self.subTest(stale_memory=stale_memory):
                self.assertNotIn(stale_memory, memory)

    def test_completed_phase_freeze_is_not_a_verifier_owner(self) -> None:
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        platform_receipt = (
            ROOT / "tools/regression/platform_receipt.py"
        ).read_text(encoding="utf-8")
        for retired in (
            "non-detection)",
            "audit)",
            "tools.regression.non_detection_freeze",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, verifier)
        self.assertNotIn("non_detection_audit", platform_receipt)
        self.assertIn(
            'PLATFORM_RECEIPT_SCHEMA = "x5crop_platform_receipt_v2"',
            platform_receipt,
        )

    def test_launcher_is_thin_and_standalone_embeds_current_modules(self) -> None:
        launcher = (ROOT / "X5_Crop.py").read_text(encoding="utf-8")
        self.assertEqual(len(launcher.splitlines()), 13)
        self.assertIn("from x5crop.entry.cli import main", launcher)
        sources = read_sources()
        for module in (
            "x5crop.detection.photo_geometry.detector",
            "x5crop.detection.photo_geometry.measurement",
            "x5crop.detection.photo_geometry.source_geometry",
            "x5crop.detection.photo_geometry.template_profiles",
            "x5crop.detection.photo_geometry.template_model",
            "x5crop.detection.photo_geometry.template_first",
        ):
            with self.subTest(embedded=module):
                self.assertIn(module, sources)
        for module in (
            "x5crop.detection.photo_geometry.geometry_build",
            "x5crop.detection.photo_geometry.selection",
            "x5crop.detection.photo_geometry.sequence",
        ):
            with self.subTest(retired=module):
                self.assertNotIn(module, sources)

    def test_snapshot_implementation_identity_matches_standalone_sources(
        self,
    ) -> None:
        sources = read_sources()
        expected = sha256()
        for name in sorted(sources):
            expected.update(name.encode("utf-8"))
            expected.update(b"\0")
            expected.update(sources[name].encode("utf-8"))
            expected.update(b"\0")
        implementation_sha256.cache_clear()
        self.assertEqual(implementation_sha256(), expected.hexdigest())
        with mock.patch.object(
            sys.modules["__main__"],
            "_X5_EMBEDDED_SOURCES",
            sources,
            create=True,
        ):
            implementation_sha256.cache_clear()
            self.assertEqual(implementation_sha256(), expected.hexdigest())
        implementation_sha256.cache_clear()


if __name__ == "__main__":
    unittest.main()
