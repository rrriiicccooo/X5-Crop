from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ....domain import OuterCandidate
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....policies.runtime_policy import DetectionPolicy
from ....runtime import AnalysisCache
from .base import base_outer_candidates
from .common import unique_outer_candidates
from .partial_content import floating_content_position_candidates
from .partial_edge import edge_anchored_outer_candidates
from .separator import (
    FULL_WIDTH_SEPARATOR_OUTER,
    SEPARATOR_WIDTH_PROFILE_OUTER,
    separator_derived_outer_candidates,
    separator_outer_variants_for_policy,
)


@dataclass(frozen=True)
class OuterProposalStrategy:
    name: str
    report_strategy: str
    mode: str
    fallback_only: bool
    risk_level: str

    @property
    def enabled(self) -> bool:
        return self.mode != "off"


def outer_proposal_strategy_plan_for_policy(
    policy: DetectionPolicy,
    fallback_only: bool = False,
) -> list[OuterProposalStrategy]:
    proposal_policy = policy.outer.proposal
    partial_placement = proposal_policy.geometry.partial_placement
    separator_mode = (
        "fallback"
        if fallback_only and separator_outer_variants_for_policy(policy, fallback_only=True)
        else "always"
        if (not fallback_only and separator_outer_variants_for_policy(policy, fallback_only=False))
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
    if fallback_only:
        return [strategy for strategy in active if strategy.mode == "fallback"]
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
    fallback_only: bool = False,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    strategy_plan = outer_proposal_strategy_plan_for_policy(policy, fallback_only=fallback_only)
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
            variants=separator_outer_variants_for_policy(policy, fallback_only=fallback_only),
        )
    if fallback_only:
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
        variants=(FULL_WIDTH_SEPARATOR_OUTER,),
    )


def separator_width_profile_outer_proposal_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
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
        variants=(SEPARATOR_WIDTH_PROFILE_OUTER,),
    )
