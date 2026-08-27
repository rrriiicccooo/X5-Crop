"""Directional acceptance checks for the user-confirmed golden cohort."""

from __future__ import annotations

import math
from typing import Sequence

from x5crop.detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from x5crop.formats import OUTPUT_PROTECTION_SPEC
from tools.manual_annotation.model import LINE_REVIEW_BASES


GOLD_ACCEPTANCE_CONTRACT = (
    "x5crop_directional_minimum_acceptable_crop_v1"
)
FRAME_SIDES = frozenset(
    {"sequence_start", "sequence_end", "cross_low", "cross_high"}
)
NON_BLOCKING_ACCURACY_REVIEW_BASES = frozenset({"human_width_estimate"})


def _line_blocks_accuracy(line: object, *, name: str) -> bool:
    if not isinstance(line, dict):
        raise ValueError(f"{name} is malformed")
    review_basis = line.get("review_basis")
    if not isinstance(review_basis, str) or review_basis not in LINE_REVIEW_BASES:
        raise ValueError(f"{name} review basis is invalid")
    return review_basis not in NON_BLOCKING_ACCURACY_REVIEW_BASES


def _blocking_sides_by_frame(
    gold: dict[str, object],
    frames: Sequence[dict[str, object]],
) -> tuple[frozenset[str], ...]:
    basis_evidence_present = tuple(
        key in gold for key in ("boundary_pool", "slots")
    )
    if not any(basis_evidence_present):
        return tuple(FRAME_SIDES for _frame in frames)
    if not all(basis_evidence_present) or "shared_edges" not in gold:
        raise ValueError("gold directional evidence is incomplete")

    shared_edges = gold["shared_edges"]
    boundary_pool = gold["boundary_pool"]
    slots = gold["slots"]
    if (
        not isinstance(shared_edges, list)
        or len(shared_edges) != 2
        or not isinstance(boundary_pool, list)
        or not isinstance(slots, list)
    ):
        raise ValueError("gold directional evidence is malformed")

    pool_by_id: dict[str, dict[str, object]] = {}
    for line in boundary_pool:
        if not isinstance(line, dict):
            raise ValueError("gold boundary pool is malformed")
        line_id = line.get("line_id")
        if not isinstance(line_id, str) or not line_id or line_id in pool_by_id:
            raise ValueError("gold boundary identity is invalid")
        pool_by_id[line_id] = line

    slots_by_ordinal: dict[int, dict[str, object]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("gold slot evidence is malformed")
        ordinal = slot.get("ordinal")
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal <= 0
            or ordinal in slots_by_ordinal
        ):
            raise ValueError("gold slot ordinal is invalid")
        slots_by_ordinal[ordinal] = slot

    cross_sides = {
        side
        for side, line in zip(
            ("cross_low", "cross_high"), shared_edges, strict=True
        )
        if _line_blocks_accuracy(line, name=f"gold {side}")
    }
    blocking_by_frame: list[frozenset[str]] = []
    for frame in frames:
        frame_index = frame.get("frame_index")
        if (
            not isinstance(frame_index, int)
            or isinstance(frame_index, bool)
            or frame_index not in slots_by_ordinal
        ):
            raise ValueError("gold frame does not reference a valid slot")
        reference = slots_by_ordinal[frame_index].get("reference_geometry")
        if not isinstance(reference, dict) or reference.get("kind") != "boundary_pair":
            raise ValueError("gold frame boundary reference is invalid")
        start_id = reference.get("start_boundary_id")
        end_id = reference.get("end_boundary_id")
        if (
            not isinstance(start_id, str)
            or not isinstance(end_id, str)
            or start_id not in pool_by_id
            or end_id not in pool_by_id
        ):
            raise ValueError("gold frame references an unknown boundary")
        blocking = set(cross_sides)
        if _line_blocks_accuracy(
            pool_by_id[start_id], name=f"gold frame {frame_index} start"
        ):
            blocking.add("sequence_start")
        if _line_blocks_accuracy(
            pool_by_id[end_id], name=f"gold frame {frame_index} end"
        ):
            blocking.add("sequence_end")
        blocking_by_frame.append(frozenset(blocking))
    return tuple(blocking_by_frame)


def _contains_point(
    polygon: Sequence[Sequence[float]],
    point: Sequence[float],
    *,
    epsilon: float = 1.0e-6,
) -> bool:
    signs: list[bool] = []
    for left, right in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
        cross = (
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
        if abs(cross) > epsilon:
            signs.append(cross > 0.0)
    return not signs or all(signs) or not any(signs)


def _contains_polygon(
    outer: Sequence[Sequence[float]],
    inner: Sequence[Sequence[float]],
) -> bool:
    return all(_contains_point(outer, point) for point in inner)


def _respects_blocking_sides(
    output: Sequence[Sequence[float]],
    gold: Sequence[Sequence[float]],
    strip_orientation: str,
    blocking_sides: frozenset[str],
    *,
    epsilon: float = 1.0e-6,
) -> bool:
    if blocking_sides == FRAME_SIDES:
        return _contains_polygon(output, gold)
    if len(output) < 4 or len(gold) != 4:
        return False
    horizontal = strip_orientation == "horizontal"
    sequence_axis = _mean_edge_axis(
        gold,
        (0, 1) if horizontal else (0, 3),
        (3, 2) if horizontal else (1, 2),
    )
    cross_axis = _mean_edge_axis(
        gold,
        (0, 3) if horizontal else (0, 1),
        (1, 2) if horizontal else (3, 2),
    )
    center_sequence = sum(
        point[0] * sequence_axis[0] + point[1] * sequence_axis[1]
        for point in output
    ) / len(output)
    center_cross = sum(
        point[0] * cross_axis[0] + point[1] * cross_axis[1]
        for point in output
    ) / len(output)
    points_by_side: dict[str, list[Sequence[float]]] = {
        side: [] for side in FRAME_SIDES
    }
    for left, right in zip(output, (*output[1:], output[0]), strict=True):
        edge_x = right[0] - left[0]
        edge_y = right[1] - left[1]
        sequence_alignment = abs(
            edge_x * sequence_axis[0] + edge_y * sequence_axis[1]
        )
        cross_alignment = abs(
            edge_x * cross_axis[0] + edge_y * cross_axis[1]
        )
        midpoint_x = (left[0] + right[0]) / 2.0
        midpoint_y = (left[1] + right[1]) / 2.0
        if sequence_alignment >= cross_alignment:
            midpoint_cross = (
                midpoint_x * cross_axis[0] + midpoint_y * cross_axis[1]
            )
            side = "cross_low" if midpoint_cross <= center_cross else "cross_high"
        else:
            midpoint_sequence = (
                midpoint_x * sequence_axis[0] + midpoint_y * sequence_axis[1]
            )
            side = (
                "sequence_start"
                if midpoint_sequence <= center_sequence
                else "sequence_end"
            )
        points_by_side[side].extend((left, right))
    edge_by_side = (
        {
            "cross_low": 0,
            "sequence_end": 1,
            "cross_high": 2,
            "sequence_start": 3,
        }
        if strip_orientation == "horizontal"
        else {
            "sequence_start": 0,
            "cross_high": 1,
            "sequence_end": 2,
            "cross_low": 3,
        }
    )
    for side in blocking_sides:
        if not points_by_side[side]:
            return False
        edge_index = edge_by_side[side]
        gold_left = gold[edge_index]
        gold_right = gold[(edge_index + 1) % 4]
        edge_x = gold_right[0] - gold_left[0]
        edge_y = gold_right[1] - gold_left[1]
        for point in points_by_side[side]:
            cross = (
                edge_x * (point[1] - gold_left[1])
                - edge_y * (point[0] - gold_left[0])
            )
            if cross > epsilon:
                return False
    return True


def _unit_vector(x: float, y: float) -> tuple[float, float]:
    magnitude = math.hypot(x, y)
    if magnitude <= 0.0:
        raise ValueError("gold frame has a degenerate axis")
    return x / magnitude, y / magnitude


def _mean_edge_axis(
    polygon: Sequence[Sequence[float]],
    first: tuple[int, int],
    second: tuple[int, int],
) -> tuple[float, float]:
    return _unit_vector(
        (
            polygon[first[1]][0]
            - polygon[first[0]][0]
            + polygon[second[1]][0]
            - polygon[second[0]][0]
        )
        / 2.0,
        (
            polygon[first[1]][1]
            - polygon[first[0]][1]
            + polygon[second[1]][1]
            - polygon[second[0]][1]
        )
        / 2.0,
    )


def _projection_bounds(
    polygon: Sequence[Sequence[float]],
    axis: tuple[float, float],
) -> tuple[float, float]:
    values = tuple(point[0] * axis[0] + point[1] * axis[1] for point in polygon)
    return min(values), max(values)


def _assert_direct_use_budget(
    sample_id: str,
    frame_index: int,
    gold: Sequence[Sequence[float]],
    output: Sequence[Sequence[float]],
    strip_orientation: str,
    blocking_sides: frozenset[str] = FRAME_SIDES,
) -> None:
    horizontal = strip_orientation == "horizontal"
    sequence_axis = _mean_edge_axis(
        gold,
        (0, 1) if horizontal else (0, 3),
        (3, 2) if horizontal else (1, 2),
    )
    cross_axis = _mean_edge_axis(
        gold,
        (0, 3) if horizontal else (0, 1),
        (1, 2) if horizontal else (3, 2),
    )
    gold_sequence = _projection_bounds(gold, sequence_axis)
    output_sequence = _projection_bounds(output, sequence_axis)
    gold_cross = _projection_bounds(gold, cross_axis)
    output_cross = _projection_bounds(output, cross_axis)
    sequence_span = gold_sequence[1] - gold_sequence[0]
    cross_span = gold_cross[1] - gold_cross[0]
    expansion_by_side = {
        "sequence_start": gold_sequence[0] - output_sequence[0],
        "sequence_end": output_sequence[1] - gold_sequence[1],
        "cross_low": gold_cross[0] - output_cross[0],
        "cross_high": output_cross[1] - gold_cross[1],
    }
    pixel_allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .transition_coordinate_sampling_uncertainty_px
    )
    sequence_limit = (
        sequence_span * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
        + pixel_allowance
    )
    cross_limit = (
        cross_span * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
        + pixel_allowance
    )
    sequence_exceeded = any(
        expansion_by_side[side] > sequence_limit
        for side in ("sequence_start", "sequence_end")
        if side in blocking_sides
    )
    cross_exceeded = any(
        expansion_by_side[side] > cross_limit
        for side in ("cross_low", "cross_high")
        if side in blocking_sides
    )
    if sequence_exceeded or cross_exceeded:
        raise ValueError(
            f"{sample_id} frame {frame_index} exceeds acceptance-baseline "
            "direct-use budget"
        )


def ordered_gold_mapping(
    gold_frames: Sequence[dict[str, object]],
    output_geometries: Sequence[dict[str, object]],
    strip_orientation: str,
    frame_blocking_sides: Sequence[frozenset[str]] | None = None,
) -> tuple[int, ...]:
    if len(gold_frames) != len(output_geometries):
        return ()
    if strip_orientation not in {"horizontal", "vertical"}:
        raise ValueError("gold strip orientation is invalid")
    if frame_blocking_sides is None:
        frame_blocking_sides = tuple(FRAME_SIDES for _frame in gold_frames)
    if len(frame_blocking_sides) != len(gold_frames) or any(
        not blocking_sides.issubset(FRAME_SIDES)
        for blocking_sides in frame_blocking_sides
    ):
        raise ValueError("gold frame blocking sides are invalid")

    mapping: list[int] = []
    next_output = 0
    for frame, blocking_sides in zip(
        gold_frames, frame_blocking_sides, strict=True
    ):
        polygon = frame["polygon_source_pixel_center_coordinates"]
        matches = tuple(
            index
            for index in range(next_output, len(output_geometries))
            if _respects_blocking_sides(
                output_geometries[index]["required_source_footprint"],
                polygon,
                strip_orientation,
                blocking_sides,
            )
        )
        if not matches:
            return ()
        selected = matches[0]
        mapping.append(selected)
        next_output = selected + 1
    return tuple(mapping)


def validate_selected_candidate_coverage(
    record: dict[str, object],
    report: dict[str, object],
) -> bool:
    """Check selected pre-decision geometry without requiring official output."""

    outputs = tuple(
        output
        for lane in report["photo_geometry"]["lanes"]
        for output in lane["output_footprints"]
    )
    if not outputs:
        return False
    sample_id = str(record["sample_id"])
    gold = record["confirmed_geometry"]
    frames = gold["frames"]
    blocking_sides = _blocking_sides_by_frame(gold, frames)
    mapping = ordered_gold_mapping(
        frames,
        outputs,
        str(gold["strip_orientation"]),
        blocking_sides,
    )
    if len(mapping) != len(frames):
        raise ValueError(
            f"{sample_id} candidate crosses user-confirmed inward baseline"
        )
    return True


def validate_approved_geometry(
    record: dict[str, object],
    report: dict[str, object],
) -> None:
    sample_id = str(record["sample_id"])
    gold = record["confirmed_geometry"]
    frames = gold["frames"]
    outputs = report["output"]["finalization"]["output_footprints"]
    blocking_sides = _blocking_sides_by_frame(gold, frames)
    mapping = ordered_gold_mapping(
        frames,
        outputs,
        str(gold["strip_orientation"]),
        blocking_sides,
    )
    if len(mapping) != len(frames):
        raise ValueError(
            f"{sample_id} approved output crosses user-confirmed inward baseline"
        )
    for frame, output_index, frame_blocking_sides in zip(
        frames, mapping, blocking_sides, strict=True
    ):
        polygon = frame["polygon_source_pixel_center_coordinates"]
        output_polygon = outputs[output_index]["required_source_footprint"]
        _assert_direct_use_budget(
            sample_id,
            int(frame["frame_index"]),
            polygon,
            output_polygon,
            str(gold["strip_orientation"]),
            frame_blocking_sides,
        )
