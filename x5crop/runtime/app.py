from __future__ import annotations

import sys
import traceback
import concurrent.futures
from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..report.model import ReportResult
from ..report.outputs import write_report_outputs_for_result
from ..run_config import RunConfig
from .invocation import RuntimeInvocation
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
                result = future.result()
                ok += 1
                approved += int(
                    result.record["decision"]["status"] == "approved_auto"
                )
                review += int(
                    result.record["decision"]["status"] == "needs_review"
                )
                write_report_outputs_for_result(result, config)
                print_report_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()
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
                result = process_one(path, config, invocation.configuration_bundle)
                ok += 1
                approved += int(
                    result.record["decision"]["status"] == "approved_auto"
                )
                review += int(
                    result.record["decision"]["status"] == "needs_review"
                )
                write_report_outputs_for_result(result, config)
                print_report_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1
