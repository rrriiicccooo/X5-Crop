from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..geometry.layout import HORIZONTAL, VERTICAL
from ..run_config import CompressionMode


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
    review_dir: Optional[Path]
    copy_review_files: bool
    compression: CompressionMode
    debug_analysis: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    jobs: int
