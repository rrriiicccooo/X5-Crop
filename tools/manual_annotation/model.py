"""Canonical schema and geometry for the local source annotator."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Sequence


ANNOTATION_SCHEMA = "x5crop_source_annotation_v1"
BASELINE_SCHEMA = "x5crop_user_confirmed_source_geometry_v2"
COORDINATE_SYSTEM = "raw_tiff_raster_pixel_centers"
MACHINE_ORIGIN = "independent_bounded_pixel_proposal_v1"
RED_MARKUP_ORIGIN = "user_red_markup_import_v1"
CONFIRMED_IMPORT_ORIGIN = "existing_user_confirmed_baseline_import_v1"
RECORD_STATES = frozenset(
    {"machine_proposal", "human_adjusted", "user_confirmed"}
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


def frame_polygons_display(
    record: dict[str, Any],
    task: dict[str, Any],
) -> tuple[list[list[float]], ...]:
    shared = record.get("shared_edges")
    boundary_pool = record.get("boundary_pool")
    boundary_ids = task.get("boundary_ids")
    count = task.get("count")
    if not isinstance(shared, list) or len(shared) != 2:
        raise AnnotationError("source annotation requires two shared edges")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or not isinstance(boundary_pool, list)
        or not isinstance(boundary_ids, list)
        or len(boundary_ids) != count * 2
    ):
        raise AnnotationError("task boundary count does not match explicit count")
    pool_by_id = {
        line.get("line_id"): line
        for line in boundary_pool
        if isinstance(line, dict)
    }
    if len(pool_by_id) != len(boundary_pool) or any(
        line_id not in pool_by_id for line_id in boundary_ids
    ):
        raise AnnotationError("task references an unknown physical boundary")
    boundaries = [pool_by_id[line_id] for line_id in boundary_ids]
    low = _line_points_display(record, shared[0])
    high = _line_points_display(record, shared[1])
    horizontal = record.get("strip_axis_display") == "horizontal"
    polygons: list[list[list[float]]] = []
    for index in range(count):
        start = _line_points_display(record, boundaries[index * 2])
        stop = _line_points_display(record, boundaries[index * 2 + 1])
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
    if set(line) != {"line_id", "role", "points_raw", "origin"}:
        raise AnnotationError("annotation line has unexpected fields")
    if not isinstance(line["line_id"], str) or not line["line_id"]:
        raise AnnotationError("annotation line requires an identity")
    if line["role"] != expected_role:
        raise AnnotationError(f"{line['line_id']} has an unexpected role")
    if not isinstance(line["origin"], str) or not line["origin"]:
        raise AnnotationError(f"{line['line_id']} requires provenance")
    _line_points_display(record, line)


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
    _validate_source(record)

    shared = record["shared_edges"]
    if not isinstance(shared, list) or len(shared) != 2:
        raise AnnotationError("annotation requires exactly two shared edges")
    _validate_line(record, shared[0], expected_role="short_low")
    _validate_line(record, shared[1], expected_role="short_high")
    line_ids = {shared[0]["line_id"], shared[1]["line_id"]}

    boundary_pool = record["boundary_pool"]
    if not isinstance(boundary_pool, list) or not boundary_pool:
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
            "boundary_ids",
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
        boundary_ids = task["boundary_ids"]
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or not isinstance(boundary_ids, list)
            or len(boundary_ids) != count * 2
        ):
            raise AnnotationError("annotation task count is invalid")
        if len(set(boundary_ids)) != len(boundary_ids):
            raise AnnotationError(
                f"{task_id}: one task maps multiple roles to the same boundary"
            )
        if not set(boundary_ids).issubset(pool_ids):
            raise AnnotationError(f"{task_id}: task references an unknown boundary")
        polygons = frame_polygons_display(record, task)
        previous_center = -math.inf
        horizontal = record["strip_axis_display"] == "horizontal"
        for polygon in polygons:
            if _polygon_area(polygon) < 4.0:
                raise AnnotationError("annotation frame is degenerate or reversed")
            for x, y in polygon:
                if (
                    not -0.5 <= x <= width - 0.5
                    or not -0.5 <= y <= height - 0.5
                ):
                    raise AnnotationError("annotation frame leaves the source raster")
            center = sum(point[0 if horizontal else 1] for point in polygon) / 4.0
            if center <= previous_center:
                raise AnnotationError("annotation frames are not in display order")
            previous_center = center

    reviewed = record["reviewed_task_ids"]
    if (
        not isinstance(reviewed, list)
        or len(set(reviewed)) != len(reviewed)
        or not set(reviewed).issubset(task_ids)
    ):
        raise AnnotationError("reviewed task identities are invalid")
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
    for task in result["tasks"]:
        task["frame_polygons_display"] = list(
            frame_polygons_display(record, task)
        )
    return result


def apply_client_geometry(
    current: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    if set(payload) != {"expected_revision", "shared_edges", "boundary_pool"}:
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
                or set(item) != {"line_id", "points_display"}
                or not isinstance(item["line_id"], str)
            ):
                raise AnnotationError("geometry line update is malformed")
            incoming_by_id[item["line_id"]] = item
        if set(incoming_by_id) != {line["line_id"] for line in target}:
            raise AnnotationError("geometry line identities changed")
        for line in target:
            points = incoming_by_id[line["line_id"]]["points_display"]
            if not isinstance(points, list) or len(points) != 2:
                raise AnnotationError("geometry line requires two display points")
            mapped = [
                display_to_raw_point(updated, _point(point, "display point"))
                for point in points
            ]
            if any(
                math.dist(before, after) > 1.0e-7
                for before, after in zip(line["points_raw"], mapped, strict=True)
            ):
                line["origin"] = "human_adjustment"
            line["points_raw"] = mapped

    replace_lines(updated["shared_edges"], payload["shared_edges"])
    replace_lines(updated["boundary_pool"], payload["boundary_pool"])
    updated["revision"] += 1
    updated["state"] = "human_adjusted"
    updated["reviewed_task_ids"] = []
    updated["confirmation"] = None
    validate_annotation_record(updated)
    return updated


def confirmed_baseline_rows(record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    validate_annotation_record(record)
    if record["state"] != "user_confirmed":
        raise AnnotationError("only confirmed annotations create baseline rows")
    confirmation = record["confirmation"]
    rows: list[dict[str, Any]] = []
    for task in record["tasks"]:
        polygons_raw = frame_polygons_raw(record, task)
        rows.append(
            {
                "baseline_schema": BASELINE_SCHEMA,
                "sample_id": task["sample_id"],
                "status": "user_confirmed",
                "authority": "explicit_user_confirmation_in_local_source_annotator",
                "confirmation_scope": (
                    "shared_edges_all_task_boundaries_native_pixel_checks_and_"
                    "minimum_acceptable_no_bleed_crop_baseline"
                ),
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
                    "orientation_mapping": deepcopy(
                        record["source"]["orientation_mapping"]
                    ),
                },
                "strip_orientation": record["strip_axis_display"],
                "shared_edges": deepcopy(record["shared_edges"]),
                "boundary_pool": deepcopy(record["boundary_pool"]),
                "boundary_ids": deepcopy(task["boundary_ids"]),
                "frames": [
                    {
                        "frame_index": index,
                        "polygon_source_pixel_center_coordinates": polygon,
                        "confirmed_integer_boundary_polygon": [
                            [round(point[0]), round(point[1])]
                            for point in polygon
                        ],
                    }
                    for index, polygon in enumerate(polygons_raw, start=1)
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
