from __future__ import annotations

import ast
from inspect import signature
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT, forbidden_import_edges


class LayerBoundariesOutputContractTest(unittest.TestCase):
    def test_report_restoration_is_the_only_schema_deserializer(self) -> None:
        reuse = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "final_detection_from_record as _final_detection_from_record",
            reuse,
        )
        for forbidden in (
            "DecisionGateAssessment(",
            "FinalDetection(",
            "def _box_from_record",
        ):
            self.assertNotIn(forbidden, reuse)

    def test_report_output_has_one_runtime_owner(self) -> None:
        owners = [
            path.name
            for path in (PROJECT_ROOT / "x5crop/runtime").glob("*.py")
            if "write_report_outputs_for_result"
            in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(owners, ["app.py"])

    def test_debug_reads_current_typed_sequence_geometry(self) -> None:
        source = (PROJECT_ROOT / "x5crop/debug/separators.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FinalDetection", source)
        self.assertIn("separator_observations", source)
        self.assertIn("frame_sequence.spacings", source)
        self.assertNotIn(".detail", source)

    def test_debug_policy_and_renderers_define_exactly_three_panels(self) -> None:
        from x5crop.policies.registry import get_detection_policy

        policy = get_detection_policy("135", "full").diagnostics
        self.assertEqual(
            policy.debug_panels,
            ("original_gray", "debug_boxes", "separator_evidence"),
        )
        tree = ast.parse(
            (PROJECT_ROOT / "x5crop/debug/panels.py").read_text(encoding="utf-8")
        )
        panel_ids = {
            key.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "panel_builders"
                for target in node.targets
            )
            and isinstance(node.value, ast.Dict)
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        self.assertEqual(panel_ids, set(policy.debug_panels))

    def test_runtime_resolves_format_mode_once(self) -> None:
        bootstrap = (PROJECT_ROOT / "x5crop/runtime/bootstrap.py").read_text(
            encoding="utf-8"
        )
        other_runtime = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop/runtime").glob("*.py")
            if path.name != "bootstrap.py"
        )
        self.assertEqual(bootstrap.count("DetectionPolicyBundle.for_format_mode"), 1)
        self.assertNotIn("DetectionPolicyBundle.for_format_mode", other_runtime)

    def test_frame_bleed_plan_has_explicit_physical_inputs(self) -> None:
        from x5crop.output.frame_bleed import frame_bleed_plan
        from x5crop.runtime.frame_bleed import prepare_frame_bleed

        self.assertEqual(
            tuple(signature(frame_bleed_plan).parameters),
            (
                "frames",
                "frame_crop_envelopes",
                "overlap_requirements",
                "user_bleed",
                "layout",
            ),
        )
        self.assertEqual(
            tuple(signature(prepare_frame_bleed).parameters),
            ("candidate", "user_bleed"),
        )

    def test_workflow_orders_bleed_decision_and_finalization_once(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/workflow.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(source.index("prepare_frame_bleed("), source.index("apply_decision_gate("))
        self.assertLess(source.index("apply_decision_gate("), source.index("finalize_detection("))

    def test_finalization_only_applies_frame_bleed_geometry(self) -> None:
        source = (PROJECT_ROOT / "x5crop/detection/final/finalize.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("apply_frame_bleed", source)
        for forbidden in ("gray", "DetectionPolicy", "separator", "content", "Candidate"):
            self.assertNotIn(forbidden, source)

    def test_output_layer_is_independent_of_detection_and_runtime(self) -> None:
        self.assertEqual(
            forbidden_import_edges(("x5crop.output",), ("x5crop.detection", "x5crop.runtime")),
            [],
        )

    def test_report_debug_and_output_do_not_resolve_policy_registry(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                PROJECT_ROOT / "x5crop/report",
                PROJECT_ROOT / "x5crop/debug",
                PROJECT_ROOT / "x5crop/output",
            )
            for path in root.rglob("*.py")
        )
        self.assertNotIn("get_detection_policy", source)
        self.assertNotIn("DetectionPolicyBundle.for_format_mode", source)


if __name__ == "__main__":
    unittest.main()
