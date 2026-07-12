from __future__ import annotations

from ...physical.model import ReviewOnlyGeometry
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    ReviewOnlyEvidence,
)


_REVIEW_ONLY_EVIDENCE_REASON = "review_only_geometry_not_measured"


def assess_review_only_candidate(
    candidate: BuiltCandidate,
) -> AssessedCandidate:
    geometry = candidate.geometry
    if not isinstance(geometry, ReviewOnlyGeometry):
        raise ValueError("review-only assessment requires review-only geometry")
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=ReviewOnlyEvidence(_REVIEW_ONLY_EVIDENCE_REASON),
            gate=None,
        ),
    )
