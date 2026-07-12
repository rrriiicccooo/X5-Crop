from __future__ import annotations

from pathlib import Path

import numpy as np

from ..run_config import RunConfig
from ..detection.final.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from ..output.surface import display_generated_path
from ..configuration.diagnostics import DiagnosticsConfiguration
from .writer import write_debug_analysis, write_debug_preview
from .canvas import DebugRenderCache


def write_debug_outputs(
    gray: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    output_dir: Path,
    input_stem: str,
    config: RunConfig,
    warnings: list[str],
    diagnostics: DiagnosticsConfiguration,
) -> None:
    render_cache = DebugRenderCache()
    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_stem}_debug.jpg"
        write_debug_preview(
            gray,
            detection,
            debug_path,
            diagnostics,
            render_cache,
        )
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        analysis_path = write_debug_analysis(
            gray,
            detection,
            selected_candidate,
            output_dir,
            input_stem,
            diagnostics,
            render_cache,
        )
        warnings.append(
            f"debug analysis: {display_generated_path(analysis_path, config)}"
        )
