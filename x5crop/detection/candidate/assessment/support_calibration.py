from __future__ import annotations

import math
from typing import Any

from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.runtime.separator import SeparatorGeometrySupportModePolicy
from ...evidence.photo_width import photo_width_within_limit
from ...evidence.separator_summary import separator_support_detail_summary


def detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key, None)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def separator_geometry_support_applies(
    candidate: DetectionCandidate,
    hard_detail: dict[str, Any],
    fmt: FormatPhysicalSpec,
    source: str,
    support: str,
    joint_score: float,
    mode_policy: SeparatorGeometrySupportModePolicy,
) -> bool:
    evidence = separator_support_detail_summary(hard_detail)
    outer_area = detail_float(candidate.detail, "outer_area_ratio", 1.0)
    min_hard = int(math.ceil(evidence.expected_gaps * mode_policy.min_hard_ratio))
    support_gap_count = evidence.hard_separator_gaps + evidence.grid_model_gaps
    return (
        source == "separator"
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and evidence.expected_gaps > 0
        and evidence.hard_separator_gaps >= min_hard
        and support_gap_count >= evidence.expected_gaps
        and evidence.equal_model_gaps <= mode_policy.max_equal_gaps
        and photo_width_within_limit(
            candidate.detail,
            mode_policy.max_photo_width_cv,
            unavailable_ok=True,
        )
        and support == mode_policy.required_content_support
        and joint_score >= mode_policy.min_joint_score
        and outer_area <= mode_policy.max_outer_area_ratio
    )
