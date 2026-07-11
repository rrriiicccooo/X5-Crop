from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ....cache import MeasurementCache
from ....formats import FormatPhysicalSpec
from ....policies.runtime.outer import OuterPolicy
from ....policies.runtime.separator import SeparatorPolicy
from ....units import ScanCalibration
from ...guidance.content_outer_edge import edge_anchored_outer_candidates
from ...guidance.content_outer_floating import floating_content_position_candidates
from ...physical.outer.base import base_outer_candidates
from ...physical.outer.common import unique_outer_proposals
from ...physical.outer.separator import (
    separator_derived_outer_candidates,
    separator_outer_scopes,
)
from ...physical.photo_size import PhotoSizeConsistency
from ...physical.outer.types import OuterProposal


@dataclass(frozen=True)
class OuterProposalStrategy:
    name: str
    mode: str

    @property
    def enabled(self) -> bool:
        return self.mode != "off"


def separator_sequence_rank(
    photo_size: PhotoSizeConsistency,
    aspect_error: float,
    sequence_score: float,
    sequence_score_weight: float,
    photo_width_cv_rank_weight: float,
) -> float:
    if photo_size.used:
        photo_width_cv = (
            0.0
            if photo_size.photo_width_cv is None
            else float(photo_size.photo_width_cv)
        )
        mean_error = (
            0.0
            if photo_size.mean_photo_width_error_ratio is None
            else float(photo_size.mean_photo_width_error_ratio)
        )
        photo_size_penalty = mean_error + photo_width_cv_rank_weight * photo_width_cv
    else:
        photo_size_penalty = 1.0
    return (
        photo_size_penalty
        + float(aspect_error)
        - float(sequence_score_weight) * float(sequence_score)
    )


def outer_proposal_strategy_plan_for_policy(
    outer_policy: OuterPolicy,
    strip_mode: str = "full",
    explicit_count: bool = True,
) -> list[OuterProposalStrategy]:
    proposal_policy = outer_policy.proposal
    partial_placement = proposal_policy.geometry.partial_placement
    separator_geometry = proposal_policy.geometry.separator
    separator_mode = (
        "always"
        if separator_outer_scopes(separator_geometry, strip_mode, explicit_count)
        else "off"
    )
    base = [
        OuterProposalStrategy(
            "base",
            "always",
        ),
    ]
    partial_positions = {
        "edge_anchor": OuterProposalStrategy(
            "edge_anchor",
            "always" if partial_placement.enabled else "off",
        ),
        "floating": OuterProposalStrategy(
            "floating",
            "always" if partial_placement.enabled else "off",
        ),
    }
    ordered_partial_positions = [
        partial_positions[name]
        for name in partial_placement.position_order
        if name in partial_positions
    ]
    active = [
        *ordered_partial_positions,
        OuterProposalStrategy(
            "separator_derived",
            separator_mode,
        ),
    ]
    return [*base, *[strategy for strategy in active if strategy.mode == "always"]]


def outer_proposal_candidates(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    cache: MeasurementCache,
    scan_calibration: ScanCalibration,
    long_axis: str,
    *,
    outer_policy: OuterPolicy,
    separator_policy: SeparatorPolicy,
    separator_scopes: tuple[str, ...],
    explicit_count: bool = True,
) -> list[OuterProposal]:
    strategy_plan = outer_proposal_strategy_plan_for_policy(
        outer_policy,
        strip_mode=strip_mode,
        explicit_count=explicit_count,
    )
    enabled_strategy_names = {strategy.name for strategy in strategy_plan if strategy.enabled}
    base_candidates = base_outer_candidates(
        gray_work,
        outer_policy.proposal.base,
    )
    edge_candidates: list[OuterProposal] = []
    if "edge_anchor" in enabled_strategy_names:
        edge_candidates = edge_anchored_outer_candidates(
            gray_work,
            base_candidates,
            fmt,
            count,
            strip_mode,
            partial_placement=outer_policy.proposal.geometry.partial_placement,
        )
    floating_candidates: list[OuterProposal] = []
    if "floating" in enabled_strategy_names:
        floating_candidates = floating_content_position_candidates(
            gray_work,
            base_candidates,
            fmt,
            count,
            strip_mode,
            outer_policy.proposal.geometry.partial_placement,
        )
    pre_separator_candidates = unique_outer_proposals([*base_candidates, *edge_candidates, *floating_candidates])
    separator_candidates: list[OuterProposal] = []
    if "separator_derived" in enabled_strategy_names:
        separator_candidates = separator_derived_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            scan_calibration,
            long_axis,
            separator_geometry_policy=outer_policy.proposal.geometry.separator,
            separator_policy=separator_policy,
            outer_scopes=separator_scopes,
            explicit_count=explicit_count,
            sequence_ranker=separator_sequence_rank,
        )
    return unique_outer_proposals(
        [*base_candidates, *edge_candidates, *floating_candidates, *separator_candidates]
    )
