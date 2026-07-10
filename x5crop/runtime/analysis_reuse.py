from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..app_info import REPORT_JSONL_NAME, SCRIPT_NAME, VERSION
from ..domain import Box, ImageProfile, ProcessResult
from ..export.crops import write_crops
from ..output.surface import OutputSurface
from ..image.gray import BaseGrayParameters, make_base_gray_u8
from ..image.transforms import rotate_array_expand
from ..io.tiff import read_tiff
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..policies.runtime.policy import DetectionPolicy
from ..report.identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from ..report.result_builder import result_from_cached_record
from ..utils import box_from_dict
from ..run_config import RunConfig


_REPORT_RECORD_CACHE: dict[Path, tuple[int, int, list[dict[str, Any]]]] = {}


def source_cache_signature(input_file: Path, profile: ImageProfile, page_index: int) -> dict[str, Any]:
    stat = input_file.stat()
    return {
        "name": input_file.name,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "page": int(page_index),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "axes": profile.axes,
        "photometric": profile.photometric,
    }


def config_cache_signature(config: RunConfig) -> dict[str, Any]:
    return {
        "format_id": config.format_id,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "requested_count": (
            None if config.requested_count is None else int(config.requested_count)
        ),
        "page": int(config.page),
        "deskew": config.deskew,
        "deskew_fallback": config.deskew_fallback,
        "deskew_min_angle": float(config.deskew_min_angle),
        "deskew_max_angle": float(config.deskew_max_angle),
        "confidence_threshold": float(config.confidence_threshold),
        "bleed_x": int(config.bleed_x),
        "bleed_y": int(config.bleed_y),
    }


def analysis_policy_fingerprint(policy: DetectionPolicy) -> str:
    payload = json.dumps(
        asdict(policy),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def make_analysis_cache_metadata(
    input_file: Path,
    profile: ImageProfile,
    config: RunConfig,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
        "policy_fingerprint": analysis_policy_fingerprint(policy),
    }


def final_frame_boxes_from_record(record: dict[str, Any]) -> list[Box]:
    return [box_from_dict(box) for box in record["frame_boxes"]]


def cached_record_matches(
    record: dict[str, Any],
    input_file: Path,
    profile: ImageProfile,
    config: RunConfig,
    policy: DetectionPolicy,
) -> bool:
    if record.get("schema_id") != REPORT_SCHEMA_ID:
        return False
    if record.get("schema_revision") != REPORT_SCHEMA_REVISION:
        return False
    required_schema_keys = (
        "source",
        "script_version",
        "format_id",
        "layout",
        "strip_mode",
        "count",
        "status",
        "confidence",
        "final_review_reasons",
        "outer_box",
        "frame_boxes",
        "gaps",
        "candidate_gate",
        "decision_gate",
        "decision_signals",
        "evidence_summary",
        "policy_id",
        "schema_validation",
        "output",
        "detail",
    )
    if any(key not in record for key in required_schema_keys):
        return False
    if not isinstance(record["gaps"], list):
        return False
    required_gap_keys = {"index", "center", "score", "method", "start", "end", "lane_box"}
    if any(
        not isinstance(gap, dict) or not required_gap_keys.issubset(gap)
        for gap in record["gaps"]
    ):
        return False
    if record["script_version"] != VERSION:
        return False
    if record["schema_validation"]:
        return False
    detail = record["detail"]
    if not isinstance(detail, dict):
        return False
    decision_summary = detail.get("decision_summary")
    if not isinstance(decision_summary, dict) or not isinstance(decision_summary.get("decision_gate"), dict):
        return False
    if not isinstance(detail.get("output_geometry"), dict):
        return False
    if not isinstance(detail.get("decision_geometry"), dict):
        return False
    if not isinstance(detail.get("exposure_overlap_evidence"), dict):
        return False
    if not isinstance(detail.get("output_protection_plan"), dict):
        return False
    deskew_detail = detail.get("deskew")
    if not isinstance(deskew_detail, dict) or "applied" not in deskew_detail:
        return False
    if bool(deskew_detail["applied"]) and "angle" not in deskew_detail:
        return False
    output = record["output"]
    if not isinstance(output, dict):
        return False
    if any(key not in output for key in ("output_files", "review_copy", "warnings")):
        return False
    cache = detail.get("analysis_cache")
    if not isinstance(cache, dict):
        return False
    if cache.get("script") != SCRIPT_NAME or cache.get("script_version") != VERSION:
        return False
    if cache.get("policy_fingerprint") != analysis_policy_fingerprint(policy):
        return False
    expected_source = source_cache_signature(input_file, profile, config.page)
    expected_config = config_cache_signature(config)
    if cache.get("source") != expected_source:
        return False
    cached_config = cache.get("config")
    if not isinstance(cached_config, dict):
        return False
    if cached_config != expected_config:
        return False
    return str(record["status"]) in {"approved_auto", "needs_review"}


def load_report_records(report_path: Path) -> list[dict[str, Any]]:
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return []
    cached = _REPORT_RECORD_CACHE.get(report_path)
    signature = (int(stat.st_size), int(stat.st_mtime_ns))
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]
    try:
        lines = report_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    _REPORT_RECORD_CACHE[report_path] = (signature[0], signature[1], records)
    return records


def find_reusable_analysis(
    input_file: Path,
    output_dir: Path,
    profile: ImageProfile,
    config: RunConfig,
    policy: DetectionPolicy,
) -> Optional[dict[str, Any]]:
    report_path = output_dir / REPORT_JSONL_NAME
    for record in load_report_records(report_path):
        if not cached_record_matches(record, input_file, profile, config, policy):
            continue
        if Path(str(record["source"])).name == input_file.name:
            return record
    return None


def apply_cached_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    axes: str,
    photometric: str,
    base_gray_params: BaseGrayParameters,
    detail: dict[str, Any],
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, bool]:
    deskew_detail = detail["deskew"]
    if not bool(deskew_detail["applied"]):
        return arr, gray, False
    angle = float(deskew_detail["angle"])
    arr = rotate_array_expand(arr, -angle, axes)
    gray = make_base_gray_u8(arr, axes, photometric, base_gray_params)
    warnings.append(f"reused deskew: {-angle:.4f} degrees")
    return arr, gray, True


def result_from_reusable_analysis(
    input_file: Path,
    config: RunConfig,
    output_surface: OutputSurface,
    profile: ImageProfile,
    warnings: list[str],
    policy_bundle: DetectionPolicyBundle,
) -> ProcessResult | None:
    if not (config.reuse_analysis and not config.dry_run and not config.debug_analysis):
        return None
    cached_record = find_reusable_analysis(
        input_file,
        output_surface.root,
        profile,
        config,
        policy_bundle.initial_policy,
    )
    if cached_record is None:
        return None

    status = str(cached_record["status"])
    warnings.append(f"reused analysis report: {REPORT_JSONL_NAME}")
    if status == "needs_review":
        warnings.append("cached status is needs_review; skipped export")
        return result_from_cached_record(
            input_file,
            cached_record,
            profile,
            warnings,
            output_files=[],
            detail_extra={"reused_analysis": True},
        )

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    policy = policy_bundle.policy_for(str(cached_record["format_id"]), str(cached_record["strip_mode"]))
    gray = make_base_gray_u8(arr, profile.axes, profile.photometric, policy.preprocess.base_gray)
    warnings.extend(warning for warning in page_warnings if warning not in warnings)
    source_arr = arr
    arr, gray, deskew_applied = apply_cached_deskew(
        arr,
        gray,
        profile.axes,
        profile.photometric,
        policy.preprocess.base_gray,
        cached_record["detail"],
        warnings,
    )
    output_files = write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        final_frame_boxes_from_record(cached_record),
        config,
        deskew_applied,
        output_surface.ensure_root(),
    )
    return result_from_cached_record(
        input_file,
        cached_record,
        profile,
        warnings,
        output_files=output_files,
        detail_extra={"reused_analysis": True},
    )
