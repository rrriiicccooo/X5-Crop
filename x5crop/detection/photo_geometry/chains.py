"""Materialized placement and complete fixed-format chain domain."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...formats import FramePhysicalSpec
from .line_observations import PhotoBoundaryObservation
from .model import BoundaryRole
from .observation_types import (
    OrdinalBoundaryRole,
    SeparatorBandObservation,
)
from .output_model import FrameBoundaryGeometry, SharedStripDirection
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry

if TYPE_CHECKING:
    from .chain_proposals import (
        CrossAxisProposal,
        LanePhysicalProposals,
        SequenceChainProposal,
    )
    from .sequence_models import LocalAdvanceRelation, LongAxisFillAuthority


@dataclass(frozen=True)
class SourcePlacementMaterialization:
    placements_by_lane: tuple[tuple[CompleteFormatChain, ...], ...]
    proposed_complete_chain_counts_by_lane: tuple[int, ...]
    lane_proposals: tuple[LanePhysicalProposals, ...]

    def __post_init__(self) -> None:
        if (
            len(self.placements_by_lane)
            != len(self.proposed_complete_chain_counts_by_lane)
            or len(self.placements_by_lane) != len(self.lane_proposals)
            or any(
                proposed < len(materialized)
                for proposed, materialized in zip(
                    self.proposed_complete_chain_counts_by_lane,
                    self.placements_by_lane,
                    strict=True,
                )
            )
        ):
            raise ValueError("source placement materialization is invalid")


@dataclass(frozen=True)
class BoundRoleEvidence:
    role: OrdinalBoundaryRole
    run_id: str
    observation_id: ObservationId | None
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    safety_position_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    fit_direction_interval_degrees: FiniteInterval
    full_direction_interval_degrees: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or (
                self.observation_id is not None
                and self.observation_id not in self.transition_ids
                and not str(self.observation_id).startswith("boundary-edge:")
            )
            or not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-8,
            )
            or not self.safety_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.transition_ids
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_direction_interval_degrees.contains(
                self.fit_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("bound role evidence is invalid")


@dataclass(frozen=True)
class BoundSeparatorBand:
    observation: SeparatorBandObservation
    relation_ordinal: int
    left_role_index: int
    right_role_index: int

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or self.left_role_index <= 0
            or self.right_role_index != self.left_role_index + 1
        ):
            raise ValueError("bound separator band is invalid")


@dataclass(frozen=True)
class SequencePlacement:
    placement_id: str
    chain_proposal_id: str
    sequence_group_ids: tuple[str, ...]
    source_scan_geometry_id: str
    roles: tuple[OrdinalBoundaryRole, ...]
    phase_fit_interval_px: FiniteInterval
    phase_full_interval_px: FiniteInterval
    lane_gap_model: LaneGapModel
    local_advance_relations: tuple[LocalAdvanceRelation, ...]
    canonical_positions_px: tuple[float, ...]
    fit_positions_px: tuple[FiniteInterval, ...]
    full_positions_px: tuple[FiniteInterval, ...]
    role_fit_direction_intervals_degrees: tuple[FiniteInterval, ...]
    role_full_direction_intervals_degrees: tuple[FiniteInterval, ...]
    observations: tuple[BoundRoleEvidence, ...]
    separator_bands: tuple[BoundSeparatorBand, ...]
    exclusion_authorized: bool
    long_axis_fill_authority: LongAxisFillAuthority

    def __post_init__(self) -> None:
        role_count = len(self.roles)
        observations_by_role_and_id = {
            (item.role.role_index, item.observation_id)
            for item in self.observations
            if item.observation_id is not None
        }
        bound_band_keys = tuple(
            (str(item.observation.observation_id), item.relation_ordinal)
            for item in self.separator_bands
        )
        separator_roles_are_bound = all(
            (
                band.left_role_index,
                band.observation.left_edge_observation_id,
            )
            in observations_by_role_and_id
            and (
                band.right_role_index,
                band.observation.right_edge_observation_id,
            )
            in observations_by_role_and_id
            for band in self.separator_bands
        )
        if (
            not self.placement_id
            or not self.chain_proposal_id
            or not self.sequence_group_ids
            or not self.source_scan_geometry_id
            or role_count <= 0
            or len(self.canonical_positions_px) != role_count
            or len(self.fit_positions_px) != role_count
            or len(self.full_positions_px) != role_count
            or len(self.role_fit_direction_intervals_degrees) != role_count
            or len(self.role_full_direction_intervals_degrees) != role_count
            or any(
                not full.contains(fit.minimum, epsilon=1.0e-9)
                or not full.contains(fit.maximum, epsilon=1.0e-9)
                for fit, full in zip(
                    self.role_fit_direction_intervals_degrees,
                    self.role_full_direction_intervals_degrees,
                    strict=True,
                )
            )
            or len(self.local_advance_relations)
            != max(0, role_count // 2 - 1)
            or any(
                band.relation_ordinal >= role_count // 2
                for band in self.separator_bands
            )
            or len(set(bound_band_keys)) != len(bound_band_keys)
            or len(
                {item.relation_ordinal for item in self.separator_bands}
            )
            != len(self.separator_bands)
            or not separator_roles_are_bound
            or any(
                not fit.contains(canonical, epsilon=1.0e-8)
                or not full.contains(fit.minimum, epsilon=1.0e-8)
                or not full.contains(fit.maximum, epsilon=1.0e-8)
                for canonical, fit, full in zip(
                    self.canonical_positions_px,
                    self.fit_positions_px,
                    self.full_positions_px,
                    strict=True,
                )
            )
            or (
                self.long_axis_fill_authority.state
                == EvidenceState.SUPPORTED
                and not self.long_axis_fill_authority
                .centered_midpoint_authority_px.contains(
                    (
                        self.canonical_positions_px[0]
                        + self.canonical_positions_px[-1]
                    )
                    / 2.0,
                    epsilon=1.0e-8,
                )
            )
        ):
            raise ValueError("sequence placement is invalid")

@dataclass(frozen=True)
class CrossRoleEvidence:
    role: BoundaryRole
    run_id: str
    observation: PhotoBoundaryObservation
    canonical_position_at_lane_reference_px: float
    fit_position_at_lane_reference_px: FiniteInterval
    full_position_at_lane_reference_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            or self.observation.role != self.role
            or not self.run_id
            or not self.fit_position_at_lane_reference_px.contains(
                self.canonical_position_at_lane_reference_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_at_lane_reference_px.contains(
                self.fit_position_at_lane_reference_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_at_lane_reference_px.contains(
                self.fit_position_at_lane_reference_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("cross role evidence is invalid")


@dataclass(frozen=True)
class CrossPlacement:
    placement_id: str
    cross_proposal_id: str
    source_scan_geometry_id: str
    lane_reference_trace_px: float
    frame_reference_traces_px: tuple[float, ...]
    top_canonical_positions_px: tuple[float, ...]
    bottom_canonical_positions_px: tuple[float, ...]
    top_fit_positions_px: tuple[FiniteInterval, ...]
    bottom_fit_positions_px: tuple[FiniteInterval, ...]
    top_full_positions_px: tuple[FiniteInterval, ...]
    bottom_full_positions_px: tuple[FiniteInterval, ...]
    evidence: tuple[CrossRoleEvidence, ...]
    direct_height_span_validated: bool

    def __post_init__(self) -> None:
        count = len(self.frame_reference_traces_px)
        values = (
            self.top_canonical_positions_px,
            self.bottom_canonical_positions_px,
            self.top_fit_positions_px,
            self.bottom_fit_positions_px,
            self.top_full_positions_px,
            self.bottom_full_positions_px,
        )
        if (
            not self.placement_id
            or not self.cross_proposal_id
            or not self.source_scan_geometry_id
            or count <= 0
            or any(len(value) != count for value in values)
            or not self.evidence
            or (
                self.direct_height_span_validated
                and {item.role for item in self.evidence}
                != {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
            or any(
                top >= bottom
                for top, bottom in zip(
                    self.top_canonical_positions_px,
                    self.bottom_canonical_positions_px,
                    strict=True,
                )
            )
            or any(
                not top_fit.contains(top, epsilon=1.0e-8)
                or not bottom_fit.contains(bottom, epsilon=1.0e-8)
                or not top_full.contains(top_fit.minimum, epsilon=1.0e-8)
                or not top_full.contains(top_fit.maximum, epsilon=1.0e-8)
                or not bottom_full.contains(bottom_fit.minimum, epsilon=1.0e-8)
                or not bottom_full.contains(bottom_fit.maximum, epsilon=1.0e-8)
                for top, bottom, top_fit, bottom_fit, top_full, bottom_full in zip(
                    self.top_canonical_positions_px,
                    self.bottom_canonical_positions_px,
                    self.top_fit_positions_px,
                    self.bottom_fit_positions_px,
                    self.top_full_positions_px,
                    self.bottom_full_positions_px,
                    strict=True,
                )
            )
        ):
            raise ValueError("cross placement is invalid")

def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(points, points[1:] + points[:1], strict=True)
    )


@dataclass(frozen=True)
class FixedFormatFrame:
    placement_geometry_id: str
    lane_id: str
    lane_ordinal: int
    top: FrameBoundaryGeometry
    bottom: FrameBoundaryGeometry
    start: FrameBoundaryGeometry
    end: FrameBoundaryGeometry
    canonical_source_polygon: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if (
            not self.placement_geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or tuple(
                item.role
                for item in (self.top, self.bottom, self.start, self.end)
            )
            != (
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
                BoundaryRole.START,
                BoundaryRole.END,
            )
            or len(self.canonical_source_polygon) != 4
            or abs(_polygon_area(self.canonical_source_polygon)) <= 1.0e-9
        ):
            raise ValueError("fixed format frame is invalid")


@dataclass(frozen=True)
class FixedFormatFrameSet:
    fixed_frame_set_id: str
    sequence_placement_id: str
    cross_placement_id: str
    frames: tuple[FixedFormatFrame, ...]

    def __post_init__(self) -> None:
        if (
            not self.fixed_frame_set_id
            or not self.sequence_placement_id
            or not self.cross_placement_id
            or not self.frames
            or tuple(frame.lane_ordinal for frame in self.frames)
            != tuple(range(1, len(self.frames) + 1))
        ):
            raise ValueError("fixed format frame set is invalid")


@dataclass(frozen=True)
class LaneGeometry:
    lane_geometry_id: str
    lane_id: str
    direction: SharedStripDirection
    nominal_centerline_px: float
    centerline_intervals_px: tuple[FiniteInterval, ...]
    sequence_phase_interval_px: FiniteInterval
    gap_model: LaneGapModel
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.lane_geometry_id
            or not self.lane_id
            or not math.isfinite(self.nominal_centerline_px)
            or not self.centerline_intervals_px
            or self.gap_model.lane_id != self.lane_id
        ):
            raise ValueError("lane geometry is invalid")


@dataclass(frozen=True)
class CompleteFormatChain:
    placement_id: str
    lane_id: str
    frame_spec: FramePhysicalSpec
    output_slot_count: int
    source_scan_geometry: SourceScanGeometry
    chain_proposal: SequenceChainProposal
    cross_proposal: CrossAxisProposal
    lane_geometry: LaneGeometry
    sequence: SequencePlacement
    cross: CrossPlacement
    fixed_frames: FixedFormatFrameSet

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.lane_id
            or self.output_slot_count <= 0
            or self.lane_geometry.lane_id != self.lane_id
            or self.chain_proposal.chain_proposal_id
            != self.sequence.chain_proposal_id
            or self.cross_proposal.cross_proposal_id
            != self.cross.cross_proposal_id
            or self.sequence.source_scan_geometry_id
            != self.source_scan_geometry.geometry_id
            or self.cross.source_scan_geometry_id
            != self.source_scan_geometry.geometry_id
            or self.fixed_frames.sequence_placement_id
            != self.sequence.placement_id
            or self.fixed_frames.cross_placement_id
            != self.cross.placement_id
            or len(self.fixed_frames.frames) != self.output_slot_count
            or self.source_scan_geometry.frame_spec != self.frame_spec
            or self.sequence.lane_gap_model != self.lane_geometry.gap_model
        ):
            raise ValueError("complete format chain is invalid")
