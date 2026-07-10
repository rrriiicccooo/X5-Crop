from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ...domain import Box, DetectionCandidate, Gap
from ...gap_methods import gap_method_role, is_hard_gap_method, is_model_gap_method
from ...geometry.gap_trust import (
    diagnostic_hard_gap_trust_assessment,
    hard_gap_pixel_signals,
    hard_gap_tonal_separator_like,
    hard_gap_width_ratio,
)
from ...policies.parameters.exposure_overlap import ExposureOverlapEvidenceParameters
from ...policies.runtime.separator import SeparatorPolicy
from ...utils import clamp_int


def gap_work_outer(detection: DetectionCandidate, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        return Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None


def gap_evidence_record(
    gray_work: np.ndarray,
    detection: DetectionCandidate,
    gap: Gap,
    *,
    separator_policy: SeparatorPolicy,
    exposure_overlap_policy: ExposureOverlapEvidenceParameters,
) -> dict[str, Any]:
    hard_gap_trust_policy = separator_policy.hard_gap_trust
    work_outer = gap_work_outer(detection, gap)
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    origin = float(detection.detail.get("origin", 0.0) or 0.0)
    expected = origin + pitch * float(gap.index) if pitch > 0 else float(gap.center)
    role = gap_method_role(gap.method)
    record: dict[str, Any] = {
        "index": int(gap.index),
        "method": gap.method,
        "role": role,
        "measurement_role": "gap_evidence",
        "used_for_assessment": True,
        "center": float(gap.center),
        "expected_center": float(expected),
        "model_delta_px": float(gap.center - expected),
        "score": float(gap.score),
        "width_px": float(gap.width),
        "hard_trust": "not_hard_gap",
        "exposure_overlap_like": False,
        "exposure_overlap_class": "none",
        "signals": {},
    }
    if work_outer is None or not work_outer.valid() or pitch <= 0:
        record["signals"] = {"available": False}
        return record

    work_outer = work_outer.clamp(gray_work.shape[1], gray_work.shape[0])
    if not work_outer.valid():
        record["signals"] = {"available": False}
        return record

    if gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
    else:
        half = clamp_int(
            pitch * exposure_overlap_policy.model_gap_window_ratio,
            exposure_overlap_policy.model_gap_window_min_px,
            exposure_overlap_policy.model_gap_window_max_px,
        )
        center = int(round(work_outer.left + gap.center))
        start, end = center - half, center + half + 1
    start = max(work_outer.left, min(work_outer.right, start))
    end = max(start + 1, min(work_outer.right, end))
    signal_gap = Gap(
        gap.index,
        gap.center,
        gap.score,
        gap.method,
        float(start - work_outer.left),
        float(end - work_outer.left),
        gap.lane_box,
    )
    signals = hard_gap_pixel_signals(gray_work, work_outer, signal_gap, pitch, hard_gap_trust_policy)
    if signals is None:
        record["signals"] = {"available": False}
        return record

    record["signals"] = {
        "available": True,
        "core_mean": signals.core_mean,
        "core_content": signals.core_content,
        "core_dark": signals.core_dark,
        "core_activity": signals.core_activity,
        "left_content": signals.left_content,
        "right_content": signals.right_content,
        "side_content": signals.side_content,
        "side_balance": signals.side_balance,
        "continuity": signals.continuity,
        "window": {"start": int(signals.start), "end": int(signals.end), "guard": int(signals.guard)},
    }
    width_ratio = hard_gap_width_ratio(gap, pitch)
    model_delta_ratio = abs(float(gap.center - expected)) / max(1.0, float(pitch))
    if is_hard_gap_method(gap.method):
        trust_assessment = diagnostic_hard_gap_trust_assessment(
            gap,
            pitch,
            hard_gap_trust_policy,
            width_ratio=width_ratio,
            model_delta_ratio=model_delta_ratio,
            nearby_separator_conflict=False,
            signals=signals,
        )
        record["hard_trust"] = trust_assessment.trust
        record["hard_trust_detail"] = trust_assessment.detail()
    elif is_model_gap_method(gap.method):
        if hard_gap_tonal_separator_like(signals, hard_gap_trust_policy):
            exposure_overlap_class = "none"
        elif (
            signals.continuity >= exposure_overlap_policy.strong_continuity
            and signals.core_activity >= exposure_overlap_policy.strong_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            exposure_overlap_class = "strong"
        elif (
            signals.continuity >= exposure_overlap_policy.medium_continuity
            and signals.core_activity >= exposure_overlap_policy.medium_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            exposure_overlap_class = "medium"
        elif (
            signals.continuity >= exposure_overlap_policy.weak_continuity
            and signals.core_activity >= exposure_overlap_policy.weak_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            exposure_overlap_class = "weak"
        else:
            exposure_overlap_class = "none"
        record["exposure_overlap_class"] = exposure_overlap_class
        record["exposure_overlap_like"] = exposure_overlap_class in {"medium", "strong"}
    return record
