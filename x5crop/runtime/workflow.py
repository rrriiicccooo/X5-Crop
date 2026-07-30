from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
import traceback

from .analysis_identity import make_analysis_identity, source_analysis_identity
from ..configuration.bundle import DetectionConfigurationBundle
from ..debug.outputs import write_debug_outputs
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..detection.workspace import DetectionWorkspace, prepare_detection_workspace
from ..export.actions import prepare_review_artifact
from ..export.crops import write_crops
from ..geometry.layout import infer_layout
from ..io.tiff import read_tiff, read_tiff_profile
from ..output.surface import output_surface_for_input
from ..report.configuration import detection_configuration_read_model
from ..report.result_builder import result_from_detection
from ..run_config import RunConfig
from ..run_status import RunTerminalOutcome
from ..utils import spatial_shape_from_shape
from .outcome import (
    CompletedInput,
    FailedInput,
    FailureStage,
    InputProcessingOutcome,
    RuntimeArtifacts,
    RuntimeMetrics,
)


def _metrics(
    started_at: float,
    detection_seconds: float,
    workspace: DetectionWorkspace | None,
    detection=None,
) -> RuntimeMetrics:
    processing_seconds = perf_counter() - started_at
    if workspace is None:
        return RuntimeMetrics.unavailable()
    statistics = tuple(
        lane.content.statistics
        for lane in workspace.source_core.lanes
    )
    separator_statistics = tuple(
        item.statistics for item in workspace.separator_fields
    )
    grid_work = (
        ()
        if detection is None
        else tuple(
            item
            for selection in detection.candidate.lane_selections
            for item in selection.work_by_component
        )
    )
    return RuntimeMetrics(
        processing_seconds=processing_seconds,
        detection_seconds=detection_seconds,
        domain_pixels=sum(item.domain_pixels for item in statistics),
        content_runs=sum(item.run_count for item in statistics),
        content_components=sum(item.component_count for item in statistics),
        censored_content_components=sum(
            item.censored_component_count for item in statistics
        ),
        exact_measurement_count=(
            2
            + len(statistics)
            + sum(
                item.exact_measurement_count
                for item in separator_statistics
            )
        ),
        exact_cache_hit_count=sum(
            item.exact_cache_hit_count for item in separator_statistics
        ),
        separator_line_observations=sum(
            item.line_observation_count for item in separator_statistics
        ),
        placement_seeds=sum(item.seed_count for item in grid_work),
        candidate_builds=sum(item.candidate_builds for item in grid_work),
        dp_states=sum(item.dp_states for item in grid_work),
        dp_transitions=sum(item.dp_transitions for item in grid_work),
        retained_proposals=sum(
            item.retained_proposal_count for item in grid_work
        ),
        peak_temporary_bytes=max(
            (
                *(
                    item.peak_temporary_bytes
                    for item in statistics
                ),
                *(
                    item.peak_temporary_bytes
                    for item in separator_statistics
                ),
                0,
            )
        ),
    )


def process_one(
    input_file: Path,
    config: RunConfig,
    configuration_bundle: DetectionConfigurationBundle,
) -> InputProcessingOutcome:
    started_at = perf_counter()
    detection_seconds = 0.0
    failure_stage = FailureStage.INPUT_PROFILE
    output_surface = output_surface_for_input(input_file, config)
    artifacts = RuntimeArtifacts.empty()
    warnings: list[str] = []
    workspace: DetectionWorkspace | None = None
    detection = None
    try:
        profile, profile_warnings = read_tiff_profile(input_file, config.page)
        warnings.extend(profile_warnings)
        height, width = spatial_shape_from_shape(profile.shape)
        layout = infer_layout(width, height) if config.layout_auto else config.layout
        config = replace(config, layout=layout)
        initial_configuration = configuration_bundle.initial_configuration

        failure_stage = FailureStage.IMAGE_READ
        arr, profile, page_warnings = read_tiff(input_file, config.page)
        for warning in page_warnings:
            if warning not in warnings:
                warnings.append(warning)
        source_identity = source_analysis_identity(
            input_file,
            profile,
            config.page,
        )

        failure_stage = FailureStage.DETECTION
        detection_started = perf_counter()
        lane_configuration = (
            None
            if initial_configuration.physical_spec.layout.lane_format_id is None
            else configuration_bundle.configuration_for(
                initial_configuration.physical_spec.layout.lane_format_id,
                "full",
            )
        )
        workspace = prepare_detection_workspace(
            arr,
            profile,
            config.layout,
            initial_configuration,
            lane_configuration,
        )
        candidate = choose_detection(
            workspace,
            initial_configuration,
            lane_configuration,
        )
        detection_seconds = perf_counter() - detection_started

        failure_stage = FailureStage.DECISION
        decision = apply_decision_gate(
            candidate.gate,
            initial_configuration.count_request.mode,
        )

        failure_stage = FailureStage.FINALIZATION
        detection = finalize_detection(
            candidate,
            decision,
            layout=config.layout,
        )
        analysis_identity = make_analysis_identity(
            source_identity,
            config,
            configuration_bundle,
            workspace.identity,
            (
                None
                if not detection.source_core.lanes
                else detection.source_core.lanes[
                    0
                ].scan_canvas.selected_profile.profile_id
            ),
            detection.resolved_output_slots,
            detection.output_slot_identities,
        )

        failure_stage = FailureStage.OUTPUT
        if detection.frame_export_eligible:
            if config.diagnostics:
                warnings.append(
                    "diagnostics mode: safe frame export was not requested"
                )
            else:
                output_surface.root.mkdir(parents=True, exist_ok=True)
                frame_outputs = write_crops(
                    input_file,
                    arr,
                    profile,
                    detection.final_boxes,
                    config,
                    detection.transform_assessment.transform,
                    output_surface.root,
                )
                artifacts = replace(
                    artifacts,
                    frame_outputs=tuple(frame_outputs),
                )
        else:
            review_copy = prepare_review_artifact(
                input_file,
                output_surface.root,
                config,
                detection,
                warnings,
            )
            artifacts = replace(artifacts, review_copy=review_copy)

        failure_stage = FailureStage.DEBUG
        debug_analysis = write_debug_outputs(
            workspace,
            detection,
            output_surface.root,
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
            profile,
            workspace,
            list(artifacts.frame_outputs),
            artifacts.review_copy,
            warnings,
            configuration_detail=detection_configuration_read_model(
                initial_configuration
            ),
            analysis_identity=analysis_identity,
        )
        return CompletedInput(
            result=result,
            artifacts=artifacts,
            metrics=_metrics(
                started_at,
                detection_seconds,
                workspace,
                detection,
            ),
        )
    except Exception as exc:
        return FailedInput(
            source=input_file,
            failure_stage=failure_stage,
            error_code=type(exc).__name__,
            error_message=str(exc),
            artifacts=artifacts,
            traceback_text=traceback.format_exc(),
            metrics=_metrics(
                started_at,
                detection_seconds,
                workspace,
                detection,
            ),
        )
