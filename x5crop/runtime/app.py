from __future__ import annotations

import sys
import traceback
import concurrent.futures
from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..report.model import ReportResult
from ..report.outputs import write_report_outputs_for_result
from ..run_config import RunConfig
from ..run_status import RunTerminalOutcome
from .invocation import RuntimeInvocation
from .manifest import RunManifestRecord, append_run_manifest
from .outcome import (
    FailedInput,
    FailureStage,
    InputProcessingOutcome,
    RuntimeMetrics,
)
from .workflow import process_one


def print_run_header(invocation: RuntimeInvocation) -> None:
    config = invocation.config
    files = invocation.files
    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(files)}")
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    configuration = invocation.configuration_bundle.initial_configuration
    mode_parts.append(f"configuration: {configuration.configuration_id}")
    if config.strip_mode == "partial" and config.requested_count is None:
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    if config.diagnostics:
        mode_parts.append("diagnostics")
    if config.dry_run:
        mode_parts.append("dry run")
    print("; ".join(mode_parts))
    print(f"deskew fallback: {config.deskew_fallback}")
    if len(files) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    if config.output_dir is not None:
        print(f"output: {config.output_dir}")


def print_report_result(result: ReportResult, config: RunConfig) -> None:
    record = result.record
    print(f"  status={record['decision']['status']}")
    for warning in record["output"]["warnings"]:
        print(f"  info: {warning}")
    output_files = record["output"]["output_files"]
    if output_files:
        print(f"  wrote: {len(output_files)} TIFF files")
        if config.output_dir is not None:
            for out in output_files:
                print(f"    {Path(out).name}")


def _failed_input_from_exception(
    source: Path,
    stage: FailureStage,
    exc: Exception,
) -> FailedInput:
    return FailedInput(
        source=source,
        failure_stage=stage,
        error_code=type(exc).__name__,
        error_message=str(exc),
        debug_analysis=None,
        output_files=(),
        traceback_text=traceback.format_exc(),
        metrics=RuntimeMetrics.unavailable(),
    )


def _failure_manifest(failure: FailedInput) -> RunManifestRecord:
    return RunManifestRecord(
        source=str(failure.source),
        terminal_outcome=RunTerminalOutcome.RUNTIME_ERROR,
        failure_stage=failure.failure_stage,
        error_code=failure.error_code,
        error_message=failure.error_message,
        report_written=False,
        debug_analysis=failure.debug_analysis,
        output_files=failure.output_files,
        metrics=failure.metrics,
    )


def _handle_input_outcome(
    source: Path,
    outcome: InputProcessingOutcome,
    config: RunConfig,
) -> tuple[bool, str | None]:
    if isinstance(outcome, FailedInput):
        append_run_manifest(source, config, _failure_manifest(outcome))
        print(f"  error: {outcome.error_message}", file=sys.stderr)
        if config.debug_errors and outcome.traceback_text:
            print(outcome.traceback_text, file=sys.stderr, end="")
        return False, None

    result = outcome.result
    try:
        report_written = write_report_outputs_for_result(result, config)
    except Exception as exc:
        failure = FailedInput(
            source=source,
            failure_stage=FailureStage.REPORT_WRITE,
            error_code=type(exc).__name__,
            error_message=str(exc),
            debug_analysis=outcome.debug_analysis,
            output_files=tuple(result.record["output"]["output_files"]),
            traceback_text=traceback.format_exc(),
            metrics=outcome.metrics,
        )
        append_run_manifest(source, config, _failure_manifest(failure))
        print(f"  error: {failure.error_message}", file=sys.stderr)
        if config.debug_errors and failure.traceback_text:
            print(failure.traceback_text, file=sys.stderr, end="")
        return False, None

    output_files = tuple(result.record["output"]["output_files"])
    append_run_manifest(
        source,
        config,
        RunManifestRecord(
            source=str(source),
            terminal_outcome=RunTerminalOutcome.COMPLETED,
            failure_stage=None,
            error_code=None,
            error_message=None,
            report_written=report_written,
            debug_analysis=outcome.debug_analysis,
            output_files=output_files,
            metrics=outcome.metrics,
        ),
    )
    print_report_result(result, config)
    return True, str(result.record["decision"]["status"])


def process_parallel_files(
    invocation: RuntimeInvocation,
) -> tuple[int, int, int, int]:
    config = invocation.config
    files = invocation.files
    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    try:
        executor_context = concurrent.futures.ProcessPoolExecutor(max_workers=config.jobs)
    except (OSError, PermissionError) as exc:
        print(f"info: process workers unavailable ({exc}); using thread workers")
        executor_context = concurrent.futures.ThreadPoolExecutor(max_workers=config.jobs)
    with executor_context as executor:
        future_to_path = {
            executor.submit(
                process_one,
                path,
                config,
                invocation.configuration_bundle,
            ): path
            for path in files
        }
        for index, future in enumerate(concurrent.futures.as_completed(future_to_path), start=1):
            path = future_to_path[future]
            print(f"\n[{index}/{total}] {path.name}")
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = _failed_input_from_exception(
                    path,
                    FailureStage.WORKER,
                    exc,
                )
            succeeded, status = _handle_input_outcome(path, outcome, config)
            if succeeded:
                ok += 1
                approved += int(status == "approved_auto")
                review += int(status == "needs_review")
            else:
                failed += 1
    return ok, failed, approved, review


def run_runtime(invocation: RuntimeInvocation) -> int:
    config = invocation.config
    files = invocation.files
    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    if total > 1 and config.jobs > 1:
        ok, failed, approved, review = process_parallel_files(
            invocation,
        )
    else:
        for index, path in enumerate(files, start=1):
            print(f"\n[{index}/{total}] {path.name}")
            try:
                outcome = process_one(path, config, invocation.configuration_bundle)
            except Exception as exc:
                outcome = _failed_input_from_exception(
                    path,
                    FailureStage.WORKER,
                    exc,
                )
            succeeded, status = _handle_input_outcome(path, outcome, config)
            if succeeded:
                ok += 1
                approved += int(status == "approved_auto")
                review += int(status == "needs_review")
            else:
                failed += 1

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1
