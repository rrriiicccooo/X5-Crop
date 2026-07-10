from __future__ import annotations

from dataclasses import dataclass, field
FULL = "full"
PARTIAL = "partial"


@dataclass(frozen=True)
class ReviewOnlyPolicy:
    reason: str = "review_only_mode"
    selection_override: str = "review_only_mode"


@dataclass(frozen=True)
class FrameFitPolicy:
    name: str
    edge_evidence: bool
    geometry_fallback: bool
    min_edge_samples: int = 2
    nominal_min_ratio: float = 0.72
    nominal_max_ratio: float = 1.10
    inlier_tolerance_ratio: float = 0.035
    min_inlier_tolerance_px: float = 3.0
    geometry_pitch_min_ratio: float = 0.85
    geometry_pitch_max_ratio: float = 1.15
    geometry_noop_width_cv: float = 0.006
    geometry_outer_tolerance_ratio: float = 0.0
    geometry_outer_tolerance_min: float = 1.0
    geometry_outer_tolerance_max: float = 1.0
    edge_candidate_weight_with_edges: float = 0.18
    edge_candidate_weight_without_edges: float = 1.0
    edge_adjust_tolerance_ratio: float = 0.0
    edge_adjust_tolerance_min: float = 1.0
    edge_adjust_tolerance_max: float = 1.0
    edge_pair_score_cap: float = 1.8
    edge_pair_weight_multiplier: float = 1.20
    detected_gap_score_cap: float = 1.5


@dataclass(frozen=True)
class DetectorPolicy:
    kind: str = "standard_strip"
    review_only: ReviewOnlyPolicy = field(default_factory=ReviewOnlyPolicy)


@dataclass(frozen=True)
class CountPolicy:
    """Permitted automatic count hypotheses and placement offsets."""

    auto_counts: tuple[int, ...]
    partial_offsets: tuple[float, ...] = (0.0,)
    include_default_in_partial_auto: bool = False


__all__ = [
    "FULL",
    "PARTIAL",
    "CountPolicy",
    "DetectorPolicy",
    "FrameFitPolicy",
    "ReviewOnlyPolicy",
]
