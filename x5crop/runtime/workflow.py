from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .analysis_reuse import (
    make_analysis_cache_metadata,
    result_from_reusable_analysis,
)
from ..cache.analysis import make_analysis_cache
from .config import RuntimeConfig
from .output_protection import prepare_output_protection
from .deskew import apply_deskew
from .profile import runtime_for_profile
from ..debug.outputs import write_debug_outputs
from ..detection.decision.final_decision import apply_detection_decision
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..domain import ProcessResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..image.gray import make_base_gray_u8
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.bleed import detection_bleed_parameters
from ..output.surface import output_surface_for_input
from ..policies.decision.contract import decision_contract_for_policy
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..report.outputs import write_report_outputs_for_result
from ..report.result_builder import result_from_detection
from ..units import scan_calibration_from_profile
from ..detection.evidence.holder_occupancy import enrich_holder_occupancy_with_calibration


def process_one_worker(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    return process_one(input_file, replace(config, report=False))


def process_one(input_file: Path, config: RuntimeConfig) -> ProcessResult:
    output_surface = output_surface_for_input(input_file, config)
    output_dir = output_surface.root
    profile, warnings = read_tiff_profile(input_file, config.page)
    config = runtime_for_profile(config, profile)
    policy_bundle = DetectionPolicyBundle.for_format_mode(config.film_format, config.strip_mode)
    initial_policy = policy_bundle.initial_policy
    fmt = initial_policy.physical_spec

    cached_result = result_from_reusable_analysis(input_file, config, output_surface, profile, warnings, policy_bundle)
    if cached_result is not None:
        return _finish_result(cached_result, config)

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    gray = make_base_gray_u8(arr, profile.axes, profile.photometric, initial_policy.preprocess.base_gray)
    _extend_unique(warnings, page_warnings)
    source_arr = arr

    arr, gray, deskew_detail = apply_deskew(arr, gray, profile, config, initial_policy.preprocess, warnings)
    scan_calibration = scan_calibration_from_profile(profile, initial_policy.preprocess.scan_calibration_trust)
    analysis_cache = make_analysis_cache(gray, config.layout, initial_policy.preprocess.content_evidence_image)
    policy = initial_policy
    detection_bleed = detection_bleed_parameters(policy.output)
    detection_config = replace(config, bleed_x=detection_bleed.long_axis, bleed_y=detection_bleed.short_axis)
    detection_result = choose_detection(gray, detection_config, fmt, policy_bundle, analysis_cache)
    detection = detection_result.candidate
    selected_policy = detection_result.policy
    detection.detail["scan_calibration"] = scan_calibration.detail()
    holder_occupancy = detection.detail.get("holder_occupancy")
    if isinstance(holder_occupancy, dict):
        detection.detail["holder_occupancy"] = enrich_holder_occupancy_with_calibration(
            holder_occupancy,
            scan_calibration,
        )
    output_protection_plan = prepare_output_protection(
        gray,
        detection,
        config,
        analysis_cache,
        selected_policy,
    )
    decided_detection = apply_detection_decision(
        gray,
        detection,
        config,
        analysis_cache,
        deskew_detail,
        selected_policy,
        decision_contract_for_policy(selected_policy),
    )
    detection = finalize_detection(
        gray,
        decided_detection,
        config,
        analysis_cache,
        selected_policy,
        output_protection_plan,
    )
    review_copy = copy_for_review_if_needed(input_file, output_dir, config, detection, warnings)
    output_files = write_crops_if_allowed(
        input_file,
        arr,
        source_arr,
        profile,
        detection,
        config,
        bool(deskew_detail["applied"]),
        output_surface,
    )
    write_debug_outputs(gray, detection, output_dir, input_file.stem, config, analysis_cache, warnings, selected_policy)

    result = result_from_detection(
        input_file,
        detection,
        profile,
        output_files,
        review_copy,
        warnings,
        policy=selected_policy,
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
