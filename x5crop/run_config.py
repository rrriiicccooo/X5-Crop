from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .configuration.model import SlotCountRequest


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout_auto: bool
    layout: str
    strip_mode: str
    count_request: SlotCountRequest
    debug_analysis: bool
    jobs: int
    interactive: bool = False
    development_detail: bool = False
