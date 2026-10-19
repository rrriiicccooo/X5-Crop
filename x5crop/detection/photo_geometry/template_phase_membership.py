"""Immutable ledger records for one bounded phase-competition pass.

This module is deliberately a read-model boundary.  It records every input
candidate and its optional authority projection without selecting a winner,
granting output permission, or performing another fit or pixel query.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from collections.abc import Iterable, Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .template_nominal_grid_model import CalibratedNominalGridPrior
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    MAX_TEMPLATE_FIT_PASSES,
    OverlapRelation,
    SequenceBindingUse,
    SequenceFit,
    SeparatorRelation,
    TemplateSearchReceipt,
    TemplateSpec,
)
from .template_phase_model import (
    PhaseCandidateAuthorityProjection,
    _validate_native_projection_fit_mapping,
)
from .template_source_domain import PhaseSourceDomain


_LOGICAL_MEMBER_ROLE_BYTES = 128
_ADJACENCY_RELATION_TYPES = (SeparatorRelation, ContactRelation, OverlapRelation)


@dataclass(frozen=True)
class PhaseCompetitionInputContext:
    scale_px_per_mm: PositiveInterval | None
    sequence_measurement_query_ids: tuple[str, ...]
    calibrated_nominal_grid_prior: CalibratedNominalGridPrior | None
    max_observations: int
    contact_observation_ids: tuple[ObservationId, ...] = ()
    overlap_observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if (type(self.max_observations) is not int or self.max_observations <= 0
                or self.scale_px_per_mm is not None and not isinstance(self.scale_px_per_mm, PositiveInterval)
                or self.calibrated_nominal_grid_prior is not None
                and not isinstance(self.calibrated_nominal_grid_prior, CalibratedNominalGridPrior)
                or not isinstance(self.sequence_measurement_query_ids, tuple)
                or any(type(identity) is not str or not identity
                       for identity in self.sequence_measurement_query_ids)
                or len(set(self.sequence_measurement_query_ids)) != len(self.sequence_measurement_query_ids)):
            raise ValueError("phase producer input context is invalid")
        for identities in (self.contact_observation_ids, self.overlap_observation_ids):
            if (not isinstance(identities, tuple) or any(not isinstance(identity, ObservationId) for identity in identities)
                    or len(set(identities)) != len(identities)):
                raise ValueError("phase producer topology input identities are invalid")


def _strict_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool")


def _strict_int(value: object, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")


def _validate_relations(
    relations: object,
    template: TemplateSpec,
    *,
    name: str = "adjacency relations",
) -> tuple[AdjacencyRelation, ...]:
    if not isinstance(relations, tuple):
        raise TypeError(f"{name} must be a tuple")
    if any(not isinstance(item, _ADJACENCY_RELATION_TYPES) for item in relations):
        raise TypeError(f"{name} contains an untyped relation")
    if tuple(item.relation_ordinal for item in relations) != tuple(
        range(1, len(relations) + 1)
    ):
        raise ValueError(f"{name} ordinals must be contiguous")
    if len(relations) > max(0, template.count - 1):
        raise ValueError(f"{name} exceed the template adjacency count")
    return relations


def _validate_phase_anchor_ceiling(
    ceiling: tuple[tuple[int, ObservationId], ...] | None,
    template: TemplateSpec,
) -> tuple[tuple[int, ObservationId], ...] | None:
    if ceiling is None:
        return None
    if not isinstance(ceiling, tuple):
        raise TypeError("phase-anchor authority ceiling must be a tuple or None")
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or type(item[0]) is not int
        or not isinstance(item[1], ObservationId)
        for item in ceiling
    ):
        raise TypeError("phase-anchor authority ceiling entries are invalid")
    if (
        ceiling != tuple(sorted(set(ceiling)))
        or len({item[0] for item in ceiling}) != len(ceiling)
    ):
        raise ValueError("phase-anchor authority ceiling must be sorted and unique")
    if any(not 0 <= role_index < 2 * template.count for role_index, _ in ceiling):
        raise ValueError("phase-anchor authority ceiling leaves the template")
    return ceiling


def _fit_identity_is_preserved(input_fit: SequenceFit, output_fit: SequenceFit,
                               projected_out_roles: frozenset[int]) -> None:
    """Check the discrete identity the projection owner promises to preserve."""

    if output_fit.template != input_fit.template:
        raise ValueError("projected fit changed its template identity")
    if (
        output_fit.phase_lattice_fit.integer_slot_offset
        != input_fit.phase_lattice_fit.integer_slot_offset
    ):
        raise ValueError("projected fit changed its integer slot identity")
    input_bindings = input_fit.role_bindings
    output_bindings = output_fit.role_bindings
    if len(input_bindings) != len(output_bindings):
        raise ValueError("projected fit changed its role count")
    for role_index, input_binding in enumerate(input_bindings):
        if (
            input_binding is None
            or input_binding.use != SequenceBindingUse.PHASE_ANCHOR
            or role_index in projected_out_roles
        ):
            continue
        output_binding = output_bindings[role_index]
        if (
            output_binding is None
            or output_binding.observation_id != input_binding.observation_id
        ):
            raise ValueError("projected fit changed an original phase-anchor identity")


def _validate_projection_for_fit(
    input_fit: SequenceFit,
    projected_fit: SequenceFit | None,
    projection: PhaseCandidateAuthorityProjection,
) -> None:
    if not isinstance(projection, PhaseCandidateAuthorityProjection):
        raise TypeError("phase competition projection must be typed")

    # The current projection owner validates the complete authority ledger.  A
    # second explicit identity check here prevents a projection record from
    # being detached from its input fit by a later dataclass replacement.
    _validate_native_projection_fit_mapping(input_fit, projection)
    facts = projection.input_direct_role_authority.facts
    input_role_ids = tuple(
        (role_index, binding.observation_id)
        for role_index, binding in enumerate(input_fit.role_bindings)
        if binding is not None
    )
    authority_role_ids = tuple(
        (fact.role_index, fact.observation_id) for fact in facts
    )
    if authority_role_ids != tuple(sorted(authority_role_ids)):
        raise ValueError("projection authority roles are not sorted")
    if authority_role_ids != input_role_ids:
        raise ValueError("projection authority does not cover the complete input fit")

    if projection.eligible:
        if projected_fit is None:
            raise ValueError("eligible projection must retain an output fit")
        # Removal provenance belongs to the typed projection owner. A
        # contradicted input may also contain unavailable coordinates, without
        # attempting to remove them from an output that does not exist.
        projected_out_roles = {item.role_index for item in projection.projected_out_bindings}
        _fit_identity_is_preserved(input_fit, projected_fit, frozenset(projected_out_roles))
        if any(
            projected_fit.role_bindings[role_index] is not None
            for role_index in projected_out_roles
        ):
            raise ValueError("projected output retained an unavailable role")
    elif projected_fit is not None:
        raise ValueError("failed projection cannot retain an output fit")


@dataclass(frozen=True)
class PhaseCompetitionMember:
    """One complete raw candidate and its optional projection record."""

    record_ordinal: int
    input_fit: SequenceFit
    projected_fit: SequenceFit | None
    projection: PhaseCandidateAuthorityProjection | None
    input_residual_compatible: bool
    projected_residual_compatible: bool | None
    holder_admitted: bool
    source_terminal_role_indices: tuple[int, ...]
    phase_anchor_ceiling_satisfied: bool
    source_domain_admitted: bool | None = None

    def __post_init__(self) -> None:
        if self.source_domain_admitted is not None:
            _strict_bool(self.source_domain_admitted, "source domain admission")
        _strict_int(self.record_ordinal, "phase competition record ordinal")
        if self.record_ordinal < 0:
            raise ValueError("phase competition record ordinal must be non-negative")
        if not isinstance(self.input_fit, SequenceFit):
            raise TypeError("phase competition input fit must be typed")
        if self.projected_fit is not None and not isinstance(self.projected_fit, SequenceFit):
            raise TypeError("phase competition projected fit must be typed")
        if self.projection is not None and not isinstance(
            self.projection, PhaseCandidateAuthorityProjection
        ):
            raise TypeError("phase competition projection must be typed")
        for value, name in (
            (self.input_residual_compatible, "input residual compatibility"),
            (self.holder_admitted, "holder admission"),
            (self.phase_anchor_ceiling_satisfied, "phase-anchor ceiling status"),
        ):
            _strict_bool(value, name)
        if self.projected_residual_compatible is not None:
            _strict_bool(
                self.projected_residual_compatible,
                "projected residual compatibility",
            )
        if not isinstance(self.source_terminal_role_indices, tuple):
            raise TypeError("source terminal role indices must be a tuple")
        if any(
            type(index) is not int
            for index in self.source_terminal_role_indices
        ):
            raise TypeError("source terminal role indices must contain integers")
        if (
            tuple(sorted(set(self.source_terminal_role_indices)))
            != self.source_terminal_role_indices
        ):
            raise ValueError("source terminal role indices must be sorted and unique")
        if any(
            index < 0 or index >= len(self.input_fit.role_bindings)
            for index in self.source_terminal_role_indices
        ):
            raise ValueError("source terminal role index leaves the input fit")

        projection_executed = self.projection is not None
        if not projection_executed and (
            self.projected_fit is not None
            or self.projected_residual_compatible is not None
        ):
            raise ValueError("an unprojected record cannot carry output state")
        if projection_executed:
            assert self.projection is not None
            _validate_projection_for_fit(
                self.input_fit,
                self.projected_fit,
                self.projection,
            )
            if self.projection.eligible != (self.projected_fit is not None):
                raise ValueError("projection eligibility and output fit disagree")
            if self.projection.eligible != (
                self.projected_residual_compatible is not None
            ):
                raise ValueError(
                    "projection eligibility and output residual state disagree"
                )


def _scope_identity_repr(
    template: TemplateSpec,
    phase_authority_px: FiniteInterval | None,
    holder_span_px: FiniteInterval | None,
    source_domain: PhaseSourceDomain | None,
    adjacency_relations: tuple[AdjacencyRelation, ...],
    phase_anchor_authority_ceiling: tuple[tuple[int, ObservationId], ...] | None,
    projection_evaluated: bool,
    bound_exceeded: bool,
    receipt: TemplateSearchReceipt,
    members: tuple[PhaseCompetitionMember, ...],
    input_context: PhaseCompetitionInputContext | None,
) -> str:
    """Return a deterministic repr of the complete frozen scope tuple."""

    return repr(
        (
            template,
            phase_authority_px,
            holder_span_px,
            source_domain,
            adjacency_relations,
            phase_anchor_authority_ceiling,
            projection_evaluated,
            bound_exceeded,
            receipt,
            members,
            input_context,
        )
    )


def _deterministic_scope_id(
    template: TemplateSpec,
    phase_authority_px: FiniteInterval | None,
    holder_span_px: FiniteInterval | None,
    source_domain: PhaseSourceDomain | None,
    adjacency_relations: tuple[AdjacencyRelation, ...],
    phase_anchor_authority_ceiling: tuple[tuple[int, ObservationId], ...] | None,
    projection_evaluated: bool,
    bound_exceeded: bool,
    receipt: TemplateSearchReceipt,
    members: tuple[PhaseCompetitionMember, ...],
    input_context: PhaseCompetitionInputContext | None,
) -> str:
    digest = sha256(
        _scope_identity_repr(
            template,
            phase_authority_px,
            holder_span_px,
            source_domain,
            adjacency_relations,
            phase_anchor_authority_ceiling,
            projection_evaluated,
            bound_exceeded,
            receipt,
            members,
            input_context,
        ).encode("utf-8")
    ).hexdigest()
    return f"phase-competition-scope:{digest}"


@dataclass(frozen=True)
class PhaseCompetitionScope:
    """One bounded pass of the complete phase-competition member ledger."""

    scope_id: str
    template: TemplateSpec
    phase_authority_px: FiniteInterval | None
    holder_span_px: FiniteInterval | None
    source_domain: PhaseSourceDomain | None
    adjacency_relations: tuple[AdjacencyRelation, ...]
    phase_anchor_authority_ceiling: tuple[tuple[int, ObservationId], ...] | None
    projection_evaluated: bool
    bound_exceeded: bool
    receipt: TemplateSearchReceipt
    members: tuple[PhaseCompetitionMember, ...]
    input_context: PhaseCompetitionInputContext | None = None

    def __post_init__(self) -> None:
        if self.input_context is not None and not isinstance(self.input_context, PhaseCompetitionInputContext):
            raise TypeError("phase producer input context must be typed")
        if not isinstance(self.scope_id, str):
            raise TypeError("phase competition scope identity must be a string")
        if not self.scope_id:
            raise ValueError("phase competition scope identity must be non-empty")
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("phase competition scope template must be typed")
        for value, name in (
            (self.phase_authority_px, "phase authority"),
            (self.holder_span_px, "holder span"),
        ):
            if value is not None and not isinstance(value, FiniteInterval):
                raise TypeError(f"phase competition {name} must be a finite interval")
        if self.source_domain is not None and not isinstance(self.source_domain, PhaseSourceDomain):
            raise TypeError("phase competition source domain must be typed")
        relations = _validate_relations(self.adjacency_relations, self.template)
        ceiling = _validate_phase_anchor_ceiling(
            self.phase_anchor_authority_ceiling,
            self.template,
        )
        _strict_bool(self.projection_evaluated, "projection evaluated")
        _strict_bool(self.bound_exceeded, "phase competition bound status")
        if not isinstance(self.receipt, TemplateSearchReceipt):
            raise TypeError("phase competition receipt must be typed")
        if not isinstance(self.members, tuple):
            raise TypeError("phase competition members must be a tuple")
        if any(not isinstance(item, PhaseCompetitionMember) for item in self.members):
            raise TypeError("phase competition member ledger contains an untyped record")
        if tuple(item.record_ordinal for item in self.members) != tuple(range(len(self.members))):
            raise ValueError("phase competition member ordinals must be exactly zero-based")
        if self.receipt.role_count != len(self.template.roles):
            raise ValueError("phase receipt role count disagrees with the template")
        if self.receipt.adjacency_relation_evaluation_count != len(relations):
            raise ValueError("phase receipt adjacency count disagrees with the scope")
        seed_count = self.receipt.phase_hypothesis_count
        seed_bound = self.receipt.observation_count * max(6, self.receipt.role_count)
        if not self.bound_exceeded:
            if seed_count > seed_bound:
                raise ValueError("phase seed count exceeds its structural bound")
            if len(self.members) > seed_count:
                raise ValueError("phase member count exceeds the original seed count")
            self.receipt.validate_bounds(
                slot_count=self.template.count,
                max_fit_passes=MAX_TEMPLATE_FIT_PASSES,
            )
        elif self.members:
            raise ValueError("bound-exceeded phase scope cannot retain a usable prefix")
        if self.bound_exceeded and self.projection_evaluated:
            raise ValueError("bound-exceeded phase scope cannot claim projection completion")
        projection_count = self.receipt.candidate_direct_role_projection_evaluation_count
        if self.projection_evaluated:
            if len(self.members) != projection_count:
                raise ValueError("projected scope member count must equal projection evaluations")
            if any(item.projection is None for item in self.members):
                raise ValueError("projected scope contains an unprojected member")
        elif projection_count != 0:
            raise ValueError("unprojected scope carries projection evaluations")
        if any(
            item.input_fit.template != self.template
            or item.projected_fit is not None
            and item.projected_fit.template != self.template
            for item in self.members
        ):
            raise ValueError("phase member fit leaves the complete scope identity")
        expected_id = _deterministic_scope_id(
            self.template,
            self.phase_authority_px,
            self.holder_span_px,
            self.source_domain,
            relations,
            ceiling,
            self.projection_evaluated,
            self.bound_exceeded,
            self.receipt,
            self.members,
            self.input_context,
        )
        if self.scope_id != expected_id:
            raise ValueError("phase competition scope identity does not match complete contents")

    @property
    def retained_bytes(self) -> int:
        """Logical receipt accounting for retained member references.

        This is a deterministic ``O(MR)`` ledger estimate, where ``M`` is
        retained member count and ``R`` is template role count.  It is not a
        process-memory measurement.
        """

        return _LOGICAL_MEMBER_ROLE_BYTES * len(self.members) * len(self.template.roles)


def build_phase_competition_scope(
    template: TemplateSpec,
    phase_authority_px: FiniteInterval | None,
    holder_span_px: FiniteInterval | None,
    source_domain: PhaseSourceDomain | None,
    adjacency_relations: tuple[AdjacencyRelation, ...],
    phase_anchor_authority_ceiling: tuple[tuple[int, ObservationId], ...] | None,
    projection_evaluated: bool,
    bound_exceeded: bool,
    receipt: TemplateSearchReceipt,
    members: tuple[PhaseCompetitionMember, ...],
    input_context: PhaseCompetitionInputContext | None = None,
) -> PhaseCompetitionScope:
    """Build a scope with an identity bound to every physical ledger field."""

    scope_id = _deterministic_scope_id(
        template,
        phase_authority_px,
        holder_span_px,
        source_domain,
        adjacency_relations,
        phase_anchor_authority_ceiling,
        projection_evaluated,
        bound_exceeded,
        receipt,
        members,
        input_context,
    )
    return PhaseCompetitionScope(
        scope_id,
        template,
        phase_authority_px,
        holder_span_px,
        source_domain,
        adjacency_relations,
        phase_anchor_authority_ceiling,
        projection_evaluated,
        bound_exceeded,
        receipt,
        members,
        input_context,
    )


def _scope_tuple(
    value: PhaseCompetitionScope | Iterable[PhaseCompetitionScope],
) -> tuple[PhaseCompetitionScope, ...]:
    if isinstance(value, PhaseCompetitionScope):
        return (value,)
    if isinstance(value, (str, bytes)):
        raise TypeError("phase competition scopes must be typed records")
    result = tuple(value)
    if any(not isinstance(item, PhaseCompetitionScope) for item in result):
        raise TypeError("phase competition scope collection contains an untyped record")
    return result


def combine_phase_competition_scopes(
    current: PhaseCompetitionScope | Sequence[PhaseCompetitionScope],
    prior: PhaseCompetitionScope | Sequence[PhaseCompetitionScope],
) -> tuple[PhaseCompetitionScope, ...]:
    """Combine pass scopes by exact scope equality only.

    The current scopes retain their order and object identity.  A prior scope
    is removed only when the complete frozen scope compares equal; projected
    geometry is never used as a deduplication key.
    """

    current_scopes = _scope_tuple(current)
    prior_scopes = _scope_tuple(prior)
    combined: list[PhaseCompetitionScope] = []
    for scope in (*current_scopes, *prior_scopes):
        if scope not in combined:
            combined.append(scope)
    if len(combined) > MAX_TEMPLATE_FIT_PASSES:
        raise ValueError("phase competition scope count exceeds the fixed pass bound")
    return tuple(combined)


__all__ = [
    "MAX_TEMPLATE_FIT_PASSES",
    "PhaseCompetitionMember",
    "PhaseCompetitionScope",
    "build_phase_competition_scope",
    "combine_phase_competition_scopes",
]
