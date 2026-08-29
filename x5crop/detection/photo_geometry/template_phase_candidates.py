"""Bind role-free observations to one bounded fixed-template phase."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
import math
from typing import Sequence

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceRelation,
    PhaseLatticeFit,
    PitchFit,
    SequenceFit,
    SequenceRoleBinding,
    SequenceRoleLineEvidence,
    TemplateRole,
    TemplateSpec,
    template_role_refinement_radius_px,
)
from .template_phase_model import PhaseWinnerBasis
from .template_pitch import refine_placement_pitch_interval
from .template_evidence import separator_support_authority


@dataclass(frozen=True)
class _AnchorFact:
    observation_id: ObservationId
    independent_support_id: ObservationId
    interval_px: FiniteInterval
    full_interval_px: FiniteInterval
    role_index: int | None
    direct: bool
    support_fraction: float
    fit_residual_px: float
    line_evidence: SequenceRoleLineEvidence | None
    polarity: int
    qualified_anchor_roles: tuple[BoundaryRole, ...]

    @property
    def coordinate_px(self) -> float:
        return self.interval_px.center


@dataclass(frozen=True)
class _BoundFit:
    fit: SequenceFit
    residual_compatible: bool


@dataclass(frozen=True)
class _PhaseSeed:
    """One discrete phase hypothesis and the direct fact that created it."""

    phase_px: float
    pitch_px: float
    required_bindings: tuple[tuple[int, ObservationId], ...] = ()

    def __post_init__(self) -> None:
        role_indices = tuple(item[0] for item in self.required_bindings)
        observation_ids = tuple(item[1] for item in self.required_bindings)
        if (
            not math.isfinite(self.phase_px)
            or not math.isfinite(self.pitch_px)
            or self.pitch_px <= 0.0
            or any(index < 0 for index in role_indices)
            or len(set(role_indices)) != len(role_indices)
            or len(set(observation_ids)) != len(observation_ids)
        ):
            raise ValueError("phase seed identity is invalid")


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
    observations: Sequence[BoundaryEdgeObservation],
    *,
    separator_support_ids: dict[ObservationId, ObservationId] | None = None,
) -> tuple[_AnchorFact, ...]:
    separator_support_ids = separator_support_ids or {}
    result: list[_AnchorFact] = []
    for observation in observations:
        if not isinstance(observation, BoundaryEdgeObservation):
            raise TypeError("phase input requires typed boundary observations")
        result.append(
            _AnchorFact(
                observation_id=observation.observation_id,
                independent_support_id=separator_support_ids.get(
                    observation.observation_id,
                    observation.observation_id,
                ),
                interval_px=observation.fit_position_interval_px,
                full_interval_px=observation.full_position_interval_px,
                role_index=None,
                direct=(
                    observation.support_fraction >= 0.35
                    or observation.observation_id in separator_support_ids
                )
                and bool(observation.qualified_anchor_roles),
                support_fraction=observation.support_fraction,
                fit_residual_px=observation.fit_residual_px,
                line_evidence=(
                    SequenceRoleLineEvidence(
                        observation_id=observation.observation_id,
                        reference_trace_px=observation.reference_trace_px,
                        fit_position_interval_px=(
                            observation.fit_position_interval_px
                        ),
                        fit_direction_interval_degrees=(
                            observation.fit_direction_interval_degrees
                        ),
                    )
                    if observation.fit_direction_interval_degrees is not None
                    else None
                ),
                polarity=observation.polarity,
                qualified_anchor_roles=observation.qualified_anchor_roles,
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
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
) -> dict[ObservationId, frozenset[BoundaryRole]]:
    """Return role facts proved by directly observed separator material.

    A separator's left edge is the END of one slot and its right edge is the
    START of the next slot.  This relation is stronger than a single edge's
    background hint, but it still carries no ordinal until the template is
    placed.  An identity may occur in several bands; they all prove the same
    side relation and are never counted as extra votes.
    """

    by_id = {
        observation.observation_id: observation
        for observation in observations
        if isinstance(observation, BoundaryEdgeObservation)
    }
    support_ids = separator_support_authority(tuple(separator_bands))
    components: dict[ObservationId, list[SeparatorBandObservation]] = {}
    for band in separator_bands:
        support_id = support_ids.get(band.left_edge_observation_id)
        if support_id is None:
            raise ValueError("separator band has no physical support identity")
        components.setdefault(support_id, []).append(band)

    roles: dict[ObservationId, set[BoundaryRole]] = {}
    for component in components.values():
        source_wide = tuple(
            band
            for band in component
            if band.independent_support_region_count
            >= SPATIAL_SUPPORT_REGION_COUNT
        )
        if source_wide:
            selected = source_wide
        else:
            # A short dark or bright region inside one photograph can close
            # the same local polarity pattern as separator material.  It may
            # join two edges whose independently observed roles already agree,
            # but it cannot overwrite either role.  Only a source-wide band
            # has enough spatial support to establish END -> material -> START
            # authority by itself.
            continue

        for band in selected:
            roles.setdefault(band.left_edge_observation_id, set()).add(
                BoundaryRole.END
            )
            roles.setdefault(band.right_edge_observation_id, set()).add(
                BoundaryRole.START
            )
    return {identity: frozenset(value) for identity, value in roles.items()}


def _with_separator_role_authority(
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    maximum_material_gap_px: float,
) -> tuple[BoundaryEdgeObservation, ...]:
    authority = _separator_role_authority(observations, separator_bands)
    if not authority and not separator_bands:
        return tuple(observations)
    by_id = {
        observation.observation_id: observation
        for observation in observations
        if isinstance(observation, BoundaryEdgeObservation)
    }
    support_ids = separator_support_authority(tuple(separator_bands))
    components: dict[ObservationId, list[SeparatorBandObservation]] = {}
    for band in separator_bands:
        support_id = support_ids.get(band.left_edge_observation_id)
        if support_id is None:
            raise ValueError("separator band has no physical support identity")
        components.setdefault(support_id, []).append(band)
    material_intervals: dict[ObservationId, FiniteInterval] = {}
    for component in components.values():
        pairs = {
            (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
            )
            for band in component
        }
        # Only one locally observed END -> material -> START relation needs
        # the material center retained as output protection. Source-wide bands
        # already localize their edges directly; alternative pairings remain
        # discrete evidence and must not be hulled into a huge interval.
        if (
            any(
                band.independent_support_region_count
                >= SPATIAL_SUPPORT_REGION_COUNT
                for band in component
            )
            or len(pairs) != 1
            or any(
                band.gap_interval_px.maximum > maximum_material_gap_px
                for band in component
            )
        ):
            continue
        left_id, right_id = next(iter(pairs))
        left = by_id.get(left_id)
        right = by_id.get(right_id)
        if left is None or right is None:
            raise ValueError("separator band references an unregistered edge")
        center = FiniteInterval(
            (
                left.fit_position_interval_px.minimum
                + right.fit_position_interval_px.minimum
            )
            / 2.0,
            (
                left.fit_position_interval_px.maximum
                + right.fit_position_interval_px.maximum
            )
            / 2.0,
        )
        for identity in (left_id, right_id):
            observation = by_id[identity]
            # A strict trace majority already localizes that edge directly.
            # The material center is retained only for the weak side of an
            # otherwise unique local band, where it is output protection and
            # never additional phase authority.
            if observation.support_fraction <= 0.5:
                material_intervals[identity] = center
    values: list[BoundaryEdgeObservation] = []
    for observation in observations:
        if isinstance(observation, BoundaryEdgeObservation):
            roles = authority.get(observation.observation_id)
            material = material_intervals.get(observation.observation_id)
            if roles or material is not None:
                full = observation.full_position_interval_px
                if material is not None:
                    full = FiniteInterval(
                        min(full.minimum, material.minimum),
                        max(full.maximum, material.maximum),
                    )
                observation = replace(
                    observation,
                    qualified_anchor_roles=(
                        observation.qualified_anchor_roles
                        if roles is None
                        else tuple(
                            role
                            for role in (BoundaryRole.START, BoundaryRole.END)
                            if role in roles
                        )
                    ),
                    full_position_interval_px=full,
                )
        values.append(observation)
    return tuple(values)


def _separator_phase_seeds(
    separator_bands: Sequence[SeparatorBandObservation],
    direct: tuple[_AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    *,
    width: float,
    pitch: float,
    prefixes: tuple[float, ...],
) -> tuple[_PhaseSeed, ...]:
    """Project each direct material band onto every legal adjacency once.

    A separator proves END -> material -> START, but it does not know its
    ordinal. Each legal ordinal is therefore one bounded phase hypothesis.
    The template only projects that direct evidence; it never creates a phase
    from its own grid.
    """

    by_id = {item.observation_id: item for item in direct}
    seeds: set[_PhaseSeed] = set()
    for band in separator_bands:
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or BoundaryRole.END not in left.qualified_anchor_roles
            or BoundaryRole.START not in right.qualified_anchor_roles
        ):
            continue
        for adjacency_index in range(template.count - 1):
            end_role = roles[2 * adjacency_index + 1]
            start_role = roles[2 * (adjacency_index + 1)]
            required = (
                (end_role.role_index, left.observation_id),
                (start_role.role_index, right.observation_id),
            )
            for role, anchor in ((end_role, left), (start_role, right)):
                relative = role.slot_index * pitch + prefixes[role.slot_index]
                if role.role == BoundaryRole.END:
                    relative += width
                phase = anchor.coordinate_px - template.direction * relative
                seeds.add(
                    _PhaseSeed(
                        round(phase, 9),
                        round(pitch, 9),
                        required,
                    )
                )
    return tuple(seeds)


def _separator_pair_facts(
    separator_bands: Sequence[SeparatorBandObservation],
    direct: tuple[_AnchorFact, ...],
) -> tuple[tuple[_AnchorFact, _AnchorFact], ...]:
    """Retain exact END/START pairs proved by separator material."""

    by_id = {item.observation_id: item for item in direct}
    pairs: dict[
        tuple[ObservationId, ObservationId],
        tuple[_AnchorFact, _AnchorFact],
    ] = {}
    for band in separator_bands:
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or BoundaryRole.END not in left.qualified_anchor_roles
            or BoundaryRole.START not in right.qualified_anchor_roles
        ):
            continue
        pairs[(left.observation_id, right.observation_id)] = (left, right)
    return tuple(
        pairs[key]
        for key in sorted(pairs, key=lambda value: tuple(map(str, value)))
    )


def _match_roles(
    direct: tuple[_AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    separator_pairs: tuple[tuple[_AnchorFact, _AnchorFact], ...],
    *,
    phase: float,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
    frame_width: PositiveInterval,
    fit_residual_limit_px: float | None,
    required_bindings: tuple[tuple[int, ObservationId], ...] = (),
) -> tuple[tuple[TemplateRole, _AnchorFact], ...]:
    centers = tuple(item.coordinate_px for item in direct)
    used: set[ObservationId] = set()
    used_supports: set[ObservationId] = set()
    used_roles: set[int] = set()
    separator_ids = {
        item.observation_id
        for pair in separator_pairs
        for item in pair
    }
    selected: list[tuple[TemplateRole, _AnchorFact]] = []
    corridor = template_role_refinement_radius_px(pitch)
    has_both_polarities = {item.polarity for item in direct} >= {-1, 1}
    role_by_index = {item.role_index: item for item in roles}
    direct_by_id = {item.observation_id: item for item in direct}

    def candidates(
        role: TemplateRole,
        expected: float,
    ) -> tuple[_AnchorFact, ...]:
        if role.role_index in used_roles:
            return ()
        begin = bisect_left(centers, expected - corridor)
        end = bisect_right(centers, expected + corridor)
        return tuple(
            item
            for item in direct[begin:end]
            if item.observation_id not in used
            and item.independent_support_id not in used_supports
            and (
                fit_residual_limit_px is None
                or item.fit_residual_px <= fit_residual_limit_px
            )
            and (item.role_index is None or item.role_index == role.role_index)
            and (
                not item.qualified_anchor_roles
                or role.role in item.qualified_anchor_roles
            )
        )

    def compatibility_axes(
        role: TemplateRole,
        expected: float,
        item: _AnchorFact,
    ) -> tuple[int, float]:
        return (
            int(
                not item.qualified_anchor_roles
                and has_both_polarities
                and item.polarity not in {0, _expected_polarity(role)}
            ),
            abs(item.coordinate_px - expected),
        )

    def unique_dominant(
        values: Sequence[object],
        axes,
    ) -> object | None:
        """Return one physically dominant value, never an ID/strength tie-break."""

        frontier = []
        for candidate in values:
            candidate_axes = axes(candidate)
            dominated = any(
                all(left <= right + 1.0e-9 for left, right in zip(other_axes, candidate_axes, strict=True))
                and any(left < right - 1.0e-9 for left, right in zip(other_axes, candidate_axes, strict=True))
                for other in values
                if other is not candidate
                for other_axes in (axes(other),)
            )
            if not dominated:
                frontier.append(candidate)
        return frontier[0] if len(frontier) == 1 else None

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

    required: list[tuple[TemplateRole, _AnchorFact]] = []
    for role_index, observation_id in required_bindings:
        role = role_by_index.get(role_index)
        anchor = direct_by_id.get(observation_id)
        if role is None or anchor is None:
            return ()
        expected = _role_position(
            role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        if (
            abs(anchor.coordinate_px - expected) > corridor
            or (
                fit_residual_limit_px is not None
                and anchor.fit_residual_px > fit_residual_limit_px
            )
            or (anchor.role_index is not None and anchor.role_index != role_index)
            or (
                anchor.qualified_anchor_roles
                and role.role not in anchor.qualified_anchor_roles
            )
        ):
            return ()
        required.append((role, anchor))
    required_by_support: dict[
        ObservationId,
        list[tuple[TemplateRole, _AnchorFact]],
    ] = {}
    for item in required:
        required_by_support.setdefault(item[1].independent_support_id, []).append(
            item
        )
    separator_pair_ids = {
        (left.observation_id, right.observation_id)
        for left, right in separator_pairs
    }
    for group in required_by_support.values():
        if len(group) == 1:
            continue
        if len(group) != 2:
            return ()
        ordered_group = tuple(sorted(group, key=lambda item: item[0].role_index))
        (left_role, left), (right_role, right) = ordered_group
        if (
            (left.observation_id, right.observation_id) not in separator_pair_ids
            or left_role.role != BoundaryRole.END
            or right_role.role != BoundaryRole.START
            or right_role.slot_index != left_role.slot_index + 1
        ):
            return ()
    for role, anchor in required:
        used.add(anchor.observation_id)
        used_roles.add(role.role_index)
        selected.append((role, anchor))
    used_supports.update(required_by_support)

    # A separator is one measured END -> material -> START relation.  Bind its
    # exact pair to one adjacency before individual frame edges are considered;
    # independently choosing two edges from different band interpretations
    # would manufacture a separator that was never observed.
    adjacency_roles = tuple(
        (roles[2 * index + 1], roles[2 * (index + 1)])
        for index in range(len(roles) // 2 - 1)
    )
    if direction < 0:
        adjacency_roles = tuple(reversed(adjacency_roles))
    for end_role, start_role in adjacency_roles:
        end_expected = _role_position(
            end_role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        start_expected = _role_position(
            start_role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        end_candidates = {
            item.observation_id: item
            for item in candidates(end_role, end_expected)
        }
        start_candidates = {
            item.observation_id: item
            for item in candidates(start_role, start_expected)
        }
        compatible_pairs = tuple(
            (left, right)
            for left, right in separator_pairs
            if left.observation_id in end_candidates
            and right.observation_id in start_candidates
            and left.independent_support_id not in used_supports
        )
        selected_pair = unique_dominant(
            compatible_pairs,
            lambda pair: (
                *compatibility_axes(end_role, end_expected, pair[0]),
                *compatibility_axes(start_role, start_expected, pair[1]),
            ),
        )
        if selected_pair is None:
            continue
        left, right = selected_pair
        used.update((left.observation_id, right.observation_id))
        used_supports.add(left.independent_support_id)
        used_roles.update((end_role.role_index, start_role.role_index))
        selected.extend(((end_role, left), (start_role, right)))

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
        starts = tuple(
            item
            for item in candidates(start_role, start_expected)
            if item.observation_id not in separator_ids
        )
        ends = tuple(
            item
            for item in candidates(end_role, end_expected)
            if item.observation_id not in separator_ids
        )
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
            selected_pair = unique_dominant(
                pairs,
                lambda pair: (
                    *compatibility_axes(start_role, start_expected, pair[0]),
                    *compatibility_axes(end_role, end_expected, pair[1]),
                ),
            )
            if selected_pair is None:
                # Two fixed-W interpretations are discrete placements.  This
                # seed cannot erase one by support, array order, or identity.
                continue
            start, end = selected_pair
            used.update((start.observation_id, end.observation_id))
            used_supports.update(
                (start.independent_support_id, end.independent_support_id)
            )
            used_roles.update((start_role.role_index, end_role.role_index))
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
            chosen = unique_dominant(
                compatible,
                lambda item: compatibility_axes(role, expected, item),
            )
            if chosen is None:
                continue
            if (
                not chosen.qualified_anchor_roles
                and has_both_polarities
                and chosen.polarity not in {0, _expected_polarity(role)}
                and abs(chosen.coordinate_px - expected) > corridor * 0.35
            ):
                continue
            used.add(chosen.observation_id)
            used_supports.add(chosen.independent_support_id)
            used_roles.add(role.role_index)
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
    phase_authority: FiniteInterval | None,
) -> tuple[float, float, float]:
    if not matches:
        raise ValueError("global template fit requires direct matches")
    straight = tuple(
        item for item in matches if item[1].line_evidence is not None
    )
    straight_matrix = np.asarray(
        [
            (
                1.0,
                float(direction if role.role == BoundaryRole.END else 0),
                float(direction * role.slot_index),
            )
            for role, _anchor in straight
        ],
        dtype=np.float64,
    )
    fit_matches = (
        straight
        if len(straight) >= 3 and np.linalg.matrix_rank(straight_matrix) == 3
        else matches
    )
    matrix = np.asarray(
        [
            (
                1.0,
                float(direction if role.role == BoundaryRole.END else 0),
                float(direction * role.slot_index),
            )
            for role, _anchor in fit_matches
        ],
        dtype=np.float64,
    )
    values = np.asarray(
        [
            anchor.coordinate_px - direction * prefixes[role.slot_index]
            for role, anchor in fit_matches
        ],
        dtype=np.float64,
    )
    solution = None
    if len(fit_matches) >= 3 and np.linalg.matrix_rank(matrix) == 3:
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
        for role, _anchor in fit_matches
    )
    phase_values = sorted(
        anchor.coordinate_px - offset
        for offset, (_role, anchor) in zip(offsets, fit_matches, strict=True)
    )
    phase = float(phase_values[len(phase_values) // 2])
    if solution is not None:
        phase_fit = float(solution[0])
        if math.isfinite(phase_fit):
            phase = phase_fit
    if phase_authority is not None:
        phase = min(
            max(phase, phase_authority.minimum),
            phase_authority.maximum,
        )
    return phase, width, pitch


def _fit_seed(
    seed: _PhaseSeed,
    direct: tuple[_AnchorFact, ...],
    separator_pairs: tuple[tuple[_AnchorFact, _AnchorFact], ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    relations: tuple[LocalAdvanceRelation, ...],
    pitch_authority: FiniteInterval,
    phase_authority: FiniteInterval | None,
    fit_residual_limit_px: float | None,
) -> _BoundFit | None:
    width = (
        template.frame_width_px.minimum
        + template.frame_width_px.maximum
    ) / 2.0
    pitch = seed.pitch_px
    phase = seed.phase_px
    prefixes = _prefixes(relations, template.count)
    matches: tuple[tuple[TemplateRole, _AnchorFact], ...] = ()
    required = set(seed.required_bindings)

    def retains_seed_identity(
        values: tuple[tuple[TemplateRole, _AnchorFact], ...],
    ) -> bool:
        return required.issubset(
            {
                (role.role_index, anchor.observation_id)
                for role, anchor in values
            }
        )

    for _iteration in range(4):
        updated_matches = _match_roles(
            direct,
            template.roles,
            separator_pairs,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            frame_width=template.frame_width_px,
            fit_residual_limit_px=fit_residual_limit_px,
            required_bindings=seed.required_bindings,
        )
        if not updated_matches or not retains_seed_identity(updated_matches):
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
            phase_authority=phase_authority,
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
        if not retains_seed_identity(retained):
            return None
        phase, width, pitch = _linear_fit(
            retained,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            width_authority=template.frame_width_px,
            pitch_authority=pitch_authority,
            gap_authority=template.gap_prior_px,
            phase_authority=phase_authority,
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
    measured_pitch = refine_placement_pitch_interval(
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
    role_full_intervals: list[FiniteInterval] = []
    role_bindings: list[SequenceRoleBinding | None] = []
    for role, canonical in zip(roles, canonical_positions, strict=True):
        observed = by_role.get(role.role_index)
        if observed is None:
            inferred_interval = _inferred_role_interval(
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
            role_intervals.append(inferred_interval)
            role_full_intervals.append(inferred_interval)
            role_bindings.append(None)
        else:
            role_intervals.append(
                FiniteInterval(
                    min(canonical, observed.interval_px.minimum),
                    max(canonical, observed.interval_px.maximum),
                )
            )
            role_full_intervals.append(
                FiniteInterval(
                    min(canonical, observed.full_interval_px.minimum),
                    max(canonical, observed.full_interval_px.maximum),
                )
            )
            role_bindings.append(
                SequenceRoleBinding(
                    observation_id=observed.observation_id,
                    independent_support_id=observed.independent_support_id,
                    canonical_position_px=observed.coordinate_px,
                    fit_position_interval_px=observed.interval_px,
                    full_position_interval_px=observed.full_interval_px,
                    line_evidence=observed.line_evidence,
                )
            )
    direct_ids = tuple(
        binding.observation_id
        for binding in role_bindings
        if binding is not None
    )
    support_groups: dict[int, list[tuple[TemplateRole, _AnchorFact]]] = {}
    for role, anchor in matches:
        support_groups.setdefault((role.role_index + 1) // 2, []).append(
            (role, anchor)
        )
    phase_support_coverage = sum(
        max(anchor.support_fraction for _role, anchor in group)
        for group in support_groups.values()
    )
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
        model_role_positions_px=canonical_positions,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(role_full_intervals),
        role_bindings=tuple(role_bindings),
        local_advance_relations=relations,
        contradicted_observation_count=max(0, len(direct) - len(direct_ids)),
        residual_sum_px=residual_sum,
        phase_support_coverage=phase_support_coverage,
    )
    return _BoundFit(fit, residual_compatible)


def _rank(value: _BoundFit) -> tuple[object, ...]:
    fit = value.fit
    return (
        int(value.residual_compatible),
        fit.phase_support_count,
        fit.phase_support_coverage,
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
