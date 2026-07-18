from __future__ import annotations

from dataclasses import dataclass, field

from ..image.constants import UINT8_MAX_VALUE
from ..image.evidence import SeparatorEvidenceImageParameters
from ..utils import (
    RGB_CHANNEL_COUNT,
    require_nonnegative,
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
    frame_crop_envelope_line_width: int = 1
    frame_slot_line_width: int = 3
    sequence_inferred_slot_line_width: int = 3
    containment_fallback_line_width: int = 2
    frame_slot_color: tuple[int, int, int] = (0, 255, 0)
    sequence_inferred_slot_color: tuple[int, int, int] = (255, 210, 0)
    frame_crop_envelope_color: tuple[int, int, int] = (40, 120, 255)
    holder_boundary_color: tuple[int, int, int] = (255, 255, 255)
    panel_spacing: int = 12
    panel_background: int = 32
    dark_background: int = 18
    label_height: int = 34
    label_origin: tuple[int, int] = (12, 9)
    text_color: tuple[int, int, int] = (245, 245, 245)
    jpeg_quality: int = 92
    measured_boundary_color: tuple[int, int, int] = (255, 0, 0)
    raw_observation_color: tuple[int, int, int] = (255, 170, 0)
    corroborated_overlap_color: tuple[int, int, int] = (0, 220, 255)
    dimension_hypothesis_color: tuple[int, int, int] = (190, 80, 255)
    line_dash_length: int = 8
    line_dash_gap: int = 5
    legend_row_height: int = 20
    legend_sample_width: int = 32
    legend_text_gap: int = 8
    pass_color: tuple[int, int, int] = (40, 180, 90)
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
            (
                "debug frame crop envelope line width",
                self.frame_crop_envelope_line_width,
            ),
            ("debug frame-slot line width", self.frame_slot_line_width),
            (
                "debug sequence-inferred slot line width",
                self.sequence_inferred_slot_line_width,
            ),
            (
                "debug containment fallback line width",
                self.containment_fallback_line_width,
            ),
            ("debug panel spacing", self.panel_spacing),
            ("debug label height", self.label_height),
            ("debug JPEG quality", self.jpeg_quality),
            ("debug reason display limit", self.reason_display_limit),
            ("debug status bar height", self.status_bar_height),
            ("debug status outline width", self.status_outline_width),
            ("debug status text stroke width", self.status_text_stroke_width),
            ("debug line dash length", self.line_dash_length),
            ("debug line dash gap", self.line_dash_gap),
            ("debug legend row height", self.legend_row_height),
            ("debug legend sample width", self.legend_sample_width),
            ("debug legend text gap", self.legend_text_gap),
        ):
            require_positive(name, value)
        require_unit_interval("debug frame fill alpha", self.frame_fill_alpha)
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.frame_slot_color,
            self.sequence_inferred_slot_color,
            self.frame_crop_envelope_color,
            self.holder_boundary_color,
            self.text_color,
            self.measured_boundary_color,
            self.raw_observation_color,
            self.corroborated_overlap_color,
            self.dimension_hypothesis_color,
            self.pass_color,
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
class SeparatorOverlayParameters:
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    observed_line_width: int = 2
    dimension_line_width: int = 2
    overlap_line_width: int = 3

    def __post_init__(self) -> None:
        require_nonnegative("separator tick length ratio", self.tick_length_ratio)
        for name, value in (
            ("separator tick minimum length", self.tick_length_min),
            ("observed separator line width", self.observed_line_width),
            ("dimension boundary line width", self.dimension_line_width),
            ("overlap line width", self.overlap_line_width),
        ):
            require_positive(name, value)


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    separator_overlay: SeparatorOverlayParameters = field(
        default_factory=SeparatorOverlayParameters
    )
    separator_evidence_image: SeparatorEvidenceImageParameters = field(
        default_factory=SeparatorEvidenceImageParameters
    )
    style: DebugStyleParameters = field(default_factory=DebugStyleParameters)

    @property
    def legend_entries(self) -> tuple[DebugLegendEntry, ...]:
        style = self.style
        return (
            DebugLegendEntry("Holder boundary", style.holder_boundary_color, True),
            DebugLegendEntry(
                "Selected raw observation",
                style.raw_observation_color,
                False,
            ),
            DebugLegendEntry(
                "Measured frame / separator edge",
                style.measured_boundary_color,
                False,
            ),
            DebugLegendEntry(
                "Dimension-only provisional edge",
                style.dimension_hypothesis_color,
                True,
            ),
            DebugLegendEntry(
                "External safety envelope",
                style.frame_crop_envelope_color,
                True,
            ),
            DebugLegendEntry(
                "Corroborated overlap",
                style.corroborated_overlap_color,
                False,
            ),
            DebugLegendEntry("FrameSlot", style.frame_slot_color, False),
            DebugLegendEntry(
                "Sequence-inferred FrameSlot",
                style.sequence_inferred_slot_color,
                True,
            ),
            DebugLegendEntry(
                "FrameCropEnvelope / export-eligible final box",
                style.frame_crop_envelope_color,
                True,
            ),
        )
