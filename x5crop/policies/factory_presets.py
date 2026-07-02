from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .runtime_base import FrameFitPolicy
from .runtime_separator import SeparatorEdgePairPolicy

if TYPE_CHECKING:
    from .parameter_aggregate import FormatParameters


@dataclass(frozen=True)
class DarkBandModePreset:
    mode: str = "off"
    full_selection_enabled: bool = False
    separator_outer_allow_oversized_band: bool = False
    separator_outer_oversized_band_max_ratio: float = 0.45
    separator_outer_oversized_band_score_penalty: float = 0.08


@dataclass(frozen=True)
class ModePolicyPreset:
    role: str
    notes: tuple[str, ...] = ()
    detector_kind: str = "standard_strip"
    frame_fit: FrameFitPolicy | None = None
    dark_band: DarkBandModePreset = field(default_factory=DarkBandModePreset)
    separator_geometry_support_modes: tuple[str, ...] = ()
    diagnostics_overlap_bleed: bool = False


@dataclass(frozen=True)
class FormatPolicyPreset:
    format_id: str
    parameters: Callable[[], FormatParameters]
    separator_gate_profile: str
    separator_edge_pair: SeparatorEdgePairPolicy = field(default_factory=SeparatorEdgePairPolicy)
    content_mismatch_review_enabled: bool = False
    modes: dict[str, ModePolicyPreset] = field(default_factory=dict)


__all__ = [
    "DarkBandModePreset",
    "FormatPolicyPreset",
    "ModePolicyPreset",
]
