from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import (
    EvidenceState,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)


@dataclass(frozen=True)
class GeometryResolution:
    count_resolved: bool
    frame_slots_resolved: bool
    shared_short_axis_safe: bool
    content_preservation_compatible: bool
    larger_count_search_complete: bool
    alternative_geometries_resolved: bool
    assignment_consensus_resolved: bool
    physical_search: PhysicalSearchOutcome
    state: EvidenceState = field(init=False)
    reasons: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        resolved = all(
            (
                self.count_resolved,
                self.frame_slots_resolved,
                self.shared_short_axis_safe,
                self.content_preservation_compatible,
                self.larger_count_search_complete,
                self.alternative_geometries_resolved,
                self.assignment_consensus_resolved,
            )
        ) and self.physical_search.state == EvidenceState.SUPPORTED
        reasons: list[str] = []
        if not self.count_resolved:
            reasons.append("count_unresolved")
        if not self.frame_slots_resolved:
            reasons.append("frame_slots_unresolved")
        if not self.shared_short_axis_safe:
            reasons.append("shared_short_axis_unresolved")
        if not self.content_preservation_compatible:
            reasons.append("content_preservation_unresolved")
        if not self.larger_count_search_complete:
            reasons.append("larger_count_search_incomplete")
        if not self.alternative_geometries_resolved:
            reasons.append("geometry_clusters_disagree")
        if not self.assignment_consensus_resolved:
            reasons.append("assignment_consensus_unresolved")
        if self.physical_search.state == EvidenceState.CONTRADICTED:
            reasons.append("physical_constraints_contradicted")
        if PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE in self.physical_search.facts:
            reasons.append("physical_measurements_unavailable")
        if PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED in self.physical_search.facts:
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
