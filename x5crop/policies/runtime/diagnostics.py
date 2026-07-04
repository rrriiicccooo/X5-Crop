from __future__ import annotations

from dataclasses import dataclass, field

from ..ids import REPORT_SCHEMA_VERSION


@dataclass(frozen=True)
class OverlapBleedRiskPolicy:
    enabled: bool = False
    mean_min: float = 55.0
    weak_continuity: float = 0.16
    weak_activity: float = 0.04
    medium_continuity: float = 0.35
    medium_activity: float = 0.08
    strong_continuity: float = 0.70
    strong_activity: float = 0.12


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
class LuckyPassRiskPolicy:
    enabled: bool = True
    model_gap_support_min: int = 2
    model_gap_support_weight: float = 0.24
    minor_model_gap_support_weight: float = 0.08
    limited_strong_hard_max: int = 2
    limited_strong_hard_weight: float = 0.20
    very_limited_strong_hard_max: int = 1
    very_limited_strong_hard_weight: float = 0.10
    suspicious_hard_weight: float = 0.20
    strong_overlap_weight: float = 0.20
    combo_weight: float = 0.12
    unstable_width_cv: float = 0.006
    unstable_width_weight: float = 0.16
    mild_width_cv: float = 0.003
    mild_width_weight: float = 0.08
    strong_hard_credit_min: int = 3
    strong_hard_credit: float = -0.15
    stable_width_cv: float = 0.002
    stable_model_gap_min: int = 3
    stable_geometry_credit: float = -0.35
    risk_threshold: float = 0.80


@dataclass(frozen=True)
class DebugPanelPolicy:
    panel_id: str
    title: str


@dataclass(frozen=True)
class RuntimeDiagnosticsPolicy:
    attach_read_only_when_requested: bool = True
    overlap_bleed_risk: OverlapBleedRiskPolicy = field(default_factory=OverlapBleedRiskPolicy)
    debug_gap_overlay: DebugGapOverlayPolicy = field(default_factory=DebugGapOverlayPolicy)
    nearby_separator: NearbySeparatorDiagnosticsPolicy = field(default_factory=NearbySeparatorDiagnosticsPolicy)
    lucky_pass_risk: LuckyPassRiskPolicy = field(default_factory=LuckyPassRiskPolicy)
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
        DebugPanelPolicy("risk_review", "Risk / review overlay"),
    )

    def debug_panel_title(self, panel_id: str) -> str:
        for panel in self.debug_panel_titles:
            if panel.panel_id == panel_id:
                return panel.title
        return panel_id.replace("_", " ").title()


@dataclass(frozen=True)
class ReportPolicy:
    schema_version: str = REPORT_SCHEMA_VERSION
    sections: tuple[str, ...] = (
        "version",
        "format",
        "result",
        "selected_candidate",
        "policy",
        "evidence_summary",
        "risk_summary",
        "decision_policy_detail",
        "policy_id",
        "candidate_table",
        "output",
    )


__all__ = [
    "DebugGapOverlayPolicy",
    "DebugPanelPolicy",
    "LuckyPassRiskPolicy",
    "NearbySeparatorDiagnosticsPolicy",
    "OverlapBleedRiskPolicy",
    "ReportPolicy",
    "RuntimeDiagnosticsPolicy",
]
