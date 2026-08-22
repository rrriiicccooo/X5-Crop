from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .configuration.model import SlotCountRequest


class DeskewMode(str, Enum):
    OFF = "off"
    AUTO = "auto"


DESKEW_CHOICES = tuple(mode.value for mode in DeskewMode)


@dataclass(frozen=True)
class RunConfig:
    input_path: Path
    output_dir: Path | None
    format_id: str
    layout: str
    count_request: SlotCountRequest
    debug_analysis: bool
    jobs: int
    deskew_mode: DeskewMode = DeskewMode.AUTO
    development_detail: bool = False
