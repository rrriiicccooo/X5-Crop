"""Current-only complete physical-chain domain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import FramePhysicalSpec
from .model import (
    BoundaryAxis,
    BoundaryRole,
    FrameBoundaryGeometry,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    SharedStripDirection,
)
from .source_geometry import LaneGapModel, SourceScanGeometry
from .observations import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    SequenceGroupingWork,
    SequenceRoleProposal,
    ProfileRun,
    SeparatorBandObservation,
    SequenceHypothesisGroup,
    OrdinalBoundaryRole,
)


class LocalAdvanceKind(str, Enum):
    NOMINAL = "nominal"
    OBSERVED_UNCLASSIFIED = "observed_unclassified"
    WIDE = "wide"
    NARROW = "narrow"
    CONTACT = "contact"
    OVERLAP = "overlap"


@dataclass(frozen=True)
class LocalAdvanceRelation:
    relation_ordinal: int
    kind: LocalAdvanceKind
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not self.delta_interval_px.contains(
                self.canonical_delta_px,
                epsilon=1.0e-9,
            )
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or (
                self.kind == LocalAdvanceKind.NOMINAL
                and (
                    self.delta_interval_px != FiniteInterval.exact(0.0)
                    or self.canonical_delta_px != 0.0
                )
            )
            or (
                self.kind != LocalAdvanceKind.NOMINAL
                and not self.observation_ids
            )
        ):
            raise ValueError("local advance relation is invalid")


@dataclass(frozen=True)
class SequenceChainProposal:
    """One bounded complete sequence interpretation with local advances."""

    chain_proposal_id: str
    sequence_group_ids: tuple[str, ...]
    base_phase_interval_px: FiniteInterval
    role_proposals: tuple[SequenceRoleProposal, ...]
    local_advance_proposals: tuple[SequenceRoleProposal, ...]
    local_advance_relations: tuple[LocalAdvanceRelation, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        if (
            not self.chain_proposal_id
            or not self.sequence_group_ids
            or not self.role_proposals
            or len({item.proposal_id for item in self.role_proposals}) != len(self.role_proposals)
            or len(
                {item.proposal_id for item in self.local_advance_proposals}
            )
            != len(self.local_advance_proposals)
            or not {
                item.proposal_id for item in self.role_proposals
            }.issubset(
                item.proposal_id for item in self.local_advance_proposals
            )
            or tuple(
                item.relation_ordinal for item in self.local_advance_relations
            )
            != tuple(range(1, len(self.local_advance_relations) + 1))
        ):
            raise ValueError("sequence chain proposal is invalid")


@dataclass(frozen=True)
class RegisteredSequenceRoleQuery:
    """One ordinal role registered before direction-aware evidence binding."""

    query_id: str
    chain_proposal_id: str
    role: OrdinalBoundaryRole
    target_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if not self.query_id or not self.chain_proposal_id:
            raise ValueError("registered sequence role query requires identities")


@dataclass(frozen=True)
class ChainProducerWorkReceipt:
    measurement_query_count: int
    pixel_query_count: int
    basic_profile_coordinate_count: int
    basic_profile_run_count: int
    role_proposal_count: int
    sequence_group_count: int
    ordinal_role_lookup_count: int
    ordinal_role_match_count: int
    local_relation_evaluation_count: int
    refinement_query_count: int
    materialized_frame_geometry_count: int
    shared_measurement_reuse_count: int
    domain_pixels: int
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.__dict__.values()):
            raise ValueError("chain-producer work receipt cannot be negative")

    def validate_bounds(
        self,
        *,
        ordered_role_count: int,
        slot_count: int,
        registered_refinement_query_count: int,
    ) -> None:
        if (
            ordered_role_count <= 0
            or slot_count <= 0
            or registered_refinement_query_count < 0
        ):
            raise ValueError("chain-producer work bound requires positive shape")
        if (
            self.ordinal_role_lookup_count
            > self.sequence_group_count * ordered_role_count
            or self.ordinal_role_match_count > self.role_proposal_count
            or self.refinement_query_count > registered_refinement_query_count
            or self.local_relation_evaluation_count
            > self.sequence_group_count * max(0, slot_count - 1)
        ):
            raise ValueError("chain-producer work exceeded its structural bound")


@dataclass(frozen=True)
class CrossAxisProposal:
    cross_proposal_id: str
    frame_spec_id: str
    origin_interval_px: FiniteInterval
    observed_runs: tuple[ProfileRun, ...]
    raw_observations: tuple[PhotoBoundaryObservation, ...]

    def __post_init__(self) -> None:
        run_roles = tuple(run.role_hint for run in self.observed_runs)
        observation_roles = tuple(
            observation.role for observation in self.raw_observations
        )
        if (
            not self.cross_proposal_id
            or not self.frame_spec_id
            or not 1 <= len(self.observed_runs) <= 2
            or len(self.raw_observations) != len(self.observed_runs)
            or run_roles != observation_roles
            or tuple(
                sorted(
                    run_roles,
                    key=lambda role: (
                        0 if role == BoundaryRole.TOP else 1
                    ),
                )
            )
            != run_roles
            or len(set(run_roles)) != len(run_roles)
            or any(
                role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
                for role in run_roles
            )
            or any(
                set(run.transition_ids) != set(observation.transition_ids)
                for run, observation in zip(
                    self.observed_runs,
                    self.raw_observations,
                    strict=True,
                )
            )
        ):
            raise ValueError("cross-axis proposal is invalid")


@dataclass(frozen=True)
class LaneObservationInput:
    lane_id: str
    output_slot_count: int
    measurement_slot_count: int
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    width_scale_px_per_mm: PositiveInterval
    height_scale_px_per_mm: PositiveInterval
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    sequence_edges: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    sequence_measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    top_measurement_set: PhotoBoundaryMeasurementSet
    bottom_measurement_set: PhotoBoundaryMeasurementSet
    transition_by_id: dict[str, PhotoBoundaryTransition]

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.output_slot_count <= 0
            or self.measurement_slot_count < self.output_slot_count
            or self.width_axis == self.height_axis
            or self.sequence_profile.axis_name != "sequence"
            or self.cross_profile.axis_name != "cross"
            or any(
                edge.run_id not in {run.run_id for run in self.sequence_profile.runs}
                for edge in self.sequence_edges
            )
            or any(
                item.query.boundary_axis != self.width_axis
                for item in self.sequence_measurement_sets
            )
        ):
            raise ValueError("lane observation input is invalid")


@dataclass(frozen=True)
class FrameChainProposals:
    frame_spec: FramePhysicalSpec
    initial_source_scan_geometry: SourceScanGeometry
    roles: tuple[OrdinalBoundaryRole, ...]
    role_proposals: tuple[SequenceRoleProposal, ...]
    sequence_groups: tuple[SequenceHypothesisGroup, ...]
    registered_sequence_role_queries: tuple[RegisteredSequenceRoleQuery, ...]
    cross_proposals: tuple[CrossAxisProposal, ...]
    grouping_work: SequenceGroupingWork

    def __post_init__(self) -> None:
        if (
            self.initial_source_scan_geometry.frame_spec != self.frame_spec
            or not self.roles
            or not self.role_proposals
            or not self.sequence_groups
            or len(
                {
                    item.query_id
                    for item in self.registered_sequence_role_queries
                }
            )
            != len(self.registered_sequence_role_queries)
        ):
            raise ValueError("frame chain proposals are invalid")


@dataclass(frozen=True)
class LanePhysicalProposals:
    lane: LaneObservationInput
    frame_proposals: tuple[FrameChainProposals, ...]
    raw_top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    direction_classes: tuple[SharedStripDirection, ...]

    def __post_init__(self) -> None:
        if any(
            proposal.frame_spec.frame_spec_id
            != proposal.initial_source_scan_geometry.frame_spec.frame_spec_id
            for proposal in self.frame_proposals
        ):
            raise ValueError("lane proposal frame identity is invalid")


@dataclass(frozen=True)
class SourcePlacementMaterialization:
    placements_by_lane: tuple[tuple[CompleteFormatChain, ...], ...]
    proposed_complete_chain_counts_by_lane: tuple[int, ...]
    refinement_query_counts_by_lane: tuple[int, ...]
    lane_proposals: tuple[LanePhysicalProposals, ...]

    def __post_init__(self) -> None:
        if (
            len(self.placements_by_lane)
            != len(self.refinement_query_counts_by_lane)
            or len(self.placements_by_lane)
            != len(self.proposed_complete_chain_counts_by_lane)
            or len(self.placements_by_lane) != len(self.lane_proposals)
            or any(value < 0 for value in self.refinement_query_counts_by_lane)
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
    transition_ids: tuple[ObservationId, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    background_preference: float

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
            or not self.transition_ids
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not 0.0 <= self.background_preference <= 1.0
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
    sequence_edge_direction_intervals_degrees: tuple[FiniteInterval, ...]
    safety_support_transition_ids: tuple[tuple[ObservationId, ...], ...]
    observations: tuple[BoundRoleEvidence, ...]
    separator_bands: tuple[BoundSeparatorBand, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        role_count = len(self.roles)
        if (
            not self.placement_id
            or not self.chain_proposal_id
            or not self.sequence_group_ids
            or not self.source_scan_geometry_id
            or role_count <= 0
            or len(self.canonical_positions_px) != role_count
            or len(self.fit_positions_px) != role_count
            or len(self.full_positions_px) != role_count
            or len(
                self.sequence_edge_direction_intervals_degrees
            )
            != role_count
            or len(self.safety_support_transition_ids) != role_count
            or any(
                len(set(values)) != len(values)
                for values in self.safety_support_transition_ids
            )
            or len(self.local_advance_relations) != max(0, role_count // 2 - 1)
            or any(
                band.relation_ordinal >= role_count // 2
                for band in self.separator_bands
            )
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
        ):
            raise ValueError("sequence placement is invalid")

    @property
    def observed_role_count(self) -> int:
        return len({item.role.role_index for item in self.observations})

    @property
    def observed_opposite_pair_count(self) -> int:
        roles_by_ordinal: dict[int, set[BoundaryRole]] = {}
        for observation in self.observations:
            roles_by_ordinal.setdefault(
                observation.role.lane_ordinal,
                set(),
            ).add(observation.role.role)
        return sum(
            roles == {BoundaryRole.START, BoundaryRole.END}
            for roles in roles_by_ordinal.values()
        )

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

    @property
    def observed_role_count(self) -> int:
        return len({item.role for item in self.evidence})

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
                item.role for item in (self.top, self.bottom, self.start, self.end)
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
    centerline_intervals_px: tuple[FiniteInterval, ...]
    sequence_phase_interval_px: FiniteInterval
    gap_model: LaneGapModel
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.lane_geometry_id
            or not self.lane_id
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
