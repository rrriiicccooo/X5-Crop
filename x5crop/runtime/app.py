from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import errno
import os
from pathlib import Path
import sys
import uuid

from ..app_info import SCRIPT_NAME, VERSION
from ..output.filesystem import (
    FilesystemIdentity,
    OutputSupportLevel,
    identify_filesystem,
    probe_same_parent_rename,
)
from ..output.ownership import OutputOwnershipError, read_owned_output
from ..output.safe_tree import safe_remove_tree
from ..output.surface import output_directory_for
from ..output.transaction import (
    OutputTransaction,
    OutputTransactionError,
    RecoveryRequiredError,
)
from ..report.model import ReportResult
from ..report.outputs import write_report_outputs_for_result
from ..run_status import RunTerminalOutcome
from .invocation import PlannedSource, RuntimeInvocation
from .disk_budget import (
    DiskSpaceBudgetError,
    RunWideDiskBudget,
    estimate_run_reservation,
)
from .manifest import SourceTerminalRecord, write_run_manifest
from .outcome import CompletedInput, FailedInput, InputProcessingOutcome, RuntimeArtifacts
from .workflow import process_one


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def print_run_header(invocation: RuntimeInvocation, output_root: Path) -> None:
    config = invocation.config
    sources = invocation.sources
    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(sources)}")
    layout_label = "auto" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    configuration = invocation.configuration_bundle.initial_configuration
    mode_parts.append(f"configuration: {configuration.configuration_id}")
    if config.count_request.mode.value == "auto":
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    print("; ".join(mode_parts))
    if len(sources) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    print(f"output: {output_root}")


def print_report_result(result: ReportResult, artifacts: RuntimeArtifacts) -> None:
    record = result.record
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
        invocation.configuration_bundle,
        output_root,
    )


def _process_all(
    invocation: RuntimeInvocation,
    output_root: Path,
) -> tuple[tuple[PlannedSource, InputProcessingOutcome], ...]:
    sources = invocation.sources
    if len(sources) <= 1 or invocation.config.jobs <= 1:
        return tuple(
            (source, _process_source(source, invocation, output_root))
            for source in sources
        )
    try:
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=invocation.config.jobs
        )
    except (OSError, PermissionError):
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=invocation.config.jobs
        )
    outcomes: dict[int, tuple[PlannedSource, InputProcessingOutcome]] = {}
    with executor:
        futures = {
            executor.submit(_process_source, source, invocation, output_root): source
            for source in sources
        }
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = FailedInput.from_exception(source.path, exc)
            outcomes[source.input_ordinal] = (source, outcome)
    return tuple(outcomes[index] for index in sorted(outcomes))


def _terminal_record(
    source: PlannedSource,
    outcome: InputProcessingOutcome,
) -> SourceTerminalRecord:
    try:
        info = source.path.stat()
        size = int(info.st_size)
        mtime_ns = int(info.st_mtime_ns)
    except OSError:
        size = None
        mtime_ns = None
    if isinstance(outcome, FailedInput):
        return SourceTerminalRecord(
            source.input_ordinal,
            source.path.name,
            source.portable_stem,
            size,
            mtime_ns,
            RunTerminalOutcome.RUNTIME_ERROR,
            outcome.failure_stage,
            outcome.error_code,
            outcome.error_message,
            outcome.artifacts,
        )
    return SourceTerminalRecord(
        source.input_ordinal,
        source.path.name,
        source.portable_stem,
        size,
        mtime_ns,
        RunTerminalOutcome(outcome.result.record["decision"]["status"]),
        None,
        None,
        None,
        outcome.artifacts,
    )


def _discard_failed_artifacts(outcome: FailedInput, output_root: Path) -> FailedInput:
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
            raise RuntimeError("failed source exposed an artifact outside output") from exc
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
        metrics=outcome.metrics,
        error_errno=outcome.error_errno,
    )


def _filesystem_consent(
    identity: FilesystemIdentity,
    invocation: RuntimeInvocation,
    output_root: Path,
) -> str:
    if identity.support_level == OutputSupportLevel.VERIFIED_LOCAL:
        return "not_required"
    if invocation.config.allow_best_effort_output:
        return "explicit_cli_flag"
    if invocation.config.interactive:
        print()
        print("warning: output filesystem is not verified for strong publication semantics")
        print(f"target: {output_root}")
        print(f"filesystem: {identity.filesystem_kind} ({identity.reason})")
        answer = input("continue with best-effort output? [y/N]: ").strip().casefold()
        if answer in {"y", "yes"}:
            return "interactive_confirmation"
        raise ValueError("Best-effort output was not accepted")
    raise ValueError(
        "The output filesystem is not verified. Non-interactive use requires "
        "--allow-best-effort-output after reviewing the target and risk."
    )


def _cleanup_source_workspaces(output_root: Path) -> None:
    for path in output_root.glob(".x5crop-source-*"):
        safe_remove_tree(path)


def _discard_building_transaction(
    transaction: OutputTransaction,
    transaction_id: str,
    staging: Path,
    run_id: str,
) -> None:
    try:
        transaction.discard_staging(transaction_id, staging, run_id)
    except RecoveryRequiredError:
        raise
    except Exception as exc:
        raise RecoveryRequiredError(
            "Failed to discard an identified building transaction; preserving data"
        ) from exc


def run_runtime(invocation: RuntimeInvocation) -> int:
    config = invocation.config
    output_root = output_directory_for(config)
    started_at = _utc_now()
    run_id = uuid.uuid4().hex
    print_run_header(invocation, output_root)
    try:
        filesystem = identify_filesystem(output_root.parent)
        consent = _filesystem_consent(filesystem, invocation, output_root)
        estimate = estimate_run_reservation(
            tuple(source.path for source in invocation.sources),
            debug_analysis=config.debug_analysis,
        )
        with OutputTransaction(output_root) as transaction:
            probe_same_parent_rename(
                transaction.paths.target.parent,
                transaction.paths.token,
            )
            if os.path.lexists(transaction.paths.target):
                read_owned_output(transaction.paths.target)
            _budget = RunWideDiskBudget.reserve(
                transaction.paths.target.parent,
                estimate.total_bytes,
            )
            transaction_id, staging = transaction.create_staging(run_id)
            try:
                outcomes = _process_all(invocation, staging)
                _cleanup_source_workspaces(staging)
                if any(
                    isinstance(outcome, FailedInput)
                    and outcome.error_errno == errno.ENOSPC
                    for _source, outcome in outcomes
                ):
                    raise DiskSpaceBudgetError(
                        "The filesystem returned ENOSPC during staged output"
                    )
                terminals: list[SourceTerminalRecord] = []
                completed_results: list[CompletedInput] = []
                for index, (source, outcome) in enumerate(outcomes, 1):
                    print(f"\n[{index}/{len(outcomes)}] {source.path.name}")
                    if isinstance(outcome, FailedInput):
                        outcome = _discard_failed_artifacts(outcome, staging)
                    terminal = _terminal_record(source, outcome)
                    terminals.append(terminal)
                    if isinstance(outcome, FailedInput):
                        print(f"  error: {outcome.error_message}", file=sys.stderr)
                        continue
                    completed_results.append(outcome)
                    write_report_outputs_for_result(outcome.result, staging)
                    print_report_result(outcome.result, outcome.artifacts)

                valid_count = len(completed_results)
                failed_count = len(outcomes) - valid_count
                if not valid_count:
                    _discard_building_transaction(
                        transaction,
                        transaction_id,
                        staging,
                        run_id,
                    )
                    print(f"\ndone: completed=0 failed={failed_count}; prior output kept")
                    return 1
                write_run_manifest(
                    staging,
                    run_id=run_id,
                    started_at_utc=started_at,
                    finished_at_utc=_utc_now(),
                    jobs=config.jobs,
                    filesystem=filesystem,
                    best_effort_consent=consent,
                    disk_reservation=_budget.as_record(),
                    terminals=tuple(terminals),
                )
                transaction.publish(transaction_id, staging, run_id)
                print(f"\ndone: completed={valid_count} failed={failed_count}")
                return 0 if failed_count == 0 else 1
            except Exception:
                if staging.exists() and transaction.paths.journal.exists():
                    _discard_building_transaction(
                        transaction,
                        transaction_id,
                        staging,
                        run_id,
                    )
                raise
    except (RecoveryRequiredError, OutputOwnershipError, OutputTransactionError) as exc:
        print(f"transaction error: {exc}", file=sys.stderr)
        return 3
