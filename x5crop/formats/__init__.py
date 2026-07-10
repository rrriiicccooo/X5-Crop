from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .descriptions import FORMAT_DESCRIPTIONS, FormatDescription


class FormatId(str, Enum):
    STANDARD_STRIP = "135"
    DUAL_LANE = "135-dual"
    HALF = "half"
    XPAN = "xpan"
    MEDIUM_RECTANGLE = "120-645"
    MEDIUM_SQUARE = "120-66"
    MEDIUM_WIDE = "120-67"


class StripMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


@dataclass(frozen=True)
class FrameSizeMm:
    width_mm: float
    height_mm: float
    label: str = "nominal"

    @property
    def aspect(self) -> float:
        return float(self.width_mm) / float(self.height_mm)


@dataclass(frozen=True)
class FormatPhysicalSpec:
    format_id: FormatId
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str
    frame_size_mm_options: tuple[FrameSizeMm, ...]
    expected_separator_count: int
    physical_layout: str = "single_strip"
    complete_strip_can_be_underfilled: bool = False
    lane_count: int = 1
    lane_format_id: FormatId | None = None

    @property
    def nominal_frame_size_mm(self) -> FrameSizeMm:
        return self.frame_size_mm_options[0]

    @property
    def horizontal_content_aspect(self) -> float:
        return self.nominal_frame_size_mm.aspect

    @property
    def frame_aspect(self) -> float:
        return self.horizontal_content_aspect


FormatSpec = FormatPhysicalSpec


def expected_separator_count(
    default_count: int,
    physical_layout: str,
    lane_count: int = 1,
) -> int:
    if physical_layout == "dual_lane":
        lanes = max(1, int(lane_count))
        lane_frame_count = max(1, int(default_count) // lanes)
        return lanes * max(0, lane_frame_count - 1)
    return max(0, int(default_count) - 1)


def _format_spec(
    format_id: FormatId,
    default_count: int,
    allowed_counts: tuple[int, ...],
    family: str,
    nominal_frame_size_mm: FrameSizeMm,
    frame_size_mm_options: tuple[FrameSizeMm, ...] = (),
    physical_layout: str = "single_strip",
    complete_strip_can_be_underfilled: bool = False,
    lane_count: int = 1,
    lane_format_id: FormatId | None = None,
) -> FormatSpec:
    name = format_id.value
    frame_options = frame_size_mm_options or (nominal_frame_size_mm,)
    return FormatPhysicalSpec(
        format_id=format_id,
        name=name,
        default_count=default_count,
        allowed_counts=allowed_counts,
        family=family,
        frame_size_mm_options=frame_options,
        expected_separator_count=expected_separator_count(
            default_count,
            physical_layout,
            lane_count,
        ),
        physical_layout=physical_layout,
        complete_strip_can_be_underfilled=complete_strip_can_be_underfilled,
        lane_count=lane_count,
        lane_format_id=lane_format_id,
    )


FORMATS: dict[str, FormatSpec] = {
    "135": _format_spec(
        FormatId.STANDARD_STRIP,
        6,
        tuple(range(1, 7)),
        "35mm",
        FrameSizeMm(36.0, 24.0),
    ),
    "135-dual": _format_spec(
        FormatId.DUAL_LANE,
        12,
        (12,),
        "35mm",
        FrameSizeMm(36.0, 24.0),
        physical_layout="dual_lane",
        lane_count=2,
        lane_format_id=FormatId.STANDARD_STRIP,
    ),
    "half": _format_spec(
        FormatId.HALF,
        12,
        tuple(range(1, 13)),
        "35mm",
        FrameSizeMm(18.0, 24.0),
    ),
    "xpan": _format_spec(
        FormatId.XPAN,
        3,
        (1, 2, 3),
        "35mm",
        FrameSizeMm(65.0, 24.0),
        complete_strip_can_be_underfilled=True,
    ),
    "120-645": _format_spec(
        FormatId.MEDIUM_RECTANGLE,
        4,
        (1, 2, 3, 4),
        "120",
        FrameSizeMm(42.0, 56.0),
    ),
    "120-66": _format_spec(
        FormatId.MEDIUM_SQUARE,
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(56.0, 56.0),
        frame_size_mm_options=(
            FrameSizeMm(56.0, 56.0),
            FrameSizeMm(54.0, 54.0, label="camera_variant"),
        ),
        complete_strip_can_be_underfilled=True,
    ),
    "120-67": _format_spec(
        FormatId.MEDIUM_WIDE,
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(70.0, 56.0),
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("full", "partial")
DESKEW_CHOICES = ("off", "auto")
DESKEW_FALLBACK_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")
CONTENT_ASPECTS_HORIZONTAL = {
    key: spec.horizontal_content_aspect
    for key, spec in FORMATS.items()
    if spec.horizontal_content_aspect is not None
}


def format_spec(format_id: str | FormatId) -> FormatSpec:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    return FORMATS[key]


def format_description(format_id: str | FormatId) -> FormatDescription:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    return FORMAT_DESCRIPTIONS[key]


__all__ = [
    "COMPRESSION_CHOICES",
    "CONTENT_ASPECTS_HORIZONTAL",
    "DESKEW_CHOICES",
    "DESKEW_FALLBACK_CHOICES",
    "FORMAT_CHOICES",
    "FORMAT_DESCRIPTIONS",
    "FORMATS",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "FrameSizeMm",
    "FormatId",
    "FormatDescription",
    "FormatPhysicalSpec",
    "FormatSpec",
    "StripMode",
    "expected_separator_count",
    "format_description",
    "format_spec",
]
