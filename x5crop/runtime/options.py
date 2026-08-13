from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from ..geometry.layout import HORIZONTAL, VERTICAL


LAYOUT_CHOICES = ("auto", HORIZONTAL, VERTICAL)
@dataclass(frozen=True)
class RuntimeOptions:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout: str
    strip_mode: str
    requested_count: int | None
    debug_analysis: bool
    jobs: int
    interactive: bool = False
    development_detail: bool = False
