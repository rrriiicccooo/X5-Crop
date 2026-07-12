from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class ContentEvidenceParameters:
    activation_percentile: float = 70.0
    minimum_evidence_range: float = 1e-6
    minimum_active_pixels: int = 16
    boundary_band_ratio: float = 0.02
    boundary_band_min_px: int = 2

@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float = 0.010
    smooth_min_px: int = 5
    min_run_width_px: int = 6
    activation_percentile: float = 70.0
