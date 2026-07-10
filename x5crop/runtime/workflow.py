from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .analysis_reuse import (
    make_analysis_cache_metadata,
    result_from_reusable_analysis,
)
from ..cache.analysis import make_analysis_cache
from ..run_config import RunConfig
from .output_protection import prepare_output_protection
from .deskew import apply_deskew
from ..debug.outputs import write_debug_outputs
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.evidence.selected_candidate import complete_selected_candidate_evidence
from ..detection.detail import DECISION_POLICY_DETAIL, RUNTIME_POLICY_DETAIL
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..domain import ProcessResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..geometry.layout import infer_layout
from ..image.gray import make_base_gray_u8
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.surface import output_surface_for_input
from ..policies.decision.contract import decision_contract_for_policy
from ..policies.reporting import (
    decision_contract_report_detail,
    detection_policy_report_detail,
)
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..report.outputs import write_report_outputs_for_result
from ..report.result_builder import result_from_detection
from ..units import scan_calibration_from_profile
from ..utils import spatial_shape_from_shape
from ..detection.evidence.holder_occupancy import enrich_holder_occupancy_with_calibration


def process_one(
    input_file: Path,
    config: RunConfig,
    policy_bundle: DetectionPolicyBundle,
) -> ProcessResult:
    output_surface = output_surface_for_input(input_file, config)
    output_dir = output_surface.root
    profile, warnings = read_tiff_profile(input_file, config.page)
    height, width = spatial_shape_from_shape(profile.shape)
    layout = infer_layout(width, height) if config.layout_auto else config.layout
    config = replace(config, layout=layout)
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
    detection_config = replace(config, bleed_x=0, bleed_y=0)
    detection_result = choose_detection(gray, detection_config, fmt, policy_bundle, analysis_cache)
    detection = detection_result.candidate
    selected_policy = detection_result.policy
    detection.detail[RUNTIME_POLICY_DETAIL] = detection_policy_report_detail(selected_policy)
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
    decision_contract = decision_contract_for_policy(selected_policy)
    selected_evidence = complete_selected_candidate_evidence(
        gray,
        detection,
        analysis_cache,
        content_policy=selected_policy.content,
        alignment_parameters=selected_policy.outer.alignment_evidence,
        horizontal_frame_aspect=decision_contract.physical_spec.horizontal_content_aspect,
    )
    decided_detection = apply_decision_gate(
        gray,
        selected_evidence.candidate,
        config,
        selected_evidence.content,
        selected_evidence.outer_alignment,
        policy=decision_contract,
        deskew_detail=deskew_detail,
    )
    decided_detection.detail[DECISION_POLICY_DETAIL] = decision_contract_report_detail(
        decision_contract
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
        detail_extra={
            "deskew": deskew_detail,
            "analysis_cache": make_analysis_cache_metadata(
                input_file,
                profile,
                config,
                selected_policy,
            ),
        },
    )
    return _finish_result(result, config)


def _finish_result(result: ProcessResult, config: RunConfig) -> ProcessResult:
    write_report_outputs_for_result(result, config)
    return result


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)
