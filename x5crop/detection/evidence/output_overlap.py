from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import DetectionCandidate
from ...geometry.layout import work_gray
from ...policies.runtime.diagnostics import NearbySeparatorDiagnosticsPolicy
from ...policies.runtime.output_evidence import OutputOverlapEvidencePolicy
from ...policies.runtime.separator import SeparatorPolicy
from .gap_diagnostics import gap_diagnostic_record


def _overlap_record_band_width_px(record: dict[str, Any]) -> float:
    width = float(record.get("width_px", 0.0) or 0.0)
    signals = record.get("signals")
    if isinstance(signals, dict):
        window = signals.get("window")
        if isinstance(window, dict):
            try:
                width = max(width, float(window["end"]) - float(window["start"]))
            except (KeyError, TypeError, ValueError):
                pass
    return max(0.0, width)


def _required_output_bleed_px(
    records: list[dict[str, Any]],
    output_overlap_policy: OutputOverlapEvidencePolicy,
) -> int:
    overlap_records = [
        record
        for record in records
        if str(record.get("output_overlap_class", "none")) in {"medium", "strong"}
    ]
    if not overlap_records:
        return 0
    widest_band = max(_overlap_record_band_width_px(record) for record in overlap_records)
    required = ceil(
        widest_band * float(output_overlap_policy.required_bleed_window_fraction)
        + float(output_overlap_policy.required_bleed_padding_px)
    )
    return max(int(output_overlap_policy.required_bleed_min_px), int(required))


def output_overlap_evidence_detail(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: AnalysisCache | None = None,
    *,
    separator_policy: SeparatorPolicy,
    nearby_policy: NearbySeparatorDiagnosticsPolicy,
    output_overlap_policy: OutputOverlapEvidencePolicy,
    available_output_bleed_px: int,
) -> dict[str, Any]:
    if not detection.gaps:
        return {
            "used": False,
            "output_overlap_detected": False,
            "output_overlap_bleed_protectable": False,
            "output_overlap_protected_by_bleed": False,
            "output_overlap_unresolved": False,
            "required_output_bleed_px": 0,
            "available_output_bleed_px": max(0, int(available_output_bleed_px)),
            "bleed_sufficiency_px": max(0, int(available_output_bleed_px)),
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
    required_bleed_px = _required_output_bleed_px(gap_records, output_overlap_policy)
    available_bleed_px = max(0, int(available_output_bleed_px))
    bleed_sufficiency_px = int(available_bleed_px - required_bleed_px)
    output_overlap_bleed_protectable = bool(
        output_overlap_detected
        and output_overlap_policy.bleed_protection_enabled
        and required_bleed_px > 0
    )
    output_overlap_protected_by_bleed = bool(
        output_overlap_bleed_protectable
        and bleed_sufficiency_px >= 0
    )
    output_overlap_unresolved = bool(output_overlap_detected and not output_overlap_bleed_protectable)
    if output_overlap_bleed_protectable:
        output_overlap_unresolved = bool(not output_overlap_protected_by_bleed)
    return {
        "used": True,
        "output_overlap_detected": bool(output_overlap_detected),
        "output_overlap_bleed_protectable": bool(output_overlap_bleed_protectable),
        "output_overlap_protected_by_bleed": bool(output_overlap_protected_by_bleed),
        "output_overlap_unresolved": bool(output_overlap_unresolved),
        "required_output_bleed_px": int(required_bleed_px),
        "available_output_bleed_px": int(available_bleed_px),
        "bleed_sufficiency_px": int(bleed_sufficiency_px),
        "reason": (
            "output_overlap_protected_by_bleed"
            if output_overlap_protected_by_bleed
            else "output_overlap_unresolved"
            if output_overlap_unresolved
            else "no_medium_or_strong_output_overlap"
        ),
        "decision_role": (
            "output_bleed_adjustment_not_review_blocker"
            if output_overlap_protected_by_bleed
            else "output_overlap_review_blocker"
            if output_overlap_unresolved
            else "no_output_overlap_decision_signal"
        ),
        "output_overlap_counts": output_overlap_counts,
        "gap_diagnostics": gap_records,
        "gap_count": len(gap_records),
    }


__all__ = [
    "output_overlap_evidence_detail",
]
