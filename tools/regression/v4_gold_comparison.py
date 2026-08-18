"""Compare v4.2.8 and V5 geometry with the independent golden aperture.

This is a development experiment, not a verifier and not a source of runtime
authority.  Historical output is always reported as behavior; only the
user-confirmed golden geometry is treated as reference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .accuracy import GOLD_COHORT_PATH, PROJECT_ROOT
from .cohort_count import validate_cohort_counts
from .file_identity import sha256_file


COMPARISON_SCHEMA = "x5crop_v4_v5_gold_comparison_v1"


def _load_json(path: Path) -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError(f"expected one JSON object: {path}")
    return rows[0]


def _interval(minimum: float, maximum: float) -> dict[str, float]:
    if minimum > maximum:
        raise ValueError("interval is reversed")
    return {"minimum": float(minimum), "maximum": float(maximum)}


def _box_axes(
    box: Mapping[str, object], orientation: str
) -> tuple[dict[str, float], dict[str, float]]:
    if orientation == "horizontal":
        sequence = _interval(float(box["left"]), float(box["right"]))
        cross = _interval(float(box["top"]), float(box["bottom"]))
    elif orientation == "vertical":
        sequence = _interval(float(box["top"]), float(box["bottom"]))
        cross = _interval(float(box["left"]), float(box["right"]))
    else:
        raise ValueError(f"unsupported strip orientation: {orientation}")
    return sequence, cross


def _point_axes(
    point: Sequence[object], orientation: str
) -> tuple[float, float]:
    if len(point) != 2:
        raise ValueError("gold polygon point must contain x and y")
    x, y = float(point[0]), float(point[1])
    return (x, y) if orientation == "horizontal" else (y, x)


def _gold_aperture(
    geometry: Mapping[str, object], orientation: str
) -> dict[str, dict[str, float]]:
    frames = geometry.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("confirmed geometry has no frames")
    sequence_values: list[float] = []
    cross_values: list[float] = []
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("confirmed frame is invalid")
        polygon = frame.get("polygon_source_pixel_center_coordinates")
        if not isinstance(polygon, list) or len(polygon) < 4:
            raise ValueError("confirmed frame polygon is invalid")
        for point in polygon:
            sequence, cross = _point_axes(point, orientation)
            sequence_values.append(sequence)
            cross_values.append(cross)
    return {
        "sequence": _interval(min(sequence_values), max(sequence_values)),
        "cross": _interval(min(cross_values), max(cross_values)),
    }


def _union_boxes(
    boxes: Iterable[Mapping[str, object]], orientation: str
) -> dict[str, dict[str, float]] | None:
    axes = [_box_axes(box, orientation) for box in boxes]
    if not axes:
        return None
    return {
        "sequence": _interval(
            min(item[0]["minimum"] for item in axes),
            max(item[0]["maximum"] for item in axes),
        ),
        "cross": _interval(
            min(item[1]["minimum"] for item in axes),
            max(item[1]["maximum"] for item in axes),
        ),
    }


def _union_polygons(
    polygons: Iterable[Sequence[Sequence[object]]], orientation: str
) -> dict[str, dict[str, float]] | None:
    sequence_values: list[float] = []
    cross_values: list[float] = []
    for polygon in polygons:
        for point in polygon:
            sequence, cross = _point_axes(point, orientation)
            sequence_values.append(sequence)
            cross_values.append(cross)
    if not sequence_values:
        return None
    return {
        "sequence": _interval(min(sequence_values), max(sequence_values)),
        "cross": _interval(min(cross_values), max(cross_values)),
    }


def _deviation(
    candidate: Mapping[str, object] | None,
    reference: Mapping[str, object],
    px_per_mm: float,
) -> dict[str, object] | None:
    if candidate is None:
        return None
    result: dict[str, object] = {}
    for axis in ("sequence", "cross"):
        observed = candidate[axis]
        expected = reference[axis]
        if not isinstance(observed, Mapping) or not isinstance(expected, Mapping):
            raise ValueError("axis interval is invalid")
        lower = float(observed["minimum"]) - float(expected["minimum"])
        upper = float(observed["maximum"]) - float(expected["maximum"])
        result[axis] = {
            "lower_delta_px": lower,
            "upper_delta_px": upper,
            "lower_delta_mm": lower / px_per_mm,
            "upper_delta_mm": upper / px_per_mm,
        }
    return result


def _v5_scale(report: Mapping[str, object], orientation: str) -> float:
    geometry = report["photo_geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("V5 photo geometry is invalid")
    holder = geometry["matched_holder"]
    scales = holder["axis_scales"]
    key = (
        "width_axis_px_per_mm"
        if orientation == "horizontal"
        else "height_axis_px_per_mm"
    )
    interval = scales[key]
    value = (float(interval["minimum"]) + float(interval["maximum"])) / 2.0
    if value <= 0.0:
        raise ValueError("V5 pixel scale is invalid")
    return value


def _v5_coarse(report: Mapping[str, object]) -> dict[str, dict[str, float]] | None:
    lanes = report["photo_geometry"]["lanes"]
    supports = [lane.get("coarse_strip_support") for lane in lanes]
    supports = [item for item in supports if isinstance(item, Mapping)]
    if not supports:
        return None
    return {
        "sequence": _interval(
            min(float(item["long_interval_px"]["minimum"]) for item in supports),
            max(float(item["long_interval_px"]["maximum"]) for item in supports),
        ),
        "cross": _interval(
            min(float(item["short_interval_px"]["minimum"]) for item in supports),
            max(float(item["short_interval_px"]["maximum"]) for item in supports),
        ),
    }


def _v5_photo_group_outer(
    report: Mapping[str, object],
) -> dict[str, dict[str, float]] | None:
    outers = [
        lane.get("photo_group_outer")
        for lane in report["photo_geometry"]["lanes"]
    ]
    outers = [item for item in outers if isinstance(item, Mapping)]
    if not outers:
        return None
    # PhotoGroupOuter owns only the sequence axis.  Cross remains deliberately
    # absent instead of being inferred from another object.
    return {
        "sequence": _interval(
            min(float(item["lower_px"]["minimum"]) for item in outers),
            max(float(item["upper_px"]["maximum"]) for item in outers),
        )
    }


def _v5_output_footprint(
    report: Mapping[str, object], orientation: str
) -> dict[str, dict[str, float]] | None:
    polygons = []
    for lane in report["photo_geometry"]["lanes"]:
        for footprint in lane.get("output_footprints", ()):
            polygon = footprint.get("required_source_footprint")
            if isinstance(polygon, list):
                polygons.append(polygon)
    return _union_polygons(polygons, orientation)


def _v5_observation_summary(report: Mapping[str, object]) -> dict[str, object]:
    development = report.get("development")
    if not isinstance(development, Mapping):
        return {"available": False}
    sequence: list[Mapping[str, object]] = []
    cross: list[Mapping[str, object]] = []
    for lane in development.get("lanes", ()):
        observations = lane.get("observations", {})
        sequence.extend(observations.get("sequence_edges", ()))
        cross.extend(observations.get("registered_top_bottom_bindings", ()))
    qualified_sequence = [
        item for item in sequence if item.get("qualified_anchor_roles")
    ]
    role_authorized_cross = [
        item for item in cross if item.get("role_authorized") is True
    ]
    return {
        "available": True,
        "sequence_edge_count": len(sequence),
        "qualified_sequence_edge_count": len(qualified_sequence),
        "cross_binding_count": len(cross),
        "role_authorized_cross_binding_count": len(role_authorized_cross),
        "sequence_observation_ids": [
            str(item["observation_id"]) for item in qualified_sequence
        ],
        "cross_observation_ids": [
            str(item["observation_id"]) for item in role_authorized_cross
        ],
    }


def _v5_selected_cross(report: Mapping[str, object]) -> list[dict[str, object]]:
    development = report.get("development")
    if not isinstance(development, Mapping):
        return []
    selected: list[dict[str, object]] = []
    for lane in development.get("lanes", ()):
        best = lane.get("cross_competition", {}).get("best")
        if not isinstance(best, Mapping):
            continue
        selected.append(
            {
                "lane_id": lane["lane_id"],
                "boundary_use": best.get("boundary_use"),
                "top_canonical_px": best.get("top_canonical_px"),
                "bottom_canonical_px": best.get("bottom_canonical_px"),
                "direct_observation_ids": [
                    item["observation_id"]
                    for item in best.get("direct_bindings", ())
                ],
            }
        )
    return selected


def _v5_protection(report: Mapping[str, object]) -> dict[str, object]:
    values: dict[str, list[tuple[float, float]]] = {
        role: [] for role in ("start", "end", "top", "bottom")
    }
    for lane in report["photo_geometry"]["lanes"]:
        for footprint in lane.get("output_footprints", ()):
            for protection in footprint.get("boundary_protections", ()):
                role = str(protection.get("role"))
                if role in values:
                    values[role].append(
                        (
                            float(protection["bleed_px"]),
                            float(protection["joint_expansion_px"]),
                        )
                    )
    return {
        role: {
            "maximum_bleed_px": max(item[0] for item in items),
            "maximum_joint_expansion_px": max(item[1] for item in items),
        }
        for role, items in values.items()
        if items
    }


def build_comparison_record(
    cohort: Mapping[str, object],
    v4_report: Mapping[str, object],
    v5_report: Mapping[str, object],
) -> dict[str, object]:
    sample_id = str(cohort["sample_id"])
    geometry = cohort["confirmed_geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("gold geometry is invalid")
    source_sha = str(cohort["source_sha256"])
    v5_source = v5_report["runtime_identity"]["source"]
    expected_name = Path(str(cohort["source_relative_path"])).name
    expected_shape = [
        int(geometry["raw_height_px"]),
        int(geometry["raw_width_px"]),
    ]
    reported_shape = list(v5_source.get("shape", ()))
    if (
        str(v5_source.get("name")) != expected_name
        or reported_shape[:2] != expected_shape
    ):
        raise ValueError(f"{sample_id}: V5 source identity does not match gold")
    if Path(str(v4_report.get("source", ""))).name != expected_name:
        raise ValueError(f"{sample_id}: v4 source identity does not match gold")

    orientation = str(geometry["strip_orientation"])
    gold = _gold_aperture(geometry, orientation)
    px_per_mm = _v5_scale(v5_report, orientation)
    v4_outer_box = v4_report.get("outer_box")
    v4_outer = None
    if isinstance(v4_outer_box, Mapping):
        sequence, cross = _box_axes(v4_outer_box, orientation)
        v4_outer = {"sequence": sequence, "cross": cross}
    frame_boxes = [
        item
        for item in v4_report.get("frame_boxes", ())
        if isinstance(item, Mapping)
    ]
    v4_crop = _union_boxes(frame_boxes, orientation)
    v5_coarse = _v5_coarse(v5_report)
    v5_outer = _v5_photo_group_outer(v5_report)
    v5_footprint = _v5_output_footprint(v5_report, orientation)

    v4_outer_to_crop = None
    if v4_outer is not None and v4_crop is not None:
        v4_outer_to_crop = {
            axis: {
                "lower_delta_px": float(v4_crop[axis]["minimum"])
                - float(v4_outer[axis]["minimum"]),
                "upper_delta_px": float(v4_crop[axis]["maximum"])
                - float(v4_outer[axis]["maximum"]),
            }
            for axis in ("sequence", "cross")
        }

    detail = v4_report.get("detail")
    v4_output_bleed = None
    if isinstance(detail, Mapping):
        bleed = detail.get("output_bleed")
        if isinstance(bleed, Mapping):
            v4_output_bleed = {
                "used": bleed.get("used"),
                "long_axis_px": bleed.get("output_long_axis_bleed"),
                "short_axis_px": bleed.get("output_short_axis_bleed"),
                "overlap_risk_long_axis": bleed.get(
                    "overlap_risk_long_axis_bleed"
                ),
            }

    v5_status = str(v5_report["decision"]["status"])
    return {
        "schema": COMPARISON_SCHEMA,
        "sample_id": sample_id,
        "source_sha256": source_sha,
        "orientation": orientation,
        "authority": {
            "reference": "user_confirmed_golden_geometry",
            "v4": "historical_behavior_only",
            "v5": "current_behavior_only",
        },
        "status": {"v4": v4_report.get("status"), "v5": v5_status},
        "px_per_mm": px_per_mm,
        "human_confirmed_aperture": gold,
        "v4_detected_outer": v4_outer,
        "v4_final_crop_union": v4_crop,
        "v4_output_bleed_policy": v4_output_bleed,
        "v4_outer_to_final_crop_delta": v4_outer_to_crop,
        "v4_outer_crop_identity_note": (
            "raw_delta_only; detected outer and per-frame crop union may be "
            "different physical objects"
        ),
        "v5_coarse_strip_support": v5_coarse,
        "v5_outer_observations": _v5_observation_summary(v5_report),
        "v5_photo_group_outer": v5_outer,
        "v5_selected_cross": _v5_selected_cross(v5_report),
        "v5_output_footprint_union": v5_footprint,
        "v5_protection_ledger": _v5_protection(v5_report),
        "deviation_from_human": {
            "v4_detected_outer": _deviation(v4_outer, gold, px_per_mm),
            "v4_final_crop_union": _deviation(v4_crop, gold, px_per_mm),
            "v5_coarse_strip_support": _deviation(v5_coarse, gold, px_per_mm),
            "v5_output_footprint_union": _deviation(
                v5_footprint, gold, px_per_mm
            ),
        },
    }


def compare_gold_reports(
    *, cohort_path: Path, v4_root: Path, v5_root: Path
) -> tuple[dict[str, object], ...]:
    validate_cohort_counts((cohort_path,))
    records = [
        json.loads(line)
        for line in cohort_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output = []
    for cohort in records:
        sample_id = str(cohort["sample_id"])
        relative_source = Path(str(cohort["source_relative_path"]))
        source = (PROJECT_ROOT / relative_source).resolve()
        expected_sha256 = str(cohort["source_sha256"]).lower()
        if (
            relative_source.is_absolute()
            or not source.is_relative_to(PROJECT_ROOT.resolve())
            or not source.is_file()
            or len(expected_sha256) != 64
            or sha256_file(source) != expected_sha256
        ):
            raise ValueError(f"{sample_id}: golden source identity is invalid")
        v4_report = _load_json(v4_root / sample_id / "split_report.jsonl")
        v5_report = _load_json(v5_root / sample_id / "x5_crop_report.jsonl")
        output.append(build_comparison_record(cohort, v4_report, v5_report))
    return tuple(output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare v4.2.8 and V5 reports with user-confirmed gold."
    )
    parser.add_argument("--v4-root", type=Path, required=True)
    parser.add_argument("--v5-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, default=GOLD_COHORT_PATH)
    args = parser.parse_args(argv)
    records = compare_gold_reports(
        cohort_path=args.cohort,
        v4_root=args.v4_root,
        v5_root=args.v5_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    print(f"v4/V5 gold comparison: {len(records)} sample(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
