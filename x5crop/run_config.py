from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CompressionMode = Literal["none", "same"]


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout_auto: bool
    layout: str
    strip_mode: str
    requested_count: int | None
    page: int
    bleed_x: int
    bleed_y: int
    review_dir: Path | None
    copy_review_files: bool
    export_review: bool
    compression: CompressionMode
    debug: bool
    debug_analysis: bool
    dry_run: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    jobs: int
