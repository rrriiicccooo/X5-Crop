"""Auditable evidence ledger for complete physical chains."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .chain_authority import placement_local_advance_authorized
from .chains import CompleteFormatChain
from .candidate_sampling import ChainSamplingGeometry
from .chain_observation_accounting import (
    ChainObservationAccounting,
    account_chain_observations,
)
from .chain_direction_evidence import lane_direction_evidence
from .chain_record_model import (
    ChainEvidenceTier,
    ChainLedgerEntry,
    CompleteChainRecord,
)
from .model import BoundaryRole
from .observation_spatial_index import ChainObservationSpatialIndex
from .selection_identity import selection_fact_id

def interval_identity_fields(intervals: tuple[FiniteInterval, ...]) -> tuple[str, ...]:
    return tuple(
        value
        for interval in intervals
        for value in (interval.minimum.hex(), interval.maximum.hex())
    )


def placement_boundary_intervals(placement: CompleteFormatChain) -> tuple[FiniteInterval, ...]:
    return tuple(
        boundary.full_position_interval_px
        for frame in placement.fixed_frames.frames
        for boundary in (frame.start, frame.end, frame.top, frame.bottom)
    )


def direct_chain_evidence(
    placement: CompleteFormatChain,
) -> tuple[
    int,
    int,
    tuple[ObservationId, ...],
    tuple[ObservationId, ...],
    float,
    int,
    bool,
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
    # Separator attachment is finalized only after the complete placement is
    # known.  Its two role-bound sides must therefore participate in the
    # structural W-span ledger even when they were not part of the construction
    # seed.  This keeps evidence accounting independent of proposal order.
    for band in sequence.separator_bands:
        sequence_by_ordinal.setdefault(band.relation_ordinal, {})[
            BoundaryRole.END
        ] = band.observation.left_edge_observation_id
        sequence_by_ordinal.setdefault(band.relation_ordinal + 1, {})[
            BoundaryRole.START
        ] = band.observation.right_edge_observation_id
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
    cross_pair = (
        cross.direct_height_span_validated
        and cross_roles == {BoundaryRole.TOP, BoundaryRole.BOTTOM}
    )
    if cross_pair:
        structural_pair_count += 1
        structural_ids.update(cross_ids)
    material_quality = sum(
        band.observation.continuous_support_fraction
        + band.observation.darkness_contrast
        + band.observation.texture_contrast
        for band in sequence.separator_bands
    )
    support_region_count = sum(
        band.observation.independent_support_region_count
        for band in sequence.separator_bands
    )
    return (
        len(direct_ids),
        structural_pair_count,
        tuple(sorted(direct_ids, key=str)),
        tuple(sorted(structural_ids, key=str)),
        material_quality,
        support_region_count,
        cross_pair,
    )


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
    (
        _,
        structural_count,
        _,
        structural_ids,
        material_quality,
        _support_region_count,
        _cross_pair,
    ) = direct_chain_evidence(placement)
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
            entry_id=selection_fact_id(
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


def complete_chain_record(
    placement: CompleteFormatChain,
    sampling: ChainSamplingGeometry,
    *,
    observations: ChainObservationSpatialIndex,
    accounting: ChainObservationAccounting | None = None,
    development_detail: bool = False,
) -> CompleteChainRecord:
    if (
        sampling.placement_id != placement.placement_id
        or sampling.lane_id != placement.lane_id
    ):
        raise ValueError("chain sampling geometry belongs to another placement")
    sampling_boxes = sampling.sampling_boxes
    sampling_authority_boxes = sampling.sampling_authority_boxes
    authority_profile_ids = sampling.authority_profile_ids
    if len(sampling_boxes) != placement.output_slot_count:
        raise ValueError("complete chain lacks final sampling boxes")
    if not placement_local_advance_authorized(placement):
        raise ValueError("complete chain has unresolved local advance")
    intervals = placement_boundary_intervals(placement)
    (
        direct_count,
        pair_count,
        direct_ids,
        pair_ids,
        material_quality,
        separator_support_region_count,
        cross_pair,
    ) = direct_chain_evidence(placement)
    direction_disagreement, direction_observation_ids = (
        lane_direction_evidence(placement)
    )
    chain_id = selection_fact_id(
        "complete-chain",
        (
            placement.placement_id,
            placement.lane_id,
            *placement.frame_spec.identity_fields,
            placement.lane_geometry.direction.direction_id,
            *interval_identity_fields(intervals),
            *(str(value) for value in direct_ids),
            *(
                str(value)
                for box in sampling_boxes
                for value in (box.left, box.top, box.right, box.bottom)
            ),
        ),
    )
    if accounting is None:
        accounting = account_chain_observations(
            placement,
            observations,
            include_facts=development_detail,
        )
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
        separator_band_count=len(placement.sequence.separator_bands),
        structural_pair_count=pair_count,
        cross_axis_pair_supported=cross_pair,
        cross_axis_support_region_count=sum(
            item.observation.independent_support_region_count
            for item in placement.cross.evidence
        ),
        cross_axis_observation_ids=(
            tuple(sorted(
                (
                    item.observation.observation_id
                    for item in placement.cross.evidence
                ),
                key=str,
            ))
            if cross_pair
            else ()
        ),
        direct_observation_ids=direct_ids,
        structural_observation_ids=pair_ids,
        normal_gap_supported=(
            placement.sequence.lane_gap_model.state == EvidenceState.SUPPORTED
        ),
        separator_support_region_count=separator_support_region_count,
        lane_direction_disagreement_degrees=direction_disagreement,
        direction_observation_ids=direction_observation_ids,
        separator_material_quality=material_quality,
        local_advance_authorized=True,
        accounted_observation_ids=accounting.accounted_observation_ids,
        ledger=(
            _chain_ledger(placement, chain_id)
            if development_detail
            else ()
        ),
        observation_facts=accounting.facts,
    )
