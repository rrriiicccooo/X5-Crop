from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import Detection
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..evidence.content.containment import content_containment_detail
from ..evidence.content.frame_support import content_evidence_detail
from ..evidence.outer_alignment import outer_content_alignment_detail
from ..evidence.output_overlap import output_overlap_evidence_detail
from .contract_applier import apply_decision_contract
from ...policies.decision.contract import decision_contract_for_policy


@dataclass
class FinalDecisionResult:
    detection: Detection
    status: str
    content_detail: dict[str, Any]
    outer_alignment: dict[str, Any]


def apply_detection_decision(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
    policy: DetectionPolicy,
) -> FinalDecisionResult:
    raw_content_detail = content_evidence_detail(
        gray,
        detection,
        analysis_cache,
        content_policy=policy.content,
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
            content_containment_policy=policy.outer.correction.content_containment,
        )
        if policy.decision.align_outer_to_content
        else {"used": False, "reason": policy.decision.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment
    _attach_decision_output_evidence(
        gray,
        detection,
        policy,
        analysis_cache,
    )
    detection = apply_decision_contract(
        gray,
        detection,
        config,
        content_detail,
        outer_alignment,
        policy=decision_contract_for_policy(policy),
        deskew_detail=deskew_detail,
    )
    decision_summary = detection.detail.get("decision_summary", {})
    status = (
        str(decision_summary.get("status"))
        if isinstance(decision_summary, dict) and decision_summary.get("status")
        else "needs_review"
    )
    return FinalDecisionResult(
        detection=detection,
        status=status,
        content_detail=content_detail,
        outer_alignment=outer_alignment,
    )


def _attach_decision_output_evidence(
    gray: np.ndarray,
    detection: Detection,
    policy: DetectionPolicy,
    analysis_cache: AnalysisCache,
) -> None:
    if (
        policy.output_evidence.output_overlap.enabled
        and not isinstance(detection.detail.get("output_overlap_evidence"), dict)
    ):
        detection.detail["output_overlap_evidence"] = output_overlap_evidence_detail(
            gray,
            detection,
            analysis_cache,
            separator_policy=policy.separator,
            nearby_policy=policy.diagnostics.nearby_separator,
            output_overlap_policy=policy.output_evidence.output_overlap,
        )


__all__ = [
    "FinalDecisionResult",
    "apply_detection_decision",
]
