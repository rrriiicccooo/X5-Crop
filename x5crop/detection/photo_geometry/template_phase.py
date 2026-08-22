"""Orchestrate bounded global fitting of one fixed sequence template."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from typing import Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import OUTPUT_PROTECTION_SPEC
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceRelation,
    SequenceFit,
    TemplateSearchReceipt,
    TemplateSpec,
    ordered_template_roles,
)
from .template_phase_candidates import (
    _AnchorFact,
    _BoundFit,
    _clear_winner_basis,
    _facts,
    _fit_seed,
    _holder_limits,
    _positive,
    _prefixes,
    _rank,
    _relations,
    _separator_phase_seeds,
    _with_separator_role_authority,
)
from .template_evidence import separator_support_authority
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


def _same_continuous_placement(
    left: SequenceFit,
    right: SequenceFit,
    separator_support_ids: dict[ObservationId, ObservationId],
) -> bool:
    """Distinguish one joint feasible placement from a discrete runner."""

    def same_role_state(
        left_interval: FiniteInterval,
        right_interval: FiniteInterval,
        left_id: ObservationId | None,
        right_id: ObservationId | None,
    ) -> bool:
        if _intervals_overlap(left_interval, right_interval):
            return True
        if left_id is None or right_id is None:
            return False
        # Several measured edges can describe the two sides or texture inside
        # one directly observed separator.  Once the ordinal lattice is the
        # same, those alternatives are uncertainty about one role position,
        # not two photo placements.  The connected material identity is the
        # authority for that statement; proximity or edge strength is not.
        left_support = separator_support_ids.get(left_id)
        return (
            left_support is not None
            and left_support == separator_support_ids.get(right_id)
        )

    return (
        left.template == right.template
        and left.phase_lattice_fit.integer_slot_offset
        == right.phase_lattice_fit.integer_slot_offset
        and left.local_advance_relations == right.local_advance_relations
        and left.independent_support_ids == right.independent_support_ids
        and _intervals_overlap(
            left.phase_lattice_fit.absolute_phase_interval_px,
            right.phase_lattice_fit.absolute_phase_interval_px,
        )
        and all(
            same_role_state(
                left_interval,
                right_interval,
                left_id,
                right_id,
            )
            for left_interval, right_interval, left_id, right_id in zip(
                left.role_full_position_intervals_px,
                right.role_full_position_intervals_px,
                left.role_observation_ids,
                right.role_observation_ids,
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
    separator_support_ids: dict[ObservationId, ObservationId],
) -> _BoundFit:
    """Retain the selected canonical state and expose the full joint hull."""

    left = selected.fit
    right = alternative.fit
    if not _same_continuous_placement(
        left,
        right,
        separator_support_ids,
    ):
        raise ValueError("cannot merge discrete phase placements")
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
        role_positions_px=tuple(
            _interval_hull(left_interval, right_interval)
            for left_interval, right_interval in zip(
                left.role_positions_px,
                right.role_positions_px,
                strict=True,
            )
        ),
        role_full_position_intervals_px=tuple(
            _interval_hull(left_interval, right_interval)
            for left_interval, right_interval in zip(
                left.role_full_position_intervals_px,
                right.role_full_position_intervals_px,
                strict=True,
            )
        ),
        direct_observation_ids=tuple(
            sorted(
                set(left.direct_observation_ids)
                | set(right.direct_observation_ids)
            )
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
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit `{phase, W, pitch}` without building a chain product."""

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
    separator_support_ids = separator_support_authority(
        tuple(separator_bands)
    )
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
    roles = ordered_template_roles(template.count)
    relations = _relations(local_advance_relations, template.count)
    base = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=0,
        role_binding_count=0,
        local_relation_evaluation_count=len(relations),
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
    seed_values: set[tuple[float, float]] = set()
    seed_values.update(
        _separator_phase_seeds(
            separator_bands,
            direct,
            roles,
            template,
            width=width0,
            pitch=pitch0,
            prefixes=prefixes,
        )
    )
    if template.direction > 0:
        for first in direct:
            target = first.coordinate_px + nominal_span
            insertion = bisect_left(coordinates, target)
            for index in (insertion - 2, insertion - 1, insertion, insertion + 1):
                if not 0 <= index < len(direct):
                    continue
                last = direct[index]
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
                seed_values.add((round(first.coordinate_px, 9), round(derived_pitch, 9)))
    else:
        for first in reversed(direct):
            target = first.coordinate_px - nominal_span
            insertion = bisect_left(coordinates, target)
            for index in (insertion - 2, insertion - 1, insertion, insertion + 1):
                if not 0 <= index < len(direct):
                    continue
                last = direct[index]
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
                seed_values.add((round(first.coordinate_px, 9), round(derived_pitch, 9)))
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
            seed_values.add(
                (
                    round(
                        anchor.coordinate_px
                        - template.direction * relative,
                        9,
                    ),
                    round(pitch0, 9),
                )
            )
    if phase_authority_px is not None:
        seed_values.add((
            round(phase_authority_px.center, 9),
            round(pitch0, 9),
        ))
    maximum_hypotheses = len(facts) * max(6, len(roles))
    if len(seed_values) > maximum_hypotheses:
        receipt = TemplateSearchReceipt(
            observation_count=len(facts),
            role_count=len(roles),
            phase_lookup_count=len(seed_values),
            role_binding_count=0,
            local_relation_evaluation_count=len(relations),
            phase_hypothesis_count=len(seed_values),
            phase_offset_lookup_count=len(seed_values),
            direct_observation_count=len(direct),
            inferred_role_count=0,
            peak_temporary_bytes=len(seed_values) * len(roles) * 32,
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
    candidates = tuple(
        value
        for value in (
            _fit_seed(
                seed_phase,
                seed_pitch,
                direct,
                roles,
                template,
                relations,
                pitch_authority,
                fit_residual_limit_px,
            )
            for seed_phase, seed_pitch in sorted(seed_values)
        )
        if value is not None
        and (
            holder_limits is None
            or (
                min(value.fit.canonical_role_positions_px)
                >= holder_limits[0] - width0 * 0.04
                and max(value.fit.canonical_role_positions_px)
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
    by_binding: dict[tuple[int, tuple[ObservationId | None, ...]], _BoundFit] = {}
    for candidate in candidates:
        key = (
            candidate.fit.phase_lattice_fit.integer_slot_offset,
            candidate.fit.role_observation_ids,
        )
        current = by_binding.get(key)
        if current is None or _rank(candidate) > _rank(current):
            by_binding[key] = candidate
    ordered = tuple(sorted(by_binding.values(), key=_rank, reverse=True))
    best = ordered[0] if ordered else None
    if len(ordered) > 1:
        discrete: list[_BoundFit] = []
        original_best = ordered[0]
        for candidate in ordered[1:]:
            if _same_continuous_placement(
                original_best.fit,
                candidate.fit,
                separator_support_ids,
            ):
                best = _merge_continuous_placement(
                    best,
                    candidate,
                    separator_support_ids,
                )
            else:
                discrete.append(candidate)
        runner = discrete[0] if discrete else None
    else:
        runner = None
    receipt = TemplateSearchReceipt(
        observation_count=len(facts),
        role_count=len(roles),
        phase_lookup_count=len(seed_values),
        role_binding_count=len(seed_values) * len(roles),
        local_relation_evaluation_count=len(relations),
        phase_hypothesis_count=len(seed_values),
        phase_offset_lookup_count=len(seed_values),
        direct_observation_count=len(direct),
        inferred_role_count=(0 if best is None else len(best.fit.inferred_role_indices)),
        peak_temporary_bytes=len(seed_values) * len(roles) * 32,
    )
    receipt.validate_bounds()
    if best is None:
        return PhaseFitResult(
            template,
            None,
            None,
            PhaseFitStatus.UNRESOLVED,
            "no direct observation matched the fixed template",
            receipt,
            direct_ids,
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH,
        )
    if runner is None:
        winner_basis = PhaseWinnerBasis.ONLY_PHYSICAL_FIT
    else:
        winner_basis = _clear_winner_basis(best, runner)
    if winner_basis is not None:
        status = PhaseFitStatus.RESOLVED
        reason = None
    else:
        status = PhaseFitStatus.AMBIGUOUS
        reason = "runner-up is not clearly separated from the best template"
    return PhaseFitResult(
        template,
        best.fit,
        None if runner is None else runner.fit,
        status,
        reason,
        receipt,
        direct_ids,
        (
            None
            if status == PhaseFitStatus.RESOLVED
            else PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS
        ),
        winner_basis,
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
    )
    receipt.validate_bounds()
    return replace(result, receipt=receipt)


def fit_template_phase_with_local_advance(
    phase_input: TemplatePhaseInput,
) -> PhaseFitResult:
    """Fit the normal template, then allow one directly proved suffix shift."""

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
        max_observations=max_observations,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        return normal
    # Import here keeps the residual owner dependent on the canonical phase
    # types without creating a module import cycle.
    from .template_residual import (
        LocalAdvanceFailureKind,
        ResidualPattern,
        derive_bounded_local_advances,
    )

    analysis = derive_bounded_local_advances(
        normal.best,
        tuple(
            item for item in observations if isinstance(item, BoundaryEdgeObservation)
        ),
        separator_bands,
    )
    scale = (
        0.0
        if scale_px_per_mm is None
        else scale_px_per_mm.maximum
        if isinstance(scale_px_per_mm, PositiveInterval)
        else float(scale_px_per_mm)
    )
    normal_bleed_px = max(
        OUTPUT_PROTECTION_SPEC.sequence_bleed_frame_ratio
        * normal.best.pitch_fit.canonical_frame_width_px,
        OUTPUT_PROTECTION_SPEC.sequence_bleed_minimum_mm * scale,
    )
    direct_by_id = {
        item.observation_id: item
        for item in observations
        if isinstance(item, BoundaryEdgeObservation)
    }
    direct_role_misses = tuple(
        0.0
        if direct_by_id[identity].full_position_interval_px.contains(
            position,
            epsilon=1.0e-9,
        )
        else direct_by_id[identity].full_position_interval_px.minimum - position
        if position < direct_by_id[identity].full_position_interval_px.minimum
        else position - direct_by_id[identity].full_position_interval_px.maximum
        for position, identity in zip(
            normal.best.canonical_role_positions_px,
            normal.best.role_observation_ids,
            strict=True,
        )
        if identity is not None
    )
    normal_output_covers_direct_residuals = (
        not direct_role_misses
        or max(direct_role_misses) <= normal_bleed_px + 1.0e-7
    )
    if normal_output_covers_direct_residuals and (
        analysis.pattern == ResidualPattern.LOCAL_STEP
        or analysis.failure_kind == LocalAdvanceFailureKind.TOO_MANY_ANOMALIES
    ):
        # The normal placement is already unique, and its ordinary deterministic
        # bleed covers every direct sequence residual.  Small gap variation is
        # a validation fact, not permission to open another degree of freedom.
        # Contact/overlap and topology contradictions never use this stop.
        return replace(
            normal,
            receipt=replace(
                normal.receipt,
                local_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
    if analysis.unresolved_reason is not None:
        return replace(
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
    if not analysis.relations:
        return replace(
            normal,
            receipt=replace(
                normal.receipt,
                local_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
    adjusted = fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        phase_authority_px=phase_authority_px,
        local_advance_relations=analysis.relations,
        max_observations=max_observations,
    )
    return _aggregate_phase_work(
        adjusted,
        normal.receipt,
        local_relation_evaluation_count=analysis.evaluated_adjacency_count,
    )


def account_prior_phase_fit(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Attach a prior calibration fit to the lane's auditable work receipt."""

    return _aggregate_phase_work(result, prior.receipt)
