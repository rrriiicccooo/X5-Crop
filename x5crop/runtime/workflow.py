from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .analysis_reuse import (
    make_analysis_reuse_signature,
    result_from_reusable_analysis,
)
from ..cache.analysis import make_measurement_cache
from ..detection.context import DetectionContext, DetectionRequest
from ..run_config import RunConfig
from .output_protection import prepare_output_protection
from .deskew import apply_deskew
from ..debug.outputs import write_debug_outputs
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..domain import AxisBleedParameters, ProcessResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..geometry.layout import infer_layout
from ..image.gray import make_base_gray_u8
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.surface import output_surface_for_input
from ..policies.reporting import detection_policy_report_detail
from ..policies.runtime.bundle import DetectionPolicyBundle
from ..report.result_builder import result_from_detection
from ..units import scan_calibration_from_profile
from ..utils import spatial_shape_from_shape


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
        return cached_result

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    gray = make_base_gray_u8(arr, profile.axes, profile.photometric, initial_policy.preprocess.base_gray)
    _extend_unique(warnings, page_warnings)
    source_arr = arr

    arr, gray, transform_geometry = apply_deskew(
        arr,
        gray,
        profile,
        config,
        initial_policy.preprocess,
        warnings,
    )
    scan_calibration = scan_calibration_from_profile(profile, initial_policy.preprocess.scan_calibration_trust)
    measurement_cache = make_measurement_cache(
        gray,
        config.layout,
        initial_policy.preprocess.content_evidence_image,
    )
    detection_context = DetectionContext(
        source_gray=gray,
        image_profile=profile,
        scan_calibration=scan_calibration,
        request=DetectionRequest(
            layout=config.layout,
            strip_mode=config.strip_mode,
            requested_count=config.requested_count,
        ),
        policy=initial_policy,
        lane_policy=(
            None
            if fmt.lane_format_id is None
            else policy_bundle.policy_for(fmt.lane_format_id, "full")
        ),
        measurement_cache=measurement_cache,
    )
    selection = choose_detection(detection_context)
    selected_policy = detection_context.policy
    prepared_output_protection = prepare_output_protection(
        selection.selected,
        detection_context,
        AxisBleedParameters(
            long_axis=int(config.bleed_x),
            short_axis=int(config.bleed_y),
        ),
    )
    decided_detection = apply_decision_gate(
        selection,
        prepared_output_protection.plan,
        prepared_output_protection.evidence,
        transform_geometry,
        scan_calibration,
    )
    runtime_policy_detail = detection_policy_report_detail(selected_policy)
    detection = finalize_detection(
        gray,
        decided_detection,
        approved_geometry_parameters=(
            selected_policy.approved_geometry_adjustment
        ),
        edge_bleed_parameters=selected_policy.output.edge_bleed_protection,
    )
    review_copy = copy_for_review_if_needed(input_file, output_dir, config, detection, warnings)
    output_files = write_crops_if_allowed(
        input_file,
        arr,
        source_arr,
        profile,
        detection,
        config,
        transform_geometry.applied,
        output_surface,
    )
    write_debug_outputs(
        gray,
        detection,
        output_dir,
        input_file.stem,
        config,
        warnings,
        selected_policy.diagnostics,
        selected_policy.preprocess.separator_evidence_image,
    )

    result = result_from_detection(
        input_file,
        detection,
        profile,
        output_files,
        review_copy,
        warnings,
        policy_id=selected_policy.policy_id,
        runtime_policy_detail=runtime_policy_detail,
        transform_geometry=transform_geometry,
        analysis_reuse_signature=make_analysis_reuse_signature(
            input_file,
            profile,
            config,
            selected_policy,
        ),
    )
    return result


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)
