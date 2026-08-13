"""Bounded global fit of one fixed-format sequence template."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

import numpy as np

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
    template: TemplateSpec
    best: SequenceFit | None
    runner_up: SequenceFit | None
    status: PhaseFitStatus
    ambiguity_reason: str | None
    receipt: TemplateSearchReceipt
    direct_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if self.status == PhaseFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved phase fit requires a placement")
        if self.status == PhaseFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded phase fit cannot authorize placement")
        if self.ambiguity_reason is not None and not self.ambiguity_reason:
            raise ValueError("phase ambiguity reason must not be empty")

@dataclass(frozen=True)
class _AnchorFact:
    observation_id: ObservationId
    interval_px: FiniteInterval
    role_index: int | None
    direct: bool
    support_fraction: float
    polarity: int

    @property
    def coordinate_px(self) -> float:
        return self.interval_px.center


@dataclass(frozen=True)
class _BoundFit:
    fit: SequenceFit
    residual_compatible: bool
    center_error_px: float


def _interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("template interval must be numeric")


def _positive(value: PositiveInterval | FiniteInterval | float | int) -> PositiveInterval:
    interval = _interval(value)
    if interval.minimum <= 0.0:
        raise ValueError("template scale must be positive")
    return PositiveInterval(interval.minimum, interval.maximum)


def _facts(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
) -> tuple[_AnchorFact, ...]:
    result: list[_AnchorFact] = []
    for observation in observations:
        if isinstance(observation, PhaseAnchor):
            result.append(
                _AnchorFact(
                    observation.observation_id,
                    observation.coordinate_interval_px,
                    None if observation.role is None else observation.role.role_index,
                    observation.direct,
                    1.0,
                    0,
                )
            )
            continue
        if not isinstance(observation, BoundaryEdgeObservation):
            raise TypeError("phase input requires typed boundary observations")
        result.append(
            _AnchorFact(
                observation.observation_id,
                observation.coordinate_interval_px,
                None,
                observation.support_fraction >= 0.35,
                observation.support_fraction,
                observation.polarity,
            )
        )
    if len({item.observation_id for item in result}) != len(result):
        raise ValueError("phase observations must have unique identities")
    return tuple(sorted(result, key=lambda item: (item.coordinate_px, str(item.observation_id))))


def _relations(
    values: Sequence[LocalAdvanceRelation],
    count: int,
) -> tuple[LocalAdvanceRelation, ...]:
    result = tuple(values)
    if tuple(item.relation_ordinal for item in result) != tuple(
        range(1, len(result) + 1)
    ) or len(result) > max(0, count - 1):
        raise ValueError("local relations must be ordered fixed adjacencies")
    return result


def _prefixes(
    relations: tuple[LocalAdvanceRelation, ...],
    count: int,
) -> tuple[float, ...]:
    result = [0.0]
    running = 0.0
    for slot_index in range(1, count):
        if slot_index <= len(relations):
            running += relations[slot_index - 1].canonical_delta_px
        result.append(running)
    return tuple(result)


def _role_position(
    role: TemplateRole,
    *,
    phase: float,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
) -> float:
    relative = role.slot_index * pitch + prefixes[role.slot_index]
    if role.role == BoundaryRole.END:
        relative += width
    return phase + direction * relative


def _holder_center(
    span: FiniteInterval | None,
) -> float | None:
    if span is None:
        return None
    if span.width == 0.0 and span.minimum > 0.0:
        return span.minimum / 2.0
    if span.width <= 0.0:
        raise ValueError("holder span must have a positive extent")
    return span.center


def _holder_limits(span: FiniteInterval | None) -> tuple[float, float] | None:
    if span is None:
        return None
    if span.width == 0.0 and span.minimum > 0.0:
        return (0.0, span.minimum)
    if span.width <= 0.0:
        raise ValueError("holder span must have a positive extent")
    return (span.minimum, span.maximum)


def _expected_polarity(role: TemplateRole) -> int:
    return 1 if role.role == BoundaryRole.START else -1


def _match_roles(
    direct: tuple[_AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    *,
    phase: float,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
) -> tuple[tuple[TemplateRole, _AnchorFact], ...]:
    centers = tuple(item.coordinate_px for item in direct)
    used: set[ObservationId] = set()
    selected: list[tuple[TemplateRole, _AnchorFact]] = []
    corridor = max(3.0, pitch * 0.11)
    has_both_polarities = {item.polarity for item in direct} >= {-1, 1}
    ordered_roles = roles if direction > 0 else tuple(reversed(roles))
    for role in ordered_roles:
        expected = _role_position(
            role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        begin = bisect_left(centers, expected - corridor)
        end = bisect_right(centers, expected + corridor)
        compatible = tuple(
            item
            for item in direct[begin:end]
            if item.observation_id not in used
            and (item.role_index is None or item.role_index == role.role_index)
        )
        if not compatible:
            continue
        chosen = min(
            compatible,
            key=lambda item: (
                int(
                    has_both_polarities
                    and item.polarity not in {0, _expected_polarity(role)}
                ),
                abs(item.coordinate_px - expected),
                -item.support_fraction,
                str(item.observation_id),
            ),
        )
        if (
            has_both_polarities
            and chosen.polarity not in {0, _expected_polarity(role)}
            and abs(chosen.coordinate_px - expected) > corridor * 0.35
        ):
            continue
        used.add(chosen.observation_id)
        selected.append((role, chosen))
    return tuple(sorted(selected, key=lambda item: item[0].role_index))


def _linear_fit(
    matches: tuple[tuple[TemplateRole, _AnchorFact], ...],
    *,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
    width_authority: PositiveInterval,
    pitch_authority: FiniteInterval,
) -> tuple[float, float, float]:
    if not matches:
        raise ValueError("global template fit requires direct matches")
    matrix = np.asarray(
        [
            (
                1.0,
                float(direction if role.role == BoundaryRole.END else 0),
                float(direction * role.slot_index),
            )
            for role, _anchor in matches
        ],
        dtype=np.float64,
    )
    values = np.asarray(
        [
            anchor.coordinate_px - direction * prefixes[role.slot_index]
            for role, anchor in matches
        ],
        dtype=np.float64,
    )
    if len(matches) >= 3 and np.linalg.matrix_rank(matrix) == 3:
        phase_fit, width_fit, pitch_fit = np.linalg.lstsq(
            matrix,
            values,
            rcond=None,
        )[0]
        if width_authority.minimum <= width_fit <= width_authority.maximum:
            width = float(width_fit)
        if pitch_authority.contains(float(pitch_fit)):
            pitch = float(pitch_fit)
    offsets = tuple(
        direction
        * (
            role.slot_index * pitch
            + prefixes[role.slot_index]
            + (width if role.role == BoundaryRole.END else 0.0)
        )
        for role, _anchor in matches
    )
    phase_values = sorted(
        anchor.coordinate_px - offset
        for offset, (_role, anchor) in zip(offsets, matches, strict=True)
    )
    phase = float(phase_values[len(phase_values) // 2])
    if len(matches) >= 3 and np.linalg.matrix_rank(matrix) == 3:
        phase_fit = float(
            np.linalg.lstsq(
                matrix,
                values,
                rcond=None,
            )[0][0]
        )
        if math.isfinite(phase_fit):
            phase = phase_fit
    return phase, width, pitch


def _fit_seed(
    seed_phase: float,
    seed_pitch: float,
    direct: tuple[_AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    relations: tuple[LocalAdvanceRelation, ...],
    holder_center: float | None,
    phase_prior: FiniteInterval | None,
    pitch_authority: FiniteInterval,
) -> _BoundFit | None:
    width = (
        template.frame_width_px.minimum
        + template.frame_width_px.maximum
    ) / 2.0
    pitch = seed_pitch
    phase = seed_phase
    prefixes = _prefixes(relations, template.count)
    matches: tuple[tuple[TemplateRole, _AnchorFact], ...] = ()
    for _iteration in range(4):
        matches = _match_roles(
            direct,
            template.roles,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
        )
        if not matches:
            return None
        phase, width, pitch = _linear_fit(
            matches,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            width_authority=template.frame_width_px,
            pitch_authority=pitch_authority,
        )
    residual_limit = max(3.0, width * 0.035)
    retained = tuple(
        (role, anchor)
        for role, anchor in matches
        if abs(
            anchor.coordinate_px
            - _role_position(
                role,
                phase=phase,
                width=width,
                pitch=pitch,
                direction=template.direction,
                prefixes=prefixes,
            )
        )
        <= residual_limit
    )
    if retained and retained != matches:
        phase, width, pitch = _linear_fit(
            retained,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            width_authority=template.frame_width_px,
            pitch_authority=pitch_authority,
        )
        matches = retained
    if not matches:
        return None
    canonical_positions = tuple(
        _role_position(
            role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
        )
        for role in roles
    )
    by_role = {role.role_index: anchor for role, anchor in matches}
    residuals = tuple(
        abs(anchor.coordinate_px - canonical_positions[role.role_index])
        for role, anchor in matches
    )
    residual_sum = sum(residuals)
    residual_mean = residual_sum / len(residuals)
    residual_compatible = residual_mean <= max(2.0, width * 0.015)
    uncertainty = max(1.0, min(width * 0.04, residual_mean + 1.0))
    role_intervals: list[FiniteInterval] = []
    role_ids: list[ObservationId | None] = []
    for role, canonical in zip(roles, canonical_positions, strict=True):
        observed = by_role.get(role.role_index)
        if observed is None:
            role_intervals.append(
                FiniteInterval(canonical - uncertainty, canonical + uncertainty)
            )
            role_ids.append(None)
        else:
            role_intervals.append(
                FiniteInterval(
                    min(canonical, observed.interval_px.minimum),
                    max(canonical, observed.interval_px.maximum),
                )
            )
            role_ids.append(observed.observation_id)
    span_midpoint = (canonical_positions[0] + canonical_positions[-1]) / 2.0
    requested_center = (
        phase_prior.center
        + (
            canonical_positions[-1]
            - canonical_positions[0]
        )
        / 2.0
        if phase_prior is not None
        else holder_center
    )
    center_error = (
        0.0 if requested_center is None else abs(span_midpoint - requested_center)
    )
    center_compatible = (
        template.phase_authority != PhaseAuthority.FULL_CENTERED
        or requested_center is not None
        and center_error <= 0.08 * width
    )
    matched = tuple(sorted(by_role))
    inferred = tuple(index for index in range(len(roles)) if index not in by_role)
    direct_ids = tuple(
        identity for identity in role_ids if identity is not None
    )
    polarity_matches = sum(
        anchor.polarity in {0, _expected_polarity(role)}
        for role, anchor in matches
    )
    direct_support = sum(anchor.support_fraction for _role, anchor in matches)
    phase_uncertainty = max(1.0, min(width * 0.04, residual_mean + 1.0))
    fit = SequenceFit(
        template=template,
        phase_interval_px=FiniteInterval(
            phase - phase_uncertainty,
            phase + phase_uncertainty,
        ),
        canonical_phase_px=phase,
        pitch_fit=PitchFit(
            frame_width_px=template.frame_width_px,
            gap_interval_px=template.gap_prior_px,
            pitch_interval_px=pitch_authority,
            canonical_frame_width_px=width,
            canonical_pitch_px=pitch,
            observation_ids=direct_ids,
        ),
        canonical_role_positions_px=canonical_positions,
        role_positions_px=tuple(role_intervals),
        role_observation_ids=tuple(role_ids),
        matched_role_indices=matched,
        inferred_role_indices=inferred,
        direct_observation_ids=direct_ids,
        local_advance_relations=relations,
        support_count=len(matched),
        contradicted_observation_count=max(0, len(direct) - len(matched)),
        residual_sum_px=residual_sum,
        center_compatible=center_compatible,
        direct_support_fraction=direct_support,
        polarity_match_count=polarity_matches,
    )
    return _BoundFit(fit, residual_compatible, center_error)


def _rank(value: _BoundFit) -> tuple[object, ...]:
    fit = value.fit
    common = (
        int(value.residual_compatible),
        fit.polarity_match_count,
        fit.direct_support_fraction,
        fit.support_count,
        -fit.residual_sum_px,
    )
    if fit.template.phase_authority == PhaseAuthority.FULL_CENTERED:
        center_bucket = int(
            value.center_error_px
            / max(1.0, fit.pitch_fit.canonical_frame_width_px * 0.02)
        )
        return (int(fit.center_compatible), -center_bucket, *common)
    return (
        int(value.residual_compatible),
        fit.direct_support_fraction,
        fit.polarity_match_count,
        fit.support_count,
        -fit.residual_sum_px,
    )


def _clearly_better(best: _BoundFit, runner: _BoundFit) -> bool:
    left = best.fit
    right = runner.fit
    if left.center_compatible and not right.center_compatible:
        return True
    if (
        left.template.phase_authority == PhaseAuthority.FULL_CENTERED
        and int(
            best.center_error_px
            / max(1.0, left.pitch_fit.canonical_frame_width_px * 0.02)
        )
        < int(
            runner.center_error_px
            / max(1.0, right.pitch_fit.canonical_frame_width_px * 0.02)
        )
    ):
        return True
    if best.residual_compatible and not runner.residual_compatible:
        return True
    if left.polarity_match_count >= right.polarity_match_count + 2:
        return True
    if left.direct_support_fraction >= right.direct_support_fraction + 0.35:
        return True
    if left.support_count >= right.support_count + 2:
        return True
    return (
        left.support_count == right.support_count
        and left.direct_support_fraction >= right.direct_support_fraction - 0.1
        and right.residual_sum_px
        >= left.residual_sum_px + max(2.0, left.pitch_fit.canonical_frame_width_px * 0.01)
    )


def _sampling_equivalent(left: SequenceFit, right: SequenceFit) -> bool:
    tolerance = max(
        2.0,
        min(
            left.pitch_fit.canonical_frame_width_px,
            right.pitch_fit.canonical_frame_width_px,
        )
        * 0.03,
    )
    return all(
        abs(left_value - right_value) <= tolerance
        for left_value, right_value in zip(
            left.canonical_role_positions_px,
            right.canonical_role_positions_px,
            strict=True,
        )
    )


def fit_template_phase(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
    template: TemplateSpec,
    *,
    scale_px_per_mm: PositiveInterval | float | None = None,
    holder_span_px: FiniteInterval | None = None,
    phase_prior_px: FiniteInterval | None = None,
    local_advance_relations: Sequence[LocalAdvanceRelation] = (),
    max_observations: int = 512,
) -> PhaseFitResult:
    """Fit `{phase, W, pitch}` without building a chain product."""

    if max_observations <= 0:
        raise ValueError("phase observation bound must be positive")
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
    by_binding: dict[tuple[ObservationId | None, ...], _BoundFit] = {}
    for candidate in candidates:
        key = candidate.fit.role_observation_ids
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
        )
    if (
        runner is None
        or _sampling_equivalent(best.fit, runner.fit)
        or _clearly_better(best, runner)
    ):
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
    )


__all__ = ["PhaseFitResult", "PhaseFitStatus", "fit_template_phase"]
