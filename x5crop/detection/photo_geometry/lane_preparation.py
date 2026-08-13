"""Registered measurement and bounded proposal preparation for one lane."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...configuration.model import (
    DetectionConfiguration,
    HolderLayoutAuthority,
    ResolvedSlotCount,
)
from ...domain import FiniteInterval
from ..source_core import SourceLaneEvidence
from .content_boundary_queries import separator_core_content_contradictions
from .content_topology import build_content_topology_index
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from .axis_layout import axis_interval, coordinate_count, source_axes
from .chain_proposals import LaneObservationInput, LanePhysicalProposals
from .corridors import (
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    frame_physical_pixel_intervals,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .lane_proposals import build_lane_physical_proposals
from .registered_measurement import measure_registered_queries
from .transition_tracking import track_side_transition_regions
from .model import (
    BoundaryAxis,
)
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .line_observations import SideTransitionRegion
from .search_model import SequenceAnchorDiscoveryDomain
from .output_model import ResolvedOutputSlots
from .observation_types import BasicAxisProfile, BoundaryEdgeObservation, SeparatorBandObservation
from .observations import build_sequence_observations
from .profile_adapters import (
    cross_profile_from_regions,
    sequence_profile_from_regions,
)
from .sequence_edge_families import merge_sequence_edge_families
from .producer_receipts import CorridorEdgeFamilyCount
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry

@dataclass(frozen=True)
class PreparedLane:
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
    content_contradicted_separator_count: int
    proposal: LanePhysicalProposals
    lane_gap_model: LaneGapModel
    corridor_edge_family_counts: tuple[CorridorEdgeFamilyCount, ...]


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
        direct_separator_gaps=(),
    )


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane: SourceLaneEvidence,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return configuration.physical_spec.holder_full_count(profile.profile_id) or 0


def lane_measurement_capacity(
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


def _physical_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm,
    minimum_independent_support_regions: int = 2,
) -> tuple[tuple[SideTransitionRegion, ...], tuple[CorridorEdgeFamilyCount, ...]]:
    retained: dict[str, SideTransitionRegion] = {}
    counts: list[CorridorEdgeFamilyCount] = []
    for measurement_set in measurement_sets:
        proposed = track_side_transition_regions(
            (measurement_set,),
            reference_trace_px=reference_trace_px,
            boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
            minimum_independent_support_regions=(
                minimum_independent_support_regions
            ),
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
        counts.append(
            CorridorEdgeFamilyCount(
                corridor_id=measurement_set.query.query_id,
                proposed_count=len(ordered),
                materialized_count=len(ordered),
            )
        )
        retained.update({item.region_id: item for item in ordered})
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
    )


def prepare_lane(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    output_slot_count: int,
    measurement_slot_count: int,
    holder_layout_authority: HolderLayoutAuthority,
    configuration: DetectionConfiguration,
    content_observation: ContentOccupancyObservationSet,
) -> PreparedLane:
    width_axis, height_axis = source_axes(layout)
    authority = source_lane_box(lane, layout)
    width_authority = axis_interval(authority, width_axis)
    height_authority = axis_interval(authority, height_axis)
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
    side_regions, side_counts = _physical_transition_regions(
        measurement_sets[2:],
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    top_regions, top_counts = _physical_transition_regions(
        (measurement_sets[0],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
        minimum_independent_support_regions=1,
    )
    bottom_regions, bottom_counts = _physical_transition_regions(
        (measurement_sets[1],),
        reference_trace_px=width_authority.center,
        boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
        minimum_independent_support_regions=1,
    )
    sequence_profile = sequence_profile_from_regions(
        side_regions,
        coordinate_count=coordinate_count(width_authority),
        transition_by_id=transition_by_id,
    )
    sequence_profile = merge_sequence_edge_families(
        sequence_profile,
        transition_by_id,
        reference_trace_px=height_authority.center,
        boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
    )
    cross_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=coordinate_count(height_authority),
        transition_by_id=transition_by_id,
    )
    sequence_edges, separator_bands = build_sequence_observations(
        sequence_profile,
        transition_by_id,
        field,
        width_axis,
        scales.width_axis_px_per_mm,
    )
    edge_by_observation_id = {
        edge.observation_id: edge for edge in sequence_edges
    }
    source_geometry = SourceScanGeometry.create(
        configuration.physical_spec.frame,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm,
    )
    minimum_height = (
        source_geometry.height_state.extent_projection_px().minimum
    )
    cross_core = FiniteInterval(
        height_authority.center - minimum_height / 2.0,
        height_authority.center + minimum_height / 2.0,
    )
    content_index = build_content_topology_index(
        content_observation,
        layout=layout,
    )
    content_contradicted_separator_ids = {
        band.observation_id
        for band in separator_bands
        if (
            left := edge_by_observation_id.get(
                band.left_edge_observation_id
            )
        )
        is not None
        and (
            right := edge_by_observation_id.get(
                band.right_edge_observation_id
            )
        )
        is not None
        and right.coordinate_interval_px.minimum
        > left.coordinate_interval_px.maximum
        and separator_core_content_contradictions(
            content_index,
            sequence_core=FiniteInterval(
                left.coordinate_interval_px.maximum,
                right.coordinate_interval_px.minimum,
            ),
            cross_core=cross_core,
        )
    }
    lane_input = LaneObservationInput(
        lane_id=lane.domain.lane_id,
        output_slot_count=output_slot_count,
        measurement_slot_count=measurement_slot_count,
        holder_layout_authority=holder_layout_authority,
        holder_extent_tolerance_ratio=(
            configuration.scan_canvas.physical_extent_tolerance_ratio
        ),
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
        replace(
            lane_input,
            separator_bands=tuple(
                band
                for band in separator_bands
                if band.observation_id
                not in content_contradicted_separator_ids
            ),
        ),
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
    return PreparedLane(
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
        content_contradicted_separator_count=len(
            content_contradicted_separator_ids
        ),
        proposal=proposal,
        lane_gap_model=lane_gap_model,
        corridor_edge_family_counts=(*top_counts, *bottom_counts, *side_counts),
    )
