from __future__ import annotations

import ast
from inspect import signature
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.architecture_contracts import PROJECT_ROOT, forbidden_import_edges


class LayerBoundariesOutputContractTest(unittest.TestCase):
    def test_output_layer_is_geometry_and_path_only(self) -> None:
        mutating_calls = {
            "mkdir",
            "rename",
            "replace",
            "rmdir",
            "touch",
            "unlink",
            "write_bytes",
            "write_text",
        }
        offenders = []
        for path in (PROJECT_ROOT / "x5crop/output").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{node.func.attr}"
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in mutating_calls
            )
        self.assertEqual(offenders, [])

    def test_output_surface_is_a_path_model_without_side_effect_methods(self) -> None:
        from x5crop.output.surface import OutputSurface

        self.assertEqual(set(OutputSurface.__dataclass_fields__), {"root"})
        self.assertFalse(hasattr(OutputSurface, "ensure_root"))

    def test_report_validation_is_the_only_schema_deserializer(self) -> None:
        reuse = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text(
            encoding="utf-8"
        )
        restoration = (PROJECT_ROOT / "x5crop/report/restoration.py").read_text(
            encoding="utf-8"
        )
        validation = (PROJECT_ROOT / "x5crop/report/validation.py").read_text(
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
        self.assertIn("_typed_value_from_read_model", validation)
        for duplicate_constructor in (
            "OutputGeometry(",
            "FrameBleedPlan(",
            "TransformGeometryEvidence(",
        ):
            self.assertNotIn(duplicate_constructor, restoration)

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
        self.assertNotIn("FinalDetection", source)
        self.assertIn("separator_observations", source)
        self.assertIn("solution.inter_photo_spacings", source)
        self.assertNotIn(".detail", source)

    def test_separator_overlay_uses_explicit_workspace_extent(self) -> None:
        from tools.tests.physical_gate_support import (
            candidate_fixture,
        )
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.debug.separators import draw_separator_overlay

        diagnostics = get_detection_configuration("135", "full").diagnostics
        draw_separator_overlay(
            np.zeros((100, 200, 3), dtype=np.uint8),
            candidate_fixture(),
            1.0,
            diagnostics.separator_overlay,
            diagnostics.style,
            200,
            100,
        )

    def test_separator_overlay_never_reverse_engineers_source_dimensions(self) -> None:
        from tools.tests.physical_gate_support import (
            candidate_fixture,
        )
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.debug.separators import draw_separator_overlay
        from x5crop.domain import Box

        diagnostics = get_detection_configuration("135", "full").diagnostics
        with patch(
            "x5crop.debug.separators.separator_mark_box",
            return_value=Box(0, 0, 1, 1),
        ) as mark_box:
            draw_separator_overlay(
                np.zeros((33, 67, 3), dtype=np.uint8),
                candidate_fixture(),
                1.0 / 3.0,
                diagnostics.separator_overlay,
                diagnostics.style,
                67,
                33,
            )

        self.assertTrue(mark_box.called)
        self.assertEqual(mark_box.call_args.args[-3:], (67, 33, "horizontal"))

    def test_output_bleed_reads_assessed_spacing_evidence(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/frame_bleed.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("inter_photo_boundary_preservation", source)
        self.assertNotIn("geometry.inter_photo_spacings", source)

    def test_debug_analysis_has_one_fixed_three_panel_contract(self) -> None:
        import x5crop.configuration.diagnostics as diagnostics_model
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.debug.panels import (
            draw_evidence_context_overlay,
            stack_debug_panels,
        )
        from x5crop.debug.writer import write_debug_analysis

        configuration = get_detection_configuration("135", "full").diagnostics
        self.assertEqual(
            set(configuration.__dataclass_fields__),
            {"separator_overlay", "separator_evidence_image", "style"},
        )
        self.assertFalse(hasattr(diagnostics_model, "DebugPanelConfiguration"))
        self.assertNotIn(
            "include_frames",
            signature(draw_evidence_context_overlay).parameters,
        )
        self.assertEqual(
            tuple(signature(stack_debug_panels).parameters),
            (
                "original_gray",
                "debug_boxes",
                "separator_evidence",
                "horizontal",
                "style",
            ),
        )
        self.assertEqual(
            signature(write_debug_analysis).return_annotation,
            "str",
        )

    def test_runtime_resolves_format_mode_once(self) -> None:
        bootstrap = (PROJECT_ROOT / "x5crop/runtime/bootstrap.py").read_text(
            encoding="utf-8"
        )
        other_runtime = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop/runtime").glob("*.py")
            if path.name != "bootstrap.py"
        )
        self.assertEqual(bootstrap.count("DetectionConfigurationBundle.for_format_mode"), 1)
        self.assertNotIn("DetectionConfigurationBundle.for_format_mode", other_runtime)

    def test_frame_bleed_plan_has_explicit_physical_inputs(self) -> None:
        from x5crop.output.frame_bleed import frame_bleed_plan
        from x5crop.runtime.frame_bleed import prepare_frame_bleed

        self.assertEqual(
            tuple(signature(frame_bleed_plan).parameters),
            (
                "frames",
                "frame_output_bounds",
                "overlap_requirements",
                "user_bleed",
                "layout",
            ),
        )
        self.assertEqual(
            tuple(signature(prepare_frame_bleed).parameters),
            ("selection", "user_bleed"),
        )

    def test_workflow_orders_bleed_decision_and_finalization_once(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/workflow.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(source.index("prepare_frame_bleed("), source.index("apply_decision_gate("))
        self.assertLess(source.index("apply_decision_gate("), source.index("finalize_detection("))

    def test_finalization_only_applies_frame_bleed_geometry(self) -> None:
        final_root = PROJECT_ROOT / "x5crop/detection/final"
        owners = tuple(
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in final_root.glob("*.py")
            if "apply_frame_bleed" in path.read_text(encoding="utf-8")
        )
        self.assertEqual(owners, ("x5crop/detection/final/finalize.py",))
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in final_root.glob("*.py")
        )
        for forbidden in ("gray", "DetectionConfiguration", "separator", "content", "Candidate"):
            self.assertNotIn(forbidden, source)

    def test_output_layer_is_independent_of_detection_and_runtime(self) -> None:
        self.assertEqual(
            forbidden_import_edges(("x5crop.output",), ("x5crop.detection", "x5crop.runtime")),
            [],
        )

    def test_report_debug_and_output_do_not_resolve_configuration_registry(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (
                PROJECT_ROOT / "x5crop/report",
                PROJECT_ROOT / "x5crop/debug",
                PROJECT_ROOT / "x5crop/output",
            )
            for path in root.rglob("*.py")
        )
        self.assertNotIn("get_detection_configuration", source)
        self.assertNotIn("DetectionConfigurationBundle.for_format_mode", source)

    def test_report_only_reads_assessed_candidate_results(self) -> None:
        source = (PROJECT_ROOT / "x5crop/report/read_models.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("detection.candidate.assessment", source)
        self.assertNotIn("quality_for_candidate", source)
        self.assertFalse(
            (
                PROJECT_ROOT
                / "x5crop/detection/candidate/assessment/quality.py"
            ).exists()
        )

    def test_report_validation_only_validates_serialized_facts(self) -> None:
        source = (PROJECT_ROOT / "x5crop/report/validation.py").read_text(
            encoding="utf-8"
        )
        for runtime_factory in (
            "decision_gate_matches_inputs",
            "finalization_plan_for_selection",
            "apply_frame_bleed",
        ):
            with self.subTest(runtime_factory=runtime_factory):
                self.assertNotIn(runtime_factory, source)


if __name__ == "__main__":
    unittest.main()
