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
    frame_fill_alpha: float = 0.22
    frame_line_width: int = 2
    retained_line_width: int = 1
    frame_label_inset: int = 4
    frame_label_stroke_width: int = 2
    frame_label_font_size: int = 14
    raw_transition_line_width: int = 1
    observed_edge_line_width: int = 2
    lane_authority_color: tuple[int, int, int] = (145, 155, 165)
    raw_transition_color: tuple[int, int, int] = (205, 205, 205)
    observed_edge_color: tuple[int, int, int] = (255, 78, 66)
    canonical_boundary_color: tuple[int, int, int] = (255, 170, 0)
    inferred_direction_color: tuple[int, int, int] = (0, 220, 255)
    retained_color: tuple[int, int, int] = (225, 225, 225)
    panel_spacing: int = 12
    panel_background: int = 32
    dark_background: int = 18
    label_height: int = 36
    label_origin: tuple[int, int] = (12, 10)
    panel_label_font_size: int = 14
    text_color: tuple[int, int, int] = (245, 245, 245)
    jpeg_quality: int = 92
    line_dash_length: int = 8
    line_dash_gap: int = 5
    legend_bar_height: int = 32
    legend_sample_width: int = 32
    legend_text_gap: int = 8
    legend_font_size: int = 12
    approved_color: tuple[int, int, int] = (40, 180, 90)
    review_color: tuple[int, int, int] = (230, 80, 70)
    reason_display_limit: int = 3
    text_fallback_size: tuple[int, int] = (8, 12)
    status_bar_height: int = 64
    status_outline_width: int = 2
    status_text_stroke_width: int = 2
    status_label_font_size: int = 18
    status_detail_font_size: int = 13
    status_origin: tuple[int, int] = (12, 10)
    detail_gap: int = 14
    detail_baseline: int = 12

    def __post_init__(self) -> None:
        for name, value in (
            ("debug preview size", self.preview_max_side),
            ("debug frame line width", self.frame_line_width),
            ("debug retained line width", self.retained_line_width),
            ("debug frame label inset", self.frame_label_inset),
            (
                "debug frame label stroke width",
                self.frame_label_stroke_width,
            ),
            ("debug frame label font size", self.frame_label_font_size),
            (
                "debug raw transition line width",
                self.raw_transition_line_width,
            ),
            (
                "debug observed edge line width",
                self.observed_edge_line_width,
            ),
            ("debug panel spacing", self.panel_spacing),
            ("debug label height", self.label_height),
            ("debug panel label font size", self.panel_label_font_size),
            ("debug JPEG quality", self.jpeg_quality),
            ("debug line dash length", self.line_dash_length),
            ("debug line dash gap", self.line_dash_gap),
            ("debug legend bar height", self.legend_bar_height),
            ("debug legend sample width", self.legend_sample_width),
            ("debug legend text gap", self.legend_text_gap),
            ("debug legend font size", self.legend_font_size),
            ("debug reason display limit", self.reason_display_limit),
            ("debug status bar height", self.status_bar_height),
            ("debug status outline width", self.status_outline_width),
            (
                "debug status text stroke width",
                self.status_text_stroke_width,
            ),
            ("debug status label font size", self.status_label_font_size),
            ("debug status detail font size", self.status_detail_font_size),
        ):
            require_positive(name, value)
        for name, value in (
            ("debug frame fill alpha", self.frame_fill_alpha),
        ):
            require_unit_interval(name, value)
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.lane_authority_color,
            self.raw_transition_color,
            self.observed_edge_color,
            self.canonical_boundary_color,
            self.inferred_direction_color,
            self.retained_color,
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
    def legend_entries(self) -> tuple[DebugLegendEntry, ...]:
        style = self.style
        return (
            DebugLegendEntry(
                "Lane authority",
                style.lane_authority_color,
                True,
            ),
            DebugLegendEntry(
                "Raw transition",
                style.raw_transition_color,
                True,
            ),
            DebugLegendEntry(
                "Observed photo edge",
                style.observed_edge_color,
                False,
            ),
            DebugLegendEntry(
                "Canonical START / END",
                style.canonical_boundary_color,
                False,
            ),
            DebugLegendEntry(
                "Shared direction",
                style.inferred_direction_color,
                False,
            ),
            DebugLegendEntry(
                "Retained placement",
                style.retained_color,
                True,
            ),
        )
