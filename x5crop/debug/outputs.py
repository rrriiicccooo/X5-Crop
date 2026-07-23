from __future__ import annotations

from pathlib import Path

from ..run_config import RunConfig
from ..run_status import RunTerminalOutcome
from ..detection.final.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from ..detection.workspace import DetectionWorkspace
from ..output.surface import display_generated_path
from ..configuration.diagnostics import DiagnosticsConfiguration
from .writer import write_debug_analysis, write_debug_preview
from .canvas import DebugRenderCache


def write_debug_outputs(
    workspace: DetectionWorkspace,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    output_dir: Path,
    input_stem: str,
    config: RunConfig,
    warnings: list[str],
    diagnostics: DiagnosticsConfiguration,
    terminal_outcome: RunTerminalOutcome,
) -> str | None:
    render_cache = DebugRenderCache()
    debug_analysis: str | None = None
    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_stem}_debug.jpg"
        write_debug_preview(
            workspace,
            detection,
            selected_candidate,
            debug_path,
            diagnostics,
            render_cache,
            terminal_outcome,
        )
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        debug_analysis = write_debug_analysis(
            workspace,
            detection,
            selected_candidate,
            output_dir,
            input_stem,
            diagnostics,
            render_cache,
            terminal_outcome,
        )
        warnings.append(
            f"debug analysis: {display_generated_path(debug_analysis, config)}"
        )
    return debug_analysis
