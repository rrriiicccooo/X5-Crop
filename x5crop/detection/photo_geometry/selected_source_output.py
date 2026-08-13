"""Resolve one source-level placement and build its selected-only outputs."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..gate_checks import GateGap
from ..output_geometry import OutputTransformAssessment
from .chain_signature import selected_chain_physical_signature
from .lane_preparation import PreparedLane
from .lane_reconstruction import LaneCandidateReconstructions
from .measurement_model import PhotoBoundaryMeasurementField
from .output import direct_use_budget_assessment, safe_crop_envelope_from_placement
from .output_model import DirectUseBudgetAssessment
from .reconstruction_model import LaneFormatPlacementReconstruction
from .reconstruction_receipts import empty_output_transform
from .source_selection import select_source_placement_clusters
from .source_selection_model import SourcePlacementSelection


@dataclass(frozen=True)
class SelectedSourceOutput:
    reconstructions: tuple[LaneFormatPlacementReconstruction, ...]
    selection: SourcePlacementSelection
    lane_transforms: tuple[OutputTransformAssessment, ...]
    budgets: tuple[DirectUseBudgetAssessment, ...]


def resolve_selected_source_output(
    field: PhotoBoundaryMeasurementField,
    prepared: tuple[PreparedLane, ...],
    candidates: LaneCandidateReconstructions,
    *,
    layout: str,
) -> SelectedSourceOutput:
    lane_selections, source_selection = select_source_placement_clusters(
        tuple(item.placement_selection for item in candidates.reconstructions),
        candidates.placements_by_id,
    )
    resolved_reconstructions: list[LaneFormatPlacementReconstruction] = []
    lane_transforms: list[OutputTransformAssessment] = []
    all_budgets: list[DirectUseBudgetAssessment] = []
    for (
        reconstruction,
        selection,
        placements_by_id,
        candidate_transforms,
    ) in zip(
        candidates.reconstructions,
        lane_selections,
        candidates.placements_by_id,
        candidates.candidate_transforms,
        strict=True,
    ):
        selected = (
            None
            if selection.selected_placement_id is None
            else placements_by_id[selection.selected_placement_id]
        )
        selected_signature = (
            None
            if selected is None
            else selected_chain_physical_signature(selected)
        )
        lane_transform = (
            empty_output_transform(
                field,
                layout,
                GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE.value,
            )
            if selected is None
            else candidate_transforms[selected.placement_id]
        )
        if (
            selected is not None
            and source_selection.shared_scan_geometry
            != selected.source_scan_geometry
        ):
            raise ValueError(
                "selection returned a chain without shared source W/H"
            )
        selected_lane = next(
            item.lane
            for item in prepared
            if item.lane.domain.lane_id == reconstruction.lane_id
        )
        reviewed_record = (
            None
            if selected is None
            else next(
                (
                    item
                    for item in reconstruction.placement_selection.chains
                    if item.placement_id == selected.placement_id
                ),
                None,
            )
        )
        if selected is not None and reviewed_record is None:
            raise ValueError("selected chain has no reviewed candidate record")
        try:
            geometries = (
                ()
                if selected is None
                or lane_transform.transform is None
                or reconstruction.producer_bounds.bound_exceeded
                else tuple(
                    safe_crop_envelope_from_placement(
                        selected,
                        lane=selected_lane,
                        lane_ordinal=ordinal,
                        layout=layout,
                        transform=lane_transform.transform,
                    )
                    for ordinal in range(
                        1,
                        selected.output_slot_count + 1,
                    )
                )
            )
            if geometries and reviewed_record is not None and tuple(
                item.mapped_output_box for item in geometries
            ) != reviewed_record.sampling_boxes:
                raise ValueError(
                    "selected envelope differs from candidate sampling"
                )
        except ValueError:
            geometries = ()
        selected_chain_record = (
            None
            if selected is None or not geometries
            else reviewed_record
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
        if (
            selected is not None
            and selected_chain_physical_signature(selected)
            != selected_signature
        ):
            raise ValueError("selected chain changed during output sampling")
        all_budgets.extend(budgets)
        lane_transforms.append(lane_transform)
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
    return SelectedSourceOutput(
        reconstructions=tuple(resolved_reconstructions),
        selection=source_selection,
        lane_transforms=tuple(lane_transforms),
        budgets=tuple(all_budgets),
    )
