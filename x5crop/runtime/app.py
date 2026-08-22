"""Ordinary local runtime orchestration."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
import sys
from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..output.publication import FreshOutputDirectory, FreshOutputError
from ..output.surface import output_directory_for
from ..report.outputs import write_report_outputs_for_result
from .invocation import PlannedSource, RuntimeInvocation
from .outcome import FailedInput, InputProcessingOutcome, RuntimeArtifacts
from .workflow import process_one


def print_run_header(invocation: RuntimeInvocation, output_root: Path) -> None:
    config = invocation.config
    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(invocation.sources)}")
    parts = [f"layout: {config.layout}"]
    parts.append(
        "configuration: "
        + invocation.configuration.configuration_id
    )
    if config.count_request.user_count is not None:
        parts.append(f"count: {config.count_request.user_count}")
    if config.debug_analysis:
        parts.append("debug analysis only")
    print("; ".join(parts))
    if len(invocation.sources) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    print(f"output: {output_root}")


def print_report_result(result: dict[str, Any], artifacts: RuntimeArtifacts) -> None:
    record = result
    print(f"  status={record['decision']['status']}")
    for warning in record["output"]["warnings"]:
        print(f"  info: {warning}")
    if artifacts.frame_outputs:
        print(f"  wrote: {len(artifacts.frame_outputs)} TIFF files")
        for output in artifacts.frame_outputs:
            print(f"    {Path(output).name}")


def _process_source(
    source: PlannedSource,
    invocation: RuntimeInvocation,
    output_root: Path,
) -> InputProcessingOutcome:
    return process_one(
        source,
        invocation.config,
        invocation.configuration,
        output_root,
    )


def _process_all(
    invocation: RuntimeInvocation,
    output_root: Path,
) -> tuple[tuple[PlannedSource, InputProcessingOutcome], ...]:
    if len(invocation.sources) <= 1 or invocation.config.jobs <= 1:
        return tuple(
            (source, _process_source(source, invocation, output_root))
            for source in invocation.sources
        )
    outcomes: dict[int, tuple[PlannedSource, InputProcessingOutcome]] = {}
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=invocation.config.jobs
    ) as executor:
        futures = {
            executor.submit(
                _process_source,
                source,
                invocation,
                output_root,
            ): source
            for source in invocation.sources
        }
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = FailedInput.from_exception(source.path, exc)
            outcomes[source.input_ordinal] = (source, outcome)
    return tuple(outcomes[index] for index in sorted(outcomes))


def _discard_failed_artifacts(
    outcome: FailedInput,
    output_root: Path,
) -> FailedInput:
    for value in (
        *outcome.artifacts.frame_outputs,
        outcome.artifacts.review_copy,
        outcome.artifacts.debug_analysis,
    ):
        if value is None:
            continue
        path = Path(value)
        try:
            path.relative_to(output_root)
        except ValueError as exc:
            raise RuntimeError(
                "failed source exposed an artifact outside current staging"
            ) from exc
        if path.is_file() and not path.is_symlink():
            path.unlink()
    for directory_name in ("needs_review", "_debug_analysis"):
        directory = output_root / directory_name
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return FailedInput(
        source=outcome.source,
        failure_stage=outcome.failure_stage,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
        artifacts=RuntimeArtifacts.empty(),
        traceback_text=outcome.traceback_text,
        error_errno=outcome.error_errno,
    )


def run_runtime(invocation: RuntimeInvocation) -> int:
    output_root = output_directory_for(invocation.config)
    print_run_header(invocation, output_root)
    try:
        with FreshOutputDirectory(output_root) as publication:
            assert publication.staging is not None
            outcomes = _process_all(invocation, publication.staging)
            completed_count = 0
            failed_count = 0
            for index, (source, outcome) in enumerate(outcomes, 1):
                print(f"\n[{index}/{len(outcomes)}] {source.path.name}")
                if isinstance(outcome, FailedInput):
                    failed_count += 1
                    outcome = _discard_failed_artifacts(
                        outcome,
                        publication.staging,
                    )
                    print(f"  error: {outcome.error_message}", file=sys.stderr)
                    continue
                completed_count += 1
                write_report_outputs_for_result(
                    outcome.result,
                    publication.staging,
                )
                print_report_result(outcome.result, outcome.artifacts)

            if completed_count == 0:
                print(f"\ndone: completed=0 failed={failed_count}")
                return 1
            publication.publish()
            print(
                f"\ndone: completed={completed_count} failed={failed_count}"
            )
            return 0 if failed_count == 0 else 1
    except FreshOutputError as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 3
