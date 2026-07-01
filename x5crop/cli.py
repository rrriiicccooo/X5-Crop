from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import replace
from pathlib import Path

import tifffile

from .app_info import SCRIPT_NAME, TIFF_SUFFIXES, VERSION
from .config import Config
from .format_specs import (
    ANALYSIS_CHOICES,
    COMPRESSION_CHOICES,
    DESKEW_CHOICES,
    FORMAT_CHOICES,
    FORMATS,
    LAYOUT_CHOICES,
    STRIP_CHOICES,
)
from .geometry import infer_layout
from .policies.registry import get_detection_policy
from .reports import write_reports_for_result
from .utils import spatial_shape_from_shape
from .workflow import (
    print_process_result,
    process_one,
    process_one_worker,
    process_parallel_files,
)


def iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in TIFF_SUFFIXES:
            raise ValueError(f"Input is not a TIFF: {path}")
        return [path]
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    raise ValueError(f"Path does not exist: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"X5 Crop V{VERSION} single-strip TIFF film cropper.")
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/x5_crop_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, required=True, help="Film format; launchers pass this explicitly.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument("--strip", choices=STRIP_CHOICES, default="full", help="full strip or partial/head mode.")
    parser.add_argument("-n", "--count", type=int, default=None, help="Override frame count.")
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--bleed", type=int, default=None, help="Bleed in pixels on all sides; overrides layout-aware defaults.")
    parser.add_argument("--bleed-x", type=int, default=None, help="Long-axis bleed override; default 20, or 50 when overlap/continuous-content risk is detected. Horizontal scans: left/right. Vertical scans: top/bottom.")
    parser.add_argument("--bleed-y", type=int, default=None, help="Short-axis bleed override; default 10. Horizontal scans: top/bottom. Vertical scans: left/right.")
    parser.add_argument("--deskew", choices=DESKEW_CHOICES, default="auto", help="Deskew strip before detection/export.")
    parser.add_argument("--analysis", choices=ANALYSIS_CHOICES, default="auto", help="Enhanced analysis for separator assist and deskew angle selection. auto runs enhanced separator only on weak separator evidence and enhanced deskew only when base deskew quality is weak; always enables enhanced passes; off disables enhanced analysis.")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="same", help="TIFF output compression: same for known lossless source compression, or none.")
    parser.add_argument("--deskew-min-angle", type=float, default=0.03, help="Minimum absolute deskew angle in degrees.")
    parser.add_argument("--deskew-max-angle", type=float, default=2.0, help="Maximum absolute deskew angle in degrees.")
    parser.add_argument("--confidence-threshold", type=float, default=0.85, help="Minimum confidence for automatic export.")
    parser.add_argument("--copy-review-files", dest="copy_review_files", action="store_true", default=True, help="Copy low-confidence source TIFFs to review folder; default on.")
    parser.add_argument("--no-copy-review-files", dest="copy_review_files", action="store_false", help="Do not copy low-confidence source TIFFs to review folder.")
    parser.add_argument("--review-dir", default=None, help="Review folder; default output/needs_review.")
    parser.add_argument("--export-review", action="store_true", help="Export crops even when confidence is below threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Detect only; do not write cropped TIFFs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--report", action="store_true", help="Write split_report.jsonl and split_summary.csv.")
    parser.add_argument("--debug", action="store_true", help="Write lightweight JPG previews with detected outer/frame boxes.")
    parser.add_argument("--debug-analysis", action="store_true", help="Write one combined JPG with original gray, debug boxes, and separator evidence.")
    parser.add_argument("--diagnostics", action="store_true", help="Write read-only diagnostics and diagnostic Debug Analysis overlays. Does not change crop output.")
    parser.add_argument("--no-reuse-analysis", dest="reuse_analysis", action="store_false", default=True, help="Do not reuse matching Debug Analysis report data for non-dry-run export.")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel TIFF workers. Default 2. Normal runs cap at 2; diagnostics runs cap at 4.")
    parser.add_argument("--debug-errors", action="store_true", help="Print tracebacks on errors.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    input_path = Path(args.input).expanduser().resolve()
    files_for_probe = [input_path] if input_path.is_file() else iter_input_files(input_path)
    first_file = next(iter(files_for_probe), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {input_path}")
    with tifffile.TiffFile(first_file) as tif:
        shape = tuple(int(x) for x in tif.pages[int(args.page)].shape)
    height, width = spatial_shape_from_shape(shape)

    film_format = str(args.format)
    fmt = FORMATS[film_format]
    count = int(fmt.default_count if args.count is None else args.count)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")
    layout_auto = str(args.layout) == "auto"
    layout = infer_layout(width, height) if layout_auto else str(args.layout)
    bleed_x_default = 20 if args.bleed is None else int(args.bleed)
    bleed_y_default = 10 if args.bleed is None else int(args.bleed)
    bleed_x = int(bleed_x_default if args.bleed_x is None else args.bleed_x)
    bleed_y = int(bleed_y_default if args.bleed_y is None else args.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold must be between 0 and 1")
    if float(args.deskew_min_angle) < 0 or float(args.deskew_max_angle) <= 0:
        raise ValueError("Deskew angle limits are invalid")
    jobs_cap = 4 if bool(args.diagnostics) else 2
    jobs = max(1, min(jobs_cap, int(args.jobs)))
    return Config(
        input_path=input_path,
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        film_format=film_format,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=str(args.strip),
        count=count,
        count_override=(None if args.count is None else int(args.count)),
        page=int(args.page),
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        deskew=str(args.deskew),
        analysis=str(args.analysis),
        deskew_min_angle=float(args.deskew_min_angle),
        deskew_max_angle=float(args.deskew_max_angle),
        confidence_threshold=float(args.confidence_threshold),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=bool(args.copy_review_files),
        export_review=bool(args.export_review),
        compression=str(args.compression),
        debug=bool(args.debug),
        debug_analysis=bool(args.debug_analysis),
        dry_run=bool(args.dry_run),
        diagnostics=bool(args.diagnostics),
        overwrite=bool(args.overwrite),
        report=bool(args.report),
        debug_errors=bool(args.debug_errors),
        reuse_analysis=bool(args.reuse_analysis),
        jobs=jobs,
    )


def main() -> int:
    parser = build_parser()
    try:
        config = config_from_args(parser.parse_args())
        files = iter_input_files(config.input_path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"{SCRIPT_NAME} {VERSION}")
    print(f"input: {config.input_path}")
    print(f"files: {len(files)}")
    layout_label = f"auto(probe={config.layout})" if config.layout_auto else config.layout
    mode_parts = [f"layout: {layout_label}", f"strip: {config.strip_mode}"]
    mode_parts.append(f"policy: {get_detection_policy(config.film_format, config.strip_mode).policy_id}")
    if config.strip_mode == "partial" and config.count_override is None:
        mode_parts.append("count: auto")
    if config.debug_analysis:
        mode_parts.append("debug analysis")
    if config.dry_run:
        mode_parts.append("dry run")
    print("; ".join(mode_parts))
    print(f"threshold: {config.confidence_threshold:.2f}; analysis: {config.analysis}")
    if len(files) > 1 and config.jobs > 1:
        print(f"parallel: {config.jobs} workers")
    if config.output_dir is not None:
        print(f"output: {config.output_dir}")

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
                write_reports_for_result(result, config)
                print_process_result(result, config)
            except Exception as exc:
                failed += 1
                print(f"  error: {exc}", file=sys.stderr)
                if config.debug_errors:
                    traceback.print_exc()

    print(f"\ndone: ok={ok} failed={failed} approved={approved} review={review}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
