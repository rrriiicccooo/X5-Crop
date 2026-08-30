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
    """The adaptive V5 Debug Analysis presentation grid and visual tokens."""

    canvas_width: int = 1800
    status_bar_height: int = 70
    outer_margin: int = 12
    panel_gap: int = 10
    legend_bar_height: int = 51
    panel_title_height: int = 40
    panel_media_inset_x: int = 27
    cross_axis_media_top: int = 81
    cross_axis_media_bottom_padding: int = 31
    long_axis_media_top: int = 76
    long_axis_media_bottom_padding: int = 55
    output_media_top: int = 81
    output_media_bottom_padding: int = 62
    output_fill_alpha: float = 0.40
    frame_line_width: int = 2
    evidence_line_width: int = 3
    raw_transition_line_width: int = 1
    annotation_extension: int = 22
    boundary_label_row_gap: int = 15
    boundary_label_horizontal_gap: int = 5
    budget_hatch_border_width: int = 8
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
    detected_edge_color: tuple[int, int, int] = (45, 220, 229)
    selected_edge_color: tuple[int, int, int] = (255, 78, 66)
    detected_transition_color: tuple[int, int, int] = (205, 211, 216)
    joint_transition_color: tuple[int, int, int] = (133, 231, 106)
    selected_boundary_color: tuple[int, int, int] = (255, 171, 37)
    competitor_color: tuple[int, int, int] = (197, 111, 255)
    safe_output_color: tuple[int, int, int] = (30, 144, 255)
    approved_color: tuple[int, int, int] = (50, 183, 105)
    review_color: tuple[int, int, int] = (230, 73, 61)

    def __post_init__(self) -> None:
        positive_values = (
            self.canvas_width,
            self.status_bar_height,
            self.outer_margin,
            self.panel_gap,
            self.legend_bar_height,
            self.panel_title_height,
            self.panel_media_inset_x,
            self.cross_axis_media_top,
            self.cross_axis_media_bottom_padding,
            self.long_axis_media_top,
            self.long_axis_media_bottom_padding,
            self.output_media_top,
            self.output_media_bottom_padding,
            self.frame_line_width,
            self.evidence_line_width,
            self.raw_transition_line_width,
            self.annotation_extension,
            self.boundary_label_row_gap,
            self.boundary_label_horizontal_gap,
            self.budget_hatch_border_width,
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
            require_positive("debug adaptive-grid value", value)
        require_unit_interval("debug output fill alpha", self.output_fill_alpha)
        if self.canvas_width <= 2 * (
            self.outer_margin + self.panel_media_inset_x
        ):
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
            self.detected_edge_color,
            self.selected_edge_color,
            self.detected_transition_color,
            self.joint_transition_color,
            self.selected_boundary_color,
            self.competitor_color,
            self.safe_output_color,
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
            DebugLegendEntry("DETECTED TOP/BOTTOM", style.detected_edge_color, "dashed"),
            DebugLegendEntry("SELECTED TOP/BOTTOM", style.selected_edge_color, "solid"),
            DebugLegendEntry("DETECTED START/END", style.detected_transition_color, "dashed"),
            DebugLegendEntry("JOINT START/END", style.joint_transition_color, "dashed"),
            DebugLegendEntry("SELECTED START/END", style.selected_boundary_color, "solid"),
            DebugLegendEntry("RUNNER / COMPETITOR", style.competitor_color, "dashed"),
            DebugLegendEntry("FINAL OUTPUT", style.safe_output_color, "box"),
            DebugLegendEntry("BUDGET VIOLATION", style.review_color, "hatched"),
        )
