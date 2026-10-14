"""Bounded sequence phase candidate model."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleLineEvidence,
)


_NUMERIC_RESIDUAL_PRECISION = 9
_NUMERIC_RESIDUAL_EPSILON_PX = 10.0 ** -_NUMERIC_RESIDUAL_PRECISION


@dataclass(frozen=True)
class _AnchorFact:
    observation_id: ObservationId
    evidence_group_id: ObservationId
    interval_px: FiniteInterval
    full_interval_px: FiniteInterval
    direct: bool
    support_fraction: float
    fit_residual_px: float
    line_evidence: SequenceRoleLineEvidence | None
    polarity: int
    qualified_anchor_roles: tuple[BoundaryRole, ...]
    source_spanning_direct_line: bool = False

    @property
    def coordinate_px(self) -> float:
        return self.interval_px.center


@dataclass(frozen=True)
class _BoundFit:
    fit: SequenceFit
    residual_compatible: bool


def _phase_residual_compatible(fit: SequenceFit) -> bool:
    """Assess this lattice, without counting local corrections as anchors."""

    residuals = tuple(
        abs(binding.canonical_position_px - canonical)
        for binding, canonical in zip(
            fit.role_bindings, fit.model_role_positions_px, strict=True
        )
        if binding is not None and binding.use == SequenceBindingUse.PHASE_ANCHOR
    )
    if not residuals:
        return False
    limit = max(2.0, fit.pitch_fit.canonical_frame_width_px * 0.015)
    # The physical limit is inclusive.  Absorb only LAPACK-scale numeric
    # error at the boundary, not an additional geometry tolerance.
    return sum(residuals) / len(residuals) <= limit + _NUMERIC_RESIDUAL_EPSILON_PX


@dataclass(frozen=True)
class _LocalRoleRefinement:
    fit: SequenceFit
    role_lookup_count: int
    binding_count: int


@dataclass(frozen=True)
class _PhaseSeed:
    """One discrete phase hypothesis and the direct fact that created it."""

    phase_px: float
    pitch_px: float
    required_bindings: tuple[tuple[int, ObservationId], ...] = ()
    adjacency_relations: tuple[AdjacencyRelation, ...] = ()

    def __post_init__(self) -> None:
        role_indices = tuple(item[0] for item in self.required_bindings)
        if (
            not math.isfinite(self.phase_px)
            or not math.isfinite(self.pitch_px)
            or self.pitch_px <= 0.0
            or any(index < 0 for index in role_indices)
            or len(set(role_indices)) != len(role_indices)
            or tuple(
                item.relation_ordinal for item in self.adjacency_relations
            )
            != tuple(range(1, len(self.adjacency_relations) + 1))
        ):
            raise ValueError("phase seed identity is invalid")
        duplicate_roles: dict[ObservationId, list[int]] = {}
        for role_index, observation_id in self.required_bindings:
            duplicate_roles.setdefault(observation_id, []).append(role_index)
        contacts = {
            item.shared_edge_observation_id: item
            for item in self.adjacency_relations
            if isinstance(item, ContactRelation)
        }
        for observation_id, indices in duplicate_roles.items():
            if len(indices) == 1:
                continue
            contact = contacts.get(observation_id)
            expected = (
                2 * contact.relation_ordinal - 1,
                2 * contact.relation_ordinal,
            ) if contact is not None else ()
            if tuple(sorted(indices)) != expected:
                raise ValueError(
                    "one seed observation may repeat only for one contact"
                )


def _interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("template interval must be numeric")


def _positive(value: PositiveInterval | FiniteInterval | float | int) -> PositiveInterval:
    interval = _interval(value)
    if interval.minimum <= 0.0:
        raise ValueError("template scale must be positive")
    return PositiveInterval(interval.minimum, interval.maximum)


def _rank(value: _BoundFit) -> tuple[object, ...]:
    fit = value.fit
    return (
        int(value.residual_compatible),
        fit.phase_support_count,
        fit.phase_support_coverage,
        # LAPACK-scale noise cannot reorder otherwise tied interpretations.
        -round(fit.residual_sum_px, _NUMERIC_RESIDUAL_PRECISION),
    )
