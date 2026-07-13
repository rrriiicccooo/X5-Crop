from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...domain import (
    BoundaryKind,
    BoundaryPathObservation,
    EvidenceState,
)
from ..physical.model import SequenceSolution
from ..physical.boundary import boundary_supports_holder_material


@dataclass(frozen=True)
class HolderMaterialEvidence:
    paths: tuple[BoundaryPathObservation, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if any(
            path.kind == BoundaryKind.CANVAS_CLIP
            or path.outer_material is None
            for path in self.paths
        ):
            raise ValueError("holder material evidence accepts holder paths only")
        state = EvidenceState.SUPPORTED if self.paths else EvidenceState.UNAVAILABLE
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "reason",
            (
                "edge_adjacent_holder_material_observed"
                if self.paths
                else "holder_material_observation_unavailable"
            ),
        )


def holder_material_evidence(
    geometry: SequenceSolution,
    edge_texture_limit: float,
) -> HolderMaterialEvidence:
    if not math.isfinite(edge_texture_limit) or edge_texture_limit < 0.0:
        raise ValueError("holder material texture limit must be finite and non-negative")
    return HolderMaterialEvidence(
        tuple(
            path
            for path in geometry.boundary_paths
            if boundary_supports_holder_material(
                path,
                edge_texture_limit,
            )
        )
    )
