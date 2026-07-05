from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from ....constants import (
    ANALYSIS_SOURCE_CONTENT,
    ANALYSIS_SOURCE_SEPARATOR,
    REASON_AUTO_GATE_NOT_SATISFIED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ....domain import Detection
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ....utils import HARD_REVIEW_REASONS
from ...evidence.content_evidence import content_evidence_detail
from ...evidence.separator_summary import separator_gate_detail_summary
from .gates import assess_separator_gate
from .partial_holder import partial_extra_holder_frames_gate_detail
from .scoring import (
    content_support_score,
    geometry_support_score,
    hard_full_calibration_floor_applies,
    separator_geometry_support_applies,
    separator_support_score,
)


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
    separator_gate_ok, separator_gate_detail = assess_separator_gate(
        candidate,
        config.confidence_threshold,
        policy,
    )
    content_detail = content_evidence_detail(gray, candidate, cache, policy.content)
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
    content_score = content_support_score(content_detail, fmt.name, policy.content)
    geometry_score = geometry_support_score(candidate, content_detail, policy)
    separator_score = (
        separator_support_score(candidate, separator_gate_detail, policy)
        if source == "separator"
        else 0.0
    )
    source_bias = (
        scoring_policy.separator_source_bias
        if source == "separator"
        else 0.0
    )
    joint_score = (
        scoring_policy.geometry_weight * geometry_score
        + scoring_policy.content_weight * content_score
        + scoring_policy.separator_weight * separator_score
        + source_bias
    )
    joint_score = max(0.0, min(1.0, joint_score))
    support = str(content_detail.get("support", ""))
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
        content_detail,
        fmt,
        source,
        joint_score,
        content_score,
        geometry_score,
        cache,
        policy,
    )
    partial_safe_extra_frames_ok = bool(partial_safe_extra_frames.get("ok", False))
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
                    "too_few_broad_separator_width_gaps",
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
    if partial_safe_extra_frames_ok:
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["ok"] = True
        separator_gate_detail["reason"] = "partial_safe_extra_frames_support"
        separator_gate_detail["partial_safe_extra_frames_support"] = True
        reasons = [
            reason
            for reason in reasons
            if reason
            not in {
                "partial_strip_count_candidate",
                "partial_too_ambiguous",
                REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
                "weak_separators",
                "outer_box_too_large",
                "outer_box_uncertain",
            }
        ]
    hard_reasons = HARD_REVIEW_REASONS.intersection(reasons)
    auto_gate = False
    if source == "separator":
        auto_gate = (
            (separator_gate_ok or partial_safe_extra_frames_ok)
            and support == "ok"
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
    broad_width_count = int(
        separator_gate_detail.get("broad_separator_width_gaps", 0) or 0
    )
    if source == "separator" and broad_width_count > 0:
        confidence = min(confidence, policy.separator.separator_width_profile_confidence_cap)

    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    candidate.review_reasons = sorted(set(reasons))
    candidate.detail["analysis_source"] = (
        ANALYSIS_SOURCE_SEPARATOR if source == "separator" else ANALYSIS_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["candidate_assessment"] = {
        "source": source,
        "joint_score": float(joint_score),
        "auto_gate": bool(auto_gate),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_support": support,
        "separator_hard_evidence": separator_gate_detail,
        "partial_extra_holder_frames": partial_safe_extra_frames,
        "partial_safe_extra_frames": partial_safe_extra_frames,
    }
    return candidate
