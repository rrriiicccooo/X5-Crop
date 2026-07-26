"""Compare current production geometry with user-confirmed source polygons."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from x5crop.report.validation import validate_current_report_record


COMPARISON_SCHEMA = "x5crop_golden_baseline_directional_comparison_v1"
CONFIRMED_BASELINE_SCHEMA = "x5crop_user_confirmed_golden_baseline_v1"
CONFIRMED_GEOMETRY_AUTHORITY = "confirmed_integer_boundary_polygon"
PRODUCTION_GEOMETRY_SOURCE = (
    "output.finalization_plan.base_geometry.frame_crop_envelopes"
)
EDGE_ROLES = ("top", "right", "bottom", "left")
NUMERIC_ZERO_EPSILON = 1e-9

Point = tuple[float, float]
Polygon = tuple[Point, Point, Point, Point]


def _point(value: Any, label: str) -> Point:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or isinstance(value[0], bool)
        or isinstance(value[1], bool)
    ):
        raise ValueError(f"{label} must be an x/y coordinate")
    point = (float(value[0]), float(value[1]))
    if not all(math.isfinite(item) for item in point):
        raise ValueError(f"{label} must be finite")
    return point


def _signed_area(polygon: Sequence[Point]) -> float:
    return 0.5 * sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )


def _polygon(value: Any, label: str) -> Polygon:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{label} must contain four points")
    points = tuple(
        _point(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if _signed_area(points) <= NUMERIC_ZERO_EPSILON:
        raise ValueError(
            f"{label} must be a positive clockwise polygon in source raster coordinates"
        )
    return points  # type: ignore[return-value]


def _json_polygon(polygon: Sequence[Point]) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in polygon]


def _inverse_affine_point(
    x: float,
    y: float,
    matrix: Sequence[Sequence[float]],
) -> Point:
    if (
        len(matrix) != 3
        or any(len(row) != 3 for row in matrix)
        or tuple(float(item) for item in matrix[2]) != (0.0, 0.0, 1.0)
    ):
        raise ValueError("coordinate transform matrix must be affine 3x3")
    values = tuple(float(item) for row in matrix for item in row)
    if not all(math.isfinite(item) for item in values):
        raise ValueError("coordinate transform matrix must be finite")
    a, b, c = (float(item) for item in matrix[0])
    d, e, f = (float(item) for item in matrix[1])
    determinant = a * e - b * d
    if abs(determinant) <= NUMERIC_ZERO_EPSILON:
        raise ValueError("coordinate transform matrix must be invertible")
    output_x = float(x) - c
    output_y = float(y) - f
    return (
        (e * output_x - b * output_y) / determinant,
        (-d * output_x + a * output_y) / determinant,
    )


def map_output_box_to_source_polygon(
    box: dict[str, Any],
    coordinate_transform: dict[str, Any],
) -> list[list[float]]:
    expected = {"left", "top", "right", "bottom"}
    if not isinstance(box, dict) or set(box) != expected:
        raise ValueError("production output box is incomplete")
    left = float(box["left"])
    top = float(box["top"])
    right = float(box["right"])
    bottom = float(box["bottom"])
    if not all(math.isfinite(item) for item in (left, top, right, bottom)):
        raise ValueError("production output box must be finite")
    if right <= left or bottom <= top:
        raise ValueError("production output box must have positive extent")
    matrix = coordinate_transform.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("report coordinate transform is missing its matrix")
    polygon = tuple(
        _inverse_affine_point(x, y, matrix)
        for x, y in (
            (left, top),
            (right, top),
            (right, bottom),
            (left, bottom),
        )
    )
    _polygon(polygon, "mapped production polygon")
    return _json_polygon(polygon)


def _edge_measurement(
    confirmed_start: Point,
    confirmed_end: Point,
    production_start: Point,
    production_end: Point,
    *,
    edge_index: int,
    role: str,
) -> dict[str, Any]:
    confirmed_dx = confirmed_end[0] - confirmed_start[0]
    confirmed_dy = confirmed_end[1] - confirmed_start[1]
    production_dx = production_end[0] - production_start[0]
    production_dy = production_end[1] - production_start[1]
    confirmed_length = math.hypot(confirmed_dx, confirmed_dy)
    production_length = math.hypot(production_dx, production_dy)
    if min(confirmed_length, production_length) <= NUMERIC_ZERO_EPSILON:
        raise ValueError("polygon edges must have positive length")

    outward_x = confirmed_dy / confirmed_length
    outward_y = -confirmed_dx / confirmed_length
    distances = (
        (production_start[0] - confirmed_start[0]) * outward_x
        + (production_start[1] - confirmed_start[1]) * outward_y,
        (production_end[0] - confirmed_end[0]) * outward_x
        + (production_end[1] - confirmed_end[1]) * outward_y,
    )
    minimum_distance = min(distances)
    maximum_distance = max(distances)
    dot = (
        confirmed_dx * production_dx + confirmed_dy * production_dy
    )
    cross = (
        confirmed_dx * production_dy - confirmed_dy * production_dx
    )
    angle_difference = math.degrees(math.atan2(cross, dot))
    return {
        "edge_index": int(edge_index),
        "role": str(role),
        "signed_normal_distance_px": 0.5 * sum(distances),
        "signed_normal_distance_min_px": minimum_distance,
        "signed_normal_distance_max_px": maximum_distance,
        "angle_difference_degrees": angle_difference,
        "unsafe_outward_crossing_px": max(0.0, maximum_distance),
        "inward_content_loss_px": max(0.0, -minimum_distance),
    }


def _contains_polygon(
    container: Polygon,
    candidate: Polygon,
) -> bool:
    for index, start in enumerate(container):
        end = container[(index + 1) % len(container)]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        outward_x = dy / length
        outward_y = -dx / length
        if any(
            (point[0] - start[0]) * outward_x
            + (point[1] - start[1]) * outward_y
            > NUMERIC_ZERO_EPSILON
            for point in candidate
        ):
            return False
    return True


def compare_confirmed_polygon(
    confirmed_polygon: Sequence[Sequence[float]],
    production_polygon: Sequence[Sequence[float]],
) -> dict[str, Any]:
    confirmed = _polygon(confirmed_polygon, "confirmed polygon")
    production = _polygon(production_polygon, "production polygon")
    edges = [
        _edge_measurement(
            confirmed[index],
            confirmed[(index + 1) % 4],
            production[index],
            production[(index + 1) % 4],
            edge_index=index + 1,
            role=EDGE_ROLES[index],
        )
        for index in range(4)
    ]
    confirmed_contains_production = _contains_polygon(
        confirmed,
        production,
    )
    production_contains_confirmed = _contains_polygon(
        production,
        confirmed,
    )
    if confirmed_contains_production and production_contains_confirmed:
        relationship = "mutual"
    elif confirmed_contains_production:
        relationship = "confirmed_contains_production"
    elif production_contains_confirmed:
        relationship = "production_contains_confirmed"
    else:
        relationship = "crossing_or_disjoint"
    return {
        "confirmed_polygon": _json_polygon(confirmed),
        "production_polygon_source_coordinates": _json_polygon(production),
        "confirmed_contains_production": confirmed_contains_production,
        "production_contains_confirmed": production_contains_confirmed,
        "containment_relationship": relationship,
        "edges": edges,
        "unsafe_outward_crossing_max_px": max(
            edge["unsafe_outward_crossing_px"] for edge in edges
        ),
        "inward_content_loss_max_px": max(
            edge["inward_content_loss_px"] for edge in edges
        ),
        "angle_difference_abs_max_deg": max(
            abs(edge["angle_difference_degrees"]) for edge in edges
        ),
    }


def _validate_baseline_record(record: dict[str, Any]) -> None:
    sample_id = str(record.get("sample_id", "<missing>"))
    if record.get("baseline_schema") != CONFIRMED_BASELINE_SCHEMA:
        raise ValueError(f"{sample_id}: unsupported confirmed baseline schema")
    if record.get("status") != "user_confirmed":
        raise ValueError(f"{sample_id}: baseline is not user-confirmed")
    if record.get("authority") != (
        "explicit_user_confirmation_of_current_fitted_review_jpg"
    ):
        raise ValueError(f"{sample_id}: baseline authority is not explicit confirmation")
    frames = record.get("frames")
    frame_count = record.get("frame_count")
    if (
        not isinstance(frame_count, int)
        or frame_count <= 0
        or not isinstance(frames, list)
        or len(frames) != frame_count
    ):
        raise ValueError(f"{sample_id}: confirmed frame count is incomplete")
    expected_indices = list(range(1, frame_count + 1))
    if [frame.get("frame_index") for frame in frames] != expected_indices:
        raise ValueError(f"{sample_id}: confirmed frame indexes are not canonical")
    for frame in frames:
        _polygon(
            frame.get(CONFIRMED_GEOMETRY_AUTHORITY),
            f"{sample_id} frame {frame['frame_index']} confirmed polygon",
        )


def _selected_count(report: dict[str, Any]) -> int:
    selection = report["selection"]
    rank = int(selection["selected_rank"])
    candidates = selection["candidates"]
    if rank < 1 or rank > len(candidates):
        raise ValueError("current report selected rank is out of range")
    count = candidates[rank - 1]["provisional_geometry"]["count"]
    if not isinstance(count, int) or count <= 0:
        raise ValueError("current report selected count is invalid")
    return count


def _production_detail(report: dict[str, Any]) -> dict[str, Any]:
    identity = report["analysis_identity"]
    geometry_resolution = report["selection"]["geometry_resolution"]
    transform = report["input"]["transform_geometry"]
    final_geometry = report["output"]["final_geometry"]
    return {
        "report_source": str(report["source"]),
        "script_version": str(report["script_version"]),
        "implementation_fingerprint": str(
            identity["implementation_fingerprint"]
        ),
        "runtime_configuration": dict(identity["runtime_configuration"]),
        "decision_status": str(report["decision"]["status"]),
        "final_review_reasons": list(
            report["decision"]["final_review_reasons"]
        ),
        "selected_rank": int(report["selection"]["selected_rank"]),
        "selected_count": _selected_count(report),
        "geometry_resolution_state": str(geometry_resolution["state"]),
        "geometry_resolution_reasons": list(
            geometry_resolution["reasons"]
        ),
        "transform_outcome": str(transform["outcome"]),
        "estimated_angle_degrees": transform["estimated_angle_degrees"],
        "final_boxes": (
            None
            if final_geometry is None
            else [
                dict(box)
                for box in final_geometry["final_boxes"]
            ]
        ),
    }


def _aggregate_frames(frames: Sequence[dict[str, Any]]) -> dict[str, Any]:
    edges = [
        edge
        for frame in frames
        for edge in frame["edges"]
    ]
    relationships: dict[str, int] = {}
    for frame in frames:
        relationship = str(frame["containment_relationship"])
        relationships[relationship] = relationships.get(relationship, 0) + 1
    return {
        "frame_count": len(frames),
        "edge_count": len(edges),
        "signed_normal_distance_min_px": min(
            edge["signed_normal_distance_min_px"] for edge in edges
        ),
        "signed_normal_distance_max_px": max(
            edge["signed_normal_distance_max_px"] for edge in edges
        ),
        "unsafe_outward_crossing_max_px": max(
            edge["unsafe_outward_crossing_px"] for edge in edges
        ),
        "inward_content_loss_max_px": max(
            edge["inward_content_loss_px"] for edge in edges
        ),
        "angle_difference_abs_max_deg": max(
            abs(edge["angle_difference_degrees"]) for edge in edges
        ),
        "containment_relationship_counts": relationships,
    }


def compare_baseline_record_to_report(
    baseline: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    _validate_baseline_record(baseline)
    validate_current_report_record(report)
    sample_id = str(baseline["sample_id"])
    source_identity = report["analysis_identity"]["source"]
    if str(source_identity["content_sha256"]) != str(baseline["source_sha256"]):
        raise ValueError(f"{sample_id}: source SHA-256 mismatch")
    if str(source_identity["name"]) != Path(
        str(baseline["source_relative_path"])
    ).name:
        raise ValueError(f"{sample_id}: source filename mismatch")
    transform = report["input"]["transform_geometry"]["coordinate_transform"]
    source_extent = transform["source_extent"]
    if (
        int(source_extent["width"]) != int(baseline["raw_width_px"])
        or int(source_extent["height"]) != int(baseline["raw_height_px"])
    ):
        raise ValueError(f"{sample_id}: source raster extent mismatch")
    if int(source_identity["page"]) != 0:
        raise ValueError(f"{sample_id}: confirmed baseline only supports TIFF page 0")

    production = _production_detail(report)
    confirmed_count = int(baseline["frame_count"])
    selected_count = int(production["selected_count"])
    result: dict[str, Any] = {
        "comparison_schema": COMPARISON_SCHEMA,
        "sample_id": sample_id,
        "source_relative_path": str(baseline["source_relative_path"]),
        "source_sha256": str(baseline["source_sha256"]),
        "confirmed_geometry_authority": CONFIRMED_GEOMETRY_AUTHORITY,
        "production_geometry_source": None,
        "comparison_state": "production_geometry_unavailable",
        "production": production,
        "frame_count": {
            "confirmed": confirmed_count,
            "selected": selected_count,
            "output": None,
            "match": selected_count == confirmed_count,
        },
        "frames": [],
        "aggregate": None,
    }
    finalization_plan = report["output"]["finalization_plan"]
    if finalization_plan is None:
        return result

    envelopes = finalization_plan["base_geometry"]["frame_crop_envelopes"]
    output_count = len(envelopes)
    result["production_geometry_source"] = PRODUCTION_GEOMETRY_SOURCE
    result["frame_count"]["output"] = output_count
    result["frame_count"]["match"] = bool(
        selected_count == confirmed_count == output_count
    )
    if not result["frame_count"]["match"]:
        raise ValueError(
            f"{sample_id}: production frame count does not match the confirmed baseline"
        )

    expected_indices = list(range(1, confirmed_count + 1))
    if [envelope["frame_index"] for envelope in envelopes] != expected_indices:
        raise ValueError(f"{sample_id}: production frame indexes are not canonical")
    frames: list[dict[str, Any]] = []
    for confirmed_frame, envelope in zip(
        baseline["frames"],
        envelopes,
        strict=True,
    ):
        production_polygon = map_output_box_to_source_polygon(
            envelope["box"],
            transform,
        )
        comparison = compare_confirmed_polygon(
            confirmed_frame[CONFIRMED_GEOMETRY_AUTHORITY],
            production_polygon,
        )
        frames.append(
            {
                "frame_index": int(confirmed_frame["frame_index"]),
                **comparison,
            }
        )
    result["comparison_state"] = "compared"
    result["frames"] = frames
    result["aggregate"] = _aggregate_frames(frames)
    return result


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSONL record"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(row)
    return rows


def audit_baseline_rows(
    baseline_rows: Iterable[dict[str, Any]],
    report_rows: Iterable[dict[str, Any]],
    *,
    sample_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    baselines = list(baseline_rows)
    baseline_by_id: dict[str, dict[str, Any]] = {}
    for baseline in baselines:
        _validate_baseline_record(baseline)
        sample_id = str(baseline["sample_id"])
        if sample_id in baseline_by_id:
            raise ValueError(f"duplicate confirmed baseline sample: {sample_id}")
        baseline_by_id[sample_id] = baseline

    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("requested sample IDs must be unique")
    unknown = [sample_id for sample_id in sample_ids if sample_id not in baseline_by_id]
    if unknown:
        raise ValueError(f"unknown confirmed baseline samples: {', '.join(unknown)}")
    selected = (
        [baseline_by_id[sample_id] for sample_id in sample_ids]
        if sample_ids
        else baselines
    )

    report_by_sha: dict[str, dict[str, Any]] = {}
    for report in report_rows:
        validate_current_report_record(report)
        source_sha256 = str(
            report["analysis_identity"]["source"]["content_sha256"]
        )
        if source_sha256 in report_by_sha:
            raise ValueError(
                f"duplicate production report source SHA-256: {source_sha256}"
            )
        report_by_sha[source_sha256] = report

    comparisons: list[dict[str, Any]] = []
    for baseline in selected:
        source_sha256 = str(baseline["source_sha256"])
        report = report_by_sha.get(source_sha256)
        if report is None:
            raise ValueError(
                f"{baseline['sample_id']}: production report is missing"
            )
        comparisons.append(
            compare_baseline_record_to_report(baseline, report)
        )
    return comparisons


def _print_summary(comparisons: Sequence[dict[str, Any]]) -> None:
    state_counts: dict[str, int] = {}
    for comparison in comparisons:
        state = str(comparison["comparison_state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    print(f"samples: {len(comparisons)}")
    print(
        "states: "
        + ", ".join(
            f"{state}={count}"
            for state, count in sorted(state_counts.items())
        )
    )
    for comparison in comparisons:
        production = comparison["production"]
        count = comparison["frame_count"]
        detail = (
            f"{comparison['sample_id']}: {comparison['comparison_state']}; "
            f"decision={production['decision_status']}; "
            f"count={count['selected']}/{count['confirmed']}; "
            f"geometry={production['geometry_resolution_state']}"
        )
        aggregate = comparison["aggregate"]
        if aggregate is not None:
            detail += (
                f"; outward_max={aggregate['unsafe_outward_crossing_max_px']:.3f}px"
                f"; inward_max={aggregate['inward_content_loss_max_px']:.3f}px"
                f"; angle_max={aggregate['angle_difference_abs_max_deg']:.4f}deg"
            )
        else:
            reasons = production["final_review_reasons"]
            if reasons:
                detail += f"; reasons={','.join(reasons)}"
        print(detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare current X5 Crop report geometry with user-confirmed "
            "source-coordinate polygons."
        )
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="One or more current-schema JSONL reports.",
    )
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        help="Confirmed sample ID to include. Repeat to define an exact subset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write comparison JSONL to this path.",
    )
    arguments = parser.parse_args(argv)
    report_rows = [
        row
        for report_path in arguments.reports
        for row in load_jsonl(report_path)
    ]
    comparisons = audit_baseline_rows(
        load_jsonl(arguments.baseline),
        report_rows,
        sample_ids=tuple(arguments.sample),
    )
    _print_summary(comparisons)
    if arguments.output is not None:
        with arguments.output.open("w", encoding="utf-8") as handle:
            for comparison in comparisons:
                handle.write(
                    json.dumps(
                        comparison,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                handle.write("\n")
        print(f"comparison_jsonl: {arguments.output}")
    else:
        for comparison in comparisons:
            print(
                json.dumps(
                    comparison,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
