from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OutputOverlapEvidencePolicy:
    enabled: bool = False
    mean_min: float = 55.0
    weak_continuity: float = 0.16
    weak_activity: float = 0.04
    medium_continuity: float = 0.35
    medium_activity: float = 0.08
    strong_continuity: float = 0.70
    strong_activity: float = 0.12


@dataclass(frozen=True)
class RuntimeOutputEvidencePolicy:
    output_overlap: OutputOverlapEvidencePolicy = field(default_factory=OutputOverlapEvidencePolicy)


__all__ = [
    "OutputOverlapEvidencePolicy",
    "RuntimeOutputEvidencePolicy",
]
