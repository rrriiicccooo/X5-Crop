from __future__ import annotations

from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMATS
from ..runtime.bootstrap import SlotCountPreflightError, run_options
from ..runtime.limits import STANDARD_JOB_DEFAULT
from ..runtime.options import RuntimeOptions


FORMAT_SELECTIONS = {
    "": "135",
    "135": "135",
    "dual": "135-dual",
    "xpan": "xpan",
    "half": "half",
    "645": "120-645",
    "66": "120-66",
    "67": "120-67",
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
        format_id = FORMAT_SELECTIONS.get(answer)
        if format_id in FORMATS:
            return format_id
        print(f"unknown format: {answer}")
        print("use return/135, dual, xpan, half, 645, 66, or 67.")


def ask_partial_count(format_id: str) -> int:
    partial_count_range = FORMATS[format_id].interactive_partial_counts
    allowed_text = " ".join(str(count) for count in partial_count_range)
    while True:
        print("partial output slots:")
        print(f"  explicit slots: {allowed_text}")
        answer = normalized_input(input("count: "))
        try:
            count = int(answer)
        except ValueError:
            count = -1
        if count in partial_count_range:
            return count
        print(f"unknown count: {answer}")
        print(f"use one of: {allowed_text}")


def interactive_options(
    *,
    selected_format_id: str | None = None,
    selected_debug_analysis: bool | None = None,
) -> RuntimeOptions:
    if selected_format_id is None:
        print(f"{SCRIPT_NAME} {VERSION} launcher")
        print(f"Folder: {Path.cwd()}")
        print()
        print("This creates conservative bounded-safe frame TIFF crops.")
        print("A complete new output replaces the prior X5 Crop-owned output.")
        print()
    format_id = selected_format_id or ask_format()
    partial_supported = FORMATS[format_id].partial_mode_supported
    partial = (
        ask_yes_no("partial mode? [y/n, return=no]: ", default=False)
        if partial_supported
        else False
    )
    if not partial_supported:
        print(f"{format_id} supports full mode only.")
    strip_mode = "partial" if partial else "full"
    requested_count = ask_partial_count(format_id) if partial else None
    debug_analysis = (
        ask_yes_no(
            "debug analysis? [y/n, return=no]: ",
            default=False,
        )
        if selected_debug_analysis is None
        else selected_debug_analysis
    )

    print()
    if debug_analysis:
        print("debug analysis: enabled")
        print("analysis only: no cropped TIFF files will be written")
    else:
        print("debug analysis: off")
        print("matching analysis report: reused automatically when valid")
        print("frame TIFF export: enabled after the bounded safety Gate")
    print(f"strip mode: {strip_mode}")
    if partial:
        print(f"count: {requested_count}")
    print()

    return RuntimeOptions(
        input_path=Path(".").resolve(),
        output_dir=None,
        format_id=format_id,
        layout="auto",
        strip_mode=strip_mode,
        requested_count=requested_count,
        debug_analysis=debug_analysis,
        allow_best_effort_output=False,
        jobs=STANDARD_JOB_DEFAULT,
        interactive=True,
    )


def run_interactive() -> int:
    options = interactive_options()
    while True:
        try:
            return run_options(options)
        except SlotCountPreflightError as exc:
            print()
            print(str(exc))
            print("re-enter mode and count for this batch.")
            options = interactive_options(
                selected_format_id=options.format_id,
                selected_debug_analysis=options.debug_analysis,
            )
