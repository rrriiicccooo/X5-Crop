from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import (
    EdgePairParameters,
    EdgeRefineProfileParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    NearbySeparatorRefinementParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from ..parameters.separator import SeparatorWidthProfileParameters
from ...strip_modes import FULL, PARTIAL


@dataclass(frozen=True)
class SeparatorWidthProfilePolicy:
    mode: str = "off"
    parameters: SeparatorWidthProfileParameters = field(
        default_factory=SeparatorWidthProfileParameters
    )


@dataclass(frozen=True)
class SeparatorRefinementFamilyPolicy:
    mode: str = "off"
    phase: str = "primary"
    strip_modes: tuple[str, ...] = (FULL,)

    def available_for(self, strip_mode: str, explicit_count: bool) -> bool:
        if self.mode == "off":
            return False
        if strip_mode not in self.strip_modes:
            return False
        if (
            strip_mode == PARTIAL
            and not explicit_count
        ):
            return False
        return True

    def block_reason(self, strip_mode: str, explicit_count: bool) -> str | None:
        if self.mode == "off":
            return "policy_disabled"
        if strip_mode not in self.strip_modes:
            return "strip_mode_not_enabled"
        if (
            strip_mode == PARTIAL
            and not explicit_count
        ):
            return "partial_requires_explicit_count"
        return None


@dataclass(frozen=True)
class SeparatorRefinementPolicy:
    edge_pair: SeparatorRefinementFamilyPolicy = field(default_factory=SeparatorRefinementFamilyPolicy)
    nearby: SeparatorRefinementFamilyPolicy = field(default_factory=SeparatorRefinementFamilyPolicy)


@dataclass(frozen=True)
class SeparatorPolicy:
    width_profile: SeparatorWidthProfilePolicy = field(default_factory=SeparatorWidthProfilePolicy)
    width_profile_search: SeparatorWidthProfileSearchParameters = field(default_factory=SeparatorWidthProfileSearchParameters)
    refinement: SeparatorRefinementPolicy = field(default_factory=SeparatorRefinementPolicy)
    edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)
    nearby_refinement: NearbySeparatorRefinementParameters = field(default_factory=NearbySeparatorRefinementParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
