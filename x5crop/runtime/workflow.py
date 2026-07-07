from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .analysis_reuse import (
    make_analysis_cache_metadata,
    result_from_reusable_analysis,
)
from ..cache.analysis import make_analysis_cache
from .config import RuntimeConfig
from .deskew import apply_deskew
from .profile import runtime_for_profile
from ..debug.outputs import write_debug_outputs
from ..detection.decision.final_decision import apply_detection_decision
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..domain import ProcessResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..export.paths import output_directory_for
from ..formats import FORMATS
from ..image.gray import make_base_gray_u8
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.bleed import detection_bleed_parameters
from ..policies.registry import get_detection_policy
from ..report.outputs import write_report_outputs_for_result
from ..report.result_builder import result_from_detection


def process_one_worker(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    output_dir = output_directory_for(input_file, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = runtime_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    cached_result = result_from_reusable_analysis(input_file, config, output_dir, profile, warnings)
    if cached_result is not None:
        return _finish_result(cached_result, config)

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    gray = make_base_gray_u8(arr, profile.axes, profile.photometric)
    _extend_unique(warnings, page_warnings)
    source_arr = arr
    config = runtime_for_profile(config, profile)
    fmt = FORMATS[config.film_format]

    arr, gray, deskew_detail = apply_deskew(arr, gray, profile, config, fmt, warnings)
    analysis_cache = make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    detection_bleed = detection_bleed_parameters(policy.output)
    detection_config = replace(config, bleed_x=detection_bleed.long_axis, bleed_y=detection_bleed.short_axis)
    detection = choose_detection(gray, detection_config, fmt, analysis_cache)
    selected_policy = get_detection_policy(fmt.name, detection.strip_mode)
    decision = apply_detection_decision(
        gray,
        detection,
        config,
        fmt,
        analysis_cache,
        deskew_detail,
        selected_policy,
    )
    finalization = finalize_detection(
        gray,
        decision.detection,
        decision.status,
        config,
        fmt,
        analysis_cache,
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
