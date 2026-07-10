from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CliOptions:
    input_path: Path
    output_dir: Optional[Path]
    format_id: str
    layout: str
    strip_mode: str
    requested_count: Optional[int]
    page: int
    bleed: Optional[int]
    bleed_x: Optional[int]
    bleed_y: Optional[int]
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
