from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..geometry.layout import HORIZONTAL, VERTICAL
from ..run_config import DeskewMode


LAYOUT_CHOICES = ("auto", HORIZONTAL, VERTICAL)


@dataclass(frozen=True)
class RuntimeOptions:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout: str
    requested_count: int | None
    debug_analysis: bool
    jobs: int
    deskew_mode: DeskewMode = DeskewMode.AUTO
    development_detail: bool = False
