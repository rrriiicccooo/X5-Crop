from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ...domain import Box


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


def frame_topology_evidence(boxes: list[Box], expected_count: int) -> dict[str, Any]:
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
    return {
        "used": True,
        "evidence_role": "frame_geometry_topology",
        "physical_rule": "strip_frames_are_ordered_and_non_overlapping",
        "ok": bool(ok),
        "expected_count": int(expected_count),
        "actual_count": int(len(boxes)),
        "count_matches": bool(count_matches),
        "frame_extent_valid": bool(extent_valid),
        "frame_order_valid": bool(order_valid),
        "frame_monotonicity_ok": bool(order_valid),
        "frame_overlap_absent": bool(overlap_absent),
        "invalid_extent_indexes": invalid_extent_indexes,
        "order_invalid_indexes": order_invalid_indexes,
        "overlap_pairs": [[left, right] for left, right in overlap_pairs],
        "boxes": [asdict(box) for box in boxes],
    }
