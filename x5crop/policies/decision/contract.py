from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...formats import FormatPhysicalSpec
from ..identity import decision_policy_id_for
from ..parameters.decision import DecisionEvidenceParameters, DecisionReviewParameters
from ..parameters.scoring import CandidateCompetitionParameters

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class DetectionDecisionContract:
    policy_id: str
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    evidence: DecisionEvidenceParameters
    decision: DecisionReviewParameters
    candidate_selection: CandidateCompetitionParameters


def decision_contract_for_policy(detection_policy: DetectionPolicy) -> DetectionDecisionContract:
    spec = detection_policy.physical_spec
    policy_id = decision_policy_id_for(spec.format_id, detection_policy.strip_mode)
    return DetectionDecisionContract(
        policy_id=policy_id,
        physical_spec=spec,
        strip_mode=detection_policy.strip_mode,
        evidence=detection_policy.decision_evidence,
        decision=detection_policy.decision,
        candidate_selection=detection_policy.candidate_selection,
    )
