from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import Detection
from ...geometry.layout import work_gray
from ...policies.runtime.diagnostics import NearbySeparatorDiagnosticsPolicy
from ...policies.runtime.output_evidence import OutputOverlapEvidencePolicy
from ...policies.runtime.separator import SeparatorPolicy
from .gap_diagnostics import gap_diagnostic_record


def output_overlap_evidence_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache | None = None,
    *,
    separator_policy: SeparatorPolicy,
    nearby_policy: NearbySeparatorDiagnosticsPolicy,
    output_overlap_policy: OutputOverlapEvidencePolicy,
) -> dict[str, Any]:
    if not detection.gaps:
        return {
            "used": False,
            "output_overlap_detected": False,
            "output_overlap_protected_by_bleed": False,
            "output_overlap_unresolved": False,
            "reason": "no_gaps",
            "decision_role": "no_output_overlap_evidence",
        }
    gray_work = (
        cache.gray_work
        if cache is not None and cache.layout == detection.layout
        else work_gray(gray, detection.layout)
    )
    gap_records = [
        gap_diagnostic_record(
            gray_work,
            detection,
            gap,
            cache,
            separator_policy=separator_policy,
            nearby_policy=nearby_policy,
            output_overlap_policy=output_overlap_policy,
        )
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
    output_overlap_protected_by_bleed = bool(output_overlap_detected)
    return {
        "used": True,
        "output_overlap_detected": bool(output_overlap_detected),
        "output_overlap_protected_by_bleed": bool(output_overlap_protected_by_bleed),
        "output_overlap_unresolved": False,
        "reason": (
            "output_overlap_protected_by_bleed"
            if output_overlap_protected_by_bleed
            else "no_medium_or_strong_output_overlap"
        ),
        "decision_role": (
            "output_bleed_adjustment_not_review_blocker"
            if output_overlap_protected_by_bleed
            else "no_output_overlap_decision_signal"
        ),
        "output_overlap_counts": output_overlap_counts,
        "gap_diagnostics": gap_records,
        "gap_count": len(gap_records),
    }


__all__ = [
    "output_overlap_evidence_detail",
]
