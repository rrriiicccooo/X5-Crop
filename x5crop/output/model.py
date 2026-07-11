from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, CropEnvelope


@dataclass(frozen=True)
class OutputGeometry:
    crop_envelope: CropEnvelope
    frames: tuple[Box, ...]
