"""Current photo-geometry reconstruction result contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState
from ...geometry.affine import AffineCoordinateTransform
from ..gate_checks import TypedAssessment
from ..output_geometry import OutputTransformAssessment
from .chain_record_model import CompleteChainRecord
from .chain_proposals import CrossAxisProposal
from .chains import CompleteFormatChain
from .measurement_model import PhotoBoundaryMeasurementSet
from .line_observations import PhotoBoundaryObservation, SideTransitionRegion
from .search_model import SequenceAnchorDiscoveryDomain
from .output_model import (
    DirectUseBudgetAssessment,
    OutputSlotIdentity,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SharedStripDirection,
)
from .observation_types import BasicAxisProfile, BoundaryEdgeObservation, SeparatorBandObservation
from .placement_clusters import LanePlacementSelection
from .producer_receipts import ChainProducerWorkReceipt, ProducerBoundsReceipt
from .lane_gap_model import LaneGapModel
from .source_selection_model import SourcePlacementSelection

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
    work: ChainProducerWorkReceipt | None

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
