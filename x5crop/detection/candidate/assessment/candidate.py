from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from ....constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_SAFETY,
    CANDIDATE_SOURCE_SEPARATOR,
)
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.layout import work_gray
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....run_config import RunConfig
from ...confidence_caps import apply_confidence_cap
from ...evidence.content.containment import content_containment_detail
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.separator_summary import separator_support_detail_summary
from ..signals import (
    SIGNAL_CONTENT_ASPECT_CONFLICT,
    SIGNAL_CONTENT_EVIDENCE_WEAK,
    SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING,
    SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO,
    SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING,
    SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_DETECTED,
    SIGNAL_PARTIAL_COUNT_AMBIGUOUS,
    SIGNAL_PARTIAL_EDGE_CONTENT_PRESENT,
    SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
    SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
    candidate_signals,
    merged_candidate_signals,
    set_candidate_signals,
)
from .base_scoring import apply_base_detection_scoring
from .content_candidate import content_candidate_assessment_from_proposal
from .evidence_independence import evidence_independence_detail
from .support_calibration import separator_geometry_support_applies
from .candidate_gate import candidate_gate_assessment
from .partial_holder import partial_edge_safety_assessment_detail
from .separator_support import assess_separator_support
from .scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
    joint_support_score,
    separator_support_score,
)


def _uses_separator_evidence(source: str) -> bool:
    return source in {"separator", CANDIDATE_SOURCE_SEPARATOR, CANDIDATE_SOURCE_SAFETY}


def _detail_float(detail: dict, key: str, default: float) -> float:
    value = detail.get(key)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _candidate_confidence_caps(candidate: DetectionCandidate) -> list[dict]:
    caps = candidate.detail.get("candidate_confidence_caps", [])
    return list(caps) if isinstance(caps, list) else []


def apply_candidate_assessment_policy(
    gray: np.ndarray,
    detection: DetectionCandidate,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    source: str,
    cache: Optional[AnalysisCache],
    *,
    policy: DetectionPolicy,
) -> DetectionCandidate:
    candidate_detail = dict(detection.detail)
    initial_candidate_signals = candidate_signals(detection)
    if initial_candidate_signals:
        candidate_detail["candidate_signals"] = initial_candidate_signals
    candidate = replace(
        detection,
        detail=candidate_detail,
    )
    if _uses_separator_evidence(source):
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
    separator_support_result = assess_separator_support(
        candidate,
        config.confidence_threshold,
        policy,
    )
    separator_support_ok = separator_support_result.ok
    separator_support_detail = separator_support_result.detail
    content_detail = content_evidence_detail(
        gray,
        candidate,
        cache,
        content_policy=policy.content,
        horizontal_frame_aspect=fmt.horizontal_content_aspect,
    )
    containment_detail = content_containment_detail(
        content_detail,
        policy.content.evidence,
        expected_count=candidate.count,
    )
    scoring_policy = policy.scoring
    content_score = content_support_score(containment_detail)
    content_quality = content_quality_score(containment_detail, policy.content)
    geometry_score = geometry_support_score(candidate, containment_detail, policy)
    separator_score = (
        separator_support_score(candidate, separator_support_detail, policy)
        if _uses_separator_evidence(source)
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
    content_integrity_failed = bool(containment_detail.get("content_integrity_failed", True))
    holder_occupancy = holder_occupancy_evidence(
        candidate,
        fmt,
        containment_detail,
    )
    strip_completeness = dict(holder_occupancy.get("strip_completeness", {}))
    candidate.detail["strip_completeness"] = strip_completeness
    candidate.detail["holder_occupancy"] = holder_occupancy
    signals = candidate_signals(candidate)
    detected_geometry_policy = policy.separator.geometry_support.detected_geometry
    stable_grid_policy = policy.separator.geometry_support.stable_grid
    detected_geometry_support = (
        detected_geometry_policy is not None
        and (not separator_support_ok)
    ) and separator_geometry_support_applies(
        candidate,
        separator_support_detail,
        fmt,
        source,
        support,
        joint_score,
        detected_geometry_policy,
    )
    stable_grid_support = (
        False
        if detected_geometry_support
        or stable_grid_policy is None
        else separator_geometry_support_applies(
            candidate,
            separator_support_detail,
            fmt,
            source,
            support,
            joint_score,
            stable_grid_policy,
        )
    )
    if detected_geometry_support or stable_grid_support:
        separator_support_ok = True
        separator_support_detail = dict(separator_support_detail)
        separator_support_detail["ok"] = True
        if detected_geometry_support:
            separator_support_detail["reason"] = "separator_detected_geometry_support"
            separator_support_detail["separator_geometry_support_mode"] = "detected_geometry"
        else:
            separator_support_detail["reason"] = "separator_stable_grid_support"
            separator_support_detail["separator_geometry_support_mode"] = "stable_grid"

    outer_candidate_strategy = str(candidate.detail.get("outer_candidate_strategy", ""))
    if _uses_separator_evidence(source) and outer_candidate_strategy == "edge_anchor_outer":
        hard_count = separator_support_detail_summary(separator_support_detail).hard_separator_gaps
        if hard_count <= 0:
            separator_support_ok = False
            separator_support_detail = dict(separator_support_detail)
            separator_support_detail["ok"] = False
            separator_support_detail["reason"] = "edge_anchor_needs_hard_separator"
            separator_support_detail["edge_anchor_needs_hard_separator"] = True
            signals.append(SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING)

    content_guided_hard_separator_missing = False
    content_guided_detail = candidate.detail.get("content_guided_separator", {})
    if source in {"separator", CANDIDATE_SOURCE_SEPARATOR} and isinstance(content_guided_detail, dict) and bool(content_guided_detail.get("used", False)):
        hard_count = separator_support_detail_summary(separator_support_detail).hard_separator_gaps
        if hard_count <= 0:
            content_guided_hard_separator_missing = True
            separator_support_ok = False
            separator_support_detail = dict(separator_support_detail)
            separator_support_detail["ok"] = False
            separator_support_detail["reason"] = SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING
            separator_support_detail["content_guided_separator_needs_hard_separator"] = True
            signals.append(SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING)

    if _uses_separator_evidence(source) and not separator_support_ok:
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
    partial_edge_safety = partial_edge_safety_assessment_detail(
        gray,
        candidate,
        separator_support_detail,
        containment_detail,
        source,
        joint_score,
        content_quality,
        geometry_score,
        holder_occupancy,
        cache,
        policy=policy,
    )
    partial_edge_safety_ok = bool(partial_edge_safety.get("ok", False))
    partial_edge_safety_candidate_support_ok = (
        partial_edge_safety_ok
        and not content_guided_hard_separator_missing
    )
    partial_edge_safety_disqualifiers = set(
        partial_edge_safety.get("disqualifiers", [])
    )
    partial_signal_map = {
        SIGNAL_PARTIAL_EDGE_CONTENT_PRESENT: SIGNAL_PARTIAL_EDGE_CONTENT_PRESENT,
        "partial_frame_content_unstable": SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
    }
    partial_edge_safety_blocker_signals = {
        partial_signal_map[disqualifier]
        for disqualifier in partial_edge_safety_disqualifiers
        if disqualifier in partial_signal_map
    }
    partial_edge_safety_blocks_auto = (
        policy.partial_holder.enabled
        and candidate.strip_mode == "partial"
        and _uses_separator_evidence(source)
        and bool(partial_edge_safety.get("used", False))
        and bool(
            partial_edge_safety_blocker_signals.intersection(
                {
                    SIGNAL_PARTIAL_EDGE_CONTENT_PRESENT,
                    SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
                }
            )
        )
    )
    if partial_edge_safety_blocks_auto:
        separator_support_ok = False
        separator_support_detail = dict(separator_support_detail)
        separator_support_detail["ok"] = False
        separator_support_detail["reason"] = "partial_edge_safety_blocked"
        separator_support_detail["partial_edge_safety_blocked"] = sorted(
            partial_edge_safety_disqualifiers
        )
        signals.extend(sorted(partial_edge_safety_blocker_signals))
    if partial_edge_safety_candidate_support_ok:
        separator_support_detail = dict(separator_support_detail)
        separator_support_detail["ok"] = True
        separator_support_detail["reason"] = "partial_edge_safety_support"
        separator_support_detail["partial_edge_safety_support"] = True
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
    if _uses_separator_evidence(source):
        separator_support_detail = dict(separator_support_detail)
        separator_support_detail["evidence_independence"] = independence_detail
    if not evidence_independence_ok:
        signals.append(
            str(
                independence_detail.get("reason")
                or SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_DETECTED
            )
        )
    candidate_gate = candidate_gate_assessment(
        source=source,
        separator_support_ok=bool(separator_support_ok),
        separator_support_detail=separator_support_detail,
        partial_edge_safety_candidate_support_ok=bool(
            partial_edge_safety_candidate_support_ok
        ),
        partial_edge_safety_blocks_auto=bool(partial_edge_safety_blocks_auto),
        partial_edge_safety_disqualifiers=partial_edge_safety_disqualifiers,
        content_containment_ok=bool(content_containment_ok),
        content_integrity_failed=bool(content_integrity_failed),
        content_support=support,
        evidence_independence_ok=bool(evidence_independence_ok),
        evidence_independence_detail=independence_detail,
        signals=signals,
    )
    confidence_caps = _candidate_confidence_caps(candidate)
    if not candidate_gate.passed:
        calibration = scoring_policy.calibration
        cap = (
            calibration.no_auto_cap_partial
            if candidate.strip_mode == "partial"
            else calibration.no_auto_cap_full
        )
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            cap,
            owner="candidate.assessment",
            reason="candidate_gate_failed",
        )
        confidence_caps.append(cap_detail)
    candidate_gate = candidate_gate.with_confidence_caps(confidence_caps)
    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    set_candidate_signals(candidate, signals)
    candidate.detail["candidate_source"] = (
        CANDIDATE_SOURCE_SEPARATOR
        if source in {"separator", CANDIDATE_SOURCE_SEPARATOR}
        else source
        if source == CANDIDATE_SOURCE_SAFETY
        else CANDIDATE_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["content_containment"] = containment_detail
    candidate.detail["strip_completeness"] = strip_completeness
    candidate.detail["holder_occupancy"] = holder_occupancy
    candidate.detail["candidate_assessment"] = {
        "source": source,
        "joint_score": float(joint_score),
        "candidate_gate": candidate_gate.report_detail(),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_score_role": "content_containment_support",
        "content_quality_score": float(content_quality),
        "content_quality_score_role": "quality_diagnostic_not_boundary_evidence",
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
        "content_integrity_failed": bool(content_integrity_failed),
        "content_containment": containment_detail,
        "strip_completeness": strip_completeness,
        "holder_occupancy": holder_occupancy,
        "separator_support": separator_support_detail,
        "evidence_independence": independence_detail,
        "partial_edge_safety": partial_edge_safety,
    }
    return candidate
