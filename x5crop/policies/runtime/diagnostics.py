from __future__ import annotations

from dataclasses import dataclass
from ..parameters.diagnostics import DebugGapOverlayParameters


@dataclass(frozen=True)
class DebugPanelPolicy:
    panel_id: str
    title: str


@dataclass(frozen=True)
class RuntimeDiagnosticsPolicy:
    debug_gap_overlay: DebugGapOverlayParameters
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )
    debug_panel_titles: tuple[DebugPanelPolicy, ...] = (
        DebugPanelPolicy("original_gray", "Original gray context"),
        DebugPanelPolicy("debug_boxes", "Debug boxes"),
        DebugPanelPolicy("separator_evidence", "Separator evidence"),
    )

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        raise KeyError(f"Unknown debug panel: {panel_id}")
