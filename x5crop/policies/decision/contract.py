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
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    evidence: DecisionEvidenceParameters
    decision: DecisionReviewParameters
    candidate_selection: CandidateCompetitionParameters

    @property
    def policy_id(self) -> str:
        return decision_policy_id_for(
            self.physical_spec.format_id,
            self.strip_mode,
        )


def decision_contract_for_policy(detection_policy: DetectionPolicy) -> DetectionDecisionContract:
    spec = detection_policy.physical_spec
    return DetectionDecisionContract(
        physical_spec=spec,
        strip_mode=detection_policy.strip_mode,
        evidence=detection_policy.decision_evidence,
        decision=detection_policy.decision,
        candidate_selection=detection_policy.candidate_selection,
    )
