"""Materialize and record every bounded placement for prepared source lanes."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from ..output_geometry import (
    OutputTransformAssessment,
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from .candidate_sampling import chain_sampling_geometry
from .chain_authority import placement_local_advance_authorized
from .chain_record_model import CompleteChainRecord
from .chain_records import complete_chain_record
from .chains import CompleteFormatChain, SourcePlacementMaterialization
from .content_topology import build_content_topology_index
from .early_physical_frontier import (
    content_assessed_physical_frontier,
    early_physical_frontier,
)
from .lane_preparation import PreparedLane
from .measurement_model import PhotoBoundaryMeasurementField
from .observation_spatial_index import build_chain_observation_spatial_index
from .placement_clusters import prepare_placement_clusters
from .reconstruction_model import LaneFormatPlacementReconstruction
from .reconstruction_receipts import producer_bounds_receipt, work_receipt


@dataclass(frozen=True)
class LaneCandidateReconstructions:
    reconstructions: tuple[LaneFormatPlacementReconstruction, ...]
    candidate_transforms: tuple[dict[str, OutputTransformAssessment], ...]
    placements_by_id: tuple[dict[str, CompleteFormatChain], ...]


def build_lane_candidate_reconstructions(
    field: PhotoBoundaryMeasurementField,
    prepared: tuple[PreparedLane, ...],
    materialization: SourcePlacementMaterialization,
    content_observations: tuple[ContentOccupancyObservationSet, ...],
    *,
    layout: str,
    development_detail: bool,
) -> LaneCandidateReconstructions:
    reconstructions: list[LaneFormatPlacementReconstruction] = []
    lane_candidate_transforms: list[dict[str, OutputTransformAssessment]] = []
    lane_placements_by_id: list[dict[str, CompleteFormatChain]] = []
    for (
        prepared_lane,
        placements,
        proposed_chain_count,
        refined_proposal,
        content_observation,
    ) in zip(
        prepared,
        materialization.placements_by_lane,
        materialization.proposed_complete_chain_counts_by_lane,
        materialization.lane_proposals,
        content_observations,
        strict=True,
    ):
        candidate_transforms: dict[str, OutputTransformAssessment] = {}
        materialized_chains: list[CompleteFormatChain] = []
        chain_records: list[CompleteChainRecord] = []
        sampling_invalid_count = 0
        local_advance_unresolved_count = 0
        top_bottom_observations = tuple(
            sorted(
                {
                    str(observation.observation_id): observation
                    for observation in (
                        *refined_proposal.raw_top_bottom_observations,
                        *(
                            evidence.observation
                            for placement in placements
                            for evidence in placement.cross.evidence
                        ),
                    )
                }.values(),
                key=lambda item: str(item.observation_id),
            )
        )
        observation_index = build_chain_observation_spatial_index(
            refined_proposal.lane.sequence_edges,
            refined_proposal.lane.separator_bands,
            top_bottom_observations,
        )
        physical_frontier = early_physical_frontier(
            placements,
            observations=observation_index,
            include_observation_facts=development_detail,
        )
        content_index = build_content_topology_index(
            content_observation,
            layout=layout,
        )
        early_frontier = content_assessed_physical_frontier(
            physical_frontier,
            content=content_index,
        )
        content_assessments_by_placement = {
            item.placement.placement_id: item.content
            for item in early_frontier
            if item.content is not None
        }
        accounting_by_placement = {
            item.placement.placement_id: item.accounting
            for item in early_frontier
        }
        for early in early_frontier:
            placement = early.placement
            lane_transform = output_transform_assessment(
                SharedStripDirectionResolution(
                    direction=placement.lane_geometry.direction,
                    state=EvidenceState.SUPPORTED,
                    named_gap=None,
                ),
                layout=layout,
                source_width=field.source_extent.width,
                source_height=field.source_extent.height,
            )
            candidate_transforms[placement.placement_id] = lane_transform
            if lane_transform.transform is None:
                continue
            if not placement_local_advance_authorized(placement):
                local_advance_unresolved_count += 1
                continue
            try:
                sampling = chain_sampling_geometry(
                    placement,
                    lane=prepared_lane.lane,
                    layout=layout,
                    transform=lane_transform.transform,
                )
                record = complete_chain_record(
                    placement,
                    sampling,
                    observations=observation_index,
                    accounting=accounting_by_placement[
                        placement.placement_id
                    ],
                    development_detail=development_detail,
                )
            except ValueError:
                sampling_invalid_count += 1
                continue
            materialized_chains.append(placement)
            chain_records.append(record)
        ordered_records = tuple(
            sorted(
                chain_records,
                key=lambda item: (
                    -int(item.cross_axis_pair_supported),
                    -item.separator_band_count,
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
            content_assessments_by_placement=(
                content_assessments_by_placement
            ),
        )
        producer_bounds = producer_bounds_receipt(
            prepared_lane,
            proposed_chain_count=proposed_chain_count,
            chains=ordered_records,
            physical_dominated_count=(
                len(placements) - len(early_frontier)
            ),
            sampling_invalid_count=sampling_invalid_count,
        )
        lane_candidate_transforms.append(candidate_transforms)
        lane_placements_by_id.append(placements_by_id)
        reconstructions.append(
            LaneFormatPlacementReconstruction(
                lane_id=prepared_lane.lane.domain.lane_id,
                anchor_domain=prepared_lane.anchor_domain,
                measurement_sets=prepared_lane.measurement_sets,
                side_transition_regions=prepared_lane.side_regions,
                sequence_profile=refined_proposal.lane.sequence_profile,
                cross_profile=prepared_lane.cross_profile,
                sequence_edges=refined_proposal.lane.sequence_edges,
                separator_bands=refined_proposal.lane.separator_bands,
                raw_top_bottom_observations=top_bottom_observations,
                cross_axis_proposals=refined_proposal.cross_proposals,
                lane_gap_model=prepared_lane.lane_gap_model,
                direction_classes=refined_proposal.direction_classes,
                materialized_chains=ordered_placements,
                placement_selection=selection,
                selected_placement=None,
                selected_chain_record=None,
                producer_bounds=producer_bounds,
                local_advance_unresolved_count=(
                    local_advance_unresolved_count
                ),
                safe_crop_envelopes=(),
                direct_use_budget_assessments=(),
                work=(
                    work_receipt(
                        prepared_lane,
                        ordered_placements,
                        proposal=refined_proposal,
                    )
                    if development_detail
                    else None
                ),
            )
        )
    return LaneCandidateReconstructions(
        reconstructions=tuple(reconstructions),
        candidate_transforms=tuple(lane_candidate_transforms),
        placements_by_id=tuple(lane_placements_by_id),
    )
