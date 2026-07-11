from __future__ import annotations

from pathlib import Path
import numpy as np

from ..detection.decision.model import FinalDetection
from ..image.evidence import SeparatorEvidenceImageParameters
from ..policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from .canvas import DebugRenderCache, write_rgb_jpeg
from .panels import make_debug_analysis_panel, make_debug_preview_rgb
from .status import add_status_bar


def write_debug_preview(
    gray: np.ndarray,
    detection: FinalDetection,
    output_path: Path,
    render_cache: DebugRenderCache,
) -> None:
    rgb = add_status_bar(
        make_debug_preview_rgb(gray, detection, render_cache),
        detection,
    )
    write_rgb_jpeg(rgb, output_path)


def write_debug_analysis(
    gray: np.ndarray,
    detection: FinalDetection,
    output_dir: Path,
    stem: str,
    diagnostics: RuntimeDiagnosticsPolicy,
    separator_evidence_image: SeparatorEvidenceImageParameters,
    render_cache: DebugRenderCache,
) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(
        make_debug_analysis_panel(
            gray,
            detection,
            diagnostics,
            separator_evidence_image,
            render_cache,
        ),
        panel_path,
    )
    return [str(panel_path)]
