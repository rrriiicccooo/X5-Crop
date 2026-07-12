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
        require_positive(
            "content percentile sample budget",
            self.maximum_percentile_samples,
        )


@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float = 0.010
    smooth_min_px: int = 5
    min_run_width_px: int = 6
    activation_percentile: float = 70.0

    def __post_init__(self) -> None:
        require_nonnegative("content profile smoothing ratio", self.smooth_ratio)
        require_positive("content profile smoothing width", self.smooth_min_px)
        require_positive("content run width", self.min_run_width_px)
        require_percentile(
            "content profile activation percentile",
            self.activation_percentile,
        )


@dataclass(frozen=True)
class ContentConfiguration:
    evidence: ContentEvidenceParameters = field(
        default_factory=ContentEvidenceParameters
    )
    profile: ContentProfileParameters = field(
        default_factory=ContentProfileParameters
    )
