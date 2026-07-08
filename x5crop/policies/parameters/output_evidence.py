from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputOverlapEvidenceParameters:
    mean_min: float
    weak_continuity: float
    weak_activity: float
    medium_continuity: float
    medium_activity: float
    strong_continuity: float
    strong_activity: float


__all__ = [
    "OutputOverlapEvidenceParameters",
]
