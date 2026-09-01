"""Prove independent closure of the fixed sequence lattice unknowns."""

from __future__ import annotations

from typing import Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import BoundaryRole
from .template_model import (
    OverlapRelation,
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceBindingUse,
    SequenceFit,
    SequenceRoleBinding,
    TemplateRole,
    adjacency_prefix_coefficients,
)
from .template_direct_role_authority import DirectRoleBindingAuthority
from .template_phase_model import (
    GlobalLatticeAuthority,
    GlobalLatticeAuthorityBasis,
    GlobalLatticeConstraint,
    GlobalLatticeConstraintKind,
    TemplatePhaseInput,
)


def _constraint_rank(rows: Sequence[tuple[float, float, float]]) -> int:
    """Return the exact rank of the fixed three-unknown system."""

    matrix = [list(map(float, row)) for row in rows]
    rank = 0
    for column in range(3):
        pivot = next(
            (
                index
                for index in range(rank, len(matrix))
                if abs(matrix[index][column]) > 1.0e-12
            ),
            None,
        )
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        divisor = matrix[rank][column]
        matrix[rank] = [value / divisor for value in matrix[rank]]
        for index, row in enumerate(matrix):
            if index == rank or abs(row[column]) <= 1.0e-12:
                continue
            factor = row[column]
            matrix[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    row,
                    matrix[rank],
                    strict=True,
                )
            ]
        rank += 1
        if rank == 3:
            break
    return rank


def _direct_role_rows(
    fit: SequenceFit,
    authorized_role_indices: set[int] | None,
) -> tuple[
    tuple[TemplateRole, SequenceRoleBinding, tuple[float, float, float]],
    ...,
]:
    by_evidence_group: dict[
        ObservationId,
        tuple[TemplateRole, SequenceRoleBinding, tuple[float, float, float]],
    ] = {}
    for role, binding in zip(
        fit.template.roles,
        fit.role_bindings,
        strict=True,
    ):
        if (
            binding is None
            or binding.use != SequenceBindingUse.PHASE_ANCHOR
            or authorized_role_indices is not None
            and role.role_index not in authorized_role_indices
        ):
            continue
        width_count, pitch_count, _fixed_delta = (
            adjacency_prefix_coefficients(
                fit.adjacency_relations,
                role.slot_index,
            )
        )
        value = (
            role,
            binding,
            (
                1.0,
                float(
                    fit.template.direction
                    * (width_count + int(role.role == BoundaryRole.END))
                ),
                float(fit.template.direction * pitch_count),
            ),
        )
        current = by_evidence_group.get(binding.evidence_group_id)
        if current is None or role.role_index < current[0].role_index:
            by_evidence_group[binding.evidence_group_id] = value
    return tuple(
        by_evidence_group[identity]
        for identity in sorted(by_evidence_group, key=str)
    )


def _direct_role_value_interval(
    fit: SequenceFit,
    role: TemplateRole,
    binding: SequenceRoleBinding,
) -> FiniteInterval:
    """Remove measured fixed-gap prefixes from one native role interval."""

    fixed_minimum = 0.0
    fixed_maximum = 0.0
    for relation in fit.adjacency_relations[: role.slot_index]:
        signed_gap = None
        if isinstance(relation, OverlapRelation):
            signed_gap = relation.signed_gap_interval_px
        elif (
            isinstance(relation, SeparatorRelation)
            and relation.kind != SeparatorRelationKind.NOMINAL
        ):
            signed_gap = relation.signed_gap_interval_px
        if signed_gap is None:
            continue
        fixed_minimum += signed_gap.minimum
        fixed_maximum += signed_gap.maximum
    if fit.template.direction > 0:
        offset = FiniteInterval(fixed_minimum, fixed_maximum)
    else:
        offset = FiniteInterval(-fixed_maximum, -fixed_minimum)
    position = binding.full_position_interval_px
    return FiniteInterval(
        position.minimum - offset.maximum,
        position.maximum - offset.minimum,
    )


def direct_role_constraint_rank(
    fit: SequenceFit,
    authorized_role_indices: Sequence[int] | None = None,
) -> int:
    """Return rank owned only by retained direct phase-anchor coordinates."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("direct-role rank requires a sequence fit")
    authorized = (
        None
        if authorized_role_indices is None
        else set(authorized_role_indices)
    )
    return _constraint_rank(
        tuple(
            coefficients
            for _role, _binding, coefficients in _direct_role_rows(
                fit,
                authorized,
            )
        )
    )


def assess_global_lattice_authority(
    fit: SequenceFit,
    phase_input: TemplatePhaseInput,
    *,
    direct_role_authority: DirectRoleBindingAuthority | None = None,
) -> GlobalLatticeAuthority:
    """Close ``phase``, ``W``, and ``pitch`` only from direct constraints."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("global lattice authority requires a sequence fit")
    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError("global lattice authority requires the exact phase input")
    if direct_role_authority is not None and not isinstance(
        direct_role_authority,
        DirectRoleBindingAuthority,
    ):
        raise TypeError("global lattice authority requires typed direct-role authority")
    authorized_role_indices = (
        None
        if direct_role_authority is None
        else set(direct_role_authority.supported_role_indices)
    )
    constraints: list[GlobalLatticeConstraint] = []
    role_rows: list[tuple[float, float, float]] = []
    role_ids: list[ObservationId] = []
    for role, binding, coefficients in _direct_role_rows(
        fit,
        authorized_role_indices,
    ):
        role_rows.append(coefficients)
        role_ids.append(binding.observation_id)
        constraints.append(
            GlobalLatticeConstraint(
                constraint_id=(
                    f"direct-role:{role.role_index}:"
                    f"{binding.observation_id}"
                ),
                kind=GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE,
                coefficients=coefficients,
                observation_ids=(binding.observation_id,),
                role_index=role.role_index,
                value_interval_px=_direct_role_value_interval(
                    fit,
                    role,
                    binding,
                ),
            )
        )
    direct_rank = _constraint_rank(role_rows)
    evidence = phase_input.global_lattice_evidence
    joint_rows = list(role_rows)
    if (
        phase_input.phase_authority_px is not None
        and evidence.phase_observation_ids
    ):
        coefficients = (1.0, 0.0, 0.0)
        joint_rows.append(coefficients)
        constraints.append(
            GlobalLatticeConstraint(
                constraint_id="registered:absolute-phase",
                kind=GlobalLatticeConstraintKind.ABSOLUTE_PHASE,
                coefficients=coefficients,
                observation_ids=evidence.phase_observation_ids,
                role_index=None,
                value_interval_px=phase_input.phase_authority_px,
            )
        )
    if evidence.frame_width_observation_ids:
        coefficients = (0.0, 1.0, 0.0)
        joint_rows.append(coefficients)
        constraints.append(
            GlobalLatticeConstraint(
                constraint_id="registered:frame-width",
                kind=GlobalLatticeConstraintKind.FRAME_WIDTH,
                coefficients=coefficients,
                observation_ids=evidence.frame_width_observation_ids,
                role_index=None,
                value_interval_px=None,
            )
        )
    if evidence.pitch_observation_ids:
        coefficients = (0.0, 0.0, 1.0)
        joint_rows.append(coefficients)
        constraints.append(
            GlobalLatticeConstraint(
                constraint_id="registered:source-pitch",
                kind=GlobalLatticeConstraintKind.SOURCE_PITCH,
                coefficients=coefficients,
                observation_ids=evidence.pitch_observation_ids,
                role_index=None,
                value_interval_px=None,
            )
        )
    joint_rank = _constraint_rank(joint_rows)
    closed = joint_rank == 3
    basis = (
        GlobalLatticeAuthorityBasis.DIRECT_ROLE_SYSTEM
        if direct_rank == 3
        else GlobalLatticeAuthorityBasis.COMPLEMENTARY_DIRECT_EVIDENCE
        if closed
        else None
    )
    return GlobalLatticeAuthority(
        state=(EvidenceState.SUPPORTED if closed else EvidenceState.UNAVAILABLE),
        direct_role_constraint_rank=direct_rank,
        joint_constraint_rank=joint_rank,
        constraints=tuple(constraints),
        role_observation_ids=tuple(role_ids),
        registered_evidence=evidence,
        basis=basis,
        reason=(
            None
            if closed
            else "direct evidence does not jointly close phase, W, and pitch"
        ),
    )


def direct_lattice_constraint_basis(
    authority: GlobalLatticeAuthority,
) -> tuple[GlobalLatticeConstraint, ...]:
    """Return one deterministic rank-three basis of direct role constraints."""

    if not isinstance(authority, GlobalLatticeAuthority):
        raise TypeError("direct lattice basis requires typed authority")
    if (
        authority.state != EvidenceState.SUPPORTED
        or authority.basis != GlobalLatticeAuthorityBasis.DIRECT_ROLE_SYSTEM
        or authority.direct_role_constraint_rank != 3
    ):
        return ()
    selected: list[GlobalLatticeConstraint] = []
    current_rank = 0
    for constraint in authority.constraints:
        if constraint.kind != GlobalLatticeConstraintKind.DIRECT_ROLE_COORDINATE:
            continue
        proposed = (*selected, constraint)
        proposed_rank = _constraint_rank(
            tuple(item.coefficients for item in proposed)
        )
        if proposed_rank <= current_rank:
            continue
        selected.append(constraint)
        current_rank = proposed_rank
        if current_rank == 3:
            break
    if len(selected) != 3:
        raise ValueError("supported direct lattice lacks a rank-three basis")
    return tuple(selected)


__all__ = [
    "assess_global_lattice_authority",
    "direct_lattice_constraint_basis",
    "direct_role_constraint_rank",
]
