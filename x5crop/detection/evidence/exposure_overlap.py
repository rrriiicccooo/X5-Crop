from __future__ import annotations

from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import DetectionCandidate
from ...geometry.layout import work_gray
from ...policies.runtime.exposure_overlap import ExposureOverlapEvidencePolicy
from ...policies.runtime.separator import SeparatorPolicy
from .gap_evidence import gap_evidence_record


def _overlap_band_width_px(record: dict[str, Any]) -> float:
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


def exposure_overlap_evidence_detail(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: AnalysisCache | None = None,
    *,
    separator_policy: SeparatorPolicy,
    exposure_overlap_policy: ExposureOverlapEvidencePolicy,
) -> dict[str, Any]:
    if not detection.gaps:
        return {
            "used": False,
            "exposure_overlap_detected": False,
            "widest_overlap_band_px": 0.0,
            "reason": "no_gaps",
            "exposure_overlap_counts": {},
            "gap_evidence": [],
        }
    gray_work = (
        cache.gray_work
        if cache is not None and cache.layout == detection.layout
        else work_gray(gray, detection.layout)
    )
    records = [
        gap_evidence_record(
            gray_work,
            detection,
            gap,
            separator_policy=separator_policy,
            exposure_overlap_policy=exposure_overlap_policy,
        )
        for gap in detection.gaps
    ]
    counts: dict[str, int] = {}
    overlap_records: list[dict[str, Any]] = []
    for record in records:
        overlap_class = str(record.get("exposure_overlap_class", "none"))
        counts[overlap_class] = counts.get(overlap_class, 0) + 1
        if overlap_class in {"medium", "strong"}:
            overlap_records.append(record)
    detected = bool(overlap_records)
    widest_band = max(
        (_overlap_band_width_px(record) for record in overlap_records),
        default=0.0,
    )
    return {
        "used": True,
        "exposure_overlap_detected": detected,
        "widest_overlap_band_px": float(widest_band),
        "reason": "exposure_overlap_detected" if detected else "no_exposure_overlap",
        "exposure_overlap_counts": counts,
        "gap_evidence": records,
        "gap_count": len(records),
    }
