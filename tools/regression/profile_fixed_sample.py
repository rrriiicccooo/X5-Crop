"""Profile the frozen real-TIFF source-coordinate geometry sample."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import subprocess
import time
from typing import Any, Sequence

from x5crop.runtime.bootstrap import runtime_invocation_from_options
from x5crop.runtime.options import RuntimeOptions
from x5crop.runtime.outcome import CompletedInput, FailedInput
from x5crop.runtime.workflow import process_one

from .benchmark_workload import load_performance_sources


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXED_SAMPLE_ID = "S062"
FIXED_SOURCE_SHA256 = (
    "ed1e0aba8b78a8619ffe0cc14b855fdd87ebcc92f4c8c137da3fef8f7192a7f6"
)
FIXED_FORMAT_ID = "120-66"
FIXED_STRIP_MODE = "partial"
FIXED_COUNT_MODE = "auto"
PROFILE_RECEIPT_SCHEMA = "x5crop_fixed_sample_profile_v5"

_CURRENT_RUNTIME_METRICS = (
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


def _clean_head() -> str:
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    if status:
        raise ValueError("formal S062 profile requires a clean committed tree")
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixed_source() -> Path:
    matches = tuple(
        source
        for source in load_performance_sources()
        if source.sample_id == FIXED_SAMPLE_ID
    )
    if len(matches) != 1:
        raise ValueError("fixed profiling sample is not unique in the cohort")
    identity = matches[0]
    if (
        identity.source_sha256 != FIXED_SOURCE_SHA256
        or identity.strip_mode != FIXED_STRIP_MODE
        or identity.format_id != FIXED_FORMAT_ID
    ):
        raise ValueError("fixed profiling identity changed")
    source = identity.source_path
    if not source.is_file() or _sha256(source) != FIXED_SOURCE_SHA256:
        raise ValueError("fixed profiling source SHA cannot be resolved")
    return source


def _hotspots(profile: cProfile.Profile) -> list[dict[str, Any]]:
    statistics = pstats.Stats(profile)
    rows = []
    for (filename, line, function), values in statistics.stats.items():
        primitive_calls, total_calls, total_time, cumulative_time, _callers = (
            values
        )
        rows.append(
            {
                "file": filename,
                "line": int(line),
                "function": function,
                "primitive_calls": int(primitive_calls),
                "total_calls": int(total_calls),
                "self_seconds": float(total_time),
                "cumulative_seconds": float(cumulative_time),
            }
        )
    rows.sort(
        key=lambda item: (
            -item["cumulative_seconds"],
            -item["self_seconds"],
            item["file"],
            item["line"],
        )
    )
    return rows[:20]


def run_fixed_profile(
    output_root: Path,
) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"profile output root must be empty: {output_root}")
    v49_commit = _clean_head()
    output_root.mkdir(parents=True, exist_ok=True)
    source = _fixed_source()
    invocation = runtime_invocation_from_options(
        RuntimeOptions(
            input_path=source,
            output_dir=output_root,
            format_id=FIXED_FORMAT_ID,
            layout="vertical",
            strip_mode=FIXED_STRIP_MODE,
            requested_count=None,
            page=0,
            review_dir=None,
            copy_review_files=False,
            compression="same",
            debug_analysis=False,
            diagnostics=True,
            overwrite=False,
            report=True,
            debug_errors=True,
            jobs=1,
        )
    )
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    outcome = process_one(
        invocation.files[0],
        invocation.config,
        invocation.configuration_bundle,
    )
    profiler.disable()
    wall_seconds = time.perf_counter() - started
    profiler.dump_stats(output_root / "fixed_sample.prof")
    if isinstance(outcome, FailedInput):
        raise RuntimeError(
            f"fixed sample failed at {outcome.failure_stage.value}: "
            f"{outcome.error_message}"
        )
    if not isinstance(outcome, CompletedInput):
        raise TypeError("unknown fixed-sample runtime outcome")
    record = outcome.result.record
    output_identity = record["analysis_identity"]["output_identity"]
    resolved = output_identity["resolved_output_slots"]
    lane_counts = (
        ()
        if resolved is None
        else tuple(resolved["lane_output_slot_counts"])
    )
    output_slot_count = output_identity["output_slot_count"]
    if (
        lane_counts != (3,)
        or output_slot_count != 3
        or outcome.artifacts.frame_outputs
    ):
        raise RuntimeError("fixed profiling workload identity changed")
    work_rows = tuple(
        lane["work"]
        for lane in record["photo_geometry"]["lanes"]
    )
    metrics = outcome.metrics.as_record()
    current_metrics = {
        field: int(metrics[field])
        for field in _CURRENT_RUNTIME_METRICS
    }
    role_lookup_limit = sum(
        int(row["template_group_count"]) * count * 2
        for row, count in zip(work_rows, lane_counts, strict=True)
    )
    local_relation_limit = sum(
        int(row["template_group_count"]) * max(0, count - 1)
        for row, count in zip(work_rows, lane_counts, strict=True)
    )
    selected_aperture_labels: list[str] = []
    for lane in record["photo_geometry"]["lanes"]:
        placement = lane["placement"]
        canonical_id = placement["canonical_placement_id"]
        if canonical_id is None:
            selected_aperture_labels.append("")
            continue
        selected_aperture_labels.append(
            next(
                item["component"]["component_id"]
                for item in placement["retained_placements"]
                if item["placement_id"] == canonical_id
            )
        )
    receipt = {
        "schema": PROFILE_RECEIPT_SCHEMA,
        "v49_commit": v49_commit,
        "sample_id": FIXED_SAMPLE_ID,
        "source_sha256": FIXED_SOURCE_SHA256,
        "format_id": FIXED_FORMAT_ID,
        "strip_mode": FIXED_STRIP_MODE,
        "count_mode": FIXED_COUNT_MODE,
        "selected_scan_canvas_profile_id": output_identity[
            "selected_scan_canvas_profile_id"
        ],
        "lane_output_slot_counts": list(lane_counts),
        "output_slot_count": output_slot_count,
        "slot_identities": output_identity["slot_identities"],
        "wall_seconds": wall_seconds,
        "runtime_metrics": current_metrics,
        "structural_limits": {
            "template_role_lookup_count": role_lookup_limit,
            "template_role_match_count": current_metrics[
                "phase_vote_count"
            ],
            "local_relation_evaluation_count": local_relation_limit,
            "enhanced_query_count": current_metrics["phase_vote_count"],
        },
        "selected_aperture_labels": selected_aperture_labels,
        "decision_status": record["decision"]["status"],
        "call_stack_hotspots": _hotspots(profiler),
        "sample_identity_frozen_before_measurement": True,
    }
    (output_root / "fixed_sample_profile.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = run_fixed_profile(
        args.output_root.expanduser().resolve(),
    )
    print(
        f"{FIXED_SAMPLE_ID}: {receipt['wall_seconds']:.3f}s, "
        f"output_slot_count={receipt['output_slot_count']}"
    )
    print(f"artifacts: {args.output_root.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
