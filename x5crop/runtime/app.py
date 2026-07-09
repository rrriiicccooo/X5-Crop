from __future__ import annotations

import sys
import traceback
import concurrent.futures
from dataclasses import replace
from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..domain import ProcessResult
from ..entry.options import CliOptions
from ..report.outputs import write_report_outputs_for_result
from ..policies.runtime.bundle import DetectionPolicyBundle
from .config import RuntimeConfig
from .input_probe import runtime_config_from_options
from .workflow import (
    process_one,
    process_one_worker,
)


def print_run_header(config: RuntimeConfig, files: list[Path]) -> None:
    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(files)}")
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    policy = DetectionPolicyBundle.for_format_mode(config.film_format, config.strip_mode).initial_policy
    mode_parts.append(f"policy: {policy.policy_id}")
    if config.strip_mode == "partial" and config.count_override is None:
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    if config.diagnostics:
        mode_parts.append("diagnostics")
    if config.dry_run:
        mode_parts.append("dry run")
    print("; ".join(mode_parts))
    print(f"threshold: {config.confidence_threshold:.2f}; deskew fallback: {config.deskew_fallback}")
    if len(files) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    if config.output_dir is not None:
        print(f"output: {config.output_dir}")


def print_process_result(result: ProcessResult, config: RuntimeConfig) -> None:
    print(f"  status={result.status} confidence={result.confidence:.3f}")
    for warning in result.warnings:
        print(f"  info: {warning}")
    if result.output_files:
        print(f"  wrote: {len(result.output_files)} TIFF files")
        if config.output_dir is not None:
            for out in result.output_files:
                print(f"    {Path(out).name}")


def process_parallel_files(
    files: list[Path],
    config: RuntimeConfig,
    worker_config: RuntimeConfig,
) -> tuple[int, int, int, int]:
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
            executor.submit(process_one_worker, path, worker_config): path
            for path in files
        }
        for index, future in enumerate(concurrent.futures.as_completed(future_to_path), start=1):
            path = future_to_path[future]
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = future.result()
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_report_outputs_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()
    return ok, failed, approved, review


def run_runtime(config: RuntimeConfig, files: list[Path]) -> int:
    ok = 0
    failed = 0
    approved = 0
    review = 0
    total = len(files)
    worker_config = replace(config, report=False)
    if total > 1 and config.jobs > 1:
        ok, failed, approved, review = process_parallel_files(files, config, worker_config)
    else:
        for index, path in enumerate(files, start=1):
            print(f"\n[{index}/{total}] {path.name}")
            try:
                result = process_one_worker(path, worker_config)
                ok += 1
                approved += int(result.status == "approved_auto")
                review += int(result.status == "needs_review")
                write_report_outputs_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1


def run_cli_options(options: CliOptions) -> int:
    config, files = runtime_config_from_options(options)
    print_run_header(config, files)
    return run_runtime(config, files)


__all__ = [
    "print_run_header",
    "process_one",
    "process_one_worker",
    "process_parallel_files",
    "run_cli_options",
    "run_runtime",
]
