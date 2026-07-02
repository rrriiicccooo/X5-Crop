from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..utils import clamp_float, clamp_int
from .nearby_separator import nearby_separator_replacement
from .detection_parameters import HardGapTrustParameters, NearbySeparatorCorrectionParameters


def light_hard_gap_trust(
    gap: Gap,
    pitch: float,
    *,
    predicted: Optional[float] = None,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    hard_gap_trust: HardGapTrustParameters | None = None,
    nearby_correction: NearbySeparatorCorrectionParameters | None = None,
) -> tuple[str, dict[str, Any]]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0:
        return "not_hard_gap", {"reason": "not_hard_gap"}
    trust_config = hard_gap_trust or HardGapTrustParameters()
    width_ratio = float(gap.width) / max(1.0, float(pitch))
    detail: dict[str, Any] = {
        "width_ratio": float(width_ratio),
        "score": float(gap.score),
    }
    if profile is not None:
        nearby = nearby_separator_replacement(profile, gap, pitch, nearby_correction)
        if nearby is not None:
            detail["nearby_separator_candidate"] = nearby
            return "nearby_separator_conflict", detail
    if predicted is not None:
        model_delta_ratio = abs(float(gap.center) - float(predicted)) / max(1.0, float(pitch))
        detail["model_delta_ratio"] = float(model_delta_ratio)
        if model_delta_ratio >= trust_config.model_delta_ratio and (
            width_ratio < trust_config.geometry_width_ratio or gap.score < trust_config.model_conflict_score
        ):
            return "geometry_conflict", detail
    if gray_work is not None and outer is not None and gap.start is not None and gap.end is not None:
        start = int(round(outer.left + min(gap.start, gap.end)))
        end = int(round(outer.left + max(gap.start, gap.end)))
        start = max(outer.left, min(outer.right, start))
        end = max(start + 1, min(outer.right, end))
        guard = clamp_int(
            max(float(end - start), pitch * trust_config.guard_ratio),
            trust_config.guard_min,
            trust_config.guard_max,
        )
        left_start = max(outer.left, start - guard)
        right_end = min(outer.right, end + guard)
        core = gray_work[outer.top:outer.bottom, start:end]
        left = gray_work[outer.top:outer.bottom, left_start:start]
        right = gray_work[outer.top:outer.bottom, end:right_end]
        if core.size:
            core_mean = float(core.mean())
            core_content = float((core < trust_config.core_content_threshold).mean())
            core_dark = float((core < trust_config.core_dark_threshold).mean())
            core_activity = float(core.std() / 255.0)
            left_content = float((left < trust_config.core_content_threshold).mean()) if left.size else 0.0
            right_content = float((right < trust_config.core_content_threshold).mean()) if right.size else 0.0
            continuity = min(core_content, min(left_content, right_content))
            dark_separator_like = (
                core_mean <= trust_config.dark_mean_max
                and core_dark >= trust_config.dark_fraction_min
                and core_activity <= trust_config.dark_activity_max
            )
            weak_dark_gap = core_mean >= trust_config.weak_mean_min and core_content >= trust_config.weak_content_min
            narrow_hard = 0.0 < gap.width <= clamp_float(
                pitch * trust_config.narrow_ratio,
                trust_config.narrow_min,
                trust_config.narrow_max,
            )
            detail["signals"] = {
                "core_mean": core_mean,
                "core_content": core_content,
                "core_dark": core_dark,
                "core_activity": core_activity,
                "continuity": continuity,
            }
            if width_ratio < trust_config.frame_border_width_ratio and dark_separator_like:
                return "suspect_frame_border", detail
            if narrow_hard and (
                (continuity >= trust_config.continuity_min and core_activity >= trust_config.activity_min)
                or weak_dark_gap
            ):
                return "suspect_internal_edge", detail
    if gap.score >= trust_config.strong_min_score and trust_config.strong_width_min <= width_ratio <= trust_config.strong_width_max:
        return "strong_separator", detail
    if gap.score >= trust_config.narrow_ok_score and trust_config.narrow_ok_width_min <= width_ratio < trust_config.narrow_ok_width_max:
        return "narrow_but_ok", detail
    return "weak_or_ambiguous_separator", detail
