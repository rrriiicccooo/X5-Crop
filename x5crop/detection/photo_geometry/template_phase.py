"""Pure, bounded indexed phase fitting for fixed-format templates.

The solver registers each direct observation once, reflects it through the
finite theoretical role index, and retains only the best and runner-up fits.
It does not build a chain candidate product, dynamic-programming state, phase
grid, or top-K list.  Missing roles are inferred only after at least one
direct phase anchor has established the sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole
from .observation_types import BoundaryEdgeObservation
from .template_model import (
    LocalAdvanceRelation,
    PhaseAnchor,
    PhaseAuthority,
    PitchFit,
    SequenceFit,
    TemplateRole,
    TemplateSearchReceipt,
    TemplateSpec,
    ordered_template_roles,
)


class PhaseFitStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    BOUND_EXCEEDED = "bound_exceeded"


@dataclass(frozen=True)
class PhaseFitResult:
    """Best/runner-up metadata without pretending ambiguity is authority."""

    template: TemplateSpec
    best: SequenceFit | None
    runner_up: SequenceFit | None
    status: PhaseFitStatus
    ambiguity_reason: str | None
    receipt: TemplateSearchReceipt
    direct_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if self.status == PhaseFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved phase fit requires a best fit")
        if self.status == PhaseFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded phase fit cannot authorize a placement")
        if self.ambiguity_reason is not None and not self.ambiguity_reason:
            raise ValueError("phase ambiguity reason must not be empty")
        if len(set(self.direct_observation_ids)) != len(self.direct_observation_ids):
            raise ValueError("phase direct observations must be unique")

    @property
    def resolved(self) -> bool:
        return self.status == PhaseFitStatus.RESOLVED

    @property
    def ambiguous(self) -> bool:
        return self.status == PhaseFitStatus.AMBIGUOUS

    @property
    def placement(self) -> SequenceFit | None:
        """Only a clearly separated fit is placement authority."""

        return self.best if self.resolved else None


@dataclass(frozen=True)
class _Candidate:
    phase_interval_px: FiniteInterval
    source_observation_id: ObservationId | None
    source_role_index: int | None


def _interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("phase interval must be finite interval or number")


def _positive(value: PositiveInterval | FiniteInterval | float | int) -> PositiveInterval:
    if isinstance(value, PositiveInterval):
        return value
    interval = _interval(value)
    if interval.minimum <= 0.0:
        raise ValueError("phase scale must be positive")
    return PositiveInterval(interval.minimum, interval.maximum)


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum + right.minimum, left.maximum + right.maximum)


def _scale(interval: FiniteInterval, factor: int) -> FiniteInterval:
    if factor >= 0:
        return FiniteInterval(interval.minimum * factor, interval.maximum * factor)
    return FiniteInterval(interval.maximum * factor, interval.minimum * factor)


def _directed(interval: FiniteInterval, direction: int) -> FiniteInterval:
    return _scale(interval, direction)


def _subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum - right.maximum, left.maximum - right.minimum)


def _hull(intervals: Sequence[FiniteInterval]) -> FiniteInterval:
    if not intervals:
        raise ValueError("phase hull requires an interval")
    return FiniteInterval(
        min(item.minimum for item in intervals),
        max(item.maximum for item in intervals),
    )


def _intersection(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return FiniteInterval(minimum, maximum) if minimum <= maximum else None


def _distance(left: FiniteInterval, right: FiniteInterval) -> float:
    if left.maximum < right.minimum:
        return right.minimum - left.maximum
    if right.maximum < left.minimum:
        return left.minimum - right.maximum
    return 0.0


def _anchor_from_observation(
    observation: BoundaryEdgeObservation | PhaseAnchor,
) -> PhaseAnchor:
    if isinstance(observation, PhaseAnchor):
        return observation
    if not isinstance(observation, BoundaryEdgeObservation):
        raise TypeError(
            "phase observations must be BoundaryEdgeObservation or PhaseAnchor"
        )
    # A weak/profile-like edge is retained in the registration ledger but is
    # not allowed to seed phase.  This fixed threshold keeps clutter from
    # moving a global fit while preserving the observation identity for
    # accounting and later veto handling.
    direct = (
        observation.support_fraction >= 0.35
        and observation.continuous_support_fraction >= 0.35
    )
    return PhaseAnchor(
        observation_id=observation.observation_id,
        coordinate_interval_px=observation.coordinate_interval_px,
        direct=direct,
    )


def _validate_relations(
    relations: Sequence[LocalAdvanceRelation],
    count: int,
) -> tuple[LocalAdvanceRelation, ...]:
    ordered = tuple(relations)
    if tuple(item.relation_ordinal for item in ordered) != tuple(
        range(1, len(ordered) + 1)
    ):
        raise ValueError("local relations must be ordered and contiguous")
    if len(ordered) > max(0, count - 1):
        raise ValueError("local relation count exceeds fixed slot count")
    return ordered


def _prefix_adjustments(
    relations: tuple[LocalAdvanceRelation, ...],
    count: int,
) -> tuple[FiniteInterval, ...]:
    """Return one cumulative prefix per slot; each anomaly propagates once."""

    prefixes: list[FiniteInterval] = [FiniteInterval.exact(0.0)]
    running = FiniteInterval.exact(0.0)
    for slot_index in range(1, count):
        relation = relations[slot_index - 1] if slot_index <= len(relations) else None
        if relation is not None:
            running = _add(running, relation.delta_interval_px)
        prefixes.append(running)
    return tuple(prefixes)


def _role_offsets(
    template: TemplateSpec,
    pitch_interval_px: FiniteInterval,
    relations: tuple[LocalAdvanceRelation, ...],
) -> tuple[FiniteInterval, ...]:
    prefixes = _prefix_adjustments(relations, template.count)
    offsets: list[FiniteInterval] = []
    width = FiniteInterval(template.frame_width_px.minimum, template.frame_width_px.maximum)
    for slot_index in range(template.count):
        start = _directed(
            _add(_scale(pitch_interval_px, slot_index), prefixes[slot_index]),
            template.direction,
        )
        end = _add(start, _directed(width, template.direction))
        offsets.extend((start, end))
    return tuple(offsets)


def _phase_prior(
    template: TemplateSpec,
    pitch_interval_px: FiniteInterval,
    relations: tuple[LocalAdvanceRelation, ...],
    holder_span_px: FiniteInterval | None,
    explicit_prior_px: FiniteInterval | None,
) -> FiniteInterval | None:
    if explicit_prior_px is not None:
        return explicit_prior_px
    if template.phase_authority != PhaseAuthority.FULL_CENTERED:
        return None
    if holder_span_px is None:
        raise ValueError("full-centered phase authority requires holder span")
    prefixes = _prefix_adjustments(relations, template.count)
    total = _add(
        _scale(pitch_interval_px, max(0, template.count - 1)),
        prefixes[-1],
    )
    total = _add(total, FiniteInterval(template.frame_width_px.minimum, template.frame_width_px.maximum))
    # ``holder_span_px`` is a source-coordinate extent (left/right or
    # start/end), not an uncertainty interval around its length.  Centre the
    # exposure span inside that extent while retaining total-span uncertainty.
    holder_origin = holder_span_px.minimum
    holder_length = holder_span_px.maximum - holder_span_px.minimum
    # An exact positive span is accepted as a length with origin zero; an
    # extent with two equal coordinates would otherwise be degenerate.
    if holder_length == 0.0 and holder_span_px.minimum > 0.0:
        holder_origin = 0.0
        holder_length = holder_span_px.minimum
    if holder_length <= 0.0:
        raise ValueError("full-centered holder span must have positive extent")
    return FiniteInterval(
        holder_origin + (holder_length - total.maximum) / 2.0,
        holder_origin + (holder_length - total.minimum) / 2.0,
    )


def _candidate_intervals(
    anchors: tuple[PhaseAnchor, ...],
    roles: tuple[TemplateRole, ...],
    offsets: tuple[FiniteInterval, ...],
    prior: FiniteInterval | None,
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for anchor in anchors:
        if not anchor.direct:
            continue
        role_indices = (
            (anchor.role.role_index,)
            if anchor.role is not None
            else tuple(range(len(roles)))
        )
        for role_index in role_indices:
            phase_interval = _subtract(anchor.coordinate_interval_px, offsets[role_index])
            candidates.append(
                _Candidate(
                    phase_interval_px=phase_interval,
                    source_observation_id=anchor.observation_id,
                    source_role_index=role_index,
                )
            )
    # A full-centered prior is a compatibility/tie-break bucket, never an
    # independent phase hypothesis.  Direct evidence must seed every fit.
    # Intervals from the same indexed observation are collapsed when they
    # overlap.  This is interval indexing, not a sampled phase grid.
    merged: list[_Candidate] = []
    for candidate in sorted(candidates, key=lambda item: item.phase_interval_px.center):
        if not merged:
            merged.append(candidate)
            continue
        previous = merged[-1]
        if _distance(previous.phase_interval_px, candidate.phase_interval_px) <= 0.5:
            merged[-1] = _Candidate(
                phase_interval_px=_hull(
                    (previous.phase_interval_px, candidate.phase_interval_px)
                ),
                source_observation_id=previous.source_observation_id,
                source_role_index=previous.source_role_index,
            )
        else:
            merged.append(candidate)
    return tuple(merged)


def _bind_candidate(
    candidate: _Candidate,
    anchors: tuple[PhaseAnchor, ...],
    roles: tuple[TemplateRole, ...],
    offsets: tuple[FiniteInterval, ...],
    template: TemplateSpec,
    pitch_fit: PitchFit,
    relations: tuple[LocalAdvanceRelation, ...],
    prior: FiniteInterval | None,
) -> SequenceFit:
    role_positions = tuple(_add(candidate.phase_interval_px, offset) for offset in offsets)
    available = set(range(len(roles)))
    matches: list[tuple[float, PhaseAnchor, int]] = []
    contradictions = 0
    for anchor in anchors:
        if not anchor.direct:
            continue
        allowed = (
            (anchor.role.role_index,)
            if anchor.role is not None
            else tuple(sorted(available))
        )
        distances = [
            (
                _distance(anchor.coordinate_interval_px, role_positions[index]),
                index,
            )
            for index in allowed
            if index in available
        ]
        if not distances:
            contradictions += 1
            continue
        distance, role_index = min(distances, key=lambda item: (item[0], item[1]))
        allowed_distance = max(
            1.0,
            anchor.coordinate_interval_px.width,
            role_positions[role_index].width,
        )
        if distance <= allowed_distance:
            available.remove(role_index)
            matches.append((distance, anchor, role_index))
        else:
            contradictions += 1
    # The interval candidate itself is the phase evidence.  Keep a small
    # deterministic residual only for ordering close hypotheses; it is not a
    # confidence score or authority vote.
    residual = sum(item[0] for item in matches)
    matched = tuple(sorted(item[2] for item in matches))
    direct_ids = tuple(item[1].observation_id for item in matches)
    inferred = tuple(index for index in range(len(roles)) if index not in matched)
    canonical_phase = candidate.phase_interval_px.center
    if prior is not None:
        # A prior is a tie-breaker only after direct support; it cannot create
        # a fit in a partial/free sequence.
        residual += min(
            abs(canonical_phase - prior.minimum),
            abs(canonical_phase - prior.maximum),
        ) * 1.0e-6
    center_compatible = True
    if template.phase_authority == PhaseAuthority.FULL_CENTERED and prior is not None:
        center_compatible = _distance(
            candidate.phase_interval_px,
            prior,
        ) <= 0.08 * template.frame_width_px.maximum
    return SequenceFit(
        template=template,
        phase_interval_px=candidate.phase_interval_px,
        canonical_phase_px=canonical_phase,
        pitch_fit=pitch_fit,
        role_positions_px=role_positions,
        matched_role_indices=matched,
        inferred_role_indices=inferred,
        direct_observation_ids=direct_ids,
        local_advance_relations=relations,
        support_count=len(matched),
        contradicted_observation_count=contradictions,
        residual_sum_px=residual,
        center_compatible=center_compatible,
    )


def _fit_key(fit: SequenceFit) -> tuple[int, int, int, float]:
    return (
        int(fit.center_compatible)
        if fit.template.phase_authority == PhaseAuthority.FULL_CENTERED
        else 1,
        fit.support_count,
        -fit.contradicted_observation_count,
        -fit.residual_sum_px,
    )


def fit_template_phase(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
    template: TemplateSpec,
    *,
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    phase_prior_px: FiniteInterval | None = None,
    local_advance_relations: Sequence[LocalAdvanceRelation] = (),
    max_observations: int = 256,
) -> PhaseFitResult:
    """Fit one fixed template in bounded indexed work.

    ``template.gap_prior_px`` is a source-pixel interval.  ``scale_px_per_mm``
    is retained in the typed pitch fit for provenance; conversion belongs to
    the format/spec owner and is intentionally not repeated here.
    """

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
    roles = ordered_template_roles(template.count)
    relation_tuple = _validate_relations(local_advance_relations, template.count)
    anchors = tuple(_anchor_from_observation(item) for item in observations)
    identities = tuple(item.observation_id for item in anchors)
    if len(set(identities)) != len(identities):
        raise ValueError("phase observations must have unique identities")
    direct_ids = tuple(item.observation_id for item in anchors if item.direct)
    base_receipt = TemplateSearchReceipt(
        observation_count=len(anchors),
        role_count=len(roles),
        phase_lookup_count=0,
        role_binding_count=0,
        local_relation_evaluation_count=len(relation_tuple),
        phase_hypothesis_count=0,
        direct_observation_count=len(direct_ids),
        inferred_role_count=0,
    )
    if len(anchors) > max_observations:
        return PhaseFitResult(
            template=template,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.BOUND_EXCEEDED,
            ambiguity_reason="phase observation bound exceeded",
            receipt=base_receipt,
            direct_observation_ids=direct_ids,
        )
    if not direct_ids:
        return PhaseFitResult(
            template=template,
            best=None,
            runner_up=None,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="phase requires direct edge evidence",
            receipt=base_receipt,
            direct_observation_ids=direct_ids,
        )
    if scale_px_per_mm is not None:
        scale = _positive(scale_px_per_mm)
    else:
        scale = None
    declared_pitch = FiniteInterval(template.pitch_px.minimum, template.pitch_px.maximum)
    gap_pitch = _add(
        FiniteInterval(template.frame_width_px.minimum, template.frame_width_px.maximum),
        template.gap_prior_px,
    )
    pitch_interval = _intersection(declared_pitch, gap_pitch)
    if pitch_interval is None:
        raise ValueError("template pitch and gap prior have no common interval")
    pitch_fit = PitchFit(
        frame_width_px=template.frame_width_px,
        gap_interval_px=template.gap_prior_px,
        pitch_interval_px=pitch_interval,
        canonical_pitch_px=pitch_interval.center,
        scale_px_per_mm=scale,
        observation_ids=direct_ids,
    )
    offsets = _role_offsets(template, pitch_interval, relation_tuple)
    prior = _phase_prior(
        template,
        pitch_interval,
        relation_tuple,
        holder_span_px,
        phase_prior_px,
    )
    candidates = _candidate_intervals(anchors, roles, offsets, prior)
    receipt = TemplateSearchReceipt(
        observation_count=len(anchors),
        role_count=len(roles),
        phase_lookup_count=len(direct_ids) * len(roles),
        role_binding_count=len(direct_ids) * len(roles),
        local_relation_evaluation_count=len(relation_tuple),
        phase_hypothesis_count=len(candidates),
        direct_observation_count=len(direct_ids),
        inferred_role_count=0,
        peak_temporary_bytes=max(0, len(candidates) * len(roles) * 96),
    )
    receipt.validate_bounds()
    best: SequenceFit | None = None
    runner: SequenceFit | None = None
    for candidate in candidates:
        fit = _bind_candidate(
            candidate,
            anchors,
            roles,
            offsets,
            template,
            pitch_fit,
            relation_tuple,
            prior,
        )
        if best is None or _fit_key(fit) > _fit_key(best):
            runner = best
            best = fit
        elif runner is None or _fit_key(fit) > _fit_key(runner):
            runner = fit
    if best is None or best.support_count == 0:
        return PhaseFitResult(
            template=template,
            best=best,
            runner_up=runner,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason="no direct observation matched indexed roles",
            receipt=TemplateSearchReceipt(
                **{
                    **receipt.__dict__,
                    "inferred_role_count": (
                        len(best.inferred_role_indices) if best is not None else 0
                    ),
                }
            ),
            direct_observation_ids=direct_ids,
        )
    receipt = TemplateSearchReceipt(
        **{
            **receipt.__dict__,
            "inferred_role_count": len(best.inferred_role_indices),
        }
    )
    receipt.validate_bounds()
    if runner is None:
        status = PhaseFitStatus.RESOLVED
        reason = None
    else:
        support_margin = best.support_count - runner.support_count
        residual_margin = runner.residual_sum_px - best.residual_sum_px
        clearly_distinct = support_margin >= 2 or (
            support_margin >= 1 and residual_margin > 2.0
        )
        if clearly_distinct:
            status = PhaseFitStatus.RESOLVED
            reason = None
        else:
            status = PhaseFitStatus.AMBIGUOUS
            reason = "runner-up is not clearly separated from the best fit"
    return PhaseFitResult(
        template=template,
        best=best,
        runner_up=runner,
        status=status,
        ambiguity_reason=reason,
        receipt=receipt,
        direct_observation_ids=direct_ids,
    )


__all__ = [
    "PhaseFitResult",
    "PhaseFitStatus",
    "fit_template_phase",
]
