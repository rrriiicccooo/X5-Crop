from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMAT_CHOICES
from ..runtime.bootstrap import run_options
from ..runtime.limits import STANDARD_JOB_DEFAULT
from ..runtime.options import LAYOUT_CHOICES, RuntimeOptions
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
    parser.add_argument(
        "--debug-analysis",
        action="store_true",
        help=(
            "Write one three-panel JPG preserving four V5 fact layers: "
            "source authority, pixel evidence, canonical placement, and "
            "protected output."
        ),
    )
    parser.add_argument(
        "--allow-best-effort-output",
        action="store_true",
        help=(
            "Explicitly accept weaker output transaction semantics on an "
            "unverified filesystem in non-interactive use."
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=STANDARD_JOB_DEFAULT,
        help=(
            "Parallel TIFF workers. Default 2; capped at 3."
        ),
    )
    parser.add_argument("--interactive", action="store_true", help="Prompt for format, mode, and Debug Analysis options.")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME} {VERSION}")
    return parser


def options_from_args(args: argparse.Namespace) -> RuntimeOptions:
    if args.format is None:
        raise ValueError("--format is required unless --interactive is used")
    if int(args.jobs) < 1:
        raise ValueError("--jobs must be 1 or greater")

    return RuntimeOptions(
        input_path=Path(args.input).expanduser().resolve(),
        output_dir=Path(args.output).expanduser().resolve() if args.output else None,
        format_id=str(args.format),
        layout=str(args.layout),
        strip_mode=str(args.strip),
        requested_count=(None if args.count is None else int(args.count)),
        debug_analysis=bool(args.debug_analysis),
        allow_best_effort_output=bool(args.allow_best_effort_output),
        jobs=int(args.jobs),
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
