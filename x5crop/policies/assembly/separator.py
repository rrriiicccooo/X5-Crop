from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ...strip_modes import FULL, PARTIAL
from ..runtime.separator import (
    SeparatorPolicy,
    SeparatorRefinementFamilyPolicy,
    SeparatorRefinementPolicy,
    SeparatorWidthProfilePolicy,
)


def separator_width_profile_policy(
    detector_kind: str,
    params: FormatParameters,
) -> SeparatorWidthProfilePolicy:
    mode = (
        "conditional"
        if detector_kind == "standard_strip"
        else "off"
    )
    return SeparatorWidthProfilePolicy(
        mode=mode,
        parameters=params.separator.separator_width_profile,
    )


def separator_refinement_policy(
    detector_kind: str,
) -> SeparatorRefinementPolicy:
    if detector_kind != "standard_strip":
        return SeparatorRefinementPolicy()
    standard_strip_modes = (FULL, PARTIAL)
    return SeparatorRefinementPolicy(
        edge_pair=SeparatorRefinementFamilyPolicy(
            mode="conditional",
            phase="primary",
            strip_modes=standard_strip_modes,
        ),
        nearby=SeparatorRefinementFamilyPolicy(
            mode="conditional",
            phase="extension",
            strip_modes=standard_strip_modes,
        ),
    )


def separator_policy(
    detector_kind: str,
    params: FormatParameters,
) -> SeparatorPolicy:
    hard_gap_trust = params.separator.hard_gap_trust
    nearby_refinement = params.separator.nearby_separator_refinement
    gap_search = params.separator.gap_search
    profile = params.separator.separator_profile
    edge_refine = params.separator.edge_refine_profile
    return SeparatorPolicy(
        width_profile=separator_width_profile_policy(
            detector_kind,
            params,
        ),
        width_profile_search=params.separator.separator_width_profile_search,
        refinement=separator_refinement_policy(detector_kind),
        edge_pair=params.separator.edge_pair,
        hard_gap_trust=hard_gap_trust,
        nearby_refinement=nearby_refinement,
        gap_search=gap_search,
        profile=profile,
        edge_refine_profile=edge_refine,
    )
