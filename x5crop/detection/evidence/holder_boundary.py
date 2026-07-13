from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...domain import BoundaryPathObservation, EvidenceState
from ..physical.boundary import boundary_supports_holder_region
from ..physical.model import SequenceSolution


@dataclass(frozen=True)
class HolderBoundaryEvidence:
    paths: tuple[BoundaryPathObservation, ...]
    edge_texture_limit: float
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.edge_texture_limit) or self.edge_texture_limit < 0.0:
            raise ValueError("holder boundary texture limit must be finite and non-negative")
        if any(
            not boundary_supports_holder_region(path, self.edge_texture_limit)
            for path in self.paths
        ):
            raise ValueError("holder boundary evidence accepts measured paths only")
        state = EvidenceState.SUPPORTED if self.paths else EvidenceState.UNAVAILABLE
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "reason",
            (
                "edge_adjacent_holder_boundary_observed"
                if self.paths
                else "holder_boundary_observation_unavailable"
            ),
        )


def holder_boundary_evidence(
    geometry: SequenceSolution,
    edge_texture_limit: float,
) -> HolderBoundaryEvidence:
    return HolderBoundaryEvidence(
        tuple(
            path
            for path in geometry.boundary_paths
            if boundary_supports_holder_region(path, edge_texture_limit)
        ),
        edge_texture_limit,
    )
