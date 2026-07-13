from __future__ import annotations

import ast
from pathlib import Path
from typing import get_type_hints
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from x5crop.configuration.diagnostics import SeparatorOverlayParameters
from x5crop.debug.panels import make_separator_evidence_debug_rgb
from x5crop.debug.separators import draw_separator_overlay
from x5crop.detection.gate_checks import GateCheck
from x5crop.domain import MeasurementProvenance, SeparatorBandObservation
from x5crop.io.model import ImageProfile
from x5crop.output.model import FrameBleedPlan
from x5crop.report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from x5crop.report.read_models import (
    frame_bleed_plan_read_model,
    gate_check_read_model,
    resolution_metadata_read_model,
)
from x5crop.units import ResolutionMetadataObservation


def _active_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
    )


class CurrentSchemaNamingContractTest(unittest.TestCase):
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
            get_type_hints(resolution_metadata_read_model)["metadata"],
            ResolutionMetadataObservation,
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
                "center",
                "tonal_evidence",
                "appearance",
                "provenance",
                "cross_axis_measurements",
                "lane_box",
            ),
        )
        self.assertTrue(SeparatorBandObservation.__dataclass_params__.frozen)
        self.assertEqual(
            tuple(MeasurementProvenance.__dataclass_fields__),
            ("root_measurement", "source", "dependencies", "boundary_anchors"),
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

    def test_current_coordination_and_test_fixtures_use_sequence_vocabulary(self) -> None:
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
        self.assertIn("gray_sequence_integrity", coordination)

        architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Boundary、Sequence 与 Outer", architecture)
        self.assertNotIn("旧 generic outer", architecture)

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
        self.assertIn("CropEnvelope", readme)
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
        guidance = PROJECT_ROOT / "x5crop/detection/guidance"
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
