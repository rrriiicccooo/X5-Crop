from __future__ import annotations

import numpy as np

from ....cache import MeasurementCache
from ....cache.separator import cached_edge_refine_profiles
from ....domain import Box, SeparatorBandObservation
from ....geometry.edge_pairs import refine_gaps_with_edge_profiles
from ....geometry.nearby_separator import apply_nearby_separator_refinement
from ....policies.runtime.separator import (
    SeparatorPolicy,
    SeparatorRefinementFamilyPolicy,
)


def _edge_pair_refinement_allowed(
    count: int,
    strip_mode: str,
    explicit_count: bool,
    family: SeparatorRefinementFamilyPolicy,
) -> bool:
    return bool(
        count > 1
        and family.block_reason(strip_mode, explicit_count) is None
    )


def apply_primary_separator_refinements(
    outer: Box,
    gaps: list[SeparatorBandObservation],
    count: int,
    strip_mode: str,
    explicit_count: bool,
    cache: MeasurementCache,
    separator_policy: SeparatorPolicy,
) -> list[SeparatorBandObservation]:
    if not _edge_pair_refinement_allowed(
        count,
        strip_mode,
        explicit_count,
        separator_policy.refinement.edge_pair,
    ):
        return list(gaps)
    edge, background, _activity = cached_edge_refine_profiles(
        cache,
        outer,
        separator_policy.edge_refine_profile,
    )
    return refine_gaps_with_edge_profiles(
        edge,
        background,
        gaps,
        count,
        separator_policy.edge_pair,
    )


def apply_nearby_separator_refinements(
    gaps: list[SeparatorBandObservation],
    profile: np.ndarray,
    pitch: float,
    count: int,
    strip_mode: str,
    explicit_count: bool,
    separator_policy: SeparatorPolicy,
) -> list[SeparatorBandObservation]:
    family = separator_policy.refinement.nearby
    if family.block_reason(strip_mode, explicit_count) is not None:
        return list(gaps)
    return apply_nearby_separator_refinement(
        profile,
        gaps,
        pitch,
        count,
        separator_policy.nearby_refinement,
    )
