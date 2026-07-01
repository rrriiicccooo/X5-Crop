from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .format_specs import (
    CONTENT_ASPECTS_HORIZONTAL,
    FORMAT_CHOICES,
    FORMATS,
    STRIP_CHOICES,
    FilmFormat,
)
from .policies.parameters import FormatParameters, format_parameters


class FormatId(str, Enum):
    FORMAT_135 = "135"
    FORMAT_135_DUAL = "135-dual"
    HALF = "half"
    XPAN = "xpan"
    FORMAT_120_645 = "120-645"
    FORMAT_120_66 = "120-66"
    FORMAT_120_67 = "120-67"


class StripMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


@dataclass(frozen=True)
class FormatSpec:
    format_id: FormatId
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str
    horizontal_content_aspect: float | None
    parameters: FormatParameters


def format_spec(format_id: str | FormatId) -> FormatSpec:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    fmt = FORMATS[key]
    return FormatSpec(
        format_id=FormatId(key),
        name=fmt.name,
        default_count=fmt.default_count,
        allowed_counts=fmt.allowed_counts,
        family=fmt.family,
        horizontal_content_aspect=CONTENT_ASPECTS_HORIZONTAL.get(key),
        parameters=format_parameters(key),
    )


__all__ = [
    "CONTENT_ASPECTS_HORIZONTAL",
    "FORMAT_CHOICES",
    "FORMATS",
    "STRIP_CHOICES",
    "FilmFormat",
    "FormatId",
    "FormatSpec",
    "FormatParameters",
    "StripMode",
    "format_spec",
    "format_parameters",
]
