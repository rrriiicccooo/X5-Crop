from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .formats import (
    ANALYSIS_CHOICES,
    COMPRESSION_CHOICES,
    DESKEW_CHOICES,
    FORMAT_CHOICES,
    LAYOUT_CHOICES,
    STRIP_CHOICES,
)


@dataclass(frozen=True)
class CliOptions:
    input_path: Path
    output_dir: Optional[Path]
    film_format: str
    layout: str
    strip_mode: str
    count_override: Optional[int]
    page: int
    bleed: Optional[int]
    bleed_x: Optional[int]
    bleed_y: Optional[int]
    deskew: str
    analysis: str
    deskew_min_angle: float
    deskew_max_angle: float
    confidence_threshold: float
    review_dir: Optional[Path]
    copy_review_files: bool
    export_review: bool
    compression: str
    debug: bool
    debug_analysis: bool
    dry_run: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    reuse_analysis: bool
    jobs: int


@dataclass(frozen=True)
class RuntimeConfig:
    input_path: Path
    output_dir: Optional[Path]
    film_format: str
    layout_auto: bool
    layout: str
    strip_mode: str
    count: int
    count_override: Optional[int]
    page: int
    bleed_x: int
    bleed_y: int
    deskew: str
    analysis: str
    deskew_min_angle: float
    deskew_max_angle: float
    confidence_threshold: float
    review_dir: Optional[Path]
    copy_review_files: bool
    export_review: bool
    compression: str
    debug: bool
    debug_analysis: bool
    dry_run: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    reuse_analysis: bool
    jobs: int


Config = RuntimeConfig


__all__ = [
    "ANALYSIS_CHOICES",
    "COMPRESSION_CHOICES",
    "DESKEW_CHOICES",
    "FORMAT_CHOICES",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "CliOptions",
    "Config",
    "RuntimeConfig",
]
