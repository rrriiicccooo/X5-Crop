from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .analysis_reuse import (
    make_analysis_cache_metadata,
    result_from_reusable_analysis,
)
from .config import RuntimeConfig
from .detection.pipeline import choose_detection
from .detection.finalizer import finalize_detection
from .debug.outputs import write_debug_outputs
from .deskew_runtime import apply_deskew
from .domain import ProcessResult
from .export.actions import copy_for_review_if_needed, write_crops_if_allowed
from .export.paths import output_directory_for
from .formats import FORMATS
from .analysis_cache import make_analysis_cache
from .detection.final_geometry import detection_geometry_config
from .io.tiff import read_tiff, read_tiff_profile
from .policies.registry import get_detection_policy
from .report_outputs import write_report_outputs_for_result
from .result_builder import result_from_detection
from .source_config import config_for_profile


def process_one_worker(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    cached_result = result_from_reusable_analysis(input_file, config, output_dir, profile, warnings)
    if cached_result is not None:
        return _finish_result(cached_result, config)

    arr, gray, profile, page_warnings = read_tiff(input_file, config.page)
    _extend_unique(warnings, page_warnings)
    source_arr = arr
    config = config_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    arr, gray, deskew_detail = apply_deskew(arr, gray, profile, config, fmt, warnings)
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

    review_copy = copy_for_review_if_needed(input_file, output_dir, config, detection, status, warnings)
    output_files = write_crops_if_allowed(
        input_file,
        arr,
        source_arr,
        profile,
        detection,
        config,
        bool(deskew_detail["applied"]),
        output_dir,
        status,
    )
    write_debug_outputs(gray, detection, output_dir, input_file.stem, config, analysis_cache, warnings)

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


def _finish_result(result: ProcessResult, config: RuntimeConfig) -> ProcessResult:
    write_report_outputs_for_result(result, config)
    return result


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)


__all__ = [
    "process_one",
    "process_one_worker",
]
