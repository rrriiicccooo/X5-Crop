from __future__ import annotations

from pathlib import Path
import tempfile
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
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.io.tiff import read_tiff
from x5crop.run_status import RunTerminalOutcome


def _full_135_pixels(height: int = 100, width: int = 720) -> np.ndarray:
    pixels = np.zeros((height, width), dtype=np.uint8)
    for ordinal in range(6):
        start = 9 + ordinal * 117
        pixels[14:86, start : start + 112] = 180
    return pixels


def _fixture(
    root: Path,
):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "135.tif"
    tifffile.imwrite(
        source,
        _full_135_pixels(),
        photometric="minisblack",
    )
    array, profile, _warnings = read_tiff(source, 0)
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
    return configuration, workspace, detection


class DebugAnalysisContractTest(unittest.TestCase):
    def test_four_authority_panels_and_one_status_bar_are_current(self) -> None:
        self.assertEqual(
            DEBUG_ANALYSIS_PANEL_LABELS,
            (
                "Source-coordinate gray and lane authority",
                "Raw boundary evidence and shared direction",
                "Canonical format placement and retained union",
                "Continuous safe output geometry and budget",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            configuration, workspace, detection = _fixture(
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
                    configuration.diagnostics,
                    DebugRenderCache(),
                    RunTerminalOutcome.COMPLETED,
                )
        self.assertEqual(status.call_count, 1)
        self.assertEqual(panel.ndim, 3)
        self.assertEqual(panel.shape[2], 3)
        self.assertGreater(panel.shape[0], workspace.source_gray.shape[0] * 4)

    def test_output_panel_reads_saved_placement_and_constrained_footprints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, workspace, detection = _fixture(
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

    def test_review_keeps_candidate_audit_without_official_output_geometry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, workspace, detection = _fixture(
                Path(temporary)
            )
            with (
                mock.patch(
                    "x5crop.debug.panels._fill_polygon"
                ) as fill,
                mock.patch(
                    "x5crop.debug.panels._labeled",
                    side_effect=lambda rgb, label, _style: rgb,
                ) as labeled,
            ):
                _protected_output_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
            with mock.patch(
                "x5crop.debug.panels._labeled",
                side_effect=lambda rgb, label, _style: rgb,
            ) as selected_labeled:
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
        self.assertIn("NOT EXPORTABLE", labeled.call_args.args[1])
        self.assertIn(
            "candidate audit only - NOT EXPORTABLE",
            selected_labeled.call_args.args[1],
        )

    def test_fixed_palette_and_panel_stacking_are_bounded(self) -> None:
        self.assertEqual(len(FRAME_FILL_COLORS), 12)
        self.assertEqual(len(set(FRAME_FILL_COLORS)), 12)
        style = DebugStyleParameters()
        panels = tuple(
            np.zeros((4, 5, 3), dtype=np.uint8)
            for _ in range(4)
        )
        vertical = stack_debug_panels(
            panels,
            horizontal=False,
            style=style,
        )
        horizontal = stack_debug_panels(
            panels,
            horizontal=True,
            style=style,
        )
        self.assertEqual(
            vertical.shape[:2],
            (16 + style.panel_spacing * 3, 5),
        )
        self.assertEqual(
            horizontal.shape[:2],
            (4, 20 + style.panel_spacing * 3),
        )


if __name__ == "__main__":
    unittest.main()
