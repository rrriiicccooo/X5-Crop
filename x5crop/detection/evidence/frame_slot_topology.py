from __future__ import annotations

from dataclasses import dataclass, field

from ...domain import EvidenceState
from ..physical.model import FrameSequenceSolution


@dataclass(frozen=True)
class FrameSlotTopologyEvidence:
    count: int
    frame_indexes: tuple[int, ...]
    shared_short_axis: bool
    long_axis_boundaries_resolved: bool
    sequence_inferred_frame_indexes: tuple[int, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        expected = tuple(range(1, self.count + 1))
        if self.count <= 0 or self.frame_indexes != expected:
            raise ValueError("frame-slot topology requires complete ordered indexes")
        if any(
            index not in expected for index in self.sequence_inferred_frame_indexes
        ):
            raise ValueError("inferred frame indexes must belong to the sequence")
        if len(set(self.sequence_inferred_frame_indexes)) != len(
            self.sequence_inferred_frame_indexes
        ):
            raise ValueError("inferred frame indexes must be unique")
        if self.shared_short_axis and self.long_axis_boundaries_resolved:
            state = EvidenceState.SUPPORTED
            reason = "frame_slot_topology_resolved"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "frame_slot_topology_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def frame_slot_topology_evidence(
    geometry: FrameSequenceSolution,
) -> FrameSlotTopologyEvidence:
    return FrameSlotTopologyEvidence(
        count=geometry.count,
        frame_indexes=tuple(slot.index for slot in geometry.frame_slots),
        shared_short_axis=geometry.shared_short_axis.supports_safe_crop,
        long_axis_boundaries_resolved=all(
            slot.leading.geometry_resolved and slot.trailing.geometry_resolved
            for slot in geometry.frame_slots
        ),
        sequence_inferred_frame_indexes=tuple(
            slot.index for slot in geometry.frame_slots if slot.sequence_inferred
        ),
    )
