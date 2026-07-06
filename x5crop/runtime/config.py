from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
    deskew_fallback: str
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


__all__ = [
    "RuntimeConfig",
]
