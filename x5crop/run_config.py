from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .configuration.model import FrameCountRequest

CompressionMode = Literal["none", "same"]


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout_auto: bool
    layout: str
    strip_mode: str
    count_request: FrameCountRequest
    page: int
    review_dir: Path | None
    copy_review_files: bool
    compression: CompressionMode
    debug: bool
    debug_analysis: bool
    diagnostics: bool
    overwrite: bool
    report: bool
    debug_errors: bool
    jobs: int
