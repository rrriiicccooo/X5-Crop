"""Bounded global fit of one fixed-format sequence template."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Sequence

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole
from .observation_types import BoundaryEdgeObservation
from .observation_types import SeparatorBandObservation
from .template_model import (
    LocalAdvanceRelation,
    PhaseAnchor,
    PhaseAuthority,
    PhaseLatticeFit,
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


class PhaseFailureKind(str, Enum):
    OBSERVATION_BOUND_EXCEEDED = "observation_bound_exceeded"
    DIRECT_PHASE_ANCHOR_UNAVAILABLE = "direct_phase_anchor_unavailable"
    FIXED_TEMPLATE_MISMATCH = "fixed_template_mismatch"
    DISCRETE_PHASE_AMBIGUOUS = "discrete_phase_ambiguous"
    LOCAL_ADVANCE_AMBIGUOUS = "local_advance_ambiguous"


@dataclass(frozen=True)
class PhaseFitResult:
    template: TemplateSpec
    best: SequenceFit | None
    runner_up: SequenceFit | None
    status: PhaseFitStatus
    ambiguity_reason: str | None
    receipt: TemplateSearchReceipt
    direct_observation_ids: tuple[ObservationId, ...]
    failure_kind: PhaseFailureKind | None = None

    def __post_init__(self) -> None:
        if self.status == PhaseFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved phase fit requires a placement")
        if self.status == PhaseFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded phase fit cannot authorize placement")
        if self.ambiguity_reason is not None and not self.ambiguity_reason:
            raise ValueError("phase ambiguity reason must not be empty")
        if (self.status == PhaseFitStatus.RESOLVED) != (self.failure_kind is None):
            raise ValueError("phase failure kind must match fit status")

    def with_calibrated_template(self, template: TemplateSpec) -> "PhaseFitResult":
        """Narrow the continuous template without rerunning role selection."""

        if template.template_id != self.template.template_id:
            raise ValueError("calibrated template changes phase identity")
        best = (
            None
            if self.best is None
            else self.best.with_calibrated_template(template)
        )
        try:
            runner = (
                None
                if self.runner_up is None
                else self.runner_up.with_calibrated_template(template)
            )
        except ValueError:
            # A discrete runner that fails the calibrated W+gap closure is
            # physically illegal; this is a hard filter, not score pruning.
            runner = None
        status = self.status
        reason = self.ambiguity_reason
        if best is not None and runner is None and status == PhaseFitStatus.AMBIGUOUS:
            status = PhaseFitStatus.RESOLVED
            reason = None
        return PhaseFitResult(
            template=template,
            best=best,
            runner_up=runner,
            status=status,
            ambiguity_reason=reason,
            receipt=self.receipt,
            direct_observation_ids=self.direct_observation_ids,
            failure_kind=(None if status == PhaseFitStatus.RESOLVED else self.failure_kind),
        )

@dataclass(frozen=True)
class _AnchorFact:
    observation_id: ObservationId
    interval_px: FiniteInterval
    role_index: int | None
    direct: bool
    support_fraction: float
    polarity: int
    qualified_anchor_roles: tuple[BoundaryRole, ...]

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
                    observation.role.role_index,
                    True,
                    1.0,
                    0,
                    (observation.role.role,),
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
                observation.support_fraction >= 0.35
                and bool(observation.qualified_anchor_roles),
                observation.support_fraction,
                observation.polarity,
                observation.qualified_anchor_roles,
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


def _prefix_intervals(
    relations: tuple[LocalAdvanceRelation, ...],
    count: int,
) -> tuple[FiniteInterval, ...]:
    """Propagate each directly authorized local advance exactly once."""

    result = [FiniteInterval.exact(0.0)]
    minimum = 0.0
    maximum = 0.0
    for slot_index in range(1, count):
        if slot_index <= len(relations):
            interval = relations[slot_index - 1].delta_interval_px
            minimum += interval.minimum
            maximum += interval.maximum
        result.append(FiniteInterval(minimum, maximum))
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


def _inferred_role_interval(
    role: TemplateRole,
    *,
    phase: FiniteInterval,
    width: FiniteInterval,
    pitch: FiniteInterval,
    direction: int,
    prefixes: tuple[FiniteInterval, ...],
) -> FiniteInterval:
    """Project continuous template authority onto one missing boundary."""

    slot = role.slot_index
    relative_minimum = slot * pitch.minimum + prefixes[slot].minimum
    relative_maximum = slot * pitch.maximum + prefixes[slot].maximum
    if role.role == BoundaryRole.END:
        relative_minimum += width.minimum
        relative_maximum += width.maximum
    if direction == 1:
        return FiniteInterval(
            phase.minimum + relative_minimum,
            phase.maximum + relative_maximum,
        )
    return FiniteInterval(
        phase.minimum - relative_maximum,
        phase.maximum - relative_minimum,
    )


def _phase_lattice_fit(
    template: TemplateSpec,
    *,
    absolute_phase_px: float,
    period_px: float,
    uncertainty_px: float,
) -> PhaseLatticeFit | None:
    authority = template.phase_lattice_authority
    normalized = template.direction * (
        absolute_phase_px - authority.cycle_origin_px
    )
    offset = math.floor(normalized / period_px)
    if not authority.contains_offset(offset):
        return None
    cycle = normalized - offset * period_px
    if cycle >= period_px - 1.0e-9:
        cycle = 0.0
        offset += 1
        if not authority.contains_offset(offset):
            return None
    radius = min(
        max(0.0, uncertainty_px),
        cycle,
        period_px - cycle,
    )
    cycle_interval = FiniteInterval(cycle - radius, cycle + radius)
    projected = tuple(
        authority.cycle_origin_px
        + template.direction * (value + offset * period_px)
        for value in (cycle_interval.minimum, cycle_interval.maximum)
    )
    return PhaseLatticeFit(
        authority=authority,
        cycle_phase_interval_px=cycle_interval,
        canonical_cycle_phase_px=cycle,
        integer_slot_offset=offset,
        canonical_period_px=period_px,
        absolute_phase_interval_px=FiniteInterval(min(projected), max(projected)),
        canonical_absolute_phase_px=absolute_phase_px,
        direction=template.direction,
    )


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


def _separator_role_authority(
    separator_bands: Sequence[SeparatorBandObservation],
) -> dict[ObservationId, frozenset[BoundaryRole]]:
    """Return role facts proved by directly observed separator material.

    A separator's left edge is the END of one slot and its right edge is the
    START of the next slot.  This relation is stronger than a single edge's
    background hint, but it still carries no ordinal until the template is
    placed.  An identity may occur in several bands; they all prove the same
    side relation and are never counted as extra votes.
    """

    roles: dict[ObservationId, set[BoundaryRole]] = {}
    for band in separator_bands:
        roles.setdefault(band.left_edge_observation_id, set()).add(
            BoundaryRole.END
        )
        roles.setdefault(band.right_edge_observation_id, set()).add(
            BoundaryRole.START
        )
    return {identity: frozenset(value) for identity, value in roles.items()}


def _with_separator_role_authority(
    observations: Sequence[BoundaryEdgeObservation | PhaseAnchor],
    separator_bands: Sequence[SeparatorBandObservation],
) -> tuple[BoundaryEdgeObservation | PhaseAnchor, ...]:
    authority = _separator_role_authority(separator_bands)
    if not authority:
        return tuple(observations)
    values: list[BoundaryEdgeObservation | PhaseAnchor] = []
    for observation in observations:
        if isinstance(observation, BoundaryEdgeObservation):
            roles = authority.get(observation.observation_id)
            if roles:
                observation = replace(
                    observation,
                    qualified_anchor_roles=tuple(
                        role
                        for role in (BoundaryRole.START, BoundaryRole.END)
                        if role in roles
                    ),
                )
        values.append(observation)
    return tuple(values)


def _match_roles(
    direct: tuple[_AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    *,
    phase: float,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
    frame_width: PositiveInterval,
) -> tuple[tuple[TemplateRole, _AnchorFact], ...]:
    centers = tuple(item.coordinate_px for item in direct)
    used: set[ObservationId] = set()
    selected: list[tuple[TemplateRole, _AnchorFact]] = []
    corridor = max(3.0, pitch * 0.11)
    has_both_polarities = {item.polarity for item in direct} >= {-1, 1}

    def candidates(
        role: TemplateRole,
        expected: float,
    ) -> tuple[_AnchorFact, ...]:
        begin = bisect_left(centers, expected - corridor)
        end = bisect_right(centers, expected + corridor)
        return tuple(
            item
            for item in direct[begin:end]
            if item.observation_id not in used
            and (item.role_index is None or item.role_index == role.role_index)
            and (
                not item.qualified_anchor_roles
                or role.role in item.qualified_anchor_roles
            )
        )

    def choice_key(
        role: TemplateRole,
        expected: float,
        item: _AnchorFact,
    ) -> tuple[object, ...]:
        return (
            int(
                not item.qualified_anchor_roles
                and has_both_polarities
                and item.polarity not in {0, _expected_polarity(role)}
            ),
            abs(item.coordinate_px - expected),
            -item.support_fraction,
            str(item.observation_id),
        )

    def width_compatible(start: _AnchorFact, end: _AnchorFact) -> bool:
        values = tuple(
            direction * (end_value - start_value)
            for start_value in (
                start.interval_px.minimum,
                start.interval_px.maximum,
            )
            for end_value in (
                end.interval_px.minimum,
                end.interval_px.maximum,
            )
        )
        span = FiniteInterval(min(values), max(values))
        return max(span.minimum, frame_width.minimum) <= min(
            span.maximum,
            frame_width.maximum,
        )

    # A frame's two roles are one fixed-width physical relation.  Bind that
    # relation before considering either edge alone, so a nearby interior line
    # cannot defeat a slightly farther outer edge merely through polarity or
    # strength.  Each start consults only the constant-size neighbourhood of
    # its theoretical fixed-W endpoint in the sorted observation index.
    slot_roles = tuple(
        (roles[2 * index], roles[2 * index + 1])
        for index in range(len(roles) // 2)
    )
    if direction < 0:
        slot_roles = tuple(reversed(slot_roles))
    for start_role, end_role in slot_roles:
        start_expected = _role_position(
            start_role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        end_expected = _role_position(
            end_role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        starts = candidates(start_role, start_expected)
        ends = candidates(end_role, end_expected)
        end_ids = {item.observation_id for item in ends}
        pairs: list[tuple[_AnchorFact, _AnchorFact]] = []
        for start in starts:
            frame_width_center = (
                frame_width.minimum + frame_width.maximum
            ) / 2.0
            target = start.coordinate_px + direction * frame_width_center
            insertion = bisect_left(centers, target)
            for index in range(insertion - 2, insertion + 3):
                if not 0 <= index < len(direct):
                    continue
                end = direct[index]
                if (
                    end.observation_id in end_ids
                    and width_compatible(start, end)
                ):
                    pairs.append((start, end))
        if pairs:
            start, end = min(
                pairs,
                key=lambda pair: (
                    choice_key(start_role, start_expected, pair[0]),
                    choice_key(end_role, end_expected, pair[1]),
                ),
            )
            used.update((start.observation_id, end.observation_id))
            selected.extend(((start_role, start), (end_role, end)))
            continue

        for role, expected, compatible in (
            (start_role, start_expected, starts),
            (end_role, end_expected, ends),
        ):
            compatible = tuple(
                item for item in compatible if item.observation_id not in used
            )
            if not compatible:
                continue
            chosen = min(
                compatible,
                key=lambda item: choice_key(role, expected, item),
            )
            if (
                not chosen.qualified_anchor_roles
                and has_both_polarities
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
    gap_authority: FiniteInterval,
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
        proposed_width = (
            float(width_fit)
            if width_authority.minimum <= width_fit <= width_authority.maximum
            else width
        )
        proposed_pitch = (
            float(pitch_fit)
            if pitch_authority.contains(float(pitch_fit))
            else pitch
        )
        if gap_authority.contains(proposed_pitch - proposed_width):
            width = proposed_width
            pitch = proposed_pitch
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
            frame_width=template.frame_width_px,
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
            gap_authority=template.gap_prior_px,
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
            gap_authority=template.gap_prior_px,
        )
        matches = retained
    if not matches:
        return None
    if not template.gap_prior_px.contains(pitch - width):
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
    # One role's residual belongs to that role.  Smearing the largest residual
    # over every boundary turns one local observation into source-wide
    # uncertainty and can exceed the direct-use budget even when the template
    # placement is unique.  The global phase interval below carries the common
    # fit uncertainty; every directly bound role keeps only its own observed
    # interval plus its fitted coordinate.  Missing roles propagate the full
    # continuous template authority: pitch uncertainty grows with the slot
    # ordinal and a directly authorized local advance changes the suffix once.
    uncertainty = max(1.0, min(width * 0.04, residual_mean + 1.0))
    phase_interval = FiniteInterval(phase - uncertainty, phase + uncertainty)
    prefix_intervals = _prefix_intervals(relations, template.count)
    role_intervals: list[FiniteInterval] = []
    role_ids: list[ObservationId | None] = []
    for role, canonical in zip(roles, canonical_positions, strict=True):
        observed = by_role.get(role.role_index)
        if observed is None:
            role_intervals.append(
                _inferred_role_interval(
                    role,
                    phase=phase_interval,
                    width=FiniteInterval(
                        template.frame_width_px.minimum,
                        template.frame_width_px.maximum,
                    ),
                    pitch=FiniteInterval(
                        pitch_authority.minimum,
                        pitch_authority.maximum,
                    ),
                    direction=template.direction,
                    prefixes=prefix_intervals,
                )
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
    phase_uncertainty = uncertainty
    lattice_fit = _phase_lattice_fit(
        template,
        absolute_phase_px=phase,
        period_px=pitch,
        uncertainty_px=phase_uncertainty,
    )
    if lattice_fit is None:
        return None
    fit = SequenceFit(
        template=template,
        phase_lattice_fit=lattice_fit,
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
    if (
        left.phase_lattice_fit.integer_slot_offset
        != right.phase_lattice_fit.integer_slot_offset
    ):
        return False
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
        (
            None
            if status == PhaseFitStatus.RESOLVED
            else PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS
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
    "PhaseFailureKind",
    "PhaseFitResult",
    "PhaseFitStatus",
    "account_prior_phase_fit",
    "fit_template_phase",
    "fit_template_phase_with_local_advance",
]
