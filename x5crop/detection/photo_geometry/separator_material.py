"""Physical material authority for directly visible separator bands."""

from __future__ import annotations

from ..robust_statistics import REGISTERED_UINT8_QUANTIZATION_STEP
from .model import MINIMUM_INDEPENDENT_SUPPORT_REGIONS
from .observation_types import SeparatorMaterialRegionObservation


def repeated_dark_material_supported(
    regions: tuple[SeparatorMaterialRegionObservation, ...],
) -> bool:
    """Return whether a dark separator is resolved in repeated regions.

    A ``- / +`` boundary pair describes a local dark valley.  Its material
    authority therefore comes from the same darkness relation in at least two
    spatially independent regions.  A sub-code-value difference is not
    distinguishable after registered uint8 normalization.  Texture remains a
    reported quality fact, but cannot combine with darkness from another
    region to manufacture one direct black-band observation.
    """

    supported_regions = {
        region.region_index
        for region in regions
        if region.darkness_contrast_interval.minimum
        > REGISTERED_UINT8_QUANTIZATION_STEP
    }
    return len(supported_regions) >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
