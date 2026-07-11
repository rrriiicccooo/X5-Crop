from __future__ import annotations

from dataclasses import dataclass

from .state import EvidenceState


@dataclass(frozen=True)
class TransformGeometryEvidence:
    state: EvidenceState
    applied: bool
    estimated_angle_degrees: float
    applied_angle_degrees: float
    reason: str
    span_px: float | None
    span_threshold_px: float | None
