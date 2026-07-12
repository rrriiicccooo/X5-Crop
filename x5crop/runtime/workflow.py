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
from .frame_bleed import prepare_frame_bleed
from .deskew import apply_deskew
from ..debug.outputs import write_debug_outputs
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..output.model import AxisBleedParameters
from ..report.model import ReportResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..geometry.layout import infer_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..image.statistics import image_measurement_statistics
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.surface import output_surface_for_input
from ..report.configuration import detection_configuration_read_model
from ..configuration.bundle import DetectionConfigurationBundle
from ..report.result_builder import result_from_detection
from ..units import (
    scan_calibration_after_rotation,
    scan_calibration_from_resolution,
)
from ..utils import spatial_shape_from_shape


def process_one(
    input_file: Path,
    config: RunConfig,
    configuration_bundle: DetectionConfigurationBundle,
) -> ReportResult:
    output_surface = output_surface_for_input(input_file, config)
    output_dir = output_surface.root
    profile, warnings = read_tiff_profile(input_file, config.page)
    height, width = spatial_shape_from_shape(profile.shape)
    layout = infer_layout(width, height) if config.layout_auto else config.layout
    config = replace(config, layout=layout)
    initial_configuration = configuration_bundle.initial_configuration
    fmt = initial_configuration.physical_spec
    analysis_reuse_signature = make_analysis_reuse_signature(
        input_file,
        profile,
        config,
        configuration_bundle,
    )

    cached_result = result_from_reusable_analysis(
        input_file,
        config,
        output_surface,
        profile,
        warnings,
        analysis_reuse_signature,
    )
    if cached_result is not None:
        return cached_result

    arr, profile, page_warnings = read_tiff(input_file, config.page)
    gray = make_base_gray_u8(arr, profile.axes, profile.photometric, initial_configuration.preprocess.base_gray)
    _extend_unique(warnings, page_warnings)
    source_arr = arr
    measurement_statistics = image_measurement_statistics(
        work_gray(gray, config.layout),
        initial_configuration.preprocess.image_statistics,
    )
    scan_calibration = scan_calibration_from_resolution(
        profile.resolution,
        profile.resolution_unit,
    )

    arr, gray, transform_geometry = apply_deskew(
        arr,
        gray,
        profile,
        config,
        initial_configuration.preprocess,
        measurement_statistics,
        warnings,
    )
    if transform_geometry.applied:
        measurement_statistics = image_measurement_statistics(
            work_gray(gray, config.layout),
            initial_configuration.preprocess.image_statistics,
        )
        scan_calibration = scan_calibration_after_rotation(
            scan_calibration,
            transform_geometry.applied_angle_degrees,
        )
    measurement_cache = make_measurement_cache(
        gray,
        config.layout,
        initial_configuration.preprocess.content_evidence_image,
        measurement_statistics,
    )
    detection_context = DetectionContext(
        scan_calibration=scan_calibration,
        request=DetectionRequest(
            layout=config.layout,
            strip_mode=config.strip_mode,
            requested_count=config.requested_count,
        ),
        configuration=initial_configuration,
        lane_configuration=(
            None
            if fmt.lane_format_id is None
            else configuration_bundle.configuration_for(fmt.lane_format_id, "full")
        ),
        measurement_cache=measurement_cache,
    )
    selection = choose_detection(detection_context)
    selected_configuration = detection_context.configuration
    prepared_frame_bleed = prepare_frame_bleed(
        selection.selected,
        AxisBleedParameters(
            long_axis=int(config.bleed_x),
            short_axis=int(config.bleed_y),
        ),
    )
    decided_detection = apply_decision_gate(
        selection,
        prepared_frame_bleed,
        transform_geometry,
        scan_calibration,
        image_width=int(gray.shape[1]),
        image_height=int(gray.shape[0]),
    )
    configuration_detail = detection_configuration_read_model(selected_configuration)
    detection = finalize_detection(
        decided_detection,
        image_width=int(gray.shape[1]),
        image_height=int(gray.shape[0]),
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
        selection.selected,
        output_dir,
        input_file.stem,
        config,
        warnings,
        selected_configuration.diagnostics,
    )

    result = result_from_detection(
        input_file,
        detection,
        selection,
        profile,
        output_files,
        review_copy,
        warnings,
        configuration_detail=configuration_detail,
        transform_geometry=transform_geometry,
        analysis_reuse_signature=analysis_reuse_signature,
    )
    return result


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)
