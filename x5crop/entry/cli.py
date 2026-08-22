from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMAT_CHOICES
from ..runtime.bootstrap import run_options
from ..runtime.limits import STANDARD_JOB_DEFAULT
from ..runtime.options import LAYOUT_CHOICES, RuntimeOptions
from ..run_config import DESKEW_CHOICES, DeskewMode
from .text_output import configure_entry_text_output


CLI_USAGE_ERROR_EXIT_CODE = 2


def parse_count_argument(value: str) -> int:
    normalized = value.strip().lower()
    try:
        return int(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--count must be a positive integer"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            f"X5 Crop V{VERSION} bounded conservative TIFF safe crop."
        )
    )
    parser.add_argument("input", nargs="?", default=".", help="TIFF file or directory; default current directory.")
    parser.add_argument("-o", "--output", default=None, help="Output directory; default input/x5_crop_output.")
    parser.add_argument("--format", choices=FORMAT_CHOICES, help="Film format. Required unless --interactive is used.")
    parser.add_argument("--layout", choices=LAYOUT_CHOICES, default="auto", help="auto/horizontal/vertical single-strip layout.")
    parser.add_argument(
        "-n",
        "--count",
        type=parse_count_argument,
        default=None,
        help=(
            "Positive exposure-slot count, including blank slots. Omit it to "
            "confirm the matched holder's default count."
        ),
    )
    parser.add_argument(
        "--deskew",
        choices=DESKEW_CHOICES,
        default=DeskewMode.AUTO.value,
        help=(
            "Optional cleanup after approved detection: auto applies only a "
            "small reliable rotation; off preserves source orientation."
        ),
    )
    parser.add_argument(
        "--debug-analysis",
        action="store_true",
        help=(
            "Write one three-panel JPG comparing detected and selected "
            "TOP/BOTTOM, detected and selected START/END, and final safe "
            "output envelopes. This analysis-only run writes no official "
            "TIFFs or review copies. A later normal run performs fresh "
            "detection."
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=STANDARD_JOB_DEFAULT,
        help=(
            "Parallel TIFF workers. Default 1; capped at 3."
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for format, count, deskew, and Debug Analysis options.",
    )
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def options_from_args(args: argparse.Namespace) -> RuntimeOptions:
    if args.format is None:
        raise ValueError("--format is required unless --interactive is used")
    if int(args.jobs) < 1:
        raise ValueError("--jobs must be 1 or greater")
    if args.count is not None and int(args.count) <= 0:
        raise ValueError("--count must be a positive integer")

    return RuntimeOptions(
        input_path=Path(args.input).expanduser().resolve(),
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        format_id=str(args.format),
        layout=str(args.layout),
        requested_count=(None if args.count is None else int(args.count)),
        debug_analysis=bool(args.debug_analysis),
        jobs=int(args.jobs),
        deskew_mode=DeskewMode(args.deskew),
    )


def main(argv: list[str] | None = None) -> int:
    configure_entry_text_output()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if bool(args.interactive):
            from .interactive import run_interactive

            return run_interactive()
        return run_options(options_from_args(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CLI_USAGE_ERROR_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
