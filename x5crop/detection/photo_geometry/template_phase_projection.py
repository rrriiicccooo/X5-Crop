"""Bounded sequence phase projection."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .interval_math import intersect, scale, subtract
from .template_model import (
    AdjacencyRelation,
    LatticeParameterFitBasis,
    PhaseLatticeFit,
    PitchFit,
    SeparatorRelation,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleBinding,
    TemplateRole,
    TemplateSpec,
    adjacency_relation_evidence_identity,
    adjacency_relation_required_bindings,
    realize_adjacency_relations_at_role_positions,
)
from .template_nominal_grid_authority import (
    NominalGridInfeasibleError,
    NominalGridRoleConstraint,
    solve_calibrated_nominal_grid_envelope,
)
from .template_nominal_grid_model import CalibratedNominalGridPrior
from .template_direct_role_authority import (
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from .template_lattice_authority import direct_role_constraint_rank
from .template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseCandidateProjectedBinding,
)
from . import (
    template_phase_candidate_model as _candidate_model,
    template_phase_fitting as _fitting,
)


def _interval_hull(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval:
    return FiniteInterval(
        min(left.minimum, right.minimum),
        max(left.maximum, right.maximum),
    )


def _fit_calibrated_nominal_grid_candidate(
    candidate: _candidate_model._BoundFit,
    *,
    prior: CalibratedNominalGridPrior,
    retained_facts: tuple[DirectRoleAuthorityFact, ...],
    registered_facts: tuple[_candidate_model._AnchorFact, ...],
    template: TemplateSpec,
    relations: tuple[AdjacencyRelation, ...],
    phase_authority: FiniteInterval | None,
    retained_direct_constraint_rank: int,
) -> _candidate_model._BoundFit | None:
    """Refit one existing discrete mapping against the calibrated Grid."""

    retained_ids = {item.observation_id for item in retained_facts}
    registered_by_id = {item.observation_id: item for item in registered_facts}
    if not retained_ids or any(identity not in registered_by_id for identity in retained_ids):
        return None
    retained_by_role = {item.role_index: item for item in retained_facts}
    # A feasible Grid cannot authorize native Frame widths outside the full
    # compiled physical range. Native departures stay independent of Grid W;
    # only a disjoint complete interval is a contradiction.
    for start_index in range(0, len(candidate.fit.role_bindings), 2):
        end_index = start_index + 1
        if start_index not in retained_by_role or end_index not in retained_by_role:
            continue
        start, end = candidate.fit.role_bindings[start_index:end_index + 1]
        if start is None or end is None:
            raise ValueError("nominal Grid projection lost its native Frame pair")
        native_width = scale(
            subtract(end.full_position_interval_px, start.full_position_interval_px),
            template.direction,
        )
        if intersect(native_width, template.frame_width_px) is None:
            return None
    phase_facts = tuple(
        item
        for item in retained_facts
        if candidate.fit.role_bindings[item.role_index] is not None
        and candidate.fit.role_bindings[item.role_index].use
        == SequenceBindingUse.PHASE_ANCHOR
    )
    if not phase_facts:
        return None
    constraints = tuple(
        NominalGridRoleConstraint(
            role_index=item.role_index,
            observation_id=item.observation_id,
            coordinate_px=registered_by_id[item.observation_id].coordinate_px,
            full_interval_px=registered_by_id[item.observation_id].full_interval_px,
        )
        for item in phase_facts
    )
    try:
        envelope, fit_state = solve_calibrated_nominal_grid_envelope(
            prior=prior,
            template=template,
            integer_slot_offset=(
                candidate.fit.phase_lattice_fit.integer_slot_offset
            ),
            role_constraints=constraints,
            relations=relations,
            phase_authority_px=phase_authority,
            retained_direct_constraint_rank=retained_direct_constraint_rank,
        )
    except NominalGridInfeasibleError:
        return None

    role_bindings: list[SequenceRoleBinding | None] = []
    role_intervals: list[FiniteInterval] = []
    role_full_intervals: list[FiniteInterval] = []
    for role_index, nominal_interval in enumerate(envelope.role_intervals_px):
        fact = retained_by_role.get(role_index)
        if fact is None:
            binding = None
            role_interval = nominal_interval
            full_interval = nominal_interval
        else:
            binding = candidate.fit.role_bindings[role_index]
            if binding is None or binding.observation_id != fact.observation_id:
                raise ValueError(
                    "nominal Grid projection lost its discrete role binding"
                )
            role_interval = _interval_hull(
                nominal_interval,
                binding.fit_position_interval_px,
            )
            full_interval = _interval_hull(
                nominal_interval,
                binding.full_position_interval_px,
            )
        role_bindings.append(binding)
        role_intervals.append(role_interval)
        role_full_intervals.append(full_interval)

    bound_direct_ids = tuple(
        dict.fromkeys(
            binding.observation_id
            for binding in role_bindings
            if binding is not None
        )
    )
    phase_direct_ids = tuple(
        dict.fromkeys(
            binding.observation_id
            for binding in role_bindings
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        )
    )
    support_by_location: dict[int, float] = {}
    for fact in retained_facts:
        binding = role_bindings[fact.role_index]
        if (
            binding is None
            or binding.use != SequenceBindingUse.PHASE_ANCHOR
        ):
            continue
        anchor = registered_by_id[fact.observation_id]
        location = (fact.role_index + 1) // 2
        support_by_location[location] = max(
            support_by_location.get(location, 0.0),
            anchor.support_fraction,
        )
    relations = realize_adjacency_relations_at_role_positions(
        relations,
        model_role_positions_px=envelope.role_positions_px,
        direction=template.direction,
        frame_width_px=envelope.canonical_frame_width_px,
        pitch_px=envelope.canonical_pitch_px,
    )
    if not (
        0.0 <= envelope.canonical_cycle_phase_px
        < envelope.canonical_pitch_px
    ):
        # A canonical point on the half-open cycle boundary belongs to the
        # adjacent integer slot.  Changing that offset would change the fixed
        # discrete identity, so this candidate is unavailable rather than
        # silently renormalized.
        return None
    fit = SequenceFit(
        template=template,
        phase_lattice_fit=PhaseLatticeFit(
            authority=template.phase_lattice_authority,
            cycle_phase_interval_px=envelope.cycle_phase_interval_px,
            canonical_cycle_phase_px=envelope.canonical_cycle_phase_px,
            integer_slot_offset=(
                candidate.fit.phase_lattice_fit.integer_slot_offset
            ),
            canonical_period_px=envelope.canonical_pitch_px,
            absolute_phase_interval_px=envelope.absolute_phase_interval_px,
            canonical_absolute_phase_px=envelope.canonical_absolute_phase_px,
            direction=template.direction,
        ),
        pitch_fit=PitchFit(
            frame_width_px=envelope.frame_width_interval_px,
            gap_interval_px=envelope.gap_interval_px,
            pitch_interval_px=envelope.pitch_interval_px,
            canonical_frame_width_px=envelope.canonical_frame_width_px,
            canonical_pitch_px=envelope.canonical_pitch_px,
            scale_px_per_mm=envelope.scale_interval_px_per_mm,
            observation_ids=phase_direct_ids,
        ),
        lattice_parameter_fit_basis=(
            LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID
        ),
        calibrated_nominal_grid_fit_state=fit_state,
        model_role_positions_px=envelope.role_positions_px,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(role_full_intervals),
        role_bindings=tuple(role_bindings),
        adjacency_relations=relations,
        contradicted_observation_count=max(
            0,
            sum(
                item.direct and item.observation_id not in bound_direct_ids
                for item in registered_facts
            ),
        ),
        residual_sum_px=sum(
            abs(binding.canonical_position_px - canonical)
            for binding, canonical in zip(
                role_bindings,
                envelope.role_positions_px,
                strict=True,
            )
            if binding is not None
        ),
        phase_support_coverage=sum(support_by_location.values()),
    )
    return _candidate_model._BoundFit(fit, _candidate_model._phase_residual_compatible(fit))


def _projected_role_counterevidence_conflicts(
    projected: _candidate_model._BoundFit,
    candidate: _candidate_model._BoundFit,
    removed_facts: tuple[DirectRoleAuthorityFact, ...],
) -> tuple[DirectRoleAuthorityFact, ...]:
    """Return projected-out native lines outside the selected lattice envelope."""

    conflicts: list[DirectRoleAuthorityFact] = []
    for fact in removed_facts:
        binding = candidate.fit.role_bindings[fact.role_index]
        if binding is None or binding.observation_id != fact.observation_id:
            raise ValueError(
                "projected validation fact lost its candidate binding"
            )
        model = projected.fit.model_full_role_intervals_px[fact.role_index]
        observed = binding.full_position_interval_px
        if observed.maximum < model.minimum or model.maximum < observed.minimum:
            conflicts.append(fact)
    return tuple(conflicts)


def _restore_authorized_local_bindings(
    projected: _candidate_model._BoundFit,
    candidate: _candidate_model._BoundFit,
    retained_facts: tuple[DirectRoleAuthorityFact, ...],
    direct: tuple[_candidate_model._AnchorFact, ...],
) -> _candidate_model._BoundFit | None:
    """Keep supported native local coordinates after a direct-rank refit.

    A refit may change the global lattice without promoting a local correction
    into an independent phase constraint.  Supported local coordinates still
    own their role, so copy only those existing native bindings back onto the
    refitted lattice and carry their full interval.  Unavailable coordinates
    are intentionally absent and remain projection provenance.
    """

    bindings = list(projected.fit.role_bindings)
    role_intervals = list(projected.fit.model_role_intervals_px)
    full_intervals = list(projected.fit.model_full_role_intervals_px)
    bound_elsewhere = {
        binding.observation_id: role_index
        for role_index, binding in enumerate(bindings)
        if binding is not None
    }
    direct_ids = {item.observation_id for item in direct}
    added = 0
    direct_added = 0
    for fact in retained_facts:
        role_index = fact.role_index
        current = bindings[role_index]
        if current is not None:
            if current.observation_id != fact.observation_id:
                return None
            continue
        original = candidate.fit.role_bindings[role_index]
        if (
            original is None
            or original.use != SequenceBindingUse.LOCAL_REFINEMENT
            or original.observation_id != fact.observation_id
            or fact.observation_id in bound_elsewhere
        ):
            return None
        bindings[role_index] = original
        role_intervals[role_index] = _interval_hull(
            role_intervals[role_index],
            original.fit_position_interval_px,
        )
        full_intervals[role_index] = _interval_hull(
            full_intervals[role_index],
            original.full_position_interval_px,
        )
        bound_elsewhere[fact.observation_id] = role_index
        added += 1
        direct_added += int(fact.observation_id in direct_ids)
    if not added:
        return projected
    fit = replace(
        projected.fit,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(full_intervals),
        role_bindings=tuple(bindings),
        contradicted_observation_count=max(
            0,
            projected.fit.contradicted_observation_count - direct_added,
        ),
    )
    return _candidate_model._BoundFit(fit, projected.residual_compatible)


def project_candidate_to_authorized_direct_roles(
    candidate: _candidate_model._BoundFit,
    authority: DirectRoleBindingAuthority,
    registered_facts: tuple[_candidate_model._AnchorFact, ...],
    separator_pairs: tuple[tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    relations: tuple[AdjacencyRelation, ...],
    pitch_authority: FiniteInterval,
    phase_authority: FiniteInterval | None,
    fit_residual_limit_px: float | None,
    calibrated_nominal_grid_prior: CalibratedNominalGridPrior | None,
    phase_anchor_authority_ceiling: (
        frozenset[tuple[int, ObservationId]] | None
    ) = None,
) -> tuple[_candidate_model._BoundFit | None, PhaseCandidateAuthorityProjection]:
    """Project one mapping with its complete identity ledger and fixed seed scope."""

    if not isinstance(candidate, _candidate_model._BoundFit):
        raise TypeError("direct-role projection requires one bounded candidate")
    if not isinstance(authority, DirectRoleBindingAuthority):
        raise TypeError("direct-role projection requires typed authority")
    # Sparse, already-bound local coordinates can have typed role authority
    # without qualifying to seed a phase search.  Keep their identities while
    # preserving the original seed filter and phase-anchor ceiling.
    direct = tuple(item for item in registered_facts if item.direct)
    retained_indices = authority.supported_role_indices
    retained_rank = direct_role_constraint_rank(
        candidate.fit,
        retained_indices,
        adjacency_relations=relations,
    )
    if authority.state == EvidenceState.CONTRADICTED:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=(
                PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION
            ),
            basis=None,
            projected_out_bindings=(),
            retained_direct_constraint_rank=retained_rank,
            reason=authority.reason or "direct-role evidence is contradicted",
        )

    removed_facts = tuple(
        item for item in authority.facts if item.state == EvidenceState.UNAVAILABLE
    )
    projected_out = tuple(
        PhaseCandidateProjectedBinding(
            role_index=item.role_index,
            observation_id=item.observation_id,
        )
        for item in removed_facts
    )
    retained_facts = tuple(
        item for item in authority.facts if item.state == EvidenceState.SUPPORTED
    )
    retained_phase_facts = tuple(
        item
        for item in retained_facts
        if candidate.fit.role_bindings[item.role_index] is not None
        and candidate.fit.role_bindings[item.role_index].use
        == SequenceBindingUse.PHASE_ANCHOR
    )
    retained_local_bindings = tuple(
        (item.role_index, item.observation_id)
        for item in retained_facts
        if candidate.fit.role_bindings[item.role_index] is not None
        and candidate.fit.role_bindings[item.role_index].use
        == SequenceBindingUse.LOCAL_REFINEMENT
    )
    supported_bindings = {
        (item.role_index, item.observation_id) for item in retained_facts
    }
    missing_topology_bindings = tuple(
        binding
        for binding in adjacency_relation_required_bindings(relations)
        if binding not in supported_bindings
    )
    if missing_topology_bindings:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=(
                PhaseCandidateProjectionOutcome.TOPOLOGY_BINDING_UNAVAILABLE
            ),
            basis=None,
            projected_out_bindings=projected_out,
            retained_direct_constraint_rank=retained_rank,
            reason=(
                "topology relation requires unavailable direct role bindings: "
                + ", ".join(
                    f"role {role_index}={observation_id}"
                    for role_index, observation_id in missing_topology_bindings
                )
            ),
        )
    nonseparator_required_bindings = adjacency_relation_required_bindings(
        tuple(
            relation
            for relation in relations
            if not isinstance(relation, SeparatorRelation)
        )
    )
    separator_required_bindings = adjacency_relation_required_bindings(
        tuple(
            relation
            for relation in relations
            if isinstance(relation, SeparatorRelation)
        )
    )
    required_bindings = tuple(
        sorted(
            {
                *(
                    (item.role_index, item.observation_id)
                    for item in retained_phase_facts
                ),
                *nonseparator_required_bindings,
            },
            key=lambda item: (item[0], str(item[1])),
        )
    )
    retained_ids = {item.observation_id for item in retained_facts}
    registered_ids = {item.observation_id for item in registered_facts}
    if not retained_ids.issubset(registered_ids):
        raise ValueError("authorized projection references an unknown direct edge")
    retained_direct = tuple(
        item for item in direct if item.observation_id in retained_ids
    )
    retained_pairs = tuple(
        pair
        for pair in separator_pairs
        if pair[0].observation_id in retained_ids
        and pair[1].observation_id in retained_ids
    )
    retained_role_indices = set(retained_indices)
    complete_frame_unobserved = any(
        2 * frame_index not in retained_role_indices
        and 2 * frame_index + 1 not in retained_role_indices
        for frame_index in range(template.count)
    )
    if (
        authority.state == EvidenceState.SUPPORTED
        and retained_rank == 3
        and not complete_frame_unobserved
        and relations == candidate.fit.adjacency_relations
    ):
        return candidate, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.UNCHANGED,
            basis=PhaseCandidateProjectionBasis.DIRECT_BINDINGS,
            projected_out_bindings=(),
            retained_direct_constraint_rank=retained_rank,
            reason=None,
        )
    if retained_rank < 3 or complete_frame_unobserved:
        if not retained_phase_facts:
            return None, PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=(
                    PhaseCandidateProjectionOutcome
                    .NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE
                ),
                basis=None,
                projected_out_bindings=projected_out,
                retained_direct_constraint_rank=retained_rank,
                reason=(
                    "calibrated nominal Grid requires one authorized direct "
                    "absolute phase anchor"
                ),
            )
        if calibrated_nominal_grid_prior is None or (
            calibrated_nominal_grid_prior.state != EvidenceState.SUPPORTED
        ):
            return None, PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=(
                    PhaseCandidateProjectionOutcome
                    .CALIBRATED_NOMINAL_GRID_UNAVAILABLE
                ),
                basis=None,
                projected_out_bindings=projected_out,
                retained_direct_constraint_rank=retained_rank,
                reason=(
                    "authorized direct coordinates do not close phase, W, and "
                    "pitch, and this format has no calibrated nominal Grid"
                ),
            )
        nominal = _fit_calibrated_nominal_grid_candidate(
            candidate,
            prior=calibrated_nominal_grid_prior,
            retained_facts=retained_facts,
            registered_facts=registered_facts,
            template=template,
            relations=relations,
            phase_authority=phase_authority,
            retained_direct_constraint_rank=retained_rank,
        )
        if nominal is None:
            return None, PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=(
                    PhaseCandidateProjectionOutcome
                    .CALIBRATED_NOMINAL_GRID_CONFLICT
                ),
                basis=None,
                projected_out_bindings=projected_out,
                retained_direct_constraint_rank=retained_rank,
                reason=(
                    "authorized direct coordinates conflict with the bounded "
                    "calibrated nominal Grid"
                ),
            )
        validation_conflicts = _projected_role_counterevidence_conflicts(
            nominal,
            candidate,
            removed_facts,
        )
        if validation_conflicts:
            return None, PhaseCandidateAuthorityProjection(
                input_direct_role_authority=authority,
                outcome=(
                    PhaseCandidateProjectionOutcome
                    .CALIBRATED_NOMINAL_GRID_CONFLICT
                ),
                basis=None,
                projected_out_bindings=projected_out,
                retained_direct_constraint_rank=retained_rank,
                reason=(
                    "validation-only direct coordinates conflict with the "
                    "bounded calibrated nominal Grid at role indices: "
                    + ", ".join(
                        str(item.role_index) for item in validation_conflicts
                    )
                ),
            )
        return nominal, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=(
                PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID
            ),
            basis=PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID,
            projected_out_bindings=projected_out,
            retained_direct_constraint_rank=retained_rank,
            reason=None,
        )

    projected = _fitting._fit_seed(
        _candidate_model._PhaseSeed(
            phase_px=(
                candidate.fit.phase_lattice_fit.canonical_absolute_phase_px
            ),
            pitch_px=candidate.fit.pitch_fit.canonical_pitch_px,
            required_bindings=required_bindings,
            adjacency_relations=relations,
        ),
        retained_direct,
        retained_pairs,
        roles,
        template,
        relations,
        pitch_authority,
        phase_authority,
        fit_residual_limit_px,
        phase_anchor_authority_ceiling,
    )
    if projected is not None:
        projected = _restore_authorized_local_bindings(
            projected,
            candidate,
            retained_facts,
            direct,
        )
    if projected is None:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
            basis=None,
            projected_out_bindings=projected_out,
            retained_direct_constraint_rank=retained_rank,
            reason="authorized direct coordinates have no bounded lattice refit",
        )
    projected_bindings = {
        index: binding.observation_id
        for index, binding in enumerate(projected.fit.role_bindings)
        if binding is not None
    }
    expected_bindings = dict(
        {
            *required_bindings,
            *separator_required_bindings,
            *retained_local_bindings,
        }
    )
    role_binding_changes = tuple(
        (
            role_index,
            expected_bindings.get(role_index),
            projected_bindings.get(role_index),
        )
        for role_index in sorted(
            set(expected_bindings) | set(projected_bindings)
        )
        if expected_bindings.get(role_index)
        != projected_bindings.get(role_index)
    )
    separator_local_bindings_are_scoped = all(
        projected.fit.role_bindings[role_index] is not None
        and (
            (role_index, observation_id) in required_bindings
            or projected.fit.role_bindings[role_index].use
            == SequenceBindingUse.LOCAL_REFINEMENT
        )
        for role_index, observation_id in separator_required_bindings
    )
    relation_identity_changed = (
        tuple(
            adjacency_relation_evidence_identity(item)
            for item in projected.fit.adjacency_relations
        )
        != tuple(
            adjacency_relation_evidence_identity(item)
            for item in relations
        )
    )
    discrete_identity_changes = tuple(
        label
        for changed, label in (
            (
                projected.fit.phase_lattice_fit.integer_slot_offset
                != candidate.fit.phase_lattice_fit.integer_slot_offset,
                "integer_slot_offset",
            ),
            (projected.fit.template != candidate.fit.template, "template"),
            (relation_identity_changed, "relation_evidence"),
            (bool(role_binding_changes), "role_bindings"),
            (
                not separator_local_bindings_are_scoped,
                "separator_local_scope",
            ),
        )
        if changed
    )
    if discrete_identity_changes:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=(
                PhaseCandidateProjectionOutcome.DISCRETE_IDENTITY_CHANGED
            ),
            basis=None,
            projected_out_bindings=projected_out,
            retained_direct_constraint_rank=retained_rank,
            reason=(
                "authorized refit changed the bounded discrete mapping: "
                + ", ".join(discrete_identity_changes)
                + (
                    " ("
                    + "; ".join(
                        "role "
                        + str(role_index)
                        + ": expected "
                        + (
                            "none"
                            if expected is None
                            else str(expected)
                        )
                        + ", got "
                        + (
                            "none" if actual is None else str(actual)
                        )
                        for role_index, expected, actual
                        in role_binding_changes
                    )
                    + ")"
                    if role_binding_changes
                    else ""
                )
            ),
        )
    validation_conflicts = _projected_role_counterevidence_conflicts(
        projected,
        candidate,
        removed_facts,
    )
    if validation_conflicts:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.DIRECT_LATTICE_CONFLICT,
            basis=None,
            projected_out_bindings=projected_out,
            retained_direct_constraint_rank=retained_rank,
            reason=(
                "validation-only direct coordinates conflict with the "
                "bounded direct-rank lattice at role indices: "
                + ", ".join(
                    str(item.role_index) for item in validation_conflicts
                )
            ),
        )
    projected = replace(
        projected,
        fit=replace(
            projected.fit,
            contradicted_observation_count=max(
                0,
                len(direct) - len(projected.fit.bound_observation_ids),
            ),
        ),
    )
    return projected, PhaseCandidateAuthorityProjection(
        input_direct_role_authority=authority,
        outcome=(
            PhaseCandidateProjectionOutcome.PROJECTED
            if projected_out
            else PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT
        ),
        basis=(
            PhaseCandidateProjectionBasis.DIRECT_RANK_THREE
            if projected_out
            else PhaseCandidateProjectionBasis.DIRECT_SEPARATOR_GAP
        ),
        projected_out_bindings=projected_out,
        retained_direct_constraint_rank=retained_rank,
        reason=None,
    )
