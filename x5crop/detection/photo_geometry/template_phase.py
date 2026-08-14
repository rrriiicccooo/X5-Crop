"""Orchestrate bounded global fitting of one fixed sequence template."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from typing import Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceRelation,
    PhaseAnchor,
    TemplateSearchReceipt,
    TemplateSpec,
    ordered_template_roles,
)
from .template_phase_candidates import (
    _BoundFit,
    _clear_winner_basis,
    _facts,
    _fit_seed,
    _holder_center,
    _holder_limits,
    _positive,
    _prefixes,
    _rank,
    _relations,
    _sampling_equivalent,
    _with_separator_role_authority,
)
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseWinnerBasis,
)


def fit_template_phase(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
    template: TemplateSpec,
    *,
    separator_bands: Sequence[SeparatorBandObservation] = (),
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    phase_prior_px: FiniteInterval | None = None,
    local_advance_relations: Sequence[LocalAdvanceRelation] = (),
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit `{phase, W, pitch}` without building a chain product."""

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
    observations = _with_separator_role_authority(
        observations,
        separator_bands,
    )
    facts = _facts(observations)
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
    if scale_px_per_mm is not None:
        _positive(scale_px_per_mm)
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
    # Missing outer evidence is common.  Each registered edge may therefore
    # bind only to one of the two outer roles as a bounded fallback; it is not
    # expanded over all internal ordinals.
    for anchor in direct:
        if anchor.role_index in {None, 0}:
            seed_values.add((round(anchor.coordinate_px, 9), round(pitch0, 9)))
        if anchor.role_index in {None, len(roles) - 1}:
            seed_values.add((
                round(anchor.coordinate_px - template.direction * nominal_span, 9),
                round(pitch0, 9),
            ))
    if phase_prior_px is not None:
        seed_values.add((
            round(phase_prior_px.center, 9),
            round(pitch0, 9),
        ))
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
                _holder_center(holder_span_px),
                phase_prior_px,
                pitch_authority,
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
    runner = ordered[1] if len(ordered) > 1 else None
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
    elif _sampling_equivalent(best.fit, runner.fit):
        winner_basis = PhaseWinnerBasis.SAMPLING_EQUIVALENT_RUNNER
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
    )
    receipt.validate_bounds()
    return replace(result, receipt=receipt)


def fit_template_phase_with_local_advance(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
    separator_bands: tuple[SeparatorBandObservation, ...],
    template: TemplateSpec,
    *,
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    phase_prior_px: FiniteInterval | None = None,
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit the normal template, then allow one directly proved suffix shift."""

    normal = fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        phase_prior_px=phase_prior_px,
        max_observations=max_observations,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        return normal
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
        phase_prior_px=phase_prior_px,
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


__all__ = [
    "account_prior_phase_fit",
    "fit_template_phase",
    "fit_template_phase_with_local_advance",
]
