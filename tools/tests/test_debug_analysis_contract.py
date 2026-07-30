from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image
import tifffile

from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.diagnostics import DebugStyleParameters
from x5crop.detection.candidate.assessment.model import (
    CandidateGateAssessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.grid.model import GridCandidateKind
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.io.tiff import read_tiff
from x5crop.run_config import RunConfig
from x5crop.run_status import RunTerminalOutcome
from x5crop.runtime.outcome import CompletedInput
from x5crop.runtime.workflow import process_one
from x5crop.debug.canvas import (
    FRAME_FILL_COLORS,
    DebugRenderCache,
    draw_preview_vertical_line,
    fill_preview_rect,
)
from x5crop.debug.panels import (
    DEBUG_ANALYSIS_PANEL_LABELS,
    _frame_outputs_panel,
    make_debug_analysis_panel,
    separator_debug_line_plan,
    stack_debug_panels,
)


def _full_135_pixels(height: int = 100, width: int = 720) -> np.ndarray:
    rng = np.random.default_rng(9)
    pixels = rng.integers(20, 230, size=(height, width), dtype=np.uint8)
    for boundary in (
        9,
        121,
        127,
        239,
        245,
        357,
        363,
        475,
        481,
        593,
        599,
        711,
    ):
        pixels[:, max(0, boundary - 1) : min(width, boundary + 1)] = (
            0 if boundary % 2 else 255
        )
    return pixels


def _fixture(
    root: Path,
    pixels: np.ndarray,
    *,
    format_id: str = "135",
    strip_mode: str = "full",
    requested_count: int | None = None,
    force_review: bool = False,
):
    root.mkdir(parents=True, exist_ok=True)
    source = root / f"{format_id}.tif"
    tifffile.imwrite(source, pixels, photometric="minisblack")
    array, profile, _warnings = read_tiff(source, 0)
    bundle = DetectionConfigurationBundle.for_format_mode(
        format_id,
        strip_mode,
        requested_count,
    )
    configuration = bundle.initial_configuration
    lane_configuration = (
        None
        if configuration.physical_spec.layout.lane_format_id is None
        else bundle.configuration_for(
            configuration.physical_spec.layout.lane_format_id,
            "full",
        )
    )
    workspace = prepare_detection_workspace(
        array,
        profile,
        "horizontal",
        configuration,
        lane_configuration,
    )
    candidate = choose_detection(
        workspace,
        configuration,
        lane_configuration,
    )
    if force_review:
        checks = list(candidate.gate.checks)
        checks[-1] = replace(
            checks[-1],
            state=EvidenceState.CONTRADICTED,
        )
        gate = CandidateGateAssessment(tuple(checks))
        candidate = replace(candidate, gate=gate)
    decision = apply_decision_gate(
        candidate.gate,
        configuration.count_request.mode,
    )
    detection = finalize_detection(
        candidate,
        decision,
        layout="horizontal",
    )
    return source, bundle, configuration, workspace, detection


def _run_config(
    source: Path,
    output: Path,
    configuration,
    *,
    debug_analysis: bool,
    diagnostics: bool = False,
) -> RunConfig:
    return RunConfig(
        input_path=source,
        output_dir=output,
        format_id=configuration.physical_spec.format_id,
        layout_auto=False,
        layout="horizontal",
        strip_mode=configuration.strip_mode,
        count_request=configuration.count_request,
        page=0,
        review_dir=None,
        copy_review_files=False,
        compression="same",
        debug_analysis=debug_analysis,
        diagnostics=diagnostics,
        overwrite=False,
        report=diagnostics,
        debug_errors=True,
        jobs=1,
    )


class DebugAnalysisContractTest(unittest.TestCase):
    def test_three_panel_layout_uses_uncolored_canonical_gray_and_one_status_bar(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _source, _bundle, configuration, workspace, detection = _fixture(
                Path(temporary),
                _full_135_pixels(),
            )
        self.assertEqual(detection.decision.status, "approved_auto")
        style = configuration.diagnostics.style
        panel = make_debug_analysis_panel(
            workspace,
            detection,
            configuration.diagnostics,
            DebugRenderCache(),
            RunTerminalOutcome.COMPLETED,
        )
        gray = workspace.measurement_cache.gray_work
        expected_gray = np.repeat(gray[..., None], 3, axis=2)
        image_top = style.status_bar_height + style.label_height
        self.assertTrue(
            np.array_equal(
                panel[
                    image_top : image_top + gray.shape[0],
                    : gray.shape[1],
                ],
                expected_gray,
            )
        )
        expected_height = (
            style.status_bar_height
            + (gray.shape[0] + style.label_height) * 2
            + (
                gray.shape[0]
                + style.label_height
                + style.legend_row_height * 4
            )
            + style.panel_spacing * 2
        )
        self.assertEqual(panel.shape[:2], (expected_height, gray.shape[1]))
        self.assertEqual(
            DEBUG_ANALYSIS_PANEL_LABELS,
            (
                "Original gray context",
                "Frame outputs",
                "Separator evidence",
            ),
        )

    def test_approved_uses_final_protected_boxes_and_review_is_provisional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, configuration, workspace, approved = _fixture(
                root / "approved",
                _full_135_pixels(),
            )
            _, _, _, review_workspace, review = _fixture(
                root / "review",
                _full_135_pixels(),
                force_review=True,
            )
        style = configuration.diagnostics.style
        with mock.patch(
            "x5crop.debug.panels.fill_preview_rect"
        ) as approved_fill:
            _frame_outputs_panel(
                workspace,
                approved,
                style,
                DebugRenderCache(),
            )
        self.assertEqual(
            tuple(call.args[1] for call in approved_fill.call_args_list),
            tuple(
                envelope.protected_work_box
                for envelope in approved.protected_envelopes
            ),
        )
        self.assertTrue(approved.final_boxes)

        with (
            mock.patch(
                "x5crop.debug.panels.fill_preview_rect"
            ) as review_fill,
            mock.patch(
                "x5crop.debug.panels.draw_preview_label"
            ) as review_label,
        ):
            _frame_outputs_panel(
                review_workspace,
                review,
                style,
                DebugRenderCache(),
            )
        expected_provisional = tuple(
            envelope.work_box
            for selection in review.candidate.lane_selections
            if selection.selected_proposal is not None
            for envelope in selection.selected_proposal.safe_envelopes
        )
        self.assertEqual(review.final_boxes, ())
        self.assertEqual(review.protected_envelopes, ())
        self.assertEqual(
            tuple(call.args[1] for call in review_fill.call_args_list),
            expected_provisional,
        )
        self.assertTrue(
            all(
                call.args[4] == style.provisional_frame_fill_alpha
                for call in review_fill.call_args_list
            )
        )
        self.assertTrue(
            all(
                "PROVISIONAL" in call.args[3]
                for call in review_label.call_args_list
            )
        )

    def test_fixed_palette_maps_global_dual_lane_ordinals_without_repetition(
        self,
    ) -> None:
        self.assertEqual(len(FRAME_FILL_COLORS), 12)
        self.assertEqual(len(set(FRAME_FILL_COLORS)), 12)
        self.assertEqual(
            FRAME_FILL_COLORS[8:],
            (
                (180, 120, 60),
                (120, 220, 60),
                (255, 160, 190),
                (70, 110, 210),
            ),
        )
        style = DebugStyleParameters()
        self.assertEqual(style.frame_fill_alpha, 0.26)
        rng = np.random.default_rng(17)
        pixels = rng.integers(0, 256, size=(200, 732), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, workspace, detection = _fixture(
                Path(temporary),
                pixels,
                format_id="135-dual",
            )
        with (
            mock.patch(
                "x5crop.debug.panels.fill_preview_rect"
            ) as fill,
            mock.patch(
                "x5crop.debug.panels.draw_preview_label"
            ) as label,
        ):
            _frame_outputs_panel(
                workspace,
                detection,
                style,
                DebugRenderCache(),
            )
        self.assertEqual(
            tuple(call.args[3] for call in fill.call_args_list),
            FRAME_FILL_COLORS,
        )
        self.assertEqual(
            tuple(call.args[3] for call in label.call_args_list),
            tuple(f"F{index}" for index in range(1, 13)),
        )

    def test_all_raw_separator_lines_and_last_selected_observation_are_drawn(
        self,
    ) -> None:
        raw_lines = tuple(
            SimpleNamespace(
                boundary_px=float(index),
                observation_id=f"line:{index}",
            )
            for index in range(257)
        )
        observation = SimpleNamespace(
            source_line_ids=("line:0", "line:256")
        )
        selected = SimpleNamespace(
            corridor_candidates=(
                SimpleNamespace(
                    kind=GridCandidateKind.OBSERVED_EDGE_PAIR,
                    observation=observation,
                    previous_photo_end_px=FiniteInterval.exact(0.0),
                    next_photo_start_px=FiniteInterval.exact(256.0),
                ),
            )
        )
        style = DebugStyleParameters()
        plan = separator_debug_line_plan(
            Box(0, 0, 300, 20),
            raw_lines,
            selected,
            style,
        )
        self.assertEqual(
            sum(line.selected_kind is None for line in plan),
            257,
        )
        self.assertEqual(plan[-1].observation_id, "line:256")
        self.assertEqual(
            plan[-1].selected_kind,
            GridCandidateKind.OBSERVED_EDGE_PAIR,
        )
        self.assertEqual(plan[-1].color, style.selected_edge_pair_color)
        rgb = np.full((20, 300, 3), 100, dtype=np.uint8)
        for line in plan:
            draw_preview_vertical_line(
                rgb,
                line.x,
                line.top,
                line.bottom,
                1.0,
                line.color,
                line.thickness,
                alpha=line.alpha,
                dashed=line.dashed,
            )
        self.assertEqual(
            tuple(rgb[10, 256]),
            style.selected_edge_pair_color,
        )

    def test_one_sided_and_model_only_separator_styles_are_distinct(
        self,
    ) -> None:
        style = DebugStyleParameters()
        raw = (
            SimpleNamespace(
                boundary_px=20.0,
                observation_id="line:selected",
            ),
        )
        selected = SimpleNamespace(
            corridor_candidates=(
                SimpleNamespace(
                    kind=GridCandidateKind.OBSERVED_ONE_SIDED,
                    observation=SimpleNamespace(
                        source_line_ids=("line:selected",)
                    ),
                    previous_photo_end_px=FiniteInterval.exact(20.0),
                    next_photo_start_px=FiniteInterval.exact(30.0),
                ),
                SimpleNamespace(
                    kind=GridCandidateKind.MODEL_ONLY,
                    observation=None,
                    previous_photo_end_px=FiniteInterval.exact(50.0),
                    next_photo_start_px=FiniteInterval.exact(60.0),
                ),
            )
        )
        selected_lines = tuple(
            line
            for line in separator_debug_line_plan(
                Box(0, 0, 100, 20),
                raw,
                selected,
                style,
            )
            if line.selected_kind is not None
        )
        self.assertEqual(
            tuple(line.selected_kind for line in selected_lines),
            (
                GridCandidateKind.OBSERVED_ONE_SIDED,
                GridCandidateKind.MODEL_ONLY,
                GridCandidateKind.MODEL_ONLY,
            ),
        )
        self.assertFalse(selected_lines[0].dashed)
        self.assertEqual(
            selected_lines[0].color,
            style.selected_one_sided_color,
        )
        self.assertTrue(all(line.dashed for line in selected_lines[1:]))
        self.assertTrue(
            all(
                line.color == style.selected_model_only_color
                for line in selected_lines[1:]
            )
        )

    def test_panel_stacking_covers_landscape_portrait_and_overlap(self) -> None:
        style = DebugStyleParameters()
        panels = tuple(
            np.zeros((4, 5, 3), dtype=np.uint8)
            for _ in range(3)
        )
        landscape = stack_debug_panels(
            panels,
            horizontal=False,
            style=style,
        )
        portrait = stack_debug_panels(
            panels,
            horizontal=True,
            style=style,
        )
        self.assertEqual(
            landscape.shape[:2],
            (4 * 3 + style.panel_spacing * 2, 5),
        )
        self.assertEqual(
            portrait.shape[:2],
            (4, 5 * 3 + style.panel_spacing * 2),
        )
        rgb = np.zeros((10, 20, 3), dtype=np.uint8)
        fill_preview_rect(
            rgb,
            Box(0, 0, 14, 10),
            1.0,
            FRAME_FILL_COLORS[0],
            style.frame_fill_alpha,
        )
        first_only = rgb[5, 5].copy()
        fill_preview_rect(
            rgb,
            Box(6, 0, 20, 10),
            1.0,
            FRAME_FILL_COLORS[1],
            style.frame_fill_alpha,
        )
        self.assertFalse(np.array_equal(rgb[5, 10], first_only))
        self.assertFalse(np.array_equal(rgb[5, 10], rgb[5, 5]))

    def test_runtime_writes_only_requested_three_panel_debug_analysis(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, bundle, configuration, _workspace, _detection = _fixture(
                root / "fixture",
                _full_135_pixels(),
            )
            ordinary_root = root / "ordinary"
            ordinary = process_one(
                source,
                _run_config(
                    source,
                    ordinary_root,
                    configuration,
                    debug_analysis=False,
                ),
                bundle,
            )
            self.assertIsInstance(ordinary, CompletedInput)
            assert isinstance(ordinary, CompletedInput)
            self.assertIsNone(ordinary.artifacts.debug_analysis)
            self.assertFalse((ordinary_root / "_debug").exists())
            self.assertFalse((ordinary_root / "_debug_analysis").exists())

            analysis_root = root / "analysis"
            analysis = process_one(
                source,
                _run_config(
                    source,
                    analysis_root,
                    configuration,
                    debug_analysis=True,
                ),
                bundle,
            )
            self.assertIsInstance(analysis, CompletedInput)
            assert isinstance(analysis, CompletedInput)
            analysis_path = Path(str(analysis.artifacts.debug_analysis))
            self.assertTrue(analysis_path.is_file())
            self.assertEqual(analysis_path.parent.name, "_debug_analysis")
            self.assertFalse((analysis_root / "_debug").exists())
            with Image.open(analysis_path) as image:
                self.assertEqual(image.format, "JPEG")

            diagnostics_root = root / "diagnostics"
            diagnostics = process_one(
                source,
                _run_config(
                    source,
                    diagnostics_root,
                    configuration,
                    debug_analysis=True,
                    diagnostics=True,
                ),
                bundle,
            )
            self.assertIsInstance(diagnostics, CompletedInput)
            assert isinstance(diagnostics, CompletedInput)
            self.assertTrue(
                Path(str(diagnostics.artifacts.debug_analysis)).is_file()
            )
            self.assertEqual(diagnostics.artifacts.frame_outputs, ())
            self.assertFalse((diagnostics_root / "_debug").exists())


if __name__ == "__main__":
    unittest.main()
