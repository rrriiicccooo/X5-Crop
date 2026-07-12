from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np

from ..app_info import REPORT_JSONL_NAME, SCRIPT_NAME, VERSION
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..domain import (
    ImageProfile,
    ProcessResult,
)
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..output.surface import OutputSurface
from ..image.gray import BaseGrayParameters, make_base_gray_u8
from ..image.transforms import rotate_array_expand
from ..io.tiff import read_tiff
from ..configuration.bundle import DetectionConfigurationBundle
from ..configuration.model import DetectionConfiguration
from ..report.restoration import (
    final_detection_from_record as _final_detection_from_record,
    transform_geometry_from_record as _transform_geometry_from_record,
)
from ..report.validation import current_report_record_errors
from ..report.result_builder import result_from_cached_record
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
        "bleed_x": int(config.bleed_x),
        "bleed_y": int(config.bleed_y),
    }


def analysis_configuration_fingerprint(configuration: DetectionConfiguration) -> str:
    analysis_configuration = asdict(configuration)
    del analysis_configuration["diagnostics"]
    payload = json.dumps(
        analysis_configuration,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def make_analysis_reuse_signature(
    input_file: Path,
    profile: ImageProfile,
    config: RunConfig,
    configuration: DetectionConfiguration,
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
        "configuration_fingerprint": analysis_configuration_fingerprint(configuration),
    }


def cached_record_matches(
    record: dict[str, Any],
    input_file: Path,
    profile: ImageProfile,
    config: RunConfig,
    configuration: DetectionConfiguration,
) -> bool:
    if current_report_record_errors(record):
        return False
    if record["script_version"] != VERSION:
        return False
    cache = record["analysis_reuse_signature"]
    if not isinstance(cache, dict):
        return False
    if cache.get("script") != SCRIPT_NAME or cache.get("script_version") != VERSION:
        return False
    if cache.get("configuration_fingerprint") != analysis_configuration_fingerprint(configuration):
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
    return str(record["decision"]["status"]) in {
        "approved_auto",
        "needs_review",
    }


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
    configuration: DetectionConfiguration,
) -> dict[str, Any] | None:
    report_path = output_dir / REPORT_JSONL_NAME
    for record in load_report_records(report_path):
        if not cached_record_matches(record, input_file, profile, config, configuration):
            continue
        if Path(str(record["source"])).name == input_file.name:
            return record
    return None


def apply_cached_transform(
    arr: np.ndarray,
    gray: np.ndarray,
    axes: str,
    photometric: str,
    base_gray_params: BaseGrayParameters,
    transform_geometry: TransformGeometryEvidence,
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, bool]:
    if not transform_geometry.applied:
        return arr, gray, False
    angle = float(transform_geometry.applied_angle_degrees)
    arr = rotate_array_expand(arr, angle, axes)
    gray = make_base_gray_u8(arr, axes, photometric, base_gray_params)
    warnings.append(f"reused deskew: {angle:.4f} degrees")
    return arr, gray, True


def result_from_reusable_analysis(
    input_file: Path,
    config: RunConfig,
    output_surface: OutputSurface,
    profile: ImageProfile,
    warnings: list[str],
    configuration_bundle: DetectionConfigurationBundle,
) -> ProcessResult | None:
    if not (config.reuse_analysis and not config.dry_run and not config.debug_analysis):
        return None
    cached_record = find_reusable_analysis(
        input_file,
        output_surface.root,
        profile,
        config,
        configuration_bundle.initial_configuration,
    )
    if cached_record is None:
        return None

    detection = _final_detection_from_record(cached_record)
    warnings.append(f"reused analysis report: {REPORT_JSONL_NAME}")
    review_copy = copy_for_review_if_needed(
        input_file,
        output_surface.root,
        config,
        detection,
        warnings,
    )
    if detection.status == "needs_review" and not config.export_review:
        warnings.append("cached status is needs_review; crop export not requested")
        return result_from_cached_record(
            input_file,
            cached_record,
            profile,
            warnings,
            output_files=[],
            review_copy=review_copy,
        )

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    configuration = configuration_bundle.initial_configuration
    gray = make_base_gray_u8(
        arr,
        profile.axes,
        profile.photometric,
        configuration.preprocess.base_gray,
    )
    warnings.extend(warning for warning in page_warnings if warning not in warnings)
    source_arr = arr
    transform_geometry = _transform_geometry_from_record(cached_record)
    arr, gray, deskew_applied = apply_cached_transform(
        arr,
        gray,
        profile.axes,
        profile.photometric,
        configuration.preprocess.base_gray,
        transform_geometry,
        warnings,
    )
    output_files = write_crops_if_allowed(
        input_file,
        arr,
        source_arr,
        profile,
        detection,
        config,
        deskew_applied,
        output_surface,
    )
    return result_from_cached_record(
        input_file,
        cached_record,
        profile,
        warnings,
        output_files=output_files,
        review_copy=review_copy,
    )
