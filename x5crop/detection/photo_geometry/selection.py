from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId
from ..evidence.content_occupancy import ContentOccupancyObservationSet
from .bounds import (
    MAX_BANDS_PER_CORRIDOR,
    MAX_COMPLETE_CHAINS_PER_LANE,
    MAX_CONTENT_VETO_FACTS_PER_CHAIN,
    MAX_LEDGER_ENTRIES_PER_CHAIN,
    MAX_LEDGER_ENTRIES_PER_LANE,
)
from .model import BoundaryRole, SafeCropEnvelope
from .template_model import FormatPlacement, LocalAdvanceKind


RELIABLE_CONTENT_THRESHOLD = 0.75


class ProducerPruneReason(str, Enum):
    SAMPLING_CONTAINMENT_INVALID = "sampling_containment_invalid"
    BAND_BOUND = "band_bound"
    COMPLETE_CHAIN_BOUND = "complete_chain_bound"
    CHAIN_LEDGER_BOUND = "chain_ledger_bound"
    CONTENT_VETO_FACT_BOUND = "content_veto_fact_bound"
    CONTENT_OBSERVATION_BOUND = "content_observation_bound"


class ChainEvidenceTier(str, Enum):
    DIRECT_OPPOSITE_PAIR = "direct_opposite_pair"
    DIRECT_BOUNDARY = "direct_boundary"
    MEASURED_UNCERTAINTY = "measured_uncertainty"
    PHYSICAL_CONTRACT = "physical_contract"


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
class CompleteChainRecord:
    chain_id: str
    placement_id: str
    lane_id: str
    sampling_boxes: tuple[Box, ...]
    boundary_intervals_px: tuple[FiniteInterval, ...]
    direct_opposite_pair_count: int
    direct_boundary_count: int
    opposite_pair_observation_ids: tuple[ObservationId, ...]
    direct_boundary_observation_ids: tuple[ObservationId, ...]
    ledger: tuple[ChainLedgerEntry, ...]
    ledger_pruned_count: int

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or not self.placement_id
            or not self.lane_id
            or not self.sampling_boxes
            or any(not box.valid() for box in self.sampling_boxes)
            or not self.boundary_intervals_px
            or self.direct_opposite_pair_count < 0
            or self.direct_boundary_count < self.direct_opposite_pair_count * 2
            or len(set(self.opposite_pair_observation_ids))
            != len(self.opposite_pair_observation_ids)
            or len(set(self.direct_boundary_observation_ids))
            != len(self.direct_boundary_observation_ids)
            or len(self.ledger) > MAX_LEDGER_ENTRIES_PER_CHAIN
            or self.ledger_pruned_count < 0
            or any(
                item.chain_id != self.chain_id
                or item.ordinal != ordinal
                for ordinal, item in enumerate(self.ledger, 1)
            )
        ):
            raise ValueError("complete chain record is invalid")


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
    pruned_fact_count: int
    adjacent_start_end_content_is_neutral: bool = True
    contact_or_overlap_crossing_is_neutral: bool = True
    missing_content_is_neutral: bool = True

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.placement_id
            or len(self.facts) > MAX_CONTENT_VETO_FACTS_PER_CHAIN
            or self.pruned_fact_count < 0
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
    direct_opposite_pair_count: int
    direct_boundary_count: int
    opposite_pair_observation_ids: tuple[ObservationId, ...]
    direct_boundary_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            not self.cluster_id
            or not self.chain_ids
            or len(set(self.chain_ids)) != len(self.chain_ids)
            or not self.representative_placement_id
            or not self.sampling_boxes
            or not self.boundary_intersections_px
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
            or not 0
            <= self.materialized_complete_chain_count
            <= MAX_COMPLETE_CHAINS_PER_LANE
            or not 0 <= self.chain_ledger_entry_count <= MAX_LEDGER_ENTRIES_PER_LANE
            or len({item.reason for item in self.prune_summaries})
            != len(self.prune_summaries)
            or self.bound_exceeded
            != any(
                item.reason
                in {
                    ProducerPruneReason.BAND_BOUND,
                    ProducerPruneReason.COMPLETE_CHAIN_BOUND,
                    ProducerPruneReason.CHAIN_LEDGER_BOUND,
                    ProducerPruneReason.CONTENT_VETO_FACT_BOUND,
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


def _stable_id(prefix: str, fields: tuple[str, ...]) -> str:
    payload = "\x1f".join((prefix, *fields)).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _interval_fields(intervals: tuple[FiniteInterval, ...]) -> tuple[str, ...]:
    return tuple(
        value
        for interval in intervals
        for value in (interval.minimum.hex(), interval.maximum.hex())
    )


def _boundary_intervals(placement: FormatPlacement) -> tuple[FiniteInterval, ...]:
    return tuple(
        boundary.full_position_interval_px
        for frame in placement.canonical.frames
        for boundary in (frame.start, frame.end, frame.top, frame.bottom)
    )


def _direct_evidence(
    placement: FormatPlacement,
) -> tuple[int, int, tuple[ObservationId, ...], tuple[ObservationId, ...]]:
    sequence = placement.sequence
    sequence_by_ordinal: dict[int, dict[BoundaryRole, tuple[ObservationId, ...]]] = {}
    for evidence in sequence.observations:
        sequence_by_ordinal.setdefault(evidence.role.lane_ordinal, {})[
            evidence.role.role
        ] = evidence.transition_ids
    paired_ids = {
        identity
        for roles in sequence_by_ordinal.values()
        if set(roles) == {BoundaryRole.START, BoundaryRole.END}
        for values in roles.values()
        for identity in values
    }
    pair_count = sum(
        set(roles) == {BoundaryRole.START, BoundaryRole.END}
        for roles in sequence_by_ordinal.values()
    )
    direct_ids = {
        identity
        for roles in sequence_by_ordinal.values()
        for values in roles.values()
        for identity in values
    }
    direct_count = sum(len(roles) for roles in sequence_by_ordinal.values())
    cross = placement.cross
    cross_roles = {item.role for item in cross.evidence}
    cross_ids = {
        identity
        for item in cross.evidence
        for identity in item.observation.transition_ids
    }
    direct_ids.update(cross_ids)
    direct_count += len(cross_roles)
    if cross_roles == {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        pair_count += 1
        paired_ids.update(cross_ids)
    return (
        pair_count,
        direct_count,
        tuple(sorted(paired_ids, key=str)),
        tuple(sorted(direct_ids, key=str)),
    )


def _chain_ledger(
    placement: FormatPlacement,
    chain_id: str,
) -> tuple[tuple[ChainLedgerEntry, ...], int]:
    raw: list[tuple[ChainEvidenceTier, tuple[ObservationId, ...], FiniteInterval | None]] = [
        (ChainEvidenceTier.PHYSICAL_CONTRACT, (), None)
    ]
    sequence = placement.sequence
    paired_ordinals = {
        ordinal
        for ordinal in range(1, placement.output_slot_count + 1)
        if {
            item.role.role
            for item in sequence.observations
            if item.role.lane_ordinal == ordinal
        }
        == {BoundaryRole.START, BoundaryRole.END}
    }
    raw.extend(
        (
            ChainEvidenceTier.DIRECT_OPPOSITE_PAIR
            if item.role.lane_ordinal in paired_ordinals
            else ChainEvidenceTier.DIRECT_BOUNDARY,
            item.transition_ids,
            item.full_position_interval_px,
        )
        for item in sequence.observations
    )
    cross_roles = {item.role for item in placement.cross.evidence}
    raw.extend(
        (
            ChainEvidenceTier.DIRECT_OPPOSITE_PAIR
            if cross_roles == {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            else ChainEvidenceTier.DIRECT_BOUNDARY,
            item.observation.transition_ids,
            item.full_position_at_lane_reference_px,
        )
        for item in placement.cross.evidence
    )
    raw.extend(
        (
            ChainEvidenceTier.MEASURED_UNCERTAINTY,
            tuple(sorted(ids, key=str)),
            interval,
        )
        for interval, ids in zip(
            sequence.full_positions_px,
            sequence.safety_support_transition_ids,
            strict=True,
        )
        if ids
    )
    ordered = tuple(
        sorted(
            raw,
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
    retained = ordered[:MAX_LEDGER_ENTRIES_PER_CHAIN]
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
        for ordinal, (tier, ids, interval) in enumerate(retained, 1)
    )
    return entries, len(ordered) - len(retained)


def complete_chain_record(
    placement: FormatPlacement,
    envelopes: tuple[SafeCropEnvelope, ...],
) -> CompleteChainRecord:
    sampling_boxes = tuple(
        envelope.mapped_output_box
        for envelope in envelopes
        if envelope.mapped_output_box is not None
    )
    if len(sampling_boxes) != placement.output_slot_count:
        raise ValueError("complete chain lacks final sampling boxes")
    intervals = _boundary_intervals(placement)
    pair_count, direct_count, pair_ids, direct_ids = _direct_evidence(placement)
    chain_id = _stable_id(
        "complete-chain",
        (
            placement.placement_id,
            placement.lane_id,
            placement.component.component_id,
            placement.direction.direction_id,
            *_interval_fields(intervals),
            *(str(value) for value in direct_ids),
            *(
                str(value)
                for box in sampling_boxes
                for value in (box.left, box.top, box.right, box.bottom)
            ),
        ),
    )
    ledger, pruned = _chain_ledger(placement, chain_id)
    return CompleteChainRecord(
        chain_id=chain_id,
        placement_id=placement.placement_id,
        lane_id=placement.lane_id,
        sampling_boxes=sampling_boxes,
        boundary_intervals_px=intervals,
        direct_opposite_pair_count=pair_count,
        direct_boundary_count=direct_count,
        opposite_pair_observation_ids=pair_ids,
        direct_boundary_observation_ids=direct_ids,
        ledger=ledger,
        ledger_pruned_count=pruned,
    )


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return None if minimum > maximum else FiniteInterval(minimum, maximum)


def _weak_representative_key(
    placement: FormatPlacement,
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
    placements_by_id: dict[str, FormatPlacement],
) -> tuple[PlacementCluster, ...]:
    groups: list[list[CompleteChainRecord]] = []
    intersections: list[tuple[FiniteInterval, ...]] = []
    ordered_chains = tuple(
        sorted(
            chains,
            key=lambda item: (
                -item.direct_opposite_pair_count,
                -item.direct_boundary_count,
                item.lane_id,
                _interval_fields(item.boundary_intervals_px),
                tuple(map(str, item.direct_boundary_observation_ids)),
                item.chain_id,
            ),
        )
    )
    for chain in ordered_chains:
        for index, group in enumerate(groups):
            if group[0].sampling_boxes != chain.sampling_boxes:
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
        pair_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.opposite_pair_observation_ids
                },
                key=str,
            )
        )
        direct_ids = tuple(
            sorted(
                {
                    identity
                    for item in ordered
                    for identity in item.direct_boundary_observation_ids
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
                direct_opposite_pair_count=max(
                    item.direct_opposite_pair_count for item in ordered
                ),
                direct_boundary_count=max(
                    item.direct_boundary_count for item in ordered
                ),
                opposite_pair_observation_ids=pair_ids,
                direct_boundary_observation_ids=direct_ids,
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
    placement: FormatPlacement,
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
    frames = placement.canonical.frames
    for observation in reliable:
        sequence_interval, cross_interval = _source_axis_intervals(
            observation.source_box,
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
            if relation.kind in {LocalAdvanceKind.CONTACT, LocalAdvanceKind.OVERLAP}:
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
    retained = ordered[:MAX_CONTENT_VETO_FACTS_PER_CHAIN]
    assessment_id = _stable_id(
        "content-veto",
        (
            placement.placement_id,
            *(
                value
                for item in retained
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
        facts=retained,
        pruned_fact_count=len(ordered) - len(retained),
    )


def cluster_strictly_dominates(
    left: PlacementCluster,
    right: PlacementCluster,
) -> bool:
    levels = (
        (
            left.direct_opposite_pair_count,
            right.direct_opposite_pair_count,
            left.opposite_pair_observation_ids,
            right.opposite_pair_observation_ids,
        ),
        (
            left.direct_boundary_count,
            right.direct_boundary_count,
            left.direct_boundary_observation_ids,
            right.direct_boundary_observation_ids,
        ),
    )
    for left_count, right_count, left_ids, right_ids in levels:
        if left_count == right_count:
            continue
        return left_count > right_count and set(right_ids).issubset(left_ids)
    return False


def select_placement_clusters(
    chains: tuple[CompleteChainRecord, ...],
    placements_by_id: dict[str, FormatPlacement],
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
    assessment_by_placement = {
        item.placement_id: item for item in assessments
    }
    eligible = tuple(
        cluster
        for cluster in clusters
        if not assessment_by_placement[
            cluster.representative_placement_id
        ].vetoed
    )
    if len(eligible) == 1:
        selected = eligible[0]
    else:
        dominant = tuple(
            item
            for item in eligible
            if all(
                item is other or cluster_strictly_dominates(item, other)
                for other in eligible
            )
        )
        selected = dominant[0] if len(dominant) == 1 else None
    return LanePlacementSelection(
        chains=chains,
        clusters=clusters,
        content_veto_assessments=assessments,
        selected_cluster_id=(None if selected is None else selected.cluster_id),
        selected_placement_id=(
            None if selected is None else selected.representative_placement_id
        ),
        state=(
            EvidenceState.SUPPORTED
            if selected is not None
            else EvidenceState.UNAVAILABLE
        ),
    )
