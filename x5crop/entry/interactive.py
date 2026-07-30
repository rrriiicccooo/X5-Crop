from __future__ import annotations

from pathlib import Path

from ..app_info import SCRIPT_NAME, VERSION
from ..formats import FORMATS
from ..runtime.bootstrap import run_options
from ..runtime.limits import DIAGNOSTICS_JOB_LIMIT, STANDARD_JOB_DEFAULT
from ..runtime.options import RuntimeOptions


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
    partial_count_range = FORMATS[format_id].strip.partial_count_range
    allowed_text = " ".join(str(count) for count in partial_count_range)
    while True:
        print("partial output slots:")
        print("  return or auto = matched-holder capacity")
        print(f"  explicit slots: {allowed_text}")
        answer = normalized_input(input("count: "))
        if answer in {"", "auto"}:
            return None
        try:
            count = int(answer)
        except ValueError:
            count = -1
        if count in partial_count_range:
            return count
        print(f"unknown count: {answer}")
        print(f"use auto or one of: {allowed_text}")


def interactive_options(diagnostics: bool = False) -> RuntimeOptions:
    mode = "interactive diagnostics" if diagnostics else "launcher"
    print(f"{SCRIPT_NAME} {VERSION} {mode}")
    print(f"Folder: {Path.cwd()}")
    print()
    if diagnostics:
        print("This read-only mode writes report + Debug Analysis.")
        print("It does not copy review files or write frame TIFFs.")
    else:
        print("This creates conservative bounded-safe frame TIFF crops.")
        print("Existing output files will not be overwritten.")
    print()

    format_id = ask_format()
    partial_supported = FORMATS[format_id].strip.partial_mode_supported
    partial = (
        ask_yes_no("partial mode? [y/n, return=no]: ", default=False)
        if partial_supported
        else False
    )
    if not partial_supported:
        print(f"{format_id} supports full mode only.")
    strip_mode = "partial" if partial else "full"
    requested_count = ask_partial_count(format_id) if partial else None
    debug_analysis = True if diagnostics else ask_yes_no("debug analysis? [y/n, return=no]: ", default=False)

    print()
    if diagnostics:
        print("diagnostics: enabled")
        print("debug analysis: enabled")
    elif debug_analysis:
        print("debug analysis: enabled")
    else:
        print("debug analysis: off")
    print(
        "frame TIFF export: disabled in read-only diagnostics"
        if diagnostics
        else "frame TIFF export: enabled after the bounded safety Gate"
    )
    print(f"strip mode: {strip_mode}")
    if partial:
        print(f"count: {'auto' if requested_count is None else requested_count}")
    print()

    return RuntimeOptions(
        input_path=Path(".").resolve(),
        output_dir=None,
        format_id=format_id,
        layout="auto",
        strip_mode=strip_mode,
        requested_count=requested_count,
        page=0,
        review_dir=None,
        copy_review_files=False if diagnostics else True,
        compression="same",
        debug_analysis=debug_analysis,
        diagnostics=diagnostics,
        overwrite=False,
        report=debug_analysis or diagnostics,
        debug_errors=False,
        jobs=DIAGNOSTICS_JOB_LIMIT if diagnostics else STANDARD_JOB_DEFAULT,
    )


def run_interactive(diagnostics: bool = False) -> int:
    return run_options(interactive_options(diagnostics=diagnostics))
