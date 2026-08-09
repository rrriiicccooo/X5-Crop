from __future__ import annotations

import inspect
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tifffile

import x5crop.debug.panels as debug_panels
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.diagnostics import DebugStyleParameters
from x5crop.debug.canvas import FRAME_FILL_COLORS, DebugRenderCache
from x5crop.debug.panels import (
    DEBUG_ANALYSIS_PANEL_LABELS,
    _cross_axis_panel,
    _clip_segment_to_box,
    _draw_hatched_polygon,
    _keep_evidence_inside_media,
    _long_axis_panel,
    _Projection,
    _protected_output_panel,
    _viewport,
    make_debug_analysis_panel,
    stack_debug_panels,
)
from x5crop.debug.status import _fit_text, _source_header, _transform_lines
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
                "01 · CROSS-AXIS TOP / BOTTOM",
                "02 · LONG-AXIS START / END",
                "03 · FINAL SAFE OUTPUT",
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
                    "135.tif",
                    configuration.diagnostics,
                    DebugRenderCache(),
                    RunTerminalOutcome.NEEDS_REVIEW,
                )
        self.assertEqual(status.call_count, 1)
        self.assertEqual(status.call_args.args[4], "135.tif")
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

    def test_budget_hatching_preserves_the_photo_interior(self) -> None:
        source = Image.new("RGB", (160, 160), (90, 90, 90))
        polygon = (
            (20.0, 20.0),
            (140.0, 20.0),
            (140.0, 140.0),
            (20.0, 140.0),
        )
        rendered = _draw_hatched_polygon(
            source,
            polygon,
            DebugStyleParameters().review_color,
            DebugStyleParameters().budget_hatch_border_width,
        )
        pixels = np.asarray(rendered)
        self.assertTrue(np.any(pixels[17:28] != 90))
        self.assertFalse(np.any(pixels[55:105, 55:105] != 90))

    def test_debug_evidence_is_clipped_to_its_media_viewport(self) -> None:
        self.assertEqual(
            _clip_segment_to_box(
                (-10.0, 50.0),
                (110.0, 50.0),
                (10, 20, 90, 80),
            ),
            ((10.0, 50.0), (90.0, 50.0)),
        )
        base = Image.new("RGB", (100, 100), (20, 20, 20))
        evidence = Image.new("RGB", (100, 100), (200, 40, 40))
        clipped = np.asarray(
            _keep_evidence_inside_media(base, evidence, (20, 30, 80, 70))
        )
        self.assertTrue(np.all(clipped[:30] == 20))
        self.assertTrue(np.all(clipped[30:70, 20:80] == (200, 40, 40)))
        self.assertTrue(np.all(clipped[70:] == 20))

    def test_square_frame_strip_normalizes_full_source_into_fixed_grid(
        self,
    ) -> None:
        projection = _Projection(
            source_width=2_797,
            source_height=9_899,
            rotate_clockwise=True,
        )
        source_corners = (
            (0.0, 0.0),
            (2_797.0, 0.0),
            (2_797.0, 9_899.0),
            (0.0, 9_899.0),
        )
        viewport = _viewport(
            projection,
            (27, 81, 1_602, 249),
        )
        self.assertEqual(viewport.source_box, (0, 0, 9_899, 2_797))
        self.assertEqual(viewport.target_box, (27, 81, 1_602, 249))
        displayed = tuple(viewport.point(point) for point in source_corners)
        self.assertEqual(
            (
                min(point[0] for point in displayed),
                min(point[1] for point in displayed),
                max(point[0] for point in displayed),
                max(point[1] for point in displayed),
            ),
            (27.0, 81.0, 1_602.0, 249.0),
        )

    def test_cross_axis_panel_separates_detected_and_selected_edges(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with (
                mock.patch(
                    "x5crop.debug.panels._draw_detected_top_bottom",
                    wraps=debug_panels._draw_detected_top_bottom,
                ) as detected,
                mock.patch(
                    "x5crop.debug.panels._draw_selected_top_bottom",
                    wraps=debug_panels._draw_selected_top_bottom,
                ) as selected,
            ):
                _cross_axis_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
        self.assertEqual(detected.call_count, 1)
        self.assertEqual(selected.call_count, 1)

    def test_long_axis_panel_draws_every_detected_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            expected_transition_count = sum(
                len(lane.side_transition_regions)
                for lane in detection.candidate.geometry.lane_reconstructions
            )
            with mock.patch(
                "x5crop.debug.panels._draw_dashed_polyline"
            ) as detected_line:
                _long_axis_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                )
        self.assertGreater(expected_transition_count, 0)
        self.assertEqual(detected_line.call_count, expected_transition_count)

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
            ) as long_axis_base:
                _long_axis_panel(
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
            "DETECTED TRANSITION / SELECTED BOUNDARY",
            long_axis_base.call_args.args[3],
        )

    def test_fixed_palette_and_panel_stacking_are_bounded(self) -> None:
        self.assertEqual(len(FRAME_FILL_COLORS), 12)
        self.assertEqual(len(set(FRAME_FILL_COLORS)), 12)
        style = DebugStyleParameters()
        width = style.canvas_width - style.outer_margin * 2
        panels = tuple(
            np.zeros((height, width, 3), dtype=np.uint8)
            for height in (
                style.cross_axis_panel_height,
                style.long_axis_panel_height,
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

    def test_header_displays_and_bounds_the_original_source_filename(self) -> None:
        self.assertEqual(
            _source_header("原始扫描 01.tif"),
            "SOURCE · 原始扫描 01.tif",
        )
        with self.assertRaisesRegex(ValueError, "source filename"):
            _source_header("\n\t")
        image = Image.new("RGB", (300, 60))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=15)
        fitted = _fit_text(
            draw,
            _source_header("a" * 500 + ".tif"),
            font,
            180,
        )
        self.assertTrue(fitted.endswith("..."))
        self.assertLessEqual(
            draw.textbbox((0, 0), fitted, font=font)[2],
            180,
        )

    def test_deskew_data_is_owned_only_by_the_status_header(self) -> None:
        self.assertNotIn(
            "transform_assessment",
            inspect.getsource(debug_panels),
        )

    def test_detected_transition_is_visible_but_secondary(self) -> None:
        style = DebugStyleParameters()
        self.assertGreater(sum(style.detected_transition_color), 600)
        self.assertLess(
            sum(style.detected_transition_color),
            sum(style.safety_envelope_color),
        )

    def test_legend_matches_the_three_row_fact_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, _workspace, _detection = _fixture(
                Path(temporary)
            )
        self.assertEqual(
            tuple(entry.label for entry in configuration.diagnostics.legend_entries),
            (
                "DETECTED TOP/BOTTOM",
                "SELECTED TOP/BOTTOM",
                "DETECTED START/END",
                "SELECTED START/END",
                "SAFETY ENVELOPE",
                "FINAL OUTPUT",
                "BUDGET VIOLATION",
            ),
        )


if __name__ == "__main__":
    unittest.main()
