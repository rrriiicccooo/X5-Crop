from __future__ import annotations

from pathlib import Path

from ..configuration.diagnostics import DiagnosticsConfiguration
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from ..run_status import RunTerminalOutcome
from .canvas import DebugRenderCache, write_rgb_jpeg
from .panels import make_debug_analysis_panel


def write_debug_analysis(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    output_dir: Path,
    stem: str,
    diagnostics: DiagnosticsConfiguration,
    terminal_outcome: RunTerminalOutcome,
) -> str:
    path = output_dir / "_debug_analysis" / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(
        make_debug_analysis_panel(
            workspace,
            detection,
            diagnostics,
            DebugRenderCache(),
            terminal_outcome,
        ),
        path,
        quality=diagnostics.style.jpeg_quality,
    )
    return str(path)
