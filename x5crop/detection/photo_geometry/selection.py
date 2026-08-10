from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import math

from ...domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    ObservationId,
)
from ..evidence.content_occupancy import ContentOccupancyObservationSet
from .bounds import (
    MAX_BANDS_PER_CORRIDOR,
)
from .model import BoundaryRole, PhotoBoundaryObservation, SafeCropEnvelope
from .observations import BoundaryEdgeObservation, SeparatorBandObservation
from .chains import CompleteFormatChain, LocalAdvanceKind
from .source_geometry import SourceScanGeometry


RELIABLE_CONTENT_THRESHOLD = 0.75


class ProducerPruneReason(str, Enum):
    SAMPLING_CONTAINMENT_INVALID = "sampling_containment_invalid"
    BAND_BOUND = "band_bound"
    CONTENT_OBSERVATION_BOUND = "content_observation_bound"


class ChainEvidenceTier(str, Enum):
    DIRECT_PHYSICAL_OBSERVATION = "direct_physical_observation"
    COMPLETE_PHYSICAL_STRUCTURE = "complete_physical_structure"
    MATERIAL_QUALITY = "material_quality"
    WEAK_PRIOR = "weak_prior"


class ObservationDisposition(str, Enum):
    DIRECT_ROLE_BOUND = "direct_role_bound"
    INFERRED_SUPPORT = "inferred_support"
    EXPLAINED_NON_BOUNDARY = "explained_non_boundary"
    CONTRADICTION = "contradiction"
    UNOBSERVABLE = "unobservable"


class ContentVetoReason(str, Enum):
    SLOT_CONTENT_CROPPED_IN = "slot_content_cropped_in"
    SEPARATOR_CORE_CONTENT_CROSSING = "separator_core_content_crossing"


@dataclass(frozen=True)
class CorridorBandCount:
    corridor_id: str
    proposed_count: int
    materialized_count: int

    def __post_init__(self) -> None:
        if (
            not self.corridor_id
            or self.proposed_count < self.materialized_count
            or self.materialized_count < 0
            or self.materialized_count > MAX_BANDS_PER_CORRIDOR
        ):
            raise ValueError("corridor band count is invalid")


@dataclass(frozen=True)
class ProducerPruneSummary:
    reason: ProducerPruneReason
    count: int

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("producer prune summary requires a positive count")


@dataclass(frozen=True)
class ChainLedgerEntry:
    entry_id: str
    chain_id: str
    ordinal: int
    evidence_tier: ChainEvidenceTier
    observation_ids: tuple[ObservationId, ...]
    physical_interval_px: FiniteInterval | None

    def __post_init__(self) -> None:
        if (
            not self.entry_id
            or not self.chain_id
            or self.ordinal <= 0
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("chain ledger entry is invalid")


@dataclass(frozen=True)
class ChainObservationFact:
    observation_id: ObservationId
    disposition: ObservationDisposition
    roles: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.reason or len(set(self.roles)) != len(self.roles):
            raise ValueError("chain observation fact is invalid")


@dataclass(frozen=True)
class CompleteChainRecord:
    chain_id: str
    placement_id: str
    lane_id: str
    sampling_boxes: tuple[Box, ...]
    sampling_authority_boxes: tuple[Box, ...]
    authority_profile_ids: tuple[str, ...]
    boundary_intervals_px: tuple[FiniteInterval, ...]
    direction_id: str
    source_scan_geometry_id: str
    direct_observation_count: int
    structural_pair_count: int
    direct_observation_ids: tuple[ObservationId, ...]
    structural_observation_ids: tuple[ObservationId, ...]
    normal_gap_supported: bool
    separator_material_quality: float
    local_advance_authorized: bool
    ledger: tuple[ChainLedgerEntry, ...]
    observation_facts: tuple[ChainObservationFact, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or not self.placement_id
            or not self.lane_id
            or not self.sampling_boxes
            or any(not box.valid() for box in self.sampling_boxes)
            or len(self.sampling_authority_boxes) != len(self.sampling_boxes)
            or any(not box.valid() for box in self.sampling_authority_boxes)
            or len(self.authority_profile_ids) != len(self.sampling_boxes)
            or not all(self.authority_profile_ids)
            or not self.boundary_intervals_px
            or not self.direction_id
            or not self.source_scan_geometry_id
            or self.direct_observation_count < 0
            or self.structural_pair_count < 0
            or len(set(self.direct_observation_ids))
            != len(self.direct_observation_ids)
            or len(set(self.structural_observation_ids))
            != len(self.structural_observation_ids)
            or not math.isfinite(self.separator_material_quality)
            or self.separator_material_quality < 0.0
            or not self.local_advance_authorized
            or any(
                item.chain_id != self.chain_id
                or item.ordinal != ordinal
                for ordinal, item in enumerate(self.ledger, 1)
            )
            or len({item.observation_id for item in self.observation_facts})
            != len(self.observation_facts)
        ):
            raise ValueError("complete chain record is invalid")

    @property
    def explained_non_boundary_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            item.observation_id
            for item in self.observation_facts
            if item.disposition
            == ObservationDisposition.EXPLAINED_NON_BOUNDARY
        )


@dataclass(frozen=True)
class ContentVetoFact:
    reason: ContentVetoReason
    slot_ordinal: int
    boundary_role: BoundaryRole | None
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.slot_ordinal <= 0
            or not self.observation_ids
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or (
                self.reason == ContentVetoReason.SLOT_CONTENT_CROPPED_IN
                and self.boundary_role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
            or (
                self.reason
                == ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING
                and self.boundary_role is not None
            )
        ):
            raise ValueError("content veto fact is invalid")


@dataclass(frozen=True)
class ContentVetoAssessment:
    assessment_id: str
    placement_id: str
    facts: tuple[ContentVetoFact, ...]
    adjacent_start_end_content_is_neutral: bool = True
    contact_or_overlap_crossing_is_neutral: bool = True
    missing_content_is_neutral: bool = True

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.placement_id
            or not self.adjacent_start_end_content_is_neutral
            or not self.contact_or_overlap_crossing_is_neutral
            or not self.missing_content_is_neutral
        ):
            raise ValueError("content veto assessment is invalid")

    @property
    def vetoed(self) -> bool:
        return bool(self.facts)


@dataclass(frozen=True)
class PlacementCluster:
    cluster_id: str
    chain_ids: tuple[str, ...]
    representative_placement_id: str
    sampling_boxes: tuple[Box, ...]
    boundary_intersections_px: tuple[FiniteInterval, ...]
    direct_observation_count: int
    structural_pair_count: int
    direct_observation_ids: tuple[ObservationId, ...]
    structural_observation_ids: tuple[ObservationId, ...]
    normal_gap_supported: bool
    separator_material_quality: float
    explained_non_boundary_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.cluster_id
            or not self.chain_ids
            or len(set(self.chain_ids)) != len(self.chain_ids)
            or not self.representative_placement_id
            or not self.sampling_boxes
            or not self.boundary_intersections_px
            or len(set(self.explained_non_boundary_ids))
            != len(self.explained_non_boundary_ids)
        ):
            raise ValueError("placement cluster is invalid")


@dataclass(frozen=True)
class ProducerBoundsReceipt:
    lane_id: str
    corridor_bands: tuple[CorridorBandCount, ...]
    proposed_complete_chain_count: int
    materialized_complete_chain_count: int
    chain_ledger_entry_count: int
    prune_summaries: tuple[ProducerPruneSummary, ...]
    bound_exceeded: bool

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.proposed_complete_chain_count
            < self.materialized_complete_chain_count
            or self.materialized_complete_chain_count < 0
            or self.chain_ledger_entry_count < 0
            or len({item.reason for item in self.prune_summaries})
            != len(self.prune_summaries)
            or self.bound_exceeded
            != any(
                item.reason
                in {
                    ProducerPruneReason.BAND_BOUND,
                    ProducerPruneReason.CONTENT_OBSERVATION_BOUND,
                }
                for item in self.prune_summaries
            )
        ):
            raise ValueError("producer bounds receipt is invalid")


@dataclass(frozen=True)
class LanePlacementSelection:
    chains: tuple[CompleteChainRecord, ...]
    clusters: tuple[PlacementCluster, ...]
    content_veto_assessments: tuple[ContentVetoAssessment, ...]
    selected_cluster_id: str | None
    selected_placement_id: str | None
    state: EvidenceState

    def __post_init__(self) -> None:
        selected = self.selected_cluster_id is not None
        if (
            selected != (self.selected_placement_id is not None)
            or selected != (self.state == EvidenceState.SUPPORTED)
            or len({item.chain_id for item in self.chains}) != len(self.chains)
            or len({item.cluster_id for item in self.clusters}) != len(self.clusters)
            or self.selected_cluster_id
            not in ({None} | {item.cluster_id for item in self.clusters})
        ):
            raise ValueError("lane placement selection is invalid")


@dataclass(frozen=True)
class SourcePlacementCombination:
    combination_id: str
    lane_cluster_ids: tuple[str, ...]
    lane_placement_ids: tuple[str, ...]
    shared_scan_geometry: SourceScanGeometry
    direct_observation_ids: tuple[ObservationId, ...]
    structural_observation_ids: tuple[ObservationId, ...]
    structural_strength: int
    separator_material_quality: float
    explained_non_boundary_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.combination_id
            or not self.lane_cluster_ids
            or len(self.lane_cluster_ids) != len(self.lane_placement_ids)
            or len(set(self.direct_observation_ids))
            != len(self.direct_observation_ids)
            or len(set(self.structural_observation_ids))
            != len(self.structural_observation_ids)
            or self.structural_strength < 0
            or not math.isfinite(self.separator_material_quality)
            or self.separator_material_quality < 0.0
            or len(set(self.explained_non_boundary_ids))
            != len(self.explained_non_boundary_ids)
        ):
            raise ValueError("source placement combination is invalid")


@dataclass(frozen=True)
class SourcePlacementSelection:
    combinations: tuple[SourcePlacementCombination, ...]
    selected_combination_id: str | None
    shared_scan_geometry: SourceScanGeometry | None
    state: EvidenceState

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        if (
            supported != (self.selected_combination_id is not None)
            or supported != (self.shared_scan_geometry is not None)
            or self.selected_combination_id
            not in ({None} | {item.combination_id for item in self.combinations})
        ):
            raise ValueError("source placement selection is invalid")


def _stable_id(prefix: str, fields: tuple[str, ...]) -> str:
    payload = "\x1f".join((prefix, *fields)).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _interval_fields(intervals: tuple[FiniteInterval, ...]) -> tuple[str, ...]:
    return tuple(
        value
        for interval in intervals
        for value in (interval.minimum.hex(), interval.maximum.hex())
    )


def _boundary_intervals(placement: CompleteFormatChain) -> tuple[FiniteInterval, ...]:
    return tuple(
        boundary.full_position_interval_px
        for frame in placement.fixed_frames.frames
        for boundary in (frame.start, frame.end, frame.top, frame.bottom)
    )


def _direct_evidence(
    placement: CompleteFormatChain,
) -> tuple[
    int,
    int,
    tuple[ObservationId, ...],
    tuple[ObservationId, ...],
    float,
]:
    sequence = placement.sequence
    sequence_by_ordinal: dict[int, dict[BoundaryRole, ObservationId]] = {}
    band_ids = {
        band.observation.observation_id for band in sequence.separator_bands
    }
    bound_band_edge_ids = {
        identity
        for band in sequence.separator_bands
        for identity in (
            band.observation.left_edge_observation_id,
            band.observation.right_edge_observation_id,
        )
    }
    for evidence in sequence.observations:
        if evidence.observation_id is None:
            continue
        sequence_by_ordinal.setdefault(evidence.role.lane_ordinal, {})[
            evidence.role.role
        ] = evidence.observation_id
    structural_ids = {
        identity
        for roles in sequence_by_ordinal.values()
        if set(roles) == {BoundaryRole.START, BoundaryRole.END}
        for identity in roles.values()
    }
    structural_pair_count = sum(
        set(roles) == {BoundaryRole.START, BoundaryRole.END}
        for roles in sequence_by_ordinal.values()
    )
    direct_ids = set(band_ids)
    direct_ids.update(
        identity
        for roles in sequence_by_ordinal.values()
        for identity in roles.values()
        if identity not in bound_band_edge_ids
    )
    cross = placement.cross
    cross_roles = {item.role for item in cross.evidence}
    cross_ids = {
        item.observation.observation_id for item in cross.evidence
    }
    direct_ids.update(cross_ids)
    if cross_roles == {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        structural_pair_count += 1
        structural_ids.update(cross_ids)
    material_quality = sum(
        band.observation.continuous_support_fraction
        + band.observation.darkness_contrast
        + band.observation.texture_contrast
        for band in sequence.separator_bands
    )
    return (
        len(direct_ids),
        structural_pair_count,
        tuple(sorted(direct_ids, key=str)),
        tuple(sorted(structural_ids, key=str)),
        material_quality,
    )


def placement_local_advance_authorized(placement: CompleteFormatChain) -> bool:
    """Require direct adjacency authority or a supported normal lane gap."""

    observed_roles = {
        (item.role.lane_ordinal, item.role.role)
        for item in placement.sequence.observations
    }
    for ordinal, relation in enumerate(
        placement.sequence.local_advance_relations,
        1,
    ):
        if relation.kind != LocalAdvanceKind.NOMINAL:
            if not relation.observation_ids:
                return False
            continue
        if {
            (ordinal, BoundaryRole.END),
            (ordinal + 1, BoundaryRole.START),
        }.issubset(observed_roles):
            continue
        if placement.sequence.lane_gap_model.state == EvidenceState.SUPPORTED:
            continue
        return False
    return True


def _chain_ledger(
    placement: CompleteFormatChain,
    chain_id: str,
) -> tuple[ChainLedgerEntry, ...]:
    raw: list[
        tuple[ChainEvidenceTier, tuple[ObservationId, ...], FiniteInterval | None]
    ] = []
    sequence = placement.sequence
    bound_band_edge_ids = {
        identity
        for band in sequence.separator_bands
        for identity in (
            band.observation.left_edge_observation_id,
            band.observation.right_edge_observation_id,
        )
    }
    raw.extend(
        (
            ChainEvidenceTier.DIRECT_PHYSICAL_OBSERVATION,
            (band.observation.observation_id,),
            band.observation.gap_interval_px,
        )
        for band in sequence.separator_bands
    )
    raw.extend(
        (
            ChainEvidenceTier.DIRECT_PHYSICAL_OBSERVATION,
            (item.observation_id,),
            item.full_position_interval_px,
        )
        for item in sequence.observations
        if item.observation_id is not None
        and item.observation_id not in bound_band_edge_ids
    )
    raw.extend(
        (
            ChainEvidenceTier.DIRECT_PHYSICAL_OBSERVATION,
            (item.observation.observation_id,),
            item.full_position_at_lane_reference_px,
        )
        for item in placement.cross.evidence
    )
    _, structural_count, _, structural_ids, material_quality = _direct_evidence(
        placement
    )
    if structural_count:
        raw.append(
            (
                ChainEvidenceTier.COMPLETE_PHYSICAL_STRUCTURE,
                structural_ids,
                None,
            )
        )
    if sequence.lane_gap_model.state == EvidenceState.SUPPORTED:
        raw.append(
            (
                ChainEvidenceTier.COMPLETE_PHYSICAL_STRUCTURE,
                sequence.lane_gap_model.supporting_observation_ids,
                sequence.lane_gap_model.gap_interval_px,
            )
        )
    if material_quality > 0.0:
        raw.append((ChainEvidenceTier.MATERIAL_QUALITY, (), None))
    raw.append((ChainEvidenceTier.WEAK_PRIOR, (), None))
    unique_raw = {
        (tier, ids, interval): (tier, ids, interval)
        for tier, ids, interval in raw
    }
    ordered = tuple(
        sorted(
            unique_raw.values(),
            key=lambda item: (
                tuple(ChainEvidenceTier).index(item[0]),
                () if item[2] is None else (
                    item[2].minimum.hex(),
                    item[2].maximum.hex(),
                ),
                tuple(map(str, item[1])),
            ),
        )
    )
    entries = tuple(
        ChainLedgerEntry(
            entry_id=_stable_id(
                "chain-ledger",
                (
                    chain_id,
                    str(ordinal),
                    tier.value,
                    *(str(value) for value in ids),
                    *( () if interval is None else (
                        interval.minimum.hex(),
                        interval.maximum.hex(),
                    )),
                ),
            ),
            chain_id=chain_id,
            ordinal=ordinal,
            evidence_tier=tier,
            observation_ids=ids,
            physical_interval_px=interval,
        )
        for ordinal, (tier, ids, interval) in enumerate(ordered, 1)
    )
    return entries


def _observation_facts(
    placement: CompleteFormatChain,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    top_bottom_observations: tuple[PhotoBoundaryObservation, ...],
) -> tuple[ChainObservationFact, ...]:
    frames = placement.fixed_frames.frames
    direct_roles: dict[ObservationId, set[str]] = {}

    def bind(identity: ObservationId, *roles: str) -> None:
        direct_roles.setdefault(identity, set()).update(roles)

    for band in placement.sequence.separator_bands:
        relation = band.relation_ordinal
        bind(
            band.observation.observation_id,
            f"end[{relation}]",
            f"start[{relation + 1}]",
        )
        bind(band.observation.left_edge_observation_id, f"end[{relation}]")
        bind(
            band.observation.right_edge_observation_id,
            f"start[{relation + 1}]",
        )
    for item in placement.sequence.observations:
        if item.observation_id is not None:
            bind(
                item.observation_id,
                f"{item.role.role.value}[{item.role.lane_ordinal}]",
            )
    for item in placement.cross.evidence:
        bind(item.observation.observation_id, item.role.value)

    edge_by_id = {item.observation_id: item for item in sequence_edges}
    raw: dict[
        ObservationId,
        tuple[str, FiniteInterval],
    ] = {
        item.observation_id: ("sequence_edge", item.coordinate_interval_px)
        for item in sequence_edges
    }
    for item in separator_bands:
        left = edge_by_id.get(item.left_edge_observation_id)
        right = edge_by_id.get(item.right_edge_observation_id)
        if left is not None and right is not None:
            raw[item.observation_id] = (
                "separator_band",
                FiniteInterval(
                    left.coordinate_interval_px.minimum,
                    right.coordinate_interval_px.maximum,
                ),
            )
    raw.update(
        {
            item.observation_id: ("cross_edge", item.offset_interval_px)
            for item in top_bottom_observations
        }
    )
    facts: list[ChainObservationFact] = []
    for identity, (kind, interval) in raw.items():
        if identity in direct_roles:
            facts.append(
                ChainObservationFact(
                    identity,
                    ObservationDisposition.DIRECT_ROLE_BOUND,
                    tuple(sorted(direct_roles[identity])),
                    "observation is bound to a physical boundary role",
                )
            )
            continue
        if kind in {"sequence_edge", "separator_band"}:
            explained = any(
                frame.start.full_position_interval_px.maximum
                < interval.center
                < frame.end.full_position_interval_px.minimum
                for frame in frames
            )
        else:
            explained = any(
                frame.top.full_position_interval_px.maximum
                < interval.center
                < frame.bottom.full_position_interval_px.minimum
                for frame in frames
            )
        facts.append(
            ChainObservationFact(
                identity,
                (
                    ObservationDisposition.EXPLAINED_NON_BOUNDARY
                    if explained
                    else ObservationDisposition.UNOBSERVABLE
                ),
                (),
                (
                    "observation lies inside a fixed format frame"
                    if explained
                    else "observation has no authorized boundary role in this chain"
                ),
            )
        )
    return tuple(sorted(facts, key=lambda item: str(item.observation_id)))


def complete_chain_record(
    placement: CompleteFormatChain,
    envelopes: tuple[SafeCropEnvelope, ...],
    *,
    sequence_edges: tuple[BoundaryEdgeObservation, ...] = (),
    separator_bands: tuple[SeparatorBandObservation, ...] = (),
    top_bottom_observations: tuple[PhotoBoundaryObservation, ...] = (),
) -> CompleteChainRecord:
    sampling_boxes = tuple(
        envelope.mapped_output_box
        for envelope in envelopes
        if envelope.mapped_output_box is not None
    )
    sampling_authority_boxes = tuple(
        envelope.sampling_authority_box for envelope in envelopes
    )
    authority_profile_ids = tuple(
        envelope.authority_profile_id for envelope in envelopes
    )
    if len(sampling_boxes) != placement.output_slot_count:
        raise ValueError("complete chain lacks final sampling boxes")
    if not placement_local_advance_authorized(placement):
        raise ValueError("complete chain has unresolved local advance")
    intervals = _boundary_intervals(placement)
    direct_count, pair_count, direct_ids, pair_ids, material_quality = (
        _direct_evidence(placement)
    )
    chain_id = _stable_id(
        "complete-chain",
        (
            placement.placement_id,
            placement.lane_id,
            *placement.frame_spec.identity_fields,
            placement.lane_geometry.direction.direction_id,
            *_interval_fields(intervals),
            *(str(value) for value in direct_ids),
            *(
                str(value)
                for box in sampling_boxes
                for value in (box.left, box.top, box.right, box.bottom)
            ),
        ),
    )
    ledger = _chain_ledger(placement, chain_id)
    return CompleteChainRecord(
        chain_id=chain_id,
        placement_id=placement.placement_id,
        lane_id=placement.lane_id,
        sampling_boxes=sampling_boxes,
        sampling_authority_boxes=sampling_authority_boxes,
        authority_profile_ids=authority_profile_ids,
        boundary_intervals_px=intervals,
        direction_id=placement.lane_geometry.direction.direction_id,
        source_scan_geometry_id=placement.source_scan_geometry.geometry_id,
        direct_observation_count=direct_count,
        structural_pair_count=pair_count,
        direct_observation_ids=direct_ids,
        structural_observation_ids=pair_ids,
        normal_gap_supported=(
            placement.sequence.lane_gap_model.state == EvidenceState.SUPPORTED
        ),
        separator_material_quality=material_quality,
        local_advance_authorized=True,
        ledger=ledger,
        observation_facts=_observation_facts(
            placement,
            sequence_edges,
            separator_bands,
            top_bottom_observations,
        ),
    )


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return None if minimum > maximum else FiniteInterval(minimum, maximum)


def _weak_representative_key(
    placement: CompleteFormatChain,
) -> tuple[object, ...]:
    residual = sum(
        item.fit_residual_px for item in placement.sequence.observations
    ) + sum(
        item.observation.fit_residual_px
        for item in placement.cross.evidence
    )
    uncertainty = sum(
        interval.width for interval in _boundary_intervals(placement)
    )
    return (residual, uncertainty, placement.placement_id)


def cluster_sampling_equivalent_chains(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> tuple[PlacementCluster, ...]:
    groups: list[list[CompleteChainRecord]] = []
    intersections: list[tuple[FiniteInterval, ...]] = []
    ordered_chains = tuple(
        sorted(
            chains,
            key=lambda item: (
                -item.direct_observation_count,
                -item.structural_pair_count,
                item.lane_id,
                _interval_fields(item.boundary_intervals_px),
                tuple(map(str, item.direct_observation_ids)),
                item.chain_id,
            ),
        )
    )
    for chain in ordered_chains:
        for index, group in enumerate(groups):
            if (
                group[0].sampling_boxes != chain.sampling_boxes
                or group[0].sampling_authority_boxes
                != chain.sampling_authority_boxes
                or group[0].authority_profile_ids != chain.authority_profile_ids
                or group[0].direction_id != chain.direction_id
                or group[0].source_scan_geometry_id != chain.source_scan_geometry_id
            ):
                continue
            merged = tuple(
                _intersection(left, right)
                for left, right in zip(
                    intersections[index],
                    chain.boundary_intervals_px,
                    strict=True,
                )
            )
            if any(value is None for value in merged):
                continue
            group.append(chain)
            intersections[index] = tuple(
                value for value in merged if value is not None
            )
            break
        else:
            groups.append([chain])
            intersections.append(chain.boundary_intervals_px)
    clusters: list[PlacementCluster] = []
    for group, common in zip(groups, intersections, strict=True):
        ordered = tuple(sorted(group, key=lambda item: item.chain_id))
        representative = min(
            ordered,
            key=lambda item: _weak_representative_key(
                placements_by_id[item.placement_id]
            ),
        )
        structural_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.structural_observation_ids
                },
                key=str,
            )
        )
        direct_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.direct_observation_ids
                },
                key=str,
            )
        )
        chain_ids = tuple(item.chain_id for item in ordered)
        cluster_id = _stable_id(
            "placement-cluster",
            (
                *chain_ids,
                *_interval_fields(common),
                *(
                    str(value)
                    for box in representative.sampling_boxes
                    for value in (box.left, box.top, box.right, box.bottom)
                ),
            ),
        )
        clusters.append(
            PlacementCluster(
                cluster_id=cluster_id,
                chain_ids=chain_ids,
                representative_placement_id=representative.placement_id,
                sampling_boxes=representative.sampling_boxes,
                boundary_intersections_px=common,
                direct_observation_count=max(
                    item.direct_observation_count for item in ordered
                ),
                structural_pair_count=max(
                    item.structural_pair_count for item in ordered
                ),
                direct_observation_ids=direct_ids,
                structural_observation_ids=structural_ids,
                normal_gap_supported=any(
                    item.normal_gap_supported for item in ordered
                ),
                separator_material_quality=max(
                    item.separator_material_quality for item in ordered
                ),
                explained_non_boundary_ids=tuple(
                    sorted(
                        {
                            identity
                            for item in ordered
                            for identity in item.explained_non_boundary_ids
                        },
                        key=str,
                    )
                ),
            )
        )
    return tuple(sorted(clusters, key=lambda item: item.cluster_id))


def _source_axis_intervals(box: Box, layout: str) -> tuple[FiniteInterval, FiniteInterval]:
    if layout == "horizontal":
        return (
            FiniteInterval(float(box.left), float(box.right - 1)),
            FiniteInterval(float(box.top), float(box.bottom - 1)),
        )
    if layout == "vertical":
        return (
            FiniteInterval(float(box.top), float(box.bottom - 1)),
            FiniteInterval(float(box.left), float(box.right - 1)),
        )
    raise ValueError("unsupported content-veto layout")


def content_veto_assessment(
    placement: CompleteFormatChain,
    observations: ContentOccupancyObservationSet,
    *,
    layout: str,
) -> ContentVetoAssessment:
    reliable = tuple(
        item
        for item in observations.observations
        if item.reliability >= RELIABLE_CONTENT_THRESHOLD
    )
    facts: list[ContentVetoFact] = []
    frames = placement.fixed_frames.frames
    for observation in reliable:
        for source_cell in observation.source_cells:
            sequence_interval, cross_interval = _source_axis_intervals(
                source_cell,
                layout,
            )
            for ordinal, frame in enumerate(frames, 1):
                slot_core = FiniteInterval(
                    frame.start.full_position_interval_px.maximum,
                    frame.end.full_position_interval_px.minimum,
                )
                if not slot_core.contains(sequence_interval.center):
                    continue
                for role, boundary in (
                    (BoundaryRole.TOP, frame.top),
                    (BoundaryRole.BOTTOM, frame.bottom),
                ):
                    interval = boundary.full_position_interval_px
                    if (
                        cross_interval.minimum < interval.minimum
                        and cross_interval.maximum > interval.maximum
                    ):
                        facts.append(
                            ContentVetoFact(
                                reason=ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
                                slot_ordinal=ordinal,
                                boundary_role=role,
                                observation_ids=(observation.observation_id,),
                            )
                        )
            gap = placement.sequence.lane_gap_model
            if (
                gap.state != EvidenceState.SUPPORTED
                or gap.gap_interval_px is None
                or gap.gap_interval_px.minimum <= 0.0
            ):
                continue
            relations = placement.sequence.local_advance_relations
            for ordinal, (left, right) in enumerate(zip(frames, frames[1:]), 1):
                relation = relations[ordinal - 1]
                if relation.kind in {
                    LocalAdvanceKind.CONTACT,
                    LocalAdvanceKind.OVERLAP,
                }:
                    continue
                if relation.kind != LocalAdvanceKind.NOMINAL:
                    continue
                core_minimum = left.end.full_position_interval_px.maximum
                core_maximum = right.start.full_position_interval_px.minimum
                if (
                    core_minimum < core_maximum
                    and sequence_interval.minimum < core_minimum
                    and sequence_interval.maximum > core_maximum
                ):
                    facts.append(
                        ContentVetoFact(
                            reason=ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING,
                            slot_ordinal=ordinal,
                            boundary_role=None,
                            observation_ids=(observation.observation_id,),
                        )
                    )
    ordered = tuple(
        sorted(
            {
                (
                    item.reason,
                    item.slot_ordinal,
                    item.boundary_role,
                    item.observation_ids,
                ): item
                for item in facts
            }.values(),
            key=lambda item: (
                item.reason.value,
                item.slot_ordinal,
                "" if item.boundary_role is None else item.boundary_role.value,
                tuple(map(str, item.observation_ids)),
            ),
        )
    )
    assessment_id = _stable_id(
        "content-veto",
        (
            placement.placement_id,
            *(
                value
                for item in ordered
                for value in (
                    item.reason.value,
                    str(item.slot_ordinal),
                    "none" if item.boundary_role is None else item.boundary_role.value,
                    *(str(identity) for identity in item.observation_ids),
                )
            ),
        ),
    )
    return ContentVetoAssessment(
        assessment_id=assessment_id,
        placement_id=placement.placement_id,
        facts=ordered,
    )


def cluster_strictly_dominates(
    left: PlacementCluster,
    right: PlacementCluster,
) -> bool:
    levels = (
        (
            left.direct_observation_count,
            right.direct_observation_count,
            left.direct_observation_ids,
            right.direct_observation_ids,
        ),
        (
            left.structural_pair_count + int(left.normal_gap_supported),
            right.structural_pair_count + int(right.normal_gap_supported),
            left.structural_observation_ids,
            right.structural_observation_ids,
        ),
    )
    for left_count, right_count, left_ids, right_ids in levels:
        if left_count == right_count:
            continue
        return left_count > right_count and (
            not right_ids or set(right_ids).issubset(left_ids)
        )
    return False


def prepare_placement_clusters(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, CompleteFormatChain],
    observations: ContentOccupancyObservationSet,
    *,
    layout: str,
) -> LanePlacementSelection:
    clusters = cluster_sampling_equivalent_chains(chains, placements_by_id)
    assessments = tuple(
        content_veto_assessment(
            placements_by_id[cluster.representative_placement_id],
            observations,
            layout=layout,
        )
        for cluster in clusters
    )
    return LanePlacementSelection(
        chains=chains,
        clusters=clusters,
        content_veto_assessments=assessments,
        selected_cluster_id=None,
        selected_placement_id=None,
        state=EvidenceState.UNAVAILABLE,
    )


def _eligible_clusters(selection: LanePlacementSelection) -> tuple[PlacementCluster, ...]:
    assessment_by_placement = {
        item.placement_id: item
        for item in selection.content_veto_assessments
    }
    return tuple(
        cluster
        for cluster in selection.clusters
        if not assessment_by_placement[cluster.representative_placement_id].vetoed
    )


def _source_combination(
    clusters: tuple[PlacementCluster, ...],
    placements_by_lane: tuple[dict[str, CompleteFormatChain], ...],
    *,
    shared_scan_geometry: SourceScanGeometry | None = None,
) -> SourcePlacementCombination | None:
    placements = tuple(
        placements_by_lane[index][cluster.representative_placement_id]
        for index, cluster in enumerate(clusters)
    )
    shared = shared_scan_geometry or placements[0].source_scan_geometry
    if shared_scan_geometry is None:
        try:
            for placement in placements[1:]:
                shared = shared.intersect_source_state(
                    placement.source_scan_geometry
                )
        except ValueError:
            return None
    direct_ids = tuple(
        sorted(
            {
                identity
                for cluster in clusters
                for identity in cluster.direct_observation_ids
            },
            key=str,
        )
    )
    structural_ids = tuple(
        sorted(
            {
                identity
                for cluster in clusters
                for identity in cluster.structural_observation_ids
            },
            key=str,
        )
    )
    cluster_ids = tuple(cluster.cluster_id for cluster in clusters)
    placement_ids = tuple(
        cluster.representative_placement_id for cluster in clusters
    )
    return SourcePlacementCombination(
        combination_id=_stable_id(
            "source-placement-combination",
            (*cluster_ids, shared.geometry_id),
        ),
        lane_cluster_ids=cluster_ids,
        lane_placement_ids=placement_ids,
        shared_scan_geometry=shared,
        direct_observation_ids=direct_ids,
        structural_observation_ids=structural_ids,
        structural_strength=sum(
            cluster.structural_pair_count
            + int(cluster.normal_gap_supported)
            for cluster in clusters
        ),
        separator_material_quality=sum(
            cluster.separator_material_quality for cluster in clusters
        ),
        explained_non_boundary_ids=tuple(
            sorted(
                {
                    identity
                    for cluster in clusters
                    for identity in cluster.explained_non_boundary_ids
                },
                key=str,
            )
        ),
    )


def _compatible_source_geometry_clusters(
    clusters: tuple[PlacementCluster, ...],
    placements: dict[str, CompleteFormatChain],
    placement: CompleteFormatChain,
) -> tuple[tuple[PlacementCluster, SourceScanGeometry], ...]:
    """Query the exact two-axis scale index for one left-lane chain."""

    geometry = placement.source_scan_geometry
    left_width = geometry.width_state.feasible_scale_interval()
    left_height = geometry.height_state.feasible_scale_interval()
    indexed = tuple(
        sorted(
            (
                (
                    cluster,
                    placements[
                        cluster.representative_placement_id
                    ].source_scan_geometry,
                )
                for cluster in clusters
                if placements[
                    cluster.representative_placement_id
                ].frame_spec.frame_spec_id
                == placement.frame_spec.frame_spec_id
            ),
            key=lambda item: (
                item[1].width_state.feasible_scale_interval().minimum,
                item[0].cluster_id,
            ),
        )
    )
    matches: list[tuple[PlacementCluster, SourceScanGeometry]] = []
    for cluster, right_geometry in indexed:
        right_width = right_geometry.width_state.feasible_scale_interval()
        right_height = right_geometry.height_state.feasible_scale_interval()
        if right_width.minimum > left_width.maximum:
            break
        if (
            right_width.maximum < left_width.minimum
            or right_height.maximum < left_height.minimum
            or right_height.minimum > left_height.maximum
        ):
            continue
        try:
            shared = geometry.intersect_source_state(right_geometry)
        except ValueError:
            continue
        matches.append((cluster, shared))
    return tuple(matches)
def _source_strictly_dominates(
    left: SourcePlacementCombination,
    right: SourcePlacementCombination,
) -> bool:
    levels = (
        (
            len(left.direct_observation_ids),
            len(right.direct_observation_ids),
            left.direct_observation_ids,
            right.direct_observation_ids,
        ),
        (
            left.structural_strength,
            right.structural_strength,
            left.structural_observation_ids,
            right.structural_observation_ids,
        ),
    )
    for left_count, right_count, left_ids, right_ids in levels:
        if left_count == right_count:
            continue
        explained = set(left.explained_non_boundary_ids)
        return left_count > right_count and (
            not right_ids
            or set(right_ids).issubset(set(left_ids) | explained)
        )
    return False


def select_source_placement_clusters(
    lane_selections: tuple[LanePlacementSelection, ...],
    placements_by_lane: tuple[dict[str, CompleteFormatChain], ...],
) -> tuple[tuple[LanePlacementSelection, ...], SourcePlacementSelection]:
    if (
        not lane_selections
        or len(lane_selections) != len(placements_by_lane)
        or len(lane_selections) > 2
    ):
        raise ValueError("source selection requires one or two aligned lanes")
    eligible_by_lane = tuple(
        _eligible_clusters(selection) for selection in lane_selections
    )
    combinations: list[SourcePlacementCombination] = []
    if len(lane_selections) == 1:
        for cluster in eligible_by_lane[0]:
            combination = _source_combination(
                (cluster,),
                placements_by_lane,
            )
            if combination is not None:
                combinations.append(combination)
    else:
        for left in eligible_by_lane[0]:
            left_placement = placements_by_lane[0][
                left.representative_placement_id
            ]
            for right, shared in _compatible_source_geometry_clusters(
                eligible_by_lane[1],
                placements_by_lane[1],
                left_placement,
            ):
                combination = _source_combination(
                    (left, right),
                    placements_by_lane,
                    shared_scan_geometry=shared,
                )
                if combination is not None:
                    combinations.append(combination)
    ordered = tuple(
        sorted(
            {item.combination_id: item for item in combinations}.values(),
            key=lambda item: item.combination_id,
        )
    )
    if len(ordered) == 1:
        selected = ordered[0]
    else:
        dominant = tuple(
            item
            for item in ordered
            if all(
                item is other or _source_strictly_dominates(item, other)
                for other in ordered
            )
        )
        selected = dominant[0] if len(dominant) == 1 else None
    if selected is None:
        resolved_lanes = lane_selections
    else:
        resolved_lanes = tuple(
            replace(
                selection,
                selected_cluster_id=cluster_id,
                selected_placement_id=placement_id,
                state=EvidenceState.SUPPORTED,
            )
            for selection, cluster_id, placement_id in zip(
                lane_selections,
                selected.lane_cluster_ids,
                selected.lane_placement_ids,
                strict=True,
            )
        )
    return (
        resolved_lanes,
        SourcePlacementSelection(
            combinations=ordered,
            selected_combination_id=(
                None if selected is None else selected.combination_id
            ),
            shared_scan_geometry=(
                None if selected is None else selected.shared_scan_geometry
            ),
            state=(
                EvidenceState.UNAVAILABLE
                if selected is None
                else EvidenceState.SUPPORTED
            ),
        ),
    )


def select_placement_clusters(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, CompleteFormatChain],
    observations: ContentOccupancyObservationSet,
    *,
    layout: str,
) -> LanePlacementSelection:
    prepared = prepare_placement_clusters(
        chains,
        placements_by_id,
        observations,
        layout=layout,
    )
    lanes, _source = select_source_placement_clusters(
        (prepared,),
        (placements_by_id,),
    )
    return lanes[0]
