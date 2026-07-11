from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import OuterBoxDetectionParameters
from ..parameters.outer import (
    ContentContainmentCorrectionParameters,
    EdgeAnchoredContentPositionParameters,
    FloatingContentPositionParameters,
    FullWidthSeparatorOuterParameters,
    LongAxisGeometryCorrectionParameters,
    OuterAlignmentEvidenceParameters,
    SeparatorOuterBandParameters,
    ShortAxisGeometryCorrectionParameters,
)


@dataclass(frozen=True)
class OuterCorrectionFamilyPolicy:
    mode: str = "off"
    phase: str = "extension"
    requires_complete_hard_gaps: bool = False
    allowed_axes: tuple[str, ...] = ()
    max_shrink_ratio: float = 0.0
    max_expand_ratio: float = 0.0

@dataclass(frozen=True)
class ShortAxisGeometryCorrectionPolicy:
    family: OuterCorrectionFamilyPolicy
    parameters: ShortAxisGeometryCorrectionParameters


@dataclass(frozen=True)
class LongAxisGeometryCorrectionPolicy:
    family: OuterCorrectionFamilyPolicy
    parameters: LongAxisGeometryCorrectionParameters


@dataclass(frozen=True)
class ContentContainmentCorrectionPolicy:
    family: OuterCorrectionFamilyPolicy
    parameters: ContentContainmentCorrectionParameters


@dataclass(frozen=True)
class PartialPlacementGeometryPolicy:
    floating: FloatingContentPositionParameters
    edge_anchor: EdgeAnchoredContentPositionParameters
    enabled: bool = False
    position_order: tuple[str, ...] = ("edge_anchor", "floating")
    edge_trust_min_candidates: int = 2


@dataclass(frozen=True)
class SeparatorOuterFamilyPolicy:
    mode: str = "off"
    phase: str = "primary"
    requires_explicit_count_for_partial: bool = False
    max_candidates: int = 0

    def available_for(self, strip_mode: str, explicit_count: bool) -> bool:
        if self.mode == "off":
            return False
        if strip_mode == "partial" and self.requires_explicit_count_for_partial and not explicit_count:
            return False
        return True


@dataclass(frozen=True)
class SeparatorGeometryProposalPolicy:
    band: SeparatorOuterBandParameters
    full_width_outer: FullWidthSeparatorOuterParameters
    local: SeparatorOuterFamilyPolicy = field(default_factory=SeparatorOuterFamilyPolicy)
    full_width: SeparatorOuterFamilyPolicy = field(default_factory=SeparatorOuterFamilyPolicy)
    separator_gap_search_max_width_ratio: float = 0.095


@dataclass(frozen=True)
class GeometryOuterProposalPolicy:
    partial_placement: PartialPlacementGeometryPolicy
    separator: SeparatorGeometryProposalPolicy


@dataclass(frozen=True)
class OuterProposalPolicy:
    base: OuterBoxDetectionParameters
    geometry: GeometryOuterProposalPolicy


@dataclass(frozen=True)
class GeometryConsistencyCorrectionPolicy:
    long_axis: LongAxisGeometryCorrectionPolicy
    short_axis: ShortAxisGeometryCorrectionPolicy


@dataclass(frozen=True)
class OuterCorrectionPolicy:
    geometry_consistency: GeometryConsistencyCorrectionPolicy
    content_containment: ContentContainmentCorrectionPolicy


@dataclass(frozen=True)
class OuterPolicy:
    alignment_evidence: OuterAlignmentEvidenceParameters
    proposal: OuterProposalPolicy
    correction: OuterCorrectionPolicy
