from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DebugGapOverlayPolicy:
    overlap_tolerance_ratio: float = 0.012
    overlap_tolerance_min: float = 4.0
    overlap_tolerance_max: float = 80.0
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    hard_line_width: int = 2
    model_line_width: int = 2
    diagnostic_line_width: int = 3


@dataclass(frozen=True)
class NearbySeparatorDiagnosticsPolicy:
    window_ratio: float = 0.040
    window_min: int = 16
    window_max: int = 320
    exclude_ratio: float = 0.012
    exclude_min: int = 8
    exclude_max: int = 120
    max_width_ratio: float = 0.070
    max_width_min: int = 2
    max_width_max: int = 520
    detail_score_add: float = 0.08
    detail_score_multiplier: float = 1.18


@dataclass(frozen=True)
class DebugPanelPolicy:
    panel_id: str
    title: str


@dataclass(frozen=True)
class RuntimeDiagnosticsPolicy:
    attach_read_only_when_requested: bool = True
    debug_gap_overlay: DebugGapOverlayPolicy = field(default_factory=DebugGapOverlayPolicy)
    nearby_separator: NearbySeparatorDiagnosticsPolicy = field(default_factory=NearbySeparatorDiagnosticsPolicy)
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )
    debug_panel_titles: tuple[DebugPanelPolicy, ...] = (
        DebugPanelPolicy("original_gray", "Original gray context"),
        DebugPanelPolicy("debug_boxes", "Debug boxes"),
        DebugPanelPolicy("separator_evidence", "Separator evidence"),
        DebugPanelPolicy("frame_geometry", "Frame geometry"),
        DebugPanelPolicy("outer_candidates", "Outer candidates"),
        DebugPanelPolicy("selected_candidate", "Selected candidate"),
        DebugPanelPolicy("decision_review", "Decision review overlay"),
    )

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        return panel_id.replace("_", " ").title()
