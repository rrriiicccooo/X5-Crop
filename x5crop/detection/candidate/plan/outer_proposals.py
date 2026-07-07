from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ....cache import AnalysisCache
from ....domain import OuterCandidate
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ...gap_profiles import WIDTH_AWARE_GAP_PROFILE
from ...guidance.content_outer_edge import edge_anchored_outer_candidates
from ...guidance.content_outer_floating import floating_content_position_candidates
from ...physical.outer.base import base_outer_candidates
from ...physical.outer.common import unique_outer_candidates
from ...physical.outer.separator import (
    FULL_WIDTH_SEPARATOR_OUTER,
    separator_derived_outer_candidates,
    separator_outer_scopes_for_policy,
)


@dataclass(frozen=True)
class OuterProposalStrategy:
    name: str
    report_strategy: str
    mode: str
    safety_only: bool
    risk_level: str

    @property
    def enabled(self) -> bool:
        return self.mode != "off"


def outer_proposal_strategy_plan_for_policy(
    policy: DetectionPolicy,
    strip_mode: str = "full",
    explicit_count: bool = True,
    safety_only: bool = False,
) -> list[OuterProposalStrategy]:
    proposal_policy = policy.outer.proposal
    partial_placement = proposal_policy.geometry.partial_placement
    separator_mode = (
        "safety"
        if safety_only and separator_outer_scopes_for_policy(policy, strip_mode, explicit_count, safety_only=True)
        else "always"
        if (not safety_only and separator_outer_scopes_for_policy(policy, strip_mode, explicit_count, safety_only=False))
        else "off"
    )
    base = [
        OuterProposalStrategy(
            "base",
            "base_outer",
            "always" if proposal_policy.base.enabled else "off",
            False,
            "low",
        ),
    ]
    partial_positions = {
        "edge_anchor": OuterProposalStrategy(
            "edge_anchor",
            "edge_anchor_outer",
            "always" if partial_placement.enabled and partial_placement.edge_anchor.enabled else "off",
            False,
            "medium",
        ),
        "floating": OuterProposalStrategy(
            "floating",
            "content_outer",
            "always" if partial_placement.enabled and partial_placement.floating.enabled else "off",
            False,
            "medium",
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
            "separator_outer",
            separator_mode,
            True,
            "medium",
        ),
    ]
    if safety_only:
        return [strategy for strategy in active if strategy.mode == "safety"]
    return [*base, *[strategy for strategy in active if strategy.mode == "always"]]


def outer_candidate_strategy(candidate: OuterCandidate | str) -> str:
    if isinstance(candidate, OuterCandidate):
        return candidate.strategy
    candidate_name = str(candidate)
    if candidate_name in {"bw", "white_x", "full_canvas"}:
        return "base_outer"
    return "unknown_outer"


def merge_outer_proposal_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    return unique_outer_candidates(candidates)


def edge_anchored_candidates_trusted(
    candidates: list[OuterCandidate],
    policy: DetectionPolicy,
) -> bool:
    partial_placement = policy.outer.proposal.geometry.partial_placement
    return bool(
        partial_placement.enabled
        and partial_placement.skip_floating_when_edge_trusted
        and len(candidates) >= int(partial_placement.edge_trust_min_candidates)
    )


def outer_proposal_candidates(
    gray_work: np.ndarray,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    safety_only: bool = False,
    policy: Optional[DetectionPolicy] = None,
    explicit_count: bool = True,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    strategy_plan = outer_proposal_strategy_plan_for_policy(
        policy,
        strip_mode=strip_mode,
        explicit_count=explicit_count,
        safety_only=safety_only,
    )
    enabled_strategy_names = {strategy.name for strategy in strategy_plan if strategy.enabled}
    base_candidates = base_outer_candidates(gray_work, policy.outer.proposal.base.candidates)
    edge_candidates: list[OuterCandidate] = []
    if "edge_anchor" in enabled_strategy_names:
        edge_candidates = edge_anchored_outer_candidates(
            gray_work,
            base_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
        )
    floating_candidates: list[OuterCandidate] = []
    if "floating" in enabled_strategy_names and not edge_anchored_candidates_trusted(edge_candidates, policy):
        floating_candidates = floating_content_position_candidates(
            gray_work,
            base_candidates,
            fmt,
            count,
            strip_mode,
            policy,
        )
    pre_separator_candidates = unique_outer_candidates([*base_candidates, *edge_candidates, *floating_candidates])
    separator_candidates: list[OuterCandidate] = []
    if "separator_derived" in enabled_strategy_names:
        separator_candidates = separator_derived_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
            outer_scopes=separator_outer_scopes_for_policy(policy, strip_mode, explicit_count, safety_only=safety_only),
            gap_search_profiles=(WIDTH_AWARE_GAP_PROFILE,),
            explicit_count=explicit_count,
        )
    if safety_only:
        return unique_outer_candidates([*edge_candidates, *separator_candidates])
    return unique_outer_candidates([*base_candidates, *edge_candidates, *floating_candidates, *separator_candidates])


def separator_full_width_outer_proposal_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
    explicit_count: bool = True,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    return separator_derived_outer_candidates(
        gray_work,
        base_candidates,
        fmt,
        count,
        strip_mode,
        cache,
        policy,
        outer_scopes=(FULL_WIDTH_SEPARATOR_OUTER,),
        gap_search_profiles=(WIDTH_AWARE_GAP_PROFILE,),
        explicit_count=explicit_count,
    )


__all__ = [
    "OuterProposalStrategy",
    "edge_anchored_candidates_trusted",
    "merge_outer_proposal_candidates",
    "outer_candidate_strategy",
    "outer_proposal_candidates",
    "outer_proposal_strategy_plan_for_policy",
    "separator_full_width_outer_proposal_candidates",
]
