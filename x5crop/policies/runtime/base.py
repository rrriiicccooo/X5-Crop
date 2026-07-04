from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...formats import FormatSpec


FULL = "full"
PARTIAL = "partial"


@dataclass(frozen=True)
class DualLanePolicy:
    lane_count: int = 2
    lane_format: str = "135"


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


@dataclass(frozen=True)
class DetectorPolicy:
    kind: str = "standard_strip"
    dual_lane: DualLanePolicy = field(default_factory=DualLanePolicy)
    review_only: ReviewOnlyPolicy = field(default_factory=ReviewOnlyPolicy)


@dataclass(frozen=True)
class CountPolicy:
    """Frame-count and partial-offset policy for one format/mode pair."""

    fixed_count: int | None
    auto_counts: tuple[int, ...]
    partial_offsets: tuple[float, ...] = (0.0,)
    include_default_in_partial_auto: bool = False

    def count_specs(
        self,
        fmt: FormatSpec,
        strip_mode: str,
        requested_count: int,
        count_override: int | None,
    ) -> list[tuple[int, str, tuple[float, ...]]]:
        if strip_mode == FULL:
            count = requested_count if self.fixed_count is None else self.fixed_count
            return [(count, FULL, (0.0,))]
        if strip_mode != PARTIAL:
            raise ValueError(f"Unsupported strip mode: {strip_mode}")
        if count_override is not None:
            return [(requested_count, PARTIAL, self.partial_offsets)]
        counts = [
            count
            for count in self.auto_counts
            if count < fmt.default_count or self.include_default_in_partial_auto
        ]
        return [(count, PARTIAL, self.partial_offsets) for count in counts] or [
            (1, PARTIAL, self.partial_offsets)
        ]


__all__ = [
    "FULL",
    "PARTIAL",
    "CountPolicy",
    "DetectorPolicy",
    "DualLanePolicy",
    "FrameFitPolicy",
    "ReviewOnlyPolicy",
]
