from __future__ import annotations

from pathlib import Path

import numpy as np

from ..cache import AnalysisCache
from ..run_config import RunConfig
from ..domain import FinalDetection
from ..image.evidence import SeparatorEvidenceImageParameters
from ..output.surface import display_generated_path
from ..policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from .writer import write_debug_analysis, write_debug_preview


def write_debug_outputs(
    gray: np.ndarray,
    detection: FinalDetection,
    output_dir: Path,
    input_stem: str,
    config: RunConfig,
    analysis_cache: AnalysisCache,
    warnings: list[str],
    diagnostics: RuntimeDiagnosticsPolicy,
    separator_evidence_image: SeparatorEvidenceImageParameters,
) -> None:
    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, analysis_cache)
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        analysis_paths = write_debug_analysis(
            gray,
            detection,
            output_dir,
            input_stem,
            diagnostics,
            separator_evidence_image,
            analysis_cache,
        )
        for analysis_path in analysis_paths:
            warnings.append(f"debug analysis: {display_generated_path(analysis_path, config)}")
