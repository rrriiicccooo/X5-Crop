"""Typed, candidate-independent photo-boundary observations."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
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


class BoundaryEdgeMeasurementBasis(str, Enum):
    DIRECT_TRACE = "direct_trace"
    CROSS_HEIGHT_AGGREGATE = "cross_height_aggregate"
    BROAD_MATERIAL_AGGREGATE = "broad_material_aggregate"
    DIRECT_WITH_AGGREGATE = "direct_with_aggregate"


@dataclass(frozen=True)
class BoundaryEdgeObservation:
    observation_id: ObservationId
    run_id: str
    discovery_interval_px: FiniteInterval
    reference_trace_px: float
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    polarity: int
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    canonical_direction_degrees: float | None
    fit_direction_interval_degrees: FiniteInterval | None
    full_direction_interval_degrees: FiniteInterval | None
    measurement_basis: BoundaryEdgeMeasurementBasis
    aggregate_support_id: ObservationId | None = None
    qualified_anchor_roles: tuple[BoundaryRole, ...] = ()
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not isinstance(self.discovery_interval_px, FiniteInterval)
            or not self.transition_ids
            or self.polarity not in {-1, 0, 1}
            or not self.trace_coordinates_px
            or not math.isfinite(self.reference_trace_px)
            or not math.isfinite(self.canonical_position_px)
            or not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-9,
            )
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not isinstance(
                self.measurement_basis,
                BoundaryEdgeMeasurementBasis,
            )
            or (
                self.measurement_basis
                == BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE
            )
            != (self.aggregate_support_id is not None)
            or (
                self.aggregate_support_id is not None
                and self.aggregate_support_id == self.observation_id
            )
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


class AggregateEdgeResolutionKind(str, Enum):
    BOUND_DIRECT_EDGE = "bound_direct_edge"
    MATCHED_EXISTING_EDGE = "matched_existing_edge"
    STANDALONE_EDGE = "standalone_edge"
    REDUNDANT_EXISTING_EDGE = "redundant_existing_edge"
    AMBIGUOUS_EXISTING_MATCH = "ambiguous_existing_match"
    INSUFFICIENT_SPATIAL_SUPPORT = "insufficient_spatial_support"


class AggregateEdgeResolutionFailureKind(str, Enum):
    INSUFFICIENT_INDEPENDENT_SPATIAL_SUPPORT = (
        "insufficient_independent_spatial_support"
    )
    MULTIPLE_COMPATIBLE_EXISTING_EDGES = (
        "multiple_compatible_existing_edges"
    )
    MULTIPLE_AGGREGATES_FOR_ONE_EXISTING_EDGE = (
        "multiple_aggregates_for_one_existing_edge"
    )


@dataclass(frozen=True)
class AggregateEdgeResolution:
    """How one three-region aggregate may enter the edge ledger."""

    support_observation_id: ObservationId
    state: EvidenceState
    kind: AggregateEdgeResolutionKind
    compatible_existing_edge_ids: tuple[ObservationId, ...]
    final_edge_observation_id: ObservationId | None
    failure_kind: AggregateEdgeResolutionFailureKind | None

    def __post_init__(self) -> None:
        ambiguous = self.kind == (
            AggregateEdgeResolutionKind.AMBIGUOUS_EXISTING_MATCH
        )
        insufficient = self.kind == (
            AggregateEdgeResolutionKind.INSUFFICIENT_SPATIAL_SUPPORT
        )
        failed = ambiguous or insufficient
        expected_state = (
            EvidenceState.CONTRADICTED
            if ambiguous
            else EvidenceState.UNAVAILABLE
            if insufficient
            else EvidenceState.SUPPORTED
        )
        if (
            not isinstance(self.support_observation_id, ObservationId)
            or not isinstance(self.state, EvidenceState)
            or not isinstance(self.kind, AggregateEdgeResolutionKind)
            or tuple(sorted(set(self.compatible_existing_edge_ids)))
            != self.compatible_existing_edge_ids
            or any(
                not isinstance(item, ObservationId)
                for item in self.compatible_existing_edge_ids
            )
            or self.state != expected_state
            or failed != (self.failure_kind is not None)
            or (
                self.failure_kind is not None
                and not isinstance(
                    self.failure_kind,
                    AggregateEdgeResolutionFailureKind,
                )
            )
            or (
                self.failure_kind
                == AggregateEdgeResolutionFailureKind
                .INSUFFICIENT_INDEPENDENT_SPATIAL_SUPPORT
                and not insufficient
            )
            or (
                self.failure_kind
                == AggregateEdgeResolutionFailureKind
                .MULTIPLE_COMPATIBLE_EXISTING_EDGES
                and len(self.compatible_existing_edge_ids) <= 1
            )
            or (
                self.failure_kind
                == AggregateEdgeResolutionFailureKind
                .MULTIPLE_AGGREGATES_FOR_ONE_EXISTING_EDGE
                and len(self.compatible_existing_edge_ids) != 1
            )
            or (
                self.kind
                in {
                    AggregateEdgeResolutionKind.BOUND_DIRECT_EDGE,
                    AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE,
                    AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE,
                }
                and len(self.compatible_existing_edge_ids) != 1
            )
            or (
                self.kind
                == AggregateEdgeResolutionKind.STANDALONE_EDGE
                and (
                    self.compatible_existing_edge_ids
                    or self.final_edge_observation_id
                    != self.support_observation_id
                )
            )
            or (
                self.kind
                in {
                    AggregateEdgeResolutionKind.BOUND_DIRECT_EDGE,
                    AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE,
                    AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE,
                }
                and self.final_edge_observation_id
                not in self.compatible_existing_edge_ids
            )
            or (
                failed
                and (
                    self.final_edge_observation_id is not None
                    or (
                        insufficient
                        and self.compatible_existing_edge_ids
                    )
                )
            )
        ):
            raise ValueError("aggregate edge resolution is invalid")


class SeparatorMaterialPolarity(str, Enum):
    DARK = "dark"
    LIGHT = "light"


class SeparatorBandMeasurementBasis(str, Enum):
    DIRECT_TRACE = "direct_trace"
    CROSS_HEIGHT_AGGREGATE = "cross_height_aggregate"
    BROAD_MATERIAL_AGGREGATE = "broad_material_aggregate"


class SeparatorMaterialRegionState(str, Enum):
    SUPPORTED = "supported"
    TONE_UNRESOLVED = "tone_unresolved"
    MATERIAL_NON_UNIFORM = "material_non_uniform"


@dataclass(frozen=True)
class SeparatorMaterialRegionObservation:
    region_index: int
    sample_count: int
    material_contrast_interval: FiniteInterval
    core_texture_interval: FiniteInterval
    state: SeparatorMaterialRegionState

    def __post_init__(self) -> None:
        if (
            not 0 <= self.region_index < SPATIAL_SUPPORT_REGION_COUNT
            or self.sample_count <= 0
            or self.core_texture_interval.minimum < 0.0
            or not isinstance(self.state, SeparatorMaterialRegionState)
        ):
            raise ValueError("separator material region observation is invalid")


@dataclass(frozen=True)
class SeparatorBandObservation:
    """Directly visible positive-width separator material.

    Contact and overlap have no positive material band and therefore
    travel through role-bound edge/adjacency evidence instead.  Keeping
    this interval non-negative is a type boundary, not a clamp on ``g[i]``.
    """

    observation_id: ObservationId
    left_edge_observation_id: ObservationId
    right_edge_observation_id: ObservationId
    left_run_id: str
    right_run_id: str
    measurement_basis: SeparatorBandMeasurementBasis
    material_polarity: SeparatorMaterialPolarity
    gap_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    material_support_region_count: int
    continuous_support_fraction: float
    material_contrast: float
    material_contrast_interval: FiniteInterval
    core_texture: float
    core_texture_interval: FiniteInterval
    material_regions: tuple[SeparatorMaterialRegionObservation, ...]
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.left_run_id
            or not self.right_run_id
            or not isinstance(
                self.measurement_basis,
                SeparatorBandMeasurementBasis,
            )
            or not isinstance(
                self.material_polarity,
                SeparatorMaterialPolarity,
            )
            or self.gap_interval_px.minimum < 0.0
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not 0
            <= self.material_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.material_contrast)
            or not math.isfinite(self.core_texture)
            or self.core_texture < 0.0
            or not self.material_contrast_interval.contains(
                self.material_contrast,
                epsilon=1.0e-9,
            )
            or not self.core_texture_interval.contains(
                self.core_texture,
                epsilon=1.0e-9,
            )
            or self.core_texture_interval.minimum < 0.0
            or not MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            <= len(self.material_regions)
            <= SPATIAL_SUPPORT_REGION_COUNT
            or tuple(sorted(item.region_index for item in self.material_regions))
            != tuple(item.region_index for item in self.material_regions)
            or len({item.region_index for item in self.material_regions})
            != len(self.material_regions)
            or self.material_support_region_count
            != sum(
                item.state == SeparatorMaterialRegionState.SUPPORTED
                for item in self.material_regions
            )
            or self.evidence_state
            not in {
                BoundaryEvidenceState.SUPPORT,
                BoundaryEvidenceState.CONTRADICTION,
            }
            or (
                self.evidence_state == BoundaryEvidenceState.SUPPORT
                and self.material_support_region_count
                < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            )
            or (
                self.evidence_state == BoundaryEvidenceState.CONTRADICTION
                and (
                    len(self.material_regions)
                    != SPATIAL_SUPPORT_REGION_COUNT
                    or self.material_support_region_count
                    >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                )
            )
        ):
            raise ValueError("separator band observation is invalid")


@dataclass(frozen=True)
class OuterMaterialBoundaryObservation:
    """One material band that distinguishes an aperture edge from its exterior.

    The two physical edges carry the same START or END role.  The inner edge
    may own only the corresponding first/last template role; the exterior edge
    is counterevidence for that same role.  Correlated direct, cross-height and
    broad-material measurements are collapsed into one evidence group.
    """

    observation_id: ObservationId
    evidence_group_id: ObservationId
    role: BoundaryRole
    boundary_edge_observation_id: ObservationId
    exterior_edge_observation_id: ObservationId
    supporting_band_observation_ids: tuple[ObservationId, ...]
    measurement_bases: tuple[SeparatorBandMeasurementBasis, ...]
    material_polarities: tuple[SeparatorMaterialPolarity, ...]
    material_interval_px: FiniteInterval
    independent_support_region_count: int
    exterior_edge_has_intrinsic_authority: bool
    state: EvidenceState = EvidenceState.SUPPORTED

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.evidence_group_id, ObservationId)
            or self.role not in {BoundaryRole.START, BoundaryRole.END}
            or not isinstance(
                self.boundary_edge_observation_id,
                ObservationId,
            )
            or not isinstance(
                self.exterior_edge_observation_id,
                ObservationId,
            )
            or self.boundary_edge_observation_id
            == self.exterior_edge_observation_id
            or tuple(sorted(set(self.supporting_band_observation_ids)))
            != self.supporting_band_observation_ids
            or not self.supporting_band_observation_ids
            or any(
                not isinstance(item, ObservationId)
                for item in self.supporting_band_observation_ids
            )
            or tuple(
                item
                for item in SeparatorBandMeasurementBasis
                if item in self.measurement_bases
            )
            != self.measurement_bases
            or not self.measurement_bases
            or tuple(
                item
                for item in SeparatorMaterialPolarity
                if item in self.material_polarities
            )
            != self.material_polarities
            or not self.material_polarities
            or self.material_interval_px.minimum < 0.0
            or self.independent_support_region_count
            not in {
                MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
                SPATIAL_SUPPORT_REGION_COUNT,
            }
            or not isinstance(
                self.exterior_edge_has_intrinsic_authority,
                bool,
            )
            or (
                self.independent_support_region_count
                < SPATIAL_SUPPORT_REGION_COUNT
                and not self.exterior_edge_has_intrinsic_authority
            )
            or self.state != EvidenceState.SUPPORTED
        ):
            raise ValueError("outer material boundary observation is invalid")


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
