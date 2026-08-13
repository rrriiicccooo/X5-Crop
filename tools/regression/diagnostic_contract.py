"""Bounded-work checks owned by the external diagnostic verifier."""

from __future__ import annotations

import math
from typing import Any, Sequence


MAXIMUM_PEAK_TEMPORARY_BYTES_PER_SOURCE_PIXEL = 10
MAXIMUM_PEAK_TEMPORARY_FIXED_ALLOWANCE_BYTES = 32 * 1024 * 1024
WORK_FIELDS = (
    "measurement_query_count",
    "pixel_query_count",
    "basic_profile_coordinate_count",
    "basic_profile_run_count",
    "role_proposal_count",
    "phase_hypothesis_count",
    "sequence_group_count",
    "ordinal_role_lookup_count",
    "ordinal_role_match_count",
    "local_relation_evaluation_count",
    "materialized_frame_geometry_count",
    "shared_measurement_reuse_count",
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
        int(row["ordinal_role_lookup_count"])
        <= int(row["phase_hypothesis_count"]) * count * 2
        and int(row["ordinal_role_match_count"])
        <= int(row["phase_hypothesis_count"])
        * int(row["role_proposal_count"])
        and int(row["local_relation_evaluation_count"])
        <= int(row["sequence_group_count"]) * max(0, count - 1)
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
