from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from ..domain import FinalDetection
from ..image.evidence import SeparatorEvidenceImageParameters
from ..policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from ..cache import AnalysisCache
from .canvas import write_rgb_jpeg
from .panels import make_debug_analysis_panel, make_debug_preview_rgb
from .status import add_status_bar


def write_debug_preview(
    gray: np.ndarray,
    detection: FinalDetection,
    output_path: Path,
    threshold: float,
    cache: Optional[AnalysisCache],
) -> None:
    rgb = add_status_bar(make_debug_preview_rgb(gray, detection, cache), detection, threshold)
    write_rgb_jpeg(rgb, output_path)


def write_debug_analysis(
    gray: np.ndarray,
    detection: FinalDetection,
    output_dir: Path,
    stem: str,
    threshold: float,
    diagnostics: RuntimeDiagnosticsPolicy,
    separator_evidence_image: SeparatorEvidenceImageParameters,
    cache: Optional[AnalysisCache],
) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(
        make_debug_analysis_panel(
            gray,
            detection,
            threshold,
            diagnostics,
            separator_evidence_image,
            cache,
        ),
        panel_path,
    )
    return [str(panel_path)]
