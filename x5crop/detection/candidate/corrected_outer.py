from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

from ...domain import Box, Detection
from ...formats import FormatSpec
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from ...runtime_config import RuntimeConfig


@dataclass(frozen=True)
class CorrectedOuterCandidateInput:
    box: Box
    name: str
    strategy: str
    source_reason: str
    original_outer_work_box: Any
    preserve_separator_width_profile: bool = False
    suppress_outer_mismatch: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


def build_assessed_corrected_outer_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    corrected: CorrectedOuterCandidateInput,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    from ..evidence.content_evidence import content_evidence_detail
    from ..evidence.outer_alignment import outer_content_alignment_detail
    from .build import build_detection_for_outer
    from .candidate_assessment import apply_candidate_assessment_policy

    gap_override: Optional[float] = None
    separator_width_profile = detection.detail.get("separator_width_profile")
    if (
        corrected.preserve_separator_width_profile
        and isinstance(separator_width_profile, dict)
        and bool(separator_width_profile.get("used", False))
    ):
        gap_override = float(
            separator_width_profile.get(
                "gap_max_width_ratio",
                policy.separator.separator_width_profile_max_width_ratio,
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
        policy=policy,
    )
    reassessed = apply_candidate_assessment_policy(gray, reassessed, config, fmt, "separator", cache, policy=policy)
    if gap_override is not None:
        reassessed.detail["separator_width_profile"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_correction_candidate": True,
        }

    reassessed_alignment = outer_content_alignment_detail(gray, reassessed, cache, policy=policy)
    reassessed_content = content_evidence_detail(gray, reassessed, cache, policy.content)
    reassessed.detail["outer_content_alignment"] = reassessed_alignment
    reassessed.detail["content_evidence"] = reassessed_content
    reassessed.detail["outer_correction"] = {
        "used": True,
        "source_reason": corrected.source_reason,
        "original_outer_work_box": corrected.original_outer_work_box,
        "corrected_outer_work_box": asdict(corrected.box),
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
    "CorrectedOuterCandidateInput",
    "build_assessed_corrected_outer_candidate",
]
