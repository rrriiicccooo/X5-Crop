from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import Detection
from ...geometry.layout import work_gray
from ...policies.runtime.policy import DetectionPolicy
from .gap_diagnostics import gap_diagnostic_record


def output_overlap_evidence_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache | None = None,
    *,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    if not detection.gaps:
        return {
            "used": False,
            "output_overlap_detected": False,
            "reason": "no_gaps",
        }
    gray_work = (
        cache.gray_work
        if cache is not None and cache.layout == detection.layout
        else work_gray(gray, detection.layout)
    )
    gap_records = [
        gap_diagnostic_record(gray_work, detection, gap, cache, policy=policy)
        for gap in detection.gaps
    ]
    output_overlap_counts: dict[str, int] = {}
    for record in gap_records:
        overlap_class = str(record.get("output_overlap_class", "none"))
        output_overlap_counts[overlap_class] = output_overlap_counts.get(overlap_class, 0) + 1
    output_overlap_detected = (
        int(output_overlap_counts.get("strong", 0)) > 0
        or int(output_overlap_counts.get("medium", 0)) > 0
    )
    return {
        "used": True,
        "output_overlap_detected": bool(output_overlap_detected),
        "reason": (
            "output_overlap_detected"
            if output_overlap_detected
            else "no_medium_or_strong_output_overlap"
        ),
        "output_overlap_counts": output_overlap_counts,
        "gap_diagnostics": gap_records,
        "gap_count": len(gap_records),
    }


__all__ = [
    "output_overlap_evidence_detail",
]
