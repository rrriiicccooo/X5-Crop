from __future__ import annotations

from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMATS
from ..runtime.bootstrap import SlotCountPreflightError, run_options
from ..runtime.limits import STANDARD_JOB_DEFAULT
from ..runtime.options import RuntimeOptions
from ..run_config import DeskewMode


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


def ask_count(format_id: str) -> int | None:
    maximum = FORMATS[format_id].maximum_full_count
    while True:
        answer = normalized_input(input(f"count [default {maximum}]: "))
        if not answer:
            return None
        try:
            count = int(answer)
        except ValueError:
            count = -1
        if 1 <= count <= maximum:
            return count
        print(f"unknown count: {answer}")
        print(f"use 1-{maximum}, or press return for the matched-holder default.")


def interactive_options(
    *,
    selected_format_id: str | None = None,
    selected_debug_analysis: bool | None = None,
    selected_deskew_mode: DeskewMode | None = None,
) -> RuntimeOptions:
    if selected_format_id is None:
        print(f"{SCRIPT_NAME} {VERSION} launcher")
        print(f"Folder: {Path.cwd()}")
        print()
        print("This creates conservative bounded-safe frame TIFF crops.")
        print("The output must be a fresh directory; existing output is never replaced.")
        print()
    format_id = selected_format_id or ask_format()
    requested_count = ask_count(format_id)
    if selected_deskew_mode is None:
        deskew_enabled = ask_yes_no(
            "lightweight deskew after approval? [y/n, return=yes]: ",
            default=True,
        )
        deskew_mode = DeskewMode.AUTO if deskew_enabled else DeskewMode.OFF
    else:
        deskew_mode = selected_deskew_mode
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
        print("fresh detection: enabled")
        print("frame TIFF export: enabled after the bounded safety Gate")
    print(
        "count: matched-holder default"
        if requested_count is None
        else f"count: {requested_count}"
    )
    print(f"deskew cleanup: {deskew_mode.value}")
    print()

    return RuntimeOptions(
        input_path=Path(".").resolve(),
        output_dir=None,
        format_id=format_id,
        layout="auto",
        requested_count=requested_count,
        debug_analysis=debug_analysis,
        jobs=STANDARD_JOB_DEFAULT,
        deskew_mode=deskew_mode,
    )


def run_interactive() -> int:
    options = interactive_options()
    while True:
        try:
            return run_options(options)
        except SlotCountPreflightError as exc:
            print()
            print(str(exc))
            print("re-enter count for this batch.")
            options = interactive_options(
                selected_format_id=options.format_id,
                selected_debug_analysis=options.debug_analysis,
                selected_deskew_mode=options.deskew_mode,
            )
