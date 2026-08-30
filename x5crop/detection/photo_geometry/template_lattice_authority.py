"""Prove independent closure of the fixed sequence lattice unknowns."""

from __future__ import annotations

from typing import Sequence

from ...domain import EvidenceState, ObservationId
from .model import BoundaryRole
from .template_model import SequenceBindingUse, SequenceFit
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


def assess_global_lattice_authority(
    fit: SequenceFit,
    phase_input: TemplatePhaseInput,
) -> GlobalLatticeAuthority:
    """Close ``phase``, ``W``, and ``pitch`` only from direct constraints."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("global lattice authority requires a sequence fit")
    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError("global lattice authority requires the exact phase input")
    constraints: list[GlobalLatticeConstraint] = []
    role_rows: list[tuple[float, float, float]] = []
    role_ids: list[ObservationId] = []
    for role, binding in zip(
        fit.template.roles,
        fit.role_bindings,
        strict=True,
    ):
        if binding is None or binding.use != SequenceBindingUse.PHASE_ANCHOR:
            continue
        coefficients = (
            1.0,
            (
                float(fit.template.direction)
                if role.role == BoundaryRole.END
                else 0.0
            ),
            float(fit.template.direction * role.slot_index),
        )
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


__all__ = ["assess_global_lattice_authority"]
