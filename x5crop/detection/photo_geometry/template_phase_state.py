"""Bounded sequence phase state."""

from __future__ import annotations

from dataclasses import replace

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .template_model import (
    ContactRelation,
    OverlapRelation,
    SequenceBindingUse,
    SequenceFit,
    SequenceRoleBinding,
    most_constrained_lattice_parameter_fit_basis,
)
from .template_phase_model import (
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitResult,
)
from . import template_phase_candidate_model as _candidate_model


def _intervals_overlap(left: FiniteInterval, right: FiniteInterval) -> bool:
    return not (
        left.maximum < right.minimum or right.maximum < left.minimum
    )


def _projection_failure_kind(
    outcome: PhaseCandidateProjectionOutcome,
) -> PhaseFailureKind:
    """Map one canonical projection failure to its public phase failure."""

    return {
        PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION: (
            PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
        ),
        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_UNAVAILABLE: (
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE
        ),
        PhaseCandidateProjectionOutcome.NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE: (
            PhaseFailureKind.NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE
        ),
        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT: (
            PhaseFailureKind.CALIBRATED_NOMINAL_GRID_CONFLICT
        ),
        PhaseCandidateProjectionOutcome.DIRECT_LATTICE_CONFLICT: (
            PhaseFailureKind.DIRECT_LATTICE_CONFLICT
        ),
        PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE: (
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH
        ),
        PhaseCandidateProjectionOutcome.DISCRETE_IDENTITY_CHANGED: (
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH
        ),
    }.get(
        outcome,
        PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE,
    )


def _topology_signature(
    fit: SequenceFit,
) -> tuple[tuple[str, int, ObservationId], ...]:
    return tuple(
        (
            relation.kind.value,
            relation.relation_ordinal,
            relation.contact_observation_id
            if isinstance(relation, ContactRelation)
            else relation.overlap_observation_id,
        )
        for relation in fit.adjacency_relations
        if isinstance(relation, (ContactRelation, OverlapRelation))
    )


def _same_lattice_fit_lineage(
    current: SequenceFit,
    prior: SequenceFit,
) -> bool:
    """Identify one discrete placement across continuous calibration passes."""

    if (
        current.template.template_id != prior.template.template_id
        or current.template.count != prior.template.count
        or current.template.direction != prior.template.direction
        or current.phase_lattice_fit.integer_slot_offset
        != prior.phase_lattice_fit.integer_slot_offset
        or not _intervals_overlap(
            current.phase_lattice_fit.absolute_phase_interval_px,
            prior.phase_lattice_fit.absolute_phase_interval_px,
        )
    ):
        return False
    current_roles = {
        binding.observation_id: role_index
        for role_index, binding in enumerate(current.role_bindings)
        if binding is not None
    }
    prior_roles = {
        binding.observation_id: role_index
        for role_index, binding in enumerate(prior.role_bindings)
        if binding is not None
    }
    shared = current_roles.keys() & prior_roles.keys()
    return bool(shared) and all(
        current_roles[observation_id] == prior_roles[observation_id]
        for observation_id in shared
    )


def _inherit_prior_lattice_fit_basis(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Retain direct-fit provenance without reclassifying a nominal solve."""

    prior_fits = tuple(
        fit for fit in (prior.best, prior.runner_up) if fit is not None
    )

    def inherit(current: SequenceFit | None) -> SequenceFit | None:
        if current is None:
            return None
        # A calibrated Grid state belongs to the exact bounded solve that
        # produced the current coordinates.  Earlier direct passes remain in
        # the work receipt, but cannot relabel that solve or donate nominal
        # authority to a later non-nominal fit.
        if current.calibrated_nominal_grid_fit_state is not None:
            return current
        bases = (
            current.lattice_parameter_fit_basis,
            *(
                candidate.lattice_parameter_fit_basis
                for candidate in prior_fits
                if _same_lattice_fit_lineage(current, candidate)
                and candidate.calibrated_nominal_grid_fit_state is None
            ),
        )
        basis = most_constrained_lattice_parameter_fit_basis(*bases)
        if basis == current.lattice_parameter_fit_basis:
            return current
        return replace(
            current,
            lattice_parameter_fit_basis=basis,
        )

    return replace(
        result,
        best=inherit(result.best),
        runner_up=inherit(result.runner_up),
    )


def _continuous_role_bindings(
    left: SequenceFit,
    right: SequenceFit,
) -> tuple[SequenceRoleBinding | None, ...] | None:
    """Union complementary facts without collapsing distinct role evidence."""

    merged: list[SequenceRoleBinding | None] = []
    for left_binding, right_binding in zip(
        left.role_bindings,
        right.role_bindings,
        strict=True,
    ):
        if left_binding is None:
            merged.append(right_binding)
        elif right_binding is None:
            merged.append(left_binding)
        elif left_binding.observation_id == right_binding.observation_id:
            merged.append(left_binding)
        else:
            return None
    roles_by_observation: dict[ObservationId, list[int]] = {}
    for role_index, binding in enumerate(merged):
        if binding is not None:
            roles_by_observation.setdefault(
                binding.observation_id,
                [],
            ).append(role_index)
    contacts = {
        item.shared_edge_observation_id: item
        for item in left.adjacency_relations
        if isinstance(item, ContactRelation)
    }
    for identity, role_indices in roles_by_observation.items():
        if len(role_indices) == 1:
            continue
        contact = contacts.get(identity)
        expected = (
            2 * contact.relation_ordinal - 1,
            2 * contact.relation_ordinal,
        ) if contact is not None else ()
        if tuple(role_indices) != expected:
            return None
    return tuple(merged)


def _same_continuous_placement(
    left: SequenceFit,
    right: SequenceFit,
) -> bool:
    """Distinguish one joint feasible placement from a discrete runner."""

    def same_role_state(
        left_interval: FiniteInterval,
        right_interval: FiniteInterval,
        left_binding,
        right_binding,
    ) -> bool:
        if left_binding is None or right_binding is None:
            return _intervals_overlap(left_interval, right_interval)
        # A material component can correlate several measured edges without
        # making them the same physical coordinate.  Edge-family registration
        # has already merged fragments that truly own one coordinate, so only
        # the canonical observation identity may collapse two role bindings.
        return left_binding.observation_id == right_binding.observation_id

    merged_bindings = _continuous_role_bindings(left, right)
    return (
        left.template == right.template
        and left.lattice_parameter_fit_basis
        == right.lattice_parameter_fit_basis
        and left.calibrated_nominal_grid_fit_state
        == right.calibrated_nominal_grid_fit_state
        and left.phase_lattice_fit.integer_slot_offset
        == right.phase_lattice_fit.integer_slot_offset
        and left.adjacency_relations == right.adjacency_relations
        and merged_bindings is not None
        and _intervals_overlap(
            left.phase_lattice_fit.absolute_phase_interval_px,
            right.phase_lattice_fit.absolute_phase_interval_px,
        )
        and all(
            same_role_state(
                left_interval,
                right_interval,
                left_binding,
                right_binding,
            )
            for left_interval, right_interval, left_binding, right_binding in zip(
                left.model_full_role_intervals_px,
                right.model_full_role_intervals_px,
                left.role_bindings,
                right.role_bindings,
                strict=True,
            )
        )
    )


def _interval_hull(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        min(left.minimum, right.minimum),
        max(left.maximum, right.maximum),
    )


def _merge_continuous_placement(
    selected: _candidate_model._BoundFit,
    alternative: _candidate_model._BoundFit,
) -> _candidate_model._BoundFit:
    """Retain the selected canonical state and expose the full joint hull."""

    left = selected.fit
    right = alternative.fit
    if not _same_continuous_placement(left, right):
        raise ValueError("cannot merge discrete phase placements")
    if left == right:
        return _candidate_model._BoundFit(
            left,
            selected.residual_compatible and alternative.residual_compatible,
        )
    role_bindings = _continuous_role_bindings(left, right)
    if role_bindings is None:
        raise ValueError("continuous phase bindings cannot be combined")
    observation_ids = tuple(
        dict.fromkeys(
            binding.observation_id
            for binding in role_bindings
            if binding is not None
        )
    )
    left_direct_count = (
        left.contradicted_observation_count + len(left.bound_observation_ids)
    )
    right_direct_count = (
        right.contradicted_observation_count + len(right.bound_observation_ids)
    )
    if left_direct_count != right_direct_count:
        raise ValueError("continuous phase fits disagree on registered evidence")
    cycle_interval = _interval_hull(
        left.phase_lattice_fit.cycle_phase_interval_px,
        right.phase_lattice_fit.cycle_phase_interval_px,
    )
    if cycle_interval.maximum > left.phase_lattice_fit.canonical_period_px:
        raise ValueError("continuous phase hull crosses a lattice period")
    merged = replace(
        left,
        phase_lattice_fit=replace(
            left.phase_lattice_fit,
            cycle_phase_interval_px=cycle_interval,
            absolute_phase_interval_px=_interval_hull(
                left.phase_lattice_fit.absolute_phase_interval_px,
                right.phase_lattice_fit.absolute_phase_interval_px,
            ),
        ),
        pitch_fit=replace(
            left.pitch_fit,
            pitch_interval_px=PositiveInterval(
                min(
                    left.pitch_fit.pitch_interval_px.minimum,
                    right.pitch_fit.pitch_interval_px.minimum,
                ),
                max(
                    left.pitch_fit.pitch_interval_px.maximum,
                    right.pitch_fit.pitch_interval_px.maximum,
                ),
            ),
            observation_ids=observation_ids,
        ),
        model_role_intervals_px=tuple(
            _interval_hull(left_interval, right_interval)
            for left_interval, right_interval in zip(
                left.model_role_intervals_px,
                right.model_role_intervals_px,
                strict=True,
            )
        ),
        model_full_role_intervals_px=tuple(
            _interval_hull(left_interval, right_interval)
            for left_interval, right_interval in zip(
                left.model_full_role_intervals_px,
                right.model_full_role_intervals_px,
                strict=True,
            )
        ),
        role_bindings=role_bindings,
        contradicted_observation_count=max(
            0,
            left_direct_count - len(observation_ids),
        ),
        residual_sum_px=sum(
            abs(binding.canonical_position_px - canonical)
            for binding, canonical in zip(
                role_bindings,
                left.model_role_positions_px,
                strict=True,
            )
            if binding is not None
        ),
        phase_support_coverage=max(
            left.phase_support_coverage,
            right.phase_support_coverage,
        ),
    )
    return _candidate_model._BoundFit(
        merged,
        selected.residual_compatible and alternative.residual_compatible,
    )


def _continuous_state_is_absorbed(best: SequenceFit, candidate: SequenceFit) -> bool:
    """A continuous candidate is redundant only after its full state is retained."""
    if not _same_continuous_placement(best, candidate):
        return False
    for retained, incoming in zip(best.role_bindings, candidate.role_bindings, strict=True):
        if incoming is not None and (
            retained is None
            or retained.observation_id != incoming.observation_id
            or (
                incoming.use == SequenceBindingUse.PHASE_ANCHOR
                and retained.use != SequenceBindingUse.PHASE_ANCHOR
            )
        ):
            return False
    retained_intervals = (
        best.phase_lattice_fit.cycle_phase_interval_px,
        best.phase_lattice_fit.absolute_phase_interval_px,
        best.pitch_fit.pitch_interval_px,
        *best.model_role_intervals_px,
        *best.model_full_role_intervals_px,
    )
    incoming_intervals = (
        candidate.phase_lattice_fit.cycle_phase_interval_px,
        candidate.phase_lattice_fit.absolute_phase_interval_px,
        candidate.pitch_fit.pitch_interval_px,
        *candidate.model_role_intervals_px,
        *candidate.model_full_role_intervals_px,
    )
    return all(
        retained.minimum <= incoming.minimum and incoming.maximum <= retained.maximum
        for retained, incoming in zip(retained_intervals, incoming_intervals, strict=True)
    ) and best.phase_support_coverage >= candidate.phase_support_coverage
