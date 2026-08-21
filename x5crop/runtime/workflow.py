from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
import traceback

from .identity import make_runtime_identity, source_runtime_identity
from ..configuration.model import DetectionConfiguration
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..detection.workspace import DetectionWorkspace, prepare_detection_workspace
from ..export.actions import prepare_review_artifact
from ..export.crops import write_crops
from ..geometry.layout import infer_layout
from ..io.tiff import read_tiff, read_tiff_profile
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
from .invocation import PlannedSource
from ..run_local_identity import source_identity_scope


def _metrics(
    started_at: float,
    detection_seconds: float,
    workspace: DetectionWorkspace | None,
    detection=None,
) -> RuntimeMetrics:
    processing_seconds = perf_counter() - started_at
    if workspace is None:
        return RuntimeMetrics.unavailable()
    work = (
        ()
        if detection is None
        else tuple(
            lane.work
            for lane in detection.candidate.geometry.lane_reconstructions
            if lane.work is not None
        )
    )
    reconstructed = (
        ()
        if detection is None
        else detection.candidate.geometry.lane_reconstructions
    )
    prepared = tuple(lane.prepared for lane in reconstructed)
    return RuntimeMetrics(
        processing_seconds=processing_seconds,
        detection_seconds=detection_seconds,
        domain_pixels=sum(
            lane.domain.work_box.width * lane.domain.work_box.height
            for lane in workspace.source_core.lanes
        ),
        measurement_query_count=sum(
            lane.measurement_work.measurement_query_count for lane in prepared
        ),
        pixel_query_count=sum(
            lane.measurement_work.pixel_query_count for lane in prepared
        ),
        basic_profile_coordinate_count=sum(
            lane.sequence_profile.coordinate_count
            + lane.cross_profile.coordinate_count
            for lane in prepared
        ),
        basic_profile_run_count=sum(
            len(lane.sequence_profile.runs) + len(lane.cross_profile.runs)
            for lane in prepared
        ),
        registered_sequence_observation_count=sum(
            len(lane.sequence_edges) for lane in prepared
        ),
        phase_hypothesis_count=sum(
            lane.phase_competition.receipt.phase_hypothesis_count
            for lane in prepared
        ),
        separator_lattice_hypothesis_count=sum(
            lane.phase_competition.receipt.separator_lattice_hypothesis_count
            for lane in prepared
        ),
        phase_fit_pass_count=sum(
            lane.phase_competition.receipt.fit_pass_count
            for lane in prepared
        ),
        phase_role_lookup_count=sum(
            lane.phase_competition.receipt.phase_lookup_count
            for lane in prepared
        ),
        phase_role_binding_count=sum(
            lane.phase_competition.receipt.role_binding_count
            for lane in prepared
        ),
        local_relation_evaluation_count=sum(
            lane.phase_competition.receipt.local_relation_evaluation_count
            for lane in prepared
        ),
        cross_registered_run_count=sum(
            lane.cross_competition.receipt.registered_run_count
            for lane in prepared
        ),
        cross_fit_evaluation_count=sum(
            lane.cross_competition.receipt.evaluated_fit_count
            for lane in prepared
        ),
        placement_evaluation_count=sum(
            item.placement_evaluation_count for item in work
        ),
        boundary_evaluation_count=sum(
            item.boundary_evaluation_count for item in work
        ),
        content_evaluation_count=sum(
            item.content_evaluation_count for item in work
        ),
        peak_temporary_bytes=max(
            (
                *(
                    item.peak_temporary_bytes
                    for item in work
                ),
                0,
            )
        ),
    )


def process_one(
    source: PlannedSource,
    config: RunConfig,
    configuration: DetectionConfiguration,
    output_root: Path,
) -> InputProcessingOutcome:
    with source_identity_scope():
        return _process_one_scoped(
            source,
            config,
            configuration,
            output_root,
        )


def _process_one_scoped(
    source: PlannedSource,
    config: RunConfig,
    configuration: DetectionConfiguration,
    output_root: Path,
) -> InputProcessingOutcome:
    input_file = source.path
    started_at = perf_counter()
    detection_seconds = 0.0
    failure_stage = FailureStage.INPUT_PROFILE
    artifacts = RuntimeArtifacts.empty()
    warnings: list[str] = []
    workspace: DetectionWorkspace | None = None
    detection = None
    try:
        profile, profile_warnings = read_tiff_profile(input_file)
        warnings.extend(profile_warnings)
        height, width = spatial_shape_from_shape(profile.shape)
        layout = infer_layout(width, height) if config.layout_auto else config.layout
        config = replace(config, layout=layout)
        failure_stage = FailureStage.IMAGE_READ
        arr, profile, page_warnings = read_tiff(input_file)
        for warning in page_warnings:
            if warning not in warnings:
                warnings.append(warning)
        source_identity = source_runtime_identity(source, profile)

        configuration_detail = detection_configuration_read_model(
            configuration
        )
        failure_stage = FailureStage.DETECTION
        detection_started = perf_counter()
        workspace = prepare_detection_workspace(
            arr,
            profile,
            config.layout,
            configuration,
        )
        candidate = choose_detection(
            workspace,
            configuration,
        )
        detection_seconds = perf_counter() - detection_started

        failure_stage = FailureStage.DECISION
        decision = apply_decision_gate(
            candidate.gate,
        )

        failure_stage = FailureStage.FINALIZATION
        detection = finalize_detection(
            candidate,
            decision,
            workspace.deskew_observation,
            layout=workspace.layout,
            source_width=workspace.source_gray.shape[1],
            source_height=workspace.source_gray.shape[0],
        )
        runtime_identity = make_runtime_identity(
            source_identity,
            config,
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
        if config.debug_analysis:
            warnings.append(
                "debug analysis only: no official TIFF or review copy was written"
            )
        elif detection.frame_export_eligible:
            output_root.mkdir(parents=True, exist_ok=True)
            frame_outputs = write_crops(
                source.portable_stem,
                source.input_ordinal,
                arr,
                profile,
                detection.final_boxes,
                detection.sampling_authority_boxes,
                detection.output_transforms,
                output_root,
            )
            artifacts = replace(
                artifacts,
                frame_outputs=tuple(frame_outputs),
            )
        else:
            review_copy = prepare_review_artifact(
                input_file,
                source.portable_stem,
                source.input_ordinal,
                output_root,
                detection.decision.final_review_reasons,
                warnings,
            )
            artifacts = replace(artifacts, review_copy=review_copy)

        failure_stage = FailureStage.DEBUG
        if config.debug_analysis:
            from ..debug.writer import write_debug_analysis

            debug_analysis = write_debug_analysis(
                workspace,
                detection,
                configuration,
                profile,
                input_file.name,
                output_root,
                source.portable_stem,
                source.input_ordinal,
                configuration.diagnostics,
                RunTerminalOutcome(detection.decision.status),
            )
            warnings.append(
                "debug analysis: "
                + Path(debug_analysis).relative_to(output_root).as_posix()
            )
            artifacts = replace(
                artifacts,
                debug_analysis=debug_analysis,
            )

        failure_stage = FailureStage.REPORT_BUILD
        result = result_from_detection(
            input_file,
            detection,
            profile,
            workspace,
            [
                Path(path).relative_to(output_root).as_posix()
                for path in artifacts.frame_outputs
            ],
            (
                None
                if artifacts.review_copy is None
                else Path(artifacts.review_copy)
                .relative_to(output_root)
                .as_posix()
            ),
            warnings,
            configuration_detail=configuration_detail,
            runtime_identity=runtime_identity,
            frame_export_requested=not config.debug_analysis,
            development_detail=config.development_detail,
        )
        return CompletedInput(
            result=result,
            artifacts=artifacts,
            metrics=(
                _metrics(
                    started_at,
                    detection_seconds,
                    workspace,
                    detection,
                )
                if config.development_detail
                else RuntimeMetrics.unavailable()
            ),
        )
    except Exception as exc:
        return FailedInput(
            source=input_file,
            failure_stage=failure_stage,
            error_code=str(getattr(exc, "error_code", type(exc).__name__)),
            error_message=str(exc),
            artifacts=artifacts,
            traceback_text=traceback.format_exc(),
            metrics=(
                _metrics(
                    started_at,
                    detection_seconds,
                    workspace,
                    detection,
                )
                if config.development_detail
                else RuntimeMetrics.unavailable()
            ),
            error_errno=(exc.errno if isinstance(exc, OSError) else None),
        )
