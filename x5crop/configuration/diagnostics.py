from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeparatorOverlayParameters:
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    observed_line_width: int = 2
    dimension_line_width: int = 2
    overlap_line_width: int = 3


@dataclass(frozen=True)
class DebugPanelConfiguration:
    panel_id: str
    title: str


@dataclass(frozen=True)
class DiagnosticsConfiguration:
    separator_overlay: SeparatorOverlayParameters = field(
        default_factory=SeparatorOverlayParameters
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

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        raise KeyError(f"Unknown debug panel: {panel_id}")
