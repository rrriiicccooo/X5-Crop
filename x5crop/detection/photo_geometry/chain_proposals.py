"""Finite cross/sequence proposal and lane-input contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...configuration.model import HolderLayoutAuthority
from ...domain import FiniteInterval, PositiveInterval
from ...formats import FramePhysicalSpec
from .model import (
    BoundaryAxis,
    BoundaryRole,
)
from .measurement_model import (
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .line_observations import PhotoBoundaryObservation
from .observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    OrdinalBoundaryRole,
    ProfileRun,
    SeparatorBandObservation,
    SeparatorBandRoleProposal,
    SequenceGroupingWork,
    SequenceHypothesisGroup,
    SequenceRoleProposal,
)
from .output_model import SharedStripDirection
from .sequence_models import LocalAdvanceRelation, SequenceDiscoveryKind
from .source_geometry import SourceScanGeometry


@dataclass(frozen=True)
class SequenceChainProposal:
    chain_proposal_id: str
    discovery_kind: SequenceDiscoveryKind
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
            or len({item.proposal_id for item in self.role_proposals})
            != len(self.role_proposals)
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
class CrossAxisProposal:
    cross_proposal_id: str
    frame_spec_id: str
    origin_interval_px: FiniteInterval
    observed_runs: tuple[ProfileRun, ...]
    raw_observations: tuple[PhotoBoundaryObservation, ...]
    direct_height_span_validated: bool

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
                    key=lambda role: 0 if role == BoundaryRole.TOP else 1,
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
            or (
                self.direct_height_span_validated
                and len(self.observed_runs) != 2
            )
        ):
            raise ValueError("cross-axis proposal is invalid")


@dataclass(frozen=True)
class LaneObservationInput:
    lane_id: str
    output_slot_count: int
    measurement_slot_count: int
    holder_layout_authority: HolderLayoutAuthority
    holder_extent_tolerance_ratio: float
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
            or not isinstance(
                self.holder_layout_authority,
                HolderLayoutAuthority,
            )
            or not math.isfinite(self.holder_extent_tolerance_ratio)
            or not 0.0 < self.holder_extent_tolerance_ratio < 1.0
            or self.width_axis == self.height_axis
            or self.sequence_profile.axis_name != "sequence"
            or self.cross_profile.axis_name != "cross"
            or any(
                edge.run_id
                not in {run.run_id for run in self.sequence_profile.runs}
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
    discovery_kind: SequenceDiscoveryKind
    initial_source_scan_geometry: SourceScanGeometry
    roles: tuple[OrdinalBoundaryRole, ...]
    role_proposals: tuple[SequenceRoleProposal, ...]
    separator_band_proposals: tuple[SeparatorBandRoleProposal, ...]
    sequence_groups: tuple[SequenceHypothesisGroup, ...]
    grouping_work: SequenceGroupingWork

    def __post_init__(self) -> None:
        if (
            self.initial_source_scan_geometry.frame_spec != self.frame_spec
            or not self.roles
            or not self.role_proposals
            or not self.sequence_groups
        ):
            raise ValueError("frame chain proposals are invalid")


@dataclass(frozen=True)
class LanePhysicalProposals:
    lane: LaneObservationInput
    frame_proposals: tuple[FrameChainProposals, ...]
    cross_proposals: tuple[CrossAxisProposal, ...]
    raw_top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    direction_classes: tuple[SharedStripDirection, ...]

    def __post_init__(self) -> None:
        if any(
            proposal.frame_spec.frame_spec_id
            != proposal.initial_source_scan_geometry.frame_spec.frame_spec_id
            for proposal in self.frame_proposals
        ):
            raise ValueError("lane proposal frame identity is invalid")
