from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from ....constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_SEPARATOR,
)
from ....domain import Detection
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....runtime.config import RuntimeConfig
from ...confidence_caps import apply_confidence_cap
from ...evidence.content.containment import content_containment_detail
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.separator_summary import separator_gate_detail_summary
from ..signals import (
    SIGNAL_CONTENT_ASPECT_CONFLICT,
    SIGNAL_CONTENT_EVIDENCE_WEAK,
    SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING,
    SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO,
    SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING,
    SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK,
    SIGNAL_PARTIAL_COUNT_AMBIGUOUS,
    SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
    SIGNAL_PARTIAL_LEADING_CONTENT_RISK,
    SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
    candidate_signals,
    merged_candidate_signals,
    set_candidate_signals,
)
from .base_scoring import apply_base_detection_scoring
from .content_candidate import content_candidate_assessment_from_proposal
from .evidence_independence import evidence_independence_detail
from .gate_support import (
    hard_full_calibration_floor_applies,
    separator_geometry_support_applies,
)
from .candidate_gate import candidate_gate_assessment
from .gates import assess_separator_gate
from .partial_holder import partial_safe_extra_frames_gate_detail
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


def _candidate_confidence_caps(candidate: Detection) -> list[dict]:
    caps = candidate.detail.get("candidate_confidence_caps", [])
    return list(caps) if isinstance(caps, list) else []


def apply_candidate_assessment_policy(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    source: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    candidate_detail = dict(detection.detail)
    initial_candidate_signals = candidate_signals(detection)
    if initial_candidate_signals:
        candidate_detail["candidate_signals"] = initial_candidate_signals
    candidate = replace(
        detection,
        review_reasons=[],
        detail=candidate_detail,
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
        proposal_assessment = content_candidate_assessment_from_proposal(
            candidate,
            config,
            policy.content,
        )
        candidate.confidence = max(
            float(candidate.confidence),
            float(proposal_assessment.confidence),
        )
        set_candidate_signals(
            candidate,
            merged_candidate_signals(candidate, proposal_assessment.diagnostics),
        )
        content_primary = candidate.detail.get("content_primary")
        if isinstance(content_primary, dict):
            content_primary["candidate_assessment"] = proposal_assessment.detail
        proposal_caps = proposal_assessment.detail.get("confidence_caps", [])
        if isinstance(proposal_caps, list):
            candidate.detail["candidate_confidence_caps"] = [
                *_candidate_confidence_caps(candidate),
                *proposal_caps,
            ]
    separator_gate_result = assess_separator_gate(
        candidate,
        config.confidence_threshold,
        policy,
    )
    separator_gate_ok = separator_gate_result.ok
    separator_gate_detail = separator_gate_result.detail
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
        separator_gate_result = assess_separator_gate(
            gate_candidate,
            config.confidence_threshold,
            policy,
        )
        separator_gate_ok = separator_gate_result.ok
        separator_gate_detail = separator_gate_result.detail
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
    signals = candidate_signals(candidate)
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

    outer_candidate_strategy = str(candidate.detail.get("outer_candidate_strategy", ""))
    if source == "separator" and outer_candidate_strategy == "edge_anchor_outer":
        hard_count = separator_gate_detail_summary(separator_gate_detail).hard_separator_gaps
        if hard_count <= 0:
            separator_gate_ok = False
            separator_gate_detail = dict(separator_gate_detail)
            separator_gate_detail["ok"] = False
            separator_gate_detail["reason"] = "edge_anchor_needs_hard_separator"
            separator_gate_detail["edge_anchor_needs_hard_separator"] = True
            signals.append(SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING)

    content_guided_hard_separator_missing = False
    content_guided_detail = candidate.detail.get("content_guided_separator", {})
    if source == "separator" and isinstance(content_guided_detail, dict) and bool(content_guided_detail.get("used", False)):
        hard_count = separator_gate_detail_summary(separator_gate_detail).hard_separator_gaps
        if hard_count <= 0:
            content_guided_hard_separator_missing = True
            separator_gate_ok = False
            separator_gate_detail = dict(separator_gate_detail)
            separator_gate_detail["ok"] = False
            separator_gate_detail["reason"] = policy.candidate_plan.content_guided_separator.requires_hard_separator_signal
            separator_gate_detail["content_guided_separator_needs_hard_separator"] = True
            signals.append(SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING)

    if source == "separator" and not separator_gate_ok:
        signals.append(SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK)
    if support == "aspect_conflict":
        signals.append(SIGNAL_CONTENT_ASPECT_CONFLICT)
    elif support == "low_content":
        signals.append(SIGNAL_CONTENT_EVIDENCE_WEAK)
    elif support == "weak":
        signals.append(SIGNAL_CONTENT_EVIDENCE_WEAK)
    if source == "content":
        signals.append(SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO)

    confidence = max(float(candidate.confidence), joint_score)
    if floor_applies:
        confidence = max(confidence, scoring_policy.hard_full_confidence_floor)
    partial_safe_extra_frames = partial_safe_extra_frames_gate_detail(
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
    partial_safe_candidate_gate_support_ok = (
        partial_safe_extra_frames_ok
        and not content_guided_hard_separator_missing
    )
    partial_safe_disqualifiers = set(
        partial_safe_extra_frames.get("disqualifiers", [])
    )
    partial_signal_map = {
        "holder_edge_disambiguation_weak": SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK,
        SIGNAL_PARTIAL_LEADING_CONTENT_RISK: SIGNAL_PARTIAL_LEADING_CONTENT_RISK,
        "partial_frame_content_unstable": SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
    }
    partial_safe_blocker_signals = {
        partial_signal_map[disqualifier]
        for disqualifier in partial_safe_disqualifiers
        if disqualifier in partial_signal_map
    }
    partial_safe_blocks_auto = (
        policy.partial_holder.safe_extra_frames
        and policy.partial_holder.checks_leading_content
        and policy.partial_holder.checks_frame_content
        and candidate.strip_mode == "partial"
        and source == "separator"
        and bool(partial_safe_extra_frames.get("used", False))
        and bool(
            partial_safe_blocker_signals.intersection(
                {
                    SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK,
                    SIGNAL_PARTIAL_LEADING_CONTENT_RISK,
                    SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
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
        signals.extend(sorted(partial_safe_blocker_signals))
    if partial_safe_candidate_gate_support_ok:
        separator_gate_detail = dict(separator_gate_detail)
        separator_gate_detail["ok"] = True
        separator_gate_detail["reason"] = "partial_safe_extra_frames_support"
        separator_gate_detail["partial_safe_extra_frames_support"] = True
        signals = [
            signal
            for signal in signals
            if signal
            not in {
                SIGNAL_PARTIAL_COUNT_AMBIGUOUS,
                SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
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
        signals.append(
            str(
                independence_detail.get("reason")
                or policy.candidate_plan.evidence_independence.candidate_signal
            )
        )
    candidate_gate = candidate_gate_assessment(
        source=source,
        separator_gate_ok=bool(separator_gate_ok),
        separator_gate_detail=separator_gate_detail,
        partial_safe_candidate_gate_support_ok=bool(
            partial_safe_candidate_gate_support_ok
        ),
        partial_safe_blocks_auto=bool(partial_safe_blocks_auto),
        partial_safe_disqualifiers=partial_safe_disqualifiers,
        content_containment_ok=bool(content_containment_ok),
        content_harm_risk=bool(content_harm_risk),
        content_support=support,
        evidence_independence_ok=bool(evidence_independence_ok),
        evidence_independence_detail=independence_detail,
        signals=signals,
    )
    confidence_caps = _candidate_confidence_caps(candidate)
    if not candidate_gate.passed:
        cap = (
            scoring_policy.no_auto_cap_partial
            if candidate.strip_mode == "partial"
            else scoring_policy.no_auto_cap_full
        )
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            cap,
            owner="candidate.assessment",
            reason="candidate_gate_failed",
        )
        confidence_caps.append(cap_detail)
    else:
        confidence = max(confidence, config.confidence_threshold + min(0.10, joint_score * 0.08))
    candidate_gate = candidate_gate.with_confidence_caps(confidence_caps)
    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    set_candidate_signals(candidate, signals)
    candidate.detail["candidate_source"] = (
        CANDIDATE_SOURCE_SEPARATOR if source == "separator" else CANDIDATE_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["content_containment"] = containment_detail
    candidate.detail["candidate_assessment"] = {
        "source": source,
        "joint_score": float(joint_score),
        "candidate_gate_passed": bool(candidate_gate.passed),
        "gate": candidate_gate.report_detail(),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_score_role": "content_containment_support",
        "content_quality_score": float(content_quality),
        "content_quality_score_role": "quality_diagnostic_not_hard_gate",
        "blockers": candidate_gate.blockers,
        "diagnostics": candidate_gate.diagnostics,
        "confidence_caps": confidence_caps,
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
        "partial_safe_extra_frames": partial_safe_extra_frames,
    }
    return candidate
