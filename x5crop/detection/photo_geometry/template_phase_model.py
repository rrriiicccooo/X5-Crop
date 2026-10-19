"""Canonical result records for bounded sequence phase fitting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .template_phase_membership import PhaseCompetitionScope

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .observation_types import (
    BoundaryEdgeObservation,
    OuterMaterialBoundaryObservation,
    SeparatorBandObservation,
)
from .measurement_model import PhotoBoundaryMeasurementSet
from .template_adjacency_coverage import AdjacencyObservationCoverage
from .template_adjacency_topology import AdjacencyContinuityObservation, PhaseCandidateAdjacencyAssessment
from .template_contact import ContactEdgeObservation
from .template_overlap import OverlapEdgePairObservation
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleBindingAuthority,
)
from .template_outer_frame_authority import OuterFrameObservationAuthority
from .template_model import SequenceFit, TemplateSearchReceipt, TemplateSpec
from .template_nominal_grid_model import (
    CalibratedNominalGridEvidence,
    CalibratedNominalGridPrior,
)
from .template_source_domain import PhaseSourceDomain
from .template_source_clipped import SourceClippedPhaseRetention
from .template_phase_candidate_model import _BoundFit, _rank


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
    role_index: int | None
    value_interval_px: FiniteInterval | None

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
            or (
                self.kind == GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE
                and (
                    self.role_index is None
                    or self.role_index < 0
                    or not isinstance(
                        self.value_interval_px,
                        FiniteInterval,
                    )
                )
            )
            or (
                self.kind == GlobalLatticeConstraintKind.ABSOLUTE_PHASE
                and (
                    self.role_index is not None
                    or not isinstance(
                        self.value_interval_px,
                        FiniteInterval,
                    )
                )
            )
            or (
                self.kind
                in {
                    GlobalLatticeConstraintKind.FRAME_WIDTH,
                    GlobalLatticeConstraintKind.SOURCE_PITCH,
                }
                and (
                    self.role_index is not None
                    or self.value_interval_px is not None
                )
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
    calibrated_nominal_grid_prior: CalibratedNominalGridPrior
    outer_material_boundaries: tuple[
        OuterMaterialBoundaryObservation,
        ...,
    ] = ()
    contact_edge_observations: tuple[ContactEdgeObservation, ...] = ()
    overlap_edge_pair_observations: tuple[
        OverlapEdgePairObservation,
        ...,
    ] = ()
    sequence_measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...] = ()
    global_lattice_evidence: GlobalLatticeAuthorityEvidence = field(
        default_factory=GlobalLatticeAuthorityEvidence
    )
    max_observations: int = 512
    source_domain: PhaseSourceDomain | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("phase input requires a fixed template")
        if (
            not isinstance(
                self.calibrated_nominal_grid_prior,
                CalibratedNominalGridPrior,
            )
            or self.calibrated_nominal_grid_prior.template_id
            != self.template.template_id
        ):
            raise TypeError("phase input nominal Grid prior is invalid")
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
        if self.source_domain is not None:
            if not isinstance(self.source_domain, PhaseSourceDomain):
                raise TypeError("phase input source domain must be typed")
            self.source_domain.validate_registration(
                self.holder_span_px,
                self.sequence_measurement_sets,
            )
        if any(
            not isinstance(item, OuterMaterialBoundaryObservation)
            for item in self.outer_material_boundaries
        ):
            raise TypeError("phase input outer material ledger is invalid")
        if any(
            not isinstance(item, ContactEdgeObservation)
            for item in self.contact_edge_observations
        ):
            raise TypeError("phase input contact-edge ledger is invalid")
        if any(
            not isinstance(item, OverlapEdgePairObservation)
            for item in self.overlap_edge_pair_observations
        ):
            raise TypeError("phase input overlap-edge ledger is invalid")
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
        contact_ids = tuple(
            item.observation_id for item in self.contact_edge_observations
        )
        overlap_ids = tuple(
            item.observation_id
            for item in self.overlap_edge_pair_observations
        )
        band_ids = tuple(item.observation_id for item in self.separator_bands)
        outer_material_ids = tuple(
            item.observation_id for item in self.outer_material_boundaries
        )
        registered_ids = set(identities).union(
            band_ids,
            outer_material_ids,
        )
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
        if len(set(contact_ids)) != len(contact_ids):
            raise ValueError("phase input contact identities are not unique")
        if len(set(outer_material_ids)) != len(outer_material_ids):
            raise ValueError(
                "phase input outer material identities are not unique"
            )
        if len(registered_ids) != (
            len(identities) + len(band_ids) + len(outer_material_ids)
        ):
            raise ValueError(
                "phase input evidence identities overlap across ledgers"
            )
        if len(set(overlap_ids)) != len(overlap_ids):
            raise ValueError("phase input overlap identities are not unique")
        if len(overlap_ids) > max(0, len(identities) - 1):
            raise ValueError("phase input overlap ledger exceeds its linear bound")
        if not {
            item.shared_edge_observation_id
            for item in self.contact_edge_observations
        }.issubset(set(identities)):
            raise ValueError("contact edge leaves the registered observation ledger")
        outer_material_edge_ids = {
            identity
            for item in self.outer_material_boundaries
            for identity in (
                item.boundary_edge_observation_id,
                item.exterior_edge_observation_id,
            )
        }
        missing_outer_material_edges = tuple(
            sorted(outer_material_edge_ids.difference(identities))
        )
        if missing_outer_material_edges:
            raise ValueError(
                "outer material boundary leaves the registered observation "
                f"ledger: {missing_outer_material_edges}"
            )
        if not {
            identity
            for item in self.overlap_edge_pair_observations
            for identity in item.supporting_observation_ids
        }.issubset(set(identities)):
            raise ValueError("overlap pair leaves the registered observation ledger")
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
    CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE = (
        "calibrated_nominal_grid_authority_unavailable"
    )
    CALIBRATED_NOMINAL_GRID_CONFLICT = (
        "calibrated_nominal_grid_conflict"
    )
    DIRECT_LATTICE_CONFLICT = "direct_lattice_conflict"
    NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE = (
        "nominal_grid_phase_anchor_unavailable"
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
    SOURCE_FRAME_WIDTH_CONFLICT = "source_frame_width_conflict"
    FIXED_TEMPLATE_MISMATCH = "fixed_template_mismatch"
    DISCRETE_PHASE_AMBIGUOUS = "discrete_phase_ambiguous"
    ADJACENCY_RELATION_AMBIGUOUS = "adjacency_relation_ambiguous"
    ADJACENCY_CONTINUITY_UNRESOLVED = (
        "adjacency_continuity_unresolved"
    )
    ADJACENCY_TOPOLOGY_AMBIGUOUS = "adjacency_topology_ambiguous"
    ADJACENCY_TOPOLOGY_UNRESOLVED = "adjacency_topology_unresolved"


class PhaseWinnerBasis(str, Enum):
    ONLY_PHYSICAL_FIT = "only_physical_fit"
    UNIQUE_DIRECT_ROLE_AUTHORITY = "unique_direct_role_authority"
    RESIDUAL_COMPATIBILITY = "residual_compatibility"
    INDEPENDENT_SUPPORT = "independent_support"
    INDEPENDENT_COVERAGE = "independent_coverage"
    RESIDUAL_SEPARATION = "residual_separation"


class PhaseRetainedProposalBasis(str, Enum):
    """Why an unresolved phase still carries one complete proposal fit."""

    CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE = (
        "calibrated_nominal_grid_before_local_counterevidence"
    )
    DIRECT_LATTICE_BEFORE_LOCAL_COUNTEREVIDENCE = (
        "direct_lattice_before_local_counterevidence"
    )
    CALIBRATED_NOMINAL_GRID_WITH_RESIDUAL_COUNTEREVIDENCE = (
        "calibrated_nominal_grid_with_residual_counterevidence"
    )
    DIRECT_LATTICE_WITH_RESIDUAL_COUNTEREVIDENCE = (
        "direct_lattice_with_residual_counterevidence"
    )


class SourceFrameWidthTopologyFailureKind(str, Enum):
    """Why one independently closed source W cannot preserve normal topology."""

    NORMAL_ADJACENCY_UNRESOLVED = "normal_adjacency_unresolved"
    NORMAL_ADJACENCY_CONTRADICTED = "normal_adjacency_contradicted"


@dataclass(frozen=True)
class SourceFrameWidthTopologyFact:
    """One normal adjacency whose output ordering depends on source W."""

    relation_ordinal: int
    inferred_role_indices: tuple[int, ...]
    signed_gap_interval_px: FiniteInterval
    canonical_signed_gap_px: float
    state: EvidenceState

    def __post_init__(self) -> None:
        expected_state = (
            EvidenceState.SUPPORTED
            if self.signed_gap_interval_px.minimum >= -1.0e-9
            else EvidenceState.CONTRADICTED
            if self.signed_gap_interval_px.maximum < -1.0e-9
            else EvidenceState.UNAVAILABLE
        )
        if (
            self.relation_ordinal <= 0
            or not self.inferred_role_indices
            or self.inferred_role_indices
            != tuple(sorted(set(self.inferred_role_indices)))
            or any(index < 0 for index in self.inferred_role_indices)
            or any(
                index
                not in {
                    2 * self.relation_ordinal - 1,
                    2 * self.relation_ordinal,
                }
                for index in self.inferred_role_indices
            )
            or not self.signed_gap_interval_px.contains(
                self.canonical_signed_gap_px,
                epsilon=1.0e-9,
            )
            or self.state != expected_state
        ):
            raise ValueError("source-W topology fact is invalid")


@dataclass(frozen=True)
class SourceFrameWidthTopologyAssessment:
    """Selected-only proof that correlated-W inference keeps normal topology."""

    source_frame_width_authority_id: str
    state: EvidenceState
    facts: tuple[SourceFrameWidthTopologyFact, ...]
    failure_kind: SourceFrameWidthTopologyFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        expected_state = (
            EvidenceState.CONTRADICTED
            if any(item.state == EvidenceState.CONTRADICTED for item in self.facts)
            else EvidenceState.UNAVAILABLE
            if any(item.state == EvidenceState.UNAVAILABLE for item in self.facts)
            else EvidenceState.SUPPORTED
        )
        expected_failure = (
            SourceFrameWidthTopologyFailureKind.NORMAL_ADJACENCY_CONTRADICTED
            if expected_state == EvidenceState.CONTRADICTED
            else SourceFrameWidthTopologyFailureKind.NORMAL_ADJACENCY_UNRESOLVED
            if expected_state == EvidenceState.UNAVAILABLE
            else None
        )
        if (
            not self.source_frame_width_authority_id
            or tuple(item.relation_ordinal for item in self.facts)
            != tuple(sorted({item.relation_ordinal for item in self.facts}))
            or self.state != expected_state
            or self.failure_kind != expected_failure
            or (expected_state == EvidenceState.SUPPORTED) != (self.reason is None)
            or (self.reason is not None and not self.reason)
        ):
            raise ValueError("source-W topology assessment is invalid")


class PhaseCandidateProjectionOutcome(str, Enum):
    """How direct-role authority changed one bounded phase candidate."""

    UNCHANGED = "unchanged"
    DIRECT_SEPARATOR_REFIT = "direct_separator_refit"
    PROJECTED = "projected"
    CALIBRATED_NOMINAL_GRID = "calibrated_nominal_grid"
    DIRECT_ROLE_CONTRADICTION = "direct_role_contradiction"
    ADJACENCY_MATERIAL_CONFLICT = "adjacency_material_conflict"
    TOPOLOGY_BINDING_UNAVAILABLE = "topology_binding_unavailable"
    CALIBRATED_NOMINAL_GRID_UNAVAILABLE = (
        "calibrated_nominal_grid_unavailable"
    )
    CALIBRATED_NOMINAL_GRID_CONFLICT = (
        "calibrated_nominal_grid_conflict"
    )
    DIRECT_LATTICE_CONFLICT = "direct_lattice_conflict"
    NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE = (
        "nominal_grid_phase_anchor_unavailable"
    )
    REFIT_UNAVAILABLE = "refit_unavailable"
    DISCRETE_IDENTITY_CHANGED = "discrete_identity_changed"


class PhaseCandidateProjectionBasis(str, Enum):
    """Authority used after removing unavailable direct coordinates."""

    DIRECT_BINDINGS = "direct_bindings"
    DIRECT_SEPARATOR_GAP = "direct_separator_gap"
    DIRECT_RANK_THREE = "direct_rank_three"
    CALIBRATED_NOMINAL_GRID = "calibrated_nominal_grid"


@dataclass(frozen=True)
class PhaseCandidateProjectedBinding:
    """One unavailable coordinate retained only as candidate provenance."""

    role_index: int
    observation_id: ObservationId

    def __post_init__(self) -> None:
        if self.role_index < 0 or not isinstance(
            self.observation_id,
            ObservationId,
        ):
            raise ValueError("phase-candidate projected binding is invalid")


@dataclass(frozen=True)
class PhaseCandidateAuthorityProjection:
    """Typed removal of unavailable coordinates before phase competition."""

    input_direct_role_authority: DirectRoleBindingAuthority
    outcome: PhaseCandidateProjectionOutcome
    basis: PhaseCandidateProjectionBasis | None
    projected_out_bindings: tuple[PhaseCandidateProjectedBinding, ...]
    retained_direct_constraint_rank: int
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.input_direct_role_authority,
            DirectRoleBindingAuthority,
        ):
            raise TypeError("phase-candidate input authority is invalid")
        unavailable_bindings = tuple(
            PhaseCandidateProjectedBinding(
                role_index=item.role_index,
                observation_id=item.observation_id,
            )
            for item in self.input_direct_role_authority.facts
            if item.state == EvidenceState.UNAVAILABLE
        )
        eligible_basis = {
            PhaseCandidateProjectionOutcome.UNCHANGED: (
                PhaseCandidateProjectionBasis.DIRECT_BINDINGS
            ),
            PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT: (
                PhaseCandidateProjectionBasis.DIRECT_SEPARATOR_GAP
            ),
            PhaseCandidateProjectionOutcome.PROJECTED: (
                PhaseCandidateProjectionBasis.DIRECT_RANK_THREE
            ),
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID: (
                PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID
            ),
        }
        failed = self.outcome not in {
            PhaseCandidateProjectionOutcome.UNCHANGED,
            PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
            PhaseCandidateProjectionOutcome.PROJECTED,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        }
        canonical_bindings = tuple(
            sorted(
                set(self.projected_out_bindings),
                key=lambda item: (item.role_index, str(item.observation_id)),
            )
        )
        state = self.input_direct_role_authority.state
        state_matches_outcome = {
            EvidenceState.SUPPORTED: (
                self.outcome
                in {
                    PhaseCandidateProjectionOutcome.UNCHANGED,
                    PhaseCandidateProjectionOutcome.ADJACENCY_MATERIAL_CONFLICT,
                    PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
                    PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
                    PhaseCandidateProjectionOutcome
                    .CALIBRATED_NOMINAL_GRID_UNAVAILABLE,
                    PhaseCandidateProjectionOutcome
                    .CALIBRATED_NOMINAL_GRID_CONFLICT,
                    PhaseCandidateProjectionOutcome
                    .NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE,
                    PhaseCandidateProjectionOutcome
                    .TOPOLOGY_BINDING_UNAVAILABLE,
                    PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
                    PhaseCandidateProjectionOutcome
                    .DISCRETE_IDENTITY_CHANGED,
                }
            ),
            EvidenceState.CONTRADICTED: (
                self.outcome
                == PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION
            ),
            EvidenceState.UNAVAILABLE: (
                self.outcome
                not in {
                    PhaseCandidateProjectionOutcome.UNCHANGED,
                    PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
                }
            ),
        }[state]
        bindings_match_state = (
            self.projected_out_bindings == unavailable_bindings
            if state == EvidenceState.UNAVAILABLE
            else not self.projected_out_bindings
        )
        if (
            not isinstance(self.outcome, PhaseCandidateProjectionOutcome)
            or any(
                not isinstance(item, PhaseCandidateProjectedBinding)
                for item in self.projected_out_bindings
            )
            or canonical_bindings != self.projected_out_bindings
            or not 0 <= self.retained_direct_constraint_rank <= 3
            or self.basis != eligible_basis.get(self.outcome)
            or failed != (self.reason is not None)
            or self.reason is not None
            and not self.reason
            or not state_matches_outcome
            or not bindings_match_state
            or self.outcome == PhaseCandidateProjectionOutcome.PROJECTED
            and (
                not self.projected_out_bindings
                or self.retained_direct_constraint_rank != 3
            )
        ):
            raise ValueError("phase-candidate authority projection is invalid")

    @property
    def eligible(self) -> bool:
        return self.outcome in {
            PhaseCandidateProjectionOutcome.UNCHANGED,
            PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
            PhaseCandidateProjectionOutcome.PROJECTED,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        }


@dataclass(frozen=True)
class _TerminalPhaseDiagnostic:
    """One already generated failed mapping awaiting an empty Review slot."""

    fit: SequenceFit
    projection: PhaseCandidateAuthorityProjection

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fit, SequenceFit)
            or not isinstance(self.projection, PhaseCandidateAuthorityProjection)
            or self.projection.eligible
        ):
            raise ValueError("terminal phase diagnostic requires a failed projection")
        for fact in self.projection.input_direct_role_authority.facts:
            if (
                not 0 <= fact.role_index < len(self.fit.role_bindings)
                or self.fit.role_bindings[fact.role_index] is None
                or self.fit.role_bindings[fact.role_index].observation_id
                != fact.observation_id
            ):
                raise ValueError("terminal diagnostic projection lost its input mapping")


class NativeEndpointSelectionBasis(str, Enum):
    """Physical basis for a retained terminal-native phase explanation."""

    OUTER_MATERIAL_TERMINAL = "outer_material_terminal"
    INTRINSIC_TERMINAL = "intrinsic_terminal"


# Compiled Frame role offsets: START=0, END=1, in fixed SS, SE, ES, EE order.
NATIVE_ENDPOINT_ROLE_CLASSES = ((0, 0), (0, 1), (1, 0), (1, 1))
NATIVE_ENDPOINT_ROLE_CLASS_COUNT = len(NATIVE_ENDPOINT_ROLE_CLASSES)


class NativeEndpointGeometryBasis(str, Enum):
    """Distinct geometry contracts must not compete for one Review slot."""

    DIRECT_NATIVE = "direct_native"
    CALIBRATED_NOMINAL_GRID = "calibrated_nominal_grid"
    FAILED_INPUT = "failed_input"


NATIVE_ENDPOINT_GEOMETRY_BASES = tuple(NativeEndpointGeometryBasis)
NATIVE_PHASE_RETENTION_CLASS_COUNT = (
    NATIVE_ENDPOINT_ROLE_CLASS_COUNT * len(NATIVE_ENDPOINT_GEOMETRY_BASES)
)


def _validate_native_projection_fit_mapping(
    fit: SequenceFit,
    projection: PhaseCandidateAuthorityProjection,
) -> None:
    """Keep the effective fit attached to its exact input authority ledger."""

    facts = projection.input_direct_role_authority.facts
    facts_by_role: dict[int, object] = {}
    for fact in facts:
        role_index = fact.role_index
        if role_index in facts_by_role:
            raise ValueError("native projection authority repeats a role")
        if not 0 <= role_index < len(fit.role_bindings):
            raise ValueError("native projection authority role leaves its fit")
        binding = fit.role_bindings[role_index]
        if binding is None:
            if not projection.eligible or (
                role_index,
                fact.observation_id,
            ) not in {
                (item.role_index, item.observation_id)
                for item in projection.projected_out_bindings
            }:
                raise ValueError(
                    "native projection authority fact is absent from its fit"
                )
        elif binding.observation_id != fact.observation_id:
            raise ValueError(
                "native projection authority fact changed its fit identity"
            )
        facts_by_role[role_index] = fact

    for role_index, binding in enumerate(fit.role_bindings):
        if binding is None:
            continue
        fact = facts_by_role.get(role_index)
        if fact is None or fact.observation_id != binding.observation_id:
            raise ValueError(
                "native effective fit binding lacks its input authority fact"
            )

    if not projection.eligible and tuple(facts_by_role) != tuple(
        index for index, binding in enumerate(fit.role_bindings) if binding is not None
    ):
        raise ValueError(
            "failed native projection does not cover the complete input fit"
        )


@dataclass(frozen=True)
class NativeEndpointPhaseDiagnostic:
    """One projection record that retains both native terminal-frame proof sides.

    ``fit`` is the single effective fit chosen from a projection record.  The
    original projection remains attached so a failed projection cannot be
    mistaken for a supported phase explanation, and all authority facts stay
    available through its input ledger.
    """

    fit: SequenceFit
    projection: PhaseCandidateAuthorityProjection
    residual_compatible: bool
    terminal_role_indices: tuple[int, ...]
    selection_basis: NativeEndpointSelectionBasis
    geometry_basis: NativeEndpointGeometryBasis = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fit, SequenceFit)
            or not isinstance(self.projection, PhaseCandidateAuthorityProjection)
            or not isinstance(self.residual_compatible, bool)
            or not isinstance(self.selection_basis, NativeEndpointSelectionBasis)
            or tuple(sorted(set(self.terminal_role_indices)))
            != self.terminal_role_indices
            or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
                or index >= len(self.fit.role_bindings)
                for index in self.terminal_role_indices
            )
        ):
            raise ValueError("native endpoint phase diagnostic is invalid")

        _validate_native_projection_fit_mapping(self.fit, self.projection)
        object.__setattr__(self, "geometry_basis", (
            NativeEndpointGeometryBasis.FAILED_INPUT
            if not self.projection.eligible
            else NativeEndpointGeometryBasis.CALIBRATED_NOMINAL_GRID
            if self.fit.calibrated_nominal_grid_fit_state is not None
            else NativeEndpointGeometryBasis.DIRECT_NATIVE
        ))

        facts = self.projection.input_direct_role_authority.facts
        facts_by_identity = {
            (fact.role_index, fact.observation_id): fact
            for fact in facts
        }
        terminal_frame_roles = (
            tuple(self.fit.template.roles[:2])
            + tuple(self.fit.template.roles[-2:])
        )
        terminal_role_set = {
            role.role_index
            for role in terminal_frame_roles
        }
        qualifying_roles: set[int] = set()
        outer_roles: set[int] = set()
        for role_index in terminal_role_set:
            binding = self.fit.role_bindings[role_index]
            if binding is None:
                continue
            fact = facts_by_identity.get((role_index, binding.observation_id))
            if fact is None or not {
                DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                DirectRoleAuthorityBasis.AGGREGATE_UNION,
            }.intersection(fact.bases):
                continue
            qualifying_roles.add(role_index)
            if DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY in fact.bases:
                outer_roles.add(role_index)

        if (
            not qualifying_roles
            or self.terminal_role_indices != tuple(sorted(qualifying_roles))
            or not qualifying_roles.intersection(
                {role.role_index for role in terminal_frame_roles[:2]}
            )
            or not qualifying_roles.intersection(
                {role.role_index for role in terminal_frame_roles[-2:]}
            )
            or self.selection_basis
            != (
                NativeEndpointSelectionBasis.OUTER_MATERIAL_TERMINAL
                if outer_roles
                else NativeEndpointSelectionBasis.INTRINSIC_TERMINAL
            )
        ):
            raise ValueError(
                "native endpoint phase diagnostic lost terminal authority"
            )

    @property
    def rank(self) -> tuple[object, ...]:
        """Return the existing bounded candidate rank for this effective fit."""

        return _rank(_BoundFit(self.fit, self.residual_compatible))

    @property
    def selection_key(self) -> tuple[object, ...]:
        """Rank only within one geometry basis and terminal role class."""

        return (
            int(
                self.selection_basis
                == NativeEndpointSelectionBasis.OUTER_MATERIAL_TERMINAL
            ),
            *self.rank,
        )

    @property
    def role_class_memberships(self) -> tuple[int, ...]:
        """Return fixed SS, SE, ES, EE classes from the original terminal roles.

        Each compiled Frame has START then END. The same Frame can be both
        terminals when count is one; only its actual qualifying roles are used.
        """

        first_roles = self.fit.template.roles[:2]
        last_roles = self.fit.template.roles[-2:]
        return tuple(
            index
            for index, (first, last) in enumerate(NATIVE_ENDPOINT_ROLE_CLASSES)
            if first_roles[first].role_index in self.terminal_role_indices
            and last_roles[last].role_index in self.terminal_role_indices
        )

    @property
    def retention_class_memberships(self) -> tuple[int, ...]:
        offset = (
            NATIVE_ENDPOINT_GEOMETRY_BASES.index(self.geometry_basis)
            * NATIVE_ENDPOINT_ROLE_CLASS_COUNT
        )
        return tuple(offset + index for index in self.role_class_memberships)


@dataclass(frozen=True)
class NativePhaseRetention:
    """Twelve geometry/role representatives with complete-diagnostic deduplication.

    Each geometry basis has SS, SE, ES, EE. Diagnostics appear in the order of their
    first class reference. Counts describe producer operations; schema checks
    separately remain bounded by twelve complete records.
    """

    diagnostics: tuple[NativeEndpointPhaseDiagnostic, ...] = ()
    role_class_indices: tuple[int | None, ...] = (None,) * NATIVE_PHASE_RETENTION_CLASS_COUNT
    record_scan_count: int = 0
    fact_check_count: int = 0
    class_membership_count: int = 0
    class_comparison_count: int = 0
    carry_comparison_count: int = 0
    deduplication_comparison_count: int = 0
    peak_temporary_bytes: int = 0
    role_count: int = 0

    def __post_init__(self) -> None:
        receipt_values = (
            self.record_scan_count,
            self.fact_check_count,
            self.class_membership_count,
            self.class_comparison_count,
            self.carry_comparison_count,
            self.deduplication_comparison_count,
            self.peak_temporary_bytes,
            self.role_count,
        )
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(diagnostic, NativeEndpointPhaseDiagnostic)
            for diagnostic in self.diagnostics
        ):
            raise TypeError("native phase retention diagnostics are invalid")
        if len(self.diagnostics) > NATIVE_PHASE_RETENTION_CLASS_COUNT:
            raise ValueError("native phase retention exceeds twelve diagnostics")
        if (
            not isinstance(self.role_class_indices, tuple)
            or len(self.role_class_indices) != NATIVE_PHASE_RETENTION_CLASS_COUNT
        ):
            raise ValueError("native phase retention requires twelve geometry/role classes")
        referenced: set[int] = set()
        for role_class, index in enumerate(self.role_class_indices):
            if index is None:
                continue
            if type(index) is not int or not 0 <= index < len(self.diagnostics):
                raise ValueError("native phase retention class index is invalid")
            if role_class not in self.diagnostics[index].retention_class_memberships:
                raise ValueError("native phase retention invented a role class")
            if index not in referenced:
                if index != len(referenced):
                    raise ValueError("native phase retention changed first-class order")
                referenced.add(index)
        if len(referenced) != len(self.diagnostics):
            raise ValueError("native phase retention has an unreferenced diagnostic")
        for index, diagnostic in enumerate(self.diagnostics):
            if any(diagnostic == prior for prior in self.diagnostics[:index]):
                raise ValueError("native phase retention repeats a complete diagnostic")
            if diagnostic.fit.template != self.diagnostics[0].fit.template:
                raise ValueError("native phase retention mixed template identities")
            if any(self.role_class_indices[member] is None
                   for member in diagnostic.retention_class_memberships):
                raise ValueError("native phase retention lost a represented class")
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in receipt_values
        ):
            raise ValueError("native phase retention receipt is invalid")
        if self.record_scan_count == 0:
            if (
                self.diagnostics
                or any(value != 0 for value in receipt_values)
            ):
                raise ValueError("empty native phase retention receipt is invalid")
            return
        if self.role_count < 2 or self.role_count % 2:
            raise ValueError("native phase retention role bound is invalid")
        if self.fact_check_count > self.record_scan_count * self.role_count:
            raise ValueError("native phase retention fact bound is invalid")
        if (
            self.class_membership_count > 4 * self.record_scan_count
            or self.class_comparison_count > self.class_membership_count
            or self.class_membership_count < sum(
                index is not None for index in self.role_class_indices
            )
            or bool(self.diagnostics) != bool(self.class_membership_count)
        ):
            raise ValueError("native phase retention class work bound is invalid")
        if self.carry_comparison_count > NATIVE_PHASE_RETENTION_CLASS_COUNT * (self.record_scan_count - 1):
            raise ValueError("native phase retention carry bound is invalid")
        # A pool build uses at least one scanned record. A binary carry adds
        # one build; at most 2*M-1 builds therefore contribute at most 66
        # complete-identity comparisons each to an accumulated receipt.
        deduplication_bound = NATIVE_PHASE_RETENTION_CLASS_COUNT * (NATIVE_PHASE_RETENTION_CLASS_COUNT - 1) // 2
        if self.deduplication_comparison_count > deduplication_bound * (2 * self.record_scan_count - 1):
            raise ValueError("native phase retention deduplication bound is invalid")
        if any(self.role_count != len(item.fit.role_bindings) for item in self.diagnostics):
            raise ValueError("native phase retention diagnostic role bound is invalid")


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
    retained_proposal_basis: PhaseRetainedProposalBasis | None = None
    best_phase_candidate_authority_projection: (
        PhaseCandidateAuthorityProjection | None
    ) = None
    runner_phase_candidate_authority_projection: (
        PhaseCandidateAuthorityProjection | None
    ) = None
    eliminated_candidate_authority_projections: tuple[
        PhaseCandidateAuthorityProjection, ...
    ] = ()
    global_lattice_authority: GlobalLatticeAuthority | None = None
    calibrated_nominal_grid_evidence: (
        CalibratedNominalGridEvidence | None
    ) = None
    adjacency_observation_coverage: tuple[AdjacencyObservationCoverage, ...] = ()
    adjacency_continuity_observations: tuple[
        AdjacencyContinuityObservation, ...
    ] = ()
    direct_role_binding_authority: DirectRoleBindingAuthority | None = None
    outer_frame_observation_authority: (
        OuterFrameObservationAuthority | None
    ) = None
    source_frame_width_topology_assessment: (
        SourceFrameWidthTopologyAssessment | None
    ) = None
    retained_adjacency_assessments: tuple[PhaseCandidateAdjacencyAssessment, ...] = ()
    competition_scopes: tuple[PhaseCompetitionScope, ...] = ()
    competition_scope_evaluations: tuple[str, ...] = ()
    # Transient handoff, not a third retained/output candidate. The report
    # read model excludes private fields; if consumed, the original fit and
    # failed projection become the ordinary runner and are reported there.
    _terminal_diagnostic: _TerminalPhaseDiagnostic | None = field(
        default=None, repr=False, compare=False,
    )
    _native_phase_retention: NativePhaseRetention | None = field(
        default=None, repr=False, compare=False,
    )
    _source_clipped_phase_retention: SourceClippedPhaseRetention | None = field(
        default=None, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        from .template_source_clipped import SourceClippedPhaseRetention

        if self.competition_scopes:
            from .template_phase_membership import PhaseCompetitionScope, combine_phase_competition_scopes
            if (not isinstance(self.competition_scopes, tuple)
                    or any(not isinstance(scope, PhaseCompetitionScope)
                           or scope.template.template_id != self.template.template_id
                           for scope in self.competition_scopes)
                    or combine_phase_competition_scopes(self.competition_scopes, ()) != self.competition_scopes):
                raise ValueError("phase competition lost its complete producer scopes")
        elif not isinstance(self.competition_scopes, tuple):
            raise TypeError("phase competition scopes must be a tuple")
        by_scope = {scope.scope_id: scope for scope in self.competition_scopes}
        if (not isinstance(self.competition_scope_evaluations, tuple)
                or any(identity not in by_scope for identity in self.competition_scope_evaluations)
                or set(self.competition_scope_evaluations) != set(by_scope)
                or len(self.competition_scope_evaluations) != self.receipt.phase_producer_scope_count
                or sum(len(by_scope[identity].members) for identity in self.competition_scope_evaluations)
                != self.receipt.phase_producer_record_count):
            raise ValueError("phase competition omitted a producer scope or record evaluation")

        if (
            not isinstance(self.retained_adjacency_assessments, tuple)
            or any(not isinstance(item, PhaseCandidateAdjacencyAssessment) for item in self.retained_adjacency_assessments)
            or len(self.retained_adjacency_assessments) > 2
        ):
            raise ValueError("retained adjacency assessments exceed the fixed candidate bound")
        if self.retained_adjacency_assessments:
            retained = tuple(fit for fit in (self.best, self.runner_up) if fit is not None)
            if tuple(item.fit for item in self.retained_adjacency_assessments) != retained:
                raise ValueError("retained adjacency assessments lost their complete fit identities")
            if self.status == PhaseFitStatus.RESOLVED and self.retained_adjacency_assessments[0].state == EvidenceState.CONTRADICTED:
                raise ValueError("resolved phase carries registered adjacency counterevidence")
        source_retention = self._source_clipped_phase_retention
        if source_retention is not None:
            if not isinstance(source_retention, SourceClippedPhaseRetention):
                raise TypeError("source-clipped phase retention is invalid")
            if self.status == PhaseFitStatus.BOUND_EXCEEDED or (
                source_retention.record_scan_count
                and source_retention.template != self.template
            ):
                raise ValueError("source-clipped retention leaves its registered template")
            for source_diagnostic in source_retention.diagnostics:
                if source_diagnostic.fit.template != self.template or not {
                    identity
                    for identity in source_diagnostic.fit.binding_observation_ids
                    if identity is not None
                }.issubset(self.registered_direct_observation_ids):
                    raise ValueError("source-clipped retention escaped registered observations")
        diagnostic = self._terminal_diagnostic
        if diagnostic is not None and (
            not isinstance(diagnostic, _TerminalPhaseDiagnostic)
            or diagnostic.fit.template != self.template
            or not {
                identity for identity in diagnostic.fit.binding_observation_ids
                if identity is not None
            }.issubset(self.registered_direct_observation_ids)
        ):
            raise ValueError("terminal phase diagnostic leaves its registered template")
        native_retention = self._native_phase_retention
        if native_retention is not None and not isinstance(
            native_retention,
            NativePhaseRetention,
        ):
            raise TypeError("native phase retention is invalid")
        for native_diagnostic in (
            () if native_retention is None else native_retention.diagnostics
        ):
            native_fit = native_diagnostic.fit
            if (
                self.status == PhaseFitStatus.BOUND_EXCEEDED
                or native_fit.template != self.template
                or not {
                    identity
                    for identity in native_fit.binding_observation_ids
                    if identity is not None
                }.issubset(self.registered_direct_observation_ids)
            ):
                raise ValueError(
                    "native phase retention leaves its registered template"
                )
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
        if self.retained_proposal_basis is not None:
            calibrated = (
                self.best is not None
                and self.best.calibrated_nominal_grid_fit_state is not None
            )
            calibrated_bases = {
                PhaseRetainedProposalBasis
                .CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE,
                PhaseRetainedProposalBasis
                .CALIBRATED_NOMINAL_GRID_WITH_RESIDUAL_COUNTEREVIDENCE,
            }
            if (
                not isinstance(
                    self.retained_proposal_basis,
                    PhaseRetainedProposalBasis,
                )
                or self.status == PhaseFitStatus.RESOLVED
                or self.best is None
                or calibrated
                != (self.retained_proposal_basis in calibrated_bases)
            ):
                raise ValueError("retained phase proposal basis is invalid")
        if (
            self.best_phase_candidate_authority_projection is not None
            and not isinstance(
                self.best_phase_candidate_authority_projection,
                PhaseCandidateAuthorityProjection,
            )
        ):
            raise TypeError("best phase-candidate authority projection is invalid")
        if (
            self.runner_phase_candidate_authority_projection is not None
            and not isinstance(
                self.runner_phase_candidate_authority_projection,
                PhaseCandidateAuthorityProjection,
            )
        ):
            raise TypeError("runner phase-candidate authority projection is invalid")
        if (
            len(self.eliminated_candidate_authority_projections) > 2
            or any(
                not isinstance(item, PhaseCandidateAuthorityProjection)
                or item.outcome
                != PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION
                for item in self.eliminated_candidate_authority_projections
            )
        ):
            raise ValueError(
                "eliminated phase-candidate authority ledger is invalid"
            )
        if (
            self.best is None
            and self.best_phase_candidate_authority_projection is not None
            or self.runner_up is None
            and self.runner_phase_candidate_authority_projection is not None
        ):
            raise ValueError("phase-candidate assessment requires its candidate")
        if self.global_lattice_authority is not None and not isinstance(
            self.global_lattice_authority,
            GlobalLatticeAuthority,
        ):
            raise TypeError("phase global lattice authority is invalid")
        if (
            self.calibrated_nominal_grid_evidence is not None
            and not isinstance(
                self.calibrated_nominal_grid_evidence,
                CalibratedNominalGridEvidence,
            )
        ):
            raise TypeError("phase calibrated nominal Grid evidence is invalid")
        if self.calibrated_nominal_grid_evidence is not None and (
            self.best is None
            or self.best.calibrated_nominal_grid_fit_state is None
            or self.calibrated_nominal_grid_evidence.prior_id
            != self.best.calibrated_nominal_grid_fit_state.prior_id
            or self.calibrated_nominal_grid_evidence.phase_anchor_role_indices
            != self.best.calibrated_nominal_grid_fit_state.phase_anchor_role_indices
            or self.calibrated_nominal_grid_evidence.phase_anchor_observation_ids
            != self.best.calibrated_nominal_grid_fit_state.phase_anchor_observation_ids
        ):
            raise ValueError("phase nominal Grid evidence lost its fit state")
        if any(
            not isinstance(item, AdjacencyObservationCoverage)
            for item in self.adjacency_observation_coverage
        ):
            raise TypeError("phase adjacency observation coverage is invalid")
        if any(
            not isinstance(item, AdjacencyContinuityObservation)
            for item in self.adjacency_continuity_observations
        ):
            raise TypeError("phase adjacency continuity ledger is invalid")
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
        if (
            self.source_frame_width_topology_assessment is not None
            and not isinstance(
                self.source_frame_width_topology_assessment,
                SourceFrameWidthTopologyAssessment,
            )
        ):
            raise TypeError("phase source-W topology assessment is invalid")
        if self.adjacency_observation_coverage and tuple(
            item.relation_ordinal
            for item in self.adjacency_observation_coverage
        ) != tuple(range(1, self.template.count)):
            raise ValueError("phase adjacency coverage must follow template order")
        if self.adjacency_continuity_observations and tuple(
            item.relation_ordinal
            for item in self.adjacency_continuity_observations
        ) != tuple(range(1, self.template.count)):
            raise ValueError(
                "phase adjacency continuity must follow template order"
            )
        if bool(self.adjacency_continuity_observations) != bool(
            self.adjacency_observation_coverage
        ):
            raise ValueError(
                "phase adjacency continuity requires the coverage ledger"
            )


@dataclass(frozen=True)
class TemplatePhaseCandidateCompetition:
    """One discrete/local competition before placement-bound W is consumed."""

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
