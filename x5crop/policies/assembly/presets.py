from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...geometry.detection_parameters import EdgePairParameters
from ..runtime.base import FrameFitPolicy, ReviewOnlyPolicy

if TYPE_CHECKING:
    from ...formats import FormatPhysicalSpec
    from ..parameters.aggregate import FormatParameters


@dataclass(frozen=True)
class SeparatorWidthProfilePreset:
    mode: str = "off"
    separator_outer_allow_oversized_band: bool = False
    separator_outer_oversized_band_max_ratio: float = 0.45
    separator_outer_oversized_band_score_penalty: float = 0.08


@dataclass(frozen=True)
class ModePolicyPreset:
    detector_kind: str = "standard_strip"
    frame_fit: FrameFitPolicy | None = None
    review_only: ReviewOnlyPolicy = field(default_factory=ReviewOnlyPolicy)
    separator_width_profile: SeparatorWidthProfilePreset = field(default_factory=SeparatorWidthProfilePreset)
    separator_geometry_support_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormatPolicyPreset:
    format_spec: FormatPhysicalSpec
    parameters: Callable[[], FormatParameters]
    separator_edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    modes: dict[str, ModePolicyPreset] = field(default_factory=dict)


__all__ = [
    "FormatPolicyPreset",
    "ModePolicyPreset",
    "SeparatorWidthProfilePreset",
]
