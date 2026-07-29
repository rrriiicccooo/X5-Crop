from __future__ import annotations

import contextlib
import io
from pathlib import Path
import unittest

from tools.release.standalone import read_sources
from x5crop.detection.decision.model import (
    DECISION_GATE_CHECK_CODES,
    DECISION_GATE_REASON_BY_CODE,
    DecisionGateAssessment,
)
from x5crop.detection.gate_checks import (
    GateCheck,
    GateRequirement,
    GateStage,
)
from x5crop.domain import EvidenceState
from x5crop.entry.cli import build_parser
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
)


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

    def test_active_runtime_has_no_legacy_detection_vocabulary(self) -> None:
        forbidden = (
            "PhotoEdge",
            "FrameBleed",
            "AxisBleedParameters",
            "TransformGeometryEvidence",
            "approved_auto",
            "shared_short_axis",
            "rotated_gray",
            "bleed_x",
            "bleed_y",
            "copy_for_review_if_needed",
            "write_crops_if_allowed",
        )
        sources = read_sources()
        combined = "\n".join(sources.values())
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, combined)

    def test_gitignore_has_no_obsolete_source_exceptions(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn("x5crop/detection/candidate/build", ignore)

    def test_ci_and_installers_share_runtime_dependencies(self) -> None:
        package_list = "numpy scipy tifffile imagecodecs Pillow"
        owners = (
            ".github/workflows/verify.yml",
            "install/X5_Crop_Mac_install.command",
            "install/X5_Crop_win_install.bat",
        )
        for relative in owners:
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(package_list, text)

    def test_old_pixel_bleed_and_dead_export_switches_are_rejected(self) -> None:
        parser = build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        for option in (
            "--bleed",
            "--bleed-x",
            "--bleed-y",
            "--export-review",
            "--dry-run",
        ):
            self.assertNotIn(option, option_strings)
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            parser.parse_args(["input.tif", "--format", "135", "--bleed", "1"])
        self.assertEqual(raised.exception.code, 2)

    def test_schema_has_one_current_revision(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "detection_report")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "source_core_grid_authority",
        )

    def test_decision_gate_cannot_express_auto_approval(self) -> None:
        supported_checks = tuple(
            GateCheck(
                code=code,
                stage=GateStage.DECISION,
                state=EvidenceState.SUPPORTED,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
                final_review_reason=DECISION_GATE_REASON_BY_CODE[code],
            )
            for code in DECISION_GATE_CHECK_CODES
        )
        with self.assertRaises(ValueError):
            DecisionGateAssessment(supported_checks)

    def test_launcher_remains_thin_and_release_embeds_modular_tree(self) -> None:
        launcher = (ROOT / "X5_Crop.py").read_text(encoding="utf-8")
        self.assertEqual(len(launcher.splitlines()), 13)
        self.assertIn("from x5crop.entry.cli import main", launcher)
        self.assertIn("x5crop.detection.source_core", read_sources())


if __name__ == "__main__":
    unittest.main()
