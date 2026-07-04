from __future__ import annotations

import numpy as np

from ..image.evidence import make_content_evidence_gray
from ..geometry.layout import work_gray
from . import AnalysisCache


def make_analysis_cache(gray: np.ndarray, layout: str) -> AnalysisCache:
    gray_work = work_gray(gray, layout)
    content_evidence = make_content_evidence_gray(gray_work)
    return AnalysisCache(
        layout=layout,
        gray_work=gray_work,
        content_evidence_work=content_evidence,
        content_evidence_float_work=content_evidence.astype(np.float32) / 255.0,
    )
