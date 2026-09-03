"""Read-only deviation ledger for one bounded template alignment."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval, ObservationId
from .model import BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_separator_support import resolve_separator_support
from .template_model import (
    AdjacencyRelation,
    FrameWidthInferenceAssessment,
    SequenceFit,
)
from .template_adjacency_coverage import AdjacencyObservationCoverage
from .template_adjacency_topology import AdjacencyContinuityObservation
from .template_direct_role_authority import DirectRoleBindingAuthority
from .template_outer_frame_authority import OuterFrameObservationAuthority
from .template_nominal_grid_model import CalibratedNominalGridEvidence
from .template_phase_model import (
    GlobalLatticeAuthority,
    PhaseFitResult,
    PhaseFitStatus,
)
from .template_residual import ResidualPattern


@dataclass(frozen=True)
class TemplateRoleResidual:
    """One indexed role compared with its bound role-free observation."""

    role_index: int
    lane_ordinal: int
    role: BoundaryRole
    theoretical_position_px: float
    observation_id: ObservationId | None
    observed_position_interval_px: FiniteInterval | None
    canonical_residual_px: float | None
    residual_interval_px: FiniteInterval | None

    def __post_init__(self) -> None:
        direct = self.observation_id is not None
        if (
            self.role_index < 0
            or self.lane_ordinal <= 0
            or self.role not in {BoundaryRole.START, BoundaryRole.END}
            or not math.isfinite(self.theoretical_position_px)
            or direct != (self.observed_position_interval_px is not None)
            or direct != (self.canonical_residual_px is not None)
            or direct != (self.residual_interval_px is not None)
            or (
                direct
                and (
                    not math.isfinite(float(self.canonical_residual_px))
                    or not self.residual_interval_px.contains(
                        float(self.canonical_residual_px), epsilon=1.0e-9
                    )
                )
            )
        ):
            raise ValueError("template role residual is invalid")


@dataclass(frozen=True)
class TemplateAlignmentDiagnostic:
    """Explain one fit without changing its placement or evidence authority."""

    template_id: str
    phase_status: PhaseFitStatus
    pattern: ResidualPattern
    absolute_phase_px: float | None
    canonical_pitch_px: float | None
    pitch_delta_from_compiled_center_px: float | None
    role_residuals: tuple[TemplateRoleResidual, ...]
    adjacency_relations: tuple[AdjacencyRelation, ...]
    global_lattice_authority: GlobalLatticeAuthority | None
    calibrated_nominal_grid_evidence: CalibratedNominalGridEvidence | None
    adjacency_observation_coverage: tuple[
        AdjacencyObservationCoverage, ...
    ]
    adjacency_continuity_observations: tuple[
        AdjacencyContinuityObservation, ...
    ]
    direct_role_binding_authority: DirectRoleBindingAuthority | None
    outer_frame_observation_authority: OuterFrameObservationAuthority | None
    frame_width_inference: FrameWidthInferenceAssessment | None
    unbound_direct_observation_ids: tuple[ObservationId, ...]
    incompatible_separator_support_ids: tuple[ObservationId, ...]
    maximum_absolute_role_residual_px: float | None
    unresolved_reason: str | None

    def __post_init__(self) -> None:
        fitted = self.absolute_phase_px is not None
        numeric = (
            self.absolute_phase_px,
            self.canonical_pitch_px,
            self.pitch_delta_from_compiled_center_px,
        )
        if (
            not self.template_id
            or fitted != all(value is not None for value in numeric)
            or any(value is not None and not math.isfinite(value) for value in numeric)
            or len(set(self.unbound_direct_observation_ids))
            != len(self.unbound_direct_observation_ids)
            or len(set(self.incompatible_separator_support_ids))
            != len(self.incompatible_separator_support_ids)
            or self.global_lattice_authority is not None
            and not isinstance(
                self.global_lattice_authority,
                GlobalLatticeAuthority,
            )
            or self.calibrated_nominal_grid_evidence is not None
            and not isinstance(
                self.calibrated_nominal_grid_evidence,
                CalibratedNominalGridEvidence,
            )
            or any(
                not isinstance(item, AdjacencyObservationCoverage)
                for item in self.adjacency_observation_coverage
            )
            or any(
                not isinstance(item, AdjacencyContinuityObservation)
                for item in self.adjacency_continuity_observations
            )
            or self.direct_role_binding_authority is not None
            and not isinstance(
                self.direct_role_binding_authority,
                DirectRoleBindingAuthority,
            )
            or self.outer_frame_observation_authority is not None
            and not isinstance(
                self.outer_frame_observation_authority,
                OuterFrameObservationAuthority,
            )
            or self.frame_width_inference is not None
            and not isinstance(
                self.frame_width_inference,
                FrameWidthInferenceAssessment,
            )
            or (self.pattern == ResidualPattern.NORMAL and self.adjacency_relations)
            or (
                self.pattern == ResidualPattern.MEASURED_RELATIONS
                and not self.adjacency_relations
            )
            or (self.pattern == ResidualPattern.UNRESOLVED)
            != (self.unresolved_reason is not None)
            or (
                self.maximum_absolute_role_residual_px is not None
                and (
                    not math.isfinite(self.maximum_absolute_role_residual_px)
                    or self.maximum_absolute_role_residual_px < 0.0
                )
            )
        ):
            raise ValueError("template alignment diagnostic is invalid")


def _residual_interval(
    observed: FiniteInterval,
    theoretical: float,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return FiniteInterval(
            observed.minimum - theoretical,
            observed.maximum - theoretical,
        )
    return FiniteInterval(
        theoretical - observed.maximum,
        theoretical - observed.minimum,
    )


def _role_residuals(
    fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
) -> tuple[TemplateRoleResidual, ...]:
    by_id = {item.observation_id: item for item in observations}
    if len(by_id) != len(observations):
        raise ValueError("alignment observations require unique identities")
    values: list[TemplateRoleResidual] = []
    for role, theoretical, observation_id in zip(
        fit.template.roles,
        fit.model_role_positions_px,
        fit.binding_observation_ids,
        strict=True,
    ):
        observation = None if observation_id is None else by_id.get(observation_id)
        if observation_id is not None and observation is None:
            raise ValueError("alignment fit references an unknown observation")
        interval = (
            None
            if observation is None
            else _residual_interval(
                observation.full_position_interval_px,
                theoretical,
                fit.template.direction,
            )
        )
        canonical = (
            None
            if observation is None
            else fit.template.direction
            * (observation.canonical_position_px - theoretical)
        )
        values.append(
            TemplateRoleResidual(
                role_index=role.role_index,
                lane_ordinal=role.lane_ordinal,
                role=role.role,
                theoretical_position_px=theoretical,
                observation_id=observation_id,
                observed_position_interval_px=(
                    None if observation is None else observation.full_position_interval_px
                ),
                canonical_residual_px=canonical,
                residual_interval_px=interval,
            )
        )
    return tuple(values)


def _incompatible_separator_supports(
    residuals: tuple[TemplateRoleResidual, ...],
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> tuple[ObservationId, ...]:
    """Find physical separators whose bound sides cannot share one shift."""

    support_by_edge = resolve_separator_support(
        observations,
        separator_bands
    ).edge_component_ids
    support_region_count: dict[ObservationId, int] = {}
    for band in separator_bands:
        support_id = support_by_edge.get(band.left_edge_observation_id)
        if support_id is None:
            continue
        support_region_count[support_id] = max(
            support_region_count.get(support_id, 0),
            band.material_support_region_count,
        )
    grouped: dict[ObservationId, list[FiniteInterval]] = {}
    for residual in residuals:
        if (
            residual.observation_id is None
            or residual.residual_interval_px is None
            or residual.observation_id not in support_by_edge
            or support_region_count[
                support_by_edge[residual.observation_id]
            ]
            < SPATIAL_SUPPORT_REGION_COUNT
        ):
            continue
        grouped.setdefault(
            support_by_edge[residual.observation_id],
            [],
        ).append(residual.residual_interval_px)
    incompatible: list[ObservationId] = []
    for support_id, intervals in grouped.items():
        if len(intervals) < 2:
            continue
        minimum = max(item.minimum for item in intervals)
        maximum = min(item.maximum for item in intervals)
        if maximum < minimum:
            incompatible.append(support_id)
    return tuple(sorted(incompatible, key=str))


def template_alignment_diagnostic(
    phase: PhaseFitResult,
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...] = (),
) -> TemplateAlignmentDiagnostic:
    """Derive one finite diagnostic ledger from already-registered evidence."""

    if not isinstance(phase, PhaseFitResult):
        raise TypeError("alignment diagnostic requires a phase fit result")
    fit = phase.best
    role_residuals = () if fit is None else _role_residuals(fit, observations)
    bound = {
        item.observation_id
        for item in role_residuals
        if item.observation_id is not None
    }
    unbound = tuple(
        identity
        for identity in phase.registered_direct_observation_ids
        if identity not in bound
    )
    residual_values = tuple(
        abs(float(item.canonical_residual_px))
        for item in role_residuals
        if item.canonical_residual_px is not None
    )
    incompatible = _incompatible_separator_supports(
        role_residuals,
        observations,
        separator_bands,
    )
    if phase.status != PhaseFitStatus.RESOLVED:
        pattern = ResidualPattern.UNRESOLVED
        reason = phase.ambiguity_reason or phase.status.value
    elif fit is not None and fit.adjacency_relations:
        pattern = ResidualPattern.MEASURED_RELATIONS
        reason = None
    else:
        pattern = ResidualPattern.NORMAL
        reason = None
    return TemplateAlignmentDiagnostic(
        template_id=phase.template.template_id,
        phase_status=phase.status,
        pattern=pattern,
        absolute_phase_px=(
            None if fit is None else fit.phase_lattice_fit.canonical_absolute_phase_px
        ),
        canonical_pitch_px=(
            None if fit is None else fit.pitch_fit.canonical_pitch_px
        ),
        pitch_delta_from_compiled_center_px=(
            None
            if fit is None
            else fit.pitch_fit.canonical_pitch_px
            - (
                phase.template.phase_lattice_authority.period_px.minimum
                + phase.template.phase_lattice_authority.period_px.maximum
            )
            / 2.0
        ),
        role_residuals=role_residuals,
        adjacency_relations=(
            () if fit is None else fit.adjacency_relations
        ),
        global_lattice_authority=phase.global_lattice_authority,
        calibrated_nominal_grid_evidence=(
            phase.calibrated_nominal_grid_evidence
        ),
        adjacency_observation_coverage=(
            phase.adjacency_observation_coverage
        ),
        adjacency_continuity_observations=(
            phase.adjacency_continuity_observations
        ),
        direct_role_binding_authority=(
            phase.direct_role_binding_authority
        ),
        outer_frame_observation_authority=(
            phase.outer_frame_observation_authority
        ),
        frame_width_inference=(
            None if fit is None else fit.frame_width_inference
        ),
        unbound_direct_observation_ids=unbound,
        incompatible_separator_support_ids=incompatible,
        maximum_absolute_role_residual_px=(
            None if not residual_values else max(residual_values)
        ),
        unresolved_reason=reason,
    )
