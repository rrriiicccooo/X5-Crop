from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import DetectionCandidate, FinalDetection
from ...policies.decision.contract import DetectionDecisionContract
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..evidence.content.containment import content_containment_detail
from ..evidence.content.frame_support import content_evidence_detail
from ..evidence.outer_alignment import outer_content_alignment_detail
from .contract_applier import apply_decision_contract


def apply_detection_decision(
    gray: np.ndarray,
    detection: DetectionCandidate,
    config: RuntimeConfig,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
    policy: DetectionPolicy,
    decision_contract: DetectionDecisionContract,
) -> FinalDetection:
    detection = deepcopy(detection)
    if not isinstance(detection.detail.get("exposure_overlap_evidence"), dict):
        raise ValueError("decision requires exposure_overlap_evidence")
    if not isinstance(detection.detail.get("output_protection_plan"), dict):
        raise ValueError("decision requires output_protection_plan")
    raw_content_detail = content_evidence_detail(
        gray,
        detection,
        analysis_cache,
        content_policy=policy.content,
        horizontal_frame_aspect=decision_contract.format.horizontal_content_aspect,
    )
    content_detail = content_containment_detail(
        raw_content_detail,
        policy.content.evidence,
        expected_count=detection.count,
    )
    detection.detail["content_evidence"] = raw_content_detail
    detection.detail["content_containment"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(
            gray,
            detection,
            analysis_cache,
            alignment_policy=policy.outer.alignment_evidence,
        )
        if policy.decision.align_outer_to_content
        else {"used": False, "reason": policy.decision.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment
    return apply_decision_contract(
        gray,
        detection,
        config,
        content_detail,
        outer_alignment,
        policy=decision_contract,
        deskew_detail=deskew_detail,
    )


__all__ = [
    "apply_detection_decision",
]
