"""Read-only deviation ledger for one bounded template alignment."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...domain import FiniteInterval, ObservationId
from .model import BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_evidence import separator_support_authority
from .template_model import (
    MAX_LOCAL_ADVANCE_ANOMALIES,
    LocalAdvanceRelation,
    SequenceFit,
)
from .template_phase_model import (
    PhaseFailureKind,
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
    local_advance_relations: tuple[LocalAdvanceRelation, ...]
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
            or (self.pattern == ResidualPattern.NORMAL and self.local_advance_relations)
            or (
                self.pattern == ResidualPattern.LOCAL_STEP
                and not any(item.is_anomaly for item in self.local_advance_relations)
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
        fit.canonical_role_positions_px,
        fit.role_observation_ids,
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
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> tuple[ObservationId, ...]:
    """Find physical separators whose bound sides cannot share one shift."""

    support_by_edge = separator_support_authority(separator_bands)
    support_region_count: dict[ObservationId, int] = {}
    for band in separator_bands:
        support_id = support_by_edge.get(band.left_edge_observation_id)
        if support_id is None:
            raise ValueError("separator band has no physical support identity")
        support_region_count[support_id] = max(
            support_region_count.get(support_id, 0),
            band.independent_support_region_count,
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
        identity for identity in phase.direct_observation_ids if identity not in bound
    )
    residual_values = tuple(
        abs(float(item.canonical_residual_px))
        for item in role_residuals
        if item.canonical_residual_px is not None
    )
    incompatible = _incompatible_separator_supports(
        role_residuals,
        separator_bands,
    )
    if phase.status != PhaseFitStatus.RESOLVED:
        pattern = ResidualPattern.UNRESOLVED
        reason = phase.ambiguity_reason or phase.status.value
    elif len(incompatible) > MAX_LOCAL_ADVANCE_ANOMALIES:
        pattern = ResidualPattern.UNRESOLVED
        reason = (
            "multiple independent separator residuals contradict one "
            "global template"
        )
    elif fit is not None and any(
        relation.is_anomaly for relation in fit.local_advance_relations
    ):
        pattern = ResidualPattern.LOCAL_STEP
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
        local_advance_relations=(
            () if fit is None else fit.local_advance_relations
        ),
        unbound_direct_observation_ids=unbound,
        incompatible_separator_support_ids=incompatible,
        maximum_absolute_role_residual_px=(
            None if not residual_values else max(residual_values)
        ),
        unresolved_reason=reason,
    )


def enforce_template_alignment(
    phase: PhaseFitResult,
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> PhaseFitResult:
    """Apply only the negative residual-shape verdict to a finished fit."""

    diagnostic = template_alignment_diagnostic(
        phase,
        observations,
        separator_bands,
    )
    if (
        phase.status != PhaseFitStatus.RESOLVED
        or diagnostic.pattern != ResidualPattern.UNRESOLVED
    ):
        return phase
    return replace(
        phase,
        status=PhaseFitStatus.UNRESOLVED,
        ambiguity_reason=diagnostic.unresolved_reason,
        failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
        winner_basis=None,
    )


__all__ = [
    "TemplateAlignmentDiagnostic",
    "TemplateRoleResidual",
    "enforce_template_alignment",
    "template_alignment_diagnostic",
]
