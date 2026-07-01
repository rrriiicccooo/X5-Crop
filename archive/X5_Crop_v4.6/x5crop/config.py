from __future__ import annotations

from .cli import build_parser, config_from_args, iter_input_files
from .common import (
    ANALYSIS_CHOICES,
    COMPRESSION_CHOICES,
    DESKEW_CHOICES,
    LAYOUT_CHOICES,
    STRIP_CHOICES,
    Config,
)

RuntimeConfig = Config

__all__ = [
    "ANALYSIS_CHOICES",
    "COMPRESSION_CHOICES",
    "DESKEW_CHOICES",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "Config",
    "RuntimeConfig",
    "build_parser",
    "config_from_args",
    "iter_input_files",
]
