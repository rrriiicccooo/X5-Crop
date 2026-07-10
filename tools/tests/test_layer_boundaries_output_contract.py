from __future__ import annotations

from pathlib import Path
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT


class LayerBoundariesOutputContractTest(unittest.TestCase):
    def test_finalization_does_not_generate_exposure_overlap_evidence(self) -> None:
        banned = (
            "exposure_overlap_evidence_detail",
            "get_detection_policy",
            "policies.registry",
        )
        offenders: list[str] = []
        source_root = PROJECT_ROOT / "x5crop" / "detection" / "final"
        self.assertTrue(source_root.is_dir())
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_exposure_evidence_output_plan_and_decision_keep_one_way_dependencies(self) -> None:
        exposure_text = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "evidence"
            / "exposure_overlap.py"
        ).read_text(encoding="utf-8")
        output_plan_text = (
            PROJECT_ROOT / "x5crop" / "output" / "protection.py"
        ).read_text(encoding="utf-8")
        decision_text = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "decision"
            / "final_decision.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("runtime.diagnostics", exposure_text)
        self.assertNotIn("output.protection", exposure_text)
        self.assertNotIn("decision", exposure_text)
        self.assertNotIn("x5crop.detection", output_plan_text)
        self.assertNotIn("policies.registry", output_plan_text)
        self.assertNotIn("evidence.exposure_overlap", decision_text)
        self.assertNotIn("output.protection", decision_text)

    def test_outer_alignment_evidence_does_not_own_correction_policy(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "detection" / "evidence" / "outer_alignment.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("OuterAlignmentEvidenceParameters", text)
        self.assertNotIn("ContentContainmentCorrectionPolicy", text)
        self.assertNotIn("corrected_outer_from_alignment", text)

    def test_runtime_policy_lookup_stays_out_of_output_and_detection_layers(self) -> None:
        banned = ("get_detection_policy", "policies.registry")
        checked_paths = [
            PROJECT_ROOT / "x5crop" / "detection",
            PROJECT_ROOT / "x5crop" / "debug",
            PROJECT_ROOT / "x5crop" / "report",
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py",
        ]
        offenders: list[str] = []
        for root in checked_paths:
            paths = [root] if root.is_file() else list(root.rglob("*.py"))
            for path in paths:
                text = path.read_text(encoding="utf-8")
                for term in banned:
                    if term in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])

    def test_output_bleed_helpers_live_in_output_layer(self) -> None:
        offenders: list[str] = []
        banned = (
            "detection.final.output_bleed",
            "from .output_bleed",
            "final.output_bleed",
        )
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
        self.assertTrue((PROJECT_ROOT / "x5crop" / "output" / "bleed.py").is_file())


if __name__ == "__main__":
    unittest.main()
