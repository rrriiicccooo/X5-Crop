from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ...formats import FormatSpec, format_spec
from .overrides import evidence_policy_values
from ..ids import REPORT_SCHEMA_VERSION, decision_policy_id_for

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class ModePolicy:
    mode: str
    nominal_count: int
    allowed_counts: tuple[int, ...]
    expected_separator_count: int
    count_behavior: str
    outer_behavior: str
    stop_condition: str
    partial_edge_trust: str


@dataclass(frozen=True)
class EvidencePolicy:
    min_outer_area_ratio: float = 0.30
    max_outer_area_ratio: float = 0.985
    max_photo_width_cv_ratio: float = 0.030
    min_geometry_score: float = 0.70
    min_content_score: float = 0.72
    min_hard_separator_ratio: float = 0.50
    min_hard_separator_count: int = 1
    max_equal_gap_count: int = 0
    max_content_gap_count: int = 0
    max_model_gap_share: float = 0.70
    allow_geometry_supported_separator: bool = False
    geometry_supported_min_hard_ratio: float = 0.35
    geometry_supported_max_photo_width_cv_ratio: float = 0.010
    partial_requires_safe_edge: bool = False


@dataclass(frozen=True)
class DecisionPolicy:
    confidence_threshold_default: float = 0.85
    review_confidence_cap: float = 0.84
    policy_id: str = "evidence_guarded_decision"
    align_outer_to_content: bool = True
    outer_alignment_disabled_reason: str = "disabled_by_policy"
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84
    candidate_close_margin: float = 0.020
    suppress_close_competition_when_partial_edge_safe: bool = True
    outer_candidate_disagreement_review_reason: str = "outer_candidate_disagreement"
    deskew_uncertain_review_reason: str = "deskew_uncertain"
    separator_incomplete_reason: str = "separator_evidence_incomplete"
    geometry_unstable_reason: str = "geometry_unstable"
    outer_content_mismatch_reason: str = "outer_content_mismatch"
    candidate_competition_close_reason: str = "candidate_competition_close"
    output_overlap_reason: str = "output_overlap_detected"
    content_only_evidence_reason: str = "content_only_evidence"
    content_evidence_insufficient_reason: str = "content_evidence_insufficient"
    partial_edge_uncertain_reason: str = "partial_edge_uncertain"
    decision_insufficient_reason: str = "evidence_combination_insufficient"


@dataclass(frozen=True)
class DetectionDecisionContract:
    policy_id: str
    schema_version: str
    format: FormatSpec
    mode: ModePolicy
    evidence: EvidencePolicy
    decision: DecisionPolicy

    def report_detail(self) -> dict[str, Any]:
        from ..reporting import decision_contract_report_detail

        return decision_contract_report_detail(self)

def mode_policy_for(spec: FormatSpec, strip_mode: str) -> ModePolicy:
    partial = strip_mode == "partial"
    return ModePolicy(
        mode=strip_mode,
        nominal_count=spec.default_count,
        allowed_counts=spec.allowed_counts,
        expected_separator_count=(
            max(0, spec.default_count - 1)
            if not partial
            else max(0, max(spec.allowed_counts) - 1)
        ),
        count_behavior=(
            "fixed_nominal_count" if not partial else "candidate_count_search"
        ),
        outer_behavior=(
            "outer_must_match_content_and_geometry"
            if not partial
            else "outer_edges_are_untrusted_until_supported"
        ),
        stop_condition=(
            "all_expected_internal_separators_supported"
            if not partial
            else "first_safe_candidate_or_review"
        ),
        partial_edge_trust=(
            "not_applicable" if not partial else "requires_safe_edge_evidence"
        ),
    )


def evidence_policy_for(
    format_id: str,
    strip_mode: str,
    detection_policy: DetectionPolicy | None = None,
) -> EvidencePolicy:
    policy = EvidencePolicy()
    values = evidence_policy_values(format_id, strip_mode, policy, detection_policy)
    return replace(policy, **values)


def decision_policy_for(detection_policy: DetectionPolicy) -> DecisionPolicy:
    policy_id = decision_policy_id_for(detection_policy.format_id, detection_policy.strip_mode)
    return replace(
        DecisionPolicy(),
        policy_id=policy_id,
        confidence_threshold_default=detection_policy.scoring.confidence_threshold_default,
        review_confidence_cap=detection_policy.candidate_selection.confidence_cap,
        align_outer_to_content=detection_policy.decision.align_outer_to_content,
        outer_alignment_disabled_reason=detection_policy.decision.outer_alignment_disabled_reason,
        content_aspect_conflict_cap=detection_policy.decision.content_aspect_conflict_cap,
        content_low_confidence_cap=detection_policy.decision.content_low_confidence_cap,
        outer_mismatch_cap=detection_policy.decision.outer_mismatch_cap,
        candidate_close_margin=float(detection_policy.candidate_selection.close_margin),
        outer_candidate_disagreement_review_reason=detection_policy.decision.outer_candidate_disagreement_review_reason,
        deskew_uncertain_review_reason=detection_policy.decision.deskew_uncertain_review_reason,
    )


def decision_contract_for_policy(detection_policy: DetectionPolicy) -> DetectionDecisionContract:
    spec = format_spec(detection_policy.format_id)
    policy_id = decision_policy_id_for(detection_policy.format_id, detection_policy.strip_mode)
    return DetectionDecisionContract(
        policy_id=policy_id,
        schema_version=detection_policy.report.schema_version,
        format=spec,
        mode=mode_policy_for(spec, detection_policy.strip_mode),
        evidence=evidence_policy_for(
            detection_policy.format_id,
            detection_policy.strip_mode,
            detection_policy,
        ),
        decision=decision_policy_for(detection_policy),
    )


def decision_contract_for(format_id: str, strip_mode: str) -> DetectionDecisionContract:
    from ..registry import get_detection_policy

    return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "DetectionDecisionContract",
    "DecisionPolicy",
    "EvidencePolicy",
    "ModePolicy",
    "decision_contract_for",
    "decision_contract_for_policy",
    "decision_policy_for",
    "evidence_policy_for",
]
