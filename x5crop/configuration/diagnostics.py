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
class DebugLegendEntry:
    label: str
    color: tuple[int, int, int]
    dashed: bool


@dataclass(frozen=True)
class DebugStyleParameters:
    preview_max_side: int = 1800
    frame_fill_alpha: float = 0.26
    provisional_frame_fill_alpha: float = 0.13
    frame_line_width: int = 2
    provisional_frame_line_width: int = 2
    frame_label_inset: int = 4
    frame_label_stroke_width: int = 2
    raw_separator_alpha: float = 0.18
    raw_separator_line_width: int = 1
    selected_separator_line_width: int = 2
    raw_separator_color: tuple[int, int, int] = (180, 180, 180)
    selected_edge_pair_color: tuple[int, int, int] = (255, 0, 0)
    selected_one_sided_color: tuple[int, int, int] = (255, 170, 0)
    selected_model_only_color: tuple[int, int, int] = (0, 220, 255)
    panel_spacing: int = 12
    panel_background: int = 32
    dark_background: int = 18
    label_height: int = 34
    label_origin: tuple[int, int] = (12, 9)
    text_color: tuple[int, int, int] = (245, 245, 245)
    jpeg_quality: int = 92
    line_dash_length: int = 8
    line_dash_gap: int = 5
    legend_row_height: int = 20
    legend_sample_width: int = 32
    legend_text_gap: int = 8
    approved_color: tuple[int, int, int] = (40, 180, 90)
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
            ("debug frame line width", self.frame_line_width),
            (
                "debug provisional frame line width",
                self.provisional_frame_line_width,
            ),
            ("debug frame label inset", self.frame_label_inset),
            (
                "debug frame label stroke width",
                self.frame_label_stroke_width,
            ),
            (
                "debug raw separator line width",
                self.raw_separator_line_width,
            ),
            (
                "debug selected separator line width",
                self.selected_separator_line_width,
            ),
            ("debug panel spacing", self.panel_spacing),
            ("debug label height", self.label_height),
            ("debug JPEG quality", self.jpeg_quality),
            ("debug line dash length", self.line_dash_length),
            ("debug line dash gap", self.line_dash_gap),
            ("debug legend row height", self.legend_row_height),
            ("debug legend sample width", self.legend_sample_width),
            ("debug legend text gap", self.legend_text_gap),
            ("debug reason display limit", self.reason_display_limit),
            ("debug status bar height", self.status_bar_height),
            ("debug status outline width", self.status_outline_width),
            (
                "debug status text stroke width",
                self.status_text_stroke_width,
            ),
        ):
            require_positive(name, value)
        for name, value in (
            ("debug frame fill alpha", self.frame_fill_alpha),
            (
                "debug provisional frame fill alpha",
                self.provisional_frame_fill_alpha,
            ),
            ("debug raw separator alpha", self.raw_separator_alpha),
        ):
            require_unit_interval(name, value)
        if self.provisional_frame_fill_alpha >= self.frame_fill_alpha:
            raise ValueError(
                "provisional frame fill must be lighter than final frame fill"
            )
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.raw_separator_color,
            self.selected_edge_pair_color,
            self.selected_one_sided_color,
            self.selected_model_only_color,
            self.text_color,
            self.approved_color,
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
            for value in (self.panel_background, self.dark_background)
        ):
            raise ValueError("debug backgrounds must be byte values")


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    style: DebugStyleParameters = field(default_factory=DebugStyleParameters)

    @property
    def separator_legend_entries(self) -> tuple[DebugLegendEntry, ...]:
        style = self.style
        return (
            DebugLegendEntry(
                "Raw separator observation",
                style.raw_separator_color,
                False,
            ),
            DebugLegendEntry(
                "Selected edge-pair",
                style.selected_edge_pair_color,
                False,
            ),
            DebugLegendEntry(
                "Selected one-sided",
                style.selected_one_sided_color,
                False,
            ),
            DebugLegendEntry(
                "Selected model-only Grid",
                style.selected_model_only_color,
                True,
            ),
        )
