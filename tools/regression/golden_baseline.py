"""Compare current source-coordinate geometry with the tracked gold cohort."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Sequence

from x5crop.report.validation import validate_current_report_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_ACCURACY_PATH = (
    Path(__file__).with_name("cohorts") / "gold_accuracy.jsonl"
)
COMPARISON_SCHEMA = "x5crop_gold_geometry_comparison_v3"
GOLD_COHORT_SCHEMA = "x5crop_gold_accuracy_cohort_v1"
CONFIRMED_BASELINE_SCHEMA = "x5crop_user_confirmed_golden_baseline_v1"
GOLD_SAMPLE_COUNT = 9
GOLD_SCENARIO_COUNT = 14


def _jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _geometry_digest(geometry: dict[str, Any]) -> str:
    payload = {
        key: geometry[key]
        for key in (
            "source_sha256",
            "raw_width_px",
            "raw_height_px",
            "coordinate_system",
            "frame_count",
            "shared_edges",
            "frame_boundaries",
            "frames",
        )
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_gold_record(record: dict[str, Any]) -> None:
    geometry = record.get("confirmed_geometry")
    count_modes = record.get("count_modes")
    expectations = record.get("decision_expectations")
    if (
        record.get("cohort_schema") != GOLD_COHORT_SCHEMA
        or record.get("validation_role") != "gold_accuracy_blocking"
        or record.get("calibration_role")
        not in {"nominal", "stress_excluded"}
        or not isinstance(geometry, dict)
        or geometry.get("baseline_schema") != CONFIRMED_BASELINE_SCHEMA
        or geometry.get("status") != "user_confirmed"
        or geometry.get("source_sha256") != record.get("source_sha256")
        or geometry.get("sample_id") != record.get("sample_id")
        or geometry.get("frame_count")
        != record.get("confirmed_photo_count")
        or not isinstance(count_modes, list)
        or not count_modes
        or not isinstance(expectations, dict)
        or set(expectations) != set(count_modes)
        or any(
            value
            not in {
                "must_approve_safe",
                "must_review_with_competition",
            }
            for value in expectations.values()
        )
        or _geometry_digest(geometry) != record.get("geometry_digest")
        or len(str(record.get("legacy_record_sha256", ""))) != 64
    ):
        raise ValueError("tracked gold record is invalid")


def load_gold_records() -> tuple[dict[str, Any], ...]:
    records = _jsonl(GOLD_ACCURACY_PATH)
    if (
        len(records) != GOLD_SAMPLE_COUNT
        or sum(len(record.get("count_modes", ())) for record in records)
        != GOLD_SCENARIO_COUNT
    ):
        raise ValueError("tracked gold cohort cardinality changed")
    for record in records:
        validate_gold_record(record)
    if len({record["sample_id"] for record in records}) != len(records):
        raise ValueError("tracked gold sample IDs are not unique")
    if len({record["source_sha256"] for record in records}) != len(records):
        raise ValueError("tracked gold source identities are not unique")
    return records


def _inverse_map(
    matrix: Sequence[Sequence[float]],
    x: float,
    y: float,
) -> tuple[float, float]:
    a, b, tx = matrix[0]
    c, d, ty = matrix[1]
    determinant = a * d - b * c
    if abs(determinant) <= 1.0e-12:
        raise ValueError("report transform is not invertible")
    x -= tx
    y -= ty
    return (
        (d * x - b * y) / determinant,
        (-c * x + a * y) / determinant,
    )


def _contains(
    polygon: Sequence[tuple[float, float]],
    point: tuple[float, float],
) -> bool:
    signs = tuple(
        (right[0] - left[0]) * (point[1] - left[1])
        - (right[1] - left[1]) * (point[0] - left[0])
        for left, right in zip(
            polygon,
            (*polygon[1:], polygon[0]),
            strict=True,
        )
    )
    return all(value >= -1.0e-6 for value in signs) or all(
        value <= 1.0e-6 for value in signs
    )


def _box_polygon(box: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    return (
        (float(box["left"]), float(box["top"])),
        (float(box["right"]), float(box["top"])),
        (float(box["right"]), float(box["bottom"])),
        (float(box["left"]), float(box["bottom"])),
    )


def _ordered_containment(
    confirmed_frames: Sequence[dict[str, Any]],
    footprints: Sequence[Sequence[tuple[float, float]]],
) -> tuple[bool, tuple[int, ...], tuple[tuple[bool, ...], ...]]:
    matrix = tuple(
        tuple(
            all(
                _contains(
                    footprint,
                    (float(point[0]), float(point[1])),
                )
                for point in frame[
                    "polygon_source_pixel_center_coordinates"
                ]
            )
            for footprint in footprints
        )
        for frame in confirmed_frames
    )
    matches: list[int] = []
    following = 0
    for row in matrix:
        match = next(
            (
                index
                for index in range(following, len(row))
                if row[index]
            ),
            None,
        )
        if match is None:
            return False, (), matrix
        matches.append(match)
        following = match + 1
    return True, tuple(matches), matrix


def _selected_source_footprints(
    report: dict[str, Any],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    finalization = report["output"]["finalization"]
    transform = finalization["transform_assessment"]["transform"]
    if transform is None:
        return ()
    matrix = transform["matrix"]
    return tuple(
        tuple(
            _inverse_map(matrix, x, y)
            for x, y in _box_polygon(box)
        )
        for box in finalization["final_boxes"]
    )


def _candidate_source_footprints(
    candidate: dict[str, Any],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        _box_polygon(geometry["source_protected_box"])
        for geometry in candidate["output_geometries"]
    )


def _polygon_area(polygon: Sequence[tuple[float, float]]) -> float:
    return abs(
        sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(
                polygon,
                (*polygon[1:], polygon[0]),
                strict=True,
            )
        )
    ) / 2.0


def _approved_comparison(
    record: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    geometry = record["confirmed_geometry"]
    footprints = _selected_source_footprints(report)
    contained, matches, matrix = _ordered_containment(
        geometry["frames"],
        footprints,
    )
    confirmed_area = sum(
        _polygon_area(
            tuple(
                (float(point[0]), float(point[1]))
                for point in frame[
                    "polygon_source_pixel_center_coordinates"
                ]
            )
        )
        for frame in geometry["frames"]
    )
    matched_output_area = sum(
        _polygon_area(footprints[index]) for index in matches
    )
    finalization = report["output"]["finalization"]
    return {
        "comparison_schema": COMPARISON_SCHEMA,
        "sample_id": record["sample_id"],
        "comparison_mode": "final_selected_geometry",
        "decision_status": "approved_auto",
        "core_facts_sha256": report["core_facts_sha256"],
        "source_footprints": [
            [list(point) for point in footprint]
            for footprint in footprints
        ],
        "containment_matrix": [list(row) for row in matrix],
        "matched_output_ordinals": [index + 1 for index in matches],
        "zero_inward_loss": contained,
        "confirmed_area_px2": confirmed_area,
        "matched_output_area_px2": matched_output_area,
        "extra_area_px2": max(0.0, matched_output_area - confirmed_area),
        "extra_area_recalculation_inputs": finalization[
            "resolved_output_geometries"
        ],
        "official_tiff_expected": True,
        "official_tiff_count": finalization["official_tiff_count"],
        "passed": (
            contained
            and finalization["official_tiff_expected"] is True
            and finalization["official_tiff_count"]
            == finalization["output_slot_count"]
        ),
    }


def _review_comparison(
    record: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    geometry = record["confirmed_geometry"]
    all_candidates = tuple(
        candidate
        for lane in report["photo_geometry"]["lanes"]
        for candidate in lane["selection"]["undominated_candidate_set"]
    )
    candidate_results = []
    for candidate in all_candidates:
        footprints = _candidate_source_footprints(candidate)
        contained, matches, matrix = _ordered_containment(
            geometry["frames"],
            footprints,
        )
        candidate_results.append(
            {
                "candidate_id": candidate["candidate_id"],
                "hypothesis_id": candidate["hypothesis_id"],
                "output_equivalence_class_id": candidate[
                    "output_equivalence_class_id"
                ],
                "zero_inward_loss": contained,
                "matched_output_ordinals": [
                    index + 1 for index in matches
                ],
                "containment_matrix": [list(row) for row in matrix],
            }
        )
    competition = tuple(
        lane["selection"]["competition_assessment"]
        for lane in report["photo_geometry"]["lanes"]
    )
    competition_ids = {
        candidate_id
        for item in competition
        for candidate_id in item["candidate_ids"]
    }
    non_equivalent_pairs = tuple(
        pair
        for item in competition
        for pair in item["pairwise_output_differences"]
        if pair["first_non_equivalent_ordinal"] is not None
    )
    blocking_codes = {
        item["code"]
        for item in report["candidate_gate"]["checks"]
        if item["blocks"]
    }
    matching_ids = tuple(
        item["candidate_id"]
        for item in candidate_results
        if item["zero_inward_loss"]
    )
    matching_id_set = set(matching_ids)
    competing_ids = tuple(
        sorted(
            {
                candidate_id
                for pair in non_equivalent_pairs
                for candidate_id, other_id in (
                    (
                        pair["left_candidate_id"],
                        pair["right_candidate_id"],
                    ),
                    (
                        pair["right_candidate_id"],
                        pair["left_candidate_id"],
                    ),
                )
                if (
                    other_id in matching_id_set
                    and candidate_id in competition_ids
                    and candidate_id != other_id
                )
            }
        )
    )
    finalization = report["output"]["finalization"]
    passed = (
        bool(matching_ids)
        and bool(competing_ids)
        and bool(non_equivalent_pairs)
        and len(competition_ids) > 1
        and bool(blocking_codes)
        and bool(report["decision"]["final_review_reasons"])
        and finalization["official_tiff_expected"] is False
        and finalization["official_tiff_count"] == 0
        and not finalization["resolved_output_geometries"]
        and not report["output"]["output_files"]
    )
    return {
        "comparison_schema": COMPARISON_SCHEMA,
        "sample_id": record["sample_id"],
        "comparison_mode": "undominated_candidate_set",
        "decision_status": "needs_review",
        "core_facts_sha256": report["core_facts_sha256"],
        "candidate_results": candidate_results,
        "matching_candidate_ids": list(matching_ids),
        "competing_candidate_ids": list(competing_ids),
        "candidate_gate_blocking_codes": sorted(blocking_codes),
        "final_review_reasons": list(
            report["decision"]["final_review_reasons"]
        ),
        "non_equivalent_candidate_pairs": list(non_equivalent_pairs),
        "official_tiff_expected": False,
        "official_tiff_count": finalization["official_tiff_count"],
        "passed": passed,
    }


def compare_gold_record_to_report(
    record: dict[str, Any],
    report: dict[str, Any],
    *,
    count_mode: str,
) -> dict[str, Any]:
    validate_gold_record(record)
    validate_current_report_record(report)
    if count_mode not in record["count_modes"]:
        raise ValueError("count mode is not declared by the gold record")
    source_identity = report["analysis_identity"]["source"]
    if (
        str(record["source_sha256"]).lower()
        != str(source_identity["content_sha256"]).lower()
    ):
        raise ValueError("gold and report source SHA-256 disagree")
    expectation = record["decision_expectations"][count_mode]
    status = report["decision"]["status"]
    if expectation == "must_approve_safe":
        if status != "approved_auto":
            return {
                "comparison_schema": COMPARISON_SCHEMA,
                "sample_id": record["sample_id"],
                "comparison_mode": "final_selected_geometry",
                "decision_status": status,
                "passed": False,
                "failure": "must_approve_safe_status_mismatch",
            }
        return _approved_comparison(record, report)
    if status != "needs_review":
        return {
            "comparison_schema": COMPARISON_SCHEMA,
            "sample_id": record["sample_id"],
            "comparison_mode": "undominated_candidate_set",
            "decision_status": status,
            "passed": False,
            "failure": "must_review_with_competition_status_mismatch",
        }
    return _review_comparison(record, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare current reports with tracked gold geometry"
    )
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--count-mode",
        choices=("fixed_full", "explicit", "auto"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    records_by_sha = {
        str(record["source_sha256"]).lower(): record
        for record in load_gold_records()
    }
    results = []
    for report in _jsonl(args.report):
        digest = str(
            report["analysis_identity"]["source"]["content_sha256"]
        ).lower()
        record = records_by_sha.get(digest)
        if record is not None and args.count_mode in record["count_modes"]:
            results.append(
                compare_gold_record_to_report(
                    record,
                    report,
                    count_mode=args.count_mode,
                )
            )
    text = "".join(
        json.dumps(result, ensure_ascii=False) + "\n"
        for result in results
    )
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0 if results and all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
