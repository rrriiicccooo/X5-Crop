"""Run source-bound diagnostics against the current development gold."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any, Iterable, Sequence

import numpy as np

from .accuracy import (
    DEVELOPMENT_GOLD_COHORT_PATH,
    PROJECT_ROOT,
    validate_gold_source_identities,
    validate_gold_task_result,
)
from .file_identity import sha256_file
from .gold_geometry import (
    gold_frame_diagnostics,
    validate_selected_candidate_coverage,
)
from .report_validation import validate_current_report_record


ANALYSIS_RECORD_SCHEMA = "x5crop_development_gold_analysis_record_v3"
ANALYSIS_SUMMARY_SCHEMA = "x5crop_development_gold_analysis_summary_v3"
STAGE_INDEX_CONTRACT = "x5crop_gold_optimization_stage_index_v1"
STAGE_ONE_MAX_LATTICE_RESIDUAL_FRACTION = 0.02
SOURCE_TIMEOUT_SECONDS = 600
COMPARATOR_SOURCE_PATHS = (
    "tools/manual_annotation/model.py",
    "tools/regression/accuracy.py",
    "tools/regression/development_run.py",
    "tools/regression/gold_analysis.py",
    "tools/regression/gold_geometry.py",
    "tools/regression/report_validation.py",
)


def _canonical_point(
    geometry: dict[str, Any],
    point: Sequence[float],
) -> tuple[float, float]:
    matrix = geometry["coordinate_system"]["orientation_mapping"][
        "raw_to_canonical"
    ]
    x = float(point[0])
    y = float(point[1])
    transformed = (
        float(matrix[0][0]) * x
        + float(matrix[0][1]) * y
        + float(matrix[0][2]),
        float(matrix[1][0]) * x
        + float(matrix[1][1]) * y
        + float(matrix[1][2]),
        float(matrix[2][0]) * x
        + float(matrix[2][1]) * y
        + float(matrix[2][2]),
    )
    if abs(transformed[2]) < 1.0e-12:
        raise ValueError("gold orientation mapping has an invalid homogeneous scale")
    return (
        transformed[0] / transformed[2],
        transformed[1] / transformed[2],
    )


def line_axis_position(
    geometry: dict[str, Any],
    line: dict[str, Any],
    *,
    axis: str,
    reference_trace_px: float,
) -> float:
    """Evaluate one raw gold line on a canonical long/cross reference trace."""

    if axis not in {"sequence", "cross"}:
        raise ValueError("gold analysis axis is invalid")
    points = tuple(
        _canonical_point(geometry, point)
        for point in line["points_raw"]
    )
    horizontal = geometry["strip_orientation"] == "horizontal"
    sequence_axis = 0 if horizontal else 1
    cross_axis = 1 - sequence_axis
    dependent = sequence_axis if axis == "sequence" else cross_axis
    independent = cross_axis if axis == "sequence" else sequence_axis
    denominator = points[1][independent] - points[0][independent]
    if abs(denominator) < 1.0e-9:
        raise ValueError("gold line does not span its independent axis")
    fraction = (reference_trace_px - points[0][independent]) / denominator
    return points[0][dependent] + fraction * (
        points[1][dependent] - points[0][dependent]
    )


def _canonical_axis_extents(
    geometry: dict[str, Any],
) -> tuple[float, float]:
    extent = geometry["coordinate_system"]["canonical_extent"]
    horizontal = geometry["strip_orientation"] == "horizontal"
    long_extent = float(extent["width"] if horizontal else extent["height"])
    cross_extent = float(extent["height"] if horizontal else extent["width"])
    return long_extent, cross_extent


def _referenced_sequence_roles(
    geometry: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    lines = {line["line_id"]: line for line in geometry["boundary_pool"]}
    roles: list[dict[str, Any]] = []
    for slot in geometry["slots"]:
        reference = slot["reference_geometry"]
        if reference["kind"] != "boundary_pair":
            continue
        for role, key in (
            ("start", "start_boundary_id"),
            ("end", "end_boundary_id"),
        ):
            line_id = reference[key]
            roles.append(
                {
                    "ordinal": int(slot["ordinal"]),
                    "slot_kind": slot["slot_kind"],
                    "role": role,
                    "line_id": line_id,
                    "line": lines[line_id],
                }
            )
    return tuple(roles)


def gold_lattice_fit(geometry: dict[str, Any]) -> dict[str, Any] | None:
    """Fit the fixed phase/pitch/W model to gold geometry only."""

    _, cross_extent = _canonical_axis_extents(geometry)
    reference_trace = (cross_extent - 1.0) / 2.0
    rows: list[list[float]] = []
    values: list[float] = []
    widths: list[float] = []
    by_ordinal: dict[int, dict[str, float]] = defaultdict(dict)
    for role in _referenced_sequence_roles(geometry):
        ordinal = int(role["ordinal"])
        boundary_role = str(role["role"])
        position = line_axis_position(
            geometry,
            role["line"],
            axis="sequence",
            reference_trace_px=reference_trace,
        )
        rows.append(
            [
                1.0,
                float(ordinal - 1),
                1.0 if boundary_role == "end" else 0.0,
            ]
        )
        values.append(position)
        by_ordinal[ordinal][boundary_role] = position
    for pair in by_ordinal.values():
        if set(pair) == {"start", "end"}:
            widths.append(pair["end"] - pair["start"])
    if len(set(by_ordinal)) < 2 or not widths:
        return None
    matrix = np.asarray(rows, dtype=np.float64)
    target = np.asarray(values, dtype=np.float64)
    solution, _, rank, _ = np.linalg.lstsq(matrix, target, rcond=None)
    if int(rank) != 3:
        return None
    fitted = matrix @ solution
    residuals = target - fitted
    median_width = float(statistics.median(widths))
    if not math.isfinite(median_width) or median_width <= 0.0:
        return None
    return {
        "reference_trace_px": reference_trace,
        "phase_px": float(solution[0]),
        "pitch_px": float(solution[1]),
        "frame_width_px": float(solution[2]),
        "median_observed_frame_width_px": median_width,
        "maximum_absolute_role_residual_px": float(np.max(np.abs(residuals))),
        "rms_role_residual_px": float(np.sqrt(np.mean(residuals**2))),
        "maximum_absolute_role_residual_fraction_of_frame_width": (
            float(np.max(np.abs(residuals))) / median_width
        ),
    }


def optimization_stage_index(record: dict[str, Any]) -> dict[str, Any]:
    """Derive a validation-only stage; never feed it to production runtime."""

    geometry = record["confirmed_geometry"]
    lattice = gold_lattice_fit(geometry)
    if record["cohort_role"] == "challenge":
        return {
            "contract": STAGE_INDEX_CONTRACT,
            "stage": "stage3_challenge",
            "reasons": list(geometry["evaluation_role"]["reasons"]),
            "gold_lattice_fit": lattice,
        }

    roles = _referenced_sequence_roles(geometry)
    reasons: list[str] = []
    if int(record["count"]) < 3:
        reasons.append("fewer_than_three_slots")
    if any(item["slot_kind"] != "image" for item in geometry["slots"]):
        reasons.append("non_image_slot")
    if any(item["line"]["review_basis"] != "directly_visible" for item in roles):
        reasons.append("non_direct_sequence_reference")
    if any(
        edge["review_basis"] != "directly_visible"
        for edge in geometry["shared_edges"]
    ):
        reasons.append("non_direct_shared_edge")
    if any(item["kind"] != "separator" for item in geometry["adjacencies"]):
        reasons.append("non_separator_adjacency")
    if lattice is None:
        reasons.append("gold_lattice_not_identifiable")
    elif (
        lattice["maximum_absolute_role_residual_fraction_of_frame_width"]
        > STAGE_ONE_MAX_LATTICE_RESIDUAL_FRACTION
    ):
        reasons.append("gold_lattice_residual_over_2_percent")
    return {
        "contract": STAGE_INDEX_CONTRACT,
        "stage": "stage1_core_nominal" if not reasons else "stage2_harder_nominal",
        "reasons": reasons,
        "gold_lattice_fit": lattice,
    }


def _interval_contains(interval: object, value: float) -> bool:
    return (
        isinstance(interval, dict)
        and float(interval["minimum"]) <= value <= float(interval["maximum"])
    )


def _interval_distance(interval: dict[str, Any], value: float) -> float:
    minimum = float(interval["minimum"])
    maximum = float(interval["maximum"])
    if value < minimum:
        return minimum - value
    if value > maximum:
        return value - maximum
    return 0.0


def sequence_boundary_diagnostics(
    geometry: dict[str, Any],
    lane: dict[str, Any],
    *,
    placement_state: str,
) -> tuple[dict[str, Any], ...]:
    observations = tuple(lane["observations"]["sequence_edges"])
    observation_by_id = {
        item["observation_id"]: item for item in observations
    }
    competition = lane["phase_competition"]
    best = competition.get("best")
    bound_ids = [] if best is None else list(best["role_observation_ids"])
    canonical_positions = (
        [] if best is None else list(best["canonical_role_positions_px"])
    )
    _, cross_extent = _canonical_axis_extents(geometry)
    common_trace = (cross_extent - 1.0) / 2.0
    results: list[dict[str, Any]] = []
    for item in _referenced_sequence_roles(geometry):
        role_index = 2 * (int(item["ordinal"]) - 1) + (
            1 if item["role"] == "end" else 0
        )
        qualified_matches: list[str] = []
        position_matches: list[str] = []
        nearest_distance = math.inf
        for observation in observations:
            gold_position = line_axis_position(
                geometry,
                item["line"],
                axis="sequence",
                reference_trace_px=float(observation["reference_trace_px"]),
            )
            interval = observation["full_position_interval_px"]
            nearest_distance = min(
                nearest_distance,
                _interval_distance(interval, gold_position),
            )
            if not _interval_contains(interval, gold_position):
                continue
            observation_id = str(observation["observation_id"])
            position_matches.append(observation_id)
            if item["role"] in observation["qualified_anchor_roles"]:
                qualified_matches.append(observation_id)
        bound_id = bound_ids[role_index] if role_index < len(bound_ids) else None
        if bound_id in qualified_matches:
            diagnostic_class = "observed_and_bound"
        elif qualified_matches:
            diagnostic_class = "observed_but_unbound"
        elif position_matches:
            diagnostic_class = "observed_but_role_unqualified"
        elif bound_id is None:
            diagnostic_class = "template_inferred_without_gold_observation"
        else:
            diagnostic_class = "bound_elsewhere_without_gold_observation"
        if competition["status"] != "resolved" or placement_state != "supported":
            resolution = "competing_or_unresolved"
        else:
            resolution = "resolved"
        gold_common = line_axis_position(
            geometry,
            item["line"],
            axis="sequence",
            reference_trace_px=common_trace,
        )
        selected = (
            float(canonical_positions[role_index])
            if role_index < len(canonical_positions)
            else None
        )
        bound_observation = observation_by_id.get(bound_id)
        results.append(
            {
                "axis": "sequence",
                "ordinal": item["ordinal"],
                "slot_kind": item["slot_kind"],
                "role": item["role"],
                "gold_line_id": item["line_id"],
                "gold_review_basis": item["line"]["review_basis"],
                "gold_position_px": gold_common,
                "selected_position_px": selected,
                "selected_minus_gold_px": (
                    None if selected is None else selected - gold_common
                ),
                "bound_observation_id": bound_id,
                "bound_observation_position_px": (
                    None
                    if bound_observation is None
                    else float(bound_observation["canonical_position_px"])
                ),
                "qualified_gold_observation_ids": qualified_matches,
                "position_only_gold_observation_ids": [
                    identity
                    for identity in position_matches
                    if identity not in qualified_matches
                ],
                "nearest_observation_interval_distance_px": (
                    None if math.isinf(nearest_distance) else nearest_distance
                ),
                "diagnostic_class": diagnostic_class,
                "resolution": resolution,
            }
        )
    return tuple(results)


def cross_boundary_diagnostics(
    geometry: dict[str, Any],
    lane: dict[str, Any],
    *,
    placement_state: str,
) -> tuple[dict[str, Any], ...]:
    competition = lane["cross_competition"]
    best = competition.get("best")
    long_extent, _ = _canonical_axis_extents(geometry)
    reference_trace = (
        (long_extent - 1.0) / 2.0
        if best is None
        else float(best["lane_reference_trace_px"])
    )
    bindings = tuple(lane["observations"]["registered_top_bottom_bindings"])
    results: list[dict[str, Any]] = []
    for line, role in zip(geometry["shared_edges"], ("top", "bottom"), strict=True):
        gold_position = line_axis_position(
            geometry,
            line,
            axis="cross",
            reference_trace_px=reference_trace,
        )
        role_bindings = [item for item in bindings if item["role"] == role]
        matching = [
            str(item["observation_id"])
            for item in role_bindings
            if _interval_contains(item["full_interval_px"], gold_position)
        ]
        direct = (
            None
            if best is None
            else next(
                (
                    item
                    for item in best["direct_bindings"]
                    if item["role"] == role
                ),
                None,
            )
        )
        bound_id = None if direct is None else str(direct["observation_id"])
        if bound_id in matching:
            diagnostic_class = "observed_and_bound"
        elif matching:
            diagnostic_class = "observed_but_unbound"
        elif bound_id is None:
            diagnostic_class = "template_or_support_inferred_without_gold_observation"
        else:
            diagnostic_class = "bound_elsewhere_without_gold_observation"
        selected = (
            None
            if best is None
            else float(best[f"{role}_canonical_px"])
        )
        results.append(
            {
                "axis": "cross",
                "ordinal": None,
                "slot_kind": None,
                "role": role,
                "gold_line_id": line["line_id"],
                "gold_review_basis": line["review_basis"],
                "gold_position_px": gold_position,
                "selected_position_px": selected,
                "selected_minus_gold_px": (
                    None if selected is None else selected - gold_position
                ),
                "bound_observation_id": bound_id,
                "qualified_gold_observation_ids": matching,
                "position_only_gold_observation_ids": [],
                "nearest_observation_interval_distance_px": (
                    None
                    if not role_bindings
                    else min(
                        _interval_distance(item["full_interval_px"], gold_position)
                        for item in role_bindings
                    )
                ),
                "diagnostic_class": diagnostic_class,
                "resolution": (
                    "resolved"
                    if competition["status"] == "resolved"
                    and placement_state == "supported"
                    else "competing_or_unresolved"
                ),
                "selected_boundary_use": (
                    None if best is None else best["boundary_use"]
                ),
            }
        )
    return tuple(results)


def _command(record: dict[str, Any], output: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tools.regression.development_run",
        str((PROJECT_ROOT / record["source_relative_path"]).resolve()),
        "--output",
        str(output),
        "--format",
        str(record["format_id"]),
        "--count",
        str(record["count"]),
    ]


def _frame_diagnostics_with_physical_identity(
    record: dict[str, Any],
    diagnostics: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    slots = {
        int(slot["ordinal"]): slot
        for slot in record["confirmed_geometry"]["slots"]
    }
    results: list[dict[str, object]] = []
    for diagnostic in diagnostics:
        ordinal = int(diagnostic["frame_index"])
        reference = slots[ordinal]["reference_geometry"]
        results.append(
            {
                **diagnostic,
                "physical_frame_id": (
                    f"{reference['start_boundary_id']}|"
                    f"{reference['end_boundary_id']}"
                ),
            }
        )
    return results


def _challenge_capability_outcome(
    *,
    cohort_role: str,
    decision_status: str,
    development_contract_passed: bool,
    candidate_geometry_conformance: str,
) -> str | None:
    if cohort_role != "challenge":
        return None
    if decision_status == "approved_auto":
        return (
            "safe_approved_auto"
            if development_contract_passed
            else "unsafe_approved_auto"
        )
    return {
        "safe": "needs_review_with_safe_candidate",
        "unsafe": "needs_review_with_unsafe_candidate",
        "not_available": "needs_review_without_candidate",
    }[candidate_geometry_conformance]


def run_gold_analysis_task(record: dict[str, Any]) -> dict[str, Any]:
    source = (PROJECT_ROOT / record["source_relative_path"]).resolve()
    before = source.stat()
    started = time.perf_counter()
    with TemporaryDirectory(
        prefix=f"x5crop-gold-analysis-{record['sample_id']}-"
    ) as temporary:
        output = Path(temporary) / "x5_crop_output"
        completed = subprocess.run(
            _command(record, output),
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=SOURCE_TIMEOUT_SECONDS,
        )
        duration = time.perf_counter() - started
        if completed.returncode != 0:
            raise ValueError(
                f"production development run failed: {completed.stdout[-4000:]}"
            )
        reports = tuple(
            json.loads(line)
            for line in (output / "x5_crop_report.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        if len(reports) != 1:
            raise ValueError("gold analysis requires one terminal report")
        report = reports[0]
        validate_current_report_record(report)
        after = source.stat()
        identity = report["runtime_identity"]["source"]
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or identity["input_ordinal"] != 1
            or identity["name"] != source.name
            or identity["size"] != before.st_size
            or identity["mtime_ns"] != before.st_mtime_ns
        ):
            raise ValueError("source stat identity changed across gold analysis")

        development_contract_failure = None
        try:
            status = validate_gold_task_result(record, report)
        except ValueError as error:
            status = str(report["decision"]["status"])
            development_contract_failure = str(error)
        candidate_geometry_failure = None
        try:
            candidate_available = validate_selected_candidate_coverage(
                record,
                report,
            )
        except ValueError as error:
            candidate_available = True
            candidate_geometry_failure = str(error)
        candidate_geometry_conformance = (
            "unsafe"
            if candidate_geometry_failure is not None
            else "safe"
            if candidate_available
            else "not_available"
        )
        development_lanes = report["development"]["lanes"]
        production_lanes = report["photo_geometry"]["lanes"]
        if len(development_lanes) != 1 or len(production_lanes) != 1:
            raise ValueError("current gold analysis requires one physical lane")
        placement_state = report["photo_geometry"]["source_placement_selection"][
            "state"
        ]
        boundaries = (
            *sequence_boundary_diagnostics(
                record["confirmed_geometry"],
                development_lanes[0],
                placement_state=placement_state,
            ),
            *cross_boundary_diagnostics(
                record["confirmed_geometry"],
                development_lanes[0],
                placement_state=placement_state,
            ),
        )
        frame_diagnostics = _frame_diagnostics_with_physical_identity(
            record,
            gold_frame_diagnostics(record, report),
        )
    development_contract_passed = development_contract_failure is None
    unsafe_approved_auto = (
        status == "approved_auto" and not development_contract_passed
    )
    return {
        "record_schema": ANALYSIS_RECORD_SCHEMA,
        "sample_id": record["sample_id"],
        "source_sha256": record["source_sha256"],
        "format_id": record["format_id"],
        "count": record["count"],
        "cohort_role": record["cohort_role"],
        "optimization_stage": optimization_stage_index(record),
        "decision_status": status,
        "final_review_reasons": list(report["decision"]["final_review_reasons"]),
        "development_contract_passed": development_contract_passed,
        "development_contract_failure": development_contract_failure,
        "candidate_geometry_conformance": candidate_geometry_conformance,
        "candidate_geometry_failure": candidate_geometry_failure,
        "unsafe_approved_auto": unsafe_approved_auto,
        "nominal_auto_goal_passed": (
            record["cohort_role"] == "nominal"
            and status == "approved_auto"
            and development_contract_passed
        ),
        "challenge_capability_outcome": _challenge_capability_outcome(
            cohort_role=str(record["cohort_role"]),
            decision_status=status,
            development_contract_passed=development_contract_passed,
            candidate_geometry_conformance=candidate_geometry_conformance,
        ),
        "source_placement_state": placement_state,
        "phase_status": production_lanes[0]["phase_status"],
        "cross_status": production_lanes[0]["cross_status"],
        "selected_cross_boundary_use": production_lanes[0][
            "selected_cross_boundary_use"
        ],
        "duration_seconds": duration,
        "boundary_diagnostics": list(boundaries),
        "frame_candidate_geometry_diagnostics": list(frame_diagnostics),
    }


def _counter(records: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record[key]) for record in records).items()))


def _development_contract_failure_category(
    record: dict[str, Any],
) -> str | None:
    failure = record["development_contract_failure"]
    if failure is None:
        return None
    if "nominal task is needs_review" in failure:
        return "nominal_needs_review"
    if "candidate crosses user-confirmed inward baseline" in failure:
        return "candidate_crosses_inward_baseline"
    if "approved output crosses user-confirmed inward baseline" in failure:
        return "approved_output_crosses_inward_baseline"
    if "exceeds acceptance-baseline direct-use budget" in failure:
        return "direct_use_budget_exceeded"
    return "analysis_or_contract_failure"


def _source_manifest_identity(paths: Sequence[str]) -> dict[str, Any]:
    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *paths],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if diff.returncode not in {0, 1}:
        raise ValueError("cannot establish analysis source identity")
    source_paths = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *paths,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.splitlines()
    untracked_paths = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            *paths,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.splitlines()
    manifest = hashlib.sha256()
    for relative in sorted(source_paths):
        manifest.update(relative.encode("utf-8"))
        manifest.update(b"\0")
        path = PROJECT_ROOT / relative
        manifest.update(
            sha256_file(path).encode("ascii") if path.is_file() else b"deleted"
        )
        manifest.update(b"\n")
    return {
        "paths_match_head": diff.returncode == 0 and not untracked_paths,
        "source_manifest_sha256": manifest.hexdigest(),
    }


def _analysis_identity() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    detector = _source_manifest_identity(("X5_Crop.py", "x5crop"))
    comparator = _source_manifest_identity(COMPARATOR_SOURCE_PATHS)
    return {
        "repository_head_commit": head,
        "detector_paths_match_head": detector["paths_match_head"],
        "detector_source_manifest_sha256": detector[
            "source_manifest_sha256"
        ],
        "comparator_paths_match_head": comparator["paths_match_head"],
        "comparator_source_manifest_sha256": comparator[
            "source_manifest_sha256"
        ],
        "development_gold_cohort_sha256": sha256_file(
            DEVELOPMENT_GOLD_COHORT_PATH
        ),
    }


def _count_variant_diagnostics(
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_source[str(record["source_sha256"])].append(record)
    diagnostics: list[dict[str, Any]] = []
    for source_sha, members in sorted(by_source.items()):
        if len(members) < 2:
            continue
        frame_states: dict[str, dict[str, str]] = defaultdict(dict)
        for member in members:
            for frame in member["frame_candidate_geometry_diagnostics"]:
                unsafe = bool(
                    frame["inward_failure_sides"]
                    or frame["outward_budget_failure_sides"]
                )
                frame_states[str(frame["physical_frame_id"])][
                    str(member["sample_id"])
                ] = "unsafe" if unsafe else "safe"
        mismatches = [
            {
                "physical_frame_id": identity,
                "task_states": dict(sorted(states.items())),
            }
            for identity, states in sorted(frame_states.items())
            if len(states) > 1 and set(states.values()) == {"safe", "unsafe"}
        ]
        diagnostics.append(
            {
                "source_sha256": source_sha,
                "tasks": [
                    {
                        "sample_id": member["sample_id"],
                        "count": member["count"],
                        "cohort_role": member["cohort_role"],
                        "decision_status": member["decision_status"],
                        "candidate_geometry_conformance": member[
                            "candidate_geometry_conformance"
                        ],
                        "unsafe_approved_auto": member[
                            "unsafe_approved_auto"
                        ],
                    }
                    for member in sorted(
                        members,
                        key=lambda item: str(item["sample_id"]),
                    )
                ],
                "shared_frame_safety_mismatches": mismatches,
                "candidate_safety_mismatch": bool(mismatches),
                "candidate_availability_mismatch": len(
                    {
                        member["candidate_geometry_conformance"]
                        for member in members
                    }
                )
                > 1,
                "unsafe_approved_auto_task_ids": sorted(
                    str(member["sample_id"])
                    for member in members
                    if member["unsafe_approved_auto"]
                ),
            }
        )
    return diagnostics


def _summary(
    records: Sequence[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    boundaries: list[dict[str, Any]] = []
    for record in records:
        by_stage[record["optimization_stage"]["stage"]].append(record)
        boundaries.extend(record["boundary_diagnostics"])
    directly_visible = [
        item
        for item in boundaries
        if item["gold_review_basis"] == "directly_visible"
    ]
    durations = [float(record["duration_seconds"]) for record in records]
    analysis_error_count = sum(record["decision_status"] is None for record in records)
    failure_categories = Counter(
        category
        for record in records
        if (
            category := _development_contract_failure_category(record)
        )
        is not None
    )
    variants = _count_variant_diagnostics(records)
    completed = [record for record in records if record["decision_status"] is not None]
    challenge_outcomes = Counter(
        str(record["challenge_capability_outcome"])
        for record in completed
        if record["challenge_capability_outcome"] is not None
    )
    candidate_states = Counter(
        str(record["candidate_geometry_conformance"])
        for record in completed
    )
    review_candidate_states = Counter(
        str(record["candidate_geometry_conformance"])
        for record in completed
        if record["decision_status"] == "needs_review"
    )
    return {
        "summary_schema": ANALYSIS_SUMMARY_SCHEMA,
        "validation_role": "development_gold_diagnostic",
        "analysis_identity": identity,
        "task_count": len(records),
        "analysis_completed_count": len(records) - analysis_error_count,
        "analysis_error_count": analysis_error_count,
        "development_contract_passed_count": sum(
            record["development_contract_passed"] for record in records
        ),
        "development_contract_failure_count": sum(
            not record["development_contract_passed"] for record in records
        ),
        "development_contract_failure_category_counts": dict(
            sorted(failure_categories.items())
        ),
        "safe_approved_auto_count": sum(
            record["decision_status"] == "approved_auto"
            and not record["unsafe_approved_auto"]
            for record in records
        ),
        "unsafe_approved_auto_count": sum(
            record["unsafe_approved_auto"] for record in records
        ),
        "candidate_geometry_conformance_counts": dict(
            sorted(candidate_states.items())
        ),
        "review_candidate_conformance_counts": dict(
            sorted(review_candidate_states.items())
        ),
        "nominal_auto_goal_passed_count": sum(
            record["nominal_auto_goal_passed"] for record in records
        ),
        "nominal_needs_review_count": sum(
            record["cohort_role"] == "nominal"
            and record["decision_status"] == "needs_review"
            for record in records
        ),
        "challenge_capability_outcome_counts": dict(
            sorted(challenge_outcomes.items())
        ),
        "count_variant_source_count": len(variants),
        "count_variant_candidate_safety_mismatch_count": sum(
            item["candidate_safety_mismatch"] for item in variants
        ),
        "count_variant_diagnostics": variants,
        "decision_status_counts": _counter(records, "decision_status"),
        "stage_counts": dict(
            sorted(
                (stage, len(items)) for stage, items in by_stage.items()
            )
        ),
        "stages": {
            stage: {
                "task_count": len(items),
                "development_contract_passed_count": sum(
                    item["development_contract_passed"] for item in items
                ),
                "safe_approved_auto_count": sum(
                    item["decision_status"] == "approved_auto"
                    and not item["unsafe_approved_auto"]
                    for item in items
                ),
                "approved_auto_count": sum(
                    item["decision_status"] == "approved_auto" for item in items
                ),
                "needs_review_count": sum(
                    item["decision_status"] == "needs_review" for item in items
                ),
                "unsafe_approved_auto_count": sum(
                    item["unsafe_approved_auto"] for item in items
                ),
                "candidate_geometry_conformance_counts": dict(
                    sorted(
                        Counter(
                            str(item["candidate_geometry_conformance"])
                            for item in items
                        ).items()
                    )
                ),
            }
            for stage, items in sorted(by_stage.items())
        },
        "boundary_diagnostic_counts": _counter(boundaries, "diagnostic_class"),
        "directly_visible_boundary_diagnostic_counts": _counter(
            directly_visible,
            "diagnostic_class",
        ),
        "resolution_counts": _counter(boundaries, "resolution"),
        "duration_seconds": {
            "total": sum(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "maximum": max(durations),
            "scope": "development_detail_end_to_end_diagnostic_not_performance_gate",
        },
    }


def validate_gold_analysis_artifacts(output_root: Path) -> dict[str, Any]:
    """Re-read one analysis artifact and prove its schema and aggregation."""

    records = tuple(
        json.loads(line)
        for line in (output_root / "gold_analysis_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )
    summary = json.loads(
        (output_root / "gold_analysis_summary.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        not records
        or any(
            record.get("record_schema") != ANALYSIS_RECORD_SCHEMA
            for record in records
        )
        or len({record.get("sample_id") for record in records}) != len(records)
        or summary.get("summary_schema") != ANALYSIS_SUMMARY_SCHEMA
        or not isinstance(summary.get("analysis_identity"), dict)
        or _summary(records, summary["analysis_identity"]) != summary
    ):
        raise ValueError("development gold analysis artifact is invalid")
    return summary


def run_gold_analysis(
    output_root: Path,
    *,
    sample_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"gold analysis output root must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    identity = _analysis_identity()
    complete_gold = validate_gold_source_identities()
    requested = None if sample_ids is None else set(sample_ids)
    if requested is not None:
        known = {str(record["sample_id"]) for record in complete_gold}
        unknown = requested - known
        if unknown:
            raise ValueError(
                "unknown gold task: " + ", ".join(sorted(unknown))
            )
    gold = tuple(
        record
        for record in complete_gold
        if requested is None or record["sample_id"] in requested
    )
    records: list[dict[str, Any]] = []
    for index, record in enumerate(gold, start=1):
        print(
            f"[{index:03d}/{len(gold):03d}] {record['sample_id']}",
            flush=True,
        )
        try:
            result = run_gold_analysis_task(record)
        except Exception as error:
            result = {
                "record_schema": ANALYSIS_RECORD_SCHEMA,
                "sample_id": record["sample_id"],
                "source_sha256": record["source_sha256"],
                "format_id": record["format_id"],
                "count": record["count"],
                "cohort_role": record["cohort_role"],
                "optimization_stage": optimization_stage_index(record),
                "decision_status": None,
                "final_review_reasons": [],
                "development_contract_passed": False,
                "development_contract_failure": (
                    f"{type(error).__name__}: {error}"
                ),
                "candidate_geometry_conformance": "not_available",
                "candidate_geometry_failure": None,
                "unsafe_approved_auto": False,
                "nominal_auto_goal_passed": False,
                "challenge_capability_outcome": None,
                "source_placement_state": None,
                "phase_status": None,
                "cross_status": None,
                "selected_cross_boundary_use": None,
                "duration_seconds": 0.0,
                "boundary_diagnostics": [],
                "frame_candidate_geometry_diagnostics": [],
            }
        records.append(result)
        print(
            f"  {result['decision_status'] or 'analysis_error'} · "
            "candidate="
            f"{result['candidate_geometry_conformance']} · "
            "development_contract="
            f"{'pass' if result['development_contract_passed'] else 'fail'} · "
            f"{result['optimization_stage']['stage']}",
            flush=True,
        )
    records_path = output_root / "gold_analysis_records.jsonl"
    records_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    summary = _summary(records, identity)
    (output_root / "gold_analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return validate_gold_analysis_artifacts(output_root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="limit analysis to one gold task; repeat as needed",
    )
    parser.add_argument(
        "--gate",
        choices=("report", "zero-unsafe-auto"),
        default="report",
        help=(
            "report only, or fail unless the complete development gold has "
            "zero unsafe automatic approvals"
        ),
    )
    args = parser.parse_args(argv)
    if args.gate == "zero-unsafe-auto" and args.sample_ids is not None:
        print(
            "development gold analysis: FAIL: the safety gate requires the "
            "complete cohort",
            file=sys.stderr,
        )
        return 2
    try:
        summary = run_gold_analysis(
            args.output_root.expanduser().resolve(),
            sample_ids=args.sample_ids,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"development gold analysis: FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["analysis_error_count"] != 0:
        return 1
    if (
        args.gate == "zero-unsafe-auto"
        and summary["unsafe_approved_auto_count"] != 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
