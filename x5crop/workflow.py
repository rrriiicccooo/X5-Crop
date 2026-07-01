from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from .analysis_reuse import (
    apply_cached_deskew,
    detection_from_record,
    find_reusable_analysis,
    make_analysis_cache_metadata,
)
from .app_info import REPORT_JSONL_NAME
from .config import Config
from .detection.pipeline import choose_detection
from .detection.finalizer import finalize_detection
from .debug.render import write_debug_analysis, write_debug_preview
from .domain import Detection, ImageProfile, ProcessResult
from .export import (
    copy_for_review,
    display_generated_path,
    output_directory_for,
    review_directory_for,
    write_crops,
)
from .formats import FormatSpec, FORMATS
from .analysis_cache import make_analysis_cache
from .detection.final_geometry import (
    detection_geometry_config,
    output_bleed_config_for_detection,
    reapply_cached_output_bleed,
)
from .geometry.layout import (
    work_gray,
)
from .image.deskew import choose_deskew_angle, rotate_array_expand
from .image.evidence import make_gray_u8
from .io import read_tiff, read_tiff_profile
from .policies.parameters import format_parameters
from .policies.registry import get_detection_policy
from .report_outputs import write_report_outputs_for_result
from .result_builder import result_from_cached_record, result_from_detection
from .source_config import config_for_profile
from .utils import clamp_float


def process_one_worker(input_file: Path, config: Config) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: Config) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    cached_result = _result_from_reusable_analysis(input_file, config, output_dir, profile, warnings)
    if cached_result is not None:
        return _finish_result(cached_result, config)

    arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
    _extend_unique(warnings, page_warnings)
    source_arr = arr
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    arr, gray, deskew_detail = _apply_deskew(arr, gray, profile, config, fmt, warnings)
    analysis_cache = make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    detection_config = detection_geometry_config(config, policy.output)
    detection = choose_detection(gray, detection_config, fmt, analysis_cache)
    finalization = finalize_detection(
        gray,
        detection,
        config,
        fmt,
        analysis_cache,
        deskew_detail,
    )
    detection = finalization.detection
    status = finalization.status

    review_copy = _copy_for_review_if_needed(input_file, output_dir, config, detection, status, warnings)
    output_files = _write_crops_if_allowed(
        input_file,
        arr,
        source_arr,
        profile,
        page,
        detection,
        config,
        bool(deskew_detail["applied"]),
        output_dir,
        status,
    )
    _write_debug_outputs(gray, detection, output_dir, input_file.stem, config, analysis_cache, warnings)

    result = result_from_detection(
        input_file,
        detection,
        profile,
        status,
        output_files,
        review_copy,
        warnings,
        detail_extra={
            "deskew": deskew_detail,
            "analysis_cache": make_analysis_cache_metadata(input_file, profile, config),
        },
    )
    return _finish_result(result, config)


def _result_from_reusable_analysis(
    input_file: Path,
    config: Config,
    output_dir: Path,
    profile: ImageProfile,
    warnings: list[str],
) -> ProcessResult | None:
    if not (config.reuse_analysis and not config.dry_run and not config.debug_analysis):
        return None
    cached_record = find_reusable_analysis(input_file, output_dir, profile, config)
    if cached_record is None:
        return None

    status = str(cached_record["status"])
    warnings.append(f"reused analysis report: {REPORT_JSONL_NAME}")
    if status == "needs_review":
        warnings.append("cached status is needs_review; skipped export")
        return result_from_cached_record(input_file, cached_record, profile, warnings)

    arr, gray, profile, page_warnings, page = read_tiff(input_file, config.page)
    _extend_unique(warnings, page_warnings)
    source_arr = arr
    detection = detection_from_record(cached_record)
    arr, gray, deskew_applied = apply_cached_deskew(
        arr,
        gray,
        profile.axes,
        profile.photometric,
        detection.detail,
        warnings,
    )
    reapply_cached_output_bleed(detection, config, gray.shape[1], gray.shape[0])
    policy = get_detection_policy(detection.film_format, detection.strip_mode)
    output_config = output_bleed_config_for_detection(config, detection, policy.output)
    reapply_cached_output_bleed(detection, output_config, gray.shape[1], gray.shape[0])
    output_files = write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        page,
        detection,
        config,
        deskew_applied,
        output_dir,
    )
    return result_from_detection(
        input_file,
        detection,
        profile,
        status,
        output_files,
        cached_record.get("review_copy"),
        warnings,
        detail_extra={"reused_analysis": True},
    )


def _apply_deskew(
    arr: Any,
    gray: Any,
    profile: ImageProfile,
    config: Config,
    fmt: FormatSpec,
    warnings: list[str],
) -> tuple[Any, Any, dict[str, Any]]:
    tuning = format_parameters(fmt.name)
    deskew_detail: dict[str, Any] = {"applied": False}
    if config.deskew == "off":
        return arr, gray, deskew_detail

    angle, angle_detail = choose_deskew_angle(gray, config.layout, config.analysis, fmt.name)
    deskew_detail.update(angle_detail)
    deskew_detail["angle"] = angle
    deskew_work_width = float(work_gray(gray, config.layout).shape[1])
    deskew_span = abs(math.tan(math.radians(angle)) * deskew_work_width)
    deskew_span_threshold = clamp_float(
        deskew_work_width * tuning.deskew_span_skip_ratio,
        tuning.deskew_span_skip_min,
        tuning.deskew_span_skip_max,
    )
    deskew_detail["span_px"] = deskew_span
    deskew_detail["span_threshold_px"] = deskew_span_threshold
    if deskew_span < deskew_span_threshold:
        deskew_detail["skipped"] = "span_below_threshold"
    elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
        arr = rotate_array_expand(arr, -angle, profile.axes)
        gray = make_gray_u8(arr, profile.axes, profile.photometric)
        deskew_detail["applied"] = True
        warnings.append(f"deskew applied: {-angle:.4f} degrees")
    else:
        deskew_detail["skipped"] = "angle_out_of_range"
    return arr, gray, deskew_detail


def _copy_for_review_if_needed(
    input_file: Path,
    output_dir: Path,
    config: Config,
    detection: Detection,
    status: str,
    warnings: list[str],
) -> str | None:
    if status != "needs_review":
        return None
    warnings.append(
        f"low confidence: {detection.confidence:.3f} < {config.confidence_threshold:.3f}; "
        f"reasons={','.join(detection.review_reasons)}"
    )
    if not config.copy_review_files:
        return None
    review_copy = str(copy_for_review(input_file, review_directory_for(output_dir, config)))
    warnings.append(f"review copy: {review_copy}")
    return review_copy


def _write_crops_if_allowed(
    input_file: Path,
    arr: Any,
    source_arr: Any,
    profile: ImageProfile,
    page: Any,
    detection: Detection,
    config: Config,
    deskew_applied: bool,
    output_dir: Path,
    status: str,
) -> list[str]:
    should_export = (status == "approved_auto" or config.export_review) and not config.dry_run
    if not should_export:
        return []
    return write_crops(
        input_file,
        arr,
        source_arr,
        profile,
        page,
        detection,
        config,
        deskew_applied,
        output_dir,
    )


def _write_debug_outputs(
    gray: Any,
    detection: Detection,
    output_dir: Path,
    input_stem: str,
    config: Config,
    analysis_cache: Any,
    warnings: list[str],
) -> None:
    if config.debug and not config.debug_analysis:
        debug_path = output_dir / "_debug" / f"{input_stem}_debug.jpg"
        write_debug_preview(gray, detection, debug_path, config.confidence_threshold, analysis_cache)
        warnings.append(f"debug preview: {display_generated_path(debug_path, config)}")
    if config.debug_analysis:
        analysis_paths = write_debug_analysis(
            gray,
            detection,
            output_dir,
            input_stem,
            config.confidence_threshold,
            analysis_cache,
        )
        for analysis_path in analysis_paths:
            warnings.append(f"debug analysis: {display_generated_path(analysis_path, config)}")


def _finish_result(result: ProcessResult, config: Config) -> ProcessResult:
    write_report_outputs_for_result(result, config)
    return result


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)


__all__ = [
    "process_one",
    "process_one_worker",
]
