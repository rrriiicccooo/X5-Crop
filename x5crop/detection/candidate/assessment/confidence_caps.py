from __future__ import annotations

from ....domain import DetectionCandidate
from ...confidence_caps import apply_confidence_cap


def apply_candidate_confidence_cap(
    detection: DetectionCandidate,
    cap: float,
    reason: str,
) -> None:
    detection.confidence, cap_detail = apply_confidence_cap(
        detection.confidence,
        cap,
        owner="candidate.assessment",
        reason=reason,
    )
    confidence_caps = detection.detail.setdefault("candidate_confidence_caps", [])
    if not isinstance(confidence_caps, list):
        confidence_caps = []
        detection.detail["candidate_confidence_caps"] = confidence_caps
    confidence_caps.append(cap_detail)


__all__ = ["apply_candidate_confidence_cap"]
