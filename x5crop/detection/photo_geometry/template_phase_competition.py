"""Bounded sequence phase competition."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from typing import Callable, Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import (
    BoundaryEdgeObservation,
    OuterMaterialBoundaryObservation,
    SeparatorBandObservation,
)
from .template_contact import ContactEdgeObservation
from .template_overlap import OverlapEdgePairObservation
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    OverlapRelation,
    SeparatorRelation,
    SequenceBindingUse,
    SequenceFit,
    TemplateSearchReceipt,
    TemplateSpec,
    adjacency_relation_required_bindings,
    adjacency_prefix_positions,
    ordered_template_roles,
)
from .template_adjacency_coverage import assess_adjacency_observation_coverage
from .template_adjacency_topology import unbound_registered_adjacency_counterevidence
from .template_direct_role_authority import assess_direct_role_binding_authorities
from .template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
    PhaseWinnerBasis,
    _TerminalPhaseDiagnostic,
)
from .template_native_retention import select_native_phase_retention
from .template_source_domain import PhaseSourceDomain, source_clipped_terminal_roles
from .template_source_clipped import select_source_clipped_phase_retention
from .template_nominal_grid_model import CalibratedNominalGridPrior
from . import (
    template_phase_candidate_model as _candidate_model,
    template_phase_fitting as _fitting,
    template_phase_observations as _observations,
    template_phase_projection as _projection,
    template_phase_state as _state,
)


def _unseparated_completion_competitor(
    best: _candidate_model._BoundFit,
    candidates: Sequence[_candidate_model._BoundFit],
) -> int | None:
    """Check every discrete interpretation without materializing completions.

    Continuous merging can add anchors from several partial fits. Ranking a
    merged winner against an uncompleted runner compares a support total to a
    lower bound. Static identity groups provide an intentionally loose upper
    bound over connected phase and role-interval components. Coordinate conflicts can
    only reduce support. Sorting plus indexed passes avoids pairwise scans and
    Cartesian products; an interval gap cannot be crossed by continuous merges.
    """

    def identity(fit: SequenceFit) -> tuple[object, ...]:
        return (
            fit.template,
            fit.lattice_parameter_fit_basis,
            fit.calibrated_nominal_grid_fit_state,
            fit.phase_lattice_fit.integer_slot_offset,
            fit.adjacency_relations,
        )

    groups: dict[tuple[object, ...], list[int]] = {}
    for index, candidate in enumerate(candidates):
        groups.setdefault(identity(candidate.fit), []).append(index)
    # A role bound in every member can never lose its identity in a merge.
    # Partition on these shared roles before taking loose support unions, so
    # evidence from an irreconcilable observed endpoint cannot inflate a rival.
    partitions: dict[tuple[int, tuple[ObservationId, ...]], list[int]] = {}
    for group_index, indices in enumerate(groups.values()):
        common_roles = [
            role for role, binding in enumerate(candidates[indices[0]].fit.role_bindings)
            if binding is not None
        ]
        for index in indices[1:]:
            common_roles = [
                role for role in common_roles
                if candidates[index].fit.role_bindings[role] is not None
            ]
        for index in indices:
            signature = []
            for role in common_roles:
                binding = candidates[index].fit.role_bindings[role]
                assert binding is not None
                signature.append(binding.observation_id)
            partitions.setdefault((group_index, tuple(signature)), []).append(index)
    groups.clear()
    bounds: dict[int, tuple[int, float, int]] = {}
    for indices in partitions.values():
        components = [indices]
        for role in range(-1, len(candidates[indices[0]].fit.role_bindings)):
            refined: list[list[int]] = []
            for members in components:
                if len(members) == 1:
                    refined.append(members)
                    continue
                intervals = {
                    index: (
                        candidates[index].fit.phase_lattice_fit.absolute_phase_interval_px
                        if role == -1
                        else candidates[index].fit.model_full_role_intervals_px[role]
                    )
                    for index in members
                }
                if role >= 0:
                    identity_hulls: dict[ObservationId, FiniteInterval] = {}
                    for index in members:
                        binding = candidates[index].fit.role_bindings[role]
                        if binding is not None:
                            previous = identity_hulls.get(binding.observation_id)
                            identity_hulls[binding.observation_id] = (
                                intervals[index] if previous is None
                                else _state._interval_hull(previous, intervals[index])
                            )
                    for index in members:
                        binding = candidates[index].fit.role_bindings[role]
                        if binding is not None:
                            # Same coordinate identity may merge even when its
                            # model intervals differ. Its hull can then bridge
                            # an unbound candidate, so retain that possibility.
                            intervals[index] = identity_hulls[binding.observation_id]
                component: list[int] = []
                maximum = -float("inf")
                for index in sorted(members, key=lambda item: intervals[item].minimum):
                    interval = intervals[index]
                    if component and interval.minimum > maximum:
                        refined.append(component)
                        component = []
                        maximum = -float("inf")
                    component.append(index)
                    maximum = max(maximum, interval.maximum)
                refined.append(component)
            components = refined
        for component in components:
            locations = {
                location for index in component
                for location in candidates[index].fit.phase_support_locations
            }
            coverage = max(candidates[index].fit.phase_support_coverage for index in component)
            bound = (len(locations), coverage, len(component))
            for member in component:
                bounds[member] = bound
    for index, candidate in enumerate(candidates):
        fit = candidate.fit
        # A late interval bridge can make previously discrete records mergeable
        # with the final best. They may add mutually conflicting identities or
        # extend its required hull; continuity alone does not absorb either fact.
        if _state._continuous_state_is_absorbed(best.fit, fit):
            continue
        support_count, coverage, count = bounds[index]
        if count == 1:
            if _clear_winner_basis(best, candidate) is None:
                return index
            continue
        if best.fit.phase_support_count > support_count:
            continue
        if (
            best.fit.phase_support_count == support_count
            and best.fit.phase_support_coverage >= coverage + 0.35
        ):
            continue
        # A completion's residual cannot be assumed positive. Its lower bound
        # is zero, so residual separation cannot reject it without a full fit.
        return index
    return None


def _candidate_respects_holder(
    fit: SequenceFit,
    *,
    holder_span_px: FiniteInterval | None,
    holder_slack_px: float,
) -> bool:
    """Keep the canonical competition's original holder admission."""

    limits = _observations._holder_limits(holder_span_px)
    positions = fit.model_role_positions_px
    return limits is None or (
        min(positions) >= limits[0] - holder_slack_px
        and max(positions) <= limits[1] + holder_slack_px
    )


def _candidate_respects_holder_or_terminal_source(
    fit: SequenceFit,
    *,
    holder_span_px: FiniteInterval | None,
    holder_slack_px: float,
    source_domain: PhaseSourceDomain | None,
) -> bool:
    """Admit extra true source-terminal fits only for independent Review."""

    if _candidate_respects_holder(
        fit, holder_span_px=holder_span_px, holder_slack_px=holder_slack_px,
    ):
        return True
    if source_domain is None:
        return False
    return source_clipped_terminal_roles(fit, source_domain) is not None


def fit_template_phase(
    observations: Sequence[BoundaryEdgeObservation],
    template: TemplateSpec,
    *,
    separator_bands: Sequence[SeparatorBandObservation] = (),
    outer_material_boundaries: Sequence[
        OuterMaterialBoundaryObservation
    ] = (),
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    source_domain: PhaseSourceDomain | None = None,
    phase_authority_px: FiniteInterval | None = None,
    adjacency_relations: Sequence[AdjacencyRelation] = (),
    contact_edge_observations: Sequence[ContactEdgeObservation] = (),
    overlap_edge_pair_observations: Sequence[
        OverlapEdgePairObservation
    ] = (),
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet] = (),
    calibrated_nominal_grid_prior: CalibratedNominalGridPrior | None = None,
    phase_anchor_authority_ceiling: (
        tuple[tuple[int, ObservationId], ...] | None
    ) = None,
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit `{phase, W, pitch}` without building a chain product."""

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
    if source_domain is not None:
        if not isinstance(source_domain, PhaseSourceDomain):
            raise TypeError("phase source domain must be typed")
        source_domain.validate_registration(
            holder_span_px,
            tuple(sequence_measurement_sets),
        )
    registered_observations = tuple(observations)
    separator_support = _observations.prepare_phase_separator_support(
        registered_observations,
        separator_bands,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    phase_separator_bands = separator_support.bands
    separator_support_ids = separator_support.resolution.edge_component_ids
    observations = separator_support.observations
    facts = _observations._facts(
        observations,
        separator_support_ids=separator_support_ids,
        registered_trace_positions_px=(
            sequence_measurement_sets[0].query.trace_positions_px
            if sequence_measurement_sets else ()
        ),
    )
    direct = tuple(item for item in facts if item.direct)
    separator_pairs = _observations._separator_pair_facts(
        phase_separator_bands,
        direct,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    roles = ordered_template_roles(template.count)
    if phase_anchor_authority_ceiling is not None:
        if (
            phase_anchor_authority_ceiling
            != tuple(sorted(set(phase_anchor_authority_ceiling)))
            or any(
                not 0 <= role_index < len(roles)
                or not isinstance(observation_id, ObservationId)
                for role_index, observation_id
                in phase_anchor_authority_ceiling
            )
            or len({item[0] for item in phase_anchor_authority_ceiling})
            != len(phase_anchor_authority_ceiling)
        ):
            raise ValueError("phase-anchor authority ceiling is invalid")
    relations = _observations._relations(adjacency_relations, template.count)
    contact_edges = tuple(contact_edge_observations)
    if any(
        not isinstance(item, ContactEdgeObservation)
        for item in contact_edges
    ):
        raise TypeError("phase contact observations must be typed")
    overlap_pairs = tuple(overlap_edge_pair_observations)
    if any(
        not isinstance(item, OverlapEdgePairObservation)
        for item in overlap_pairs
    ):
        raise TypeError("phase overlap observations must be typed")
    base = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=0,
        role_binding_count=0,
        adjacency_relation_evaluation_count=len(relations),
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
        None if scale_px_per_mm is None else _candidate_model._positive(scale_px_per_mm)
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
    prefixes = adjacency_prefix_positions(relations, template.count)
    width0 = width.center
    pitch0 = pitch_authority.center
    coordinates = tuple(item.coordinate_px for item in direct)
    nominal_span = (
        width0
        + max(0, template.count - 1) * pitch0
        + prefixes[-1]
    )
    span_window = max(3.0, pitch0 * 0.35)
    maximum_hypotheses = max(1, len(facts)) * max(6, len(roles))
    seed_registration_overflow = False
    seed_values: dict[
        tuple[float, float, tuple[AdjacencyRelation, ...]],
        _candidate_model._PhaseSeed | None,
    ] = {}
    nonseparator_required_bindings = adjacency_relation_required_bindings(
        tuple(
            relation
            for relation in relations
            if not isinstance(relation, SeparatorRelation)
        )
    )
    effective_phase_anchor_authority_ceiling = (
        None
        if phase_anchor_authority_ceiling is None
        else frozenset(
            {
                *phase_anchor_authority_ceiling,
                *nonseparator_required_bindings,
            }
        )
    )

    def prepare_seed(seed: _candidate_model._PhaseSeed) -> _candidate_model._PhaseSeed | None:
        if nonseparator_required_bindings:
            try:
                seed = replace(
                    seed,
                    required_bindings=tuple(
                        sorted(
                            {
                                *seed.required_bindings,
                                *nonseparator_required_bindings,
                            },
                            key=lambda item: (item[0], str(item[1])),
                        )
                    ),
                )
            except ValueError:
                return None
        return seed

    def register_seed(seed: _candidate_model._PhaseSeed) -> None:
        nonlocal seed_registration_overflow
        seed = prepare_seed(seed)
        if seed is None:
            return
        key = (seed.phase_px, seed.pitch_px, seed.adjacency_relations)
        if key not in seed_values:
            if len(seed_values) >= maximum_hypotheses:
                seed_registration_overflow = True
                return
            seed_values[key] = seed
            return
        current = seed_values[key]
        if current is None:
            return
        merged = set(current.required_bindings) | set(seed.required_bindings)
        role_to_observation: dict[int, ObservationId] = {}
        for role_index, observation_id in merged:
            if (
                role_index in role_to_observation
                and role_to_observation[role_index] != observation_id
            ):
                seed_values[key] = None
                return
            role_to_observation[role_index] = observation_id
        try:
            seed_values[key] = _candidate_model._PhaseSeed(
                seed.phase_px,
                seed.pitch_px,
                tuple(
                    sorted(merged, key=lambda item: (item[0], str(item[1])))
                ),
                seed.adjacency_relations,
            )
        except ValueError:
            seed_values[key] = None

    def generate_seeds(register_seed: Callable[[_candidate_model._PhaseSeed], None]) -> None:
        existing_contact = any(
            isinstance(item, ContactRelation) for item in relations
        )
        existing_overlap = any(
            isinstance(item, OverlapRelation) for item in relations
        )
        ordinary_topology = not (existing_contact or existing_overlap)
        if ordinary_topology:
            for seed in _observations._separator_phase_seeds(
                    phase_separator_bands,
                    direct,
                    roles,
                    template,
                    width=width0,
                    pitch=pitch0,
                    prefixes=prefixes,
                ):
                register_seed(replace(seed, adjacency_relations=relations))
        if not relations or existing_contact:
            for seed in _observations._contact_phase_seeds(
                contact_edges,
                direct,
                roles,
                template,
                width=width,
                pitch=pitch_authority,
                base_relations=relations,
            ):
                register_seed(seed)
        if not relations or existing_overlap:
            for seed in _observations._overlap_phase_seeds(
                overlap_pairs,
                direct,
                roles,
                template,
                width=width,
                pitch=pitch_authority,
                base_relations=relations,
            ):
                register_seed(seed)
        # Count-one templates have no pitch relation.  Their START and END seeds
        # already close the fixed-width pair below; treating every nearby END as a
        # second full-span origin would merge distinct physical edge alternatives
        # into one seed identity.
        if not ordinary_topology:
            pass
        elif template.count == 1:
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
                        _candidate_model._PhaseSeed(
                            round(first.coordinate_px, 9),
                            round(derived_pitch, 9),
                            (
                                (roles[0].role_index, first.observation_id),
                                (roles[-1].role_index, last.observation_id),
                            ),
                            relations,
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
                        _candidate_model._PhaseSeed(
                            round(first.coordinate_px, 9),
                            round(derived_pitch, 9),
                            (
                                (roles[0].role_index, first.observation_id),
                                (roles[-1].role_index, last.observation_id),
                            ),
                            relations,
                        )
                    )
        # Missing or dark outer frames are common.  A direct role-qualified edge
        # therefore seeds every compatible indexed role.  The pixel observation
        # remains the phase authority; the template contributes only the finite
        # ordinal alternatives.  Different ordinal mappings survive as discrete
        # placements and can never be averaged or selected by coarse support.
        for anchor in direct if ordinary_topology else ():
            for role in roles:
                if (
                    anchor.qualified_anchor_roles
                    and role.role not in anchor.qualified_anchor_roles
                ):
                    continue
                relative = role.slot_index * pitch0 + prefixes[role.slot_index]
                if role.role == BoundaryRole.END:
                    relative += width0
                register_seed(
                    _candidate_model._PhaseSeed(
                        round(
                            anchor.coordinate_px
                            - template.direction * relative,
                            9,
                        ),
                        round(pitch0, 9),
                        ((role.role_index, anchor.observation_id),),
                        relations,
                    )
                )
        if phase_authority_px is not None and ordinary_topology:
            register_seed(
                _candidate_model._PhaseSeed(
                    round(phase_authority_px.center, 9),
                    round(pitch0, 9),
                    adjacency_relations=relations,
                )
            )
    generate_seeds(register_seed)
    retained_seeds = {
        seed: None for seed in seed_values.values() if seed is not None
    }

    def retain_conflicting_seed(seed: _candidate_model._PhaseSeed) -> None:
        nonlocal seed_registration_overflow
        seed = prepare_seed(seed)
        if seed is None:
            return
        key = (seed.phase_px, seed.pitch_px, seed.adjacency_relations)
        if key not in seed_values or seed_values[key] is not None:
            return
        if seed in retained_seeds:
            return
        if len(retained_seeds) >= maximum_hypotheses:
            seed_registration_overflow = True
            return
        retained_seeds[seed] = None

    # Replay the same deterministic generators only when a geometric bucket
    # contains incompatible coordinate identities. Compatible buckets retain
    # their original union. No Cartesian product or new pixel query is needed.
    if not seed_registration_overflow and any(
        seed is None for seed in seed_values.values()
    ):
        generate_seeds(retain_conflicting_seed)
    seeds = tuple(retained_seeds)
    seed_peak_bytes = (len(seed_values) + len(seeds)) * len(roles) * 32
    seed_values.clear()
    retained_seeds.clear()
    if seed_registration_overflow:
        rejected_seed_count = maximum_hypotheses + 1
        receipt = TemplateSearchReceipt(
            observation_count=len(facts),
            role_count=len(roles),
            phase_lookup_count=rejected_seed_count,
            role_binding_count=0,
            adjacency_relation_evaluation_count=len(relations),
            local_refinement_lookup_count=0,
            local_refinement_binding_count=0,
            phase_hypothesis_count=rejected_seed_count,
            phase_offset_lookup_count=rejected_seed_count,
            direct_observation_count=len(direct),
            inferred_role_count=0,
            peak_temporary_bytes=seed_peak_bytes,
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
    # The admission scan is at most R coordinates per existing fitted seed:
    # O(H * R), without new hypotheses, queries, lookups or fit passes.
    matching_index = _fitting._PhaseMatchingIndex(direct, roles, separator_pairs)
    local_candidates = tuple(
        value
        for value in (
            _fitting._fit_seed(
                seed,
                direct,
                separator_pairs,
                roles,
                template,
                seed.adjacency_relations,
                pitch_authority,
                phase_authority_px,
                fit_residual_limit_px,
                effective_phase_anchor_authority_ceiling,
                matching_index=matching_index,
            )
            for seed in sorted(
                seeds,
                key=lambda item: (
                    item.phase_px,
                    item.pitch_px,
                    tuple(map(repr, item.adjacency_relations)),
                    tuple(
                        (role_index, str(observation_id))
                        for role_index, observation_id in item.required_bindings
                    ),
                ),
            )
        )
        if value is not None
        and _candidate_respects_holder_or_terminal_source(
            value.fit,
            holder_span_px=holder_span_px,
            holder_slack_px=width0 * 0.04,
            source_domain=source_domain,
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
    del matching_index
    # A binding tuple does not identify its joint state, protection intervals
    # or later local-role lookup. Only identical complete fits are duplicates.
    candidates = tuple(dict.fromkeys(local_candidates))
    measurement_sets = tuple(sequence_measurement_sets)
    candidate_authorities = (
        assess_direct_role_binding_authorities(
            tuple(item.fit for item in candidates),
            registered_observations,
            tuple(separator_bands),
            measurement_sets,
            outer_material_boundaries=tuple(
                outer_material_boundaries
            ),
        )
        if candidates and measurement_sets
        else ()
    )
    from .template_residual import derive_candidate_separator_relations

    overlap_validation_peak_bytes = 0

    def project_record(
        index: int,
        candidate: _candidate_model._BoundFit,
    ) -> tuple[
        _candidate_model._BoundFit,
        _candidate_model._BoundFit | None,
        PhaseCandidateAuthorityProjection,
    ]:
        nonlocal overlap_validation_peak_bytes
        candidate_relations = derive_candidate_separator_relations(
            candidate.fit,
            candidate_authorities[index],
            tuple(phase_separator_bands),
            pitch_authority,
        )
        projected, projection = _projection.project_candidate_to_authorized_direct_roles(
            candidate,
            candidate_authorities[index],
            facts,
            separator_pairs,
            roles,
            template,
            candidate_relations,
            pitch_authority,
            phase_authority_px,
            fit_residual_limit_px,
            calibrated_nominal_grid_prior,
            effective_phase_anchor_authority_ceiling,
        )
        if (
            projected is not None
            and (phase_separator_bands or overlap_pairs and projection.basis
                 == PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID)
        ):
            coverage = assess_adjacency_observation_coverage(
                projected.fit,
                measurement_sets,
                directly_observed_ordinals=(),
            )
            overlap_validation_peak_bytes = max(
                overlap_validation_peak_bytes,
                128 * (len(facts) + len(overlap_pairs) + len(phase_separator_bands) + len(coverage))
                + sum(
                    64 + 32 * (
                        len(trace.covering_query_ids)
                        + len(trace.covered_intervals_px)
                    )
                    for item in coverage
                    for trace in item.trace_coverage
                ),
            )
            conflicts = unbound_registered_adjacency_counterevidence(
                projected.fit,
                registered_observations,
                coverage,
                overlap_pairs if projection.basis == PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID else (),
                separator_bands=tuple(phase_separator_bands),
                separator_support=separator_support.resolution,
                direct_role_authority=projection.input_direct_role_authority,
            )
            if conflicts:
                projected = None
                projection = replace(
                    projection,
                    outcome=(
                        PhaseCandidateProjectionOutcome.ADJACENCY_MATERIAL_CONFLICT
                        if any(isinstance(pair, SeparatorBandObservation) for _, pair in conflicts)
                        else PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT
                    ),
                    basis=None,
                    reason=(
                        "phase mapping conflicts with unique "
                        "registered adjacency partners: "
                        + ", ".join(
                            f"adjacency {ordinal}={pair.observation_id}"
                            for ordinal, pair in conflicts
                        )
                    ),
                )
        return candidate, projected, projection

    projection_records: tuple[
        tuple[_candidate_model._BoundFit, _candidate_model._BoundFit | None, PhaseCandidateAuthorityProjection],
        ...,
    ] = (
        tuple(
            project_record(index, candidate)
            for index, candidate in enumerate(candidates)
        )
        if candidate_authorities
        else ()
    )
    # Admission through the true-source domain does not grant a new ordinal
    # interpretation a place in canonical competition or the native pool.
    # Filter on the original input fit, before authority projection can move it.
    canonical_projection_records = tuple(
        record for record in projection_records
        if _candidate_respects_holder(
            record[0].fit, holder_span_px=holder_span_px,
            holder_slack_px=width0 * 0.04,
        )
    )
    native_retention = select_native_phase_retention(
        canonical_projection_records, template=template,
    )
    source_clipped_retention = select_source_clipped_phase_retention(
        projection_records, template=template, source_domain=source_domain,
    )
    if not source_clipped_retention.record_scan_count:
        source_clipped_retention = None

    def respects_phase_anchor_authority_ceiling(
        candidate: _candidate_model._BoundFit,
    ) -> bool:
        if effective_phase_anchor_authority_ceiling is None:
            return True
        return all(
            (role_index, binding.observation_id)
            in effective_phase_anchor_authority_ceiling
            for role_index, binding in enumerate(candidate.fit.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        )

    eligible_records: tuple[
        tuple[_candidate_model._BoundFit, PhaseCandidateAuthorityProjection | None], ...
    ] = (
        tuple(
            (projected, projection)
            for _input, projected, projection in canonical_projection_records
            if projected is not None
            and respects_phase_anchor_authority_ceiling(projected)
        )
        if measurement_sets
        else tuple(
            (candidate, None)
            for candidate in candidates
            if _candidate_respects_holder(
                candidate.fit, holder_span_px=holder_span_px,
                holder_slack_px=width0 * 0.04,
            )
            and respects_phase_anchor_authority_ceiling(candidate)
        )
    )
    terminal_records = tuple(
        (input_candidate, projection)
        for input_candidate, projected, projection in canonical_projection_records
        if projected is None
    )
    phase_anchor_authority_exceeded = any(
        projected is not None
        and not respects_phase_anchor_authority_ceiling(projected)
        for _input, projected, _projection in canonical_projection_records
    )

    def record_rank(
        record: tuple[_candidate_model._BoundFit, PhaseCandidateAuthorityProjection | None],
    ) -> tuple[object, ...]:
        candidate, projection = record
        return (
            *_candidate_model._rank(candidate),
            (
                3
                if projection is None
                or projection.basis
                == PhaseCandidateProjectionBasis.DIRECT_BINDINGS
                or projection.basis
                == PhaseCandidateProjectionBasis.DIRECT_SEPARATOR_GAP
                else 2
                if projection.basis
                == PhaseCandidateProjectionBasis.DIRECT_RANK_THREE
                else 1
                if projection.basis
                == PhaseCandidateProjectionBasis.CALIBRATED_NOMINAL_GRID
                else 0
            ),
            0 if projection is None else -len(projection.projected_out_bindings),
            ()
            if projection is None
            else tuple(
                (item.role_index, str(item.observation_id))
                for item in projection.projected_out_bindings
            ),
        )

    # Equal projected geometry can still have different authority provenance.
    # Continuous merging and selection below own any further reduction.
    canonical_records = tuple(dict.fromkeys(eligible_records))
    compatible = tuple(
        record for record in canonical_records if record[0].residual_compatible
    )
    incompatible = tuple(
        record for record in canonical_records if not record[0].residual_compatible
    )

    ordered = tuple(sorted(compatible, key=record_rank, reverse=True))
    best_record = ordered[0] if ordered else None
    best = None if best_record is None else best_record[0]
    best_projection = None if best_record is None else best_record[1]
    runner_record: (
        tuple[_candidate_model._BoundFit, PhaseCandidateAuthorityProjection | None] | None
    ) = None
    if len(ordered) > 1:
        discrete: list[
            tuple[_candidate_model._BoundFit, PhaseCandidateAuthorityProjection | None]
        ] = []
        for candidate_record in ordered[1:]:
            assert best is not None
            candidate = candidate_record[0]
            if _state._same_continuous_placement(best.fit, candidate.fit):
                best = _state._merge_continuous_placement(best, candidate)
            else:
                discrete.append(candidate_record)
        runner_record = discrete[0] if discrete else None
    runner = None if runner_record is None else runner_record[0]
    runner_projection = None if runner_record is None else runner_record[1]
    receipt = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=len(seeds),
        role_binding_count=len(seeds) * len(roles),
        adjacency_relation_evaluation_count=len(relations),
        local_refinement_lookup_count=0,
        local_refinement_binding_count=(
            0
            if best is None
            else len(best.fit.local_refinement_observation_ids)
        ),
        phase_hypothesis_count=len(seeds),
        phase_offset_lookup_count=len(seeds),
        direct_observation_count=len(direct),
        inferred_role_count=(0 if best is None else len(best.fit.unbound_role_indices)),
        peak_temporary_bytes=max(
            seed_peak_bytes,
            len(seeds) * len(roles) * 32 + len(ordered) * len(roles) * 96,
            overlap_validation_peak_bytes,
        ) + (len(roles) * 128 if terminal_records else 0)
        + 8 * len(canonical_projection_records),
        candidate_direct_role_authority_evaluation_count=len(
            candidate_authorities
        ),
        candidate_direct_role_authority_terminal_count=sum(
            projected is None
            for _input, projected, _projection in projection_records
        ),
        candidate_direct_role_authority_role_check_count=sum(
            len(item.facts) for item in candidate_authorities
        ),
        candidate_direct_role_projection_evaluation_count=len(
            projection_records
        ),
        candidate_direct_role_projection_success_count=sum(
            projection.outcome
            in {
                PhaseCandidateProjectionOutcome.PROJECTED,
                PhaseCandidateProjectionOutcome.DIRECT_SEPARATOR_REFIT,
            }
            for _input, _projected, projection in projection_records
        ),
        candidate_direct_role_projection_binding_count=sum(
            len(projection.projected_out_bindings)
            for _input, _projected, projection in projection_records
            if projection.outcome == PhaseCandidateProjectionOutcome.PROJECTED
        ),
        candidate_nominal_grid_solve_count=sum(
            projection.outcome
            in {
                PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
                PhaseCandidateProjectionOutcome
                .CALIBRATED_NOMINAL_GRID_CONFLICT,
            }
            for _input, _projected, projection in projection_records
        ),
        candidate_nominal_grid_solve_success_count=sum(
            projection.outcome
            == PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID
            for _input, _projected, projection in projection_records
        ),
    )
    receipt.validate_bounds()
    if best is None:
        if phase_anchor_authority_exceeded:
            return PhaseFitResult(
                template,
                None,
                None,
                PhaseFitStatus.UNRESOLVED,
                "direct separator refit exceeded pre-refit phase-anchor authority",
                receipt,
                direct_ids,
                PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
                _native_phase_retention=native_retention,
                _source_clipped_phase_retention=source_clipped_retention,
            )
        raw_compatible = tuple(
            sorted(
                (
                    (input_candidate, projection)
                    for input_candidate, projected, projection in canonical_projection_records
                    if projected is None and input_candidate.residual_compatible
                ),
                key=record_rank,
                reverse=True,
            )
        )
        if raw_compatible and measurement_sets:
            diagnostic_best, best_projection = raw_compatible[0]
            diagnostic_runner_record = next(
                (
                    (item, projection)
                    for pool in (
                        raw_compatible[1:],
                        sorted(terminal_records, key=record_rank, reverse=True),
                    )
                    for item, projection in pool
                    if not _state._same_continuous_placement(
                        diagnostic_best.fit,
                        item.fit,
                    )
                ),
                None,
            )
            diagnostic_runner = (
                None if diagnostic_runner_record is None
                else diagnostic_runner_record[0]
            )
            runner_projection = (
                None if diagnostic_runner_record is None
                else diagnostic_runner_record[1]
            )
            return PhaseFitResult(
                template=template,
                best=diagnostic_best.fit,
                runner_up=(
                    None if diagnostic_runner is None else diagnostic_runner.fit
                ),
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=best_projection.reason,
                receipt=replace(
                    receipt,
                    inferred_role_count=len(
                        diagnostic_best.fit.unbound_role_indices
                    ),
                ),
                registered_direct_observation_ids=direct_ids,
                failure_kind=_state._projection_failure_kind(
                    best_projection.outcome
                ),
                winner_basis=None,
                best_phase_candidate_authority_projection=best_projection,
                runner_phase_candidate_authority_projection=runner_projection,
                _native_phase_retention=native_retention,
                _source_clipped_phase_retention=source_clipped_retention,
            )
        # A bounded, anchored fit remains useful as a pre-Gate proposal even
        # when every complete interpretation carries direct residual
        # counterevidence.  Keep the strongest deterministic fit and one
        # discrete runner for diagnosis; the unresolved status and typed
        # mismatch continue to withhold candidate and auto authority.
        residual_counterevidence_records = tuple(
            sorted(
                (*canonical_records, *terminal_records),
                key=record_rank,
                reverse=True,
            )
        )
        if residual_counterevidence_records:
            diagnostic_best, best_projection = (
                residual_counterevidence_records[0]
            )
            diagnostic_runner_record = next(
                (
                    record
                    for record in residual_counterevidence_records[1:]
                    if not _state._same_continuous_placement(
                        diagnostic_best.fit,
                        record[0].fit,
                    )
                ),
                None,
            )
            diagnostic_runner = (
                None
                if diagnostic_runner_record is None
                else diagnostic_runner_record[0]
            )
            runner_projection = (
                None
                if diagnostic_runner_record is None
                else diagnostic_runner_record[1]
            )
            calibrated = (
                diagnostic_best.fit.calibrated_nominal_grid_fit_state
                is not None
            )
            return PhaseFitResult(
                template=template,
                best=diagnostic_best.fit,
                runner_up=(
                    None
                    if diagnostic_runner is None
                    else diagnostic_runner.fit
                ),
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=(
                    "all complete anchored phase fits exceed the direct "
                    "residual compatibility contract"
                ),
                receipt=replace(
                    receipt,
                    inferred_role_count=len(
                        diagnostic_best.fit.unbound_role_indices
                    ),
                ),
                registered_direct_observation_ids=direct_ids,
                failure_kind=PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
                winner_basis=None,
                retained_proposal_basis=(
                    PhaseRetainedProposalBasis
                    .CALIBRATED_NOMINAL_GRID_WITH_RESIDUAL_COUNTEREVIDENCE
                    if calibrated
                    else PhaseRetainedProposalBasis
                    .DIRECT_LATTICE_WITH_RESIDUAL_COUNTEREVIDENCE
                ),
                best_phase_candidate_authority_projection=best_projection,
                runner_phase_candidate_authority_projection=(
                    runner_projection
                ),
                _native_phase_retention=native_retention,
                _source_clipped_phase_retention=source_clipped_retention,
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
            _native_phase_retention=native_retention,
            _source_clipped_phase_retention=source_clipped_retention,
        )
    contradictory_runner_record = max(
        (
            record
            for record in (*incompatible, *terminal_records)
            for item in (record[0],)
            if (
                not item.residual_compatible
                or (
                    record[1] is not None
                    and record[1].outcome
                    == PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT
                    and record[1].input_direct_role_authority.state
                    == EvidenceState.SUPPORTED
                    and not record[1].projected_out_bindings
                )
            )
            and item.fit.phase_support_count > best.fit.phase_support_count
            and (
                not _state._same_continuous_placement(item.fit, best.fit)
                or not _state._intervals_overlap(
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
        key=record_rank,
        default=None,
    )
    contradictory_runner = (
        None
        if contradictory_runner_record is None
        else contradictory_runner_record[0]
    )
    if contradictory_runner is not None:
        runner = contradictory_runner
        runner_projection = contradictory_runner_record[1]
        winner_basis = None
    elif runner is None:
        rejected_runner = (
            max(
                (
                    record
                    for record in terminal_records
                    for candidate in (record[0],)
                    if not _state._same_continuous_placement(best.fit, candidate.fit)
                ),
                key=record_rank,
                default=None,
            )
            if measurement_sets
            else None
        )
        if rejected_runner is None:
            winner_basis = PhaseWinnerBasis.ONLY_PHYSICAL_FIT
        else:
            runner, runner_projection = rejected_runner
            winner_basis = PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY
    else:
        winner_basis = _clear_winner_basis(best, runner)
    if winner_basis is not None:
        competitor_index = _unseparated_completion_competitor(
            best, tuple(record[0] for record in ordered),
        )
        if competitor_index is not None:
            runner, runner_projection = ordered[competitor_index]
            winner_basis = None
    if winner_basis is not None:
        status = PhaseFitStatus.RESOLVED
        reason = None
        failure_kind = None
    else:
        status = PhaseFitStatus.AMBIGUOUS
        topology_ambiguous = (
            runner is not None
            and _state._topology_signature(best.fit)
            != _state._topology_signature(runner.fit)
            and bool(
                _state._topology_signature(best.fit)
                or _state._topology_signature(runner.fit)
            )
        )
        reason = (
            "multiple physically legal adjacency topologies remain"
            if topology_ambiguous
            else "higher-support direct evidence contradicts the selected fixed template"
            if contradictory_runner is not None
            else "runner-up is not clearly separated from the best template"
        )
        failure_kind = (
            PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS
            if topology_ambiguous
            else PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS
        )
    terminal_diagnostic_record = max(
        terminal_records, key=record_rank, default=None,
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
        best_phase_candidate_authority_projection=best_projection,
        runner_phase_candidate_authority_projection=runner_projection,
        _native_phase_retention=native_retention,
        _source_clipped_phase_retention=source_clipped_retention,
        _terminal_diagnostic=(
            None
            if terminal_diagnostic_record is None
            else _TerminalPhaseDiagnostic(
                terminal_diagnostic_record[0].fit,
                terminal_diagnostic_record[1],
            )
        ),
    )


def _clear_winner_basis(
    best: _candidate_model._BoundFit,
    runner: _candidate_model._BoundFit,
) -> PhaseWinnerBasis | None:
    left = best.fit
    right = runner.fit
    if best.residual_compatible and not runner.residual_compatible:
        return PhaseWinnerBasis.RESIDUAL_COMPATIBILITY
    if left.phase_support_count >= right.phase_support_count + 1:
        return PhaseWinnerBasis.INDEPENDENT_SUPPORT
    if (
        left.phase_support_count == right.phase_support_count
        and left.phase_support_coverage >= right.phase_support_coverage + 0.35
    ):
        return PhaseWinnerBasis.INDEPENDENT_COVERAGE
    if (
        left.phase_support_count == right.phase_support_count
        and left.phase_support_coverage >= right.phase_support_coverage - 0.1
        and right.residual_sum_px
        >= left.residual_sum_px
        + max(2.0, left.pitch_fit.canonical_frame_width_px * 0.05)
    ):
        return PhaseWinnerBasis.RESIDUAL_SEPARATION
    return None
