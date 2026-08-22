from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import traceback

from .identity import make_runtime_identity, source_runtime_identity
from ..configuration.model import DetectionConfiguration
from ..detection.decision.decision_gate import apply_decision_gate
from ..detection.final.finalize import finalize_detection
from ..detection.output_deskew import (
    disabled_lightweight_deskew_observation,
    observe_lightweight_deskew,
)
from ..detection.pipeline import choose_detection
from ..detection.workspace import prepare_detection_workspace
from ..export.actions import prepare_review_artifact
from ..export.crops import write_crops
from ..geometry.layout import infer_layout
from ..io.tiff import read_tiff, read_tiff_profile
from ..report.configuration import detection_configuration_read_model
from ..report.read_models import typed_read_model
from ..report.record import (
    capture_workspace_report_facts,
    report_record_for_final_detection,
)
from ..run_config import DeskewMode, RunConfig
from ..run_status import RunTerminalOutcome
from ..utils import spatial_shape_from_shape
from .outcome import (
    CompletedInput,
    FailedInput,
    FailureStage,
    InputProcessingOutcome,
    RuntimeArtifacts,
)
from .invocation import PlannedSource
from ..run_local_identity import source_identity_scope


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
    failure_stage = FailureStage.INPUT_PROFILE
    artifacts = RuntimeArtifacts.empty()
    warnings: list[str] = []
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

        failure_stage = FailureStage.DECISION
        decision = apply_decision_gate(
            candidate.gate,
        )

        failure_stage = FailureStage.FINALIZATION
        if decision.status != "approved_auto":
            deskew_observation = None
        elif config.deskew_mode == DeskewMode.AUTO:
            deskew_observation = observe_lightweight_deskew(
                workspace.source_gray,
                workspace.layout,
            )
        elif config.deskew_mode == DeskewMode.OFF:
            deskew_observation = disabled_lightweight_deskew_observation()
        else:
            raise ValueError(f"unsupported deskew mode: {config.deskew_mode}")
        detection = finalize_detection(
            candidate,
            decision,
            deskew_observation,
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
        measurement_detail, development_detail = capture_workspace_report_facts(
            detection,
            workspace,
            development_detail=config.development_detail,
        )
        if not config.debug_analysis:
            # Product output no longer needs registered gray after optional
            # deskew and report-fact capture. Release it before TIFF sampling.
            workspace = None

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
            assert workspace is not None
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
        result = report_record_for_final_detection(
            detection,
            source=str(input_file),
            profile=typed_read_model(profile),
            measurement=measurement_detail,
            development=development_detail,
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
            configuration=configuration_detail,
            runtime_identity=runtime_identity,
            frame_export_requested=not config.debug_analysis,
        )
        return CompletedInput(
            result=result,
            artifacts=artifacts,
        )
    except Exception as exc:
        return FailedInput(
            source=input_file,
            failure_stage=failure_stage,
            error_code=str(getattr(exc, "error_code", type(exc).__name__)),
            error_message=str(exc),
            artifacts=artifacts,
            traceback_text=traceback.format_exc(),
            error_errno=(exc.errno if isinstance(exc, OSError) else None),
        )
