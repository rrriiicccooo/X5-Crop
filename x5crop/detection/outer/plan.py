from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ...domain import OuterCandidate
from ...formats import FormatSpec
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from .base import base_outer_candidates, unique_outer_candidates
from .content_outer import floating_outer_candidates
from .edge_anchor import long_axis_edge_anchor_outer_candidates
from .separator import separator_derived_outer_candidates, separator_outer_variants_for_policy


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
            "always" if policy.outer.base_outer else "off",
            False,
            "low",
        ),
        OuterProposalStrategy(
            "content_floating",
            "content_outer",
            "always" if policy.outer.content_floating else "off",
            False,
            "medium",
        ),
    ]
    active = [
        OuterProposalStrategy(
            "long_axis_edge_anchor",
            "edge_anchor_outer",
            policy.outer.edge_anchor,
            True,
            "medium",
        ),
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
    base_candidates = base_outer_candidates(gray_work, policy.outer.base_candidates)
    floating_candidates = floating_outer_candidates(gray_work, base_candidates, fmt, count, strip_mode, policy)
    pre_separator_candidates = unique_outer_candidates([*base_candidates, *floating_candidates])
    long_axis_candidates: list[OuterCandidate] = []
    if "long_axis_edge_anchor" in enabled_strategy_names:
        long_axis_candidates = long_axis_edge_anchor_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
            policy,
        )
        pre_separator_candidates = unique_outer_candidates([*pre_separator_candidates, *long_axis_candidates])
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
        return unique_outer_candidates([*long_axis_candidates, *separator_candidates])
    return unique_outer_candidates([*base_candidates, *floating_candidates, *long_axis_candidates, *separator_candidates])
