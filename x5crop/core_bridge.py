from __future__ import annotations

import contextlib
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from .core import x5_split_engine as engine

TIFF_SUFFIXES = {".tif", ".tiff"}
LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class EngineOptions:
    count: int = 6
    bleed: int = 10
    deskew: str = "auto"
    analysis_enhance: str = "auto"
    preset: str = "standard"
    outer_x_detect: str = "auto"
    outer_refine: str = "auto"
    grid_fit: str = "auto"
    frame_size_fit: str = "auto"
    debug: bool = True
    debug_analysis: bool = False
    report: bool = True
    overwrite: bool = False
    equal_split: bool = False
    compression: str = "same"


def discover_tiffs(path: Path) -> list[Path]:
    path = path.expanduser().resolve()
    if path.is_file():
        return [path] if path.suffix.lower() in TIFF_SUFFIXES else []
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    return []


def default_output_dir(input_path: Path) -> Path:
    input_path = input_path.expanduser().resolve()
    if input_path.is_dir():
        return input_path / "split_output"
    return input_path.parent / "split_output"


def cli_args(input_path: Path, output_dir: Optional[Path], options: EngineOptions, dry_run: bool) -> list[str]:
    args: list[str] = [str(input_path)]
    if output_dir is not None:
        args += ["-o", str(output_dir)]
    args += ["--count", str(options.count)]
    args += ["--bleed", str(options.bleed)]
    args += ["--deskew", options.deskew]
    args += ["--analysis-enhance", options.analysis_enhance]
    args += ["--outer-x-detect", options.outer_x_detect]
    args += ["--outer-refine", options.outer_refine]
    args += ["--grid-fit", options.grid_fit]
    args += ["--frame-size-fit", options.frame_size_fit]
    args += ["--compression", options.compression]

    # Presets intentionally stay conservative. They mainly reduce how often the
    # heavy enhanced candidate runs; difficult files should be flagged for review
    # instead of forcing every file through slow fallback logic.
    if options.preset == "fast":
        args += ["--analysis-enhance", "off"]
    elif options.preset == "underexposed":
        args += [
            "--analysis-enhance", "strict",
            "--outer-refine", "strict",
            "--grid-fit", "strict",
            "--frame-size-fit", "strict",
            "--frame-size-min-samples", "1",
            "--frame-size-tolerance-ratio", "0.02",
        ]
    elif options.preset == "review":
        # Analysis mode with richer debug output. Export still follows user flags.
        args += ["--debug-analysis"]

    if options.equal_split:
        args.append("--equal-split")
    if options.debug:
        args.append("--debug")
    if options.debug_analysis:
        args.append("--debug-analysis")
    if options.report:
        args.append("--report")
    if options.overwrite:
        args.append("--overwrite")
    if dry_run:
        args.append("--dry-run")
    return args


class _CallbackStream:
    def __init__(self, callback: Optional[LogCallback]) -> None:
        self.callback = callback
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self.callback is not None:
                self.callback(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer and self.callback is not None:
            self.callback(self._buffer)
        self._buffer = ""


def _parse_config_from_cli(args: list[str]):
    parser = engine.build_parser()
    return engine.config_from_args(parser.parse_args(args))


def run_engine(
    input_path: Path,
    output_dir: Optional[Path],
    options: EngineOptions,
    dry_run: bool,
    log_callback: Optional[LogCallback] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> tuple[int, int, Path]:
    args = cli_args(input_path, output_dir, options, dry_run)
    config = _parse_config_from_cli(args)
    files = engine.iter_input_files(config.input_path)
    if not files:
        raise RuntimeError(f"未找到 TIFF 文件：{config.input_path}")

    out_dir = engine.output_directory_for(files[0], config) if len(files) == 1 else (
        config.output.resolve() if config.output else config.input_path / "split_output"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    if log_callback:
        log_callback(f"X5 Crop Core: {engine.VERSION}")
        log_callback(f"输入：{config.input_path}")
        log_callback(f"文件数：{len(files)}")
        log_callback(f"输出：{out_dir}")
        log_callback(f"preset={options.preset}, deskew={config.deskew}, analysis={config.analysis_enhance}, bleed={config.bleed_x}/{config.bleed_y}")

    ok = 0
    fail = 0
    stream = _CallbackStream(log_callback)
    for index, file in enumerate(files, start=1):
        if progress_callback:
            progress_callback(index - 1, len(files), file.name)
        if log_callback:
            log_callback("")
            log_callback(f"[{file.name}]")
        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                result = engine.process_one(file, config)
                for warning in result.warnings:
                    print(f"  警告：{warning}")
            ok += 1
        except Exception as exc:
            fail += 1
            if log_callback:
                log_callback(f"  ✗ 失败：{file.name} — {exc}")
                if os.environ.get(engine.TRACEBACK_ENV) == "1":
                    log_callback(traceback.format_exc())
        finally:
            stream.flush()
            if progress_callback:
                progress_callback(index, len(files), file.name)

    if log_callback:
        log_callback("")
        log_callback(f"完成：成功 {ok}，失败 {fail}")
    return ok, fail, out_dir


def read_report(output_dir: Path) -> list[dict]:
    report_path = output_dir / "split_report.jsonl"
    if not report_path.exists():
        return []
    rows: list[dict] = []
    for line in report_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def debug_preview_for(output_dir: Path, source_file: Path) -> Path:
    return output_dir / "_debug" / f"{source_file.stem}_debug.jpg"


def analysis_preview_for(output_dir: Path, source_file: Path) -> Path:
    return output_dir / "_debug" / f"{source_file.stem}_analysis.jpg"
