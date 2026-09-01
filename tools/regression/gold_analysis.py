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

from x5crop.configuration.scan_canvas import (
    ScanCanvasDetectionConfiguration,
)
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.source_core import SourceStripValidationDomain
from x5crop.domain import Box
from x5crop.formats import (
    APERTURE_COMPATIBILITY_SPEC,
    format_spec,
)
from x5crop.formats.scan_canvas import scan_canvas_specs_for_format

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


ANALYSIS_RECORD_SCHEMA = "x5crop_development_gold_analysis_record_v10"
ANALYSIS_SUMMARY_SCHEMA = "x5crop_development_gold_analysis_summary_v11"
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


def _line_pool(geometry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(line["line_id"]): line for line in geometry["boundary_pool"]
    }


def _boundary_pair_by_ordinal(
    geometry: dict[str, Any],
) -> dict[int, tuple[dict[str, Any], dict[str, Any], str]]:
    lines = _line_pool(geometry)
    pairs: dict[int, tuple[dict[str, Any], dict[str, Any], str]] = {}
    for slot in geometry["slots"]:
        reference = slot["reference_geometry"]
        if reference["kind"] != "boundary_pair":
            continue
        pairs[int(slot["ordinal"])] = (
            lines[str(reference["start_boundary_id"])],
            lines[str(reference["end_boundary_id"])],
            str(slot["slot_kind"]),
        )
    return pairs


def _outside_distance(interval: object, value: float) -> float:
    minimum = float(getattr(interval, "minimum"))
    maximum = float(getattr(interval, "maximum"))
    return max(minimum - value, value - maximum, 0.0)


def _physical_prior_diagnostic(record: dict[str, Any]) -> dict[str, Any]:
    """Compare one confirmed source against the current physical catalogue."""

    geometry = record["confirmed_geometry"]
    physical = format_spec(str(record["format_id"]))
    frame = physical.frame
    long_extent, cross_extent = _canonical_axis_extents(geometry)
    profiles = scan_canvas_specs_for_format(physical.format_id)
    observed_aspect = long_extent / cross_extent
    nearest_profile = min(
        profiles,
        key=lambda item: (
            abs(observed_aspect - item.aspect) / item.aspect,
            item.profile_id,
        ),
    )
    aspect_error = (
        abs(observed_aspect - nearest_profile.aspect) / nearest_profile.aspect
    )
    canvas_configuration = ScanCanvasDetectionConfiguration(profiles)
    canvas_evidence = observe_scan_canvas(
        int(long_extent),
        int(cross_extent),
        "horizontal",
        canvas_configuration,
    )
    selected_profile = canvas_evidence.selected_profile
    scale_authority = canvas_evidence.axis_scales
    source_geometry = (
        None
        if scale_authority is None
        else SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=scale_authority.width_axis_px_per_mm,
            height_scale_px_per_mm=scale_authority.height_axis_px_per_mm,
        )
    )
    plan = None
    if selected_profile is not None and scale_authority is not None:
        holder_count = physical.holder_full_count(selected_profile.profile_id)
        if holder_count is None:
            raise ValueError("selected scan canvas has no format capacity")
        plan = compile_template_measurement_plan(
            format_spec=physical,
            frame_spec=frame,
            count=int(record["count"]),
            full_count=holder_count,
            holder_full_count=holder_count,
            lane_authority=SourceStripValidationDomain(
                lane_id="gold-physics",
                work_box=Box(0, 0, int(long_extent), int(cross_extent)),
                source_axis_long="x",
                authority_profile_id=selected_profile.profile_id,
            ),
            layout="horizontal",
            scale_authority=scale_authority,
        )

    pairs = _boundary_pair_by_ordinal(geometry)
    shared = geometry["shared_edges"]
    cross_reference = (cross_extent - 1.0) / 2.0
    sequence_scale_px_per_nominal_mm = (
        None
        if selected_profile is None
        else long_extent / selected_profile.long_axis_mm
    )
    cross_scale_px_per_nominal_mm = (
        None
        if selected_profile is None
        else cross_extent / selected_profile.short_axis_mm
    )
    frame_ratio_measurements: list[float] = []
    frame_width_estimates_mm: list[float] = []
    frame_height_estimates_mm: list[float] = []
    frame_width_prior_containment: list[bool] = []
    frame_height_prior_containment: list[bool] = []
    excluded_frame_count = 0
    for start, end, slot_kind in pairs.values():
        if (
            slot_kind != "image"
            or start["review_basis"] != "directly_visible"
            or end["review_basis"] != "directly_visible"
        ):
            excluded_frame_count += 1
            continue
        start_position = line_axis_position(
            geometry,
            start,
            axis="sequence",
            reference_trace_px=cross_reference,
        )
        end_position = line_axis_position(
            geometry,
            end,
            axis="sequence",
            reference_trace_px=cross_reference,
        )
        long_reference = (start_position + end_position) / 2.0
        top = line_axis_position(
            geometry,
            shared[0],
            axis="cross",
            reference_trace_px=long_reference,
        )
        bottom = line_axis_position(
            geometry,
            shared[1],
            axis="cross",
            reference_trace_px=long_reference,
        )
        width = abs(end_position - start_position)
        height = abs(bottom - top)
        if min(width, height) <= 0.0:
            raise ValueError("gold frame has non-positive physical extent")
        frame_ratio_measurements.append(width / height)
        if (
            sequence_scale_px_per_nominal_mm is not None
            and cross_scale_px_per_nominal_mm is not None
        ):
            frame_width_estimates_mm.append(
                width / sequence_scale_px_per_nominal_mm
            )
            frame_height_estimates_mm.append(
                height / cross_scale_px_per_nominal_mm
            )
        if source_geometry is not None:
            frame_width_prior_containment.append(
                source_geometry.width_state.extent_projection_px().contains(
                    width
                )
            )
            frame_height_prior_containment.append(
                source_geometry.height_state.extent_projection_px().contains(
                    height
                )
            )

    gap_estimates_mm: list[float] = []
    gap_prior_containment: list[bool] = []
    pitch_estimates_mm: list[float] = []
    pitch_prior_containment: list[bool] = []
    excluded_separator_count = 0
    for adjacency in geometry["adjacencies"]:
        if adjacency["kind"] != "separator":
            continue
        left = pairs.get(int(adjacency["left_ordinal"]))
        right = pairs.get(int(adjacency["right_ordinal"]))
        if (
            left is None
            or right is None
            or left[1]["review_basis"] != "directly_visible"
            or right[0]["review_basis"] != "directly_visible"
        ):
            excluded_separator_count += 1
            continue
        left_end = line_axis_position(
            geometry,
            left[1],
            axis="sequence",
            reference_trace_px=cross_reference,
        )
        right_start = line_axis_position(
            geometry,
            right[0],
            axis="sequence",
            reference_trace_px=cross_reference,
        )
        gap = right_start - left_end
        if gap < 0.0:
            raise ValueError("gold separator contradicts physical order")
        if sequence_scale_px_per_nominal_mm is not None:
            gap_estimates_mm.append(
                gap / sequence_scale_px_per_nominal_mm
            )
        if (
            left[0]["review_basis"] == "directly_visible"
            and right[1]["review_basis"] == "directly_visible"
        ):
            left_start = line_axis_position(
                geometry,
                left[0],
                axis="sequence",
                reference_trace_px=cross_reference,
            )
            right_end = line_axis_position(
                geometry,
                right[1],
                axis="sequence",
                reference_trace_px=cross_reference,
            )
            pitch = (
                (right_start - left_start) + (right_end - left_end)
            ) / 2.0
            if pitch <= 0.0:
                raise ValueError("gold pitch contradicts physical order")
            if sequence_scale_px_per_nominal_mm is not None:
                pitch_estimates_mm.append(
                    pitch / sequence_scale_px_per_nominal_mm
                )
            if plan is not None:
                pitch_prior_containment.append(
                    plan.template_spec.pitch_px.minimum
                    <= pitch
                    <= plan.template_spec.pitch_px.maximum
                )
        if frame.format_gap_prior_mm is not None and plan is not None:
            gap_prior_containment.append(
                plan.template_spec.nominal_gap_px.minimum
                <= gap
                <= plan.template_spec.nominal_gap_px.maximum
            )

    corridor = {
        "available": False,
        "trace_count": 0,
        "top_outside_trace_count": 0,
        "bottom_outside_trace_count": 0,
        "maximum_top_outside_px": None,
        "maximum_bottom_outside_px": None,
    }
    if plan is not None:
        projected = plan.projected_queries
        top_outside: list[float] = []
        bottom_outside: list[float] = []
        for trace, top_interval, bottom_interval in zip(
            projected.cross_trace_positions_px,
            projected.top_measurement_intervals_px,
            projected.bottom_measurement_intervals_px,
            strict=True,
        ):
            top_position = line_axis_position(
                geometry,
                shared[0],
                axis="cross",
                reference_trace_px=float(trace),
            )
            bottom_position = line_axis_position(
                geometry,
                shared[1],
                axis="cross",
                reference_trace_px=float(trace),
            )
            top_outside.append(_outside_distance(top_interval, top_position))
            bottom_outside.append(
                _outside_distance(bottom_interval, bottom_position)
            )
        corridor = {
            "available": True,
            "trace_count": len(top_outside),
            "top_outside_trace_count": sum(value > 0.0 for value in top_outside),
            "bottom_outside_trace_count": sum(
                value > 0.0 for value in bottom_outside
            ),
            "maximum_top_outside_px": max(top_outside, default=0.0),
            "maximum_bottom_outside_px": max(bottom_outside, default=0.0),
        }

    return {
        "source_sha256": record["source_sha256"],
        "format_id": physical.format_id,
        "count": int(record["count"]),
        "scan_canvas_outcome": canvas_evidence.outcome.value,
        "scan_canvas_matching_profile_ids": [
            match.profile.profile_id for match in canvas_evidence.matches
        ],
        "scan_canvas_profile_id": (
            None if selected_profile is None else selected_profile.profile_id
        ),
        "nearest_scan_canvas_profile_id": nearest_profile.profile_id,
        "scan_canvas_aspect_error_ratio": aspect_error,
        "scan_canvas_scale_authority_supported": scale_authority is not None,
        "dimension_estimate_basis": (
            "gold_native_geometry_divided_by_selected_nominal_holder_axis_scale"
        ),
        "sequence_scale_px_per_nominal_mm": (
            sequence_scale_px_per_nominal_mm
        ),
        "cross_scale_px_per_nominal_mm": cross_scale_px_per_nominal_mm,
        "frame_ratio_measurements": frame_ratio_measurements,
        "holder_normalized_frame_width_estimates_mm": (
            frame_width_estimates_mm
        ),
        "holder_normalized_frame_height_estimates_mm": (
            frame_height_estimates_mm
        ),
        "frame_width_prior_containment": frame_width_prior_containment,
        "frame_height_prior_containment": frame_height_prior_containment,
        "excluded_frame_count": excluded_frame_count,
        "holder_normalized_separator_gap_estimates_mm": gap_estimates_mm,
        "separator_gap_prior_containment": gap_prior_containment,
        "holder_normalized_pitch_estimates_mm": pitch_estimates_mm,
        "pitch_prior_containment": pitch_prior_containment,
        "excluded_separator_count": excluded_separator_count,
        "cross_corridor": corridor,
    }


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


def _selected_placement(lane: dict[str, Any]) -> dict[str, Any] | None:
    competition = lane["placement_competition"]
    selected_id = competition.get("selected_placement_id")
    if selected_id is None:
        return None
    matches = tuple(
        placement
        for placement in competition["placements"]
        if placement["placement_id"] == selected_id
    )
    if len(matches) != 1:
        raise ValueError("selected placement identity is not unique")
    return matches[0]


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
    bound_ids = (
        []
        if best is None
        else [
            None if binding is None else str(binding["observation_id"])
            for binding in best["role_bindings"]
        ]
    )
    selected_placement = _selected_placement(lane)
    selected_frames = (
        () if selected_placement is None else selected_placement["frames"]
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
        frame_index = int(item["ordinal"]) - 1
        selected = (
            None
            if frame_index >= len(selected_frames)
            else float(selected_frames[frame_index][item["role"]]["canonical_position_px"])
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
    selected_placement = _selected_placement(lane)
    selected_cross = (
        None if selected_placement is None else selected_placement["cross_fit"]
    )
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
            if selected_cross is None
            else float(selected_cross[f"{role}_canonical_px"])
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
                    None if selected_cross is None else selected_cross["boundary_use"]
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
    physical_prior = _physical_prior_diagnostic(record)
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
        phase_competition = development_lanes[0]["phase_competition"]
        phase_best = phase_competition["best"]
        nominal_evidence = phase_competition[
            "calibrated_nominal_grid_evidence"
        ]
        nominal_authority = production_lanes[0][
            "calibrated_nominal_grid_authority"
        ]
        phase_receipt = phase_competition["receipt"]
        enclosing_resolution = development_lanes[0]["search"][
            "coarse_strip_support"
        ]["enclosing_resolution"]
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
        "phase_failure_kind": development_lanes[0]["phase_competition"].get(
            "failure_kind"
        ),
        "coarse_enclosing_resolution_state": enclosing_resolution["state"],
        "coarse_enclosing_resolution_failure_kind": enclosing_resolution[
            "failure_kind"
        ],
        "coarse_enclosing_candidate_measurement_bases": [
            candidate["measurement_basis"]
            for candidate in enclosing_resolution["candidates"]
        ],
        "coarse_enclosing_selected_measurement_basis": (
            None
            if enclosing_resolution["selected_candidate"] is None
            else enclosing_resolution["selected_candidate"][
                "measurement_basis"
            ]
        ),
        "lattice_parameter_fit_basis": (
            None
            if phase_best is None
            else phase_best["lattice_parameter_fit_basis"]
        ),
        "calibrated_nominal_grid_evidence_state": (
            None if nominal_evidence is None else nominal_evidence["state"]
        ),
        "calibrated_nominal_grid_evidence_failure_kind": (
            None
            if nominal_evidence is None
            else nominal_evidence["failure_kind"]
        ),
        "calibrated_nominal_grid_authority_state": nominal_authority["state"],
        "calibrated_nominal_grid_authority_failure_kind": nominal_authority[
            "failure_kind"
        ],
        "candidate_nominal_grid_solve_count": phase_receipt[
            "candidate_nominal_grid_solve_count"
        ],
        "candidate_nominal_grid_solve_success_count": phase_receipt[
            "candidate_nominal_grid_solve_success_count"
        ],
        "cross_status": production_lanes[0]["cross_status"],
        "cross_failure_kind": development_lanes[0][
            "cross_competition"
        ].get("failure_kind"),
        "cross_failure_reason": development_lanes[0][
            "cross_competition"
        ].get("reason"),
        "placement_failure_gap": (
            None
            if development_lanes[0]["placement_competition"]["failure"]
            is None
            else development_lanes[0]["placement_competition"]["failure"][
                "gap"
            ]
        ),
        "selected_cross_boundary_use": production_lanes[0][
            "selected_cross_boundary_use"
        ],
        "duration_seconds": duration,
        "boundary_diagnostics": list(boundaries),
        "frame_candidate_geometry_diagnostics": list(frame_diagnostics),
        "physical_prior_diagnostic": physical_prior,
    }


def _counter(records: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record[key]) for record in records).items()))


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    samples = tuple(float(value) for value in values)
    if not samples:
        return {
            "count": 0,
            "minimum": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "maximum": None,
        }
    return {
        "count": len(samples),
        "minimum": min(samples),
        "p50": float(np.percentile(samples, 50)),
        "p90": float(np.percentile(samples, 90)),
        "p95": float(np.percentile(samples, 95)),
        "maximum": max(samples),
    }


def _source_variation_summary(
    diagnostics: Sequence[dict[str, Any]],
    measurement_key: str,
) -> dict[str, Any]:
    """Separate per-source aperture variation from between-source variation."""

    source_values = tuple(
        tuple(float(value) for value in diagnostic[measurement_key])
        for diagnostic in diagnostics
        if diagnostic[measurement_key]
    )
    centers = tuple(statistics.median(values) for values in source_values)
    within_source = tuple(values for values in source_values if len(values) >= 2)
    relative_ranges = tuple(
        (max(values) - min(values)) / statistics.median(values)
        for values in within_source
    )
    relative_residuals = tuple(
        (value - center) / center
        for values in within_source
        for center in (statistics.median(values),)
        for value in values
    )
    pooled_within_rms = (
        None
        if not relative_residuals
        else math.sqrt(
            sum(value * value for value in relative_residuals)
            / len(relative_residuals)
        )
    )
    between_relative_std = (
        None
        if len(centers) < 2
        else statistics.pstdev(centers) / statistics.median(centers)
    )
    return {
        "measurement_count": sum(len(values) for values in source_values),
        "source_count": len(source_values),
        "multi_measurement_source_count": len(within_source),
        "measurement_distribution": _distribution(
            value for values in source_values for value in values
        ),
        "source_center_distribution": _distribution(centers),
        "within_source_relative_range": _distribution(relative_ranges),
        "pooled_within_source_relative_rms": pooled_within_rms,
        "between_source_relative_std": between_relative_std,
        "between_to_within_ratio": (
            None
            if between_relative_std is None
            or pooled_within_rms is None
            or pooled_within_rms <= 0.0
            else between_relative_std / pooled_within_rms
        ),
    }


def _unique_source_physical_diagnostics(
    records: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for record in records:
        diagnostic = record["physical_prior_diagnostic"]
        if diagnostic.get("analysis_error") is not None:
            continue
        source_sha = str(record["source_sha256"])
        current = selected.get(source_sha)
        if current is None or (
            int(diagnostic["count"]),
            str(record["sample_id"]),
        ) > (
            int(current["count"]),
            str(current["sample_id"]),
        ):
            selected[source_sha] = {
                **diagnostic,
                "sample_id": str(record["sample_id"]),
                "cohort_role": str(record["cohort_role"]),
            }
    return tuple(
        selected[source_sha] for source_sha in sorted(selected)
    )


def _unique_nominal_pitch_diagnostics(
    records: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Select one nominal task per source for pitch calibration only."""

    selected: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["cohort_role"] != "nominal":
            continue
        diagnostic = record["physical_prior_diagnostic"]
        if diagnostic.get("analysis_error") is not None:
            continue
        source_sha = str(record["source_sha256"])
        current = selected.get(source_sha)
        if current is None or (
            int(diagnostic["count"]),
            str(record["sample_id"]),
        ) > (
            int(current["count"]),
            str(current["sample_id"]),
        ):
            selected[source_sha] = {
                **diagnostic,
                "sample_id": str(record["sample_id"]),
                "cohort_role": "nominal",
            }
    return tuple(selected[source_sha] for source_sha in sorted(selected))


def _round_outward(value: float, quantum: float) -> float:
    if min(value, quantum) <= 0.0:
        raise ValueError("calibration rounding requires positive values")
    return math.ceil((value - 1.0e-12) / quantum) * quantum


def _round_outward_lower(value: float, quantum: float) -> float:
    if min(value, quantum) <= 0.0:
        raise ValueError("calibration rounding requires positive values")
    return math.floor((value + 1.0e-12) / quantum) * quantum


def _nominal_pitch_calibration(
    format_id: str,
    diagnostics: Sequence[dict[str, Any]],
    *,
    cohort_sha256: str | None,
) -> dict[str, Any]:
    """Reproduce one format's source-level calibrated nominal pitch."""

    physical = format_spec(format_id)
    configured = physical.nominal_pitch_calibration
    minimum_measurements = (
        2 if configured is None else configured.minimum_measurements_per_source
    )
    sources = []
    for diagnostic in diagnostics:
        measurements = tuple(
            float(value)
            for value in diagnostic["holder_normalized_pitch_estimates_mm"]
        )
        if (
            diagnostic["cohort_role"] != "nominal"
            or len(measurements) < minimum_measurements
        ):
            continue
        sources.append(
            {
                "sample_id": str(diagnostic["sample_id"]),
                "measurement_count": len(measurements),
                "source_center_mm": statistics.median(measurements),
            }
        )
    raw_minimum = (
        None
        if not sources
        else min(float(item["source_center_mm"]) for item in sources)
    )
    raw_maximum = (
        None
        if not sources
        else max(float(item["source_center_mm"]) for item in sources)
    )
    rounding = 0.05 if configured is None else configured.outward_rounding_mm
    expected_minimum = (
        None
        if raw_minimum is None
        else _round_outward_lower(raw_minimum, rounding)
    )
    expected_maximum = (
        None if raw_maximum is None else _round_outward(raw_maximum, rounding)
    )
    measurement_count = sum(int(item["measurement_count"]) for item in sources)
    matches = (
        configured is not None
        and cohort_sha256 == configured.development_gold_cohort_sha256
        and len(sources) == configured.development_source_count
        and measurement_count == configured.development_measurement_count
        and math.isclose(
            float(expected_minimum),
            configured.minimum_pitch_mm,
        )
        and math.isclose(
            float(expected_maximum),
            configured.maximum_pitch_mm,
        )
    )
    return {
        "method": (
            "nominal development source; directly visible START/END around a "
            "separator adjacency; per-source median; source-center hull; "
            "outward quantization"
        ),
        "minimum_measurements_per_source": minimum_measurements,
        "outward_rounding_mm": rounding,
        "eligible_source_count": len(sources),
        "eligible_measurement_count": measurement_count,
        "source_center_distribution_mm": _distribution(
            float(item["source_center_mm"]) for item in sources
        ),
        "derived_raw_interval_mm": {
            "minimum": raw_minimum,
            "maximum": raw_maximum,
        },
        "derived_outward_interval_mm": {
            "minimum": expected_minimum,
            "maximum": expected_maximum,
        },
        "registered_calibration_id": (
            None if configured is None else configured.calibration_id
        ),
        "registered_cohort_sha256": (
            None
            if configured is None
            else configured.development_gold_cohort_sha256
        ),
        "actual_cohort_sha256": cohort_sha256,
        "registered_interval_mm": (
            None
            if configured is None
            else {
                "minimum": configured.minimum_pitch_mm,
                "maximum": configured.maximum_pitch_mm,
            }
        ),
        "registered_source_count": (
            None if configured is None else configured.development_source_count
        ),
        "registered_measurement_count": (
            None
            if configured is None
            else configured.development_measurement_count
        ),
        "configured_matches_calibration": matches,
    }


def _fit_mixed_axis_guard(
    points: Sequence[tuple[float, float]],
) -> tuple[float, float, float]:
    """Fit max(absolute floor, relative * nominal) to grouped q95 facts."""

    ordered = tuple(sorted(points))
    if len(ordered) < 2 or len({item[0] for item in ordered}) != len(ordered):
        raise ValueError("mixed axis guard needs two unique nominal extents")
    candidates: list[tuple[float, int, float, float]] = []
    for split in range(1, len(ordered)):
        absolute_floor = max(value for _nominal, value in ordered[:split])
        relative_ratio = max(
            value / nominal for nominal, value in ordered[split:]
        )
        total_guard = sum(
            max(absolute_floor, relative_ratio * nominal)
            for nominal, _value in ordered
        )
        candidates.append(
            (total_guard, split, absolute_floor, relative_ratio)
        )
    _score, _split, absolute_floor, relative_ratio = min(candidates)
    return absolute_floor, relative_ratio, _score


def _axis_guard_calibration(
    diagnostics: Sequence[dict[str, Any]],
    *,
    axis: str,
) -> dict[str, Any]:
    if axis not in {"width", "height"}:
        raise ValueError("aperture guard axis is invalid")
    measurement_key = (
        "holder_normalized_frame_width_estimates_mm"
        if axis == "width"
        else "holder_normalized_frame_height_estimates_mm"
    )
    nominal_attr = "frame_width_mm" if axis == "width" else "frame_height_mm"
    by_nominal: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for diagnostic in diagnostics:
        values = tuple(float(value) for value in diagnostic[measurement_key])
        if not values:
            continue
        center = statistics.median(values)
        nominal = float(
            getattr(format_spec(str(diagnostic["format_id"])).frame, nominal_attr)
        )
        by_nominal[nominal].append(
            {
                "sample_id": str(diagnostic["sample_id"]),
                "frame_count": len(values),
                "source_center_mm": center,
                "absolute_deviation_from_nominal_mm": abs(center - nominal),
            }
        )
    quantile = APERTURE_COMPATIBILITY_SPEC.source_center_deviation_quantile
    groups = []
    for nominal, sources in sorted(by_nominal.items()):
        deviations = tuple(
            float(source["absolute_deviation_from_nominal_mm"])
            for source in sources
        )
        groups.append(
            {
                "nominal_axis_mm": nominal,
                "source_count": len(sources),
                "frame_count": sum(int(source["frame_count"]) for source in sources),
                "source_center_deviation_from_nominal_mm": _distribution(
                    deviations
                ),
                "q95_source_center_deviation_mm": float(
                    np.percentile(deviations, quantile * 100.0)
                ),
            }
        )
    configured = (
        APERTURE_COMPATIBILITY_SPEC.width
        if axis == "width"
        else APERTURE_COMPATIBILITY_SPEC.height
    )
    fit_points = tuple(
        (
            float(group["nominal_axis_mm"]),
            float(group["q95_source_center_deviation_mm"]),
        )
        for group in groups
    )
    fit = None if len(fit_points) < 2 else _fit_mixed_axis_guard(fit_points)
    raw_floor = None if fit is None else fit[0]
    raw_ratio = None if fit is None else fit[1]
    fit_score = None if fit is None else fit[2]
    expected_floor = (
        None
        if raw_floor is None
        else _round_outward(
            raw_floor,
            APERTURE_COMPATIBILITY_SPEC.absolute_rounding_mm,
        )
    )
    expected_ratio = (
        None
        if raw_ratio is None
        else _round_outward(
            raw_ratio,
            APERTURE_COMPATIBILITY_SPEC.relative_rounding_ratio,
        )
    )
    outliers = []
    for nominal, sources in sorted(by_nominal.items()):
        guard = configured.guard_mm(nominal)
        outliers.extend(
            {
                "sample_id": str(source["sample_id"]),
                "nominal_axis_mm": nominal,
                "source_center_mm": float(source["source_center_mm"]),
                "absolute_deviation_from_nominal_mm": float(
                    source["absolute_deviation_from_nominal_mm"]
                ),
                "configured_guard_mm": guard,
            }
            for source in sources
            if float(source["absolute_deviation_from_nominal_mm"]) > guard
        )
    return {
        "source_count": sum(len(values) for values in by_nominal.values()),
        "frame_count": sum(
            int(source["frame_count"])
            for values in by_nominal.values()
            for source in values
        ),
        "nominal_groups": groups,
        "raw_mixed_fit": {
            "absolute_floor_mm": raw_floor,
            "relative_ratio": raw_ratio,
            "total_guard_mm_across_nominal_groups": fit_score,
        },
        "outward_quantized_fit": {
            "absolute_floor_mm": expected_floor,
            "relative_ratio": expected_ratio,
        },
        "configured_guard": {
            "absolute_floor_mm": configured.absolute_floor_mm,
            "relative_ratio": configured.relative_ratio,
        },
        "configured_matches_calibration": (
            expected_floor is not None
            and expected_ratio is not None
            and math.isclose(configured.absolute_floor_mm, expected_floor)
            and math.isclose(configured.relative_ratio, expected_ratio)
        ),
        "source_center_deviation_outlier_count": len(outliers),
        "source_center_deviation_outliers": sorted(
            outliers,
            key=lambda item: (str(item["sample_id"]), float(item["nominal_axis_mm"])),
        ),
    }


def _aperture_compatibility_calibration(
    diagnostics: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    width = _axis_guard_calibration(diagnostics, axis="width")
    height = _axis_guard_calibration(diagnostics, axis="height")
    return {
        "calibration_id": APERTURE_COMPATIBILITY_SPEC.calibration_id,
        "method": (
            "per-source eligible direct Frame median; absolute deviation from "
            "format nominal; q95 by nominal extent; minimum-total mixed guard; "
            "outward quantization"
        ),
        "eligibility": (
            "slot_kind=image; START/END/shared edges directly_visible; at least "
            "one complete eligible Frame per source"
        ),
        "source_center_deviation_quantile": (
            APERTURE_COMPATIBILITY_SPEC.source_center_deviation_quantile
        ),
        "absolute_rounding_mm": APERTURE_COMPATIBILITY_SPEC.absolute_rounding_mm,
        "relative_rounding_ratio": (
            APERTURE_COMPATIBILITY_SPEC.relative_rounding_ratio
        ),
        "width": width,
        "height": height,
        "configured_source_count": (
            APERTURE_COMPATIBILITY_SPEC.development_source_count
        ),
        "configured_frame_count": (
            APERTURE_COMPATIBILITY_SPEC.development_frame_count
        ),
        "configured_counts_match": (
            width["source_count"]
            == height["source_count"]
            == APERTURE_COMPATIBILITY_SPEC.development_source_count
            and width["frame_count"]
            == height["frame_count"]
            == APERTURE_COMPATIBILITY_SPEC.development_frame_count
        ),
        "configured_matches_calibration": (
            bool(width["configured_matches_calibration"])
            and bool(height["configured_matches_calibration"])
        ),
    }


def _physical_format_summary(
    format_id: str,
    diagnostics: Sequence[dict[str, Any]],
    *,
    cohort_sha256: str | None,
    nominal_pitch_diagnostics: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    physical = format_spec(format_id)
    frame = physical.frame
    nominal_ratio = frame.frame_width_mm / frame.frame_height_mm
    width_factor_minimum, width_factor_maximum = frame.width_factor_bounds
    height_factor_minimum, height_factor_maximum = frame.height_factor_bounds
    minimum_ratio = (
        nominal_ratio * width_factor_minimum / height_factor_maximum
    )
    maximum_ratio = (
        nominal_ratio * width_factor_maximum / height_factor_minimum
    )
    frame_ratios = tuple(
        ratio
        for diagnostic in diagnostics
        for ratio in diagnostic["frame_ratio_measurements"]
    )
    source_ratio_centers = tuple(
        statistics.median(diagnostic["frame_ratio_measurements"])
        for diagnostic in diagnostics
        if diagnostic["frame_ratio_measurements"]
    )
    raw_ratio_minimum = min((nominal_ratio, *source_ratio_centers))
    raw_ratio_maximum = max((nominal_ratio, *source_ratio_centers))
    ratio_spec = frame.aperture_aspect_ratio
    registered_raw = (
        None
        if ratio_spec is None
        else (
            ratio_spec.raw_width_over_height_minimum,
            ratio_spec.raw_width_over_height_maximum,
        )
    )
    registered_guarded = (
        None
        if ratio_spec is None
        else ratio_spec.guarded_bounds(
            nominal_width_mm=frame.frame_width_mm,
            nominal_height_mm=frame.frame_height_mm,
        )
    )
    frame_width_containment = tuple(
        contained
        for diagnostic in diagnostics
        for contained in diagnostic["frame_width_prior_containment"]
    )
    frame_height_containment = tuple(
        contained
        for diagnostic in diagnostics
        for contained in diagnostic["frame_height_prior_containment"]
    )
    gap_containment = tuple(
        contained
        for diagnostic in diagnostics
        for contained in diagnostic["separator_gap_prior_containment"]
    )
    pitch_containment = tuple(
        contained
        for diagnostic in diagnostics
        for contained in diagnostic["pitch_prior_containment"]
    )
    corridor_diagnostics = tuple(
        diagnostic["cross_corridor"]
        for diagnostic in diagnostics
        if diagnostic["cross_corridor"]["available"]
    )
    return {
        "source_count": len(diagnostics),
        "scan_canvas_outcome_counts": dict(
            sorted(
                Counter(
                    str(diagnostic["scan_canvas_outcome"])
                    for diagnostic in diagnostics
                ).items()
            )
        ),
        "selected_scan_canvas_profile_counts": dict(
            sorted(
                Counter(
                    str(diagnostic["scan_canvas_profile_id"])
                    for diagnostic in diagnostics
                    if diagnostic["scan_canvas_profile_id"] is not None
                ).items()
            )
        ),
        "scan_canvas_aspect_error_ratio": _distribution(
            diagnostic["scan_canvas_aspect_error_ratio"]
            for diagnostic in diagnostics
        ),
        "scan_canvas_scale_authority_supported_source_count": sum(
            diagnostic["scan_canvas_scale_authority_supported"]
            for diagnostic in diagnostics
        ),
        "axis_guard_implied_design_ratio_interval": {
            "nominal": nominal_ratio,
            "minimum": minimum_ratio,
            "maximum": maximum_ratio,
        },
        "directly_visible_frame_ratio": _distribution(frame_ratios),
        "source_center_frame_ratio": _distribution(source_ratio_centers),
        "aperture_aspect_ratio_calibration": {
            "eligibility": (
                "source median of slot_kind=image Frames whose START/END and "
                "shared edges are directly_visible"
            ),
            "eligible_source_count": len(source_ratio_centers),
            "eligible_frame_count": len(frame_ratios),
            "design_ratio": nominal_ratio,
            "derived_raw_interval": {
                "minimum": raw_ratio_minimum,
                "maximum": raw_ratio_maximum,
            },
            "registered_calibration_id": (
                None if ratio_spec is None else ratio_spec.calibration_id
            ),
            "registered_raw_interval": (
                None
                if registered_raw is None
                else {
                    "minimum": registered_raw[0],
                    "maximum": registered_raw[1],
                }
            ),
            "axis_guard_calibration_id": (
                APERTURE_COMPATIBILITY_SPEC.calibration_id
            ),
            "width_guard_mm": (
                APERTURE_COMPATIBILITY_SPEC.width.guard_mm(
                    frame.frame_width_mm
                )
            ),
            "height_guard_mm": (
                APERTURE_COMPATIBILITY_SPEC.height.guard_mm(
                    frame.frame_height_mm
                )
            ),
            "width_guard_ratio": (
                APERTURE_COMPATIBILITY_SPEC.width.relative_guard(
                    frame.frame_width_mm
                )
            ),
            "height_guard_ratio": (
                APERTURE_COMPATIBILITY_SPEC.height.relative_guard(
                    frame.frame_height_mm
                )
            ),
            "registered_guarded_interval": (
                None
                if registered_guarded is None
                else {
                    "minimum": registered_guarded[0],
                    "maximum": registered_guarded[1],
                }
            ),
            "registered_matches_derived": (
                registered_raw is not None
                and math.isclose(registered_raw[0], raw_ratio_minimum)
                and math.isclose(registered_raw[1], raw_ratio_maximum)
                and ratio_spec.development_source_count
                == len(source_ratio_centers)
                and ratio_spec.development_frame_count == len(frame_ratios)
            ),
        },
        "holder_normalized_dimension_estimate_basis": (
            "gold_native_geometry_divided_by_selected_nominal_holder_axis_scale"
        ),
        "holder_normalized_frame_width_mm": _source_variation_summary(
            diagnostics,
            "holder_normalized_frame_width_estimates_mm",
        ),
        "holder_normalized_frame_height_mm": _source_variation_summary(
            diagnostics,
            "holder_normalized_frame_height_estimates_mm",
        ),
        "frame_width_within_runtime_prior_count": sum(
            frame_width_containment
        ),
        "frame_width_runtime_prior_comparison_count": len(
            frame_width_containment
        ),
        "source_with_frame_width_outside_runtime_prior_count": sum(
            bool(diagnostic["frame_width_prior_containment"])
            and not all(diagnostic["frame_width_prior_containment"])
            for diagnostic in diagnostics
        ),
        "frame_height_within_runtime_prior_count": sum(
            frame_height_containment
        ),
        "frame_height_runtime_prior_comparison_count": len(
            frame_height_containment
        ),
        "source_with_frame_height_outside_runtime_prior_count": sum(
            bool(diagnostic["frame_height_prior_containment"])
            and not all(diagnostic["frame_height_prior_containment"])
            for diagnostic in diagnostics
        ),
        "excluded_frame_count": sum(
            int(diagnostic["excluded_frame_count"])
            for diagnostic in diagnostics
        ),
        "separator_gap_prior_mm": frame.format_gap_prior_mm,
        "holder_normalized_separator_gap_mm": _source_variation_summary(
            diagnostics,
            "holder_normalized_separator_gap_estimates_mm",
        ),
        "separator_gap_within_runtime_prior_count": sum(gap_containment),
        "separator_gap_runtime_prior_comparison_count": len(gap_containment),
        "holder_normalized_pitch_mm": _source_variation_summary(
            diagnostics,
            "holder_normalized_pitch_estimates_mm",
        ),
        "nominal_pitch_calibration": _nominal_pitch_calibration(
            format_id,
            nominal_pitch_diagnostics,
            cohort_sha256=cohort_sha256,
        ),
        "pitch_within_runtime_interval_count": sum(pitch_containment),
        "pitch_runtime_interval_comparison_count": len(pitch_containment),
        "excluded_separator_count": sum(
            int(diagnostic["excluded_separator_count"])
            for diagnostic in diagnostics
        ),
        "compiled_cross_measurement_corridor": {
            "source_count": len(corridor_diagnostics),
            "trace_count": sum(
                int(diagnostic["trace_count"])
                for diagnostic in corridor_diagnostics
            ),
            "source_with_outside_trace_count": sum(
                bool(
                    diagnostic["top_outside_trace_count"]
                    or diagnostic["bottom_outside_trace_count"]
                )
                for diagnostic in corridor_diagnostics
            ),
            "top_outside_trace_count": sum(
                int(diagnostic["top_outside_trace_count"])
                for diagnostic in corridor_diagnostics
            ),
            "bottom_outside_trace_count": sum(
                int(diagnostic["bottom_outside_trace_count"])
                for diagnostic in corridor_diagnostics
            ),
            "maximum_top_outside_px": max(
                (
                    float(diagnostic["maximum_top_outside_px"])
                    for diagnostic in corridor_diagnostics
                ),
                default=None,
            ),
            "maximum_bottom_outside_px": max(
                (
                    float(diagnostic["maximum_bottom_outside_px"])
                    for diagnostic in corridor_diagnostics
                ),
                default=None,
            ),
        },
    }


def _physical_prior_validation(
    records: Sequence[dict[str, Any]],
    *,
    cohort_sha256: str | None,
) -> dict[str, Any]:
    diagnostics = _unique_source_physical_diagnostics(records)
    nominal_pitch_diagnostics = _unique_nominal_pitch_diagnostics(records)
    by_format: dict[str, list[dict[str, Any]]] = defaultdict(list)
    nominal_pitch_by_format: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for diagnostic in diagnostics:
        by_format[str(diagnostic["format_id"])].append(diagnostic)
    for diagnostic in nominal_pitch_diagnostics:
        nominal_pitch_by_format[str(diagnostic["format_id"])].append(
            diagnostic
        )
    return {
        "scope": (
            "unique_source_gold_geometry_against_current_runtime_physical_priors"
        ),
        "source_count": len(diagnostics),
        "analysis_error_source_count": len(
            {
                str(record["source_sha256"])
                for record in records
                if record["physical_prior_diagnostic"].get("analysis_error")
                is not None
            }
        ),
        "format_source_counts": dict(
            sorted(
                (format_id, len(items))
                for format_id, items in by_format.items()
            )
        ),
        "aperture_compatibility_calibration": (
            _aperture_compatibility_calibration(diagnostics)
        ),
        "formats": {
            format_id: _physical_format_summary(
                format_id,
                items,
                cohort_sha256=cohort_sha256,
                nominal_pitch_diagnostics=nominal_pitch_by_format[format_id],
            )
            for format_id, items in sorted(by_format.items())
        },
    }


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
        "physical_prior_validation": _physical_prior_validation(
            records,
            cohort_sha256=identity.get("development_gold_cohort_sha256"),
        ),
        "decision_status_counts": _counter(records, "decision_status"),
        "phase_failure_kind_counts": _counter(
            records,
            "phase_failure_kind",
        ),
        "coarse_enclosing_resolution_state_counts": _counter(
            records,
            "coarse_enclosing_resolution_state",
        ),
        "coarse_enclosing_resolution_failure_kind_counts": _counter(
            records,
            "coarse_enclosing_resolution_failure_kind",
        ),
        "coarse_enclosing_selected_measurement_basis_counts": _counter(
            records,
            "coarse_enclosing_selected_measurement_basis",
        ),
        "coarse_enclosing_candidate_measurement_basis_counts": dict(
            sorted(
                Counter(
                    "+".join(
                        record[
                            "coarse_enclosing_candidate_measurement_bases"
                        ]
                    )
                    or "none"
                    for record in records
                ).items()
            )
        ),
        "lattice_parameter_fit_basis_counts": _counter(
            records,
            "lattice_parameter_fit_basis",
        ),
        "calibrated_nominal_grid_evidence_state_counts": _counter(
            records,
            "calibrated_nominal_grid_evidence_state",
        ),
        "calibrated_nominal_grid_evidence_failure_kind_counts": _counter(
            records,
            "calibrated_nominal_grid_evidence_failure_kind",
        ),
        "calibrated_nominal_grid_authority_state_counts": _counter(
            records,
            "calibrated_nominal_grid_authority_state",
        ),
        "calibrated_nominal_grid_authority_failure_kind_counts": _counter(
            records,
            "calibrated_nominal_grid_authority_failure_kind",
        ),
        "candidate_nominal_grid_solve_count": sum(
            int(record["candidate_nominal_grid_solve_count"])
            for record in records
        ),
        "candidate_nominal_grid_solve_success_count": sum(
            int(record["candidate_nominal_grid_solve_success_count"])
            for record in records
        ),
        "cross_failure_reason_counts": _counter(
            records,
            "cross_failure_reason",
        ),
        "cross_failure_kind_counts": _counter(
            records,
            "cross_failure_kind",
        ),
        "placement_failure_gap_counts": _counter(
            records,
            "placement_failure_gap",
        ),
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
            try:
                physical_prior = _physical_prior_diagnostic(record)
            except Exception as physical_error:
                physical_prior = {
                    "source_sha256": record["source_sha256"],
                    "format_id": record["format_id"],
                    "count": record["count"],
                    "analysis_error": (
                        f"{type(physical_error).__name__}: {physical_error}"
                    ),
                }
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
                "phase_failure_kind": None,
                "coarse_enclosing_resolution_state": None,
                "coarse_enclosing_resolution_failure_kind": None,
                "coarse_enclosing_candidate_measurement_bases": [],
                "coarse_enclosing_selected_measurement_basis": None,
                "lattice_parameter_fit_basis": None,
                "calibrated_nominal_grid_evidence_state": None,
                "calibrated_nominal_grid_evidence_failure_kind": None,
                "calibrated_nominal_grid_authority_state": None,
                "calibrated_nominal_grid_authority_failure_kind": None,
                "candidate_nominal_grid_solve_count": 0,
                "candidate_nominal_grid_solve_success_count": 0,
                "cross_status": None,
                "cross_failure_kind": None,
                "cross_failure_reason": None,
                "placement_failure_gap": None,
                "selected_cross_boundary_use": None,
                "duration_seconds": 0.0,
                "boundary_diagnostics": [],
                "frame_candidate_geometry_diagnostics": [],
                "physical_prior_diagnostic": physical_prior,
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
