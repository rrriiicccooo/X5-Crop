"""Physical material authority for directly visible separator bands."""

from __future__ import annotations

import math

from ...domain import FiniteInterval
from ..robust_statistics import REGISTERED_UINT8_QUANTIZATION_STEP
from .model import (
    BoundaryEvidenceState,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .observation_types import (
    SeparatorBandObservation,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)


def classify_separator_material_region(
    material_contrast_interval: FiniteInterval,
    core_texture_interval: FiniteInterval,
) -> SeparatorMaterialRegionState:
    """Classify one independent material region without a fitted score."""

    if (
        material_contrast_interval.minimum
        <= REGISTERED_UINT8_QUANTIZATION_STEP
    ):
        return SeparatorMaterialRegionState.TONE_UNRESOLVED
    if (
        material_contrast_interval.minimum
        <= core_texture_interval.maximum
        + REGISTERED_UINT8_QUANTIZATION_STEP
    ):
        return SeparatorMaterialRegionState.MATERIAL_NON_UNIFORM
    return SeparatorMaterialRegionState.SUPPORTED


def repeated_separator_material_supported(
    regions: tuple[SeparatorMaterialRegionObservation, ...],
) -> bool:
    """Return whether one oriented material state repeats independently.

    Tone polarity and within-core texture must close in the same region; two
    regions cannot contribute different channels to manufacture one band.
    Three supported regions are required later for source-wide role authority.
    """

    supported_regions = {
        region.region_index
        for region in regions
        if region.state == SeparatorMaterialRegionState.SUPPORTED
    }
    return len(supported_regions) >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS


def normal_separator_material_bands(
    bands: tuple[SeparatorBandObservation, ...],
    *,
    maximum_material_gap_px: float,
) -> tuple[SeparatorBandObservation, ...]:
    """Return bands allowed to establish one normal adjacency.

    Wider material remains registered evidence.  It may contradict or refine
    an adjacency whose roles were established independently, but it cannot
    create phase, ordinal mapping, or direct-role authority for itself.
    """

    if (
        not math.isfinite(maximum_material_gap_px)
        or maximum_material_gap_px < 0.0
    ):
        raise ValueError("normal separator gap limit must be finite")
    return tuple(
        band
        for band in bands
        if (
            band.evidence_state == BoundaryEvidenceState.SUPPORT
            and band.gap_interval_px.minimum <= maximum_material_gap_px
        )
    )


def normal_separator_material_conflicts(
    bands: tuple[SeparatorBandObservation, ...],
    *,
    maximum_material_gap_px: float,
) -> tuple[SeparatorBandObservation, ...]:
    """Return source-wide normal-gap pairs whose material stays unresolved."""

    if (
        not math.isfinite(maximum_material_gap_px)
        or maximum_material_gap_px < 0.0
    ):
        raise ValueError("normal separator gap limit must be finite")
    return tuple(
        band
        for band in bands
        if (
            len(band.material_regions) == SPATIAL_SUPPORT_REGION_COUNT
            and band.evidence_state == BoundaryEvidenceState.CONTRADICTION
            and band.gap_interval_px.minimum <= maximum_material_gap_px
        )
    )
