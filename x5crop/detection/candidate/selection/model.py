from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState
from ..model import AssessedCandidate


@dataclass(frozen=True)
class GeometryResolution:
    state: EvidenceState
    count_resolved: bool
    placement_resolved: bool
    boundaries_resolved: bool
    content_preservation_compatible: bool
    larger_counts_evaluated: bool
    alternative_geometries_resolved: bool
    reasons: tuple[str, ...]

    @property
    def supported(self) -> bool:
        return self.state == EvidenceState.SUPPORTED


@dataclass(frozen=True)
class GeometryCluster:
    candidates: tuple[AssessedCandidate, ...]
    representative: AssessedCandidate


@dataclass(frozen=True)
class CountResolution:
    selected_count: int
    search_order: tuple[int, ...]
    evaluated_counts: tuple[int, ...]
    stopped_after_count: int | None
    reason: str


@dataclass(frozen=True)
class SelectionResult:
    selected: AssessedCandidate
    ranked_candidates: tuple[AssessedCandidate, ...]
    clusters: tuple[GeometryCluster, ...]
    consensus: str
    geometry_resolution: GeometryResolution
    count_resolution: CountResolution | None = None
