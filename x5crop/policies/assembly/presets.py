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
class ModePolicyPreset:
    detector_kind: str = "standard_strip"
    frame_fit: FrameFitPolicy | None = None
    review_only: ReviewOnlyPolicy | None = None


@dataclass(frozen=True)
class FormatPolicyPreset:
    format_spec: FormatPhysicalSpec
    parameters: Callable[[], FormatParameters]
    separator_edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    modes: dict[str, ModePolicyPreset] = field(default_factory=dict)
