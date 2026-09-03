"""Assign each registered observation one template responsibility.

The ledger prevents repeated raster traces or one physical structure from
becoming several independent votes.  It is explanatory provenance: fit
algorithms remain owned by the phase and cross modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import ObservationId
from .line_observations import PhotoBoundaryObservation
from .observation_types import (
    BoundaryEdgeObservation,
    AggregateEdgeResolution,
)
from .template_cross_model import CrossFitCompetition
from .template_phase_model import PhaseFitResult


class EvidenceUse(str, Enum):
    FIT = "fit"
    VALIDATION = "validation"


class PhysicalUnknown(str, Enum):
    PHASE = "phase"
    PITCH = "pitch"
    DIRECTION = "direction"
    CROSS_POSITION = "cross_position"
    ADJACENCY_RELATION = "adjacency_relation"
    LOCAL_BOUNDARY = "local_boundary"


@dataclass(frozen=True)
class EvidenceUseFact:
    observation_id: ObservationId
    use: EvidenceUse
    physical_owner: PhysicalUnknown

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.use, EvidenceUse)
            or not isinstance(self.physical_owner, PhysicalUnknown)
        ):
            raise ValueError("template evidence-use fact is invalid")


def template_evidence_use_ledger(
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    cross_observations: tuple[PhotoBoundaryObservation, ...],
    phase: PhaseFitResult,
    cross: CrossFitCompetition,
    aggregate_edge_resolutions: tuple[
        AggregateEdgeResolution,
        ...,
    ],
) -> tuple[EvidenceUseFact, ...]:
    """Return one non-compensating use for every registered observation."""

    adjacency_ids = {
        identity
        for relation in (() if phase.best is None else phase.best.adjacency_relations)
        for identity in relation.observation_ids
    }
    local_boundary_ids = set(
        ()
        if phase.best is None
        else phase.best.local_refinement_observation_ids
    )
    ordered_sequence_ids = tuple(
        dict.fromkeys(
            ()
            if phase.best is None
            else (
                identity
                for identity in phase.best.phase_anchor_observation_ids
                if identity is not None and identity not in adjacency_ids
            )
        )
    )
    phase_id = ordered_sequence_ids[0] if ordered_sequence_ids else None
    fit_sequence_ids = set(
        () if phase.best is None else phase.best.bound_observation_ids
    )

    direct_cross_ids = tuple(
        dict.fromkeys(
            () if cross.best is None else cross.best.direct_provenance_ids
        )
    )
    cross_position_id = direct_cross_ids[0] if direct_cross_ids else None
    direction_ids = set(
        ()
        if cross.best is None or cross.best.selected_direction is None
        else cross.best.selected_direction.selected_observation_ids
    )

    values: list[EvidenceUseFact] = []
    for observation in sequence_edges:
        identity = observation.observation_id
        owner = (
            PhysicalUnknown.ADJACENCY_RELATION
            if identity in adjacency_ids
            else PhysicalUnknown.LOCAL_BOUNDARY
            if identity in local_boundary_ids
            else PhysicalUnknown.PHASE
            if identity == phase_id
            else PhysicalUnknown.PITCH
        )
        values.append(
            EvidenceUseFact(
                identity,
                EvidenceUse.FIT if identity in fit_sequence_ids else EvidenceUse.VALIDATION,
                owner,
            )
        )
    for observation in separator_bands:
        identity = observation.observation_id
        values.append(
            EvidenceUseFact(
                identity,
                EvidenceUse.FIT
                if identity in adjacency_ids
                else EvidenceUse.VALIDATION,
                PhysicalUnknown.ADJACENCY_RELATION,
            )
        )
    for observation in cross_observations:
        identity = observation.observation_id
        owner = (
            PhysicalUnknown.CROSS_POSITION
            if identity == cross_position_id or identity not in direction_ids
            else PhysicalUnknown.DIRECTION
        )
        values.append(
            EvidenceUseFact(
                identity,
                EvidenceUse.FIT if identity in direct_cross_ids else EvidenceUse.VALIDATION,
                owner,
            )
        )
    used_ids = {item.observation_id for item in values}
    for resolution in aggregate_edge_resolutions:
        identity = resolution.support_observation_id
        if identity in used_ids:
            continue
        values.append(
            EvidenceUseFact(
                identity,
                EvidenceUse.VALIDATION,
                PhysicalUnknown.LOCAL_BOUNDARY,
            )
        )
        used_ids.add(identity)
    identities = tuple(item.observation_id for item in values)
    if len(set(identities)) != len(identities):
        raise ValueError("one physical observation cannot have multiple template uses")
    return tuple(values)
