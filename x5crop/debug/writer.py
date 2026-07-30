from __future__ import annotations

from pathlib import Path

from ..configuration.diagnostics import DiagnosticsConfiguration
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from ..run_status import RunTerminalOutcome
from .canvas import DebugRenderCache, write_rgb_jpeg
from .panels import make_bounded_safe_crop_preview_rgb
from .status import add_status_bar


def _render(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
):
    return add_status_bar(
        make_bounded_safe_crop_preview_rgb(
            workspace,
            detection,
            diagnostics.style,
            render_cache,
        ),
        detection,
        diagnostics.style,
        terminal_outcome,
    )


def write_debug_preview(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    output_path: Path,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> None:
    write_rgb_jpeg(
        _render(
            workspace,
            detection,
            diagnostics,
            render_cache,
            terminal_outcome,
        ),
        output_path,
        quality=diagnostics.style.jpeg_quality,
    )


def write_debug_analysis(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    output_dir: Path,
    stem: str,
    diagnostics: DiagnosticsConfiguration,
    render_cache: DebugRenderCache,
    terminal_outcome: RunTerminalOutcome,
) -> str:
    path = output_dir / "_debug_analysis" / f"{stem}_debug_analysis.jpg"
    write_debug_preview(
        workspace,
        detection,
        path,
        diagnostics,
        render_cache,
        terminal_outcome,
    )
    return str(path)
