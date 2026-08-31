"""Orchestrate bounded global fitting of one fixed sequence template."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from typing import Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    FrameWidthInferenceFailureKind,
    LocalAdvanceRelation,
    SequenceFit,
    SequenceRoleBinding,
    TemplateSearchReceipt,
    TemplateSpec,
    most_constrained_lattice_parameter_fit_basis,
    ordered_template_roles,
)
from .template_phase_candidates import (
    _BoundFit,
    _PhaseSeed,
    _clear_winner_basis,
    _facts,
    _fit_seed,
    _holder_limits,
    _positive,
    _prefixes,
    _rank,
    _refine_local_role_bindings,
    _relations,
    _separator_pair_facts,
    _separator_phase_seeds,
    _with_separator_role_authority,
)
from .separator_material import normal_separator_material_bands
from .template_evidence import separator_support_authority
from .template_frame_width import apply_correlated_frame_width_inference
from .template_adjacency_coverage import (
    AdjacencyCoverageState,
    assess_adjacency_observation_coverage,
)
from .template_lattice_authority import assess_global_lattice_authority
from .template_direct_role_authority import (
    assess_direct_role_binding_authorities,
    assess_direct_role_binding_authority,
)
from .template_outer_frame_authority import (
    assess_outer_frame_observation_authority,
)
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)


def _intervals_overlap(left: FiniteInterval, right: FiniteInterval) -> bool:
    return not (
        left.maximum < right.minimum or right.maximum < left.minimum
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
    """Retain the most constrained parameter solve in each fit lineage."""

    prior_fits = tuple(
        fit for fit in (prior.best, prior.runner_up) if fit is not None
    )

    def inherit(current: SequenceFit | None) -> SequenceFit | None:
        if current is None:
            return None
        bases = (
            current.lattice_parameter_fit_basis,
            *(
                candidate.lattice_parameter_fit_basis
                for candidate in prior_fits
                if _same_lattice_fit_lineage(current, candidate)
            ),
        )
        basis = most_constrained_lattice_parameter_fit_basis(*bases)
        if basis == current.lattice_parameter_fit_basis:
            return current
        return replace(current, lattice_parameter_fit_basis=basis)

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
    identities = tuple(
        binding.observation_id
        for binding in merged
        if binding is not None
    )
    if len(set(identities)) != len(identities):
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
        and left.phase_lattice_fit.integer_slot_offset
        == right.phase_lattice_fit.integer_slot_offset
        and left.local_advance_relations == right.local_advance_relations
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
    selected: _BoundFit,
    alternative: _BoundFit,
) -> _BoundFit:
    """Retain the selected canonical state and expose the full joint hull."""

    left = selected.fit
    right = alternative.fit
    if not _same_continuous_placement(left, right):
        raise ValueError("cannot merge discrete phase placements")
    role_bindings = _continuous_role_bindings(left, right)
    if role_bindings is None:
        raise ValueError("continuous phase bindings cannot be combined")
    observation_ids = tuple(
        binding.observation_id
        for binding in role_bindings
        if binding is not None
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
    return _BoundFit(
        merged,
        selected.residual_compatible and alternative.residual_compatible,
    )


def fit_template_phase(
    observations: Sequence[BoundaryEdgeObservation],
    template: TemplateSpec,
    *,
    separator_bands: Sequence[SeparatorBandObservation] = (),
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    phase_authority_px: FiniteInterval | None = None,
    local_advance_relations: Sequence[LocalAdvanceRelation] = (),
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet] = (),
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit `{phase, W, pitch}` without building a chain product."""

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
    registered_observations = tuple(observations)
    phase_separator_bands = normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    separator_support_ids = separator_support_authority(phase_separator_bands)
    observations = _with_separator_role_authority(
        observations,
        separator_bands,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    facts = _facts(
        observations,
        separator_support_ids=separator_support_ids,
    )
    direct = tuple(item for item in facts if item.direct)
    separator_pairs = _separator_pair_facts(
        phase_separator_bands,
        direct,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    roles = ordered_template_roles(template.count)
    relations = _relations(local_advance_relations, template.count)
    base = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=0,
        role_binding_count=0,
        local_relation_evaluation_count=len(relations),
        local_refinement_lookup_count=0,
        local_refinement_binding_count=0,
        phase_hypothesis_count=0,
        phase_offset_lookup_count=0,
        direct_observation_count=len(direct),
        inferred_role_count=0,
    )
    direct_ids = tuple(item.observation_id for item in direct)
    if len(facts) > max_observations:
        return PhaseFitResult(
            template,
            None,
            None,
            PhaseFitStatus.BOUND_EXCEEDED,
            "phase observation bound exceeded",
            base,
            direct_ids,
            PhaseFailureKind.OBSERVATION_BOUND_EXCEEDED,
        )
    if not direct:
        return PhaseFitResult(
            template,
            None,
            None,
            PhaseFitStatus.UNRESOLVED,
            "phase requires direct edge evidence",
            base,
            direct_ids,
            PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE,
        )
    measurement_scale = (
        None if scale_px_per_mm is None else _positive(scale_px_per_mm)
    )
    fit_residual_limit_px = (
        None
        if measurement_scale is None
        else PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
            measurement_scale.maximum
        )
    )
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap_pitch = FiniteInterval(
        width.minimum + template.gap_prior_px.minimum,
        width.maximum + template.gap_prior_px.maximum,
    )
    declared_pitch = FiniteInterval(
        template.pitch_px.minimum,
        template.pitch_px.maximum,
    )
    minimum = max(gap_pitch.minimum, declared_pitch.minimum)
    maximum = min(gap_pitch.maximum, declared_pitch.maximum)
    if maximum < minimum:
        raise ValueError("template pitch and gap prior have no common interval")
    pitch_authority = FiniteInterval(minimum, maximum)
    prefixes = _prefixes(relations, template.count)
    width0 = width.center
    pitch0 = pitch_authority.center
    coordinates = tuple(item.coordinate_px for item in direct)
    nominal_span = (
        width0
        + max(0, template.count - 1) * pitch0
        + prefixes[-1]
    )
    span_window = max(3.0, pitch0 * 0.35)
    seed_values: dict[tuple[float, float], _PhaseSeed | None] = {}

    def register_seed(seed: _PhaseSeed) -> None:
        key = (seed.phase_px, seed.pitch_px)
        if key not in seed_values:
            seed_values[key] = seed
            return
        current = seed_values[key]
        if current is None:
            return
        merged = set(current.required_bindings) | set(seed.required_bindings)
        role_to_observation: dict[int, ObservationId] = {}
        observation_to_role: dict[ObservationId, int] = {}
        for role_index, observation_id in merged:
            if (
                role_index in role_to_observation
                and role_to_observation[role_index] != observation_id
                or observation_id in observation_to_role
                and observation_to_role[observation_id] != role_index
            ):
                seed_values[key] = None
                return
            role_to_observation[role_index] = observation_id
            observation_to_role[observation_id] = role_index
        seed_values[key] = _PhaseSeed(
            seed.phase_px,
            seed.pitch_px,
            tuple(sorted(merged, key=lambda item: (item[0], str(item[1])))),
        )

    for seed in _separator_phase_seeds(
            phase_separator_bands,
            direct,
            roles,
            template,
            width=width0,
            pitch=pitch0,
            prefixes=prefixes,
        ):
        register_seed(seed)
    # Count-one templates have no pitch relation.  Their START and END seeds
    # already close the fixed-width pair below; treating every nearby END as a
    # second full-span origin would merge distinct physical edge alternatives
    # into one seed identity.
    if template.count == 1:
        pass
    elif template.direction > 0:
        for first in direct:
            if BoundaryRole.START not in first.qualified_anchor_roles:
                continue
            target = first.coordinate_px + nominal_span
            insertion = bisect_left(coordinates, target)
            for index in (insertion - 2, insertion - 1, insertion, insertion + 1):
                if not 0 <= index < len(direct):
                    continue
                last = direct[index]
                if BoundaryRole.END not in last.qualified_anchor_roles:
                    continue
                if abs(last.coordinate_px - target) > span_window:
                    continue
                if template.count > 1:
                    derived_pitch = (
                        last.coordinate_px
                        - first.coordinate_px
                        - width0
                        - prefixes[-1]
                    ) / (template.count - 1)
                    if not pitch_authority.contains(derived_pitch):
                        continue
                else:
                    derived_pitch = pitch0
                register_seed(
                    _PhaseSeed(
                        round(first.coordinate_px, 9),
                        round(derived_pitch, 9),
                        (
                            (roles[0].role_index, first.observation_id),
                            (roles[-1].role_index, last.observation_id),
                        ),
                    )
                )
    else:
        for first in reversed(direct):
            if BoundaryRole.START not in first.qualified_anchor_roles:
                continue
            target = first.coordinate_px - nominal_span
            insertion = bisect_left(coordinates, target)
            for index in (insertion - 2, insertion - 1, insertion, insertion + 1):
                if not 0 <= index < len(direct):
                    continue
                last = direct[index]
                if BoundaryRole.END not in last.qualified_anchor_roles:
                    continue
                if abs(last.coordinate_px - target) > span_window:
                    continue
                if template.count > 1:
                    derived_pitch = (
                        first.coordinate_px
                        - last.coordinate_px
                        - width0
                        - prefixes[-1]
                    ) / (template.count - 1)
                    if not pitch_authority.contains(derived_pitch):
                        continue
                else:
                    derived_pitch = pitch0
                register_seed(
                    _PhaseSeed(
                        round(first.coordinate_px, 9),
                        round(derived_pitch, 9),
                        (
                            (roles[0].role_index, first.observation_id),
                            (roles[-1].role_index, last.observation_id),
                        ),
                    )
                )
    # Missing or dark outer frames are common.  A direct role-qualified edge
    # therefore seeds every compatible indexed role.  The pixel observation
    # remains the phase authority; the template contributes only the finite
    # ordinal alternatives.  Different ordinal mappings survive as discrete
    # placements and can never be averaged or selected by coarse support.
    for anchor in direct:
        for role in roles:
            if anchor.role_index is not None and anchor.role_index != role.role_index:
                continue
            if (
                anchor.qualified_anchor_roles
                and role.role not in anchor.qualified_anchor_roles
            ):
                continue
            relative = role.slot_index * pitch0 + prefixes[role.slot_index]
            if role.role == BoundaryRole.END:
                relative += width0
            register_seed(
                _PhaseSeed(
                    round(
                        anchor.coordinate_px
                        - template.direction * relative,
                        9,
                    ),
                    round(pitch0, 9),
                    ((role.role_index, anchor.observation_id),),
                )
            )
    if phase_authority_px is not None:
        register_seed(
            _PhaseSeed(
                round(phase_authority_px.center, 9),
                round(pitch0, 9),
            )
        )
    seeds = tuple(
        seed
        for seed in seed_values.values()
        if seed is not None
    )
    maximum_hypotheses = max(1, len(facts)) * max(6, len(roles))
    if len(seeds) > maximum_hypotheses:
        receipt = TemplateSearchReceipt(
            observation_count=len(facts),
            role_count=len(roles),
            phase_lookup_count=len(seeds),
            role_binding_count=0,
            local_relation_evaluation_count=len(relations),
            local_refinement_lookup_count=0,
            local_refinement_binding_count=0,
            phase_hypothesis_count=len(seeds),
            phase_offset_lookup_count=len(seeds),
            direct_observation_count=len(direct),
            inferred_role_count=0,
            peak_temporary_bytes=len(seeds) * len(roles) * 32,
        )
        return PhaseFitResult(
            template,
            None,
            None,
            PhaseFitStatus.BOUND_EXCEEDED,
            "phase hypothesis bound exceeded",
            receipt,
            direct_ids,
            PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
        )
    holder_limits = _holder_limits(holder_span_px)
    local_candidates = tuple(
        value
        for value in (
            _fit_seed(
                seed,
                direct,
                separator_pairs,
                roles,
                template,
                relations,
                pitch_authority,
                phase_authority_px,
                fit_residual_limit_px,
            )
            for seed in sorted(
                seeds,
                key=lambda item: (
                    item.phase_px,
                    item.pitch_px,
                    tuple(
                        (role_index, str(observation_id))
                        for role_index, observation_id in item.required_bindings
                    ),
                ),
            )
        )
        if value is not None
        and (
            holder_limits is None
            or (
                min(value.fit.model_role_positions_px)
                >= holder_limits[0] - width0 * 0.04
                and max(value.fit.model_role_positions_px)
                <= holder_limits[1] + width0 * 0.04
            )
        )
        and (
            phase_authority_px is None
            or not (
                value.fit.phase_lattice_fit.absolute_phase_interval_px.maximum
                < phase_authority_px.minimum
                or phase_authority_px.maximum
                < value.fit.phase_lattice_fit.absolute_phase_interval_px.minimum
            )
        )
    )
    by_binding: dict[
        tuple[int, tuple[ObservationId | None, ...]],
        _BoundFit,
    ] = {}
    for candidate in local_candidates:
        key = (
            candidate.fit.phase_lattice_fit.integer_slot_offset,
            candidate.fit.binding_observation_ids,
        )
        current = by_binding.get(key)
        if current is None or _rank(candidate) > _rank(current):
            by_binding[key] = candidate
    candidates = tuple(by_binding.values())
    measurement_sets = tuple(sequence_measurement_sets)
    candidate_authorities = (
        assess_direct_role_binding_authorities(
            tuple(item.fit for item in candidates),
            registered_observations,
            tuple(separator_bands),
            measurement_sets,
        )
        if candidates and measurement_sets
        else ()
    )
    assessed = tuple(
        (candidate, candidate_authorities[index])
        for index, candidate in enumerate(candidates)
    ) if candidate_authorities else ()
    authoritative_candidates = (
        tuple(
            candidate
            for candidate, authority in assessed
            if authority.state == EvidenceState.SUPPORTED
        )
        if measurement_sets
        else candidates
    )
    compatible = tuple(
        item for item in authoritative_candidates if item.residual_compatible
    )
    incompatible = tuple(
        item for item in authoritative_candidates if not item.residual_compatible
    )

    ordered = tuple(sorted(compatible, key=_rank, reverse=True))
    best = ordered[0] if ordered else None
    if len(ordered) > 1:
        discrete: list[_BoundFit] = []
        for candidate in ordered[1:]:
            assert best is not None
            if _same_continuous_placement(best.fit, candidate.fit):
                best = _merge_continuous_placement(best, candidate)
            else:
                discrete.append(candidate)
        runner = discrete[0] if discrete else None
    else:
        runner = None
    receipt = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=len(seeds),
        role_binding_count=len(seeds) * len(roles),
        local_relation_evaluation_count=len(relations),
        local_refinement_lookup_count=0,
        local_refinement_binding_count=0,
        phase_hypothesis_count=len(seeds),
        phase_offset_lookup_count=len(seeds),
        direct_observation_count=len(direct),
        inferred_role_count=(0 if best is None else len(best.fit.unbound_role_indices)),
        peak_temporary_bytes=len(seeds) * len(roles) * 32,
        candidate_direct_role_authority_evaluation_count=len(
            candidate_authorities
        ),
        candidate_direct_role_authority_rejection_count=sum(
            item.state != EvidenceState.SUPPORTED
            for item in candidate_authorities
        ),
        candidate_direct_role_authority_role_check_count=sum(
            len(item.facts) for item in candidate_authorities
        ),
    )
    receipt.validate_bounds()
    if best is None:
        raw_compatible = tuple(
            sorted(
                (item for item in candidates if item.residual_compatible),
                key=_rank,
                reverse=True,
            )
        )
        if raw_compatible and measurement_sets:
            diagnostic_best = raw_compatible[0]
            diagnostic_runner = next(
                (
                    item
                    for item in raw_compatible[1:]
                    if not _same_continuous_placement(
                        diagnostic_best.fit,
                        item.fit,
                    )
                ),
                None,
            )
            authority_by_candidate = {
                id(candidate): authority
                for candidate, authority in assessed
            }
            best_authority = authority_by_candidate[id(diagnostic_best)]
            runner_authority = (
                None
                if diagnostic_runner is None
                else authority_by_candidate[id(diagnostic_runner)]
            )
            return PhaseFitResult(
                template=template,
                best=diagnostic_best.fit,
                runner_up=(
                    None if diagnostic_runner is None else diagnostic_runner.fit
                ),
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=best_authority.reason,
                receipt=replace(
                    receipt,
                    inferred_role_count=len(
                        diagnostic_best.fit.unbound_role_indices
                    ),
                ),
                registered_direct_observation_ids=direct_ids,
                failure_kind=(
                    PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
                    if best_authority.state == EvidenceState.CONTRADICTED
                    else PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
                ),
                winner_basis=None,
                best_phase_candidate_direct_role_authority=best_authority,
                runner_phase_candidate_direct_role_authority=runner_authority,
            )
        return PhaseFitResult(
            template,
            None,
            None,
            PhaseFitStatus.UNRESOLVED,
            "no residual-compatible direct observation matched the fixed template",
            receipt,
            direct_ids,
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
        )
    contradictory_runner = max(
        (
            item
            for item in incompatible
            if item.fit.phase_support_count > best.fit.phase_support_count
            and not (
                _intervals_overlap(
                    item.fit.phase_lattice_fit.absolute_phase_interval_px,
                    best.fit.phase_lattice_fit.absolute_phase_interval_px,
                )
                and _intervals_overlap(
                    FiniteInterval(
                        item.fit.pitch_fit.pitch_interval_px.minimum,
                        item.fit.pitch_fit.pitch_interval_px.maximum,
                    ),
                    FiniteInterval(
                        best.fit.pitch_fit.pitch_interval_px.minimum,
                        best.fit.pitch_fit.pitch_interval_px.maximum,
                    ),
                )
            )
        ),
        key=_rank,
        default=None,
    )
    if contradictory_runner is not None:
        runner = contradictory_runner
        winner_basis = None
    elif runner is None:
        rejected_runner = (
            max(
                (
                    candidate
                    for candidate, authority in assessed
                    if authority.state != EvidenceState.SUPPORTED
                    and not _same_continuous_placement(best.fit, candidate.fit)
                ),
                key=_rank,
                default=None,
            )
            if measurement_sets
            else None
        )
        if rejected_runner is None:
            winner_basis = PhaseWinnerBasis.ONLY_PHYSICAL_FIT
        else:
            runner = rejected_runner
            winner_basis = PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY
    else:
        winner_basis = _clear_winner_basis(best, runner)
    if winner_basis is not None:
        status = PhaseFitStatus.RESOLVED
        reason = None
        failure_kind = None
    else:
        status = PhaseFitStatus.AMBIGUOUS
        reason = (
            "higher-support direct evidence contradicts the selected fixed template"
            if contradictory_runner is not None
            else "runner-up is not clearly separated from the best template"
        )
        failure_kind = PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS
    final_candidate_authorities = (
        assess_direct_role_binding_authorities(
            tuple(
                item.fit
                for item in (best, runner)
                if item is not None
            ),
            registered_observations,
            tuple(separator_bands),
            measurement_sets,
        )
        if measurement_sets
        else ()
    )
    return PhaseFitResult(
        template,
        best.fit,
        None if runner is None else runner.fit,
        status,
        reason,
        receipt,
        direct_ids,
        failure_kind,
        winner_basis,
        best_phase_candidate_direct_role_authority=(
            final_candidate_authorities[0]
            if final_candidate_authorities
            else None
        ),
        runner_phase_candidate_direct_role_authority=(
            final_candidate_authorities[1]
            if len(final_candidate_authorities) > 1
            else None
        ),
    )


def _aggregate_phase_work(
    result: PhaseFitResult,
    *prior: TemplateSearchReceipt,
    local_relation_evaluation_count: int | None = None,
) -> PhaseFitResult:
    receipts = (*prior, result.receipt)
    receipt = TemplateSearchReceipt(
        observation_count=result.receipt.observation_count,
        role_count=result.receipt.role_count,
        phase_lookup_count=sum(item.phase_lookup_count for item in receipts),
        role_binding_count=sum(item.role_binding_count for item in receipts),
        local_relation_evaluation_count=(
            sum(item.local_relation_evaluation_count for item in receipts)
            if local_relation_evaluation_count is None
            else local_relation_evaluation_count
        ),
        local_refinement_lookup_count=sum(
            item.local_refinement_lookup_count for item in receipts
        ),
        local_refinement_binding_count=sum(
            item.local_refinement_binding_count for item in receipts
        ),
        phase_hypothesis_count=sum(
            item.phase_hypothesis_count for item in receipts
        ),
        phase_offset_lookup_count=sum(
            item.phase_offset_lookup_count for item in receipts
        ),
        direct_observation_count=result.receipt.direct_observation_count,
        inferred_role_count=result.receipt.inferred_role_count,
        peak_temporary_bytes=max(
            item.peak_temporary_bytes for item in receipts
        ),
        fit_pass_count=sum(item.fit_pass_count for item in receipts),
        separator_lattice_hypothesis_count=sum(
            item.separator_lattice_hypothesis_count for item in receipts
        ),
        candidate_direct_role_authority_evaluation_count=sum(
            item.candidate_direct_role_authority_evaluation_count
            for item in receipts
        ),
        candidate_direct_role_authority_rejection_count=sum(
            item.candidate_direct_role_authority_rejection_count
            for item in receipts
        ),
        candidate_direct_role_authority_role_check_count=sum(
            item.candidate_direct_role_authority_role_check_count
            for item in receipts
        ),
    )
    receipt.validate_bounds()
    return replace(result, receipt=receipt)


def _with_local_role_refinement(
    result: PhaseFitResult,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
) -> PhaseFitResult:
    if result.status != PhaseFitStatus.RESOLVED or result.best is None:
        return result
    refinement = _refine_local_role_bindings(
        result.best,
        observations,
        separator_bands,
    )
    receipt = replace(
        result.receipt,
        local_refinement_lookup_count=(
            result.receipt.local_refinement_lookup_count
            + refinement.role_lookup_count
        ),
        local_refinement_binding_count=(
            result.receipt.local_refinement_binding_count
            + refinement.binding_count
        ),
        inferred_role_count=len(refinement.fit.unbound_role_indices),
    )
    receipt.validate_bounds()
    return replace(result, best=refinement.fit, receipt=receipt)


def _apply_final_lattice_contract(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    directly_observed_ordinals: tuple[int, ...],
) -> PhaseFitResult:
    """Require direct-role, global, and local authority for one placement."""

    preliminary_direct_role_authority = (
        None
        if result.best is None or not phase_input.sequence_measurement_sets
        else assess_direct_role_binding_authority(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
        )
    )
    if result.best is not None:
        assessed_best = apply_correlated_frame_width_inference(
            result.best,
            frame_width_observation_ids=(
                phase_input.global_lattice_evidence
                .frame_width_observation_ids
            ),
            direct_role_authority=preliminary_direct_role_authority,
            sequence_edges=phase_input.observations,
        )
        receipt = replace(
            result.receipt,
            inferred_role_count=len(assessed_best.unbound_role_indices),
        )
        receipt.validate_bounds()
        result = replace(
            result,
            best=assessed_best,
            receipt=receipt,
        )
    direct_role_authority = (
        None
        if result.best is None or not phase_input.sequence_measurement_sets
        else assess_direct_role_binding_authority(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
        )
    )

    authority = (
        None
        if result.best is None
        else assess_global_lattice_authority(
            result.best,
            phase_input,
            direct_role_authority=direct_role_authority,
        )
    )
    coverage = (
        ()
        if result.best is None
        else assess_adjacency_observation_coverage(
            result.best,
            phase_input.sequence_measurement_sets,
            directly_observed_ordinals=directly_observed_ordinals,
        )
    )
    outer_authority = (
        None
        if result.best is None
        else assess_outer_frame_observation_authority(result.best)
    )
    result = replace(
        result,
        global_lattice_authority=authority,
        adjacency_observation_coverage=coverage,
        direct_role_binding_authority=direct_role_authority,
        outer_frame_observation_authority=outer_authority,
    )
    inferred = tuple(item for item in coverage if item.normal_inference_required)
    if (
        result.status == PhaseFitStatus.RESOLVED
        and direct_role_authority is not None
        and direct_role_authority.state != EvidenceState.SUPPORTED
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=direct_role_authority.reason,
            failure_kind=(
                PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
                if direct_role_authority.state == EvidenceState.CONTRADICTED
                else PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and inferred
        and (
            authority is None
            or authority.state != EvidenceState.SUPPORTED
        )
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "an inferred normal adjacency requires independently closed "
                "global phase, W, and pitch authority"
            ),
            failure_kind=(
                PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and any(
            item.state != AdjacencyCoverageState.COMPLETE
            for item in inferred
        )
    ):
        missing = ", ".join(
            str(item.relation_ordinal)
            for item in inferred
            if item.state != AdjacencyCoverageState.COMPLETE
        )
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "registered sequence queries do not fully cover inferred "
                f"normal adjacency ordinals: {missing}"
            ),
            failure_kind=(
                PhaseFailureKind.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and inferred
        and (
            outer_authority is None
            or outer_authority.state != EvidenceState.SUPPORTED
        )
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "normal Grid inference requires one directly bound long-axis "
                "role on each outer output frame"
            ),
            failure_kind=(
                PhaseFailureKind.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if result.status == PhaseFitStatus.RESOLVED and result.best is not None:
        width_inference = result.best.frame_width_inference
        if (
            width_inference is not None
            and width_inference.state != EvidenceState.SUPPORTED
        ):
            return replace(
                result,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=(
                    "a Frame with two unobserved sequence roles cannot be "
                    "created from the Grid"
                    if width_inference.failure_kind
                    == FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED
                    else "missing opposite Frame roles require one independently "
                    "closed source-level common W"
                ),
                failure_kind=(
                    PhaseFailureKind.FRAME_WIDTH_INFERENCE_UNAVAILABLE
                ),
                winner_basis=None,
            )
    return result


def fit_template_phase_with_local_advance(
    phase_input: TemplatePhaseInput,
) -> PhaseFitResult:
    """Fit the normal template, then apply directly measured adjacency advances."""

    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError("local-advance phase fit requires TemplatePhaseInput")
    observations = phase_input.observations
    separator_bands = phase_input.separator_bands
    template = phase_input.template
    scale_px_per_mm = phase_input.scale_px_per_mm
    holder_span_px = phase_input.holder_span_px
    phase_authority_px = phase_input.phase_authority_px
    max_observations = phase_input.max_observations

    normal = fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        phase_authority_px=phase_authority_px,
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        max_observations=max_observations,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        return _apply_final_lattice_contract(
            normal,
            phase_input,
            directly_observed_ordinals=(),
        )
    normal = _with_local_role_refinement(
        normal,
        observations,
        separator_bands,
    )
    assert normal.best is not None
    # Import here keeps the residual owner dependent on the canonical phase
    # types without creating a module import cycle.
    from .template_residual import derive_bounded_local_advances

    analysis = derive_bounded_local_advances(
        normal.best,
        tuple(
            item for item in observations if isinstance(item, BoundaryEdgeObservation)
        ),
        separator_bands,
    )
    directly_observed_ordinals = tuple(
        item.relation_ordinal for item in analysis.adjacency_facts
    )
    if analysis.unresolved_reason is not None:
        unresolved = replace(
            normal,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=analysis.unresolved_reason,
            failure_kind=PhaseFailureKind.LOCAL_ADVANCE_AMBIGUOUS,
            winner_basis=None,
            receipt=replace(
                normal.receipt,
                local_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        return _apply_final_lattice_contract(
            unresolved,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
    if not analysis.relations:
        measured = replace(
            normal,
            receipt=replace(
                normal.receipt,
                local_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        return _apply_final_lattice_contract(
            measured,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
    adjusted = fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        phase_authority_px=phase_authority_px,
        local_advance_relations=analysis.relations,
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        max_observations=max_observations,
    )
    adjusted = _with_local_role_refinement(
        adjusted,
        observations,
        separator_bands,
    )
    adjusted = _inherit_prior_lattice_fit_basis(adjusted, normal)
    adjusted = _aggregate_phase_work(
        adjusted,
        normal.receipt,
        local_relation_evaluation_count=analysis.evaluated_adjacency_count,
    )
    return _apply_final_lattice_contract(
        adjusted,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
    )


def account_prior_phase_fit(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Attach a prior calibration fit to the lane's auditable work receipt."""

    return _aggregate_phase_work(
        _inherit_prior_lattice_fit_basis(result, prior),
        prior.receipt,
    )
