from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import tifffile

from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.diagnostics import DebugStyleParameters
from x5crop.debug.canvas import FRAME_FILL_COLORS, DebugRenderCache
from x5crop.debug.panels import (
    DEBUG_ANALYSIS_PANEL_LABELS,
    _protected_output_panel,
    _selected_geometry_panel,
    make_debug_analysis_panel,
    stack_debug_panels,
)
from x5crop.debug.status import _transform_lines
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.io.tiff import read_tiff
from x5crop.run_status import RunTerminalOutcome


def _full_135_pixels(height: int = 100, width: int = 720) -> np.ndarray:
    pixels = np.zeros((height, width, 3), dtype=np.uint16)
    for ordinal in range(6):
        start = 9 + ordinal * 117
        pixels[14:86, start : start + 112, :] = 46_000
    return pixels


def _fixture(
    root: Path,
):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "135.tif"
    tifffile.imwrite(
        source,
        _full_135_pixels(),
        photometric="rgb",
        planarconfig="contig",
    )
    array, profile, _warnings = read_tiff(source)
    bundle = DetectionConfigurationBundle.for_format_mode(
        "135",
        "partial",
    )
    configuration = bundle.initial_configuration
    workspace = prepare_detection_workspace(
        array,
        profile,
        "horizontal",
        configuration,
        None,
    )
    candidate = choose_detection(workspace, configuration, None)
    decision = apply_decision_gate(
        candidate.gate,
        configuration.count_request.mode,
    )
    detection = finalize_detection(
        candidate,
        decision,
        layout="horizontal",
    )
    return configuration, profile, workspace, detection


class DebugAnalysisContractTest(unittest.TestCase):
    def test_three_panels_preserve_four_v5_fact_layers(self) -> None:
        self.assertEqual(
            DEBUG_ANALYSIS_PANEL_LABELS,
            (
                "01 · SOURCE & OBSERVED EVIDENCE",
                "02 · RETAINED PLACEMENTS & CANONICAL",
                "03 · SAFE OUTPUT & DIRECT-USE BUDGET",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            configuration, profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with mock.patch(
                "x5crop.debug.panels.add_status_bar",
                wraps=__import__(
                    "x5crop.debug.panels",
                    fromlist=["add_status_bar"],
                ).add_status_bar,
            ) as status:
                panel = make_debug_analysis_panel(
                    workspace,
                    detection,
                    configuration,
                    profile,
                    configuration.diagnostics,
                    DebugRenderCache(),
                    RunTerminalOutcome.NEEDS_REVIEW,
                )
        self.assertEqual(status.call_count, 1)
        style = configuration.diagnostics.style
        self.assertEqual(
            panel.shape,
            (style.canvas_height, style.canvas_width, 3),
        )

    def test_output_panel_reads_saved_placement_and_constrained_footprints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with mock.patch(
                "x5crop.debug.panels._fill_polygon"
            ) as fill:
                _protected_output_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
        self.assertFalse(detection.frame_export_eligible)
        self.assertEqual(
            tuple(call.args[1] for call in fill.call_args_list),
            tuple(
                footprint
                for geometry in (
                    detection.candidate.geometry.safe_crop_envelopes
                )
                for footprint in (
                    geometry.placement_source_footprint,
                    geometry.constrained_source_footprint,
                )
            ),
        )

    def test_retained_panel_draws_every_complete_retained_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            expected_frame_count = sum(
                len(placement.canonical.frames)
                for lane in detection.candidate.geometry.lane_reconstructions
                for placement in lane.retained_placements
            )
            with mock.patch(
                "x5crop.debug.panels._draw_dashed_polyline"
            ) as retained_line:
                _selected_geometry_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
        self.assertGreater(expected_frame_count, 0)
        self.assertEqual(retained_line.call_count, expected_frame_count)

    def test_review_keeps_candidate_audit_without_official_output_geometry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with (
                mock.patch(
                    "x5crop.debug.panels._fill_polygon"
                ) as fill,
                mock.patch(
                    "x5crop.debug.panels._panel_base",
                    wraps=__import__(
                        "x5crop.debug.panels",
                        fromlist=["_panel_base"],
                    )._panel_base,
                ) as output_base,
            ):
                _protected_output_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
            with mock.patch(
                "x5crop.debug.panels._panel_base",
                wraps=__import__(
                    "x5crop.debug.panels",
                    fromlist=["_panel_base"],
                )._panel_base,
            ) as selected_base:
                _selected_geometry_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
        self.assertEqual(detection.decision.status, "needs_review")
        self.assertFalse(detection.frame_export_eligible)
        self.assertEqual(detection.resolved_output_geometries, ())
        self.assertGreater(fill.call_count, 0)
        self.assertEqual(
            output_base.call_args.args[3],
            "CANDIDATE AUDIT · NOT EXPORTABLE",
        )
        self.assertIn(
            "CANONICAL · REPRESENTATIVE ONLY",
            selected_base.call_args.args[3],
        )

    def test_fixed_palette_and_panel_stacking_are_bounded(self) -> None:
        self.assertEqual(len(FRAME_FILL_COLORS), 12)
        self.assertEqual(len(set(FRAME_FILL_COLORS)), 12)
        style = DebugStyleParameters()
        width = style.canvas_width - style.outer_margin * 2
        panels = tuple(
            np.zeros((height, width, 3), dtype=np.uint8)
            for height in (
                style.source_panel_height,
                style.retained_panel_height,
                style.output_panel_height,
            )
        )
        body = stack_debug_panels(panels, style=style)
        self.assertEqual(
            body.shape,
            (
                style.canvas_height
                - style.status_bar_height
                - style.legend_bar_height,
                style.canvas_width,
                3,
            ),
        )

    def test_header_keeps_actual_deskew_angle_and_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _configuration, profile, _workspace, detection = _fixture(
                Path(temporary)
            )
        assessment = SimpleNamespace(
            outcome="shared_rotation",
            applied_source_rotation_degrees=-0.153,
            observed_angle_interval_degrees=(
                detection.transform_assessment.observed_angle_interval_degrees
            ),
        )
        applied = SimpleNamespace(transform_assessment=assessment)
        first, second = _transform_lines(applied, profile)
        self.assertEqual(first, "V5 · DESKEW APPLIED -0.153°")
        self.assertIn("observed -0.166°…+0.166°", second)
        self.assertIn("ORIENTATION 1>CANONICAL>1", second)

    def test_raw_transition_is_visible_but_secondary(self) -> None:
        style = DebugStyleParameters()
        self.assertGreater(sum(style.raw_transition_color), 600)
        self.assertLess(
            sum(style.raw_transition_color),
            sum(style.retained_color),
        )


if __name__ == "__main__":
    unittest.main()
