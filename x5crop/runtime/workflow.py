from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
import traceback

from .analysis_identity import make_analysis_identity
from ..cache import MeasurementCache, MeasurementCacheStatistics
from ..detection.context import (
    DetectionContext,
    DetectionExecutionStatistics,
    DetectionRequest,
)
from ..detection.workspace import prepare_detection_workspace
from ..run_config import RunConfig
from ..run_status import RunTerminalOutcome
from ..detection.output_preparation import frame_bleed_plan_for_selection
from ..debug.outputs import write_debug_outputs
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from ..detection.pipeline import choose_detection
from ..domain import EvidenceState
from ..output.model import AxisBleedParameters
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..geometry.layout import infer_layout
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.surface import output_surface_for_input
from ..report.configuration import detection_configuration_read_model
from ..configuration.bundle import DetectionConfigurationBundle
from ..report.result_builder import result_from_detection
from ..units import (
    resolution_metadata_observation,
)
from ..utils import spatial_shape_from_shape
from .outcome import (
    CompletedInput,
    FailedInput,
    FailureStage,
    InputProcessingOutcome,
    RuntimeArtifacts,
    RuntimeMetrics,
)


def process_one(
    input_file: Path,
    config: RunConfig,
    configuration_bundle: DetectionConfigurationBundle,
) -> InputProcessingOutcome:
    started_at = perf_counter()
    detection_seconds = 0.0
    execution_statistics = DetectionExecutionStatistics()
    measurement_cache_statistics = MeasurementCacheStatistics()
    measurement_cache: MeasurementCache | None = None
    failure_stage = FailureStage.INPUT_PROFILE
    output_surface = output_surface_for_input(input_file, config)
    output_dir = output_surface.root
    artifacts = RuntimeArtifacts.empty()
    gray = None
    detection = None
    selected_candidate = None
    try:
        profile, warnings = read_tiff_profile(input_file, config.page)
        height, width = spatial_shape_from_shape(profile.shape)
        layout = infer_layout(width, height) if config.layout_auto else config.layout
        config = replace(config, layout=layout)
        initial_configuration = configuration_bundle.initial_configuration
        fmt = initial_configuration.physical_spec
        failure_stage = FailureStage.IMAGE_READ
        arr, profile, page_warnings = read_tiff(input_file, config.page)
        source_arr = arr

        _extend_unique(warnings, page_warnings)
        resolution_metadata = resolution_metadata_observation(
            profile.resolution,
            profile.resolution_unit,
        )
        failure_stage = FailureStage.DETECTION
        detection_started_at = perf_counter()
        try:
            lane_configuration = (
                None
                if fmt.layout.lane_format_id is None
                else configuration_bundle.configuration_for(
                    fmt.layout.lane_format_id,
                    "full",
                )
            )
            workspace = prepare_detection_workspace(
                arr,
                profile,
                config.layout,
                initial_configuration,
                lane_configuration,
                measurement_cache_statistics,
            )
            arr = workspace.pixels
            gray = workspace.gray
            transform_geometry = workspace.transform_geometry
            measurement_cache = workspace.measurement_cache
            if transform_geometry.applied:
                assert transform_geometry.applied_angle_degrees is not None
                warnings.append(
                    f"deskew applied: {transform_geometry.applied_angle_degrees:.4f} degrees"
                )
            detection_context = DetectionContext(
                request=DetectionRequest(
                    layout=config.layout,
                    strip_mode=config.strip_mode,
                    requested_count=config.requested_count,
                ),
                configuration=initial_configuration,
                lane_configuration=lane_configuration,
                workspace=workspace,
                execution_statistics=execution_statistics,
            )
            selection = choose_detection(detection_context)
        finally:
            detection_seconds += perf_counter() - detection_started_at
        selected_candidate = selection.selected

        analysis_identity = make_analysis_identity(
            input_file,
            profile,
            config,
            configuration_bundle,
            workspace.identity,
        )

        failure_stage = FailureStage.DECISION
        frame_bleed = frame_bleed_plan_for_selection(
            selection,
            AxisBleedParameters(
                long_axis=int(config.bleed_x),
                short_axis=int(config.bleed_y),
            ),
        )
        decided_detection = apply_decision_gate(
            selection,
            frame_bleed,
            transform_geometry,
            automatic_processing_eligibility=(
                EvidenceState.SUPPORTED
                if initial_configuration.detector_kind != "review_only"
                else EvidenceState.CONTRADICTED
            ),
        )

        failure_stage = FailureStage.FINALIZATION
        configuration_detail = detection_configuration_read_model(initial_configuration)
        finalization_plan = finalization_plan_for_selection(
            selection,
            workspace_extent=workspace.identity.extent,
        )
        detection = finalize_detection(
            decided_detection,
            frame_bleed,
            finalization_plan,
        )

        failure_stage = FailureStage.OUTPUT
        review_copy = copy_for_review_if_needed(
            input_file,
            output_dir,
            config,
            detection,
            warnings,
        )
        artifacts = replace(artifacts, review_copy=review_copy)
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
        artifacts = replace(artifacts, frame_outputs=tuple(output_files))

        failure_stage = FailureStage.DEBUG
        debug_analysis = write_debug_outputs(
            gray,
            detection,
            selected_candidate,
            output_dir,
            input_file.stem,
            config,
            warnings,
            initial_configuration.diagnostics,
            RunTerminalOutcome.COMPLETED,
        )
        artifacts = replace(artifacts, debug_analysis=debug_analysis)

        failure_stage = FailureStage.REPORT_VALIDATION
        result = result_from_detection(
            input_file,
            detection,
            selection,
            profile,
            workspace,
            list(artifacts.frame_outputs),
            artifacts.review_copy,
            warnings,
            configuration_detail=configuration_detail,
            resolution_metadata=resolution_metadata,
            analysis_identity=analysis_identity,
        )
        return CompletedInput(
            result=result,
            artifacts=artifacts,
            metrics=_runtime_metrics(
                started_at,
                detection_seconds,
                execution_statistics,
                measurement_cache,
            ),
        )
    except Exception as exc:
        traceback_text = traceback.format_exc()
        if (
            detection is not None
            and gray is not None
            and selected_candidate is not None
            and failure_stage != FailureStage.DEBUG
        ):
            try:
                debug_analysis = write_debug_outputs(
                    gray,
                    detection,
                    selected_candidate,
                    output_dir,
                    input_file.stem,
                    config,
                    warnings,
                    initial_configuration.diagnostics,
                    RunTerminalOutcome.RUNTIME_ERROR,
                )
                artifacts = replace(
                    artifacts,
                    debug_analysis=debug_analysis,
                )
            except Exception:
                pass
        return FailedInput(
            source=input_file,
            failure_stage=failure_stage,
            error_code=type(exc).__name__,
            error_message=str(exc),
            artifacts=artifacts,
            traceback_text=traceback_text,
            metrics=_runtime_metrics(
                started_at,
                detection_seconds,
                execution_statistics,
                measurement_cache,
            ),
        )


def _extend_unique(items: list[str], additions: list[str]) -> None:
    items.extend(item for item in additions if item not in items)


def _runtime_metrics(
    started_at: float,
    detection_seconds: float,
    execution_statistics: DetectionExecutionStatistics,
    measurement_cache: MeasurementCache | None,
) -> RuntimeMetrics:
    cache_hits = 0
    cache_misses = 0
    if measurement_cache is not None:
        cache_hits = measurement_cache.lookup_statistics.hits
        cache_misses = measurement_cache.lookup_statistics.misses
    return RuntimeMetrics(
        processing_seconds=perf_counter() - started_at,
        detection_seconds=detection_seconds,
        assessed_candidates=execution_statistics.assessed_candidates,
        assignment_evaluations=execution_statistics.assignment_evaluations,
        measurement_cache_hits=cache_hits,
        measurement_cache_misses=cache_misses,
    )
