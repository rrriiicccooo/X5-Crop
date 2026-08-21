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

import x5crop.debug.axis_panels as debug_axis_panels
import x5crop.debug.panel_facts as debug_panel_facts
import x5crop.debug.panels as debug_panels
from x5crop.configuration.registry import get_detection_configuration
from x5crop.configuration.diagnostics import DebugStyleParameters
from x5crop.debug.canvas import FRAME_FILL_COLORS, DebugRenderCache
from x5crop.debug.axis_panels import cross_axis_panel, long_axis_panel
from x5crop.debug.output_panel import (
    draw_hatched_polygon,
    keep_evidence_inside_media,
    protected_output_panel,
)
from x5crop.debug.panel_facts import (
    alignment_summary,
    axis_authority_summaries,
    competition_summary,
    primary_geometry_by_identity,
    root_gate_summary,
    selected_output_safety_summary,
    runner_geometry_by_identity,
    source_projection,
)
from x5crop.debug.panel_layout import (
    Projection,
    clip_segment_to_box,
    presentation_grid,
    viewport,
)
from x5crop.debug.panels import (
    make_debug_analysis_panel,
    stack_debug_panels,
)
from x5crop.debug.status import fit_text, source_header, transform_lines
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import FiniteInterval
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
    configuration = get_detection_configuration("135", 3)
    workspace = prepare_detection_workspace(
        array,
        profile,
        "horizontal",
        configuration,
    )
    candidate = choose_detection(workspace, configuration)
    decision = apply_decision_gate(candidate.gate)
    detection = finalize_detection(
        candidate,
        decision,
        workspace.deskew_observation,
        layout=workspace.layout,
        source_width=workspace.source_gray.shape[1],
        source_height=workspace.source_gray.shape[0],
    )
    return configuration, profile, workspace, detection


def _grid(workspace, style: DebugStyleParameters):
    return presentation_grid(source_projection(workspace), style)


class DebugAnalysisContractTest(unittest.TestCase):
    def test_review_titles_preserve_each_axis_minimum_missing_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _configuration, _profile, _workspace, detection = _fixture(
                Path(temporary)
            )
        cross, sequence, source = axis_authority_summaries(detection)
        self.assertIn("CROSS FIT ·", cross)
        self.assertIn("DIR ", cross)
        self.assertIn("ENCLOSING ", cross)
        self.assertIn("SEQUENCE FIT ·", sequence)
        self.assertIn("SOURCE FIT ·", source)

    def test_three_panels_preserve_four_v5_fact_layers(self) -> None:
        self.assertEqual(
            (
                "01 · CROSS-AXIS TOP / BOTTOM",
                "02 · LONG-AXIS START / END",
                "03 · FINAL SAFE OUTPUT",
            ),
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
        grid = _grid(workspace, style)
        self.assertEqual(
            panel.shape,
            (grid.canvas_height, style.canvas_width, 3),
        )

    def test_output_panel_reads_selected_joint_and_required_footprints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with mock.patch(
                "x5crop.debug.output_panel.fill_polygon"
            ) as fill:
                protected_output_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                    _grid(workspace, configuration.diagnostics.style),
                )
        self.assertFalse(detection.frame_export_eligible)
        outputs = detection.candidate.geometry.output_footprints
        self.assertCountEqual(
            tuple(call.args[1] for call in fill.call_args_list),
            (
                tuple(
                    footprint
                    for output in outputs
                    for footprint in (
                        output.envelope.canonical_source_footprint,
                        output.envelope.feasible_source_footprint,
                    )
                )
                if outputs
                else ()
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
        rendered = draw_hatched_polygon(
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
            clip_segment_to_box(
                (-10.0, 50.0),
                (110.0, 50.0),
                (10, 20, 90, 80),
            ),
            ((10.0, 50.0), (90.0, 50.0)),
        )
        base = Image.new("RGB", (100, 100), (20, 20, 20))
        evidence = Image.new("RGB", (100, 100), (200, 40, 40))
        clipped = np.asarray(
            keep_evidence_inside_media(base, evidence, (20, 30, 80, 70))
        )
        self.assertTrue(np.all(clipped[:30] == 20))
        self.assertTrue(np.all(clipped[30:70, 20:80] == (200, 40, 40)))
        self.assertTrue(np.all(clipped[70:] == 20))

    def test_square_frame_strip_expands_canvas_without_aspect_compression(
        self,
    ) -> None:
        projection = Projection(
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
        style = DebugStyleParameters()
        self.assertEqual(style.canvas_width, 1_800)
        grid = presentation_grid(projection, style)
        panel_width = style.canvas_width - 2 * style.outer_margin
        target_box = (
            style.panel_media_inset_x,
            style.cross_axis_media_top,
            panel_width - style.panel_media_inset_x,
            style.cross_axis_media_top + grid.media_height,
        )
        selected_viewport = viewport(projection, target_box)
        self.assertEqual(selected_viewport.source_box, (0, 0, 9_899, 2_797))
        self.assertEqual(grid.media_height, 487)
        self.assertEqual(selected_viewport.target_box, (27, 81, 1_749, 568))
        displayed = tuple(
            selected_viewport.point(point) for point in source_corners
        )
        scale_x = (
            max(point[0] for point in displayed)
            - min(point[0] for point in displayed)
        ) / projection.display_width
        scale_y = (
            max(point[1] for point in displayed)
            - min(point[1] for point in displayed)
        ) / projection.display_height
        self.assertAlmostEqual(
            scale_x,
            scale_y,
            delta=1.0 / projection.display_height,
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
                    "x5crop.debug.axis_panels._draw_detected_top_bottom",
                    wraps=debug_axis_panels._draw_detected_top_bottom,
                ) as detected,
                mock.patch(
                    "x5crop.debug.axis_panels._draw_primary_top_bottom",
                    wraps=debug_axis_panels._draw_primary_top_bottom,
                ) as primary,
                mock.patch(
                    "x5crop.debug.axis_panels._draw_runner_top_bottom",
                    wraps=debug_axis_panels._draw_runner_top_bottom,
                ) as runner,
            ):
                cross_axis_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                    _grid(workspace, configuration.diagnostics.style),
                )
        self.assertEqual(detected.call_count, 1)
        self.assertEqual(primary.call_count, 1)
        self.assertEqual(runner.call_count, 1)

    def test_long_axis_panel_draws_every_detected_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            expected_transition_count = sum(
                len(lane.prepared.side_regions)
                for lane in detection.candidate.geometry.lane_reconstructions
            )
            with mock.patch(
                "x5crop.debug.axis_panels._draw_detected_start_end",
                wraps=debug_axis_panels._draw_detected_start_end,
            ) as detected:
                long_axis_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                    _grid(workspace, configuration.diagnostics.style),
                )
        self.assertGreater(expected_transition_count, 0)
        self.assertEqual(detected.call_count, 1)

    def test_review_keeps_candidate_audit_without_official_output_geometry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            configuration, _profile, workspace, detection = _fixture(
                Path(temporary)
            )
            with (
                mock.patch(
                    "x5crop.debug.output_panel.fill_polygon"
                ) as fill,
                mock.patch(
                    "x5crop.debug.output_panel.panel_base",
                    wraps=__import__(
                        "x5crop.debug.output_panel",
                        fromlist=["panel_base"],
                    ).panel_base,
                ) as output_base,
            ):
                protected_output_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                    _grid(workspace, configuration.diagnostics.style),
                )
            with mock.patch(
                "x5crop.debug.axis_panels.panel_base",
                wraps=__import__(
                    "x5crop.debug.axis_panels",
                    fromlist=["panel_base"],
                ).panel_base,
            ) as long_axis_base:
                long_axis_panel(
                    workspace,
                    detection,
                    configuration.diagnostics.style,
                    DebugRenderCache(),
                    _grid(workspace, configuration.diagnostics.style),
                )
        self.assertEqual(detection.decision.status, "needs_review")
        self.assertFalse(detection.frame_export_eligible)
        self.assertEqual(detection.output_footprints, ())
        self.assertEqual(fill.call_count, 0)
        shared_title = output_base.call_args.args[3]
        sequence_title = long_axis_base.call_args.args[3]
        self.assertTrue(shared_title.startswith("SOURCE FIT · "))
        self.assertIn("PLACEMENTS · ", shared_title)
        self.assertTrue(sequence_title.startswith("SEQUENCE FIT · "))
        self.assertIn("COARSE ", sequence_title)
        self.assertIn("RUNNER ", sequence_title)

    def test_adaptive_panel_stacking_is_bounded(self) -> None:
        self.assertEqual(len(FRAME_FILL_COLORS), 12)
        self.assertEqual(len(set(FRAME_FILL_COLORS)), 12)
        style = DebugStyleParameters()
        grid = presentation_grid(
            Projection(720, 100, rotate_clockwise=False),
            style,
        )
        width = style.canvas_width - style.outer_margin * 2
        panels = tuple(
            np.zeros((height, width, 3), dtype=np.uint8)
            for height in (
                grid.cross_axis_panel_height,
                grid.long_axis_panel_height,
                grid.output_panel_height,
            )
        )
        body = stack_debug_panels(panels, style=style, grid=grid)
        self.assertEqual(
            body.shape,
            (
                grid.canvas_height
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
            deskew_applied=True,
            applied_source_rotation_degrees=-0.153,
            observed_angle_degrees=0.153,
            skip_reason=None,
        )
        applied = SimpleNamespace(deskew_assessment=assessment)
        first, second = transform_lines(applied, profile)
        self.assertEqual(first, "V5 · DESKEW APPLIED -0.153°")
        self.assertIn("observed +0.153°", second)
        self.assertIn("ORIENTATION 1>CANONICAL>1", second)

    def test_header_distinguishes_rotation_not_needed_from_measurement_skip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _configuration, profile, _workspace, _detection = _fixture(
                Path(temporary)
            )
        not_needed = SimpleNamespace(
            deskew_assessment=SimpleNamespace(
                deskew_applied=False,
                applied_source_rotation_degrees=0.0,
                observed_angle_degrees=0.0,
                skip_reason=SimpleNamespace(value="rotation_not_needed"),
            )
        )
        skipped = SimpleNamespace(
            deskew_assessment=SimpleNamespace(
                deskew_applied=False,
                applied_source_rotation_degrees=None,
                observed_angle_degrees=None,
                skip_reason=SimpleNamespace(value="edge_slope_conflict"),
            )
        )

        self.assertEqual(
            transform_lines(not_needed, profile)[0],
            "V5 · ROTATION NOT NEEDED +0.000°",
        )
        self.assertEqual(
            transform_lines(skipped, profile)[0],
            "V5 · DESKEW SKIPPED · edge_slope_conflict",
        )

    def test_header_displays_and_bounds_the_original_source_filename(self) -> None:
        self.assertEqual(
            source_header("原始扫描 01.tif"),
            "SOURCE · 原始扫描 01.tif",
        )
        with self.assertRaisesRegex(ValueError, "source filename"):
            source_header("\n\t")
        image = Image.new("RGB", (300, 60))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=15)
        fitted = fit_text(
            draw,
            source_header("a" * 500 + ".tif"),
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
                "RUNNER / COMPETITOR",
                "SAFETY ENVELOPE",
                "FINAL OUTPUT",
                "BUDGET VIOLATION",
            ),
        )

    def test_winner_runner_and_official_output_are_separate_facts(self) -> None:
        winner_frame = SimpleNamespace(lane_ordinal=1)
        runner_frame = SimpleNamespace(lane_ordinal=1)
        winner = SimpleNamespace(
            placement_id="winner",
            lane_id="lane:0",
            frames=(winner_frame,),
            sequence_fit="phase:best",
            cross_fit="cross:best",
        )
        runner = SimpleNamespace(
            placement_id="runner",
            lane_id="lane:0",
            frames=(runner_frame,),
            sequence_fit="phase:runner",
            cross_fit="cross:best",
        )
        competition = SimpleNamespace(
            placements=(winner, runner),
            selected_placement_id="winner",
            runner_up_placement_id="runner",
        )
        geometry = SimpleNamespace(
            lane_reconstructions=(
                SimpleNamespace(
                    placement_competition=competition,
                    prepared=SimpleNamespace(
                        phase_competition=SimpleNamespace(
                            runner_up="phase:runner",
                            winner_basis=SimpleNamespace(value="direct_support"),
                        ),
                        cross_competition=SimpleNamespace(runner_up=None),
                    ),
                ),
            ),
            source_placement_selection=SimpleNamespace(
                state=SimpleNamespace(value="supported")
            ),
        )
        detection = SimpleNamespace(
            output_slot_identities=(
                SimpleNamespace(
                    lane_id="lane:0",
                    lane_ordinal=1,
                    global_output_ordinal=1,
                ),
            ),
            candidate=SimpleNamespace(geometry=geometry),
        )
        self.assertEqual(primary_geometry_by_identity(detection), ((1, winner_frame),))
        self.assertEqual(runner_geometry_by_identity(detection), ((1, runner_frame),))
        self.assertIn("PHASE DIRECT SUPPORT", competition_summary(detection))
        self.assertIn("RUNNER DIFF PHASE", competition_summary(detection))
        self.assertFalse(hasattr(debug_panel_facts, "geometry_by_identity"))

    def test_debug_names_the_root_blocking_gate_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _configuration, _profile, _workspace, detection = _fixture(
                Path(temporary)
            )
        summary = root_gate_summary(detection)
        self.assertTrue(summary.startswith("ROOT GATE · "))
        self.assertIn("NEED ", summary)
        self.assertIn("ACTION ", summary)

    def test_debug_names_alignment_pattern_and_selected_output_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _configuration, _profile, _workspace, detection = _fixture(
                Path(temporary)
            )
        self.assertTrue(alignment_summary(detection).startswith("ALIGNMENT · "))
        self.assertTrue(
            selected_output_safety_summary(detection).startswith(
                "SELECTED OUTPUT SAFETY · "
            )
        )


if __name__ == "__main__":
    unittest.main()
