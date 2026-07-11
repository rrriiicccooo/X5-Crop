from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DualLaneDividerParameters:
    search_min_ratio: float = 0.30
    search_max_ratio: float = 0.70
    band_width_ratio: float = 0.012
    band_width_min_px: int = 4
    band_width_max_px: int = 96
    proposal_count: int = 3
    minimum_center_separation_ratio: float = 0.06
    content_weight: float = 0.55
    texture_weight: float = 0.45


@dataclass(frozen=True)
class ContentSeparatorGuidanceParameters:
    max_hint_offset_ratio: float = 0.28
    max_hint_offset_min: int = 18
    max_hint_offset_max: int = 420


@dataclass(frozen=True)
class CandidatePlanParameters:
    content_separator_guidance: ContentSeparatorGuidanceParameters = field(
        default_factory=ContentSeparatorGuidanceParameters
    )
    dual_lane_divider: DualLaneDividerParameters = field(
        default_factory=DualLaneDividerParameters
    )
