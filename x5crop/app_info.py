from __future__ import annotations

import sys

VERSION = "4.9"
SCRIPT_NAME = "X5_Crop.py"
TIFF_SUFFIXES = {".tif", ".tiff"}


def configure_text_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except Exception:
            pass


configure_text_output()


__all__ = ["SCRIPT_NAME", "TIFF_SUFFIXES", "VERSION", "configure_text_output"]
