"""Canonical schema and geometry for the local source annotator."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Sequence

from x5crop.formats import format_spec


ANNOTATION_SCHEMA = "x5crop_source_annotation_v4"
BASELINE_SCHEMA = "x5crop_user_confirmed_source_geometry_v6"
EVALUATION_ROLE_CONTRACT = "x5crop_pre_detector_evidence_role_v2"
COORDINATE_SYSTEM = "raw_tiff_raster_pixel_centers"
MACHINE_ORIGIN = "independent_bounded_pixel_proposal_v1"
RED_MARKUP_ORIGIN = "user_red_markup_import"
RECORD_STATES = frozenset(
    {"machine_proposal", "human_adjusted", "user_confirmed"}
)
LINE_REVIEW_BASES = frozenset(
    {
        "unclassified",
        "directly_visible",
        "visible_content_limit",
        "human_width_estimate",
        "unresolved_red_stroke",
    }
)
CLIENT_EDITABLE_LINE_REVIEW_BASES = frozenset(
    {
        "unclassified",
        "directly_visible",
        "visible_content_limit",
        "human_width_estimate",
    }
)
CONFIRMABLE_LINE_REVIEW_BASES = frozenset(
    {"directly_visible", "visible_content_limit", "human_width_estimate"}
)
NON_DIRECT_LINE_REVIEW_BASES = frozenset(
    {"visible_content_limit", "human_width_estimate"}
)
SLOT_KINDS = frozenset(
    {"image", "blank_exposure", "partial_exposure", "source_truncated", "unknown"}
)
CLIENT_EDITABLE_SLOT_KINDS = frozenset(
    {"image", "partial_exposure", "source_truncated", "unknown"}
)
ADJACENCY_KINDS = frozenset(
    {"separator", "contact", "overlap", "not_applicable"}
)


class AnnotationError(RuntimeError):
    """Raised when local annotation authority or geometry is invalid."""


def canonical_record_sha256(record: dict[str, Any]) -> str:
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise AnnotationError(f"{name} must be a finite number")
    return result


def _point(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise AnnotationError(f"{name} must contain x and y")
    return _finite(value[0], f"{name}.x"), _finite(value[1], f"{name}.y")


def _matrix(value: object, name: str) -> tuple[tuple[float, float, float], ...]:
    if not isinstance(value, list) or len(value) != 3:
        raise AnnotationError(f"{name} must be a 3 by 3 matrix")
    rows: list[tuple[float, float, float]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != 3:
            raise AnnotationError(f"{name} must be a 3 by 3 matrix")
        rows.append(
            tuple(
                _finite(item, f"{name}[{row_index}]")
                for item in row
            )
        )
    if rows[2] != (0.0, 0.0, 1.0):
        raise AnnotationError(f"{name} must be affine")
    return tuple(rows)


def map_point(
    matrix: Sequence[Sequence[float]],
    point: Sequence[float],
) -> list[float]:
    x, y = float(point[0]), float(point[1])
    return [
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    ]


def _source_matrix(
    record: dict[str, Any],
    key: str,
) -> tuple[tuple[float, float, float], ...]:
    return _matrix(record["source"]["orientation_mapping"][key], key)


def raw_to_display_point(
    record: dict[str, Any],
    point: Sequence[float],
) -> list[float]:
    return map_point(_source_matrix(record, "raw_to_canonical"), point)


def display_to_raw_point(
    record: dict[str, Any],
    point: Sequence[float],
) -> list[float]:
    return map_point(_source_matrix(record, "canonical_to_raw"), point)


def _line_points_display(
    record: dict[str, Any],
    line: dict[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]]:
    points = line.get("points_raw")
    if not isinstance(points, list) or len(points) != 2:
        raise AnnotationError(f"{line.get('line_id', 'line')} requires two points")
    mapped = tuple(
        tuple(raw_to_display_point(record, _point(point, "line point")))
        for point in points
    )
    if math.dist(mapped[0], mapped[1]) < 1.0:
        raise AnnotationError(f"{line.get('line_id', 'line')} is degenerate")
    return mapped  # type: ignore[return-value]


def _intersection(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> list[float]:
    (x1, y1), (x2, y2) = first
    (x3, y3), (x4, y4) = second
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1.0e-9:
        raise AnnotationError("annotation lines do not form a stable intersection")
    first_cross = x1 * y2 - y1 * x2
    second_cross = x3 * y4 - y3 * x4
    return [
        (first_cross * (x3 - x4) - (x1 - x2) * second_cross)
        / denominator,
        (first_cross * (y3 - y4) - (y1 - y2) * second_cross)
        / denominator,
    ]


def slot_boundary_ids(
    slot: dict[str, Any],
    *,
    name: str = "slot",
) -> tuple[str, str] | None:
    """Return the authoritative boundary pair, or None when it is inapplicable."""
    reference = slot.get("reference_geometry")
    if not isinstance(reference, dict):
        raise AnnotationError(f"{name}: reference geometry is malformed")
    kind = reference.get("kind")
    if kind == "not_applicable":
        if set(reference) != {"kind"} or slot.get("slot_kind") != "blank_exposure":
            raise AnnotationError(
                f"{name}: only blank exposure may omit reference geometry"
            )
        return None
    if kind != "boundary_pair" or set(reference) != {
        "kind",
        "start_boundary_id",
        "end_boundary_id",
    }:
        raise AnnotationError(f"{name}: reference geometry is malformed")
    start = reference["start_boundary_id"]
    end = reference["end_boundary_id"]
    if (
        not isinstance(start, str)
        or not start
        or not isinstance(end, str)
        or not end
        or start == end
    ):
        raise AnnotationError(f"{name}: boundary pair is invalid")
    if slot.get("slot_kind") == "blank_exposure":
        raise AnnotationError(f"{name}: blank exposure cannot own reference boundaries")
    return start, end


def referenced_boundary_ids(record: dict[str, Any]) -> set[str]:
    return {
        line_id
        for task in record["tasks"]
        for slot in task["slots"]
        for boundary_pair in (slot_boundary_ids(slot),)
        if boundary_pair is not None
        for line_id in boundary_pair
    }


def line_basis_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Summarize active line authority without changing annotation state."""
    referenced = referenced_boundary_ids(record)
    uses: dict[str, list[str]] = {}
    for task in record["tasks"]:
        for slot in task["slots"]:
            pair = slot_boundary_ids(
                slot,
                name=f"{task['task_id']} slot {slot['ordinal']}",
            )
            if pair is None:
                continue
            uses.setdefault(pair[0], []).append(
                f"{task['task_id']}#{slot['ordinal']}.start"
            )
            uses.setdefault(pair[1], []).append(
                f"{task['task_id']}#{slot['ordinal']}.end"
            )

    active_lines = [
        *record["shared_edges"],
        *(
            line
            for line in record["boundary_pool"]
            if line["line_id"] in referenced
            or line["review_basis"] == "unresolved_red_stroke"
        ),
    ]
    attention_lines: list[dict[str, Any]] = []
    unclassified_count = 0
    non_direct_count = 0
    shared_ids = {line["line_id"] for line in record["shared_edges"]}
    for line in active_lines:
        basis = line["review_basis"]
        if basis == "directly_visible":
            continue
        is_unclassified = basis in {"unclassified", "unresolved_red_stroke"}
        unclassified_count += int(is_unclassified)
        non_direct_count += int(not is_unclassified)
        attention_lines.append(
            {
                "line_id": line["line_id"],
                "family": "shared" if line["line_id"] in shared_ids else "boundary",
                "review_basis": basis,
                "uses": (
                    [line["role"]]
                    if line["line_id"] in shared_ids
                    else sorted(set(uses.get(line["line_id"], [])))
                ),
            }
        )

    source_conditions = []
    for task in record["tasks"]:
        for slot in task["slots"]:
            if slot["slot_kind"] not in {"source_truncated", "unknown"}:
                continue
            pair = slot_boundary_ids(
                slot,
                name=f"{task['task_id']} slot {slot['ordinal']}",
            )
            source_conditions.append(
                {
                    "task_id": task["task_id"],
                    "ordinal": slot["ordinal"],
                    "slot_kind": slot["slot_kind"],
                    "line_ids": list(pair) if pair is not None else [],
                }
            )

    classification_complete = unclassified_count == 0
    if not classification_complete:
        status = "needs_classification"
    elif attention_lines or source_conditions:
        status = "has_non_direct_basis"
    else:
        status = "all_directly_visible"
    return {
        "status": status,
        "classification_complete": classification_complete,
        "all_directly_visible": status == "all_directly_visible",
        "unclassified_line_count": unclassified_count,
        "non_direct_line_count": non_direct_count,
        "attention_lines": attention_lines,
        "source_conditions": source_conditions,
    }


def frame_state_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Summarize whether every explicit task slot is a normal photo."""
    non_normal_slots = [
        {
            "task_id": task["task_id"],
            "ordinal": slot["ordinal"],
            "slot_kind": slot["slot_kind"],
        }
        for task in record["tasks"]
        for slot in task["slots"]
        if slot["slot_kind"] != "image"
    ]
    pending_source_truncation = _pending_source_truncated_geometry(record)
    all_normal = not non_normal_slots
    return {
        "status": (
            "all_frames_normal" if all_normal else "has_non_normal_frames"
        ),
        "all_frames_normal": all_normal,
        "non_normal_slot_count": len(non_normal_slots),
        "non_normal_slots": non_normal_slots,
        "pending_source_truncated_geometry_count": len(pending_source_truncation),
        "pending_source_truncated_geometry": pending_source_truncation,
    }


def _floating_partial_sequence_facts(
    *,
    format_id: str,
    strip_axis_display: str,
    source_canonical_extent: dict[str, Any],
    orientation_mapping: dict[str, Any],
    shared_edges: Sequence[dict[str, Any]],
    boundary_pool: Sequence[dict[str, Any]],
    task: dict[str, Any],
) -> dict[str, Any]:
    """Describe a partial task that floats by at least one W on both sides."""

    result: dict[str, Any] = {
        "two_sided_floating_source_span": False,
        "direct_sequence_outer_count": 0,
        "source_axis_margin_frame_ratios": None,
    }
    try:
        physical = format_spec(str(format_id))
    except KeyError:
        return result
    count = task.get("count")
    slots = task.get("slots")
    if (
        physical.layout.kind != "single_strip"
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or count >= physical.maximum_full_count
        or not isinstance(slots, list)
        or len(slots) != count
        or not slots
    ):
        return result
    first_pair = slot_boundary_ids(slots[0], name=f"{task['task_id']} first slot")
    last_pair = slot_boundary_ids(slots[-1], name=f"{task['task_id']} last slot")
    if first_pair is None or last_pair is None:
        return result

    boundary_by_id = {line["line_id"]: line for line in boundary_pool}
    outer_ids = (first_pair[0], last_pair[1])
    result["direct_sequence_outer_count"] = sum(
        boundary_by_id[line_id]["review_basis"] == "directly_visible"
        for line_id in outer_ids
    )
    role_record = {
        "source": {
            "canonical_extent": source_canonical_extent,
            "orientation_mapping": orientation_mapping,
        },
        "strip_axis_display": strip_axis_display,
        "shared_edges": list(shared_edges),
        "boundary_pool": list(boundary_pool),
    }
    polygons = _physical_frame_polygons_display(role_record, task)
    if not polygons:
        return result
    horizontal = strip_axis_display == "horizontal"
    long_axis = 0 if horizontal else 1
    long_extent_key = "width" if horizontal else "height"
    long_extent = float(source_canonical_extent[long_extent_key])
    cross_edges = ((0, 3), (1, 2)) if horizontal else ((0, 1), (3, 2))
    cross_spans = sorted(
        math.dist(polygon[left], polygon[right])
        for polygon in polygons
        for left, right in cross_edges
    )
    midpoint = len(cross_spans) // 2
    median_cross_span = (
        cross_spans[midpoint]
        if len(cross_spans) % 2
        else (cross_spans[midpoint - 1] + cross_spans[midpoint]) / 2.0
    )
    nominal_frame_width = (
        median_cross_span
        * physical.frame.frame_width_mm
        / physical.frame.frame_height_mm
    )
    if not math.isfinite(nominal_frame_width) or nominal_frame_width <= 0.0:
        raise AnnotationError("floating partial sequence has no valid nominal W")
    group_minimum = min(
        point[long_axis]
        for polygon in polygons
        for point in polygon
    )
    group_maximum = max(
        point[long_axis]
        for polygon in polygons
        for point in polygon
    )
    margins = (
        group_minimum + 0.5,
        long_extent - 0.5 - group_maximum,
    )
    result["source_axis_margin_frame_ratios"] = [
        margin / nominal_frame_width for margin in margins
    ]
    result["two_sided_floating_source_span"] = all(
        margin + 1.0e-7 >= nominal_frame_width for margin in margins
    )
    return result


def evaluation_task_role(
    *,
    format_id: str,
    strip_axis_display: str,
    source_canonical_extent: dict[str, Any],
    orientation_mapping: dict[str, Any],
    shared_edges: Sequence[dict[str, Any]],
    boundary_pool: Sequence[dict[str, Any]],
    task: dict[str, Any],
    pending_source_truncated_ordinals: Iterable[int] = (),
) -> dict[str, Any]:
    """Derive one task role only from frozen pre-detector evidence."""
    boundary_by_id = {
        line["line_id"]: line
        for line in boundary_pool
    }
    pending_ordinals = set(pending_source_truncated_ordinals)
    try:
        physical = format_spec(str(format_id))
    except KeyError:
        physical = None

    reasons: list[str] = []
    boundary_ids: set[str] = set()
    non_direct_by_frame: dict[int, set[str]] = {}
    for slot in task["slots"]:
        pair = slot_boundary_ids(
            slot,
            name=f"{task['task_id']} slot {slot['ordinal']}",
        )
        if pair is None:
            continue
        boundary_ids.update(pair)
        non_direct = {
            line_id
            for line_id in pair
            if boundary_by_id[line_id]["review_basis"]
            in NON_DIRECT_LINE_REVIEW_BASES
        }
        if non_direct:
            non_direct_by_frame[slot["ordinal"]] = non_direct

    non_direct_boundary_ids = (
        set().union(*non_direct_by_frame.values())
        if non_direct_by_frame
        else set()
    )
    two_sided_non_direct_frames = sorted(
        ordinal
        for ordinal, line_ids in non_direct_by_frame.items()
        if len(line_ids) == 2
    )
    clustered_non_direct_frames = [
        ordinal
        for ordinal in two_sided_non_direct_frames
        if any(
            other_ordinal != ordinal
            and bool(other_line_ids - non_direct_by_frame[ordinal])
            for other_ordinal, other_line_ids in non_direct_by_frame.items()
        )
    ]
    task_boundaries = [boundary_by_id[line_id] for line_id in boundary_ids]
    required_lines = [*shared_edges, *task_boundaries]

    if any(
        line["review_basis"] not in CONFIRMABLE_LINE_REVIEW_BASES
        for line in required_lines
    ):
        reasons.append("required_boundary_basis_missing")
    if any(line["review_basis"] != "directly_visible" for line in shared_edges):
        reasons.append("shared_edges_lack_direct_visibility")
    if not any(
        line["review_basis"] == "directly_visible"
        for line in task_boundaries
    ):
        reasons.append("no_direct_sequence_anchor")
    count = task["count"]
    non_direct_boundary_challenge_threshold = (
        2
        if isinstance(count, int)
        and not isinstance(count, bool)
        and count <= 3
        else 4
    )
    if clustered_non_direct_frames:
        reasons.append("clustered_non_direct_boundaries")
    if len(non_direct_boundary_ids) >= non_direct_boundary_challenge_threshold:
        reasons.append("non_direct_boundary_count_threshold")
    if any(slot["slot_kind"] == "unknown" for slot in task["slots"]):
        reasons.append("unknown_required_frame")
    if any(adjacency["kind"] == "contact" for adjacency in task["adjacencies"]):
        reasons.append("contact_adjacency")
    if any(adjacency["kind"] == "overlap" for adjacency in task["adjacencies"]):
        reasons.append("overlap_adjacency")
    if any(slot["ordinal"] in pending_ordinals for slot in task["slots"]):
        reasons.append("source_truncation_not_geometrically_established")

    floating_partial = _floating_partial_sequence_facts(
        format_id=format_id,
        strip_axis_display=strip_axis_display,
        source_canonical_extent=source_canonical_extent,
        orientation_mapping=orientation_mapping,
        shared_edges=shared_edges,
        boundary_pool=boundary_pool,
        task=task,
    )
    if (
        floating_partial["two_sided_floating_source_span"]
        and floating_partial["direct_sequence_outer_count"] < 2
    ):
        reasons.append("two_sided_floating_partial_sequence")

    count_supported = (
        physical is not None
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
        and (
            count == physical.maximum_full_count
            if physical.layout.kind == "dual_lane"
            else count <= physical.maximum_full_count
        )
    )
    if not count_supported:
        reasons.append("count_outside_fixed_template_contract")

    return {
        "task_id": task["task_id"],
        "sample_id": task["sample_id"],
        "count": count,
        "cohort_role": "challenge" if reasons else "nominal",
        "reasons": reasons,
        "non_direct_boundary_count": len(non_direct_boundary_ids),
        "non_direct_boundary_challenge_threshold": (
            non_direct_boundary_challenge_threshold
        ),
        "non_direct_boundary_ids": sorted(non_direct_boundary_ids),
        "two_sided_non_direct_frame_ordinals": two_sided_non_direct_frames,
        "clustered_non_direct_frame_ordinals": clustered_non_direct_frames,
        **floating_partial,
    }


def evaluation_role_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Derive pre-detector nominal/challenge roles from reviewable task facts."""
    pending_by_task: dict[str, set[int]] = {}
    for item in _pending_source_truncated_geometry(record):
        pending_by_task.setdefault(item["task_id"], set()).add(item["ordinal"])
    tasks = [
        evaluation_task_role(
            format_id=str(record["format_id"]),
            strip_axis_display=str(record["strip_axis_display"]),
            source_canonical_extent=record["source"]["canonical_extent"],
            orientation_mapping=record["source"]["orientation_mapping"],
            shared_edges=record["shared_edges"],
            boundary_pool=record["boundary_pool"],
            task=task,
            pending_source_truncated_ordinals=pending_by_task.get(
                task["task_id"], ()
            ),
        )
        for task in record["tasks"]
    ]

    challenge_count = sum(
        task["cohort_role"] == "challenge"
        for task in tasks
    )
    return {
        "source_role": "challenge" if challenge_count else "nominal",
        "nominal_task_count": len(tasks) - challenge_count,
        "challenge_task_count": challenge_count,
        "tasks": tasks,
    }


def _polygon_area(polygon: Sequence[Sequence[float]]) -> float:
    return (
        sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(
                polygon,
                (*polygon[1:], polygon[0]),
                strict=True,
            )
        )
        / 2.0
    )


def _physical_frame_polygons_display(
    record: dict[str, Any],
    task: dict[str, Any],
) -> tuple[list[list[float]], ...]:
    shared = record.get("shared_edges")
    boundary_pool = record.get("boundary_pool")
    slots = task.get("slots")
    count = task.get("count")
    if not isinstance(shared, list) or len(shared) != 2:
        raise AnnotationError("source annotation requires two shared edges")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or not isinstance(boundary_pool, list)
        or not isinstance(slots, list)
        or len(slots) != count
    ):
        raise AnnotationError("task slot count does not match explicit count")
    pool_by_id = {
        line.get("line_id"): line
        for line in boundary_pool
        if isinstance(line, dict)
    }
    boundary_pairs = [
        (slot, slot_boundary_ids(slot, name=f"slot {slot.get('ordinal', '?')}"))
        for slot in slots
        if isinstance(slot, dict)
    ]
    if len(boundary_pairs) != count or len(pool_by_id) != len(boundary_pool) or any(
        line_id not in pool_by_id
        for _slot, pair in boundary_pairs
        if pair is not None
        for line_id in pair
    ):
        raise AnnotationError("task references an unknown physical boundary")
    low = _line_points_display(record, shared[0])
    high = _line_points_display(record, shared[1])
    horizontal = record.get("strip_axis_display") == "horizontal"
    polygons: list[list[list[float]]] = []
    for _slot, pair in boundary_pairs:
        if pair is None:
            continue
        start = _line_points_display(record, pool_by_id[pair[0]])
        stop = _line_points_display(record, pool_by_id[pair[1]])
        if horizontal:
            polygon = [
                _intersection(low, start),
                _intersection(low, stop),
                _intersection(high, stop),
                _intersection(high, start),
            ]
        else:
            polygon = [
                _intersection(low, start),
                _intersection(high, start),
                _intersection(high, stop),
                _intersection(low, stop),
            ]
        polygons.append(polygon)
    return tuple(polygons)


def _pending_source_truncated_geometry(
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return source-truncated slots whose physical frame is still fully in raster."""
    extent = record["source"]["canonical_extent"]
    width = float(extent["width"])
    height = float(extent["height"])
    pending: list[dict[str, Any]] = []
    for task in record["tasks"]:
        physical_polygons = _physical_frame_polygons_display(record, task)
        reference_slots = [
            slot
            for slot in task["slots"]
            if slot_boundary_ids(slot) is not None
        ]
        for slot, polygon in zip(reference_slots, physical_polygons, strict=True):
            if slot["slot_kind"] != "source_truncated":
                continue
            leaves_source = any(
                not -0.5 <= x <= width - 0.5
                or not -0.5 <= y <= height - 0.5
                for x, y in polygon
            )
            if not leaves_source:
                pending.append(
                    {
                        "task_id": task["task_id"],
                        "ordinal": slot["ordinal"],
                    }
                )
    return pending


def _clip_polygon_to_source_raster(
    record: dict[str, Any],
    polygon: Sequence[Sequence[float]],
) -> list[list[float]]:
    extent = record["source"]["canonical_extent"]
    bounds = (
        (0, -0.5, True),
        (0, float(extent["width"]) - 0.5, False),
        (1, -0.5, True),
        (1, float(extent["height"]) - 0.5, False),
    )

    def append_unique(points: list[list[float]], point: Sequence[float]) -> None:
        candidate = [float(point[0]), float(point[1])]
        if not points or math.dist(points[-1], candidate) > 1.0e-9:
            points.append(candidate)

    clipped = [[float(point[0]), float(point[1])] for point in polygon]
    for axis, boundary, keep_greater in bounds:
        if not clipped:
            break
        output: list[list[float]] = []
        previous = clipped[-1]
        previous_inside = (
            previous[axis] >= boundary
            if keep_greater
            else previous[axis] <= boundary
        )
        for current in clipped:
            current_inside = (
                current[axis] >= boundary
                if keep_greater
                else current[axis] <= boundary
            )
            if current_inside != previous_inside:
                delta = current[axis] - previous[axis]
                if abs(delta) <= 1.0e-12:
                    raise AnnotationError("source-raster clipping is numerically unstable")
                fraction = (boundary - previous[axis]) / delta
                intersection = [
                    previous[index]
                    + fraction * (current[index] - previous[index])
                    for index in range(2)
                ]
                intersection[axis] = boundary
                append_unique(output, intersection)
            if current_inside:
                append_unique(output, current)
            previous = current
            previous_inside = current_inside
        if len(output) > 1 and math.dist(output[0], output[-1]) <= 1.0e-9:
            output.pop()
        clipped = output
    return clipped


def frame_polygons_display(
    record: dict[str, Any],
    task: dict[str, Any],
) -> tuple[list[list[float]], ...]:
    physical_polygons = _physical_frame_polygons_display(record, task)
    reference_slots = [
        slot
        for slot in task["slots"]
        if slot_boundary_ids(slot) is not None
    ]
    return tuple(
        _clip_polygon_to_source_raster(record, polygon)
        if slot["slot_kind"] == "source_truncated"
        else polygon
        for slot, polygon in zip(reference_slots, physical_polygons, strict=True)
    )


def frame_polygons_raw(
    record: dict[str, Any],
    task: dict[str, Any],
) -> tuple[list[list[float]], ...]:
    return tuple(
        [display_to_raw_point(record, point) for point in polygon]
        for polygon in frame_polygons_display(record, task)
    )


def _validate_line(
    record: dict[str, Any],
    line: object,
    *,
    expected_role: str,
) -> None:
    if not isinstance(line, dict):
        raise AnnotationError("annotation line must be an object")
    if set(line) != {
        "line_id",
        "role",
        "points_raw",
        "origin",
        "review_basis",
    }:
        raise AnnotationError("annotation line has unexpected fields")
    if not isinstance(line["line_id"], str) or not line["line_id"]:
        raise AnnotationError("annotation line requires an identity")
    if line["role"] != expected_role:
        raise AnnotationError(f"{line['line_id']} has an unexpected role")
    if not isinstance(line["origin"], str) or not line["origin"]:
        raise AnnotationError(f"{line['line_id']} requires provenance")
    if (
        not isinstance(line["review_basis"], str)
        or line["review_basis"] not in LINE_REVIEW_BASES
    ):
        raise AnnotationError(f"{line['line_id']} has an invalid review basis")
    _line_points_display(record, line)


def _boundary_axis_position(
    record: dict[str, Any],
    line: dict[str, Any],
) -> float:
    first, second = _line_points_display(record, line)
    horizontal = record["strip_axis_display"] == "horizontal"
    if horizontal:
        reference = 0.5 * (
            float(record["source"]["canonical_extent"]["height"]) - 1.0
        )
        denominator = second[1] - first[1]
        if abs(denominator) < 1.0e-9:
            raise AnnotationError("long boundary is parallel to the strip axis")
        return first[0] + (second[0] - first[0]) * (reference - first[1]) / denominator
    reference = 0.5 * (
        float(record["source"]["canonical_extent"]["width"]) - 1.0
    )
    denominator = second[0] - first[0]
    if abs(denominator) < 1.0e-9:
        raise AnnotationError("long boundary is parallel to the strip axis")
    return first[1] + (second[1] - first[1]) * (reference - first[0]) / denominator


def _derived_adjacency_kind(
    record: dict[str, Any],
    left_slot: dict[str, Any],
    right_slot: dict[str, Any],
    pool_by_id: dict[str, dict[str, Any]],
) -> str:
    left_pair = slot_boundary_ids(left_slot)
    right_pair = slot_boundary_ids(right_slot)
    if left_pair is None or right_pair is None:
        return "not_applicable"
    left_end_id = left_pair[1]
    right_start_id = right_pair[0]
    if left_end_id == right_start_id:
        return "contact"
    left_end = _boundary_axis_position(record, pool_by_id[left_end_id])
    right_start = _boundary_axis_position(record, pool_by_id[right_start_id])
    return "overlap" if left_end > right_start else "separator"


def refresh_adjacency_kinds(record: dict[str, Any]) -> int:
    """Store adjacency facts derived only from the current slot geometry."""
    pool_by_id = {line["line_id"]: line for line in record["boundary_pool"]}
    changed = 0
    for task in record["tasks"]:
        for index, adjacency in enumerate(task["adjacencies"]):
            kind = _derived_adjacency_kind(
                record,
                task["slots"][index],
                task["slots"][index + 1],
                pool_by_id,
            )
            if adjacency["kind"] != kind:
                adjacency["kind"] = kind
                changed += 1
    return changed


def _validate_source(record: dict[str, Any]) -> None:
    source = record.get("source")
    if not isinstance(source, dict) or set(source) != {
        "canonical_sample_id",
        "relative_path",
        "sha256",
        "raw_extent",
        "canonical_extent",
        "orientation_mapping",
    }:
        raise AnnotationError("annotation source identity is malformed")
    if (
        not isinstance(source["canonical_sample_id"], str)
        or not source["canonical_sample_id"]
        or not isinstance(source["relative_path"], str)
        or not source["relative_path"]
        or not isinstance(source["sha256"], str)
        or len(source["sha256"]) != 64
    ):
        raise AnnotationError("annotation source identity is incomplete")
    for extent_name in ("raw_extent", "canonical_extent"):
        extent = source[extent_name]
        if (
            not isinstance(extent, dict)
            or set(extent) != {"width", "height"}
            or not isinstance(extent["width"], int)
            or isinstance(extent["width"], bool)
            or not isinstance(extent["height"], int)
            or isinstance(extent["height"], bool)
            or extent["width"] <= 0
            or extent["height"] <= 0
        ):
            raise AnnotationError(f"{extent_name} is invalid")
    mapping = source["orientation_mapping"]
    if not isinstance(mapping, dict) or set(mapping) != {
        "original_tag",
        "raw_to_canonical",
        "canonical_to_raw",
    }:
        raise AnnotationError("source orientation mapping is malformed")
    if mapping["original_tag"] not in range(1, 9):
        raise AnnotationError("source orientation tag is unsupported")
    raw_to_display = _matrix(mapping["raw_to_canonical"], "raw_to_canonical")
    display_to_raw = _matrix(mapping["canonical_to_raw"], "canonical_to_raw")
    raw_extent = source["raw_extent"]
    probes = (
        (0.0, 0.0),
        (float(raw_extent["width"] - 1), 0.0),
        (0.0, float(raw_extent["height"] - 1)),
    )
    for probe in probes:
        round_trip = map_point(
            display_to_raw,
            map_point(raw_to_display, probe),
        )
        if math.dist(probe, round_trip) > 1.0e-6:
            raise AnnotationError("source orientation matrices are not reversible")


def validate_annotation_record(record: dict[str, Any]) -> None:
    expected_keys = {
        "annotation_schema",
        "revision",
        "state",
        "source",
        "format_id",
        "strip_axis_display",
        "coordinate_system",
        "origin",
        "shared_edges",
        "boundary_pool",
        "tasks",
        "diagnostics",
        "reviewed_task_ids",
        "confirmation",
    }
    if set(record) != expected_keys:
        raise AnnotationError("annotation record has unexpected fields")
    if record["annotation_schema"] != ANNOTATION_SCHEMA:
        raise AnnotationError("annotation schema is not current")
    if (
        not isinstance(record["revision"], int)
        or isinstance(record["revision"], bool)
        or record["revision"] < 1
    ):
        raise AnnotationError("annotation revision is invalid")
    if record["state"] not in RECORD_STATES:
        raise AnnotationError("annotation state is invalid")
    if record["coordinate_system"] != COORDINATE_SYSTEM:
        raise AnnotationError("annotation coordinates are not raw TIFF pixels")
    if record["strip_axis_display"] not in {"horizontal", "vertical"}:
        raise AnnotationError("display strip axis is invalid")
    if not isinstance(record["format_id"], str) or not record["format_id"]:
        raise AnnotationError("annotation format is missing")
    if not isinstance(record["origin"], str) or not record["origin"]:
        raise AnnotationError("annotation origin is missing")
    if not isinstance(record["diagnostics"], dict):
        raise AnnotationError("annotation diagnostics must be typed facts")
    unresolved = record["diagnostics"].get("unresolved", [])
    if not isinstance(unresolved, list):
        raise AnnotationError("annotation unresolved diagnostics must be a list")
    if record["state"] == "user_confirmed" and unresolved:
        raise AnnotationError(
            "confirmed annotation cannot retain unresolved proposal hints"
        )
    _validate_source(record)

    shared = record["shared_edges"]
    if not isinstance(shared, list) or len(shared) != 2:
        raise AnnotationError("annotation requires exactly two shared edges")
    _validate_line(record, shared[0], expected_role="short_low")
    _validate_line(record, shared[1], expected_role="short_high")
    line_ids = {shared[0]["line_id"], shared[1]["line_id"]}

    boundary_pool = record["boundary_pool"]
    if not isinstance(boundary_pool, list):
        raise AnnotationError("annotation requires a physical boundary pool")
    for boundary in boundary_pool:
        _validate_line(record, boundary, expected_role="long_boundary")
        if boundary["line_id"] in line_ids:
            raise AnnotationError("annotation line identities must be unique")
        line_ids.add(boundary["line_id"])
    pool_ids = {line["line_id"] for line in boundary_pool}

    tasks = record["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise AnnotationError("annotation requires at least one task")
    task_ids: set[str] = set()
    canonical_extent = record["source"]["canonical_extent"]
    width = float(canonical_extent["width"])
    height = float(canonical_extent["height"])
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {
            "task_id",
            "sample_id",
            "source_relative_path",
            "count",
            "slots",
            "adjacencies",
        }:
            raise AnnotationError("annotation task is malformed")
        task_id = task["task_id"]
        if (
            not isinstance(task_id, str)
            or not task_id
            or task_id in task_ids
            or task["sample_id"] != task_id
            or not isinstance(task["source_relative_path"], str)
            or not task["source_relative_path"]
        ):
            raise AnnotationError("annotation task identity is invalid")
        task_ids.add(task_id)
        count = task["count"]
        slots = task["slots"]
        adjacencies = task["adjacencies"]
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or not isinstance(slots, list)
            or len(slots) != count
            or not isinstance(adjacencies, list)
            or len(adjacencies) != max(0, count - 1)
        ):
            raise AnnotationError("annotation task count is invalid")
        if any(
            not isinstance(slot, dict)
            or set(slot) != {
                "ordinal",
                "slot_kind",
                "reference_geometry",
            }
            for slot in slots
        ):
            raise AnnotationError(f"{task_id}: slot mapping is malformed")
        if [slot["ordinal"] for slot in slots] != list(range(1, count + 1)):
            raise AnnotationError(f"{task_id}: slot ordinals are not canonical")
        if any(
            not isinstance(slot["slot_kind"], str)
            or slot["slot_kind"] not in SLOT_KINDS
            for slot in slots
        ):
            raise AnnotationError(f"{task_id}: slot semantics are invalid")
        boundary_pairs = [
            slot_boundary_ids(slot, name=f"{task_id} slot {slot['ordinal']}")
            for slot in slots
        ]
        boundary_ids = [
            line_id
            for pair in boundary_pairs
            if pair is not None
            for line_id in pair
        ]
        if not set(boundary_ids).issubset(pool_ids):
            raise AnnotationError(f"{task_id}: task references an unknown boundary")
        if any(
            not isinstance(adjacency, dict)
            or set(adjacency) != {"left_ordinal", "right_ordinal", "kind"}
            for adjacency in adjacencies
        ):
            raise AnnotationError(f"{task_id}: adjacency mapping is malformed")
        expected_pairs = [(index, index + 1) for index in range(1, count)]
        actual_pairs = [
            (adjacency["left_ordinal"], adjacency["right_ordinal"])
            for adjacency in adjacencies
        ]
        if actual_pairs != expected_pairs or any(
            not isinstance(adjacency["kind"], str)
            or adjacency["kind"] not in ADJACENCY_KINDS
            for adjacency in adjacencies
        ):
            raise AnnotationError(f"{task_id}: adjacency semantics are invalid")
        pool_by_id = {line["line_id"]: line for line in boundary_pool}
        for index, adjacency in enumerate(adjacencies):
            expected_kind = _derived_adjacency_kind(
                record,
                slots[index],
                slots[index + 1],
                pool_by_id,
            )
            if adjacency["kind"] != expected_kind:
                raise AnnotationError(
                    f"{task_id}: adjacency {index + 1}-{index + 2} must be "
                    f"derived as {expected_kind}"
                )
        uses: dict[str, list[tuple[int, str]]] = {}
        for slot, pair in zip(slots, boundary_pairs, strict=True):
            if pair is None:
                continue
            uses.setdefault(pair[0], []).append((slot["ordinal"], "start"))
            uses.setdefault(pair[1], []).append((slot["ordinal"], "end"))
        for roles in uses.values():
            if len(roles) == 1:
                continue
            if len(roles) != 2:
                raise AnnotationError(f"{task_id}: physical line is reused ambiguously")
            first, second = sorted(roles)
            if first[1] != "end" or second != (first[0] + 1, "start"):
                raise AnnotationError(f"{task_id}: physical line reuse is not contact")
            if adjacencies[first[0] - 1]["kind"] != "contact":
                raise AnnotationError(f"{task_id}: reused line lacks contact semantics")
        physical_polygons = _physical_frame_polygons_display(record, task)
        polygons = frame_polygons_display(record, task)
        reference_slots = [
            slot
            for slot in slots
            if slot_boundary_ids(slot) is not None
        ]
        previous_center = -math.inf
        horizontal = record["strip_axis_display"] == "horizontal"
        for slot, physical_polygon, polygon in zip(
            reference_slots,
            physical_polygons,
            polygons,
            strict=True,
        ):
            if _polygon_area(physical_polygon) < 4.0:
                raise AnnotationError("annotation frame is degenerate or reversed")
            leaves_source = any(
                not -0.5 <= x <= width - 0.5
                or not -0.5 <= y <= height - 0.5
                for x, y in physical_polygon
            )
            if leaves_source and slot["slot_kind"] != "source_truncated":
                raise AnnotationError(
                    f"{task_id} frame {slot['ordinal']} leaves the source raster; "
                    "classify it as source_truncated only when the TIFF truly cuts it"
                )
            if _polygon_area(polygon) < 4.0:
                raise AnnotationError(
                    f"{task_id} frame {slot['ordinal']} has no usable source-raster intersection"
                )
            if any(
                not -0.5 <= x <= width - 0.5
                or not -0.5 <= y <= height - 0.5
                for x, y in polygon
            ):
                raise AnnotationError("source-raster clipping did not contain the frame")
            center = sum(
                point[0 if horizontal else 1] for point in polygon
            ) / len(polygon)
            if center <= previous_center:
                raise AnnotationError("annotation frames are not in display order")
            previous_center = center

    canonical_task = min(
        tasks,
        key=lambda task: (
            -int(task["count"]),
            -sum(slot_boundary_ids(slot) is not None for slot in task["slots"]),
            str(task["task_id"]),
        ),
    )
    canonical_pairs = {
        pair
        for slot in canonical_task["slots"]
        if (pair := slot_boundary_ids(slot)) is not None
    }
    if any(
        pair not in canonical_pairs
        for task in tasks
        for slot in task["slots"]
        if (pair := slot_boundary_ids(slot)) is not None
    ):
        raise AnnotationError(
            "count task reference geometry is not a subset of the source reference"
        )

    physical_frame_kinds: dict[tuple[str, str], str] = {}
    for task in tasks:
        for slot in task["slots"]:
            pair = slot_boundary_ids(slot)
            if pair is None:
                continue
            previous = physical_frame_kinds.setdefault(pair, slot["slot_kind"])
            if previous != slot["slot_kind"]:
                raise AnnotationError(
                    "one physical frame cannot have conflicting slot kinds"
                )

    used_boundary_ids = referenced_boundary_ids(record)
    if any(
        line["line_id"] not in used_boundary_ids
        and line["review_basis"] != "unresolved_red_stroke"
        for line in boundary_pool
    ):
        raise AnnotationError("unused machine boundary is not reference geometry")

    reviewed = record["reviewed_task_ids"]
    if (
        not isinstance(reviewed, list)
        or len(set(reviewed)) != len(reviewed)
        or not set(reviewed).issubset(task_ids)
        or (reviewed and set(reviewed) != task_ids)
    ):
        raise AnnotationError("source reference review state is invalid")
    confirmation = record["confirmation"]
    if record["state"] == "user_confirmed":
        if not isinstance(confirmation, dict) or set(confirmation) != {
            "confirmed_at_utc",
            "proposal_snapshot_sha256",
            "review_artifact_relative_path",
            "review_artifact_sha256",
            "checklist",
        }:
            raise AnnotationError("confirmed annotation lacks exact evidence")
        if set(reviewed) != task_ids:
            raise AnnotationError("all task mappings must be reviewed before confirmation")
        checklist = confirmation["checklist"]
        if (
            not isinstance(checklist, dict)
            or set(checklist) != {
                "shared_edges",
                "task_boundaries",
                "native_pixel_checks",
                "safe_without_bleed",
            }
            or not all(value is True for value in checklist.values())
        ):
            raise AnnotationError("confirmation checklist is incomplete")
        basis_summary = line_basis_summary(record)
        if not basis_summary["classification_complete"]:
            line_ids = ", ".join(
                line["line_id"]
                for line in basis_summary["attention_lines"]
                if line["review_basis"] not in CONFIRMABLE_LINE_REVIEW_BASES
            )
            raise AnnotationError(
                f"confirmed annotation has unclassified lines: {line_ids}"
            )
        pending_source_truncation = _pending_source_truncated_geometry(record)
        if pending_source_truncation:
            frames = ", ".join(
                f"{item['task_id']}#{item['ordinal']}"
                for item in pending_source_truncation
            )
            raise AnnotationError(
                "source_truncated frames must physically leave the source raster "
                f"before confirmation: {frames}"
            )
    elif confirmation is not None:
        raise AnnotationError("unconfirmed annotation cannot carry confirmation")


def geometry_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "annotation_schema": record["annotation_schema"],
        "source": deepcopy(record["source"]),
        "format_id": record["format_id"],
        "strip_axis_display": record["strip_axis_display"],
        "coordinate_system": record["coordinate_system"],
        "shared_edges": deepcopy(record["shared_edges"]),
        "boundary_pool": deepcopy(record["boundary_pool"]),
        "tasks": deepcopy(record["tasks"]),
    }


def record_for_client(record: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(record)
    result["line_basis_summary"] = line_basis_summary(record)
    result["frame_state_summary"] = frame_state_summary(record)
    result["evaluation_role_summary"] = evaluation_role_summary(record)
    for line in result["shared_edges"]:
        line["points_display"] = [
            raw_to_display_point(record, point)
            for point in line.pop("points_raw")
        ]
    for line in result["boundary_pool"]:
        line["points_display"] = [
            raw_to_display_point(record, point)
            for point in line.pop("points_raw")
        ]
    return result


def apply_client_geometry(
    current: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    if set(payload) != {
        "expected_revision",
        "shared_edges",
        "boundary_pool",
        "slot_kinds",
    }:
        raise AnnotationError("geometry update has unexpected fields")
    if (
        not isinstance(payload["expected_revision"], int)
        or isinstance(payload["expected_revision"], bool)
        or payload["expected_revision"] != current["revision"]
    ):
        raise AnnotationError("annotation revision conflict")
    if current["state"] == "user_confirmed":
        raise AnnotationError("confirmed annotation is immutable")
    updated = deepcopy(current)
    changed_refinement_line_ids: set[str] = set()

    def replace_lines(
        target: list[dict[str, Any]],
        incoming: object,
    ) -> None:
        if not isinstance(incoming, list) or len(incoming) != len(target):
            raise AnnotationError("geometry line set does not match the task")
        incoming_by_id: dict[str, dict[str, Any]] = {}
        for item in incoming:
            if (
                not isinstance(item, dict)
                or set(item) != {"line_id", "points_display", "review_basis"}
                or not isinstance(item["line_id"], str)
                or not isinstance(item["review_basis"], str)
                or item["review_basis"] not in LINE_REVIEW_BASES
            ):
                raise AnnotationError("geometry line update is malformed")
            incoming_by_id[item["line_id"]] = item
        if set(incoming_by_id) != {line["line_id"] for line in target}:
            raise AnnotationError("geometry line identities changed")
        for line in target:
            incoming_line = incoming_by_id[line["line_id"]]
            points = incoming_line["points_display"]
            if not isinstance(points, list) or len(points) != 2:
                raise AnnotationError("geometry line requires two display points")
            requested_basis = incoming_line["review_basis"]
            if requested_basis != line["review_basis"] and (
                requested_basis not in CLIENT_EDITABLE_LINE_REVIEW_BASES
            ):
                raise AnnotationError("line review basis change is not editable")
            mapped = [
                display_to_raw_point(updated, _point(point, "display point"))
                for point in points
            ]
            geometry_changed = any(
                math.dist(before, after) > 1.0e-7
                for before, after in zip(line["points_raw"], mapped, strict=True)
            )
            if geometry_changed:
                line["origin"] = "human_adjustment"
                changed_refinement_line_ids.add(str(line["line_id"]))
            if requested_basis != line["review_basis"]:
                changed_refinement_line_ids.add(str(line["line_id"]))
            line["review_basis"] = requested_basis
            line["points_raw"] = mapped

    replace_lines(
        updated["shared_edges"],
        payload["shared_edges"],
    )
    replace_lines(
        updated["boundary_pool"],
        payload["boundary_pool"],
    )

    incoming_slot_kinds = payload["slot_kinds"]
    if not isinstance(incoming_slot_kinds, list):
        raise AnnotationError("slot kind update must be a list")
    current_slots = {
        (task["task_id"], slot["ordinal"]): slot
        for task in updated["tasks"]
        for slot in task["slots"]
    }
    requested_slot_kinds: dict[tuple[str, int], str] = {}
    for item in incoming_slot_kinds:
        if (
            not isinstance(item, dict)
            or set(item) != {"task_id", "ordinal", "slot_kind"}
            or not isinstance(item["task_id"], str)
            or not isinstance(item["ordinal"], int)
            or isinstance(item["ordinal"], bool)
            or not isinstance(item["slot_kind"], str)
            or item["slot_kind"] not in SLOT_KINDS
        ):
            raise AnnotationError("slot kind update is malformed")
        identity = (item["task_id"], item["ordinal"])
        if identity in requested_slot_kinds:
            raise AnnotationError("slot kind identities are duplicated")
        requested_slot_kinds[identity] = item["slot_kind"]
    if set(requested_slot_kinds) != set(current_slots):
        raise AnnotationError("slot kind identities changed")
    for identity, slot in current_slots.items():
        requested_kind = requested_slot_kinds[identity]
        if requested_kind != slot["slot_kind"] and (
            requested_kind not in CLIENT_EDITABLE_SLOT_KINDS
            or slot["slot_kind"] not in CLIENT_EDITABLE_SLOT_KINDS
        ):
            raise AnnotationError("slot kind change is not editable")
        if requested_kind != slot["slot_kind"]:
            pair = slot_boundary_ids(slot)
            if pair is not None:
                changed_refinement_line_ids.update(pair)
        slot["slot_kind"] = requested_kind

    refresh_adjacency_kinds(updated)

    updated["revision"] += 1
    updated["state"] = "human_adjusted"
    updated["reviewed_task_ids"] = []
    updated["confirmation"] = None
    refinement = updated["diagnostics"].get("refinement")
    if isinstance(refinement, dict):
        line_evidence = refinement.get("lines")
        if isinstance(line_evidence, dict):
            for line_id in changed_refinement_line_ids:
                evidence = line_evidence.get(line_id)
                if isinstance(evidence, dict):
                    evidence["human_review_status"] = "adjusted_after_refinement"
        refinement["human_review_state"] = "pending"
        refinement["current_geometry_sha256"] = canonical_record_sha256(
            geometry_snapshot(updated)
        )
    validate_annotation_record(updated)
    return updated


def confirmed_baseline_rows(record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    validate_annotation_record(record)
    if record["state"] != "user_confirmed":
        raise AnnotationError("only confirmed annotations create baseline rows")
    confirmation = record["confirmation"]
    role_by_task = {
        item["task_id"]: item
        for item in evaluation_role_summary(record)["tasks"]
    }
    rows: list[dict[str, Any]] = []
    for task in record["tasks"]:
        polygons_raw = frame_polygons_raw(record, task)
        reference_slots = [
            slot
            for slot in task["slots"]
            if slot_boundary_ids(slot) is not None
        ]
        rows.append(
            {
                "baseline_schema": BASELINE_SCHEMA,
                "sample_id": task["sample_id"],
                "status": "user_confirmed",
                "authority": "explicit_user_confirmation_in_local_source_annotator",
                "confirmation_scope": (
                    "shared_edges_applicable_task_boundaries_native_pixel_checks_and_"
                    "minimum_acceptable_no_bleed_crop_baseline"
                ),
                "accuracy_scope": "slots_with_boundary_pair_reference_geometry",
                "confirmed_at_utc": confirmation["confirmed_at_utc"],
                "proposal_snapshot_sha256": confirmation[
                    "proposal_snapshot_sha256"
                ],
                "source_relative_path": task["source_relative_path"],
                "source_sha256": record["source"]["sha256"],
                "format_id": record["format_id"],
                "count": task["count"],
                "coordinate_system": {
                    "origin": "top_left",
                    "x_direction": "right",
                    "y_direction": "down",
                    "continuous_coordinates": COORDINATE_SYSTEM,
                    "canonical_extent": deepcopy(
                        record["source"]["canonical_extent"]
                    ),
                    "orientation_mapping": deepcopy(
                        record["source"]["orientation_mapping"]
                    ),
                },
                "strip_orientation": record["strip_axis_display"],
                "shared_edges": deepcopy(record["shared_edges"]),
                "boundary_pool": deepcopy(record["boundary_pool"]),
                "slots": deepcopy(task["slots"]),
                "adjacencies": deepcopy(task["adjacencies"]),
                "evaluation_role": {
                    "contract": EVALUATION_ROLE_CONTRACT,
                    "cohort_role": role_by_task[task["task_id"]]["cohort_role"],
                    "reasons": deepcopy(role_by_task[task["task_id"]]["reasons"]),
                },
                "frames": [
                    {
                        "frame_index": slot["ordinal"],
                        "polygon_source_pixel_center_coordinates": polygon,
                        "confirmed_integer_boundary_polygon": [
                            [round(point[0]), round(point[1])]
                            for point in polygon
                        ],
                    }
                    for slot, polygon in zip(
                        reference_slots,
                        polygons_raw,
                        strict=True,
                    )
                ],
                "confirmed_review_artifact": confirmation[
                    "review_artifact_relative_path"
                ],
                "confirmed_review_artifact_sha256": confirmation[
                    "review_artifact_sha256"
                ],
            }
        )
    return tuple(rows)


def confirmed_rows_jsonl(records: Iterable[dict[str, Any]]) -> str:
    rows = [row for record in records for row in confirmed_baseline_rows(record)]
    rows.sort(key=lambda row: row["sample_id"])
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )
