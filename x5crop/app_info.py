from __future__ import annotations

import sys

VERSION = "4.9"
SCRIPT_NAME = "X5_Crop.py"
TIFF_SUFFIXES = {".tif", ".tiff"}
REPORT_JSONL_NAME = "x5_crop_report.jsonl"
SUMMARY_CSV_NAME = "x5_crop_summary.csv"


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


__all__ = [
    "REPORT_JSONL_NAME",
    "SCRIPT_NAME",
    "SUMMARY_CSV_NAME",
    "TIFF_SUFFIXES",
    "VERSION",
    "configure_text_output",
]
