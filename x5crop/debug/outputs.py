from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Config
from ..domain import Detection
from ..export import display_generated_path
from .writer import write_debug_analysis, write_debug_preview


def write_debug_outputs(
    gray: Any,
    detection: Detection,
    output_dir: Path,
    input_stem: str,
    config: Config,
    analysis_cache: Any,
    warnings: list[str],
) -> None:
    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold, analysis_cache)
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        analysis_paths = write_debug_analysis(
            gray,
            detection,
            output_dir,
            input_stem,
            config.confidence_threshold,
            analysis_cache,
        )
        for analysis_path in analysis_paths:
            warnings.append(f"debug analysis: {display_generated_path(analysis_path, config)}")


__all__ = [
    "write_debug_outputs",
]
