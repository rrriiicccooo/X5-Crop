from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SCRIPT_NAME, SUMMARY_CSV_NAME, VERSION
from ..formats import (
    COMPRESSION_CHOICES,
    DESKEW_CHOICES,
    DESKEW_FALLBACK_CHOICES,
    FORMAT_CHOICES,
    FORMATS,
    LAYOUT_CHOICES,
    STRIP_CHOICES,
)
from ..output.protection import DEFAULT_OUTPUT_BLEED
from .options import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DESKEW_MAX_ANGLE_DEGREES,
    DEFAULT_DESKEW_MIN_ANGLE_DEGREES,
    STANDARD_JOB_LIMIT,
    CliOptions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"X5 Crop V{VERSION} single-strip TIFF film cropper.")
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/x5_crop_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, help="Film format. Required unless --interactive is used.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument("--strip", choices=STRIP_CHOICES, default="full", help="full strip or partial/head mode.")
    parser.add_argument("-n", "--count", type=int, default=None, help="Override frame count.")
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--bleed", type=int, default=None, help="Bleed in pixels on all sides; overrides layout-aware defaults.")
    parser.add_argument("--bleed-x", type=int, default=None, help=f"Long-axis bleed override; default {DEFAULT_OUTPUT_BLEED.long_axis}, increased when exposure-overlap protection requires it. Horizontal scans: left/right. Vertical scans: top/bottom.")
    parser.add_argument("--bleed-y", type=int, default=None, help=f"Short-axis bleed override; default {DEFAULT_OUTPUT_BLEED.short_axis}. Horizontal scans: top/bottom. Vertical scans: left/right.")
    parser.add_argument("--deskew", choices=DESKEW_CHOICES, default="auto", help="Deskew strip before detection/export.")
    parser.add_argument("--deskew-fallback", choices=DESKEW_FALLBACK_CHOICES, default="auto", help="Fallback edge fitting for deskew angle selection. auto runs the fallback only when base deskew quality is weak; always evaluates it; off disables the fallback.")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="same", help="TIFF output compression: same for known lossless source compression, or none.")
    parser.add_argument("--deskew-min-angle", type=float, default=DEFAULT_DESKEW_MIN_ANGLE_DEGREES, help="Minimum absolute deskew angle in degrees.")
    parser.add_argument("--deskew-max-angle", type=float, default=DEFAULT_DESKEW_MAX_ANGLE_DEGREES, help="Maximum absolute deskew angle in degrees.")
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD, help="Minimum confidence for automatic export.")
    parser.add_argument("--copy-review-files", dest="copy_review_files", action="store_true", default=True, help="Copy low-confidence source TIFFs to review folder; default on.")
    parser.add_argument("--no-copy-review-files", dest="copy_review_files", action="store_false", help="Do not copy low-confidence source TIFFs to review folder.")
    parser.add_argument("--review-dir", default=None, help="Review folder; default output/needs_review.")
    parser.add_argument("--export-review", action="store_true", help="Export crops even when confidence is below threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Detect only; do not write cropped TIFFs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--report", action="store_true", help=f"Write {REPORT_JSONL_NAME} and {SUMMARY_CSV_NAME}.")
    parser.add_argument("--debug", action="store_true", help="Write lightweight JPG previews with detected outer/frame boxes.")
    parser.add_argument("--debug-analysis", action="store_true", help="Write one combined JPG with original gray, debug boxes, and separator evidence.")
    parser.add_argument("--diagnostics", action="store_true", help="Read-only diagnostics mode; implies --report --debug-analysis --dry-run --no-copy-review-files --no-reuse-analysis.")
    parser.add_argument("--no-reuse-analysis", dest="reuse_analysis", action="store_false", default=True, help="Do not reuse matching Debug Analysis report data for non-dry-run export.")
    parser.add_argument("--jobs", type=int, default=STANDARD_JOB_LIMIT, help="Parallel TIFF workers. Default 2. Normal runs cap at 2; diagnostics runs cap at 4.")
    parser.add_argument("--debug-errors", action="store_true", help="Print tracebacks on errors.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for format, mode, and Debug Analysis options.")
    parser.add_argument("--interactive-diagnostics", action="store_true", help="Prompt for diagnostics options and run read-only diagnostics.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def options_from_args(args: argparse.Namespace) -> CliOptions:
    if args.format is None:
        raise ValueError("--format is required unless --interactive is used")
    if int(args.page) < 0:
        raise ValueError("--page must be 0 or greater")
    if args.count is not None and int(args.count) not in FORMATS[str(args.format)].allowed_counts:
        allowed = ", ".join(str(x) for x in FORMATS[str(args.format)].allowed_counts)
        raise ValueError(f"--format {args.format} allows --count values: {allowed}")
    for name in ("bleed", "bleed_x", "bleed_y"):
        value = getattr(args, name)
        if value is not None and int(value) < 0:
            raise ValueError("Bleed cannot be negative")
    if not (0.0 <= float(args.confidence_threshold) <= 1.0):
        raise ValueError("--confidence-threshold must be between 0 and 1")
    if float(args.deskew_min_angle) < 0 or float(args.deskew_max_angle) <= 0:
        raise ValueError("Deskew angle limits are invalid")
    if int(args.jobs) < 1:
        raise ValueError("--jobs must be 1 or greater")

    diagnostics = bool(args.diagnostics)
    return CliOptions(
        input_path=Path(args.input).expanduser().resolve(),
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        format_id=str(args.format),
        layout=str(args.layout),
        strip_mode=str(args.strip),
        requested_count=(None if args.count is None else int(args.count)),
        page=int(args.page),
        bleed=(None if args.bleed is None else int(args.bleed)),
        bleed_x=(None if args.bleed_x is None else int(args.bleed_x)),
        bleed_y=(None if args.bleed_y is None else int(args.bleed_y)),
        deskew=str(args.deskew),
        deskew_fallback=str(args.deskew_fallback),
        deskew_min_angle=float(args.deskew_min_angle),
        deskew_max_angle=float(args.deskew_max_angle),
        confidence_threshold=float(args.confidence_threshold),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=False if diagnostics else bool(args.copy_review_files),
        export_review=bool(args.export_review),
        compression=str(args.compression),
        debug=bool(args.debug),
        debug_analysis=bool(args.debug_analysis or diagnostics),
        dry_run=bool(args.dry_run or diagnostics),
        diagnostics=diagnostics,
        overwrite=bool(args.overwrite),
        report=bool(args.report or diagnostics),
        debug_errors=bool(args.debug_errors),
        reuse_analysis=False if diagnostics else bool(args.reuse_analysis),
        jobs=int(args.jobs),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if bool(args.interactive) or bool(args.interactive_diagnostics):
            from .interactive import run_interactive

            return run_interactive(diagnostics=bool(args.interactive_diagnostics))
        from .invocation import run_entry_options

        return run_entry_options(options_from_args(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        if "args" in locals() and bool(getattr(args, "debug_errors", False)):
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
