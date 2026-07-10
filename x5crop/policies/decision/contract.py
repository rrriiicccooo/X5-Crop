from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...formats import FormatPhysicalSpec
from ..identity import decision_policy_id_for

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy


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
    review_confidence_cap: float = 0.84
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84
    candidate_close_margin: float = 0.020
    outer_candidate_disagreement_min_spread_ratio: float = 0.20


@dataclass(frozen=True)
class DetectionDecisionContract:
    policy_id: str
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    evidence: EvidencePolicy
    decision: DecisionPolicy


def decision_policy_for(detection_policy: DetectionPolicy) -> DecisionPolicy:
    return replace(
        DecisionPolicy(),
        review_confidence_cap=detection_policy.candidate_selection.confidence_cap,
        content_aspect_conflict_cap=detection_policy.decision.content_aspect_conflict_cap,
        content_low_confidence_cap=detection_policy.decision.content_low_confidence_cap,
        outer_mismatch_cap=detection_policy.decision.outer_mismatch_cap,
        candidate_close_margin=float(detection_policy.candidate_selection.close_margin),
        outer_candidate_disagreement_min_spread_ratio=(
            detection_policy.decision.outer_candidate_disagreement_min_spread_ratio
        ),
    )


def decision_contract_for_policy(detection_policy: DetectionPolicy) -> DetectionDecisionContract:
    from .evidence_policy import evidence_policy_for_physical_spec

    spec = detection_policy.physical_spec
    policy_id = decision_policy_id_for(spec.format_id, detection_policy.strip_mode)
    return DetectionDecisionContract(
        policy_id=policy_id,
        physical_spec=spec,
        strip_mode=detection_policy.strip_mode,
        evidence=evidence_policy_for_physical_spec(
            spec,
            detection_policy.strip_mode,
            EvidencePolicy(),
            detection_policy.separator.geometry_support.active_modes(),
        ),
        decision=decision_policy_for(detection_policy),
    )
