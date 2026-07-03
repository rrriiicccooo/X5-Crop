from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import Detection
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from ..evidence.content_evidence import content_evidence_detail
from .scoring import detail_float


def select_full_separator_width_profile_candidate(
    gray: np.ndarray,
    candidates: list[Detection],
    current_best: Detection,
    threshold: float,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> Optional[Detection]:
    separator_width_profile = policy.outer.proposal.geometry.separator.width_profile
    required_count = int(separator_width_profile.required_count)
    if (
        separator_width_profile.mode == "off"
        or not separator_width_profile.full_selection_enabled
        or current_best.strip_mode not in separator_width_profile.full_selection_strip_modes
        or (
            separator_width_profile.full_selection_requires_required_count
            and required_count > 0
            and current_best.count != required_count
        )
    ):
        return None
    separator_width_profile_candidates = [
        detection
        for detection in candidates
        if str(detection.detail.get("outer_candidate_strategy", "")) == "separator_outer"
        and str(detection.detail.get("outer_candidate", "")).startswith("separator_width_profile_")
    ]
    if not separator_width_profile_candidates:
        return None

    current_content = content_evidence_detail(gray, current_best, cache, policy.content)
    current_support = str(current_content.get("support", ""))
    current_reasons = set(current_best.review_reasons)
    current_needs_help = (
        current_best.confidence < threshold
        or current_support in set(separator_width_profile.full_selection_help_supports)
        or bool(current_reasons.intersection(separator_width_profile.full_selection_help_reasons))
    )
    if separator_width_profile.full_selection_requires_help and not current_needs_help:
        return None

    scored: list[tuple[tuple[int, int, float, float, float], Detection]] = []
    for detection in separator_width_profile_candidates:
        content_detail = content_evidence_detail(gray, detection, cache, policy.content)
        support = str(content_detail.get("support", ""))
        if support != separator_width_profile.full_selection_required_support:
            continue
        hard_gaps = sum(1 for gap in detection.gaps if gap.method != "equal")
        equal_gaps = int(detection.detail.get("equal_gaps", 0) or 0)
        if hard_gaps < max(1, detection.count - 1):
            continue
        if equal_gaps > 0 and not separator_width_profile.full_selection_allow_equal_gaps:
            continue
        width_cv = detail_float(detection.detail, "width_cv", 1.0)
        median_coverage = detail_float(content_detail, "median_coverage", 0.0)
        scored.append(
            (
                (
                    1 if detection.confidence >= threshold else 0,
                    hard_gaps,
                    median_coverage,
                    float(detection.confidence),
                    -width_cv,
                ),
                detection,
            )
        )
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]
