from __future__ import annotations

from dataclasses import dataclass, field

from ..utils import (
    require_nonnegative,
    require_percentile,
    require_positive,
    require_unit_interval,
)


@dataclass(frozen=True)
class DualLaneDividerParameters:
    search_min_ratio: float = 0.30
    search_max_ratio: float = 0.70
    band_width_ratio: float = 0.012
    band_width_min_px: int = 4
    band_width_max_px: int = 96
    proposal_count: int = 3
    minimum_center_separation_ratio: float = 0.06
    residual_scale_percentile: float = 90.0
    numerical_floor: float = 1e-6

    def __post_init__(self) -> None:
        require_unit_interval("lane search minimum", self.search_min_ratio)
        require_unit_interval("lane search maximum", self.search_max_ratio)
        if self.search_max_ratio <= self.search_min_ratio:
            raise ValueError("lane search maximum must follow minimum")
        require_nonnegative("lane gutter width ratio", self.band_width_ratio)
        require_positive("lane gutter minimum width", self.band_width_min_px)
        require_positive("lane gutter maximum width", self.band_width_max_px)
        if self.band_width_max_px < self.band_width_min_px:
            raise ValueError("lane gutter maximum width must cover minimum")
        require_positive("lane divider proposal budget", self.proposal_count)
        require_nonnegative(
            "lane divider minimum separation",
            self.minimum_center_separation_ratio,
        )
        require_percentile(
            "lane divider residual percentile",
            self.residual_scale_percentile,
        )
        require_positive("lane divider numerical floor", self.numerical_floor)


@dataclass(frozen=True)
class SequenceHypothesisParameters:
    observation_budget: int = 10
    maximum_hypotheses: int = 12

    def __post_init__(self) -> None:
        require_positive("sequence observation budget", self.observation_budget)
        require_positive("sequence hypothesis budget", self.maximum_hypotheses)


@dataclass(frozen=True)
class SequenceSolverParameters:
    maximum_assignment_evaluations: int = 100_000

    def __post_init__(self) -> None:
        require_positive(
            "sequence assignment evaluation budget",
            self.maximum_assignment_evaluations,
        )


@dataclass(frozen=True)
class CandidatePlanParameters:
    sequence_hypotheses: SequenceHypothesisParameters = field(
        default_factory=SequenceHypothesisParameters
    )
    sequence_solver: SequenceSolverParameters = field(
        default_factory=SequenceSolverParameters
    )
    dual_lane_divider: DualLaneDividerParameters = field(
        default_factory=DualLaneDividerParameters
    )
