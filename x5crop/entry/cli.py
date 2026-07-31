from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from ..app_info import REPORT_JSONL_NAME, SCRIPT_NAME, SUMMARY_CSV_NAME, VERSION
from ..formats import FORMAT_CHOICES
from ..runtime.bootstrap import run_options
from ..runtime.limits import STANDARD_JOB_DEFAULT
from ..runtime.options import (
    COMPRESSION_CHOICES,
    LAYOUT_CHOICES,
    RuntimeOptions,
)
from ..strip_modes import STRIP_MODES
from .text_output import configure_entry_text_output


CLI_USAGE_ERROR_EXIT_CODE = 2


def parse_count_argument(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized == "auto":
        return None
    try:
        return int(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--count must be a positive integer or auto"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"X5 Crop V{VERSION} bounded conservative TIFF safe crop."
        )
    )
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/x5_crop_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, help="Film format. Required unless --interactive is used.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument(
        "--strip",
        choices=STRIP_MODES,
        default="full",
        help="Holder occupancy: full when film fills the holder, partial when it does not.",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=parse_count_argument,
        default=None,
        help=(
            "Partial output slots: a positive integer is explicit; auto or "
            "omission uses matched-holder capacity. Full uses the format default."
        ),
    )
    parser.add_argument("--page", type=int, default=0, help="TIFF page index; default 0.")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="same", help="Output TIFF lossless compression: preserve source or write uncompressed.")
    parser.add_argument("--copy-review-files", dest="copy_review_files", action="store_true", default=True, help="Copy source TIFFs that require review to the review folder; default on.")
    parser.add_argument("--no-copy-review-files", dest="copy_review_files", action="store_false", help="Do not copy source TIFFs that require review.")
    parser.add_argument("--review-dir", default=None, help="Review folder; default output/needs_review.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--report", action="store_true", help=f"Write {REPORT_JSONL_NAME} and {SUMMARY_CSV_NAME}.")
    parser.add_argument(
        "--debug-analysis",
        action="store_true",
        help=(
            "Write one four-layer JPG with source authority, pixel "
            "measurements, selected source geometry, and protected output."
        ),
    )
    parser.add_argument("--diagnostics", action="store_true", help="Read-only diagnostics mode; implies --report --debug-analysis --no-copy-review-files.")
    parser.add_argument(
        "--jobs",
        type=int,
        default=STANDARD_JOB_DEFAULT,
        help=(
            "Parallel TIFF workers. Default 2. Normal runs cap at 3; "
            "diagnostics runs cap at 4."
        ),
    )
    parser.add_argument("--debug-errors", action="store_true", help="Print tracebacks on errors.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for format, mode, and Debug Analysis options.")
    parser.add_argument("--interactive-diagnostics", action="store_true", help="Prompt for diagnostics options and run read-only diagnostics.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def options_from_args(args: argparse.Namespace) -> RuntimeOptions:
    if args.format is None:
        raise ValueError("--format is required unless --interactive is used")
    if int(args.page) < 0:
        raise ValueError("--page must be 0 or greater")
    if int(args.jobs) < 1:
        raise ValueError("--jobs must be 1 or greater")

    diagnostics = bool(args.diagnostics)
    return RuntimeOptions(
        input_path=Path(args.input).expanduser().resolve(),
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        format_id=str(args.format),
        layout=str(args.layout),
        strip_mode=str(args.strip),
        requested_count=(None if args.count is None else int(args.count)),
        page=int(args.page),
        review_dir=Path(args.review_dir).expanduser().resolve() if args.review_dir else None,
        copy_review_files=False if diagnostics else bool(args.copy_review_files),
        compression=str(args.compression),
        debug_analysis=bool(args.debug_analysis or diagnostics),
        diagnostics=diagnostics,
        overwrite=bool(args.overwrite),
        report=bool(args.report or diagnostics),
        debug_errors=bool(args.debug_errors),
        jobs=int(args.jobs),
    )


def main(argv: list[str] | None = None) -> int:
    configure_entry_text_output()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if bool(args.interactive) or bool(args.interactive_diagnostics):
            from .interactive import run_interactive

            return run_interactive(diagnostics=bool(args.interactive_diagnostics))
        return run_options(options_from_args(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        if "args" in locals() and bool(getattr(args, "debug_errors", False)):
            traceback.print_exc()
        return CLI_USAGE_ERROR_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
