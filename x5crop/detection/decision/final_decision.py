from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...constants import (
    CANDIDATE_SOURCE_REVIEW_ONLY,
)
from ...domain import Detection
from ...formats import FormatSpec
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..confidence_caps import apply_confidence_cap
from ..evidence.content.containment import content_containment_detail
from ..evidence.content.frame_support import content_evidence_detail
from ..evidence.outer_alignment import outer_content_alignment_detail
from ..evidence.output_overlap import output_overlap_evidence_detail
from .contract_applier import apply_decision_contract


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
    fmt: FormatSpec,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
    policy: DetectionPolicy,
) -> FinalDecisionResult:
    raw_content_detail = content_evidence_detail(gray, detection, analysis_cache, policy.content)
    content_detail = content_containment_detail(
        raw_content_detail,
        policy.content.evidence,
        expected_count=detection.count,
    )
    detection.detail["content_evidence"] = raw_content_detail
    detection.detail["content_containment"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(gray, detection, analysis_cache, policy=policy)
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
    _apply_decision_confidence_caps(
        detection,
        config,
        policy,
        content_detail,
        outer_alignment,
    )
    detection = apply_decision_contract(
        gray,
        detection,
        config,
        fmt,
        content_detail,
        outer_alignment,
        deskew_detail,
    )
    status = _decision_status_for(detection, config.confidence_threshold)
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
        )


def _apply_decision_confidence_caps(
    detection: Detection,
    config: RuntimeConfig,
    policy: DetectionPolicy,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
) -> None:
    cap_details = detection.detail.setdefault("decision_confidence_caps", [])
    if not isinstance(cap_details, list):
        cap_details = []
        detection.detail["decision_confidence_caps"] = cap_details
    review_only_mode = detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
    suppress_outer_mismatch = _suppress_outer_mismatch(detection)
    if not review_only_mode and bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            detection.confidence, cap_detail = apply_confidence_cap(
                detection.confidence,
                policy.decision.content_aspect_conflict_cap,
                owner="decision",
                reason="content_aspect_conflict",
            )
            cap_details.append(cap_detail)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                detection.confidence,
                policy.decision.content_low_confidence_cap,
                owner="decision",
                reason="content_low_confidence",
            )
            cap_details.append(cap_detail)
    if (
        not review_only_mode
        and not suppress_outer_mismatch
        and bool(outer_alignment.get("used", False))
        and not bool(outer_alignment.get("ok", True))
    ):
        detection.confidence, cap_detail = apply_confidence_cap(
            detection.confidence,
            policy.decision.outer_mismatch_cap,
            owner="decision",
            reason="outer_content_mismatch",
        )
        cap_details.append(cap_detail)
def _suppress_outer_mismatch(detection: Detection) -> bool:
    outer_correction_detail = detection.detail.get("outer_correction", {})
    return bool(
        isinstance(outer_correction_detail, dict)
        and outer_correction_detail.get("suppress_outer_mismatch", False)
    )


def _decision_status_for(detection: Detection, confidence_threshold: float) -> str:
    if detection.confidence >= confidence_threshold and not detection.review_reasons:
        return "approved_auto"
    return "needs_review"


__all__ = [
    "FinalDecisionResult",
    "apply_detection_decision",
]
