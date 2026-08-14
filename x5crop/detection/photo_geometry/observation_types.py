"""Typed, candidate-independent photo-boundary observations.

This module owns data contracts only. Pixel measurement and sequence grouping
live in their respective producer modules so complete-chain code does not
depend on observation-building algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...domain import FiniteInterval, ObservationId
from .model import (
    BoundaryEvidenceState,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)


@dataclass(frozen=True)
class ProfileRun:
    run_id: str
    coordinate_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    role_hint: BoundaryRole | None
    qualified_anchor_roles: tuple[BoundaryRole, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    evidence_strength: float
    pair_qualified: bool = False

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not self.trace_coordinates_px
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or self.role_hint not in {None, BoundaryRole.TOP, BoundaryRole.BOTTOM}
            or len(set(self.qualified_anchor_roles))
            != len(self.qualified_anchor_roles)
            or any(
                role
                not in {
                    BoundaryRole.START,
                    BoundaryRole.END,
                    BoundaryRole.TOP,
                    BoundaryRole.BOTTOM,
                }
                for role in self.qualified_anchor_roles
            )
            or (
                self.role_hint is not None
                and any(
                    role != self.role_hint
                    for role in self.qualified_anchor_roles
                )
            )
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not math.isfinite(self.evidence_strength)
            or self.evidence_strength < 0.0
        ):
            raise ValueError("profile run is invalid")

    def anchor_qualified_for(self, role: BoundaryRole) -> bool:
        return role in self.qualified_anchor_roles


@dataclass(frozen=True)
class BoundaryEdgeObservation:
    observation_id: ObservationId
    run_id: str
    coordinate_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    polarity: int
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    canonical_direction_degrees: float | None
    fit_direction_interval_degrees: FiniteInterval | None
    full_direction_interval_degrees: FiniteInterval | None
    qualified_anchor_roles: tuple[BoundaryRole, ...] = ()
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.transition_ids
            or self.polarity not in {-1, 0, 1}
            or not self.trace_coordinates_px
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or (
                (self.canonical_direction_degrees is None)
                != (self.fit_direction_interval_degrees is None)
            )
            or (
                (self.canonical_direction_degrees is None)
                != (self.full_direction_interval_degrees is None)
            )
            or (
                self.canonical_direction_degrees is not None
                and (
                    not math.isfinite(self.canonical_direction_degrees)
                    or not self.fit_direction_interval_degrees.contains(
                        self.canonical_direction_degrees,
                        epsilon=1.0e-9,
                    )
                    or not self.full_direction_interval_degrees.contains(
                        self.fit_direction_interval_degrees.minimum,
                        epsilon=1.0e-9,
                    )
                    or not self.full_direction_interval_degrees.contains(
                        self.fit_direction_interval_degrees.maximum,
                        epsilon=1.0e-9,
                    )
                )
            )
            or self.evidence_state != BoundaryEvidenceState.SUPPORT
            or len(set(self.qualified_anchor_roles))
            != len(self.qualified_anchor_roles)
            or any(
                role not in {BoundaryRole.START, BoundaryRole.END}
                for role in self.qualified_anchor_roles
            )
        ):
            raise ValueError("boundary edge observation is invalid")


@dataclass(frozen=True)
class SeparatorMaterialRegionObservation:
    region_index: int
    sample_count: int
    darkness_contrast_interval: FiniteInterval
    texture_contrast_interval: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not 0 <= self.region_index < SPATIAL_SUPPORT_REGION_COUNT
            or self.sample_count <= 0
            or self.darkness_contrast_interval.minimum < 0.0
            or self.texture_contrast_interval.minimum < 0.0
        ):
            raise ValueError("separator material region observation is invalid")


@dataclass(frozen=True)
class SeparatorBandObservation:
    """Directly visible positive-width dark separator material.

    Contact and overlap have no positive black material band and therefore
    travel through role-bound edge/local-advance evidence instead.  Keeping
    this interval non-negative is a type boundary, not a clamp on ``g[i]``.
    """

    observation_id: ObservationId
    left_edge_observation_id: ObservationId
    right_edge_observation_id: ObservationId
    left_run_id: str
    right_run_id: str
    gap_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    independent_support_region_count: int
    continuous_support_fraction: float
    darkness_contrast: float
    darkness_contrast_interval: FiniteInterval
    texture_contrast: float
    texture_contrast_interval: FiniteInterval
    material_regions: tuple[SeparatorMaterialRegionObservation, ...]
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.left_run_id
            or not self.right_run_id
            or self.gap_interval_px.minimum < 0.0
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            <= self.independent_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.darkness_contrast)
            or not math.isfinite(self.texture_contrast)
            or self.darkness_contrast < 0.0
            or self.texture_contrast < 0.0
            or not self.darkness_contrast_interval.contains(
                self.darkness_contrast,
                epsilon=1.0e-9,
            )
            or not self.texture_contrast_interval.contains(
                self.texture_contrast,
                epsilon=1.0e-9,
            )
            or self.darkness_contrast_interval.minimum < 0.0
            or self.texture_contrast_interval.minimum < 0.0
            or len(self.material_regions) != self.independent_support_region_count
            or tuple(sorted(item.region_index for item in self.material_regions))
            != tuple(item.region_index for item in self.material_regions)
            or len({item.region_index for item in self.material_regions})
            != len(self.material_regions)
            or self.evidence_state != BoundaryEvidenceState.SUPPORT
        ):
            raise ValueError("separator band observation is invalid")


@dataclass(frozen=True)
class BasicAxisProfile:
    """One lane/axis profile retaining fixed per-trace run identity."""

    axis_name: str
    coordinate_count: int
    trace_coordinates_px: tuple[int, ...]
    runs: tuple[ProfileRun, ...]
    _runs_by_trace: dict[int, tuple[ProfileRun, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if (
            self.axis_name not in {"sequence", "cross"}
            or self.coordinate_count <= 0
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or tuple(
                sorted(
                    self.runs,
                    key=lambda item: (
                        item.coordinate_interval_px.center,
                        item.run_id,
                    ),
                )
            )
            != self.runs
        ):
            raise ValueError("basic axis profile is invalid")
        by_trace: dict[int, list[ProfileRun]] = {
            trace: [] for trace in self.trace_coordinates_px
        }
        for run in self.runs:
            for trace in run.trace_coordinates_px:
                by_trace.setdefault(trace, []).append(run)
        object.__setattr__(
            self,
            "_runs_by_trace",
            {
                trace: tuple(
                    sorted(
                        values,
                        key=lambda item: (
                            item.coordinate_interval_px.center,
                            item.run_id,
                        ),
                    )
                )
                for trace, values in by_trace.items()
            },
        )

    def runs_at_trace(self, trace_coordinate_px: int) -> tuple[ProfileRun, ...]:
        return self._runs_by_trace.get(trace_coordinate_px, ())


@dataclass(frozen=True, order=True)
class OrdinalBoundaryRole:
    role_index: int
    lane_ordinal: int
    role: BoundaryRole

    def __post_init__(self) -> None:
        if (
            self.role_index < 0
            or self.lane_ordinal <= 0
            or self.role not in {BoundaryRole.START, BoundaryRole.END}
        ):
            raise ValueError("sequence proposal role is invalid")


@dataclass(frozen=True)
class SequenceRoleProposal:
    proposal_id: str
    run_id: str
    role: OrdinalBoundaryRole
    phase_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    role_coordinate_px: float
    separator_band_observation_id: ObservationId | None = None

    def __post_init__(self) -> None:
        if (
            not self.proposal_id
            or not self.run_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not math.isfinite(self.role_coordinate_px)
        ):
            raise ValueError("sequence-role proposal is invalid")


@dataclass(frozen=True)
class SeparatorBandRoleProposal:
    """One complete observed separator bound to one adjacency ordinal."""

    proposal_id: str
    band_observation_id: ObservationId
    relation_ordinal: int
    phase_interval_px: FiniteInterval
    gap_interval_px: FiniteInterval
    left_role_proposal: SequenceRoleProposal
    right_role_proposal: SequenceRoleProposal

    def __post_init__(self) -> None:
        if (
            not self.proposal_id
            or self.relation_ordinal <= 0
            or self.gap_interval_px.minimum < 0.0
            or self.left_role_proposal.separator_band_observation_id
            != self.band_observation_id
            or self.right_role_proposal.separator_band_observation_id
            != self.band_observation_id
            or self.left_role_proposal.role
            != OrdinalBoundaryRole(
                role_index=self.relation_ordinal * 2 - 1,
                lane_ordinal=self.relation_ordinal,
                role=BoundaryRole.END,
            )
            or self.right_role_proposal.role
            != OrdinalBoundaryRole(
                role_index=self.relation_ordinal * 2,
                lane_ordinal=self.relation_ordinal + 1,
                role=BoundaryRole.START,
            )
        ):
            raise ValueError("separator-band role proposal is invalid")


@dataclass(frozen=True)
class SequenceHypothesisGroup:
    group_id: str
    phase_interval_px: FiniteInterval
    role_proposals: tuple[SequenceRoleProposal, ...]
    separator_band_proposals: tuple[SeparatorBandRoleProposal, ...]
    ambiguous_proposal_ids: tuple[str, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        if (
            not self.group_id
            or not self.role_proposals
            or len({proposal.proposal_id for proposal in self.role_proposals})
            != len(self.role_proposals)
            or len(set(self.ambiguous_proposal_ids))
            != len(self.ambiguous_proposal_ids)
            or any(
                proposal.left_role_proposal not in self.role_proposals
                or proposal.right_role_proposal not in self.role_proposals
                for proposal in self.separator_band_proposals
            )
        ):
            raise ValueError("sequence hypothesis group is invalid")


@dataclass(frozen=True)
class SequenceGroupingWork:
    phase_seed_count: int
    ordinal_role_lookup_count: int
    ordinal_role_match_count: int

    def __post_init__(self) -> None:
        if (
            self.phase_seed_count < 0
            or self.ordinal_role_lookup_count < 0
            or self.ordinal_role_match_count < 0
        ):
            raise ValueError("sequence grouping work is invalid")
