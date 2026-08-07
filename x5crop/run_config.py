from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .configuration.model import FrameCountRequest


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout_auto: bool
    layout: str
    strip_mode: str
    count_request: FrameCountRequest
    debug_analysis: bool
    allow_best_effort_output: bool
    jobs: int
    interactive: bool = False
