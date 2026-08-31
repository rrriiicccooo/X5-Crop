"""Canonical result records for bounded sequence phase fitting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .measurement_model import PhotoBoundaryMeasurementSet
from .template_adjacency_coverage import AdjacencyObservationCoverage
from .template_direct_role_authority import DirectRoleBindingAuthority
from .template_outer_frame_authority import OuterFrameObservationAuthority
from .template_model import (
    SequenceFit,
    TemplateSearchReceipt,
    TemplateSpec,
)


@dataclass(frozen=True)
class GlobalLatticeAuthorityEvidence:
    """Registered direct evidence that already owns one lattice unknown."""

    phase_observation_ids: tuple[ObservationId, ...] = ()
    frame_width_observation_ids: tuple[ObservationId, ...] = ()
    pitch_observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        for identities in (
            self.phase_observation_ids,
            self.frame_width_observation_ids,
            self.pitch_observation_ids,
        ):
            if len(set(identities)) != len(identities) or any(
                not isinstance(identity, ObservationId)
                for identity in identities
            ):
                raise ValueError("global lattice evidence identities are invalid")


class GlobalLatticeConstraintKind(str, Enum):
    DIRECT_ROLE_COORDINATE = "direct_role_coordinate"
    ABSOLUTE_PHASE = "absolute_phase"
    FRAME_WIDTH = "frame_width"
    SOURCE_PITCH = "source_pitch"


@dataclass(frozen=True)
class GlobalLatticeConstraint:
    """One registered linear constraint on ``(phase, W, pitch)``."""

    constraint_id: str
    kind: GlobalLatticeConstraintKind
    coefficients: tuple[float, float, float]
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            not self.constraint_id
            or not isinstance(self.kind, GlobalLatticeConstraintKind)
            or len(self.coefficients) != 3
            or any(not math.isfinite(value) for value in self.coefficients)
            or not any(abs(value) > 1.0e-12 for value in self.coefficients)
            or not self.observation_ids
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.observation_ids
            )
        ):
            raise ValueError("global lattice constraint is invalid")


class GlobalLatticeAuthorityBasis(str, Enum):
    DIRECT_ROLE_SYSTEM = "direct_role_system"
    COMPLEMENTARY_DIRECT_EVIDENCE = "complementary_direct_evidence"


@dataclass(frozen=True)
class GlobalLatticeAuthority:
    """Joint closure of the three global unknowns: phase, W, and pitch."""

    state: EvidenceState
    direct_role_constraint_rank: int
    joint_constraint_rank: int
    constraints: tuple[GlobalLatticeConstraint, ...]
    role_observation_ids: tuple[ObservationId, ...]
    registered_evidence: GlobalLatticeAuthorityEvidence
    basis: GlobalLatticeAuthorityBasis | None
    reason: str | None

    def __post_init__(self) -> None:
        if (
            self.state not in {EvidenceState.SUPPORTED, EvidenceState.UNAVAILABLE}
            or not 0 <= self.direct_role_constraint_rank <= 3
            or not self.direct_role_constraint_rank <= self.joint_constraint_rank <= 3
            or len({item.constraint_id for item in self.constraints})
            != len(self.constraints)
            or any(
                not isinstance(item, GlobalLatticeConstraint)
                for item in self.constraints
            )
            or len(set(self.role_observation_ids)) != len(self.role_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.role_observation_ids
            )
            or not isinstance(
                self.registered_evidence,
                GlobalLatticeAuthorityEvidence,
            )
        ):
            raise ValueError("global lattice authority is invalid")
        closed = self.state == EvidenceState.SUPPORTED
        if closed != (self.joint_constraint_rank == 3):
            raise ValueError("global lattice state disagrees with joint closure")
        if closed != isinstance(self.basis, GlobalLatticeAuthorityBasis):
            raise ValueError("global lattice basis must match closure state")
        if closed == (self.reason is not None):
            raise ValueError("global lattice reason must describe only unavailable state")
        direct_constraints = tuple(
            item
            for item in self.constraints
            if item.kind == GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE
        )
        if tuple(
            identity
            for item in direct_constraints
            for identity in item.observation_ids
        ) != self.role_observation_ids:
            raise ValueError("global lattice role provenance disagrees")


@dataclass(frozen=True)
class TemplatePhaseInput:
    """Exact registered input to the bounded phase/advance solver."""

    observations: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    template: TemplateSpec
    scale_px_per_mm: PositiveInterval | None
    holder_span_px: FiniteInterval | None
    phase_authority_px: FiniteInterval | None
    sequence_measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...] = ()
    global_lattice_evidence: GlobalLatticeAuthorityEvidence = field(
        default_factory=GlobalLatticeAuthorityEvidence
    )
    max_observations: int = 512

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("phase input requires a fixed template")
        if self.scale_px_per_mm is not None and not isinstance(
            self.scale_px_per_mm,
            PositiveInterval,
        ):
            raise TypeError("phase input scale must be a positive interval")
        for value, name in (
            (self.holder_span_px, "holder span"),
            (self.phase_authority_px, "phase authority"),
        ):
            if value is not None and not isinstance(value, FiniteInterval):
                raise TypeError(f"phase input {name} must be a finite interval")
        if not isinstance(
            self.global_lattice_evidence,
            GlobalLatticeAuthorityEvidence,
        ):
            raise TypeError("phase input global lattice evidence is invalid")
        if any(
            not isinstance(item, PhotoBoundaryMeasurementSet)
            for item in self.sequence_measurement_sets
        ):
            raise TypeError("phase input sequence measurement ledger is invalid")
        query_ids = tuple(
            item.query.query_id for item in self.sequence_measurement_sets
        )
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("phase input sequence queries must be unique")
        if self.sequence_measurement_sets:
            first_query = self.sequence_measurement_sets[0].query
            if any(
                item.query.lane_id != first_query.lane_id
                or item.query.boundary_axis != first_query.boundary_axis
                or item.query.trace_positions_px
                != first_query.trace_positions_px
                for item in self.sequence_measurement_sets[1:]
            ):
                raise ValueError(
                    "phase input sequence queries must share one trace lattice"
                )
        if (
            self.global_lattice_evidence.phase_observation_ids
            and self.phase_authority_px is None
        ):
            raise ValueError("phase evidence requires an absolute phase authority")
        identities = tuple(item.observation_id for item in self.observations)
        band_ids = tuple(item.observation_id for item in self.separator_bands)
        registered_ids = set(identities).union(band_ids)
        evidence_ids = {
            identity
            for group in (
                self.global_lattice_evidence.phase_observation_ids,
                self.global_lattice_evidence.frame_width_observation_ids,
                self.global_lattice_evidence.pitch_observation_ids,
            )
            for identity in group
        }
        if len(set(identities)) != len(identities):
            raise ValueError("phase input observation identities are not unique")
        if len(set(band_ids)) != len(band_ids):
            raise ValueError("phase input separator identities are not unique")
        if not evidence_ids.issubset(registered_ids):
            raise ValueError(
                "global lattice evidence is absent from the phase ledger"
            )
        if (
            not isinstance(self.max_observations, int)
            or isinstance(self.max_observations, bool)
            or self.max_observations <= 0
        ):
            raise ValueError("phase observation bound must be a positive integer")


class PhaseFitStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    BOUND_EXCEEDED = "bound_exceeded"


class PhaseFailureKind(str, Enum):
    OBSERVATION_BOUND_EXCEEDED = "observation_bound_exceeded"
    HYPOTHESIS_BOUND_EXCEEDED = "hypothesis_bound_exceeded"
    DIRECT_PHASE_ANCHOR_UNAVAILABLE = "direct_phase_anchor_unavailable"
    GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE = (
        "global_lattice_authority_unavailable"
    )
    ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE = (
        "adjacency_observation_coverage_incomplete"
    )
    DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE = (
        "direct_role_binding_authority_unavailable"
    )
    SEPARATOR_MATERIAL_CONFLICT = "separator_material_conflict"
    OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE = (
        "outer_frame_observation_authority_unavailable"
    )
    FRAME_WIDTH_INFERENCE_UNAVAILABLE = (
        "frame_width_inference_unavailable"
    )
    FIXED_TEMPLATE_MISMATCH = "fixed_template_mismatch"
    DISCRETE_PHASE_AMBIGUOUS = "discrete_phase_ambiguous"
    LOCAL_ADVANCE_AMBIGUOUS = "local_advance_ambiguous"


class PhaseWinnerBasis(str, Enum):
    ONLY_PHYSICAL_FIT = "only_physical_fit"
    UNIQUE_DIRECT_ROLE_AUTHORITY = "unique_direct_role_authority"
    RESIDUAL_COMPATIBILITY = "residual_compatibility"
    INDEPENDENT_SUPPORT = "independent_support"
    INDEPENDENT_COVERAGE = "independent_coverage"
    RESIDUAL_SEPARATION = "residual_separation"


@dataclass(frozen=True)
class PhaseFitResult:
    template: TemplateSpec
    best: SequenceFit | None
    runner_up: SequenceFit | None
    status: PhaseFitStatus
    ambiguity_reason: str | None
    receipt: TemplateSearchReceipt
    registered_direct_observation_ids: tuple[ObservationId, ...]
    failure_kind: PhaseFailureKind | None = None
    winner_basis: PhaseWinnerBasis | None = None
    best_phase_candidate_direct_role_authority: (
        DirectRoleBindingAuthority | None
    ) = None
    runner_phase_candidate_direct_role_authority: (
        DirectRoleBindingAuthority | None
    ) = None
    global_lattice_authority: GlobalLatticeAuthority | None = None
    adjacency_observation_coverage: tuple[AdjacencyObservationCoverage, ...] = ()
    direct_role_binding_authority: DirectRoleBindingAuthority | None = None
    outer_frame_observation_authority: (
        OuterFrameObservationAuthority | None
    ) = None

    def __post_init__(self) -> None:
        if (
            len(set(self.registered_direct_observation_ids))
            != len(self.registered_direct_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.registered_direct_observation_ids
            )
        ):
            raise ValueError("registered direct observation ledger is invalid")
        if self.status == PhaseFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved phase fit requires a placement")
        if self.status == PhaseFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded phase fit cannot authorize placement")
        if self.ambiguity_reason is not None and not self.ambiguity_reason:
            raise ValueError("phase ambiguity reason must not be empty")
        if (self.status == PhaseFitStatus.RESOLVED) != (self.failure_kind is None):
            raise ValueError("phase failure kind must match fit status")
        if (self.status == PhaseFitStatus.RESOLVED) != isinstance(
            self.winner_basis, PhaseWinnerBasis
        ):
            raise ValueError("phase winner basis must match resolved status")
        if (
            self.best_phase_candidate_direct_role_authority is not None
            and not isinstance(
                self.best_phase_candidate_direct_role_authority,
                DirectRoleBindingAuthority,
            )
        ):
            raise TypeError("best phase-candidate direct-role authority is invalid")
        if (
            self.runner_phase_candidate_direct_role_authority is not None
            and not isinstance(
                self.runner_phase_candidate_direct_role_authority,
                DirectRoleBindingAuthority,
            )
        ):
            raise TypeError("runner phase-candidate direct-role authority is invalid")
        if (
            self.best is None
            and self.best_phase_candidate_direct_role_authority is not None
            or self.runner_up is None
            and self.runner_phase_candidate_direct_role_authority is not None
        ):
            raise ValueError("phase-candidate authority requires its candidate")
        if self.global_lattice_authority is not None and not isinstance(
            self.global_lattice_authority,
            GlobalLatticeAuthority,
        ):
            raise TypeError("phase global lattice authority is invalid")
        if any(
            not isinstance(item, AdjacencyObservationCoverage)
            for item in self.adjacency_observation_coverage
        ):
            raise TypeError("phase adjacency observation coverage is invalid")
        if (
            self.direct_role_binding_authority is not None
            and not isinstance(
                self.direct_role_binding_authority,
                DirectRoleBindingAuthority,
            )
        ):
            raise TypeError("phase direct-role binding authority is invalid")
        if (
            self.outer_frame_observation_authority is not None
            and not isinstance(
                self.outer_frame_observation_authority,
                OuterFrameObservationAuthority,
            )
        ):
            raise TypeError("phase outer-frame observation authority is invalid")
        if self.adjacency_observation_coverage and tuple(
            item.relation_ordinal
            for item in self.adjacency_observation_coverage
        ) != tuple(range(1, self.template.count)):
            raise ValueError("phase adjacency coverage must follow template order")



@dataclass(frozen=True)
class TemplatePhaseCandidateCompetition:
    """One discrete/local competition before selected-only W is consumed."""

    result: PhaseFitResult
    directly_observed_adjacency_ordinals: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, PhaseFitResult):
            raise TypeError("phase candidate competition requires a phase result")
        ordinals = self.directly_observed_adjacency_ordinals
        if (
            tuple(sorted(set(ordinals))) != ordinals
            or any(
                ordinal <= 0 or ordinal >= self.result.template.count
                for ordinal in ordinals
            )
        ):
            raise ValueError("directly observed adjacency ordinals are invalid")
