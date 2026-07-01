"""Format-aware policy surface for X5 Crop."""

from .common import (
    EdgePairParams,
    FilmFormat,
    FormatTuning,
    OuterMaskProfile,
    FORMATS,
    FORMAT_CHOICES,
    format_tuning,
    policy_views,
    FormatPolicyViews,
)
from .geometry import (
    FrameFitPolicy,
    frame_fit_policy,
)
from .policies import (
    ContentPolicy,
    CountPolicy,
    DetectionPolicy,
    DiagnosticsPolicy,
    GatePolicy,
    OuterPolicy,
    OutputPolicy,
    PostprocessPolicy,
    ScoringPolicy,
    SelectionPolicy,
    SeparatorPolicy,
    get_detection_policy,
    policy_report_detail,
)

__all__ = [
    "EdgePairParams",
    "FilmFormat",
    "FormatTuning",
    "FrameFitPolicy",
    "FormatPolicyViews",
    "OuterMaskProfile",
    "FORMATS",
    "FORMAT_CHOICES",
    "format_tuning",
    "frame_fit_policy",
    "policy_views",
    "ContentPolicy",
    "CountPolicy",
    "DetectionPolicy",
    "DiagnosticsPolicy",
    "GatePolicy",
    "OuterPolicy",
    "OutputPolicy",
    "PostprocessPolicy",
    "ScoringPolicy",
    "SelectionPolicy",
    "SeparatorPolicy",
    "get_detection_policy",
    "policy_report_detail",
]
