from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ....cache import AnalysisCache
from ....domain import Detection
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig
from ...physical.outer.correction.types import OuterCorrectionProposal


def build_assessed_corrected_outer_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    corrected: OuterCorrectionProposal,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    from ...evidence.content.frame_support import content_evidence_detail
    from ...evidence.outer_alignment import outer_content_alignment_detail
    from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE, width_aware_gap_profile_detail
    from ..assessment.candidate import apply_candidate_assessment_policy
    from ..build.detection import build_detection_for_outer

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
        outer_candidate_detail={
            "family": "outer_correction",
            "source_reason": corrected.source_reason,
            "original_outer_work_box": corrected.original_outer_work_box,
            **corrected.detail,
        },
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=None,
        gap_search_profile=WIDTH_AWARE_GAP_PROFILE,
        policy=policy,
    )
    reassessed = apply_candidate_assessment_policy(gray, reassessed, config, fmt, "separator", cache, policy=policy)
    profile_detail = width_aware_gap_profile_detail(policy.separator)
    profile_detail["preserved_through_outer_correction_candidate"] = bool(
        corrected.preserve_gap_search_profile
    )
    reassessed.detail["gap_search_profile"] = profile_detail

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
            "owner": "candidate.extension",
            "source": "separator",
        },
    }
    reassessed.detail["outer_correction"].update(corrected.detail)
    return reassessed


__all__ = [
    "build_assessed_corrected_outer_candidate",
]
