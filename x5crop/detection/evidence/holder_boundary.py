from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...domain import EvidenceState, HolderBoundaryObservation
from ..physical.model import PhotoSequenceSolution


def boundary_supports_holder_region(
    boundary: HolderBoundaryObservation,
    edge_texture_limit: float,
) -> bool:
    if not math.isfinite(edge_texture_limit) or edge_texture_limit < 0.0:
        raise ValueError("holder boundary texture limit must be finite and non-negative")
    return all(
        appearance.texture_median <= float(edge_texture_limit)
        for appearance in boundary.outer_appearances
    )


@dataclass(frozen=True)
class HolderBoundaryEvidence:
    boundaries: tuple[HolderBoundaryObservation, ...]
    edge_texture_limit: float
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.edge_texture_limit) or self.edge_texture_limit < 0.0:
            raise ValueError("holder boundary texture limit must be finite and non-negative")
        if any(
            not boundary_supports_holder_region(boundary, self.edge_texture_limit)
            for boundary in self.boundaries
        ):
            raise ValueError("holder boundary evidence accepts supported boundaries only")
        state = EvidenceState.SUPPORTED if self.boundaries else EvidenceState.UNAVAILABLE
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "reason",
            (
                "edge_adjacent_holder_boundary_observed"
                if self.boundaries
                else "holder_boundary_observation_unavailable"
            ),
        )


def holder_boundary_evidence(
    geometry: PhotoSequenceSolution,
    edge_texture_limit: float,
) -> HolderBoundaryEvidence:
    return HolderBoundaryEvidence(
        tuple(
            boundary
            for boundary in geometry.holder_boundaries
            if boundary_supports_holder_region(boundary, edge_texture_limit)
        ),
        edge_texture_limit,
    )
