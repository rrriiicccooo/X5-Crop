from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import get_type_hints
import unittest

import numpy as np

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.configuration.diagnostics import (
    DebugStyleParameters,
    DiagnosticsConfiguration,
    SeparatorOverlayParameters,
)
from x5crop.debug import canvas as debug_canvas
from x5crop.debug.panels import make_separator_evidence_debug_rgb
from x5crop.debug.separators import draw_separator_overlay
from x5crop.detection.gate_checks import GateCheck
from x5crop.domain import Box, MeasurementProvenance, SeparatorBandObservation
from x5crop.io.model import ImageProfile
from x5crop.output.model import FrameBleedPlan
from x5crop.report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from x5crop.report.read_models import (
    frame_bleed_plan_read_model,
    gate_check_read_model,
)


def _active_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
    )


class CurrentSchemaNamingContractTest(unittest.TestCase):
    def test_report_read_models_have_no_constructor_or_projection_wrappers(self) -> None:
        finalize = (
            PROJECT_ROOT / "x5crop/detection/final/finalize.py"
        ).read_text(encoding="utf-8")
        restoration = (
            PROJECT_ROOT / "x5crop/report/restoration.py"
        ).read_text(encoding="utf-8")
        read_models = (
            PROJECT_ROOT / "x5crop/report/read_models.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("final_detection_from_facts", finalize)
        self.assertNotIn("final_detection_from_facts", restoration)
        self.assertNotIn("candidate_evidence_read_model", read_models)

    def test_known_report_and_debug_interfaces_use_canonical_types(self) -> None:
        self.assertIs(
            get_type_hints(make_separator_evidence_debug_rgb)["separator_overlay"],
            SeparatorOverlayParameters,
        )
        self.assertIs(
            get_type_hints(draw_separator_overlay)["overlay"],
            SeparatorOverlayParameters,
        )
        self.assertIs(
            get_type_hints(gate_check_read_model)["check"],
            GateCheck,
        )
        self.assertIs(
            get_type_hints(frame_bleed_plan_read_model)["plan"],
            FrameBleedPlan,
        )

    def test_tiff_profile_is_an_immutable_typed_input_contract(self) -> None:
        self.assertTrue(ImageProfile.__dataclass_params__.frozen)
        self.assertFalse(
            any(
                "Any" in str(field.type)
                for field in ImageProfile.__dataclass_fields__.values()
            )
        )

    def test_separator_measurement_has_one_count_independent_identity(self) -> None:
        self.assertEqual(
            tuple(SeparatorBandObservation.__dataclass_fields__),
            (
                "start",
                "end",
                "tonal_evidence",
                "appearance",
                "provenance",
            ),
        )
        self.assertTrue(SeparatorBandObservation.__dataclass_params__.frozen)
        self.assertEqual(
            tuple(MeasurementProvenance.__dataclass_fields__),
            (
                "root_measurement",
                "observation_id",
                "dependencies",
                "description",
                "boundary_anchors",
            ),
        )

    def test_debug_legend_is_derived_from_canonical_diagnostics_style(self) -> None:
        diagnostics = DiagnosticsConfiguration()

        self.assertEqual(
            tuple(entry.label for entry in diagnostics.legend_entries),
            (
                "Holder boundary",
                "Raw observation",
                "Measured aperture / separator edge",
                "Dimension-only provisional edge",
                "Corroborated overlap",
                "PhotoAperture",
                "FrameCropEnvelope / protected output",
            ),
        )
        self.assertEqual(
            tuple(entry.dashed for entry in diagnostics.legend_entries),
            (True, False, False, True, False, False, True),
        )
        self.assertEqual(
            tuple(entry.color for entry in diagnostics.legend_entries),
            (
                diagnostics.style.holder_boundary_color,
                diagnostics.style.raw_observation_color,
                diagnostics.style.measured_boundary_color,
                diagnostics.style.dimension_hypothesis_color,
                diagnostics.style.corroborated_overlap_color,
                diagnostics.style.photo_aperture_color,
                diagnostics.style.frame_crop_envelope_color,
            ),
        )

    def test_debug_style_has_only_current_physical_overlay_names(self) -> None:
        fields = set(DebugStyleParameters.__dataclass_fields__)

        self.assertNotIn("crop_envelope_color", fields)
        self.assertNotIn("frame_output_color", fields)
        self.assertNotIn("accepted_separator_color", fields)
        self.assertNotIn("unselected_separator_color", fields)
        self.assertNotIn("overlap_boundary_color", fields)
        self.assertNotIn("dimension_boundary_color", fields)
        self.assertTrue(
            {
                "photo_aperture_color",
                "frame_crop_envelope_color",
                "measured_boundary_color",
                "raw_observation_color",
                "corroborated_overlap_color",
                "dimension_hypothesis_color",
            }.issubset(fields)
        )

    def test_debug_line_renderer_preserves_both_axis_orientations(self) -> None:
        vertical = np.zeros((12, 12, 3), dtype=np.uint8)
        horizontal = np.zeros((12, 12, 3), dtype=np.uint8)

        debug_canvas.draw_preview_line(
            vertical, Box(5, 1, 6, 11), 1.0, (255, 0, 0), 1
        )
        debug_canvas.draw_preview_line(
            horizontal, Box(1, 5, 11, 6), 1.0, (255, 0, 0), 1
        )

        self.assertEqual(np.count_nonzero(vertical[:, :, 0]), 10)
        self.assertEqual(np.count_nonzero(horizontal[:, :, 0]), 10)

    def test_debug_dashed_line_renderer_is_axis_symmetric(self) -> None:
        renderer = getattr(debug_canvas, "draw_preview_dashed_line", None)
        self.assertIsNotNone(renderer)
        vertical = np.zeros((24, 24, 3), dtype=np.uint8)
        horizontal = np.zeros((24, 24, 3), dtype=np.uint8)

        renderer(
            vertical,
            Box(10, 2, 11, 22),
            1.0,
            (255, 0, 0),
            1,
            dash_length=3,
            dash_gap=2,
        )
        renderer(
            horizontal,
            Box(2, 10, 22, 11),
            1.0,
            (255, 0, 0),
            1,
            dash_length=3,
            dash_gap=2,
        )

        vertical_pixels = np.count_nonzero(vertical[:, :, 0])
        horizontal_pixels = np.count_nonzero(horizontal[:, :, 0])
        self.assertEqual(vertical_pixels, horizontal_pixels)
        self.assertGreater(vertical_pixels, 0)
        self.assertLess(vertical_pixels, 20)

    def test_debug_line_renderer_keeps_subpixel_source_edges_visible(self) -> None:
        vertical = np.zeros((12, 12, 3), dtype=np.uint8)
        horizontal = np.zeros((12, 12, 3), dtype=np.uint8)

        debug_canvas.draw_preview_line(
            vertical, Box(50, 10, 51, 110), 0.1, (255, 0, 0), 1
        )
        debug_canvas.draw_preview_line(
            horizontal, Box(10, 50, 110, 51), 0.1, (255, 0, 0), 1
        )

        self.assertGreater(np.count_nonzero(vertical[:, :, 0]), 0)
        self.assertGreater(np.count_nonzero(horizontal[:, :, 0]), 0)

    def test_debug_never_reconstructs_apertures_from_output_envelopes(self) -> None:
        source = (PROJECT_ROOT / "x5crop/debug/panels.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "item.box for item in final_geometry.frame_crop_envelopes",
            source,
        )

    def test_removed_gap_grid_and_correction_vocabularies_are_absent(self) -> None:
        source = _active_source()
        for forbidden in (
            "HARD_GAP_METHODS",
            "MODEL_GAP_METHODS",
            "equal_model_gap",
            "stable_grid",
            "separator_width_profile",
            "outer_correction",
            "approved_geometry_adjustment",
            "candidate_is_reliable_for_execution_budget",
        ):
            self.assertNotIn(forbidden, source)

    def test_removed_modules_do_not_exist(self) -> None:
        for relative in (
            "x5crop/gap_methods.py",
            "x5crop/geometry/model_gaps.py",
            "x5crop/geometry/gap_search.py",
            "x5crop/geometry/separator_width_profile.py",
            "x5crop/detection/physical/outer",
            "x5crop/detection/candidate/extension",
        ):
            self.assertFalse((PROJECT_ROOT / relative).exists(), relative)

    def test_content_is_guidance_not_a_candidate_source(self) -> None:
        source = _active_source()
        self.assertNotIn("CANDIDATE_SOURCE_CONTENT", source)
        self.assertFalse(
            (PROJECT_ROOT / "x5crop/detection/candidate/build/content.py").exists()
        )

    def test_configuration_identity_uses_plain_canonical_format_id(self) -> None:
        from x5crop.formats import FORMATS
        from x5crop.configuration.registry import get_detection_configuration

        for format_id in FORMATS:
            self.assertEqual(
                get_detection_configuration(
                    format_id,
                    "full",
                ).configuration_id,
                f"detection:{format_id}:full",
            )

    def test_format_names_do_not_branch_detection_algorithms(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                text = ast.unparse(node)
                if "format_id" in text and any(
                    token in text for token in ("135", "half", "120-66", "120-67", "xpan")
                ):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_report_schema_identity_is_descriptive(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "detection_report")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "photo_aperture_sequence_resolution",
        )
        self.assertNotIn("v4", REPORT_SCHEMA_REVISION)

    def test_active_source_uses_configuration_and_parameter_vocabulary(self) -> None:
        source = _active_source()
        self.assertNotRegex(source, r"\b[A-Za-z_]*[Pp]olicy[A-Za-z_]*\b")
        self.assertNotIn("profile_config", source)

    def test_report_schema_identity_is_owned_by_report_layer(self) -> None:
        owners = [
            path
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
            if "REPORT_SCHEMA_REVISION =" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            [path.relative_to(PROJECT_ROOT).as_posix() for path in owners],
            ["x5crop/report/identity.py"],
        )

    def test_current_schema_has_no_legacy_reason_field(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (PROJECT_ROOT / "x5crop/report", PROJECT_ROOT / "x5crop/debug")
            for path in root.rglob("*.py")
        )
        self.assertNotIn('"review_reasons"', source)
        self.assertIn("final_review_reasons", source)

    def test_active_detection_has_no_generic_outer_identity(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py")
        )
        self.assertNotIn("OuterProposal", source)
        self.assertNotIn("FilmSpan", source)

    def test_current_coordination_and_test_fixtures_use_aperture_vocabulary(self) -> None:
        removed_terms = (
            "film" + "_span_overcontains_holder_area",
            "independent_" + "outer_and_separator_measurements",
            "synthetic_" + "outer",
        )
        test_offenders = [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in (PROJECT_ROOT / "tools/tests").glob("*.py")
            if path != Path(__file__)
            and any(
                removed in path.read_text(encoding="utf-8")
                for removed in removed_terms
            )
        ]
        self.assertEqual(test_offenders, [])

        coordination = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for removed in (
            "outer" + "_box",
            "Film" + "Span",
            "physical" + "_resolution",
        ):
            self.assertNotIn(removed, coordination)
        self.assertNotIn("`SequenceSolution`", coordination)
        self.assertNotIn("gray_sequence_integrity", coordination)
        self.assertIn("`PhotoSequenceSolution`", coordination)
        self.assertIn("photo_aperture_sequence_resolution", coordination)

        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Boundary、Sequence 与 Outer", architecture)
        self.assertNotIn("旧 generic outer", architecture)
        self.assertNotIn("`VisibleSequenceSpan`", architecture)
        self.assertNotIn("`SequenceSolution`", architecture)
        self.assertNotIn("`CropEnvelope`", architecture)
        self.assertIn("`PhotoAperture`", architecture)
        self.assertIn("`PhotoSequenceSolution`", architecture)
        self.assertIn("photo_aperture_sequence_resolution", architecture)

    def test_user_docs_describe_current_sequence_and_bleed_model(self) -> None:
        quick_start = (PROJECT_ROOT / "快速启动_Quick_Start.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("检查外框", quick_start)
        self.assertNotIn("inspect the outer box", quick_start)

        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("可用容量由可信 scan calibration", readme)
        self.assertNotIn(
            "Capacity is resolved from trusted scan calibration",
            readme,
        )
        self.assertNotRegex(readme, r"(?<!Frame)\bCropEnvelope\b")
        self.assertIn("PhotoAperture", readme)
        self.assertIn("FrameCropEnvelope", readme)
        for legend_label in (
            "Holder boundary",
            "Raw observation",
            "Measured aperture / separator edge",
            "Dimension-only provisional edge",
            "Corroborated overlap",
            "PhotoAperture",
            "FrameCropEnvelope / protected output",
        ):
            self.assertIn(legend_label, readme)
        for stale in (
            "observed-width evidence",
            "content position",
            "order count hypotheses",
            "five fixed offsets",
            "between each base frame and its `CropEnvelope`",
        ):
            self.assertNotIn(stale, readme)

        candidate_plan = (
            PROJECT_ROOT / "x5crop/detection/candidate/plan/__init__.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("offset", candidate_plan)
        self.assertNotIn("source descriptors", candidate_plan)

    def test_content_guidance_cannot_create_or_replace_sequence_geometry(self) -> None:
        guidance = PROJECT_ROOT / "x5crop/detection/evidence/content"
        self.assertTrue(tuple(guidance.glob("*.py")))
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in guidance.glob("*.py")
        )
        self.assertNotIn("SequenceHypothesis.from_box_hypothesis", source)
        self.assertNotIn("visible_sequence_span=", source)
        self.assertFalse((guidance / "content_sequence_edge.py").exists())
        self.assertFalse((guidance / "content_sequence_floating.py").exists())
        active_detection = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py")
        )
        self.assertNotIn('"content_' + 'guidance"', active_detection)

    def test_docs_launchers_and_contracts_use_current_runtime_truth(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        cli = (PROJECT_ROOT / "x5crop/entry/cli.py").read_text(encoding="utf-8")
        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
        coordination = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        ownership_test = (
            PROJECT_ROOT / "tools/tests/test_architecture_ownership_contract.py"
        ).read_text(encoding="utf-8")

        self.assertIn("All candidates pass CandidateGate", readme)
        self.assertIn("selected candidate then passes DecisionGate", readme)
        self.assertIn("resolved REVIEW crops", cli)
        self.assertIn("resolved REVIEW crops", readme)
        self.assertNotIn("PhotoSequenceSolver", architecture)
        self.assertNotIn("PhotoSequenceSolver", coordination)
        self.assertNotIn("PhotoSequenceEnvelope", architecture)
        self.assertIn("solve_photo_sequence", architecture)
        self.assertNotIn("splitlines()) > 800", ownership_test)

        for launcher in (
            "X5_Crop_Mac.command",
            "X5_Crop_Mac_diagnostics.command",
            "X5_Crop_win.bat",
        ):
            source = (PROJECT_ROOT / launcher).read_text(encoding="utf-8")
            with self.subTest(launcher=launcher):
                self.assertIn("imagecodecs", source)

    def test_active_source_docstrings_reference_existing_modules(self) -> None:
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for module_name in re.findall(r"`(x5crop(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)`", source):
                module_path = PROJECT_ROOT / (module_name.replace(".", "/") + ".py")
                package_path = PROJECT_ROOT / module_name.replace(".", "/") / "__init__.py"
                with self.subTest(source=str(path), module=module_name):
                    self.assertTrue(module_path.is_file() or package_path.is_file())

    def test_measurement_cache_has_no_single_use_key_wrapper(self) -> None:
        source = (PROJECT_ROOT / "x5crop/cache/separator.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("separator_profile_cache_key", source)

    def test_physical_candidate_source_is_frame_sequence_not_separator(self) -> None:
        source = _active_source()
        self.assertNotIn("SeparatorSequencePlan", source)
        self.assertNotIn("CANDIDATE_SOURCE_", source)

    def test_review_only_marker_is_described_without_payload(self) -> None:
        for name in ("AGENTS.md", "ARCHITECTURE.md"):
            document = (PROJECT_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(document=name):
                self.assertNotIn(
                    "review-only assessment stores only its unsupported reason",
                    document,
                )
                self.assertNotIn(
                    "review-only assessment 只保存明确的不可自动处理原因",
                    document,
                )

    def test_agents_grants_early_stop_only_to_geometry_resolution(self) -> None:
        agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("or typed execution-budget", agents)
        self.assertIn(
            "`GeometryResolution` is the only early-stop input",
            agents,
        )


if __name__ == "__main__":
    unittest.main()
