from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import Box, DetectionCandidate
from ...formats import FormatSpec
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..candidate.signals import SIGNAL_NEEDS_MANUAL_REVIEW


def review_only_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> DetectionCandidate:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    mode_diagnostics = [policy.detector.review_only.reason, SIGNAL_NEEDS_MANUAL_REVIEW]
    return DetectionCandidate(
        film_format=fmt.name,
        layout=config.layout,
        strip_mode=config.strip_mode,
        count=fmt.default_count,
        outer=map_work_box(outer, config.layout, source_w, source_h),
        frames=[],
        gaps=[],
        confidence=0.0,
        detail={
            "candidate_signals": list(mode_diagnostics),
            "candidate_source": CANDIDATE_SOURCE_REVIEW_ONLY,
            "candidate_count": 0,
            "mode_diagnostics": list(mode_diagnostics),
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "formats": [fmt.name],
                "selected_candidate": {
                    "format": fmt.name,
                    "count": fmt.default_count,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "candidate_signals": list(mode_diagnostics),
                },
                "selection_override": policy.detector.review_only.selection_override,
                "top_candidates": [],
            },
        },
    )


__all__ = ["review_only_detection"]
