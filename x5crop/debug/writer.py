from __future__ import annotations

from pathlib import Path

from ..detection.final.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from ..detection.workspace import DetectionWorkspace
from ..configuration.diagnostics import DiagnosticsConfiguration
from ..run_status import RunTerminalOutcome
from .canvas import DebugRenderCache, write_rgb_jpeg
from .panels import make_debug_analysis_panel, make_debug_preview_rgb
from .status import add_status_bar


def write_debug_preview(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    output_path: Path,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> None:
    rgb = add_status_bar(
        make_debug_preview_rgb(
            workspace,
            detection,
            selected_candidate,
            diagnostics.style,
            render_cache,
        ),
        detection,
        diagnostics.style,
        terminal_outcome,
    )
    write_rgb_jpeg(rgb, output_path, quality=diagnostics.style.jpeg_quality)


def write_debug_analysis(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    output_dir: Path,
    stem: str,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> str:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(
        make_debug_analysis_panel(
            workspace,
            detection,
            selected_candidate,
            diagnostics,
            render_cache,
            terminal_outcome,
        ),
        panel_path,
        quality=diagnostics.style.jpeg_quality,
    )
    return str(panel_path)
