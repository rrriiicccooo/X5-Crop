"""Bounded-work checks owned by the external diagnostic verifier."""

from __future__ import annotations

import math
from typing import Any, Sequence

from x5crop.detection.photo_geometry.template_model import (
    MAX_TEMPLATE_FIT_PASSES,
)
from x5crop.detection.photo_geometry.template_measurement_plan_model import (
    MAX_PHASE_OBSERVATIONS,
)


MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL = 10
MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES = 32 * 1024 * 1024
WORK_FIELDS = (
    "measurement_query_count",
    "pixel_query_count",
    "basic_profile_coordinate_count",
    "basic_profile_run_count",
    "registered_sequence_observation_count",
    "phase_hypothesis_count",
    "separator_lattice_hypothesis_count",
    "phase_fit_pass_count",
    "phase_role_lookup_count",
    "phase_role_binding_count",
    "local_relation_evaluation_count",
    "local_refinement_lookup_count",
    "local_refinement_binding_count",
    "cross_registered_run_count",
    "cross_fit_evaluation_count",
    "placement_evaluation_count",
    "boundary_evaluation_count",
    "content_evaluation_count",
    "domain_pixels",
    "peak_temporary_bytes",
)


def aggregate_work(work_rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        field: (
            max((int(row[field]) for row in work_rows), default=0)
            if field == "peak_temporary_bytes"
            else sum(int(row[field]) for row in work_rows)
        )
        for field in WORK_FIELDS
    }


def peak_temporary_limit_bytes(source_pixels: int) -> int:
    if source_pixels <= 0:
        raise ValueError("source memory bound requires positive pixels")
    return (
        source_pixels * MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL
        + MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES
    )


def bounded_work(
    report: dict[str, Any],
    *,
    source_pixels: int,
) -> bool:
    geometry = report["photo_geometry"]
    resolved = geometry["resolved_output_slots"]
    lane_counts = (
        tuple(0 for _ in geometry["lanes"])
        if resolved is None
        else tuple(resolved["lane_output_slot_counts"])
    )
    work_rows = tuple(
        lane["work"] for lane in report["development"]["lanes"]
    )
    metrics = aggregate_work(work_rows)
    aggregate_identity = all(
        int(metrics[field]) == sum(int(row[field]) for row in work_rows)
        for field in WORK_FIELDS
        if field not in {"domain_pixels", "peak_temporary_bytes"}
    )
    structural_bounds = all(
        1
        <= int(row["phase_fit_pass_count"])
        <= MAX_TEMPLATE_FIT_PASSES
        and int(row["phase_role_lookup_count"])
        <= int(row["phase_hypothesis_count"])
        and int(row["phase_role_binding_count"])
        <= int(row["phase_hypothesis_count"]) * count * 2
        and int(row["separator_lattice_hypothesis_count"])
        <= MAX_PHASE_OBSERVATIONS * max(6, count * 2) * 2
        and int(row["local_relation_evaluation_count"])
        <= max(0, count - 1) * int(row["phase_fit_pass_count"])
        and int(row["local_refinement_lookup_count"])
        <= MAX_PHASE_OBSERVATIONS * count * 2 * int(row["phase_fit_pass_count"])
        and int(row["local_refinement_binding_count"])
        <= count * 2 * int(row["phase_fit_pass_count"])
        and int(row["placement_evaluation_count"]) <= 2
        and int(row["boundary_evaluation_count"])
        <= int(row["placement_evaluation_count"]) * count * 4
        and int(row["content_evaluation_count"]) <= 1
        for row, count in zip(work_rows, lane_counts, strict=True)
    )
    return (
        all(
            isinstance(metrics[key], (int, float))
            and math.isfinite(float(metrics[key]))
            and float(metrics[key]) >= 0.0
            for key in metrics
        )
        and aggregate_identity
        and structural_bounds
        and metrics["pixel_query_count"] <= source_pixels * 128
        and metrics["peak_temporary_bytes"]
        <= peak_temporary_limit_bytes(source_pixels)
    )
