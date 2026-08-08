from __future__ import annotations

from pathlib import Path

from ..configuration.diagnostics import DiagnosticsConfiguration
from ..configuration.model import DetectionConfiguration
from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from ..io.model import ImageProfile
from ..run_status import RunTerminalOutcome
from ..output.naming import portable_component
from .canvas import DebugRenderCache, write_rgb_jpeg
from .panels import make_debug_analysis_panel


def write_debug_analysis(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    output_dir: Path,
    portable_stem: str,
    input_ordinal: int,
    diagnostics: DiagnosticsConfiguration,
    terminal_outcome: RunTerminalOutcome,
) -> str:
    name = portable_component(
        portable_stem,
        input_ordinal=input_ordinal,
        suffix="_debug_analysis.jpg",
    ).value
    path = output_dir / "_debug_analysis" / name
    write_rgb_jpeg(
        make_debug_analysis_panel(
            workspace,
            detection,
            configuration,
            profile,
            diagnostics,
            DebugRenderCache(),
            terminal_outcome,
        ),
        path,
        quality=diagnostics.style.jpeg_quality,
    )
    return str(path)
