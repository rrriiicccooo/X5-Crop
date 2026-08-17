"""Bind role-free observations to one bounded fixed-template phase."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
import math
from typing import Sequence

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceRelation,
    PhaseAnchor,
    PhaseLatticeFit,
    PitchFit,
    SequenceFit,
    TemplateRole,
    TemplateSpec,
    ordered_template_roles,
)
from .template_phase_model import PhaseWinnerBasis
from .template_pitch import _refine_placement_pitch_interval


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
    solution = None
    if len(matches) >= 3 and np.linalg.matrix_rank(matrix) == 3:
        solution = np.linalg.lstsq(
            matrix,
            values,
            rcond=None,
        )[0]
        phase_fit, width_fit, pitch_fit = solution
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
    if solution is not None:
        phase_fit = float(solution[0])
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
        updated_matches = _match_roles(
            direct,
            template.roles,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            frame_width=template.frame_width_px,
        )
        if not updated_matches:
            return None
        updated = _linear_fit(
            updated_matches,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            width_authority=template.frame_width_px,
            pitch_authority=pitch_authority,
            gap_authority=template.gap_prior_px,
        )
        if updated_matches == matches and updated == (phase, width, pitch):
            break
        matches = updated_matches
        phase, width, pitch = updated
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
    measured_pitch = _refine_placement_pitch_interval(
        tuple(
            (role.role, role.slot_index, anchor.interval_px)
            for role, anchor in matches
        ),
        canonical_pitch=pitch,
        pitch_authority=pitch_authority,
        direction=template.direction,
        prefixes=prefix_intervals,
    )
    if measured_pitch is None:
        return None
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
                        measured_pitch.minimum,
                        measured_pitch.maximum,
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
            pitch_interval_px=measured_pitch,
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
        direct_support_fraction=direct_support,
        polarity_match_count=polarity_matches,
    )
    return _BoundFit(fit, residual_compatible)


def _rank(value: _BoundFit) -> tuple[object, ...]:
    fit = value.fit
    return (
        int(value.residual_compatible),
        fit.direct_support_fraction,
        fit.polarity_match_count,
        fit.support_count,
        -fit.residual_sum_px,
    )


def _clear_winner_basis(
    best: _BoundFit,
    runner: _BoundFit,
) -> PhaseWinnerBasis | None:
    left = best.fit
    right = runner.fit
    if best.residual_compatible and not runner.residual_compatible:
        return PhaseWinnerBasis.RESIDUAL_COMPATIBILITY
    if left.polarity_match_count >= right.polarity_match_count + 2:
        return PhaseWinnerBasis.POLARITY_SUPPORT
    if left.direct_support_fraction >= right.direct_support_fraction + 0.35:
        return PhaseWinnerBasis.DIRECT_SUPPORT
    if left.support_count >= right.support_count + 2:
        return PhaseWinnerBasis.ROLE_SUPPORT
    if (
        left.support_count == right.support_count
        and left.direct_support_fraction >= right.direct_support_fraction - 0.1
        and right.residual_sum_px
        >= left.residual_sum_px + max(2.0, left.pitch_fit.canonical_frame_width_px * 0.01)
    ):
        return PhaseWinnerBasis.RESIDUAL_SEPARATION
    return None


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
