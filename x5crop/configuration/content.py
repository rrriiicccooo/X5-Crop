from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    require_unit_interval,
)


@dataclass(frozen=True)
class ContentEvidenceParameters:
    activation_percentile: float = 70.0
    minimum_evidence_range: float = 1e-6
    minimum_active_pixels: int = 16
    boundary_band_ratio: float = 0.02
    boundary_band_min_px: int = 2
    minimum_content_bridge_ratio: float = 0.25
    content_bridge_column_percentile: float = 25.0
    minimum_gray_discontinuity_ratio: float = 0.25
    maximum_percentile_samples: int = 1_000_000

    def __post_init__(self) -> None:
        require_percentile(
            "content activation percentile",
            self.activation_percentile,
        )
        require_positive("content evidence range", self.minimum_evidence_range)
        require_positive("content active pixel count", self.minimum_active_pixels)
        require_unit_interval("content boundary band ratio", self.boundary_band_ratio)
        require_positive("content boundary band width", self.boundary_band_min_px)
        require_unit_interval(
            "content bridge ratio",
            self.minimum_content_bridge_ratio,
        )
        require_percentile(
            "content bridge column percentile",
            self.content_bridge_column_percentile,
        )
        require_unit_interval(
            "gray discontinuity ratio",
            self.minimum_gray_discontinuity_ratio,
        )
        require_positive(
            "content percentile sample budget",
            self.maximum_percentile_samples,
        )


@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float = 0.010
    smooth_min_px: int = 5
    min_run_width_px: int = 6
    low_activity_percentile: float = 10.0
    high_activity_percentile: float = 90.0
    minimum_profile_range: float = 1.0 / 255.0

    def __post_init__(self) -> None:
        require_nonnegative("content profile smoothing ratio", self.smooth_ratio)
        require_positive("content profile smoothing width", self.smooth_min_px)
        require_positive("content run width", self.min_run_width_px)
        require_percentile(
            "content profile low-activity percentile",
            self.low_activity_percentile,
        )
        require_percentile(
            "content profile high-activity percentile",
            self.high_activity_percentile,
        )
        if self.low_activity_percentile >= self.high_activity_percentile:
            raise ValueError(
                "content profile activity percentiles must be ordered"
            )
        require_positive(
            "content profile dynamic range",
            self.minimum_profile_range,
        )


@dataclass(frozen=True)
class ContentConfiguration:
    evidence: ContentEvidenceParameters = field(
        default_factory=ContentEvidenceParameters
    )
    profile: ContentProfileParameters = field(
        default_factory=ContentProfileParameters
    )
