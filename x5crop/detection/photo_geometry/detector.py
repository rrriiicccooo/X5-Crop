from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import Box, EvidenceState, FiniteInterval
from ...geometry.affine import AffineCoordinateTransform
from ..gate_checks import GateGap, TypedAssessment
from ..output_geometry import (
    OutputTransformAssessment,
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from ..source_core import SourceLaneEvidence
from ..evidence.content_occupancy import ContentOccupancyObservationSet
from .bounds import (
    MAX_BANDS_PER_CORRIDOR,
)
from .corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    frame_physical_pixel_intervals,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .measurement import measure_registered_queries, track_side_transition_regions
from .model import (
    BoundaryAxis,
    BoundaryRole,
    DirectUseBudgetAssessment,
    OutputSlotIdentity,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SequenceAnchorDiscoveryDomain,
    SharedStripDirection,
    SideTransitionRegion,
)
from .output import direct_use_budget_assessment, safe_crop_envelope_from_placement
from .source_geometry import LaneGapModel, SourceScanGeometry
from .selection import (
    CompleteChainRecord,
    CorridorBandCount,
    LanePlacementSelection,
    ProducerBoundsReceipt,
    ProducerPruneReason,
    ProducerPruneSummary,
    SourcePlacementSelection,
    complete_chain_record,
    placement_local_advance_authorized,
    prepare_placement_clusters,
    select_source_placement_clusters,
)
from .solver import (
    build_lane_physical_proposals,
    lane_directions_within_source_family,
    materialize_source_placements,
    rematerialize_complete_chain,
    shared_source_direction_classes,
)
from .chains import (
    CompleteFormatChain,
    CrossAxisProposal,
    LaneObservationInput,
    LanePhysicalProposals,
    ChainProducerWorkReceipt,
)
from .observations import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    build_sequence_observations,
    cross_profile_from_regions,
    sequence_profile_from_regions,
)


@dataclass(frozen=True)
class LaneFormatPlacementReconstruction:
    lane_id: str
    anchor_domain: SequenceAnchorDiscoveryDomain
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    side_transition_regions: tuple[SideTransitionRegion, ...]
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    sequence_edges: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    raw_top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    cross_axis_proposals: tuple[CrossAxisProposal, ...]
    lane_gap_model: LaneGapModel
    direction_classes: tuple[SharedStripDirection, ...]
    materialized_chains: tuple[CompleteFormatChain, ...]
    placement_selection: LanePlacementSelection
    selected_placement: CompleteFormatChain | None
    selected_chain_record: CompleteChainRecord | None
    producer_bounds: ProducerBoundsReceipt
    local_advance_unresolved_count: int
    safe_crop_envelopes: tuple[SafeCropEnvelope, ...]
    direct_use_budget_assessments: tuple[DirectUseBudgetAssessment, ...]
    work: ChainProducerWorkReceipt

    def __post_init__(self) -> None:
        if not self.lane_id or self.anchor_domain.lane_id != self.lane_id:
            raise ValueError("lane format placement lacks authority")
        if self.local_advance_unresolved_count < 0:
            raise ValueError("local advance unresolved count cannot be negative")
        if (self.selected_placement is None) != (
            self.placement_selection.state != EvidenceState.SUPPORTED
        ):
            raise ValueError("selected placement and selection state disagree")
        if self.selected_placement is not None and (
            self.selected_placement not in self.materialized_chains
            or self.selected_placement.placement_id
            != self.placement_selection.selected_placement_id
        ):
            raise ValueError("selected placement is not a materialized chain")
        if (self.selected_chain_record is None) != (
            self.selected_placement is None or not self.safe_crop_envelopes
        ):
            raise ValueError("selected chain audit record is incomplete")
        if self.selected_chain_record is not None and (
            self.selected_chain_record.placement_id
            != self.selected_placement.placement_id
            or self.selected_chain_record.source_scan_geometry_id
            != self.selected_placement.source_scan_geometry.geometry_id
        ):
            raise ValueError("selected chain audit record is not source-joint")
        if self.safe_crop_envelopes and (
            self.selected_placement is None
            or len(self.safe_crop_envelopes)
            != self.selected_placement.output_slot_count
        ):
            raise ValueError("lane outputs do not cover every format slot")


@dataclass(frozen=True)
class PhotoGeometryDetectionResult:
    resolved_output_slots: ResolvedOutputSlots | None
    lane_reconstructions: tuple[LaneFormatPlacementReconstruction, ...]
    source_placement_selection: SourcePlacementSelection
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    source_transform_assessment: OutputTransformAssessment
    lane_transform_assessments: tuple[OutputTransformAssessment, ...]
    assessment_facts: dict[str, TypedAssessment]

    def __post_init__(self) -> None:
        if self.resolved_output_slots is not None and (
            len(self.output_slot_identities)
            != self.resolved_output_slots.output_slot_count
        ):
            raise ValueError("resolved output slots require exact identities")
        if len(self.lane_transform_assessments) != len(
            self.lane_reconstructions
        ):
            raise ValueError("each reconstructed lane requires one transform")
        lane_selection_supported = bool(self.lane_reconstructions) and all(
            lane.placement_selection.state == EvidenceState.SUPPORTED
            for lane in self.lane_reconstructions
        )
        if lane_selection_supported != (
            self.source_placement_selection.state == EvidenceState.SUPPORTED
        ):
            raise ValueError("source and lane placement selections disagree")

    @property
    def safe_crop_envelopes(self) -> tuple[SafeCropEnvelope, ...]:
        return tuple(
            geometry
            for lane in self.lane_reconstructions
            for geometry in lane.safe_crop_envelopes
        )

    @property
    def direct_use_budget_assessments(
        self,
    ) -> tuple[DirectUseBudgetAssessment, ...]:
        return tuple(
            assessment
            for lane in self.lane_reconstructions
            for assessment in lane.direct_use_budget_assessments
        )

    @property
    def output_transforms(self) -> tuple[AffineCoordinateTransform, ...]:
        values: list[AffineCoordinateTransform] = []
        for lane, assessment in zip(
            self.lane_reconstructions,
            self.lane_transform_assessments,
            strict=True,
        ):
            if assessment.transform is None:
                continue
            values.extend(
                assessment.transform for _geometry in lane.safe_crop_envelopes
            )
        return tuple(values)


@dataclass(frozen=True)
class _PreparedLane:
    lane: SourceLaneEvidence
    layout: str
    output_slot_count: int
    measurement_slot_count: int
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    anchor_domain: SequenceAnchorDiscoveryDomain
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    side_regions: tuple[SideTransitionRegion, ...]
    top_regions: tuple[SideTransitionRegion, ...]
    bottom_regions: tuple[SideTransitionRegion, ...]
    transition_by_id: dict[str, PhotoBoundaryTransition]
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    sequence_edges: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    proposal: LanePhysicalProposals
    lane_gap_model: LaneGapModel
    corridor_band_counts: tuple[CorridorBandCount, ...]
    band_bound_exceeded: bool


def _lane_gap_model(
    lane_input: LaneObservationInput,
    source_geometry: SourceScanGeometry,
) -> LaneGapModel:
    # Search-time edge families have no ordinal authority.  The selected lane
    # gap model is created only after a complete sequence binds those roles.
    return LaneGapModel.from_ordinal_edges(
        source_geometry.width_state,
        lane_id=lane_input.lane_id,
        edge_families=(),
        format_gap_prior_mm=source_geometry.frame_spec.format_gap_prior_mm,
    )


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane: SourceLaneEvidence,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return configuration.physical_spec.holder_full_count(profile.profile_id) or 0


def _lane_measurement_capacity(
    configuration: DetectionConfiguration,
    lanes: tuple[SourceLaneEvidence, ...],
    lane: SourceLaneEvidence,
) -> int:
    capacity = _profile_capacity(configuration, lane)
    if configuration.physical_spec.layout.kind == "dual_lane":
        if not lanes or capacity % len(lanes):
            return 0
        return capacity // len(lanes)
    return capacity


def resolve_output_slots(
    configuration: DetectionConfiguration,
    lanes: tuple[SourceLaneEvidence, ...],
    resolved_slot_count: ResolvedSlotCount | None,
) -> ResolvedOutputSlots | None:
    if not lanes or resolved_slot_count is None:
        return None
    requested = resolved_slot_count.output_count
    if configuration.physical_spec.layout.kind == "dual_lane":
        capacity = _profile_capacity(configuration, lanes[0])
        if (
            requested != capacity
            or requested % len(lanes)
        ):
            return None
        return ResolvedOutputSlots(
            tuple(requested // len(lanes) for _lane in lanes)
        )
    capacity = _profile_capacity(configuration, lanes[0])
    if requested <= 0 or requested > capacity:
        return None
    return ResolvedOutputSlots((requested,))


def _source_axes(layout: str) -> tuple[BoundaryAxis, BoundaryAxis]:
    if layout == "horizontal":
        return BoundaryAxis.X, BoundaryAxis.Y
    if layout == "vertical":
        return BoundaryAxis.Y, BoundaryAxis.X
    raise ValueError(f"unsupported source layout: {layout}")


def _axis_interval(box: Box, axis: BoundaryAxis) -> FiniteInterval:
    return (
        FiniteInterval(float(box.left), float(box.right - 1))
        if axis == BoundaryAxis.X
        else FiniteInterval(float(box.top), float(box.bottom - 1))
    )


def _coordinate_count(interval: FiniteInterval) -> int:
    return max(1, int(math.floor(interval.maximum) - math.ceil(interval.minimum) + 1))


def _bounded_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm,
) -> tuple[tuple[SideTransitionRegion, ...], tuple[CorridorBandCount, ...], bool]:
    retained: dict[str, SideTransitionRegion] = {}
    counts: list[CorridorBandCount] = []
    exceeded = False
    for measurement_set in measurement_sets:
        proposed = track_side_transition_regions(
            (measurement_set,),
            reference_trace_px=reference_trace_px,
            boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        )
        ordered = tuple(
            sorted(
                proposed,
                key=lambda item: (
                    1 if item.ambiguous else 0,
                    -item.trace_support_count,
                    item.proposal_position_interval_px.minimum,
                    item.proposal_position_interval_px.maximum,
                    item.region_id,
                ),
            )
        )
        overflowed = len(ordered) > MAX_BANDS_PER_CORRIDOR
        # An overflowing corridor is not partially ranked.  Preserve its full
        # proposed count, materialize no biased subset, and let the typed
        # producer Gate route the source to review.
        materialized = () if overflowed else ordered
        exceeded = exceeded or overflowed
        counts.append(
            CorridorBandCount(
                corridor_id=measurement_set.query.query_id,
                proposed_count=len(ordered),
                materialized_count=len(materialized),
            )
        )
        retained.update({item.region_id: item for item in materialized})
    return (
        tuple(
            sorted(
                retained.values(),
                key=lambda item: (
                    item.proposal_position_interval_px.minimum,
                    item.proposal_position_interval_px.maximum,
                    item.region_id,
                ),
            )
        ),
        tuple(counts),
        exceeded,
    )


def _prepare_lane(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    output_slot_count: int,
    measurement_slot_count: int,
    configuration: DetectionConfiguration,
) -> _PreparedLane:
    width_axis, height_axis = _source_axes(layout)
    authority = source_lane_box(lane, layout)
    width_authority = _axis_interval(authority, width_axis)
    height_authority = _axis_interval(authority, height_axis)
    scales = lane.scan_canvas.axis_scales
    frame_spec_pixels = frame_physical_pixel_intervals(
        configuration.physical_spec.frame,
        scales.width_axis_px_per_mm,
        scales.height_axis_px_per_mm,
    )
    top_corridor, bottom_corridor = build_top_bottom_search_corridors(
        lane,
        layout=layout,
        aperture_pixels=frame_spec_pixels,
    )
    anchor_domain = build_sequence_anchor_discovery_domain(
        lane,
        layout=layout,
        authoritative_sequence_length=measurement_slot_count,
        aperture_pixels=frame_spec_pixels,
    )
    queries = registered_lane_measurement_queries(
        lane,
        layout=layout,
        aperture_pixels=frame_spec_pixels,
        top_corridor=top_corridor,
        bottom_corridor=bottom_corridor,
        anchor_domain=anchor_domain,
    )
    measurement_sets = measure_registered_queries(field, queries)
    transition_by_id = {
        str(transition.transition_id): transition
        for measurement_set in measurement_sets
        for transition in measurement_set.transitions
    }
    side_regions, side_counts, side_exceeded = _bounded_transition_regions(
        measurement_sets[2:],
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    top_regions, top_counts, top_exceeded = _bounded_transition_regions(
        (measurement_sets[0],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    bottom_regions, bottom_counts, bottom_exceeded = _bounded_transition_regions(
        (measurement_sets[1],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    sequence_profile = sequence_profile_from_regions(
        side_regions,
        coordinate_count=_coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    cross_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=_coordinate_count(height_authority),
        transition_by_id=transition_by_id,
    )
    sequence_edges, separator_bands = build_sequence_observations(
        sequence_profile,
        transition_by_id,
    )
    lane_input = LaneObservationInput(
        lane_id=lane.domain.lane_id,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority,
        height_authority_px=height_authority,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
        sequence_profile=sequence_profile,
        cross_profile=cross_profile,
        sequence_edges=sequence_edges,
        separator_bands=separator_bands,
        sequence_measurement_sets=measurement_sets[2:],
        top_measurement_set=measurement_sets[0],
        bottom_measurement_set=measurement_sets[1],
        transition_by_id=transition_by_id,
    )
    proposal = build_lane_physical_proposals(
        lane_input,
        configuration.physical_spec.frame,
    )
    lane_gap_model = _lane_gap_model(
        lane_input,
        SourceScanGeometry.create(
            configuration.physical_spec.frame,
            width_scale_px_per_mm=scales.width_axis_px_per_mm,
            height_scale_px_per_mm=scales.height_axis_px_per_mm,
        ),
    )
    return _PreparedLane(
        lane=lane,
        layout=layout,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority,
        height_authority_px=height_authority,
        anchor_domain=anchor_domain,
        measurement_sets=measurement_sets,
        side_regions=side_regions,
        top_regions=top_regions,
        bottom_regions=bottom_regions,
        transition_by_id=transition_by_id,
        sequence_profile=sequence_profile,
        cross_profile=cross_profile,
        sequence_edges=sequence_edges,
        separator_bands=separator_bands,
        proposal=proposal,
        lane_gap_model=lane_gap_model,
        corridor_band_counts=(*top_counts, *bottom_counts, *side_counts),
        band_bound_exceeded=(
            top_exceeded or bottom_exceeded or side_exceeded
        ),
    )


def _supported() -> TypedAssessment:
    return TypedAssessment(EvidenceState.SUPPORTED, None)


def _unavailable(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.UNAVAILABLE, gap)


def _contradicted(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.CONTRADICTED, gap)


def _empty_transform(
    field: PhotoBoundaryMeasurementField,
    layout: str,
    gap: str,
) -> OutputTransformAssessment:
    return output_transform_assessment(
        SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap=gap,
        ),
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
    )


def _output_slot_identities(
    lanes: tuple[SourceLaneEvidence, ...],
    resolved: ResolvedOutputSlots,
) -> tuple[OutputSlotIdentity, ...]:
    identities: list[OutputSlotIdentity] = []
    for lane, count in zip(lanes, resolved.lane_output_slot_counts, strict=True):
        for ordinal in range(1, count + 1):
            identities.append(
                OutputSlotIdentity(
                    global_output_ordinal=len(identities) + 1,
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                )
            )
    return tuple(identities)


def _work_receipt(
    prepared: _PreparedLane,
    placements: tuple[CompleteFormatChain, ...],
    *,
    refinement_query_count: int = 0,
    proposal: LanePhysicalProposals | None = None,
) -> ChainProducerWorkReceipt:
    active_proposal = prepared.proposal if proposal is None else proposal
    active_sequence_profile = active_proposal.lane.sequence_profile
    grouping = tuple(
        frame_spec.grouping_work
        for frame_spec in active_proposal.frame_proposals
    )
    group_count = sum(
        len(frame_spec.sequence_groups)
        for frame_spec in active_proposal.frame_proposals
    )
    profile_query_ids = {
        prepared.transition_by_id[str(identity)].query_id
        for profile in (active_sequence_profile, prepared.cross_profile)
        for run in profile.runs
        for identity in run.transition_ids
    }
    completed_measurement_count = sum(
        item.coverage.complete for item in prepared.measurement_sets
    )
    receipt = ChainProducerWorkReceipt(
        measurement_query_count=len(prepared.measurement_sets),
        pixel_query_count=sum(
            item.coverage.pixel_query_count for item in prepared.measurement_sets
        ),
        basic_profile_coordinate_count=(
            active_sequence_profile.coordinate_count
            + prepared.cross_profile.coordinate_count
        ),
        basic_profile_run_count=(
            len(active_sequence_profile.runs)
            + len(prepared.cross_profile.runs)
        ),
        role_proposal_count=sum(
            len(frame_spec.role_proposals)
            for frame_spec in active_proposal.frame_proposals
        ),
        sequence_group_count=group_count,
        ordinal_role_lookup_count=sum(
            item.ordinal_role_lookup_count for item in grouping
        ),
        ordinal_role_match_count=sum(
            item.ordinal_role_match_count for item in grouping
        ),
        local_relation_evaluation_count=(
            group_count * max(0, prepared.output_slot_count - 1)
        ),
        refinement_query_count=refinement_query_count,
        materialized_frame_geometry_count=sum(
            len(item.fixed_frames.frames) for item in placements
        ),
        shared_measurement_reuse_count=(
            completed_measurement_count + len(profile_query_ids)
        ),
        domain_pixels=(
            prepared.lane.domain.work_box.width
            * prepared.lane.domain.work_box.height
        ),
        peak_temporary_bytes=max(
            (item.coverage.peak_temporary_bytes for item in prepared.measurement_sets),
            default=0,
        ),
    )
    if active_proposal.frame_proposals:
        receipt.validate_bounds(
            ordered_role_count=prepared.output_slot_count * 2,
            slot_count=prepared.output_slot_count,
            registered_refinement_query_count=sum(
                len(frame_spec.registered_sequence_role_queries)
                for frame_spec in active_proposal.frame_proposals
            ),
        )
    return receipt


def _producer_bounds_receipt(
    prepared: _PreparedLane,
    *,
    proposed_chain_count: int = 0,
    chains: tuple[CompleteChainRecord, ...] = (),
    sampling_invalid_count: int = 0,
    content_observation_excess_count: int = 0,
) -> ProducerBoundsReceipt:
    pruned: dict[ProducerPruneReason, int] = {}
    if sampling_invalid_count:
        pruned[ProducerPruneReason.SAMPLING_CONTAINMENT_INVALID] = (
            sampling_invalid_count
        )
    band_pruned = sum(
        item.proposed_count - item.materialized_count
        for item in prepared.corridor_band_counts
    )
    if band_pruned:
        pruned[ProducerPruneReason.BAND_BOUND] = band_pruned
    if content_observation_excess_count:
        pruned[ProducerPruneReason.CONTENT_OBSERVATION_BOUND] = (
            content_observation_excess_count
        )
    return ProducerBoundsReceipt(
        lane_id=prepared.lane.domain.lane_id,
        corridor_bands=prepared.corridor_band_counts,
        proposed_complete_chain_count=proposed_chain_count,
        materialized_complete_chain_count=len(chains),
        chain_ledger_entry_count=sum(len(item.ledger) for item in chains),
        prune_summaries=tuple(
            ProducerPruneSummary(reason=reason, count=pruned[reason])
            for reason in ProducerPruneReason
            if reason in pruned
        ),
        bound_exceeded=any(
            reason
            != ProducerPruneReason.SAMPLING_CONTAINMENT_INVALID
            for reason in pruned
        ),
    )


def _empty_reconstruction(
    prepared: _PreparedLane,
    *,
    content_observation_excess_count: int = 0,
) -> LaneFormatPlacementReconstruction:
    selection = LanePlacementSelection(
        chains=(),
        clusters=(),
        content_veto_assessments=(),
        selected_cluster_id=None,
        selected_placement_id=None,
        state=EvidenceState.UNAVAILABLE,
    )
    return LaneFormatPlacementReconstruction(
        lane_id=prepared.lane.domain.lane_id,
        anchor_domain=prepared.anchor_domain,
        measurement_sets=prepared.measurement_sets,
        side_transition_regions=prepared.side_regions,
        sequence_profile=prepared.sequence_profile,
        cross_profile=prepared.cross_profile,
        sequence_edges=prepared.sequence_edges,
        separator_bands=prepared.separator_bands,
        raw_top_bottom_observations=(
            prepared.proposal.raw_top_bottom_observations
        ),
        cross_axis_proposals=tuple(
            cross_proposal
            for frame_spec in prepared.proposal.frame_proposals
            for cross_proposal in frame_spec.cross_proposals
        ),
        lane_gap_model=prepared.lane_gap_model,
        direction_classes=prepared.proposal.direction_classes,
        materialized_chains=(),
        placement_selection=selection,
        selected_placement=None,
        selected_chain_record=None,
        producer_bounds=_producer_bounds_receipt(
            prepared,
            content_observation_excess_count=content_observation_excess_count,
        ),
        local_advance_unresolved_count=0,
        safe_crop_envelopes=(),
        direct_use_budget_assessments=(),
        work=_work_receipt(prepared, ()),
    )


def _empty_source_placement_selection() -> SourcePlacementSelection:
    return SourcePlacementSelection(
        combinations=(),
        selected_combination_id=None,
        shared_scan_geometry=None,
        state=EvidenceState.UNAVAILABLE,
    )


def _unresolved_facts(
    direction_gap: GateGap,
    *,
    source_lane_authority_available: bool = True,
) -> dict[str, TypedAssessment]:
    return {
        "scan_canvas_authority": _supported(),
        "output_slot_count": _supported(),
        "observation_completeness": _supported(),
        "source_scan_geometry": _unavailable(
            GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE
        ),
        "shared_strip_direction": _unavailable(direction_gap),
        "complete_chain": _unavailable(GateGap.COMPLETE_CHAIN_UNAVAILABLE),
        "producer_coverage": _supported(),
        "independent_evidence": _unavailable(GateGap.PLACEMENT_UNRESOLVED),
        "local_advance_authority": _supported(),
        "content_protection": _supported(),
        "selected_placement": _unavailable(GateGap.PLACEMENT_UNRESOLVED),
        "slot_ordinal_assignment": _unavailable(
            GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
        ),
        "source_lane_authority": (
            _supported()
            if source_lane_authority_available
            else _unavailable(GateGap.SOURCE_LANE_AUTHORITY_INVALID)
        ),
        "selected_only_envelope": _unavailable(
            GateGap.SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE
        ),
        "direct_use_budget": _unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE),
        "transform_sampling": _unavailable(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE),
    }


def reconstruct_photo_geometry(
    field: PhotoBoundaryMeasurementField,
    lanes: tuple[SourceLaneEvidence, ...],
    content_observations: tuple[ContentOccupancyObservationSet, ...],
    *,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
    resolved_slot_count: ResolvedSlotCount | None,
) -> PhotoGeometryDetectionResult:
    del lane_configuration
    if tuple(item.lane_id for item in content_observations) != tuple(
        lane.domain.lane_id for lane in lanes
    ):
        raise ValueError("content observations must cover source lanes")
    resolved = resolve_output_slots(configuration, lanes, resolved_slot_count)
    if resolved is None:
        transform = _empty_transform(field, layout, "output_slot_count_unavailable")
        facts = _unresolved_facts(
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE,
            source_lane_authority_available=bool(lanes),
        )
        facts["scan_canvas_authority"] = (
            _supported()
            if lanes
            else _unavailable(GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE)
        )
        facts["output_slot_count"] = _unavailable(
            GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE
        )
        return PhotoGeometryDetectionResult(
            None,
            (),
            _empty_source_placement_selection(),
            (),
            transform,
            (),
            facts,
        )

    prepared = tuple(
        _prepare_lane(
            field,
            lane,
            layout=layout,
            output_slot_count=count,
            measurement_slot_count=_lane_measurement_capacity(
                configuration,
                lanes,
                lane,
            ),
            configuration=configuration,
        )
        for lane, count in zip(
            lanes,
            resolved.lane_output_slot_counts,
            strict=True,
        )
    )
    source_directions = shared_source_direction_classes(
        tuple(item.proposal for item in prepared)
    )
    if len(source_directions) != 1:
        gap = (
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE
            if not source_directions
            else GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE
        )
        transform = _empty_transform(field, layout, gap.value)
        empty_reconstructions = tuple(
            _empty_reconstruction(
                item,
                content_observation_excess_count=(
                    observation.producer_excess_count
                ),
            )
            for item, observation in zip(
                prepared,
                content_observations,
                strict=True,
            )
        )
        facts = _unresolved_facts(gap)
        if any(
            item.producer_bounds.bound_exceeded
            for item in empty_reconstructions
        ):
            facts["producer_coverage"] = _contradicted(
                GateGap.PRODUCER_BOUND_EXCEEDED
            )
        return PhotoGeometryDetectionResult(
            resolved_output_slots=resolved,
            lane_reconstructions=empty_reconstructions,
            source_placement_selection=_empty_source_placement_selection(),
            output_slot_identities=_output_slot_identities(lanes, resolved),
            source_transform_assessment=transform,
            lane_transform_assessments=tuple(
                transform for _lane in empty_reconstructions
            ),
            assessment_facts=facts,
        )

    direction = source_directions[0]
    lane_directions = lane_directions_within_source_family(
        tuple(item.proposal for item in prepared),
        direction,
    )
    if len(lane_directions) != len(prepared):
        transform = _empty_transform(
            field,
            layout,
            GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE.value,
        )
        return PhotoGeometryDetectionResult(
            resolved_output_slots=resolved,
            lane_reconstructions=tuple(
                _empty_reconstruction(item) for item in prepared
            ),
            source_placement_selection=_empty_source_placement_selection(),
            output_slot_identities=_output_slot_identities(lanes, resolved),
            source_transform_assessment=transform,
            lane_transform_assessments=tuple(
                transform for _lane in prepared
            ),
            assessment_facts=_unresolved_facts(
                GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE
            ),
        )
    direction_resolution = SharedStripDirectionResolution(
        direction=direction,
        state=EvidenceState.SUPPORTED,
        named_gap=None,
    )
    transform = output_transform_assessment(
        direction_resolution,
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
    )
    lane_transforms = tuple(
        output_transform_assessment(
            SharedStripDirectionResolution(
                direction=lane_direction,
                state=EvidenceState.SUPPORTED,
                named_gap=None,
            ),
            layout=layout,
            source_width=field.source_extent.width,
            source_height=field.source_extent.height,
        )
        for lane_direction in lane_directions
    )
    materialization = materialize_source_placements(
        tuple(item.proposal for item in prepared),
        lane_directions,
    )
    placements_by_lane = materialization.placements_by_lane
    reconstructions: list[LaneFormatPlacementReconstruction] = []
    lane_candidate_envelopes: list[
        dict[str, tuple[SafeCropEnvelope, ...]]
    ] = []
    lane_placements_by_id: list[dict[str, CompleteFormatChain]] = []
    for (
        prepared_lane,
        placements,
        proposed_chain_count,
        refinement_query_count,
        refined_proposal,
        content_observation,
        lane_direction,
        lane_transform,
    ) in zip(
        prepared,
        placements_by_lane,
        materialization.proposed_complete_chain_counts_by_lane,
        materialization.refinement_query_counts_by_lane,
        materialization.lane_proposals,
        content_observations,
        lane_directions,
        lane_transforms,
        strict=True,
    ):
        candidate_envelopes: dict[str, tuple[SafeCropEnvelope, ...]] = {}
        materialized_chains: list[CompleteFormatChain] = []
        chain_records: list[CompleteChainRecord] = []
        sampling_invalid_count = 0
        local_advance_unresolved_count = 0
        if lane_transform.transform is not None:
            for placement in placements:
                if not placement_local_advance_authorized(placement):
                    local_advance_unresolved_count += 1
                    continue
                try:
                    envelopes = tuple(
                        safe_crop_envelope_from_placement(
                            placement,
                            lane=prepared_lane.lane,
                            lane_ordinal=ordinal,
                            layout=layout,
                            transform=lane_transform.transform,
                        )
                        for ordinal in range(1, placement.output_slot_count + 1)
                    )
                    record = complete_chain_record(
                        placement,
                        envelopes,
                        sequence_edges=prepared_lane.sequence_edges,
                        separator_bands=prepared_lane.separator_bands,
                        top_bottom_observations=(
                            refined_proposal.raw_top_bottom_observations
                        ),
                    )
                except ValueError:
                    sampling_invalid_count += 1
                    continue
                candidate_envelopes[placement.placement_id] = envelopes
                materialized_chains.append(placement)
                chain_records.append(record)
        ordered_records = tuple(
            sorted(
                chain_records,
                key=lambda item: (
                    -item.direct_observation_count,
                    -item.structural_pair_count,
                    len(reconstructions) + 1,
                    tuple(
                        value
                        for interval in item.boundary_intervals_px
                        for value in (
                            interval.minimum.hex(),
                            interval.maximum.hex(),
                        )
                    ),
                    tuple(map(str, item.direct_observation_ids)),
                    item.chain_id,
                ),
            )
        )
        placements_by_id = {
            item.placement_id: item for item in materialized_chains
        }
        ordered_placements = tuple(
            placements_by_id[item.placement_id] for item in ordered_records
        )
        selection = prepare_placement_clusters(
            ordered_records,
            placements_by_id,
            content_observation,
            layout=layout,
        )
        producer_bounds = _producer_bounds_receipt(
            prepared_lane,
            proposed_chain_count=proposed_chain_count,
            chains=ordered_records,
            sampling_invalid_count=sampling_invalid_count,
            content_observation_excess_count=(
                content_observation.producer_excess_count
            ),
        )
        lane_candidate_envelopes.append(candidate_envelopes)
        lane_placements_by_id.append(placements_by_id)
        reconstructions.append(
            LaneFormatPlacementReconstruction(
                lane_id=prepared_lane.lane.domain.lane_id,
                anchor_domain=prepared_lane.anchor_domain,
                measurement_sets=prepared_lane.measurement_sets,
                side_transition_regions=prepared_lane.side_regions,
                sequence_profile=refined_proposal.lane.sequence_profile,
                cross_profile=prepared_lane.cross_profile,
                sequence_edges=prepared_lane.sequence_edges,
                separator_bands=prepared_lane.separator_bands,
                raw_top_bottom_observations=(
                    refined_proposal.raw_top_bottom_observations
                ),
                cross_axis_proposals=tuple(
                    cross_proposal
                    for frame_spec in refined_proposal.frame_proposals
                    for cross_proposal in frame_spec.cross_proposals
                ),
                lane_gap_model=prepared_lane.lane_gap_model,
                direction_classes=(lane_direction,),
                materialized_chains=ordered_placements,
                placement_selection=selection,
                selected_placement=None,
                selected_chain_record=None,
                producer_bounds=producer_bounds,
                local_advance_unresolved_count=local_advance_unresolved_count,
                safe_crop_envelopes=(),
                direct_use_budget_assessments=(),
                work=_work_receipt(
                    prepared_lane,
                    ordered_placements,
                    refinement_query_count=refinement_query_count,
                    proposal=refined_proposal,
                ),
            )
        )
    resolved_lane_selections, source_selection = select_source_placement_clusters(
        tuple(item.placement_selection for item in reconstructions),
        tuple(lane_placements_by_id),
    )
    resolved_reconstructions: list[LaneFormatPlacementReconstruction] = []
    all_budgets: list[DirectUseBudgetAssessment] = []
    for (
        reconstruction,
        selection,
        placements_by_id,
        candidate_envelopes,
        lane_transform,
        refined_proposal,
    ) in zip(
        reconstructions,
        resolved_lane_selections,
        lane_placements_by_id,
        lane_candidate_envelopes,
        lane_transforms,
        materialization.lane_proposals,
        strict=True,
    ):
        selected = (
            None
            if selection.selected_placement_id is None
            else placements_by_id[selection.selected_placement_id]
        )
        if (
            selected is not None
            and source_selection.shared_scan_geometry is not None
        ):
            try:
                selected = rematerialize_complete_chain(
                    refined_proposal,
                    selected,
                    source_selection.shared_scan_geometry,
                )
                placements_by_id[selected.placement_id] = selected
                candidate_envelopes[selected.placement_id] = tuple(
                    safe_crop_envelope_from_placement(
                        selected,
                        lane=next(
                            item.lane
                            for item in prepared
                            if item.lane.domain.lane_id == selected.lane_id
                        ),
                        lane_ordinal=ordinal,
                        layout=layout,
                        transform=lane_transform.transform,
                    )
                    for ordinal in range(1, selected.output_slot_count + 1)
                )
            except ValueError:
                candidate_envelopes.pop(selected.placement_id, None)
        geometries = (
            ()
            if selected is None
            or lane_transform.transform is None
            or reconstruction.producer_bounds.bound_exceeded
            else candidate_envelopes.get(selected.placement_id, ())
        )
        selected_chain_record = (
            None
            if selected is None or not geometries
            else complete_chain_record(
                selected,
                geometries,
                sequence_edges=reconstruction.sequence_edges,
                separator_bands=reconstruction.separator_bands,
                top_bottom_observations=(
                    reconstruction.raw_top_bottom_observations
                ),
            )
        )
        budgets = tuple(
            direct_use_budget_assessment(
                selected,
                geometry,
                lane_transform.transform,
            )
            for geometry in geometries
            if selected is not None and lane_transform.transform is not None
        )
        all_budgets.extend(budgets)
        resolved_reconstructions.append(
            replace(
                reconstruction,
                materialized_chains=tuple(
                    selected
                    if selected is not None
                    and item.placement_id == selected.placement_id
                    else item
                    for item in reconstruction.materialized_chains
                ),
                placement_selection=selection,
                selected_placement=selected,
                selected_chain_record=selected_chain_record,
                lane_gap_model=(
                    reconstruction.lane_gap_model
                    if selected is None
                    else selected.sequence.lane_gap_model
                ),
                safe_crop_envelopes=geometries,
                direct_use_budget_assessments=budgets,
            )
        )
    reconstructions = resolved_reconstructions
    lane_chains_complete = bool(reconstructions) and all(
        item.materialized_chains for item in reconstructions
    )
    source_legal = bool(source_selection.combinations)
    complete = lane_chains_complete and source_legal
    selection_complete = complete and all(
        item.placement_selection.state == EvidenceState.SUPPORTED
        for item in reconstructions
    )
    producer_bounds_valid = all(
        not item.producer_bounds.bound_exceeded for item in reconstructions
    )
    output_geometry_complete = (
        selection_complete
        and producer_bounds_valid
        and sum(
            len(item.safe_crop_envelopes)
            for item in reconstructions
        )
        == resolved.output_slot_count
    )
    budget_state = (
        _contradicted(GateGap.DIRECT_USE_BUDGET_EXCEEDED)
        if any(item.state == EvidenceState.CONTRADICTED for item in all_budgets)
        else _supported()
        if (
            output_geometry_complete
            and len(all_budgets) == resolved.output_slot_count
            and all(item.state == EvidenceState.SUPPORTED for item in all_budgets)
        )
        else _unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE)
    )
    all_clusters_vetoed = any(
        item.placement_selection.clusters
        and all(
            assessment.vetoed
            for assessment in item.placement_selection.content_veto_assessments
        )
        for item in reconstructions
    )
    local_advance_unresolved = (
        not selection_complete
        and any(
            item.local_advance_unresolved_count > 0
            for item in reconstructions
        )
    )
    facts = {
        "scan_canvas_authority": _supported(),
        "output_slot_count": _supported(),
        "observation_completeness": (
            _supported()
            if producer_bounds_valid
            else _contradicted(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "source_scan_geometry": (
            _supported()
            if source_legal
            else _unavailable(GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE)
        ),
        "shared_strip_direction": _supported(),
        "complete_chain": (
            _supported()
            if complete
            else _unavailable(GateGap.COMPLETE_CHAIN_UNAVAILABLE)
        ),
        "producer_coverage": (
            _supported()
            if producer_bounds_valid
            else _contradicted(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "independent_evidence": (
            _supported()
            if selection_complete
            else _unavailable(
                GateGap.PLACEMENT_UNRESOLVED
                if source_legal
                else GateGap.COMPLETE_CHAIN_UNAVAILABLE
            )
        ),
        "local_advance_authority": (
            _unavailable(GateGap.LOCAL_ADVANCE_UNRESOLVED)
            if local_advance_unresolved
            else _supported()
        ),
        "content_protection": (
            _contradicted(GateGap.CONTENT_VETO_REJECTED)
            if all_clusters_vetoed
            else _supported()
        ),
        "selected_placement": (
            _supported()
            if selection_complete
            else _unavailable(
                GateGap.CONTENT_VETO_REJECTED
                if all_clusters_vetoed
                else GateGap.PLACEMENT_UNRESOLVED
                if source_legal
                else GateGap.COMPLETE_CHAIN_UNAVAILABLE
            )
        ),
        "slot_ordinal_assignment": (
            _supported()
            if lane_chains_complete
            else _unavailable(GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED)
        ),
        "source_lane_authority": _supported(),
        "selected_only_envelope": (
            _supported()
            if output_geometry_complete
            else _unavailable(
                GateGap.SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE
            )
        ),
        "direct_use_budget": budget_state,
        "transform_sampling": (
            _supported()
            if transform.state == EvidenceState.SUPPORTED
            and all(
                item.state == EvidenceState.SUPPORTED
                for item in lane_transforms
            )
            else _unavailable(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE)
        ),
    }
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved,
        lane_reconstructions=tuple(reconstructions),
        source_placement_selection=source_selection,
        output_slot_identities=_output_slot_identities(lanes, resolved),
        source_transform_assessment=transform,
        lane_transform_assessments=lane_transforms,
        assessment_facts=facts,
    )
