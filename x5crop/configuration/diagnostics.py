from __future__ import annotations

from dataclasses import dataclass, field

from ..image.constants import UINT8_MAX_VALUE
from ..utils import RGB_CHANNEL_COUNT, require_positive, require_unit_interval


JPEG_QUALITY_MAX = 100


@dataclass(frozen=True)
class DebugLegendEntry:
    label: str
    color: tuple[int, int, int]
    sample: str

    def __post_init__(self) -> None:
        if self.sample not in {"solid", "dashed", "box", "hatched"}:
            raise ValueError("debug legend sample is not canonical")


@dataclass(frozen=True)
class DebugStyleParameters:
    """The fixed V5 Debug Analysis presentation grid and visual tokens."""

    canvas_width: int = 1653
    canvas_height: int = 952
    status_bar_height: int = 70
    outer_margin: int = 12
    panel_gap: int = 10
    source_panel_height: int = 280
    retained_panel_height: int = 258
    output_panel_height: int = 273
    legend_bar_height: int = 51
    panel_title_height: int = 40
    panel_media_inset_x: int = 27
    source_media_top: int = 81
    source_media_height: int = 168
    retained_media_top: int = 76
    retained_media_height: int = 145
    output_media_top: int = 81
    output_media_height: int = 148
    retained_tile_gap: int = 24
    frame_fill_alpha: float = 0.20
    safe_fill_alpha: float = 0.25
    frame_line_width: int = 2
    retained_line_width: int = 1
    evidence_line_width: int = 3
    raw_transition_line_width: int = 1
    annotation_extension: int = 22
    line_dash_length: int = 7
    line_dash_gap: int = 5
    title_font_size: int = 18
    header_status_font_size: int = 18
    header_detail_font_size: int = 15
    annotation_font_size: int = 12
    frame_label_font_size: int = 13
    legend_font_size: int = 12
    jpeg_quality: int = 94
    reason_display_limit: int = 3
    canvas_background: tuple[int, int, int] = (6, 10, 13)
    panel_background: tuple[int, int, int] = (9, 13, 17)
    panel_border_color: tuple[int, int, int] = (46, 56, 64)
    divider_color: tuple[int, int, int] = (39, 48, 56)
    text_color: tuple[int, int, int] = (240, 243, 246)
    secondary_text_color: tuple[int, int, int] = (201, 207, 214)
    lane_authority_color: tuple[int, int, int] = (145, 155, 165)
    raw_transition_color: tuple[int, int, int] = (205, 211, 216)
    observed_edge_color: tuple[int, int, int] = (255, 78, 66)
    canonical_boundary_color: tuple[int, int, int] = (255, 171, 37)
    inferred_direction_color: tuple[int, int, int] = (45, 220, 229)
    retained_color: tuple[int, int, int] = (230, 234, 238)
    safe_output_color: tuple[int, int, int] = (180, 188, 196)
    budget_limit_color: tuple[int, int, int] = (96, 205, 107)
    approved_color: tuple[int, int, int] = (50, 183, 105)
    review_color: tuple[int, int, int] = (230, 73, 61)

    def __post_init__(self) -> None:
        positive_values = (
            self.canvas_width,
            self.canvas_height,
            self.status_bar_height,
            self.outer_margin,
            self.panel_gap,
            self.source_panel_height,
            self.retained_panel_height,
            self.output_panel_height,
            self.legend_bar_height,
            self.panel_title_height,
            self.panel_media_inset_x,
            self.source_media_top,
            self.source_media_height,
            self.retained_media_top,
            self.retained_media_height,
            self.output_media_top,
            self.output_media_height,
            self.retained_tile_gap,
            self.frame_line_width,
            self.retained_line_width,
            self.evidence_line_width,
            self.raw_transition_line_width,
            self.annotation_extension,
            self.line_dash_length,
            self.line_dash_gap,
            self.title_font_size,
            self.header_status_font_size,
            self.header_detail_font_size,
            self.annotation_font_size,
            self.frame_label_font_size,
            self.legend_font_size,
            self.jpeg_quality,
            self.reason_display_limit,
        )
        for value in positive_values:
            require_positive("debug fixed-grid value", value)
        require_unit_interval("debug frame fill alpha", self.frame_fill_alpha)
        require_unit_interval("debug safe fill alpha", self.safe_fill_alpha)
        body_height = (
            self.source_panel_height
            + self.panel_gap
            + self.retained_panel_height
            + self.panel_gap
            + self.output_panel_height
            + self.legend_bar_height
        )
        if self.status_bar_height + body_height != self.canvas_height:
            raise ValueError("debug fixed grid does not fill the canvas")
        if self.canvas_width <= self.outer_margin * 2:
            raise ValueError("debug canvas cannot contain the panel grid")
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.canvas_background,
            self.panel_background,
            self.panel_border_color,
            self.divider_color,
            self.text_color,
            self.secondary_text_color,
            self.lane_authority_color,
            self.raw_transition_color,
            self.observed_edge_color,
            self.canonical_boundary_color,
            self.inferred_direction_color,
            self.retained_color,
            self.safe_output_color,
            self.budget_limit_color,
            self.approved_color,
            self.review_color,
        )
        if any(
            len(color) != RGB_CHANNEL_COUNT
            or any(channel < 0 or channel > UINT8_MAX_VALUE for channel in color)
            for color in colors
        ):
            raise ValueError("debug colors must be RGB byte triples")


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    style: DebugStyleParameters = field(default_factory=DebugStyleParameters)

    @property
    def legend_entries(self) -> tuple[DebugLegendEntry, ...]:
        style = self.style
        return (
            DebugLegendEntry("LANE AUTHORITY", style.lane_authority_color, "dashed"),
            DebugLegendEntry("OBSERVED PHOTO EDGE", style.observed_edge_color, "solid"),
            DebugLegendEntry("RAW TRANSITION", style.raw_transition_color, "dashed"),
            DebugLegendEntry("SHARED / INFERRED", style.inferred_direction_color, "dashed"),
            DebugLegendEntry("CANONICAL", style.canonical_boundary_color, "box"),
            DebugLegendEntry("RETAINED", style.retained_color, "box"),
            DebugLegendEntry("SAFE OUTPUT", style.safe_output_color, "box"),
            DebugLegendEntry("BUDGET LIMIT", style.budget_limit_color, "dashed"),
            DebugLegendEntry("BUDGET VIOLATION", style.review_color, "hatched"),
        )
