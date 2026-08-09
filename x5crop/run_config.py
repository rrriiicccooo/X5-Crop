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
    preview: bool
    allow_best_effort_output: bool
    jobs: int
    interactive: bool = False

    def __post_init__(self) -> None:
        if self.preview and not self.debug_analysis:
            raise ValueError("preview requires Debug Analysis")
