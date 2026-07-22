from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..output.model import AxisBleedParameters
from ..geometry.layout import HORIZONTAL, VERTICAL
from ..run_config import CompressionMode


DEFAULT_OUTPUT_BLEED = AxisBleedParameters(long_axis=20, short_axis=10)
LAYOUT_CHOICES = ("auto", HORIZONTAL, VERTICAL)
COMPRESSION_CHOICES: tuple[CompressionMode, ...] = ("none", "same")


@dataclass(frozen=True)
class RuntimeOptions:
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
    review_dir: Optional[Path]
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
