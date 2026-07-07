from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from ....constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_SEPARATOR,
    REASON_AUTO_GATE_NOT_SATISFIED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ....domain import Detection
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ....utils import HARD_REVIEW_REASONS
from ...evidence.content.containment import content_containment_detail
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.separator_summary import separator_gate_detail_summary
from .base_scoring import apply_base_detection_scoring
from .content_candidate import content_candidate_assessment_from_proposal
from .evidence_independence import evidence_independence_detail
from .gate_support import (
    hard_full_calibration_floor_applies,
    separator_geometry_support_applies,
)
from .gates import assess_separator_gate
from .partial_holder import partial_extra_holder_frames_gate_detail
from .scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
    joint_support_score,
    separator_support_score,
)


def _detail_float(detail: dict, key: str, default: float) -> float:
    value = detail.get(key)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def apply_candidate_assessment_policy(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    source: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    candidate = replace(
        detection,
        review_reasons=list(detection.review_reasons),
        detail=dict(detection.detail),
    )
    policy = policy or get_detection_policy(fmt.name, candidate.strip_mode)
    if source == "separator":
        gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
        candidate = apply_base_detection_scoring(
            gray_work,
            candidate,
            config,
            fmt,
            policy,
        )
    elif source == "content":
        proposal_confidence, proposal_reasons, proposal_detail = content_candidate_assessment_from_proposal(
            candidate,
            config,
            policy.content,
        )
        candidate.confidence = max(float(candidate.confidence), float(proposal_confidence))
        candidate.review_reasons = sorted(set([*candidate.review_reasons, *proposal_reasons]))
        content_primary = candidate.detail.get("content_primary")
        if isinstance(content_primary, dict):
            content_primary["candidate_assessment"] = proposal_detail
    separator_gate_ok, separator_gate_detail = assess_separator_gate(
        candidate,
        config.confidence_threshold,
        policy,
    )
    content_detail = content_evidence_detail(gray, candidate, cache, policy.content)
    containment_detail = content_containment_detail(
        content_detail,
        policy.content.evidence,
        expected_count=candidate.count,
    )
    scoring_policy = policy.scoring
    floor_applies = hard_full_calibration_floor_applies(
        candidate,
        separator_gate_detail,
        fmt,
        source,
        policy,
    )
    if floor_applies:
        gate_candidate = replace(
            candidate,
            confidence=max(
                float(candidate.confidence),
                scoring_policy.hard_full_confidence_floor,
            ),
        )
        separator_gate_ok, separator_gate_detail = assess_separator_gate(
            gate_candidate,
            config.confidence_threshold,
            policy,
        )
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["calibrate_hard_full_confidence_floor_applied"] = True
        separator_gate_detail["calibrate_hard_full_confidence_floor"] = float(
            scoring_policy.hard_full_confidence_floor
        )
    content_score = content_support_score(containment_detail)
    content_quality = content_quality_score(containment_detail, fmt.name, policy.content)
    geometry_score = geometry_support_score(candidate, containment_detail, policy)
    separator_score = (
        separator_support_score(candidate, separator_gate_detail, policy)
        if source == "separator"
        else 0.0
    )
    joint_score = joint_support_score(
        geometry_score=geometry_score,
        content_score=content_score,
        separator_score=separator_score,
        source=source,
        policy=policy,
    )
    support = str(containment_detail.get("support", ""))
    content_containment_ok = bool(containment_detail.get("content_containment_ok", False))
    content_harm_risk = bool(containment_detail.get("content_harm_risk", True))
    reasons = list(candidate.review_reasons)
    if floor_applies:
        reasons = [reason for reason in reasons if reason != "low_confidence"]
    detected_geometry_policy = policy.separator.geometry_support.detected_geometry
    stable_grid_policy = policy.separator.geometry_support.stable_grid
    detected_geometry_support = (
        (not separator_gate_ok)
        and detected_geometry_policy.enabled
    ) and separator_geometry_support_applies(
        candidate,
        separator_gate_detail,
        fmt,
        source,
        support,
        joint_score,
        detected_geometry_policy,
    )
    stable_grid_support = (
        False
        if detected_geometry_support
        or not stable_grid_policy.enabled
        else separator_geometry_support_applies(
            candidate,
            separator_gate_detail,
            fmt,
            source,
            support,
            joint_score,
            stable_grid_policy,
        )
    )
    if detected_geometry_support or stable_grid_support:
        separator_gate_ok = True
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["ok"] = True
        if detected_geometry_support:
            separator_gate_detail["reason"] = "separator_detected_geometry_support"
            separator_gate_detail["separator_geometry_support_mode"] = "detected_geometry"
        else:
            separator_gate_detail["reason"] = "separator_stable_grid_support"
            separator_gate_detail["separator_geometry_support_mode"] = "stable_grid"
        reasons = [reason for reason in reasons if reason != "outer_box_too_large"]

    outer_candidate_strategy = str(candidate.detail.get("outer_candidate_strategy", ""))
    if source == "separator" and outer_candidate_strategy == "edge_anchor_outer":
        hard_count = separator_gate_detail_summary(separator_gate_detail).hard_separator_gaps
        if hard_count <= 0:
            separator_gate_ok = False
            separator_gate_detail = dict(separator_gate_detail)
            separator_gate_detail["ok"] = False
            separator_gate_detail["reason"] = "edge_anchor_needs_hard_separator"
            separator_gate_detail["edge_anchor_needs_hard_separator"] = True
            reasons.append("edge_anchor_separator_weak")

    content_guided_hard_separator_missing = False
    content_guided_detail = candidate.detail.get("content_guided_separator", {})
    if source == "separator" and isinstance(content_guided_detail, dict) and bool(content_guided_detail.get("used", False)):
        hard_count = separator_gate_detail_summary(separator_gate_detail).hard_separator_gaps
        if hard_count <= 0:
            content_guided_hard_separator_missing = True
            separator_gate_ok = False
            separator_gate_detail = dict(separator_gate_detail)
            separator_gate_detail["ok"] = False
            separator_gate_detail["reason"] = policy.candidate_plan.content_guided_separator.requires_hard_separator_reason
            separator_gate_detail["content_guided_separator_needs_hard_separator"] = True
            reasons.append(policy.candidate_plan.content_guided_separator.requires_hard_separator_reason)

    if source == "separator" and not separator_gate_ok:
        reasons.append(REASON_SEPARATOR_HARD_EVIDENCE_WEAK)
    if support == "aspect_conflict":
        reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
    elif support == "low_content":
        reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    elif support == "weak":
        reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if source == "content":
        reasons.append("content_only_not_enough_for_auto")

    confidence = max(float(candidate.confidence), joint_score)
    if floor_applies:
        confidence = max(confidence, scoring_policy.hard_full_confidence_floor)
    partial_safe_extra_frames = partial_extra_holder_frames_gate_detail(
        gray,
        candidate,
        separator_gate_detail,
        containment_detail,
        fmt,
        source,
        joint_score,
        content_quality,
        geometry_score,
        cache,
        policy,
    )
    partial_safe_extra_frames_ok = bool(partial_safe_extra_frames.get("ok", False))
    partial_safe_auto_support_ok = partial_safe_extra_frames_ok and not content_guided_hard_separator_missing
    partial_safe_disqualifiers = set(
        partial_safe_extra_frames.get("disqualifiers", [])
    )
    partial_safe_blocks_auto = (
        policy.partial_holder.safe_extra_frames
        and policy.partial_holder.checks_leading_content
        and policy.partial_holder.checks_frame_content
        and candidate.strip_mode == "partial"
        and source == "separator"
        and bool(partial_safe_extra_frames.get("used", False))
        and bool(
            partial_safe_disqualifiers.intersection(
                {
                    "holder_edge_disambiguation_weak",
                    "partial_outer_leading_content",
                    "partial_frame_content_unstable",
                }
            )
        )
    )
    if partial_safe_blocks_auto:
        separator_gate_ok = False
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["ok"] = False
        separator_gate_detail["reason"] = "partial_safe_extra_frames_blocked"
        separator_gate_detail["partial_safe_extra_frames_blocked"] = sorted(
            partial_safe_disqualifiers
        )
        reasons.extend(sorted(partial_safe_disqualifiers))
    if partial_safe_auto_support_ok:
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["ok"] = True
        separator_gate_detail["reason"] = "partial_safe_extra_frames_support"
        separator_gate_detail["partial_safe_extra_frames_support"] = True
        reasons = [
            reason
            for reason in reasons
            if reason
            not in {
                "partial_too_ambiguous",
                REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
                "weak_separators",
                "outer_box_too_large",
                "outer_box_uncertain",
            }
        ]
    independence_detail = evidence_independence_detail(
        candidate,
        source=source,
        content_support=support,
        content_score=content_quality,
        geometry_score=geometry_score,
        policy=policy.candidate_plan.evidence_independence,
    )
    evidence_independence_ok = bool(independence_detail.get("ok", True))
    if source == "separator":
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["evidence_independence"] = independence_detail
    if not evidence_independence_ok:
        reasons.append(
            str(
                independence_detail.get("reason")
                or policy.candidate_plan.evidence_independence.review_reason
            )
        )
    hard_reasons = HARD_REVIEW_REASONS.intersection(reasons)
    auto_gate = False
    if source == "separator":
        auto_gate = (
            (separator_gate_ok or partial_safe_auto_support_ok)
            and content_containment_ok
            and not content_harm_risk
            and evidence_independence_ok
            and not hard_reasons
        )
    elif source == "content":
        auto_gate = False

    if not auto_gate:
        cap = (
            scoring_policy.no_auto_cap_partial
            if candidate.strip_mode == "partial"
            else scoring_policy.no_auto_cap_full
        )
        confidence = min(confidence, cap)
        reasons.append(REASON_AUTO_GATE_NOT_SATISFIED)
    else:
        confidence = max(confidence, config.confidence_threshold + min(0.10, joint_score * 0.08))
    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    candidate.review_reasons = sorted(set(reasons))
    candidate.detail["candidate_source"] = (
        CANDIDATE_SOURCE_SEPARATOR if source == "separator" else CANDIDATE_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["content_containment"] = containment_detail
    candidate.detail["candidate_assessment"] = {
        "source": source,
        "joint_score": float(joint_score),
        "auto_gate": bool(auto_gate),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_score_role": "content_containment_support",
        "content_quality_score": float(content_quality),
        "content_quality_score_role": "quality_diagnostic_not_hard_gate",
        "width_cv": _detail_float(candidate.detail, "width_cv", 1.0),
        "width_cv_source": str(candidate.detail.get("width_cv_source") or "unknown"),
        "photo_width_cv": candidate.detail.get("photo_width_cv"),
        "frame_box_width_cv": candidate.detail.get("frame_box_width_cv"),
        "separator_width_cv": candidate.detail.get("separator_width_cv"),
        "content_support": support,
        "content_containment_ok": bool(content_containment_ok),
        "content_harm_risk": bool(content_harm_risk),
        "content_containment": containment_detail,
        "separator_hard_evidence": separator_gate_detail,
        "evidence_independence": independence_detail,
        "partial_extra_holder_frames": partial_safe_extra_frames,
        "partial_safe_extra_frames": partial_safe_extra_frames,
    }
    return candidate
