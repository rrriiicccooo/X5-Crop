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
from .model import BoundaryEvidenceState
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
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
    LOCAL_GAP_DELTA = "local_gap_delta"
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


def separator_support_authority(
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> dict[ObservationId, ObservationId]:
    """Map every connected separator family to one physical support fact."""

    parent: dict[ObservationId, ObservationId] = {}
    band_ids: dict[ObservationId, set[ObservationId]] = {}

    def find(identity: ObservationId) -> ObservationId:
        parent.setdefault(identity, identity)
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    def union(left: ObservationId, right: ObservationId) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    supported_bands = tuple(
        band
        for band in separator_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
    )
    for band in supported_bands:
        union(band.left_edge_observation_id, band.right_edge_observation_id)
    for band in supported_bands:
        root = find(band.left_edge_observation_id)
        band_ids.setdefault(root, set()).add(band.observation_id)
    return {
        identity: min(band_ids[find(identity)])
        for identity in parent
    }


def template_evidence_use_ledger(
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    cross_observations: tuple[PhotoBoundaryObservation, ...],
    phase: PhaseFitResult,
    cross: CrossFitCompetition,
) -> tuple[EvidenceUseFact, ...]:
    """Return one non-compensating use for every registered observation."""

    local_ids = {
        identity
        for relation in (() if phase.best is None else phase.best.local_advance_relations)
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
                if identity is not None and identity not in local_ids
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
            PhysicalUnknown.LOCAL_GAP_DELTA
            if identity in local_ids
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
                EvidenceUse.FIT if identity in local_ids else EvidenceUse.VALIDATION,
                PhysicalUnknown.LOCAL_GAP_DELTA,
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
    identities = tuple(item.observation_id for item in values)
    if len(set(identities)) != len(identities):
        raise ValueError("one physical observation cannot have multiple template uses")
    return tuple(values)
