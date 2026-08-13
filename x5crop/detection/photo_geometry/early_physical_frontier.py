"""Cheap physical filtering before sampling and development artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from .axis_authority import (
    componentwise_authority_relation,
    tiered_authority_relation,
)
from .chain_authority import PlacementAxisAuthority, placement_axis_authority
from .chain_observation_accounting import (
    ChainObservationAccounting,
    account_chain_observations,
)
from .chains import CompleteFormatChain
from .content_topology import ContentTopologyIndex
from .content_veto import content_veto_assessment
from .content_veto_model import ContentVetoAssessment
from .observation_spatial_index import ChainObservationSpatialIndex


@dataclass(frozen=True)
class EarlyPlacementAssessment:
    placement: CompleteFormatChain
    authority: PlacementAxisAuthority
    accounting: ChainObservationAccounting
    content: ContentVetoAssessment | None


def _strictly_dominates(
    left: EarlyPlacementAssessment,
    right: EarlyPlacementAssessment,
) -> bool:
    if (
        left.placement.source_scan_geometry
        != right.placement.source_scan_geometry
    ):
        return False
    relations = (
        tiered_authority_relation(
            left.authority.sequence.components,
            right.authority.sequence.components,
        ),
        tiered_authority_relation(
            left.authority.cross.components,
            right.authority.cross.components,
        ),
        componentwise_authority_relation(
            left.authority.shared.components,
            right.authority.shared.components,
        ),
    )
    if any(value in {-1, None} for value in relations):
        return False
    if not any(value == 1 for value in relations):
        return False
    # A stronger vector is not allowed to erase a displaced direct pixel
    # observation unless the winning placement explicitly accounts for it.
    return set(right.authority.direct_observation_ids).issubset(
        left.accounting.accounted_observation_ids
    )


def _nondominated_frontier(
    assessed: tuple[EarlyPlacementAssessment, ...],
) -> tuple[EarlyPlacementAssessment, ...]:
    return tuple(
        item
        for item in assessed
        if not any(
            item is not other and _strictly_dominates(other, item)
            for other in assessed
        )
    )


def early_physical_frontier(
    placements: tuple[CompleteFormatChain, ...],
    *,
    observations: ChainObservationSpatialIndex,
    include_observation_facts: bool,
) -> tuple[EarlyPlacementAssessment, ...]:
    """Apply observation-bound axis dominance before content and sampling."""

    assessed = tuple(
        EarlyPlacementAssessment(
            placement=placement,
            accounting=account_chain_observations(
                placement,
                observations,
                include_facts=include_observation_facts,
            ),
            content=None,
            authority=placement_axis_authority(
                placement,
                content_veto_passed=True,
            ),
        )
        for placement in placements
    )
    return _nondominated_frontier(assessed)


def content_assessed_physical_frontier(
    assessed: tuple[EarlyPlacementAssessment, ...],
    *,
    content: ContentTopologyIndex,
) -> tuple[EarlyPlacementAssessment, ...]:
    """Add negative-only content facts after the cheap physical frontier."""

    with_content = tuple(
        replace(
            item,
            content=(assessment := content_veto_assessment(
                item.placement,
                content,
            )),
            authority=placement_axis_authority(
                item.placement,
                content_veto_passed=not assessment.vetoed,
            ),
        )
        for item in assessed
    )
    return _nondominated_frontier(with_content)
