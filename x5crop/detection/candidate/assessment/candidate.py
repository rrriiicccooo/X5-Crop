from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

import numpy as np

from ....cache import AnalysisCache
from ....constants import CANDIDATE_SOURCE_CONTENT, CANDIDATE_SOURCE_SEPARATOR
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.layout import work_gray
from ....policies.runtime.policy import DetectionPolicy
from ....run_config import RunConfig
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.content.support import frame_content_support_detail
from ...evidence.frame_topology import frame_topology_evidence
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.separator_summary import separator_support_detail_summary
from ...evidence.state import EvidenceState
from .base_scoring import apply_base_detection_scoring
from .candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from .content_candidate import content_candidate_assessment_from_proposal
from .evidence_independence import evidence_independence_detail
from .partial_holder import partial_edge_safety_assessment_detail
from .scoring import (
    content_quality_score,
    content_support_score,
    geometry_support_score,
    joint_support_score,
    separator_support_score,
)
from .separator_support import assess_separator_support


def _uses_separator_evidence(source: str) -> bool:
    return source in {"separator", CANDIDATE_SOURCE_SEPARATOR}


def _detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key)
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return float(default)


def _topology_detail(candidate: DetectionCandidate) -> dict[str, Any]:
    detail = candidate.detail.get("frame_topology_evidence")
    if isinstance(detail, dict):
        return dict(detail)
    return frame_topology_evidence(candidate.frames, candidate.count)


def _topology_state(detail: dict[str, Any]) -> EvidenceState:
    return (
        EvidenceState.SUPPORTED
        if bool(detail.get("ok", False))
        else EvidenceState.CONTRADICTED
    )


def _photo_geometry_state(candidate: DetectionCandidate) -> EvidenceState:
    detail = candidate.detail.get("photo_width_stability")
    if not isinstance(detail, dict) or not bool(detail.get("used", False)):
        return EvidenceState.UNAVAILABLE
    return (
        EvidenceState.CONTRADICTED
        if bool(detail.get("unstable", False))
        else EvidenceState.SUPPORTED
    )


def _independence_state(detail: dict[str, Any]) -> EvidenceState:
    if not bool(detail.get("used", False)):
        return EvidenceState.NOT_APPLICABLE
    return (
        EvidenceState.SUPPORTED
        if bool(detail.get("ok", False))
        else EvidenceState.CONTRADICTED
    )


def candidate_content_preservation_state(
    content_support: dict[str, Any],
    partial_edge: dict[str, Any],
) -> EvidenceState:
    if str(partial_edge.get("state", "not_applicable")) == "contradicted":
        return EvidenceState.CONTRADICTED
    if bool(content_support.get("frame_content_support_available", False)):
        return EvidenceState.SUPPORTED
    return EvidenceState.UNAVAILABLE


def _boundary_proof_paths(
    candidate: DetectionCandidate,
    source: str,
    separator_detail: dict[str, Any],
    topology_state: EvidenceState,
    photo_state: EvidenceState,
    independence_state: EvidenceState,
    partial_edge: dict[str, Any],
) -> tuple[BoundaryProofPath, ...]:
    separator = separator_support_detail_summary(separator_detail)
    expected = int(separator.expected_gaps)
    hard = int(separator.hard_separator_gaps)
    hard_complete = hard >= expected
    continuity = candidate.detail.get("separator_cross_axis_continuity", {})
    continuity = dict(continuity) if isinstance(continuity, dict) else {}
    weak_gap_indexes = list(continuity.get("weak_gap_indexes", []))
    continuity_supported = bool(continuity.get("ok", False))
    one_weak_gap_corroborated = bool(
        len(weak_gap_indexes) == 1
        and hard_complete
        and photo_state == EvidenceState.SUPPORTED
    )
    common_supported = topology_state == EvidenceState.SUPPORTED and independence_state in {
        EvidenceState.SUPPORTED,
        EvidenceState.NOT_APPLICABLE,
    }
    separator_led = bool(
        _uses_separator_evidence(source)
        and common_supported
        and bool(separator_detail.get("ok", False))
        and (continuity_supported or one_weak_gap_corroborated or expected == 0)
    )
    geometry_led = bool(
        _uses_separator_evidence(source)
        and common_supported
        and photo_state == EvidenceState.SUPPORTED
        and (hard >= 1 or expected == 0)
    )
    partial_state = str(partial_edge.get("state", "not_applicable"))
    partial_occupancy_led = bool(
        candidate.strip_mode == "partial"
        and _uses_separator_evidence(source)
        and common_supported
        and partial_state == EvidenceState.SUPPORTED.value
        and bool(partial_edge.get("boundary_support", False))
    )
    return (
        BoundaryProofPath(
            code="separator_led",
            state=(
                EvidenceState.SUPPORTED
                if separator_led
                else EvidenceState.UNAVAILABLE
            ),
            detail={
                "expected_gaps": expected,
                "hard_gaps": hard,
                "hard_gap_sequence_complete": hard_complete,
                "continuity_supported": continuity_supported,
                "one_weak_gap_corroborated": one_weak_gap_corroborated,
            },
        ),
        BoundaryProofPath(
            code="geometry_led",
            state=(
                EvidenceState.SUPPORTED
                if geometry_led
                else EvidenceState.UNAVAILABLE
            ),
            detail={
                "photo_geometry_state": photo_state.value,
                "independent_hard_separator_anchors": hard,
            },
        ),
        BoundaryProofPath(
            code="partial_occupancy_led",
            state=(
                EvidenceState.SUPPORTED
                if partial_occupancy_led
                else (
                    EvidenceState.UNAVAILABLE
                    if candidate.strip_mode == "partial"
                    else EvidenceState.NOT_APPLICABLE
                )
            ),
            detail={
                "partial_edge_state": partial_state,
                "boundary_support": bool(partial_edge.get("boundary_support", False)),
                "complete_underfilled_strip": bool(
                    partial_edge.get("complete_underfilled_strip", False)
                ),
            },
        ),
    )


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
    candidate = replace(detection, detail=dict(detection.detail))
    diagnostics: list[str] = []
    if _uses_separator_evidence(source):
        gray_work = (
            cache.gray_work
            if cache is not None and cache.layout == config.layout
            else work_gray(gray, config.layout)
        )
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
            policy.content,
        )
        candidate.confidence = max(
            float(candidate.confidence),
            float(proposal_assessment.confidence),
        )
        diagnostics.extend(proposal_assessment.diagnostics)
        content_proposal = candidate.detail.get("content_proposal")
        if isinstance(content_proposal, dict):
            content_proposal["candidate_assessment"] = proposal_assessment.detail

    separator_result = assess_separator_support(candidate, policy)
    separator_ok = bool(separator_result.ok)
    separator_detail = dict(separator_result.detail)
    hard_count = separator_support_detail_summary(separator_detail).hard_separator_gaps
    outer_strategy = str(candidate.detail.get("outer_candidate_strategy", ""))
    content_guided = candidate.detail.get("content_guided_separator", {})
    content_guided_used = bool(
        isinstance(content_guided, dict) and content_guided.get("used", False)
    )
    if _uses_separator_evidence(source) and (
        (outer_strategy == "edge_anchor_outer" and hard_count <= 0)
        or (content_guided_used and hard_count <= 0)
    ):
        separator_ok = False
        separator_detail["ok"] = False
        separator_detail["reason"] = "independent_hard_separator_missing"

    content_detail = content_evidence_detail(
        gray,
        candidate,
        cache,
        content_policy=policy.content,
        horizontal_frame_aspect=fmt.horizontal_content_aspect,
    )
    content_support = frame_content_support_detail(
        content_detail,
        policy.content.evidence,
        expected_count=candidate.count,
    )
    content_score = content_support_score(content_support)
    content_quality = content_quality_score(content_support, policy.content)
    geometry_score = geometry_support_score(candidate, content_support, policy)
    separator_score = (
        separator_support_score(separator_detail, policy)
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
    frame_content_supported = bool(
        content_support.get("frame_content_support_available", False)
    )
    if str(content_support.get("support", "")) in {"low_content", "weak"}:
        diagnostics.append("content_quality_low")
    if str(content_support.get("support", "")) == "aspect_conflict":
        diagnostics.append("content_aspect_uncertain")

    holder_occupancy = holder_occupancy_evidence(candidate, fmt, content_support)
    strip_completeness = dict(holder_occupancy.get("strip_completeness", {}))
    candidate.detail["strip_completeness"] = strip_completeness
    candidate.detail["holder_occupancy"] = holder_occupancy
    partial_edge = partial_edge_safety_assessment_detail(
        gray,
        candidate,
        separator_detail,
        content_support,
        source,
        holder_occupancy,
        cache,
        policy=policy,
    )
    topology = _topology_detail(candidate)
    topology_state = _topology_state(topology)
    content_state = candidate_content_preservation_state(content_support, partial_edge)
    photo_state = _photo_geometry_state(candidate)
    independence = evidence_independence_detail(
        candidate,
        source=source,
        frame_content_support_available=frame_content_supported,
        photo_geometry_supported=photo_state == EvidenceState.SUPPORTED,
        policy=policy.candidate_plan.evidence_independence,
    )
    independence_state = _independence_state(independence)
    separator_detail["evidence_independence"] = independence
    proof_paths = _boundary_proof_paths(
        candidate,
        source,
        separator_detail,
        topology_state,
        photo_state,
        independence_state,
        partial_edge,
    )
    gate = candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=topology_state,
            content_preservation=content_state,
            photo_geometry=photo_state,
            evidence_independence=independence_state,
            proof_paths=proof_paths,
            diagnostics=tuple(diagnostics),
            detail={
                "source": source,
                "separator_support": separator_ok,
            },
        )
    )

    candidate.confidence = float(
        max(0.0, min(1.0, max(float(candidate.confidence), joint_score)))
    )
    candidate.detail["candidate_source"] = (
        CANDIDATE_SOURCE_SEPARATOR
        if _uses_separator_evidence(source)
        else CANDIDATE_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["frame_content_support"] = content_support
    candidate.detail["candidate_assessment"] = {
        "source": source,
        "joint_score": float(joint_score),
        "candidate_gate": gate.report_detail(),
        "failed_checks": list(gate.failed_checks),
        "diagnostics": list(gate.diagnostics),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_score_role": "frame_content_support",
        "content_quality_score": float(content_quality),
        "content_quality_score_role": "quality_diagnostic_not_boundary_evidence",
        "width_cv": _detail_float(candidate.detail, "width_cv", 1.0),
        "width_cv_source": str(candidate.detail.get("width_cv_source") or "unknown"),
        "photo_width_cv": candidate.detail.get("photo_width_cv"),
        "frame_box_width_cv": candidate.detail.get("frame_box_width_cv"),
        "separator_width_cv": candidate.detail.get("separator_width_cv"),
        "content_support": str(content_support.get("support", "")),
        "content_preservation_state": content_state.value,
        "frame_content_support": content_support,
        "strip_completeness": strip_completeness,
        "holder_occupancy": holder_occupancy,
        "separator_support": separator_detail,
        "evidence_independence": independence,
        "partial_edge_safety": partial_edge,
    }
    return candidate
