from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box


@dataclass(frozen=True)
class OutputGeometry:
    outer: Box
    frames: tuple[Box, ...]
