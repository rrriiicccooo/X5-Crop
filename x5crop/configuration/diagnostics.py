from __future__ import annotations

from dataclasses import dataclass, field

from ..image.constants import UINT8_MAX_VALUE
from ..utils import (
    RGB_CHANNEL_COUNT,
    require_positive,
    require_unit_interval,
)


JPEG_QUALITY_MAX = 100


@dataclass(frozen=True)
class DebugStyleParameters:
    preview_max_side: int = 1800
    domain_fill_alpha: float = 0.12
    domain_line_width: int = 2
    content_line_width: int = 1
    domain_color: tuple[int, int, int] = (0, 220, 255)
    content_color: tuple[int, int, int] = (40, 180, 90)
    dark_background: int = 18
    text_color: tuple[int, int, int] = (245, 245, 245)
    jpeg_quality: int = 92
    review_color: tuple[int, int, int] = (230, 80, 70)
    reason_display_limit: int = 3
    text_fallback_size: tuple[int, int] = (8, 12)
    status_bar_height: int = 48
    status_outline_width: int = 2
    status_text_stroke_width: int = 2
    status_origin: tuple[int, int] = (12, 10)
    detail_gap: int = 14
    detail_baseline: int = 17

    def __post_init__(self) -> None:
        for name, value in (
            ("debug preview size", self.preview_max_side),
            ("debug domain line width", self.domain_line_width),
            ("debug content line width", self.content_line_width),
            ("debug JPEG quality", self.jpeg_quality),
            ("debug reason display limit", self.reason_display_limit),
            ("debug status bar height", self.status_bar_height),
            ("debug status outline width", self.status_outline_width),
            ("debug status text stroke width", self.status_text_stroke_width),
        ):
            require_positive(name, value)
        require_unit_interval("debug domain fill alpha", self.domain_fill_alpha)
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.domain_color,
            self.content_color,
            self.text_color,
            self.review_color,
        )
        if any(
            len(color) != RGB_CHANNEL_COUNT
            or any(channel < 0 or channel > UINT8_MAX_VALUE for channel in color)
            for color in colors
        ):
            raise ValueError("debug colors must be RGB byte triples")
        if any(
            value < 0 or value > UINT8_MAX_VALUE
            for value in (self.dark_background,)
        ):
            raise ValueError("debug backgrounds must be byte values")


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    style: DebugStyleParameters = field(default_factory=DebugStyleParameters)
