"""Compare the four fixed V4.9 performance receipts without rerunning them."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence

from .benchmark_workload import FIXED_SOURCE_COUNT, FIXED_WORKLOAD_COUNT
from .performance import (
    BASELINE_COMMIT,
    BASELINE_TAG,
    PAIRED_ORDERS,
    PERFORMANCE_RESULT_SCHEMA,
    PRODUCTION_JOBS,
    SECONDS_PER_INPUT_LIMIT,
)
from .profile_fixed_sample import PROFILE_RECEIPT_SCHEMA


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OLD_V49_COMMIT = "0fdb90dc40155cb5cfe2a97bee121453ef27f40a"
BASELINE_PAIRED_RELATIVE_PATH = Path(
    "build/v49-orthogonal-budget/baseline/paired/paired_performance_result.json"
)
BASELINE_S062_RELATIVE_PATH = Path(
    "build/v49-orthogonal-budget/baseline/s062/fixed_sample_profile.json"
)
CANDIDATE_PAIRED_RELATIVE_PATH = Path(
    "build/v49-orthogonal-budget/current/paired/paired_performance_result.json"
)
CANDIDATE_S062_RELATIVE_PATH = Path(
    "build/v49-orthogonal-budget/current/s062/fixed_sample_profile.json"
)
BASELINE_PAIRED_SHA256 = (
    "3030014bdc81c0c81a5639d431eb3f7e4a2864ce604ebe4806152086ef4ecbe8"
)
BASELINE_S062_SHA256 = (
    "85707a0516d6373a7c277b6af78bd87f7c64c0eb1cf058da775602b831cd0824"
)
BASELINE_S062_SCHEMA = "x5crop_fixed_sample_profile_v3"
COMPARISON_SCHEMA = "x5crop_performance_comparison_v2"

_CANDIDATE_S062_METRICS = (
    "measurement_query_count",
    "pixel_query_count",
    "basic_profile_coordinate_count",
    "basic_profile_run_count",
    "phase_vote_count",
    "template_group_count",
    "template_role_lookup_count",
    "template_role_match_count",
    "local_relation_evaluation_count",
    "enhanced_query_count",
    "materialized_frame_geometry_count",
    "shared_measurement_reuse_count",
    "domain_pixels",
    "peak_temporary_bytes",
)


@dataclass(frozen=True)
class PerformanceReceipt:
    record: Mapping[str, Any]
    sha256: str


def _load_receipt(path: Path) -> PerformanceReceipt:
    encoded = path.read_bytes()
    record = json.loads(encoded)
    if not isinstance(record, dict):
        raise ValueError(f"performance receipt is not an object: {path}")
    return PerformanceReceipt(
        record=record,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _mad(values: Sequence[float]) -> float:
    median = statistics.median(values)
    return statistics.median(abs(value - median) for value in values)


def _paired_measurements(
    receipt: Mapping[str, Any],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    groups = receipt.get("paired_groups")
    if (
        not isinstance(groups, list)
        or len(groups) != len(PAIRED_ORDERS)
        or tuple(tuple(group.get("order", ())) for group in groups)
        != PAIRED_ORDERS
    ):
        raise ValueError("paired order or group count changed")
    v428: list[float] = []
    v49: list[float] = []
    for group in groups:
        for kind, destination in (("v428", v428), ("v49", v49)):
            run = group.get(kind)
            if not isinstance(run, dict):
                raise ValueError("paired timing record is incomplete")
            if (
                run.get("version_kind") != kind
                or run.get("source_count") != FIXED_SOURCE_COUNT
                or run.get("workload_task_count") != FIXED_WORKLOAD_COUNT
                or run.get("source_decode_count") != FIXED_SOURCE_COUNT
                or run.get("official_product_tiff_count") != 0
            ):
                raise ValueError("paired workload or decode identity changed")
            wall = float(run.get("wall_seconds", 0.0))
            if wall <= 0.0:
                raise ValueError("paired wall timing must be positive")
            destination.append(wall)
    return tuple(v428), tuple(v49)


def _noise_floor(
    v428: tuple[float, ...],
    v49: tuple[float, ...],
) -> float:
    return max(
        0.01,
        _mad(v49) / statistics.median(v49),
        _mad(v428) / statistics.median(v428),
    )


def _validate_paired_identity(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    expected_candidate_commit: str,
) -> None:
    if (
        baseline.get("performance_schema") != PERFORMANCE_RESULT_SCHEMA
        or candidate.get("performance_schema") != PERFORMANCE_RESULT_SCHEMA
        or baseline.get("baseline")
        != {"tag": BASELINE_TAG, "commit": BASELINE_COMMIT}
        or candidate.get("baseline") != baseline.get("baseline")
        or baseline.get("v49_commit") != OLD_V49_COMMIT
        or candidate.get("v49_commit") != expected_candidate_commit
        or len(expected_candidate_commit) != 40
    ):
        raise ValueError("paired commit or schema identity changed")
    fixed_fields = (
        "jobs",
        "source_count",
        "workload_task_count",
        "compression",
        "count_mapping",
        "product_export_policy",
        "status_filtering",
        "identity",
        "environment",
    )
    if any(candidate.get(field) != baseline.get(field) for field in fixed_fields):
        raise ValueError("paired environment, workload, or I/O identity changed")
    if (
        baseline.get("jobs") != PRODUCTION_JOBS
        or baseline.get("source_count") != FIXED_SOURCE_COUNT
        or baseline.get("workload_task_count") != FIXED_WORKLOAD_COUNT
        or baseline.get("status_filtering") is not False
    ):
        raise ValueError("frozen paired receipt identity is invalid")


def _validate_s062_identity(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    expected_candidate_commit: str,
) -> None:
    if (
        baseline.get("schema") != BASELINE_S062_SCHEMA
        or candidate.get("schema") != PROFILE_RECEIPT_SCHEMA
        or candidate.get("v49_commit") != expected_candidate_commit
    ):
        raise ValueError("S062 schema or candidate commit binding changed")
    identity_fields = (
        "sample_id",
        "source_sha256",
        "format_id",
        "strip_mode",
        "count_mode",
        "selected_scan_canvas_profile_id",
        "lane_output_slot_counts",
        "output_slot_count",
        "slot_identities",
    )
    if any(candidate.get(field) != baseline.get(field) for field in identity_fields):
        raise ValueError("S062 sample, format, profile, or slot identity changed")
    metrics = candidate.get("runtime_metrics")
    limits = candidate.get("structural_limits")
    if (
        not isinstance(metrics, dict)
        or tuple(metrics) != _CANDIDATE_S062_METRICS
        or not isinstance(limits, dict)
        or tuple(limits)
        != (
            "template_role_lookup_count",
            "template_role_match_count",
            "local_relation_evaluation_count",
            "enhanced_query_count",
        )
    ):
        raise ValueError("candidate S062 current work schema changed")


def performance_compare(
    baseline_paired_receipt: PerformanceReceipt,
    candidate_paired_receipt: PerformanceReceipt,
    baseline_s062_receipt: PerformanceReceipt,
    candidate_s062_receipt: PerformanceReceipt,
    expected_candidate_commit: str,
) -> dict[str, Any]:
    """Return the one mechanical verdict from the four authoritative inputs."""

    if baseline_paired_receipt.sha256 != BASELINE_PAIRED_SHA256:
        raise ValueError("baseline paired receipt SHA-256 changed")
    if baseline_s062_receipt.sha256 != BASELINE_S062_SHA256:
        raise ValueError("baseline S062 receipt SHA-256 changed")
    baseline_paired = baseline_paired_receipt.record
    candidate_paired = candidate_paired_receipt.record
    baseline_s062 = baseline_s062_receipt.record
    candidate_s062 = candidate_s062_receipt.record
    _validate_paired_identity(
        baseline_paired,
        candidate_paired,
        expected_candidate_commit,
    )
    _validate_s062_identity(
        baseline_s062,
        candidate_s062,
        expected_candidate_commit,
    )
    old_v428, old_v49 = _paired_measurements(baseline_paired)
    new_v428, new_v49 = _paired_measurements(candidate_paired)
    old_ratios = tuple(
        v49 / v428 for v428, v49 in zip(old_v428, old_v49, strict=True)
    )
    new_ratios = tuple(
        v49 / v428 for v428, v49 in zip(new_v428, new_v49, strict=True)
    )
    old_ratio = statistics.median(old_ratios)
    new_ratio = statistics.median(new_ratios)
    old_noise_floor = _noise_floor(old_v428, old_v49)
    new_noise_floor = _noise_floor(new_v428, new_v49)
    allowed_regression = max(0.01, old_noise_floor)
    regression = new_ratio / old_ratio - 1.0
    new_v49_median_seconds_per_input = (
        statistics.median(new_v49) / FIXED_SOURCE_COUNT
    )
    new_relative_median = statistics.median(
        ratio - 1.0 for ratio in new_ratios
    )

    baseline_metrics = baseline_s062.get("runtime_metrics")
    candidate_metrics = candidate_s062.get("runtime_metrics")
    if not isinstance(baseline_metrics, dict) or not isinstance(
        candidate_metrics, dict
    ):
        raise ValueError("S062 runtime metrics are unavailable")
    directly_comparable_non_growth_fields = (
        "measurement_query_count",
        "pixel_query_count",
    )
    metric_checks = {
        field: int(candidate_metrics[field]) <= int(baseline_metrics[field])
        for field in directly_comparable_non_growth_fields
    }
    reuse_not_reduced = int(
        candidate_metrics["shared_measurement_reuse_count"]
    ) >= int(baseline_metrics["shared_measurement_reuse_count"])
    baseline_domain_pixels = int(baseline_metrics["domain_pixels"])
    candidate_domain_pixels = int(candidate_metrics["domain_pixels"])
    domain_identity = candidate_domain_pixels == baseline_domain_pixels
    memory_limit = candidate_domain_pixels * 10 + 32 * 1024 * 1024
    memory_within_limit = (
        int(candidate_metrics["peak_temporary_bytes"]) <= memory_limit
    )
    structural_limits = candidate_s062["structural_limits"]
    structural_work_bounded = all(
        int(candidate_metrics[field]) <= int(structural_limits[field])
        for field in structural_limits
    )
    checks = {
        "new_noise_floor_valid": new_noise_floor <= allowed_regression,
        "normalized_regression_within_limit": regression <= allowed_regression,
        "new_v49_absolute_limit": (
            new_v49_median_seconds_per_input <= SECONDS_PER_INPUT_LIMIT
        ),
        "new_v49_beats_v428_noise": new_relative_median < -new_noise_floor,
        **{
            f"s062_{field}_not_increased": passed
            for field, passed in metric_checks.items()
        },
        "s062_measurement_reuse_not_reduced": reuse_not_reduced,
        "s062_domain_pixels_identical": domain_identity,
        "s062_peak_temporary_bytes_within_limit": memory_within_limit,
        "s062_template_work_structurally_bounded": structural_work_bounded,
    }
    return {
        "comparison_schema": COMPARISON_SCHEMA,
        "expected_candidate_commit": expected_candidate_commit,
        "input_sha256": {
            "baseline_paired": baseline_paired_receipt.sha256,
            "candidate_paired": candidate_paired_receipt.sha256,
            "baseline_s062": baseline_s062_receipt.sha256,
            "candidate_s062": candidate_s062_receipt.sha256,
        },
        "old_ratio": old_ratio,
        "new_ratio": new_ratio,
        "old_noise_floor": old_noise_floor,
        "new_noise_floor": new_noise_floor,
        "allowed_regression": allowed_regression,
        "regression": regression,
        "new_v49_median_seconds_per_input": new_v49_median_seconds_per_input,
        "new_v49_relative_median": new_relative_median,
        "s062_memory_limit_bytes": memory_limit,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-paired", type=Path, required=True)
    parser.add_argument("--candidate-paired", type=Path, required=True)
    parser.add_argument("--baseline-s062", type=Path, required=True)
    parser.add_argument("--candidate-s062", type=Path, required=True)
    parser.add_argument("--expected-candidate-commit", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = (
        args.baseline_paired,
        args.candidate_paired,
        args.baseline_s062,
        args.candidate_s062,
    )
    comparison = performance_compare(
        *(_load_receipt(path.resolve()) for path in paths),
        args.expected_candidate_commit,
    )
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        audit = {
            **comparison,
            "input_paths": [
                str(path.resolve().relative_to(PROJECT_ROOT))
                for path in paths
            ],
        }
        output.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        f"normalized regression: {comparison['regression']:.3%}; "
        f"allowed {comparison['allowed_regression']:.3%}"
    )
    print(
        "performance comparison: PASS"
        if comparison["passed"]
        else "performance comparison: FAIL"
    )
    return 0 if comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
