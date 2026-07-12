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


@dataclass(frozen=True)
class SequenceHypothesisParameters:
    observation_budget: int = 10
    maximum_hypotheses: int = 12


@dataclass(frozen=True)
class SequenceSolverParameters:
    maximum_assignment_evaluations: int = 100_000


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
