from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState

from ..candidate.assessment.model import CANDIDATE_GATE_CHECK_CODES
from ..gate_checks import GateCheck, GateStage
from .vocabulary import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)


DECISION_CANDIDATE_CHECK_CODES = tuple(
    f"candidate_{code}" for code in CANDIDATE_GATE_CHECK_CODES
)
DECISION_FINAL_CHECK_CODES = (
    "count_resolution",
    "geometry_resolution",
    "automatic_processing_eligibility",
    "selection_geometry_consensus",
    "output_content_protection",
    "transform_geometry_integrity",
)
DECISION_GATE_REASON_BY_CODE = {
    "candidate_content_preservation": FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    "candidate_photo_geometry_consistency": FINAL_REASON_PHOTO_GEOMETRY_CONTRADICTED,
    "candidate_evidence_independence": FINAL_REASON_EVIDENCE_INDEPENDENCE_FAILED,
    "candidate_boundary_proof": FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    "count_resolution": FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
    "geometry_resolution": FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    "automatic_processing_eligibility": FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    "selection_geometry_consensus": FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    "output_content_protection": FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    "transform_geometry_integrity": FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
}


@dataclass(frozen=True)
class DecisionGateAssessment:
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("decision gate requires checks")
        if any(check.stage != GateStage.DECISION for check in self.checks):
            raise ValueError("decision gate can contain only decision-stage checks")
        codes = tuple(check.code for check in self.checks)
        if len(set(codes)) != len(codes):
            raise ValueError("decision gate check codes must be unique")
        final_count = len(DECISION_FINAL_CHECK_CODES)
        if len(codes) < final_count or codes[-final_count:] != DECISION_FINAL_CHECK_CODES:
            raise ValueError("decision gate final checks must be complete and ordered")
        candidate_codes = codes[:-final_count]
        if candidate_codes != tuple(
            code for code in DECISION_CANDIDATE_CHECK_CODES if code in candidate_codes
        ):
            raise ValueError("decision candidate checks must be canonical and ordered")
        if any(
            check.state != EvidenceState.CONTRADICTED
            for check in self.checks[: len(candidate_codes)]
        ):
            raise ValueError("projected candidate checks must be physical failures")
        if any(
            check.final_review_reason != DECISION_GATE_REASON_BY_CODE.get(check.code)
            for check in self.checks
        ):
            raise ValueError("decision gate checks must own their canonical final reason")

    @property
    def blocking_checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.blocking_checks

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                check.final_review_reason
                for check in self.blocking_checks
                if check.final_review_reason is not None
            )
        )

    @property
    def reason_inputs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (check.code, check.final_review_reason)
            for check in self.blocking_checks
            if check.final_review_reason is not None
        )

    @property
    def status(self) -> str:
        return "approved_auto" if self.passed else "needs_review"
