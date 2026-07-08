from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputOverlapEvidenceParameters:
    mean_min: float = 55.0
    weak_continuity: float = 0.16
    weak_activity: float = 0.04
    medium_continuity: float = 0.35
    medium_activity: float = 0.08
    strong_continuity: float = 0.70
    strong_activity: float = 0.12


__all__ = [
    "OutputOverlapEvidenceParameters",
]
