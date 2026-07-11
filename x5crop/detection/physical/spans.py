from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box


@dataclass(frozen=True)
class HolderSpan:
    box: Box


@dataclass(frozen=True)
class VisibleSequenceSpan:
    box: Box


@dataclass(frozen=True)
class CropEnvelope:
    box: Box
