from __future__ import annotations

from dataclasses import dataclass, field

from ..image.evidence import SeparatorEvidenceImageParameters
from ..utils import require_nonnegative, require_positive


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
class DebugPanelConfiguration:
    panel_id: str
    title: str

    def __post_init__(self) -> None:
        if not self.panel_id or not self.title:
            raise ValueError("debug panel identity and title must not be empty")


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    separator_overlay: SeparatorOverlayParameters = field(
        default_factory=SeparatorOverlayParameters
    )
    separator_evidence_image: SeparatorEvidenceImageParameters = field(
        default_factory=SeparatorEvidenceImageParameters
    )
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )
    debug_panel_titles: tuple[DebugPanelConfiguration, ...] = (
        DebugPanelConfiguration("original_gray", "Original gray context"),
        DebugPanelConfiguration("debug_boxes", "Debug boxes"),
        DebugPanelConfiguration("separator_evidence", "Separator evidence"),
    )

    def __post_init__(self) -> None:
        if len(set(self.debug_panels)) != len(self.debug_panels):
            raise ValueError("debug panel identifiers must be unique")
        title_ids = tuple(panel.panel_id for panel in self.debug_panel_titles)
        if title_ids != self.debug_panels:
            raise ValueError("debug panel titles must match configured panel order")

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        raise KeyError(f"Unknown debug panel: {panel_id}")
