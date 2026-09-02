"""Orchestrate bounded global fitting of one fixed sequence template."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from typing import Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_contact import ContactEdgeObservation
from .template_overlap import OverlapEdgePairObservation
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    FrameWidthInferenceFailureKind,
    LatticeParameterFitBasis,
    OverlapRelation,
    SeparatorRelation,
    SequenceBindingUse,
    SequenceFit,
    SequenceRoleBinding,
    TemplateSearchReceipt,
    TemplateSpec,
    adjacency_relation_required_bindings,
    most_constrained_lattice_parameter_fit_basis,
    ordered_template_roles,
)
from .template_phase_candidates import (
    _BoundFit,
    _PhaseSeed,
    _clear_winner_basis,
    _contact_phase_seeds,
    _facts,
    _fit_seed,
    _holder_limits,
    _overlap_phase_seeds,
    _positive,
    _prefixes,
    project_candidate_to_authorized_direct_roles,
    _rank,
    _refine_local_role_bindings,
    _relations,
    _separator_pair_facts,
    _separator_phase_seeds,
    _with_separator_role_authority,
)
from .separator_material import normal_separator_material_bands
from .template_evidence import separator_support_authority
from .template_frame_width import (
    SourceFrameWidthAuthority,
    apply_correlated_frame_width_inference,
    apply_placement_source_frame_width,
    assess_placement_source_frame_width_topology,
)
from .template_adjacency_coverage import (
    AdjacencyCoverageState,
    assess_adjacency_observation_coverage,
)
from .template_adjacency_topology import (
    AdjacencyContinuityKind,
    observe_adjacency_continuity,
)
from .template_lattice_authority import (
    assess_global_lattice_authority,
    direct_role_constraint_rank,
)
from .template_direct_role_authority import (
    assess_direct_role_binding_authorities,
    assess_direct_role_binding_authority,
    intrinsic_direct_role_authority_bases,
)
from .template_outer_frame_authority import (
    assess_outer_frame_observation_authority,
)
from .template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionBasis,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
    PhaseWinnerBasis,
    TemplatePhaseCandidateCompetition,
    TemplatePhaseInput,
)
from .template_nominal_grid_authority import (
    failed_nominal_grid_evidence,
    nominal_grid_evidence_id,
)
from .template_nominal_grid_model import (
    CalibratedNominalGridEvidence,
    CalibratedNominalGridPrior,
    NominalGridFailureKind,
)


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
    relations = _relations(adjacency_relations, template.count)
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
    seed_values: dict[
        tuple[float, float, tuple[AdjacencyRelation, ...]],
        _PhaseSeed | None,
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

    def register_seed(seed: _PhaseSeed) -> None:
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
                return
        key = (seed.phase_px, seed.pitch_px, seed.adjacency_relations)
        if key not in seed_values:
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
            seed_values[key] = _PhaseSeed(
                seed.phase_px,
                seed.pitch_px,
                tuple(
                    sorted(merged, key=lambda item: (item[0], str(item[1])))
                ),
                seed.adjacency_relations,
            )
        except ValueError:
            seed_values[key] = None

    existing_contact = any(
        isinstance(item, ContactRelation) for item in relations
    )
    existing_overlap = any(
        isinstance(item, OverlapRelation) for item in relations
    )
    ordinary_topology = not (existing_contact or existing_overlap)
    if ordinary_topology:
        for seed in _separator_phase_seeds(
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
        for seed in _contact_phase_seeds(
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
        for seed in _overlap_phase_seeds(
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
                    _PhaseSeed(
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
                    _PhaseSeed(
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
                    relations,
                )
            )
    if phase_authority_px is not None and ordinary_topology:
        register_seed(
            _PhaseSeed(
                round(phase_authority_px.center, 9),
                round(pitch0, 9),
                adjacency_relations=relations,
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
            adjacency_relation_evaluation_count=len(relations),
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
                seed.adjacency_relations,
                pitch_authority,
                phase_authority_px,
                fit_residual_limit_px,
                effective_phase_anchor_authority_ceiling,
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
        tuple[
            int,
            tuple[ObservationId | None, ...],
            tuple[AdjacencyRelation, ...],
        ],
        _BoundFit,
    ] = {}
    for candidate in local_candidates:
        key = (
            candidate.fit.phase_lattice_fit.integer_slot_offset,
            candidate.fit.binding_observation_ids,
            candidate.fit.adjacency_relations,
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
    from .template_residual import derive_candidate_separator_relations

    def project_record(
        index: int,
        candidate: _BoundFit,
    ) -> tuple[
        _BoundFit,
        _BoundFit | None,
        PhaseCandidateAuthorityProjection,
    ]:
        candidate_relations = derive_candidate_separator_relations(
            candidate.fit,
            candidate_authorities[index],
            tuple(phase_separator_bands),
            pitch_authority,
        )
        projected, projection = project_candidate_to_authorized_direct_roles(
            candidate,
            candidate_authorities[index],
            direct,
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
        return candidate, projected, projection

    projection_records: tuple[
        tuple[_BoundFit, _BoundFit | None, PhaseCandidateAuthorityProjection],
        ...,
    ] = (
        tuple(
            project_record(index, candidate)
            for index, candidate in enumerate(candidates)
        )
        if candidate_authorities
        else ()
    )

    def respects_phase_anchor_authority_ceiling(
        candidate: _BoundFit,
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
        tuple[_BoundFit, PhaseCandidateAuthorityProjection | None], ...
    ] = (
        tuple(
            (projected, projection)
            for _input, projected, projection in projection_records
            if projected is not None
            and respects_phase_anchor_authority_ceiling(projected)
        )
        if measurement_sets
        else tuple(
            (candidate, None)
            for candidate in candidates
            if respects_phase_anchor_authority_ceiling(candidate)
        )
    )
    terminal_records = tuple(
        (input_candidate, projection)
        for input_candidate, projected, projection in projection_records
        if projected is None
    )
    phase_anchor_authority_exceeded = any(
        projected is not None
        and not respects_phase_anchor_authority_ceiling(projected)
        for _input, projected, _projection in projection_records
    )

    def record_rank(
        record: tuple[_BoundFit, PhaseCandidateAuthorityProjection | None],
    ) -> tuple[object, ...]:
        candidate, projection = record
        return (
            *_rank(candidate),
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

    projected_by_binding: dict[
        tuple[
            int,
            tuple[ObservationId | None, ...],
            tuple[AdjacencyRelation, ...],
        ],
        tuple[_BoundFit, PhaseCandidateAuthorityProjection | None],
    ] = {}
    for record in eligible_records:
        candidate, _projection = record
        key = (
            candidate.fit.phase_lattice_fit.integer_slot_offset,
            candidate.fit.binding_observation_ids,
            candidate.fit.adjacency_relations,
        )
        current = projected_by_binding.get(key)
        if current is None or record_rank(record) > record_rank(current):
            projected_by_binding[key] = record
    canonical_records = tuple(projected_by_binding.values())
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
        tuple[_BoundFit, PhaseCandidateAuthorityProjection | None] | None
    ) = None
    if len(ordered) > 1:
        discrete: list[
            tuple[_BoundFit, PhaseCandidateAuthorityProjection | None]
        ] = []
        for candidate_record in ordered[1:]:
            assert best is not None
            candidate = candidate_record[0]
            if _same_continuous_placement(best.fit, candidate.fit):
                best = _merge_continuous_placement(best, candidate)
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
        peak_temporary_bytes=len(seeds) * len(roles) * 32,
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
            )
        raw_compatible = tuple(
            sorted(
                (
                    (input_candidate, projection)
                    for input_candidate, projected, projection in projection_records
                    if projected is None and input_candidate.residual_compatible
                ),
                key=record_rank,
                reverse=True,
            )
        )
        if raw_compatible and measurement_sets:
            diagnostic_best, best_projection = raw_compatible[0]
            diagnostic_runner = next(
                (
                    item
                    for item, _projection in raw_compatible[1:]
                    if not _same_continuous_placement(
                        diagnostic_best.fit,
                        item.fit,
                    )
                ),
                None,
            )
            runner_projection = next(
                (
                    projection
                    for item, projection in raw_compatible[1:]
                    if item is diagnostic_runner
                ),
                None,
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
                failure_kind=_projection_failure_kind(
                    best_projection.outcome
                ),
                winner_basis=None,
                best_phase_candidate_authority_projection=best_projection,
                runner_phase_candidate_authority_projection=runner_projection,
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
                    if not _same_continuous_placement(
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
    contradictory_runner_record = max(
        (
            record
            for record in incompatible
            for item in (record[0],)
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
                    if not _same_continuous_placement(best.fit, candidate.fit)
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
        status = PhaseFitStatus.RESOLVED
        reason = None
        failure_kind = None
    else:
        status = PhaseFitStatus.AMBIGUOUS
        topology_ambiguous = (
            runner is not None
            and _topology_signature(best.fit)
            != _topology_signature(runner.fit)
            and bool(
                _topology_signature(best.fit)
                or _topology_signature(runner.fit)
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
    )


def _aggregate_phase_work(
    result: PhaseFitResult,
    *prior: TemplateSearchReceipt,
    adjacency_relation_evaluation_count: int | None = None,
) -> PhaseFitResult:
    receipts = (*prior, result.receipt)
    receipt = TemplateSearchReceipt(
        observation_count=result.receipt.observation_count,
        role_count=result.receipt.role_count,
        phase_lookup_count=sum(item.phase_lookup_count for item in receipts),
        role_binding_count=sum(item.role_binding_count for item in receipts),
        adjacency_relation_evaluation_count=(
            sum(
                item.adjacency_relation_evaluation_count
                for item in receipts
            )
            if adjacency_relation_evaluation_count is None
            else adjacency_relation_evaluation_count
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
        candidate_direct_role_authority_terminal_count=sum(
            item.candidate_direct_role_authority_terminal_count
            for item in receipts
        ),
        candidate_direct_role_authority_role_check_count=sum(
            item.candidate_direct_role_authority_role_check_count
            for item in receipts
        ),
        candidate_direct_role_projection_evaluation_count=sum(
            item.candidate_direct_role_projection_evaluation_count
            for item in receipts
        ),
        candidate_direct_role_projection_success_count=sum(
            item.candidate_direct_role_projection_success_count
            for item in receipts
        ),
        candidate_direct_role_projection_binding_count=sum(
            item.candidate_direct_role_projection_binding_count
            for item in receipts
        ),
        candidate_nominal_grid_solve_count=sum(
            item.candidate_nominal_grid_solve_count for item in receipts
        ),
        candidate_nominal_grid_solve_success_count=sum(
            item.candidate_nominal_grid_solve_success_count
            for item in receipts
        ),
        selected_direct_role_projection_evaluation_count=sum(
            item.selected_direct_role_projection_evaluation_count
            for item in receipts
        ),
        selected_direct_role_projection_binding_count=sum(
            item.selected_direct_role_projection_binding_count
            for item in receipts
        ),
        selected_nominal_grid_solve_count=sum(
            item.selected_nominal_grid_solve_count for item in receipts
        ),
        selected_nominal_grid_solve_success_count=sum(
            item.selected_nominal_grid_solve_success_count
            for item in receipts
        ),
    )
    receipt.validate_bounds()
    return replace(result, receipt=receipt)


def _with_local_role_refinement(
    result: PhaseFitResult,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet] = (),
    *,
    frame_width_authority_px: FiniteInterval | None = None,
    additional_fit_pass: bool = False,
    excluded_role_bindings: frozenset[
        tuple[int, ObservationId]
    ] = frozenset(),
) -> PhaseFitResult:
    if result.status != PhaseFitStatus.RESOLVED or result.best is None:
        return result
    authority_ids = (
        frozenset(
            intrinsic_direct_role_authority_bases(
                tuple(observations),
                tuple(sequence_measurement_sets),
            )
        )
        if sequence_measurement_sets
        else frozenset()
    )
    refinement = _refine_local_role_bindings(
        result.best,
        observations,
        separator_bands,
        intrinsic_coordinate_authority_ids=authority_ids,
        frame_width_authority_px=frame_width_authority_px,
        excluded_role_bindings=excluded_role_bindings,
    )
    receipt = replace(
        result.receipt,
        fit_pass_count=(
            result.receipt.fit_pass_count + int(additional_fit_pass)
        ),
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


def _refine_selected_roles_with_candidate_elimination(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    excluded_role_bindings: frozenset[
        tuple[int, ObservationId]
    ] = frozenset(),
) -> PhaseFitResult:
    """Reject a winner contradicted only after selected local refinement.

    Candidate ranking is bounded before selected-only local refinement.  A
    newly attached line can therefore complete an exact reversed
    END/material/START pair that was not present in the candidate authority
    ledger.  Reassess that one selected fit, eliminate it through the existing
    typed direct-role contradiction, and promote only the already retained,
    authority-eligible runner.  At most two selected fits are refined; no new
    observation or TIFF query is created.
    """

    current = result
    exclusions = excluded_role_bindings
    for candidate_index in range(2):
        current = _with_local_role_refinement(
            current,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
            additional_fit_pass=candidate_index > 0,
            excluded_role_bindings=exclusions,
        )
        if (
            current.status != PhaseFitStatus.RESOLVED
            or current.best is None
            or not phase_input.sequence_measurement_sets
        ):
            return current
        authority = assess_direct_role_binding_authority(
            current.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
        )
        if authority.state != EvidenceState.CONTRADICTED:
            return current
        projection = PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
            basis=None,
            projected_out_bindings=(),
            retained_direct_constraint_rank=direct_role_constraint_rank(
                current.best,
                authority.supported_role_indices,
            ),
            reason=(
                authority.reason or "direct-role evidence is contradicted"
            ),
        )
        receipt = replace(
            current.receipt,
            selected_direct_role_projection_evaluation_count=(
                current.receipt
                .selected_direct_role_projection_evaluation_count
                + 1
            ),
        )
        receipt.validate_bounds()
        runner_projection = (
            current.runner_phase_candidate_authority_projection
        )
        if (
            candidate_index > 0
            or current.runner_up is None
            or runner_projection is None
            or not runner_projection.eligible
        ):
            return replace(
                current,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=projection.reason,
                failure_kind=(
                    PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
                ),
                winner_basis=None,
                best_phase_candidate_authority_projection=projection,
                receipt=receipt,
            )
        exclusions = frozenset(
            (item.role_index, item.observation_id)
            for item in authority.facts
            if item.state == EvidenceState.CONTRADICTED
        )
        current = replace(
            current,
            best=current.runner_up,
            runner_up=current.best,
            status=PhaseFitStatus.RESOLVED,
            ambiguity_reason=None,
            failure_kind=None,
            winner_basis=PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
            best_phase_candidate_authority_projection=runner_projection,
            runner_phase_candidate_authority_projection=projection,
            eliminated_candidate_authority_projections=(
                *current.eliminated_candidate_authority_projections,
                projection,
            ),
            receipt=receipt,
            global_lattice_authority=None,
            calibrated_nominal_grid_evidence=None,
            adjacency_observation_coverage=(),
            adjacency_continuity_observations=(),
            direct_role_binding_authority=None,
            outer_frame_observation_authority=None,
        )
    raise AssertionError("selected candidate elimination exceeded its bound")


def _eliminated_candidate_role_bindings(
    result: PhaseFitResult,
) -> frozenset[tuple[int, ObservationId]]:
    """Return exact role/edge assignments rejected by hard counterevidence."""

    return frozenset(
        (fact.role_index, fact.observation_id)
        for projection in result.eliminated_candidate_authority_projections
        for fact in projection.input_direct_role_authority.facts
        if fact.state == EvidenceState.CONTRADICTED
    )


def _project_selected_late_local_refinements(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None = None,
    allow_direct_rank: bool = False,
) -> PhaseFitResult:
    """Yield unsupported late local bindings back to the selected lattice.

    Candidate projection runs before local relation analysis.  Local
    refinement must remain free to bind registered lines while topology is
    being derived, but a short line that still lacks coordinate authority
    after that analysis cannot become output geometry merely because it was
    added later.  Reuse the same bounded projection owner on the selected
    discrete identity whether its remaining coordinates close a direct-rank
    lattice or require the calibrated Grid.  The line remains typed projection
    provenance and counterevidence; it cannot acquire authority from the time
    at which it was attached.
    """

    if (
        result.status != PhaseFitStatus.RESOLVED
        or result.best is None
        or not phase_input.sequence_measurement_sets
        or (
            result.best.calibrated_nominal_grid_fit_state is None
            and not allow_direct_rank
        )
    ):
        return result
    authority = assess_direct_role_binding_authority(
        result.best,
        phase_input.observations,
        phase_input.separator_bands,
        phase_input.sequence_measurement_sets,
        authorized_source_frame_width_px=(
            None
            if source_frame_width_authority is None
            or source_frame_width_authority.state != EvidenceState.SUPPORTED
            else source_frame_width_authority.width_px
        ),
    )
    if authority.state != EvidenceState.UNAVAILABLE:
        return result
    unsupported_bindings = tuple(
        result.best.role_bindings[role_index]
        for role_index in authority.unsupported_role_indices
    )
    if not unsupported_bindings or any(
        binding is None
        or binding.use != SequenceBindingUse.LOCAL_REFINEMENT
        for binding in unsupported_bindings
    ):
        return result

    template = phase_input.template
    phase_separator_bands = normal_separator_material_bands(
        phase_input.separator_bands,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    separator_support_ids = separator_support_authority(
        phase_separator_bands
    )
    qualified_observations = _with_separator_role_authority(
        phase_input.observations,
        phase_input.separator_bands,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    facts = _facts(
        qualified_observations,
        separator_support_ids=separator_support_ids,
    )
    direct = tuple(item for item in facts if item.direct)
    separator_pairs = _separator_pair_facts(
        phase_separator_bands,
        direct,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap_pitch = FiniteInterval(
        width.minimum + template.gap_prior_px.minimum,
        width.maximum + template.gap_prior_px.maximum,
    )
    pitch = FiniteInterval(
        max(gap_pitch.minimum, template.pitch_px.minimum),
        min(gap_pitch.maximum, template.pitch_px.maximum),
    )
    fit_residual_limit_px = (
        None
        if phase_input.scale_px_per_mm is None
        else PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
            phase_input.scale_px_per_mm.maximum
        )
    )
    projected, projection = project_candidate_to_authorized_direct_roles(
        _BoundFit(result.best, True),
        authority,
        direct,
        separator_pairs,
        ordered_template_roles(template.count),
        template,
        result.best.adjacency_relations,
        pitch,
        phase_input.phase_authority_px,
        fit_residual_limit_px,
        phase_input.calibrated_nominal_grid_prior,
        frozenset(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(result.best.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        ),
    )
    nominal_solve = projection.outcome in {
        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
        PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT,
    }
    receipt = replace(
        result.receipt,
        selected_direct_role_projection_evaluation_count=(
            result.receipt.selected_direct_role_projection_evaluation_count
            + 1
        ),
        selected_direct_role_projection_binding_count=(
            result.receipt.selected_direct_role_projection_binding_count
            + len(projection.projected_out_bindings)
        ),
        selected_nominal_grid_solve_count=(
            result.receipt.selected_nominal_grid_solve_count
            + int(nominal_solve)
        ),
        selected_nominal_grid_solve_success_count=(
            result.receipt.selected_nominal_grid_solve_success_count
            + int(
                projection.outcome
                == PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID
            )
        ),
        inferred_role_count=(
            result.receipt.inferred_role_count
            if projected is None
            else len(projected.fit.unbound_role_indices)
        ),
    )
    receipt.validate_bounds()
    if projected is None:
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=projection.reason,
            failure_kind=_projection_failure_kind(projection.outcome),
            winner_basis=None,
            best_phase_candidate_authority_projection=projection,
            receipt=receipt,
        )
    return replace(
        result,
        best=projected.fit,
        best_phase_candidate_authority_projection=projection,
        receipt=receipt,
        global_lattice_authority=None,
        calibrated_nominal_grid_evidence=None,
        adjacency_observation_coverage=(),
        adjacency_continuity_observations=(),
        direct_role_binding_authority=None,
        outer_frame_observation_authority=None,
    )


def refine_template_phase_with_source_frame_width(
    result: PhaseFitResult,
    authority: SourceFrameWidthAuthority,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet],
) -> PhaseFitResult:
    """Bind only roles uniquely selected by an independent source-level W.

    The discrete placement must already be resolved and source W independently
    closed either by complete Frames or by a retained full-rank direct
    lattice. This selected-candidate-only pass may bind a registered native
    edge pair that the broader format interval could not distinguish. An
    ambiguous retained proposal consumes W for its existing missing roles but
    does not run this additional local rebinding pass.
    """

    if authority.state != EvidenceState.SUPPORTED:
        return result
    if result.status != PhaseFitStatus.RESOLVED:
        return result
    if result.best is None:
        raise ValueError("resolved source W requires one placement")
    if not result.best.unbound_role_indices:
        return result
    if (
        not authority.matches_placement(result.best)
        or authority.width_px is None
    ):
        raise ValueError("source W authority belongs to a different placement")
    return _with_local_role_refinement(
        result,
        observations,
        separator_bands,
        sequence_measurement_sets,
        frame_width_authority_px=authority.width_px,
        additional_fit_pass=True,
        excluded_role_bindings=_eliminated_candidate_role_bindings(result),
    )


def _attach_selected_candidate_authorities(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    directly_observed_ordinals: tuple[int, ...],
    source_frame_width_authority: SourceFrameWidthAuthority | None = None,
) -> PhaseFitResult:
    """Measure selected-candidate authorities without changing its status."""

    direct_role_authority = (
        None
        if result.best is None or not phase_input.sequence_measurement_sets
        else assess_direct_role_binding_authority(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
            authorized_source_frame_width_px=(
                None
                if source_frame_width_authority is None
                or source_frame_width_authority.state
                != EvidenceState.SUPPORTED
                else source_frame_width_authority.width_px
            ),
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
    continuity = (
        ()
        if result.best is None
        else observe_adjacency_continuity(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            coverage,
            phase_input.overlap_edge_pair_observations,
        )
    )
    outer_authority = (
        None
        if result.best is None
        else assess_outer_frame_observation_authority(result.best)
    )
    nominal_evidence = None
    nominal_state = (
        None
        if result.best is None
        else result.best.calibrated_nominal_grid_fit_state
    )
    if nominal_state is not None:
        unobserved_frames = result.best.completely_unobserved_frame_ordinals
        inferred = tuple(
            item for item in coverage if item.normal_inference_required
        )
        ordinals = tuple(item.relation_ordinal for item in inferred)
        query_ids = tuple(
            sorted(
                {
                    query_id
                    for item in inferred
                    for query_id in item.covering_query_ids
                }
            )
        )
        if direct_role_authority is not None and (
            direct_role_authority.state == EvidenceState.CONTRADICTED
        ):
            nominal_evidence = failed_nominal_grid_evidence(
                nominal_state,
                inferred_adjacency_ordinals=ordinals,
                covering_query_ids=query_ids,
                state=EvidenceState.CONTRADICTED,
                failure_kind=NominalGridFailureKind.COUNTEREVIDENCE,
                reason=(
                    direct_role_authority.reason
                    or "direct role evidence contradicts the nominal Grid"
                ),
            )
        elif any(
            item.state != AdjacencyCoverageState.COMPLETE for item in inferred
        ):
            nominal_evidence = failed_nominal_grid_evidence(
                nominal_state,
                inferred_adjacency_ordinals=ordinals,
                covering_query_ids=query_ids,
                state=EvidenceState.UNAVAILABLE,
                failure_kind=(
                    NominalGridFailureKind.ADJACENCY_COVERAGE_INCOMPLETE
                ),
                reason=(
                    "one or more nominal adjacency corridors were not fully "
                    "covered by registered measurements"
                ),
            )
        else:
            nominal_evidence = CalibratedNominalGridEvidence(
                evidence_id=nominal_grid_evidence_id(
                    nominal_state,
                    ordinals,
                    unobserved_frames,
                    query_ids,
                ),
                state=EvidenceState.SUPPORTED,
                prior_id=nominal_state.prior_id,
                phase_anchor_role_indices=(
                    nominal_state.phase_anchor_role_indices
                ),
                phase_anchor_observation_ids=(
                    nominal_state.phase_anchor_observation_ids
                ),
                inferred_adjacency_ordinals=ordinals,
                unobserved_frame_ordinals=unobserved_frames,
                covering_query_ids=query_ids,
                failure_kind=None,
                reason=None,
            )
    result = replace(
        result,
        global_lattice_authority=authority,
        calibrated_nominal_grid_evidence=nominal_evidence,
        adjacency_observation_coverage=coverage,
        adjacency_continuity_observations=continuity,
        direct_role_binding_authority=direct_role_authority,
        outer_frame_observation_authority=outer_authority,
    )
    return result


def _apply_final_lattice_contract(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    directly_observed_ordinals: tuple[int, ...],
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> PhaseFitResult:
    """Require direct-role, global, and local authority for one placement."""

    # A local native-edge pass or late authority projection may rebuild the
    # continuous fit after source W was first closed. The source-W owner must
    # narrow that final retained placement again before any authority or
    # inference ledger is assessed; this is idempotent, does not register new
    # evidence and never changes ambiguity status or removes the runner.
    if (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
        and result.best is not None
    ):
        result = apply_placement_source_frame_width(
            result,
            source_frame_width_authority,
        )
    result = _attach_selected_candidate_authorities(
        result,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
        source_frame_width_authority=source_frame_width_authority,
    )
    if (
        result.best is not None
        and (
            result.best.calibrated_nominal_grid_fit_state is None
            or (
                source_frame_width_authority is not None
                and source_frame_width_authority.state
                == EvidenceState.SUPPORTED
            )
        )
    ):
        assessed_best = apply_correlated_frame_width_inference(
            result.best,
            source_frame_width_authority=source_frame_width_authority,
            direct_role_authority=result.direct_role_binding_authority,
            sequence_edges=phase_input.observations,
            projected_counterevidence_role_indices=tuple(
                item.role_index
                for item in (
                    ()
                    if result.best_phase_candidate_authority_projection is None
                    else result.best_phase_candidate_authority_projection
                    .projected_out_bindings
                )
            ),
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
    if (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
    ):
        # Only an authorized correlated-W inference transfers boundary
        # ownership. Assess that final ledger, not every role that happened
        # to be unbound earlier in the placement-bound flow.
        result = assess_placement_source_frame_width_topology(
            result,
            source_frame_width_authority,
        )
    result = _attach_selected_candidate_authorities(
        result,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
        source_frame_width_authority=source_frame_width_authority,
    )
    direct_role_authority = result.direct_role_binding_authority
    authority = result.global_lattice_authority
    nominal_evidence = result.calibrated_nominal_grid_evidence
    coverage = result.adjacency_observation_coverage
    continuity = result.adjacency_continuity_observations
    outer_authority = result.outer_frame_observation_authority
    inferred = tuple(item for item in coverage if item.normal_inference_required)
    continuity_unresolved = next(
        (
            item
            for item in continuity
            if item.kind == AdjacencyContinuityKind.UNRESOLVED
        ),
        None,
    )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and continuity_unresolved is not None
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                continuity_unresolved.reason
                or "adjacency continuity is unresolved"
            ),
            failure_kind=PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED,
            winner_basis=None,
        )
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
        and nominal_evidence is None
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
        and nominal_evidence is None
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
            nominal_evidence is None
            and
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
                    else "direct-lattice W cannot discard a registered local "
                    "boundary and then authorize missing roles"
                    if width_inference.failure_kind
                    == FrameWidthInferenceFailureKind
                    .DIRECT_LATTICE_COUNTEREVIDENCE
                    else "missing opposite Frame roles require one independently "
                    "closed source-level common W"
                ),
                failure_kind=(
                    PhaseFailureKind.FRAME_WIDTH_INFERENCE_UNAVAILABLE
                ),
                winner_basis=None,
            )
    return result


def retain_pre_local_phase_proposal(
    result: PhaseFitResult,
    *,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Keep one complete positioned phase after local evidence rejects eligibility.

    ``prior`` is the uniquely positioned direct or calibrated-Grid solution
    that exists before local refinement or adjacency continuity introduces
    counterevidence. A later refit may therefore withhold the candidate, but it
    must not erase that already complete pre-Gate proposal. The retained fit
    never changes ``result.status`` or ``result.failure_kind`` and cannot
    acquire candidate or automatic-approval authority.
    """

    if result.template != prior.template:
        raise ValueError("retained phase proposal crosses template identity")
    if (
        result.best is not None
        or result.status == PhaseFitStatus.BOUND_EXCEEDED
        or prior.status != PhaseFitStatus.RESOLVED
        or prior.best is None
    ):
        return result
    calibrated = prior.best.calibrated_nominal_grid_fit_state is not None
    return replace(
        result,
        best=prior.best,
        runner_up=prior.runner_up,
        best_phase_candidate_authority_projection=(
            prior.best_phase_candidate_authority_projection
        ),
        runner_phase_candidate_authority_projection=(
            prior.runner_phase_candidate_authority_projection
        ),
        retained_proposal_basis=(
            PhaseRetainedProposalBasis
            .CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE
            if calibrated
            else PhaseRetainedProposalBasis
            .DIRECT_LATTICE_BEFORE_LOCAL_COUNTEREVIDENCE
        ),
    )


def fit_template_phase_candidate_with_adjacency_relations(
    phase_input: TemplatePhaseInput,
) -> TemplatePhaseCandidateCompetition:
    """Resolve discrete/local competition before placement-bound source W."""

    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError(
            "adjacency-relation phase fit requires TemplatePhaseInput"
        )
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
        contact_edge_observations=phase_input.contact_edge_observations,
        overlap_edge_pair_observations=(
            phase_input.overlap_edge_pair_observations
        ),
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        calibrated_nominal_grid_prior=(
            phase_input.calibrated_nominal_grid_prior
        ),
        max_observations=max_observations,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        assessed = _attach_selected_candidate_authorities(
            normal,
            phase_input,
            directly_observed_ordinals=(),
        )
        return TemplatePhaseCandidateCompetition(assessed, ())
    pre_local_proposal = normal
    normal = _refine_selected_roles_with_candidate_elimination(
        normal,
        phase_input,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        assessed = _attach_selected_candidate_authorities(
            normal,
            phase_input,
            directly_observed_ordinals=(),
        )
        assessed = retain_pre_local_phase_proposal(
            assessed,
            prior=pre_local_proposal,
        )
        return TemplatePhaseCandidateCompetition(assessed, ())
    assert normal.best is not None
    # Import here keeps the residual owner dependent on the canonical phase
    # types without creating a module import cycle.
    from .template_residual import (
        AdjacencyRelationFailureKind,
        derive_adjacency_relations,
    )

    initial_coverage = assess_adjacency_observation_coverage(
        normal.best,
        phase_input.sequence_measurement_sets,
        directly_observed_ordinals=(),
    )
    continuity = observe_adjacency_continuity(
        normal.best,
        tuple(
            item
            for item in observations
            if isinstance(item, BoundaryEdgeObservation)
        ),
        separator_bands,
        initial_coverage,
        phase_input.overlap_edge_pair_observations,
    )

    analysis = derive_adjacency_relations(
        normal.best,
        continuity,
    )
    directly_observed_ordinals = tuple(
        item.relation_ordinal for item in analysis.adjacency_facts
    )
    if analysis.unresolved_reason is not None:
        unresolved = replace(
            normal,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=analysis.unresolved_reason,
            failure_kind=(
                PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                if analysis.failure_kind
                == AdjacencyRelationFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                else PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                if analysis.failure_kind
                == AdjacencyRelationFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                else PhaseFailureKind.ADJACENCY_RELATION_AMBIGUOUS
            ),
            winner_basis=None,
            receipt=replace(
                normal.receipt,
                adjacency_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        assessed = _attach_selected_candidate_authorities(
            unresolved,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
        return TemplatePhaseCandidateCompetition(
            assessed,
            directly_observed_ordinals,
        )
    if not analysis.relations:
        measured = replace(
            normal,
            receipt=replace(
                normal.receipt,
                adjacency_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        measured = _project_selected_late_local_refinements(
            measured,
            phase_input,
        )
        assessed = _attach_selected_candidate_authorities(
            measured,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
        return TemplatePhaseCandidateCompetition(
            assessed,
            directly_observed_ordinals,
        )
    adjusted = fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        phase_authority_px=phase_authority_px,
        adjacency_relations=analysis.relations,
        contact_edge_observations=phase_input.contact_edge_observations,
        overlap_edge_pair_observations=(
            phase_input.overlap_edge_pair_observations
        ),
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        calibrated_nominal_grid_prior=(
            phase_input.calibrated_nominal_grid_prior
        ),
        phase_anchor_authority_ceiling=tuple(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(normal.best.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        ),
        max_observations=max_observations,
    )
    adjusted = replace(
        adjusted,
        eliminated_candidate_authority_projections=(
            normal.eliminated_candidate_authority_projections
        ),
    )
    adjusted = _refine_selected_roles_with_candidate_elimination(
        adjusted,
        phase_input,
        excluded_role_bindings=_eliminated_candidate_role_bindings(normal),
    )
    adjusted = _inherit_prior_lattice_fit_basis(adjusted, normal)
    adjusted = _aggregate_phase_work(
        adjusted,
        normal.receipt,
        adjacency_relation_evaluation_count=(
            analysis.evaluated_adjacency_count
        ),
    )
    adjusted = _project_selected_late_local_refinements(
        adjusted,
        phase_input,
    )
    assessed = _attach_selected_candidate_authorities(
        adjusted,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
    )
    assessed = retain_pre_local_phase_proposal(
        assessed,
        prior=normal,
    )
    return TemplatePhaseCandidateCompetition(
        assessed,
        directly_observed_ordinals,
    )


def finalize_template_phase_candidate(
    candidate: TemplatePhaseCandidateCompetition,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> PhaseFitResult:
    """Apply placement-bound lattice and inference contracts to one competition."""

    if not isinstance(candidate, TemplatePhaseCandidateCompetition):
        raise TypeError("phase finalization requires a candidate competition")
    if candidate.result.template != phase_input.template:
        raise ValueError("phase candidate and final input use different templates")
    result = _apply_final_lattice_contract(
        candidate.result,
        phase_input,
        directly_observed_ordinals=(
            candidate.directly_observed_adjacency_ordinals
        ),
        source_frame_width_authority=source_frame_width_authority,
    )
    if (
        result.status != PhaseFitStatus.UNRESOLVED
        or result.failure_kind
        != PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
    ):
        return result
    projected = _project_selected_late_local_refinements(
        candidate.result,
        phase_input,
        source_frame_width_authority=source_frame_width_authority,
        allow_direct_rank=True,
    )
    return _apply_final_lattice_contract(
        projected,
        phase_input,
        directly_observed_ordinals=(
            candidate.directly_observed_adjacency_ordinals
        ),
        source_frame_width_authority=source_frame_width_authority,
    )


def fit_template_phase_with_adjacency_relations(
    phase_input: TemplatePhaseInput,
) -> PhaseFitResult:
    """Run canonical candidate competition and final lattice assessment."""

    candidate = fit_template_phase_candidate_with_adjacency_relations(
        phase_input
    )
    return finalize_template_phase_candidate(
        candidate,
        phase_input,
        source_frame_width_authority=None,
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
