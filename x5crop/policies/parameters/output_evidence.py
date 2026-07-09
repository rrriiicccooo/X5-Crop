from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputOverlapEvidenceParameters:
    bleed_protection_enabled: bool = True
    required_bleed_window_fraction: float = 0.5
    required_bleed_padding_px: int = 0
    required_bleed_min_px: int = 1
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
