from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
import traceback

from .identity import make_runtime_identity, source_runtime_identity
from .detection_snapshot import (
    DetectionSnapshotError,
    ReusableDetectionSnapshot,
    SourceContentIdentity,
    carry_detection_snapshot,
    detection_configuration_binding,
    detection_snapshot_path,
    load_detection_snapshot,
    result_from_detection_snapshot,
    source_content_identity,
    write_detection_snapshot,
)
from ..configuration.bundle import DetectionConfigurationBundle
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.pipeline import choose_detection
from ..detection.workspace import DetectionWorkspace, prepare_detection_workspace
from ..export.actions import prepare_review_artifact
from ..export.crops import write_crops
from ..geometry.layout import infer_layout
from ..io.model import ImageProfile
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


def _source_identity_is_stable(
    runtime_identity: dict,
    content_identity: SourceContentIdentity,
) -> bool:
    return (
        runtime_identity["size"] == content_identity.size
        and runtime_identity["mtime_ns"] == content_identity.mtime_ns
    )


def _try_reusable_snapshot(
    source: PlannedSource,
    config: RunConfig,
    snapshot_roots: tuple[Path, ...],
    configuration_binding: dict,
    profile: ImageProfile,
    source_identity: dict,
) -> tuple[
    ReusableDetectionSnapshot | None,
    SourceContentIdentity | None,
    str | None,
]:
    candidates: list[Path] = []
    for root in dict.fromkeys(snapshot_roots):
        candidate = detection_snapshot_path(root, source)
        if candidate.is_file():
            candidates.append(candidate)
    if not candidates:
        return None, None, None
    if config.debug_analysis:
        return None, None, "fresh Debug Analysis was requested"
    try:
        content_identity = source_content_identity(source)
    except (OSError, DetectionSnapshotError) as exc:
        return None, None, str(exc)
    if not _source_identity_is_stable(source_identity, content_identity):
        return None, content_identity, "source changed during input processing"
    failures: list[str] = []
    for candidate in candidates:
        try:
            return (
                load_detection_snapshot(
                    candidate,
                    source_identity=content_identity,
                    configuration_binding=configuration_binding,
                    profile=profile,
                ),
                content_identity,
                None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(str(exc))
    return (
        None,
        content_identity,
        failures[-1] if failures else "snapshot validation failed",
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
    work = (
        ()
        if detection is None
        else tuple(
            lane.work
            for lane in detection.candidate.geometry.lane_reconstructions
        )
    )
    query_sets = (
        ()
        if detection is None
        else tuple(
            item
            for lane in detection.candidate.geometry.lane_reconstructions
            for item in lane.measurement_sets
        )
    )
    return RuntimeMetrics(
        processing_seconds=processing_seconds,
        detection_seconds=detection_seconds,
        domain_pixels=sum(
            lane.domain.work_box.width * lane.domain.work_box.height
            for lane in workspace.source_core.lanes
        ),
        measurement_query_count=len(query_sets),
        pixel_query_count=sum(item.pixel_query_count for item in work),
        basic_profile_coordinate_count=sum(
            item.basic_profile_coordinate_count for item in work
        ),
        basic_profile_run_count=sum(
            item.basic_profile_run_count for item in work
        ),
        phase_vote_count=sum(item.phase_vote_count for item in work),
        template_group_count=sum(item.template_group_count for item in work),
        template_role_lookup_count=sum(
            item.template_role_lookup_count for item in work
        ),
        template_role_match_count=sum(
            item.template_role_match_count for item in work
        ),
        local_relation_evaluation_count=sum(
            item.local_relation_evaluation_count for item in work
        ),
        enhanced_query_count=sum(item.enhanced_query_count for item in work),
        materialized_frame_geometry_count=sum(
            item.materialized_frame_geometry_count for item in work
        ),
        shared_measurement_reuse_count=sum(
            item.shared_measurement_reuse_count for item in work
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
    configuration_bundle: DetectionConfigurationBundle,
    output_root: Path,
    snapshot_roots: tuple[Path, ...] = (),
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
        initial_configuration = configuration_bundle.initial_configuration

        failure_stage = FailureStage.IMAGE_READ
        arr, profile, page_warnings = read_tiff(input_file)
        for warning in page_warnings:
            if warning not in warnings:
                warnings.append(warning)
        source_identity = source_runtime_identity(source, profile)

        configuration_detail = detection_configuration_read_model(
            initial_configuration
        )
        configuration_binding = detection_configuration_binding(
            configuration_detail,
            config.layout,
        )
        snapshot, content_identity, snapshot_miss = _try_reusable_snapshot(
            source,
            config,
            snapshot_roots,
            configuration_binding,
            profile,
            source_identity,
        )
        if snapshot_miss is not None:
            warnings.append(
                "detection snapshot not reused: "
                + snapshot_miss
                + "; fresh detection performed"
            )
        if snapshot is not None:
            failure_stage = FailureStage.OUTPUT
            warnings.append(
                "detection snapshot reused: "
                + snapshot.path.relative_to(snapshot.path.parents[1]).as_posix()
            )
            output_root.mkdir(parents=True, exist_ok=True)
            if snapshot.decision_status == "approved_auto":
                frame_outputs = write_crops(
                    source.portable_stem,
                    source.input_ordinal,
                    arr,
                    profile,
                    snapshot.final_boxes,
                    snapshot.sampling_authority_boxes,
                    snapshot.transform,
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
                    snapshot.final_review_reasons,
                    warnings,
                )
                artifacts = replace(artifacts, review_copy=review_copy)

            failure_stage = FailureStage.SNAPSHOT
            carried_path = detection_snapshot_path(output_root, source)
            artifacts = replace(
                artifacts,
                detection_snapshot=str(carried_path),
            )
            carry_detection_snapshot(snapshot, output_root, source)

            failure_stage = FailureStage.REPORT_VALIDATION
            result = result_from_detection_snapshot(
                snapshot,
                input_file=input_file,
                profile=profile,
                source_runtime_identity=source_identity,
                config=config,
                output_files=[
                    Path(path).relative_to(output_root).as_posix()
                    for path in artifacts.frame_outputs
                ],
                review_copy=(
                    None
                    if artifacts.review_copy is None
                    else Path(artifacts.review_copy)
                    .relative_to(output_root)
                    .as_posix()
                ),
                warnings=warnings,
            )
            return CompletedInput(
                result=result,
                artifacts=artifacts,
                metrics=RuntimeMetrics.unavailable(),
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
        runtime_identity = make_runtime_identity(
            source_identity,
            config,
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
        if config.preview:
            warnings.append(
                "preview: no official TIFF or review copy was written"
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
                detection.transform_assessment.transform,
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
                initial_configuration,
                profile,
                input_file.name,
                output_root,
                source.portable_stem,
                source.input_ordinal,
                initial_configuration.diagnostics,
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

        if config.preview:
            failure_stage = FailureStage.SNAPSHOT
            if content_identity is None:
                content_identity = source_content_identity(source)
            if not _source_identity_is_stable(source_identity, content_identity):
                raise DetectionSnapshotError(
                    "source changed during preview processing"
                )
            snapshot_output = detection_snapshot_path(output_root, source)
            warnings.append(
                "detection snapshot: "
                + snapshot_output.relative_to(output_root).as_posix()
            )
            artifacts = replace(
                artifacts,
                detection_snapshot=str(snapshot_output),
            )

        failure_stage = FailureStage.REPORT_VALIDATION
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
            frame_export_requested=not config.preview,
        )
        if config.preview:
            failure_stage = FailureStage.SNAPSHOT
            if (
                content_identity is None
                or artifacts.detection_snapshot is None
            ):
                raise DetectionSnapshotError(
                    "preview snapshot identity is incomplete"
                )
            write_detection_snapshot(
                Path(artifacts.detection_snapshot),
                source_identity=content_identity,
                configuration_binding=configuration_binding,
                report=result.record,
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
            error_errno=(exc.errno if isinstance(exc, OSError) else None),
        )
