from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from x5crop.domain import EvidenceState


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
    measurement_scope: str
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

    def __post_init__(self) -> None:
        if self.measurement_scope not in {
            "sequence",
            "lane_composition",
            "unmeasured",
        }:
            raise ValueError("unsupported frame topology measurement scope")
        boxes = list(self.boxes)
        invalid_extent_indexes = tuple(
            index
            for index, box in enumerate(boxes, start=1)
            if not box.valid()
        )
        order_invalid_indexes = tuple(_order_invalid_indexes(boxes))
        overlap_pairs = tuple(_overlap_pairs(boxes))
        if self.expected_count <= 0:
            raise ValueError("frame topology requires a positive expected count")
        if self.measurement_scope == "unmeasured":
            if (
                self.state != EvidenceState.UNAVAILABLE
                or self.actual_count != 0
                or self.boxes
                or self.invalid_extent_indexes
                or self.order_invalid_indexes
                or self.overlap_pairs
                or any(
                    (
                        self.count_matches,
                        self.extent_valid,
                        self.order_valid,
                        self.overlap_absent,
                    )
                )
            ):
                raise ValueError("unmeasured topology cannot claim frame support")
            return
        common_fields_match = bool(
            self.actual_count == len(boxes)
            and self.count_matches == (self.expected_count == self.actual_count)
            and self.extent_valid == (not invalid_extent_indexes)
            and self.invalid_extent_indexes == invalid_extent_indexes
        )
        if not common_fields_match:
            raise ValueError("frame topology fields must match the frame geometry")
        if self.measurement_scope == "sequence" and (
            self.order_valid != (not order_invalid_indexes)
            or self.overlap_absent != (not overlap_pairs)
            or self.order_invalid_indexes != order_invalid_indexes
            or self.overlap_pairs != overlap_pairs
        ):
            raise ValueError("sequence topology must derive from ordered frame boxes")
        supported = bool(
            self.count_matches
            and self.extent_valid
            and self.order_valid
            and self.overlap_absent
        )
        if self.state == EvidenceState.SUPPORTED and not supported:
            raise ValueError("supported frame topology requires complete integrity")
        if self.state == EvidenceState.CONTRADICTED and supported:
            raise ValueError("frame topology state must match its measurements")

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
        measurement_scope="sequence",
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
