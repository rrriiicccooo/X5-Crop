from __future__ import annotations

from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMATS
from ..runtime.app import run_cli_options
from .options import CliOptions


FORMAT_ALIASES = {
    "": "135",
    "135": "135",
    "dual": "135-dual",
    "135dual": "135-dual",
    "135-dual": "135-dual",
    "xpan": "xpan",
    "half": "half",
    "645": "120-645",
    "120645": "120-645",
    "120-645": "120-645",
    "66": "120-66",
    "12066": "120-66",
    "120-66": "120-66",
    "67": "120-67",
    "12067": "120-67",
    "120-67": "120-67",
}


def normalized_input(value: str) -> str:
    return "".join(value.lower().split())


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    default_label = "yes" if default else "no"
    while True:
        answer = normalized_input(input(prompt))
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print(f"use yes/no, y/n, or press return for {default_label}.")


def ask_format() -> str:
    print("choose film format:")
    print("  return or 135 = 135")
    print("  dual = 135 dual")
    print("  xpan = xpan")
    print("  half = half-frame")
    print("  645 = 120-645")
    print("  66 = 120-66")
    print("  67 = 120-67")
    print()
    while True:
        answer = normalized_input(input("format: "))
        format_id = FORMAT_ALIASES.get(answer)
        if format_id in FORMATS:
            return format_id
        print(f"unknown format: {answer}")
        print("use return/135, dual, xpan, half, 645, 66, or 67.")


def ask_partial_count(format_id: str) -> int | None:
    allowed_counts = FORMATS[format_id].allowed_counts
    allowed_text = " ".join(str(count) for count in allowed_counts)
    while True:
        print("partial count:")
        print("  return or auto = auto")
        print(f"  allowed: {allowed_text}")
        answer = normalized_input(input("count: "))
        if answer in {"", "auto"}:
            return None
        try:
            count = int(answer)
        except ValueError:
            count = -1
        if count in allowed_counts:
            return count
        print(f"unknown count: {answer}")
        print(f"use auto or one of: {allowed_text}")


def interactive_options(diagnostics: bool = False) -> CliOptions:
    print(f"{SCRIPT_NAME} {VERSION} {'diagnostics ' if diagnostics else ''}launcher")
    print(f"Folder: {Path.cwd()}")
    print()
    if diagnostics:
        print("This is a local development diagnostics launcher.")
        print("It always runs dry run + Debug Analysis + diagnostics.")
        print("No cropped TIFF files will be exported, and review files will not be copied.")
    else:
        print("This will process TIFF files in this folder.")
        print("Existing output files will not be overwritten.")
    print()

    format_id = ask_format()
    partial = ask_yes_no("partial mode? [y/n, return=no]: ", default=False)
    strip_mode = "partial" if partial else "full"
    requested_count = ask_partial_count(format_id) if partial else None
    debug_analysis = True if diagnostics else ask_yes_no("debug analysis? [y/n, return=no]: ", default=False)

    print()
    if diagnostics:
        print("diagnostics: enabled")
        print("debug analysis: enabled")
        print("dry run: enabled")
    elif debug_analysis:
        print("debug analysis: enabled")
        print("dry run: no cropped TIFF files will be written.")
    else:
        print("debug analysis: off")
    print(f"strip mode: {strip_mode}")
    if partial:
        print(f"count: {'auto' if requested_count is None else requested_count}")
    print()

    return CliOptions(
        input_path=Path(".").resolve(),
        output_dir=None,
        format_id=format_id,
        layout="auto",
        strip_mode=strip_mode,
        requested_count=requested_count,
        page=0,
        bleed=None,
        bleed_x=None,
        bleed_y=None,
        deskew="auto",
        deskew_fallback="auto",
        deskew_min_angle=0.03,
        deskew_max_angle=2.0,
        confidence_threshold=0.85,
        review_dir=None,
        copy_review_files=False if diagnostics else True,
        export_review=False,
        compression="same",
        debug=False,
        debug_analysis=debug_analysis,
        dry_run=debug_analysis or diagnostics,
        diagnostics=diagnostics,
        overwrite=False,
        report=debug_analysis or diagnostics,
        debug_errors=False,
        reuse_analysis=False if diagnostics else True,
        jobs=4 if diagnostics else 2,
    )


def run_interactive(diagnostics: bool = False) -> int:
    return run_cli_options(interactive_options(diagnostics=diagnostics))
