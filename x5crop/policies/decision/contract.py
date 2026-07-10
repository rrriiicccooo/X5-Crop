from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...formats import FormatPhysicalSpec
from ..identity import decision_policy_id_for
from ..parameters.decision import DecisionEvidenceParameters

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy


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
    evidence: DecisionEvidenceParameters
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
    spec = detection_policy.physical_spec
    policy_id = decision_policy_id_for(spec.format_id, detection_policy.strip_mode)
    return DetectionDecisionContract(
        policy_id=policy_id,
        physical_spec=spec,
        strip_mode=detection_policy.strip_mode,
        evidence=detection_policy.decision_evidence,
        decision=decision_policy_for(detection_policy),
    )
