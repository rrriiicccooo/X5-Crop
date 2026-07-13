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
class DebugStyleParameters:
    preview_max_side: int = 1800
    frame_fill_alpha: float = 0.26
    frame_line_width: int = 1
    crop_envelope_line_width: int = 3
    evidence_envelope_line_width: int = 2
    crop_envelope_color: tuple[int, int, int] = (0, 255, 0)
    frame_output_color: tuple[int, int, int] = (40, 120, 255)
    holder_boundary_color: tuple[int, int, int] = (255, 255, 255)
    panel_spacing: int = 12
    panel_background: int = 32
    dark_background: int = 18
    label_height: int = 34
    label_origin: tuple[int, int] = (12, 9)
    text_color: tuple[int, int, int] = (245, 245, 245)
    jpeg_quality: int = 92
    accepted_separator_color: tuple[int, int, int] = (255, 0, 0)
    unselected_separator_color: tuple[int, int, int] = (255, 170, 0)
    overlap_boundary_color: tuple[int, int, int] = (0, 220, 255)
    dimension_boundary_color: tuple[int, int, int] = (190, 80, 255)
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
            ("debug frame line width", self.frame_line_width),
            ("debug crop line width", self.crop_envelope_line_width),
            ("debug evidence line width", self.evidence_envelope_line_width),
            ("debug panel spacing", self.panel_spacing),
            ("debug label height", self.label_height),
            ("debug JPEG quality", self.jpeg_quality),
            ("debug reason display limit", self.reason_display_limit),
            ("debug status bar height", self.status_bar_height),
            ("debug status outline width", self.status_outline_width),
            ("debug status text stroke width", self.status_text_stroke_width),
        ):
            require_positive(name, value)
        require_unit_interval("debug frame fill alpha", self.frame_fill_alpha)
        if self.jpeg_quality > JPEG_QUALITY_MAX:
            raise ValueError("debug JPEG quality exceeds the standard maximum")
        colors = (
            self.crop_envelope_color,
            self.frame_output_color,
            self.holder_boundary_color,
            self.text_color,
            self.accepted_separator_color,
            self.unselected_separator_color,
            self.overlap_boundary_color,
            self.dimension_boundary_color,
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
