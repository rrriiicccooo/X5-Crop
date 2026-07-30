from __future__ import annotations

import contextlib
import io
from dataclasses import fields
from pathlib import Path
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
from x5crop.domain import EvidenceState
from x5crop.entry.cli import build_parser, options_from_args
from x5crop.entry.interactive import interactive_options
from x5crop.formats import format_spec
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
)
from x5crop.run_config import RunConfig
from x5crop.runtime.bootstrap import runtime_invocation_from_options
from x5crop.runtime.limits import (
    DIAGNOSTICS_JOB_LIMIT,
    STANDARD_JOB_DEFAULT,
    STANDARD_JOB_LIMIT,
)
from x5crop.runtime.options import RuntimeOptions


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
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--debug", option_strings)
        self.assertIn("--debug-analysis", option_strings)
        self.assertIn("--debug-errors", option_strings)
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
        diagnostics = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--diagnostics"]
            )
        )
        self.assertTrue(diagnostics.report)
        self.assertTrue(diagnostics.debug_analysis)
        self.assertFalse(diagnostics.copy_review_files)

    def test_standard_job_default_and_caps_are_distinct(self) -> None:
        self.assertEqual(STANDARD_JOB_DEFAULT, 2)
        self.assertEqual(STANDARD_JOB_LIMIT, 3)
        self.assertEqual(DIAGNOSTICS_JOB_LIMIT, 4)

        parser = build_parser()
        default_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135"])
        )
        normal_four_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--jobs", "4"]
            )
        )
        diagnostics_options = options_from_args(
            parser.parse_args(
                [
                    "input.tif",
                    "--format",
                    "135",
                    "--jobs",
                    "4",
                    "--diagnostics",
                ]
            )
        )
        self.assertEqual(default_options.jobs, 2)

        with (
            mock.patch(
                "x5crop.runtime.bootstrap.iter_input_files",
                return_value=[Path("input.tif")],
            ),
            mock.patch(
                "x5crop.runtime.bootstrap.read_tiff_page_shape",
                return_value=(100, 200),
            ),
        ):
            self.assertEqual(
                runtime_invocation_from_options(default_options).config.jobs,
                2,
            )
            self.assertEqual(
                runtime_invocation_from_options(normal_four_options).config.jobs,
                3,
            )
            self.assertEqual(
                runtime_invocation_from_options(diagnostics_options).config.jobs,
                4,
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
            mock.patch("builtins.input", side_effect=("dual", "n")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            options = interactive_options()
        self.assertEqual(options.format_id, "135-dual")
        self.assertEqual(options.strip_mode, "full")
        self.assertIsNone(options.requested_count)

    def test_schema_and_two_gate_status_authority_are_current(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "detection_report")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "bounded_safe_crop_capacity_grid",
        )
        candidate = candidate_gate_assessment(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.UNAVAILABLE,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            output_slot_count_state=EvidenceState.SUPPORTED,
            slot_ordinal_state=EvidenceState.SUPPORTED,
            slot_ownership_state=EvidenceState.SUPPORTED,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.SUPPORTED,
            output_protection_state=EvidenceState.SUPPORTED,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        self.assertTrue(
            all(check.final_review_reason is None for check in candidate.checks)
        )
        decision = apply_decision_gate(candidate, FrameCountMode.AUTO)
        self.assertEqual(decision.status, "approved_auto")
        self.assertEqual(decision.final_review_reasons, ())

    def test_runtime_dependency_surface_remains_minimal(self) -> None:
        package_list = "numpy tifffile imagecodecs Pillow"
        owners = (
            ".github/workflows/verify.yml",
            "tools/install/X5_Crop_Mac_install.command",
            "tools/install/X5_Crop_win_install.bat",
        )
        active_text = "\n".join(read_sources().values()).lower()
        self.assertNotIn("scipy", active_text)
        self.assertNotIn("opencv", active_text)
        self.assertNotIn("cv2", active_text)
        for relative in owners:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(package_list, text)

    def test_repository_layout_and_release_manifest_are_current(self) -> None:
        for relative in (
            "ARCHITECTURE.md",
            "CHANGELOG.md",
            "PROJECT_MEMORY.md",
            "install",
            "X5_Crop_Mac_diagnostics.command",
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
        self.assertFalse(
            any("uninstall" in archive_path.lower() for archive_path in RELEASE_PATHS)
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

    def test_launcher_is_thin_and_standalone_embeds_current_modules(self) -> None:
        launcher = (ROOT / "X5_Crop.py").read_text(encoding="utf-8")
        self.assertEqual(len(launcher.splitlines()), 13)
        self.assertIn("from x5crop.entry.cli import main", launcher)
        sources = read_sources()
        self.assertIn("x5crop.detection.grid.search", sources)
        self.assertIn("x5crop.detection.evidence.separator", sources)


if __name__ == "__main__":
    unittest.main()
