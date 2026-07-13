from __future__ import annotations

from ...physical.model import ReviewOnlyContainment
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    ReviewOnlyEvidence,
)

def assess_review_only_candidate(
    candidate: BuiltCandidate,
) -> AssessedCandidate:
    geometry = candidate.geometry
    if not isinstance(geometry, ReviewOnlyContainment):
        raise ValueError("review-only assessment requires review-only geometry")
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=ReviewOnlyEvidence(),
            gate=None,
        ),
    )
