from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import DetectionCandidate
from ...geometry.layout import work_gray
from ...cache import AnalysisCache
from ...gap_methods import gap_method_roles
from ...policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from ...policies.runtime.separator import SeparatorPolicy
from .gap_evidence import gap_work_outer
from .nearby_separator_diagnostics import nearby_separator_diagnostic_detail


def attach_read_only_diagnostics(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: Optional[AnalysisCache],
    *,
    separator_policy: SeparatorPolicy,
    diagnostics_policy: RuntimeDiagnosticsPolicy,
) -> None:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    exposure_overlap = detection.detail.get("exposure_overlap_evidence")
    gap_records = (
        exposure_overlap.get("gap_evidence", [])
        if isinstance(exposure_overlap, dict)
        else []
    )
    if not isinstance(gap_records, list):
        gap_records = []
    gaps_by_index = {gap.index: gap for gap in detection.gaps}
    nearby_separator_diagnostics: list[dict] = []
    for record in gap_records:
        if not isinstance(record, dict):
            continue
        gap = gaps_by_index.get(int(record.get("index", -1)))
        if gap is None:
            continue
        work_outer = gap_work_outer(detection, gap)
        signals = record.get("signals")
        window = signals.get("window") if isinstance(signals, dict) else None
        if work_outer is not None and work_outer.valid() and isinstance(window, dict):
            nearby_separator_diagnostics.append(
                {
                    "index": int(gap.index),
                    "detail": nearby_separator_diagnostic_detail(
                        gray_work,
                        work_outer,
                        gap,
                        float(detection.detail.get("pitch", 0.0) or 0.0),
                        int(window["start"]),
                        int(window["end"]),
                        diagnostics_policy.nearby_separator_search,
                        diagnostics_policy.nearby_separator_comparison,
                        separator_policy.profile,
                        cache,
                    ),
                }
            )
    hard_counts: dict[str, int] = {}
    for record in gap_records:
        trust = str(record.get("hard_trust", "not_hard_gap"))
        hard_counts[trust] = hard_counts.get(trust, 0) + 1
    exposure_overlap_count = sum(
        1 for record in gap_records if bool(record.get("exposure_overlap_like", False))
    )
    exposure_overlap_counts: dict[str, int] = {}
    for record in gap_records:
        exposure_overlap_class = str(record.get("exposure_overlap_class", "none"))
        exposure_overlap_counts[exposure_overlap_class] = (
            exposure_overlap_counts.get(exposure_overlap_class, 0) + 1
        )
    strong_hard = int(hard_counts.get("strong_separator", 0))
    suspicious_hard = sum(
        int(hard_counts.get(name, 0))
        for name in ("suspect_internal_edge", "suspect_frame_border", "nearby_separator_conflict", "geometry_conflict")
    )
    method_roles = gap_method_roles()
    detection.detail["diagnostics"] = {
        "diagnostic_only": True,
        "effects": {
            "output": False,
            "confidence": False,
            "decision": False,
        },
        "purpose": "observe hard-gap trust, exposure-overlap evidence, and evidence/model roles without changing crop output",
        "method_roles": method_roles,
        "nearby_separator_diagnostics": nearby_separator_diagnostics,
        "summary": {
            "gap_count": len(gap_records),
            "hard_trust_counts": hard_counts,
            "exposure_overlap_like_model_gaps": int(exposure_overlap_count),
            "exposure_overlap_counts": exposure_overlap_counts,
            "suspect_hard_gaps": int(hard_counts.get("suspect_internal_edge", 0)),
            "suspicious_hard_gaps": int(suspicious_hard),
            "strong_hard_gaps": int(strong_hard),
        },
    }
