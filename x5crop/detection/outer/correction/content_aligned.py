from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from ....domain import Detection
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....runtime import AnalysisCache
from ....runtime_config import RuntimeConfig
from ...evidence.outer_alignment import corrected_outer_from_alignment, outer_content_alignment_detail


def retry_with_content_aligned_outer(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    from ...candidate.build import build_detection_for_outer
    from ...candidate.candidate_assessment import apply_candidate_assessment_policy
    from ...evidence.content_evidence import content_evidence_detail

    if detection.strip_mode != "full":
        return None
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_from_alignment(alignment, detection.count, policy)
    if corrected_outer is None:
        return None

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", policy.separator.wide_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "content_aligned_outer",
        "content_aligned_retry",
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
        policy=policy,
    )
    retried = apply_candidate_assessment_policy(gray, retried, config, fmt, "separator", cache, policy=policy)
    if gap_override is not None:
        retried.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["content_evidence"] = retry_content
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": alignment.get("reason"),
        "source_edge_hard_anchors": bool(alignment.get("edge_hard_anchors", False)),
        "source_white_edge_slack": bool(alignment.get("white_edge_slack", False)),
        "original_outer_work_box": alignment.get("outer_work_box"),
        "content_work_box": alignment.get("content_work_box"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    return retried
