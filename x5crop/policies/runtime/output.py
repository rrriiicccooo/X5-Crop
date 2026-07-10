from __future__ import annotations

from dataclasses import dataclass

from ..parameters.exposure_overlap import (
    EdgeBleedProtectionParameters,
    ExposureOverlapProtectionParameters,
)


@dataclass(frozen=True)
class OutputPolicy:
    exposure_overlap_protection: ExposureOverlapProtectionParameters
    edge_bleed_protection: EdgeBleedProtectionParameters
