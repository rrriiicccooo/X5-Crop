from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box


@dataclass(frozen=True)
class HolderSpan:
    box: Box


@dataclass(frozen=True)
class FilmSpan:
    box: Box
