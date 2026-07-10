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
from ..parameters.separator import (
    LeadingGridFailureParameters,
    SeparatorSupportParameters,
    SeparatorWidthProfileParameters,
)
from .base import FULL, PARTIAL


@dataclass(frozen=True)
class SeparatorGeometrySupportModePolicy:
    min_hard_ratio: float = 0.0
    min_joint_score: float = 1.0
    max_equal_gaps: int = 0
    max_photo_width_cv: float = 0.040
    required_content_support: str = "ok"
    max_outer_area_ratio: float = 0.995


@dataclass(frozen=True)
class SeparatorGeometrySupportPolicy:
    detected_geometry: SeparatorGeometrySupportModePolicy | None = None
    stable_grid: SeparatorGeometrySupportModePolicy | None = None

    def active_modes(self) -> tuple[str, ...]:
        modes: list[str] = []
        if self.detected_geometry is not None:
            modes.append("detected_geometry")
        if self.stable_grid is not None:
            modes.append("stable_grid")
        return tuple(modes)


@dataclass(frozen=True)
class SeparatorModelGapProposalPolicy:
    geometry_equal_model_strip_modes: tuple[str, ...] = ("full",)

    def geometry_equal_model_block_reason(
        self,
        *,
        strip_mode: str,
        count: int,
        default_count: int,
        gap_max_width_ratio_override: float | None,
        expected_gaps: int,
        hard_gaps: int,
    ) -> str | None:
        if strip_mode not in self.geometry_equal_model_strip_modes:
            return "strip_mode_not_enabled"
        if int(count) != int(default_count):
            return "non_default_count"
        if gap_max_width_ratio_override is not None:
            return "width_override_active"
        if int(expected_gaps) <= 0:
            return "single_frame"
        if int(hard_gaps) >= int(expected_gaps):
            return "hard_gaps_complete"
        return None


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
    target_gap_methods: tuple[str, ...] = ()
    model_promotion_gap_methods: tuple[str, ...] = ()

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
    support: SeparatorSupportParameters
    leading_grid_failure: LeadingGridFailureParameters
    model_gap_proposal: SeparatorModelGapProposalPolicy = field(default_factory=SeparatorModelGapProposalPolicy)
    width_profile: SeparatorWidthProfilePolicy = field(default_factory=SeparatorWidthProfilePolicy)
    width_profile_search: SeparatorWidthProfileSearchParameters = field(default_factory=SeparatorWidthProfileSearchParameters)
    refinement: SeparatorRefinementPolicy = field(default_factory=SeparatorRefinementPolicy)
    geometry_support: SeparatorGeometrySupportPolicy = field(default_factory=SeparatorGeometrySupportPolicy)
    edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)
    nearby_refinement: NearbySeparatorRefinementParameters = field(default_factory=NearbySeparatorRefinementParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
