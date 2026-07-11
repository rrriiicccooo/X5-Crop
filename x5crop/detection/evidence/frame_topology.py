from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from .state import EvidenceState


def _overlap_pairs(boxes: list[Box]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for index, (left, right) in enumerate(zip(boxes[:-1], boxes[1:]), start=1):
        if right.left < left.right:
            pairs.append((index, index + 1))
    return pairs


def _order_invalid_indexes(boxes: list[Box]) -> list[int]:
    invalid: list[int] = []
    for index, (left, right) in enumerate(zip(boxes[:-1], boxes[1:]), start=2):
        if right.left < left.left or right.right < left.right:
            invalid.append(index)
    return invalid


@dataclass(frozen=True)
class FrameTopologyEvidence:
    state: EvidenceState
    expected_count: int
    actual_count: int
    count_matches: bool
    extent_valid: bool
    order_valid: bool
    overlap_absent: bool
    invalid_extent_indexes: tuple[int, ...]
    order_invalid_indexes: tuple[int, ...]
    overlap_pairs: tuple[tuple[int, int], ...]
    boxes: tuple[Box, ...]

    @property
    def supported(self) -> bool:
        return self.state == EvidenceState.SUPPORTED

def frame_topology_evidence(
    boxes: list[Box] | tuple[Box, ...],
    expected_count: int,
) -> FrameTopologyEvidence:
    invalid_extent_indexes = [
        index
        for index, box in enumerate(boxes, start=1)
        if not box.valid()
    ]
    overlap_pairs = _overlap_pairs(boxes)
    order_invalid_indexes = _order_invalid_indexes(boxes)
    count_matches = len(boxes) == int(expected_count)
    extent_valid = not invalid_extent_indexes
    overlap_absent = not overlap_pairs
    order_valid = not order_invalid_indexes
    ok = count_matches and extent_valid and overlap_absent and order_valid
    return FrameTopologyEvidence(
        state=EvidenceState.SUPPORTED if ok else EvidenceState.CONTRADICTED,
        expected_count=int(expected_count),
        actual_count=len(boxes),
        count_matches=count_matches,
        extent_valid=extent_valid,
        order_valid=order_valid,
        overlap_absent=overlap_absent,
        invalid_extent_indexes=tuple(invalid_extent_indexes),
        order_invalid_indexes=tuple(order_invalid_indexes),
        overlap_pairs=tuple(overlap_pairs),
        boxes=tuple(boxes),
    )
