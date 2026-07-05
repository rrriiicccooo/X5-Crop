from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ....domain import Detection
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ..proposal.correction.types import OuterCorrectionProposal


def build_assessed_corrected_outer_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    corrected: OuterCorrectionProposal,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    from ...evidence.content_evidence import content_evidence_detail
    from ...evidence.outer_alignment import outer_content_alignment_detail
    from ...gap_profiles import BROAD_WIDTH_GAP_PROFILE, STANDARD_GAP_PROFILE, broad_width_gap_profile_detail
    from ..assessment.candidate import apply_candidate_assessment_policy
    from .detection import build_detection_for_outer

    gap_override: Optional[float] = None
    gap_profile = STANDARD_GAP_PROFILE
    gap_search_profile = detection.detail.get("gap_search_profile")
    separator_width_profile = detection.detail.get("separator_width_profile")
    broad_width_detail = gap_search_profile if isinstance(gap_search_profile, dict) else separator_width_profile
    if (
        corrected.preserve_separator_width_profile
        and isinstance(broad_width_detail, dict)
        and bool(broad_width_detail.get("used", False))
        and str(broad_width_detail.get("profile", BROAD_WIDTH_GAP_PROFILE)) == BROAD_WIDTH_GAP_PROFILE
    ):
        gap_profile = BROAD_WIDTH_GAP_PROFILE
        gap_override = float(
            broad_width_detail.get(
                "gap_max_width_ratio",
                policy.separator.width_profile.max_width_ratio,
            )
        )

    reassessed = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected.box,
        float(detection.detail.get("offset_fraction", 0.0)),
        corrected.name,
        corrected.strategy,
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
        gap_search_profile=gap_profile,
        policy=policy,
    )
    reassessed = apply_candidate_assessment_policy(gray, reassessed, config, fmt, "separator", cache, policy=policy)
    if gap_override is not None:
        profile_detail = broad_width_gap_profile_detail(
            policy.separator,
            gap_override,
            preserved_through_outer_correction_candidate=True,
        )
        reassessed.detail["gap_search_profile"] = profile_detail
        reassessed.detail["separator_width_profile"] = profile_detail

    reassessed_alignment = outer_content_alignment_detail(gray, reassessed, cache, policy=policy)
    reassessed_content = content_evidence_detail(gray, reassessed, cache, policy.content)
    reassessed.detail["outer_content_alignment"] = reassessed_alignment
    reassessed.detail["content_evidence"] = reassessed_content
    reassessed.detail["outer_correction"] = {
        "used": True,
        "source_reason": corrected.source_reason,
        "original_outer_work_box": corrected.original_outer_work_box,
        "corrected_outer_work_box": asdict(corrected.box),
        "suppress_outer_mismatch": bool(corrected.suppress_outer_mismatch),
        "reassessed_alignment": reassessed_alignment,
        "reassessed_content_support": reassessed_content.get("support"),
        "candidate_reassessment": {
            "used": True,
            "owner": "candidate",
            "source": "separator",
        },
    }
    reassessed.detail["outer_correction"].update(corrected.detail)
    return reassessed


__all__ = [
    "build_assessed_corrected_outer_candidate",
]
