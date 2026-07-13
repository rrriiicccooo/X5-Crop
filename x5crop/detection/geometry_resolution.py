from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import EvidenceState


@dataclass(frozen=True)
class GeometryResolution:
    count_resolved: bool
    placement_resolved: bool
    boundaries_resolved: bool
    content_preservation_compatible: bool
    larger_counts_evaluated: bool
    alternative_geometries_resolved: bool
    assignment_geometry_resolved: bool
    search_budget_exhausted: bool
    state: EvidenceState = field(init=False)
    reasons: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        resolved = all(
            (
                self.count_resolved,
                self.placement_resolved,
                self.boundaries_resolved,
                self.content_preservation_compatible,
                self.larger_counts_evaluated,
                self.alternative_geometries_resolved,
                self.assignment_geometry_resolved,
            )
        ) and not self.search_budget_exhausted
        reasons: list[str] = []
        if not self.count_resolved:
            reasons.append("count_unresolved")
        if not self.placement_resolved:
            reasons.append("placement_unresolved")
        if not self.boundaries_resolved:
            reasons.append("boundaries_unresolved")
        if not self.content_preservation_compatible:
            reasons.append("content_preservation_unresolved")
        if not self.larger_counts_evaluated:
            reasons.append("larger_counts_not_evaluated")
        if not self.alternative_geometries_resolved:
            reasons.append("geometry_clusters_disagree")
        if not self.assignment_geometry_resolved:
            reasons.append("separator_assignment_geometry_unresolved")
        if self.search_budget_exhausted:
            reasons.append("search_budget_exhausted")
        object.__setattr__(
            self,
            "state",
            EvidenceState.SUPPORTED if resolved else EvidenceState.UNAVAILABLE,
        )
        object.__setattr__(self, "reasons", tuple(reasons))

    @property
    def supported(self) -> bool:
        return self.state == EvidenceState.SUPPORTED
