"""Bind role-free observations to one bounded fixed-template phase."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
import math
from typing import Sequence

import numpy as np
from scipy.optimize import lsq_linear

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import (
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .separator_material import normal_separator_material_bands
from .template_model import (
    LatticeParameterFitBasis,
    LocalAdvanceRelation,
    PitchFit,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleBinding,
    SequenceRoleLineEvidence,
    TemplateRole,
    TemplateSpec,
    most_constrained_lattice_parameter_fit_basis,
    phase_lattice_fit_from_absolute,
    template_role_refinement_radius_px,
)
from .template_phase_model import PhaseWinnerBasis
from .template_pitch import refine_placement_pitch_interval
from .template_evidence import separator_support_authority


_NUMERIC_RESIDUAL_EPSILON_PX = 1.0e-9
_LINEAR_CONSTRAINT_EPSILON_PX = 1.0e-7


@dataclass(frozen=True)
class _AnchorFact:
    observation_id: ObservationId
    evidence_group_id: ObservationId
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
class _LocalRoleRefinement:
    fit: SequenceFit
    role_lookup_count: int
    binding_count: int


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
                evidence_group_id=separator_support_ids.get(
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
            if band.material_support_region_count
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
    eligible_bands = normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=maximum_material_gap_px,
    )
    authority = _separator_role_authority(observations, eligible_bands)
    if not authority and not eligible_bands:
        return tuple(observations)
    by_id = {
        observation.observation_id: observation
        for observation in observations
        if isinstance(observation, BoundaryEdgeObservation)
    }
    support_ids = separator_support_authority(eligible_bands)
    components: dict[ObservationId, list[SeparatorBandObservation]] = {}
    for band in eligible_bands:
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
                band.material_support_region_count
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
                        tuple(
                            role
                            for role in (BoundaryRole.START, BoundaryRole.END)
                            if role in roles
                        )
                        if roles is not None
                        else observation.qualified_anchor_roles
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
    for band in normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=template.gap_prior_px.maximum,
    ):
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
    *,
    maximum_material_gap_px: float,
) -> tuple[tuple[_AnchorFact, _AnchorFact], ...]:
    """Retain exact END/START pairs proved by separator material."""

    by_id = {item.observation_id: item for item in direct}
    pairs: dict[
        tuple[ObservationId, ObservationId],
        tuple[_AnchorFact, _AnchorFact],
    ] = {}
    for band in normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=maximum_material_gap_px,
    ):
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


def _refine_local_role_bindings(
    fit: SequenceFit,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
) -> _LocalRoleRefinement:
    """Bind uniquely closed local edges after global phase is immutable.

    The global fit remains the sole owner of phase and pitch.  This pass only
    replaces an unbound role near that fixed grid when source pixels provide
    one role-qualified fitted line and physical W or separator material makes
    its local interpretation unique.  It performs no pixel query, ranking, or
    candidate Cartesian product.
    """

    observations = _with_separator_role_authority(
        observations,
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    eligible_bands = normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    support_ids = separator_support_authority(eligible_bands)
    facts = _facts(
        observations,
        separator_support_ids=support_ids,
    )
    by_id = {item.observation_id: item for item in facts}
    roles = fit.template.roles
    corridor = template_role_refinement_radius_px(
        fit.pitch_fit.canonical_pitch_px
    )
    bindings = list(fit.role_bindings)
    bound_ids = {
        binding.observation_id
        for binding in bindings
        if binding is not None
    }

    # One observation may refine at most one already placed role.  A line that
    # falls in more than one role corridor retains validation-only authority.
    candidate_roles: dict[ObservationId, list[int]] = {}
    for role, expected in zip(
        roles,
        fit.model_role_positions_px,
        strict=True,
    ):
        for fact in facts:
            if (
                fit.role_bindings[role.role_index] is None
                and fact.observation_id not in bound_ids
                and fact.line_evidence is not None
                and role.role in fact.qualified_anchor_roles
                and abs(fact.coordinate_px - expected) <= corridor
            ):
                candidate_roles.setdefault(fact.observation_id, []).append(
                    role.role_index
                )
    candidate_lists: dict[int, list[_AnchorFact]] = {
        role.role_index: [] for role in roles
    }
    for identity, role_indices in candidate_roles.items():
        if len(role_indices) == 1:
            candidate_lists[role_indices[0]].append(by_id[identity])
    candidates_by_role = {
        role_index: tuple(
            sorted(
                values,
                key=lambda item: (
                    fit.template.direction * item.coordinate_px,
                    str(item.observation_id),
                ),
            )
        )
        for role_index, values in candidate_lists.items()
    }

    def binding_for(fact: _AnchorFact) -> SequenceRoleBinding:
        return SequenceRoleBinding(
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            observation_id=fact.observation_id,
            evidence_group_id=fact.evidence_group_id,
            canonical_position_px=fact.coordinate_px,
            fit_position_interval_px=fact.interval_px,
            full_position_interval_px=fact.full_interval_px,
            line_evidence=fact.line_evidence,
        )

    def width_compatible(start_px: float, end_px: float) -> bool:
        width = fit.template.direction * (end_px - start_px)
        return (
            fit.template.frame_width_px.minimum - 1.0e-9
            <= width
            <= fit.template.frame_width_px.maximum + 1.0e-9
        )

    def fact_fits_bound_frame(role_index: int, fact: _AnchorFact) -> bool:
        other_index = role_index + 1 if role_index % 2 == 0 else role_index - 1
        other = bindings[other_index]
        if other is None:
            return True
        if other.evidence_group_id == fact.evidence_group_id:
            return False
        if role_index % 2 == 0:
            return width_compatible(
                fact.coordinate_px,
                other.canonical_position_px,
            )
        return width_compatible(
            other.canonical_position_px,
            fact.coordinate_px,
        )

    def bind(role_index: int, fact: _AnchorFact) -> None:
        if bindings[role_index] is not None or fact.observation_id in bound_ids:
            raise ValueError("local refinement attempted a duplicate binding")
        bindings[role_index] = binding_for(fact)
        bound_ids.add(fact.observation_id)

    # A source-spanning separator is an atomic END -> material -> START fact.
    # Apply it before individual frame closure so its two sides cannot be
    # mixed with another band interpretation.
    bound_role_by_id = {
        binding.observation_id: role_index
        for role_index, binding in enumerate(bindings)
        if binding is not None
    }
    relation_pairs: dict[int, set[tuple[ObservationId, ObservationId]]] = {}
    for band in separator_bands:
        if (
            band.material_support_region_count < SPATIAL_SUPPORT_REGION_COUNT
            or max(
                band.gap_interval_px.minimum,
                fit.template.gap_prior_px.minimum,
            )
            > min(
                band.gap_interval_px.maximum,
                fit.template.gap_prior_px.maximum,
            )
        ):
            continue
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or left.line_evidence is None
            or right.line_evidence is None
            or left.evidence_group_id != right.evidence_group_id
        ):
            continue
        left_roles = (
            [bound_role_by_id[left.observation_id]]
            if left.observation_id in bound_role_by_id
            else candidate_roles.get(left.observation_id, [])
        )
        right_roles = (
            [bound_role_by_id[right.observation_id]]
            if right.observation_id in bound_role_by_id
            else candidate_roles.get(right.observation_id, [])
        )
        if len(left_roles) != 1 or len(right_roles) != 1:
            continue
        left_role = left_roles[0]
        right_role = right_roles[0]
        if (
            left_role % 2 != 1
            or right_role != left_role + 1
            or not fact_fits_bound_frame(left_role, left)
            or not fact_fits_bound_frame(right_role, right)
        ):
            continue
        relation_pairs.setdefault(left_role // 2, set()).add(
            (left.observation_id, right.observation_id)
        )
    for adjacency_index in range(max(0, fit.template.count - 1)):
        pairs = relation_pairs.get(adjacency_index, set())
        if len(pairs) != 1:
            continue
        left_id, right_id = next(iter(pairs))
        left_role = 2 * adjacency_index + 1
        right_role = left_role + 1
        if bindings[left_role] is None:
            bind(left_role, by_id[left_id])
        if bindings[right_role] is None:
            bind(right_role, by_id[right_id])

    def remaining(role_index: int) -> tuple[_AnchorFact, ...]:
        return tuple(
            item
            for item in candidates_by_role[role_index]
            if item.observation_id not in bound_ids
        )

    def normalized(value: float) -> float:
        return fit.template.direction * value

    def unique_missing(
        candidates: tuple[_AnchorFact, ...],
        *,
        other: SequenceRoleBinding,
        missing_start: bool,
    ) -> _AnchorFact | None:
        values = tuple(normalized(item.coordinate_px) for item in candidates)
        other_px = normalized(other.canonical_position_px)
        if missing_start:
            minimum = other_px - fit.template.frame_width_px.maximum
            maximum = other_px - fit.template.frame_width_px.minimum
        else:
            minimum = other_px + fit.template.frame_width_px.minimum
            maximum = other_px + fit.template.frame_width_px.maximum
        begin = bisect_left(values, minimum - 1.0e-9)
        end = bisect_right(values, maximum + 1.0e-9)
        if end - begin != 1:
            return None
        selected = candidates[begin]
        if selected.evidence_group_id == other.evidence_group_id:
            return None
        return selected

    def unique_pair(
        starts: tuple[_AnchorFact, ...],
        ends: tuple[_AnchorFact, ...],
    ) -> tuple[_AnchorFact, _AnchorFact] | None:
        end_values = tuple(normalized(item.coordinate_px) for item in ends)
        selected: tuple[_AnchorFact, _AnchorFact] | None = None
        for start in starts:
            start_px = normalized(start.coordinate_px)
            begin = bisect_left(
                end_values,
                start_px + fit.template.frame_width_px.minimum - 1.0e-9,
            )
            end = bisect_right(
                end_values,
                start_px + fit.template.frame_width_px.maximum + 1.0e-9,
            )
            if end - begin > 1:
                return None
            if end == begin:
                continue
            candidate = ends[begin]
            if candidate.evidence_group_id == start.evidence_group_id:
                continue
            if selected is not None:
                return None
            selected = (start, candidate)
        return selected

    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        start = bindings[start_index]
        end = bindings[end_index]
        if start is None and end is None:
            pair = unique_pair(
                remaining(start_index),
                remaining(end_index),
            )
            if pair is not None:
                bind(start_index, pair[0])
                bind(end_index, pair[1])
        elif start is None:
            candidate = unique_missing(
                remaining(start_index),
                other=end,
                missing_start=True,
            )
            if candidate is not None:
                bind(start_index, candidate)
        elif end is None:
            candidate = unique_missing(
                remaining(end_index),
                other=start,
                missing_start=False,
            )
            if candidate is not None:
                bind(end_index, candidate)

    added = tuple(
        binding
        for old, binding in zip(fit.role_bindings, bindings, strict=True)
        if old is None and binding is not None
    )
    if not added:
        return _LocalRoleRefinement(
            fit,
            len(roles) * len(facts),
            0,
        )
    added_ids = {item.observation_id for item in added}
    role_intervals = list(fit.model_role_intervals_px)
    full_role_intervals = list(fit.model_full_role_intervals_px)
    for role_index, binding in enumerate(bindings):
        if binding is None or binding.observation_id not in added_ids:
            continue
        canonical = fit.model_role_positions_px[role_index]
        current = role_intervals[role_index]
        role_intervals[role_index] = FiniteInterval(
            min(current.minimum, binding.fit_position_interval_px.minimum, canonical),
            max(current.maximum, binding.fit_position_interval_px.maximum, canonical),
        )
        current_full = full_role_intervals[role_index]
        full_role_intervals[role_index] = FiniteInterval(
            min(
                current_full.minimum,
                binding.full_position_interval_px.minimum,
                canonical,
            ),
            max(
                current_full.maximum,
                binding.full_position_interval_px.maximum,
                canonical,
            ),
        )
    direct_added = sum(by_id[item.observation_id].direct for item in added)
    refined = replace(
        fit,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(full_role_intervals),
        role_bindings=tuple(bindings),
        contradicted_observation_count=max(
            0,
            fit.contradicted_observation_count - direct_added,
        ),
    )
    return _LocalRoleRefinement(
        refined,
        len(roles) * len(facts),
        len(added),
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
            and item.evidence_group_id not in used_supports
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
        required_by_support.setdefault(item[1].evidence_group_id, []).append(
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
            and left.evidence_group_id not in used_supports
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
        used_supports.add(left.evidence_group_id)
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
                (start.evidence_group_id, end.evidence_group_id)
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
            used_supports.add(chosen.evidence_group_id)
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
) -> tuple[float, float, float, LatticeParameterFitBasis]:
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
    fit_basis = LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER
    if len(fit_matches) >= 3 and np.linalg.matrix_rank(matrix) == 3:
        solution = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=width_authority,
            pitch_authority=pitch_authority,
            gap_authority=gap_authority,
            phase_authority=phase_authority,
        )
        phase, width, pitch, fit_basis = solution
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
        phase = float(solution[0])
    elif phase_authority is not None:
        phase = min(
            max(phase, phase_authority.minimum),
            phase_authority.maximum,
        )
    return phase, width, pitch, fit_basis


def _bounded_lattice_least_squares(
    matrix: np.ndarray,
    values: np.ndarray,
    *,
    width_authority: PositiveInterval,
    pitch_authority: FiniteInterval,
    gap_authority: FiniteInterval,
    phase_authority: FiniteInterval | None,
) -> tuple[float, float, float, LatticeParameterFitBasis]:
    """Fit one continuous lattice inside every compiled physical interval.

    The unknown vector is ``(phase, W, pitch)``.  A rank-three direct system
    may have an unconstrained least-squares solution just outside the coupled
    ``pitch - W`` interval even though a nearby physical solution exists.
    Discarding both fitted axes in that case creates a synthetic source-wide
    drift.  This fixed three-variable solve keeps the nearest joint solution;
    it neither widens an authority nor compares placements.
    """

    def snap_numeric_boundary(candidate: np.ndarray) -> np.ndarray:
        snapped = candidate.copy()
        for index, authority in (
            (1, width_authority),
            (2, pitch_authority),
        ):
            if (
                authority.minimum - _LINEAR_CONSTRAINT_EPSILON_PX
                <= snapped[index]
                < authority.minimum
            ):
                snapped[index] = authority.minimum
            elif (
                authority.maximum
                < snapped[index]
                <= authority.maximum + _LINEAR_CONSTRAINT_EPSILON_PX
            ):
                snapped[index] = authority.maximum
        if phase_authority is not None:
            if (
                phase_authority.minimum - _LINEAR_CONSTRAINT_EPSILON_PX
                <= snapped[0]
                < phase_authority.minimum
            ):
                snapped[0] = phase_authority.minimum
            elif (
                phase_authority.maximum
                < snapped[0]
                <= phase_authority.maximum + _LINEAR_CONSTRAINT_EPSILON_PX
            ):
                snapped[0] = phase_authority.maximum
        gap = float(snapped[2] - snapped[1])
        if (
            gap_authority.minimum - _LINEAR_CONSTRAINT_EPSILON_PX
            <= gap
            < gap_authority.minimum
        ):
            target_gap = gap_authority.minimum
        elif (
            gap_authority.maximum
            < gap
            <= gap_authority.maximum + _LINEAR_CONSTRAINT_EPSILON_PX
        ):
            target_gap = gap_authority.maximum
        else:
            target_gap = None
        if target_gap is not None:
            snapped[2] = snapped[1] + target_gap
            if target_gap == gap_authority.minimum:
                while snapped[2] - snapped[1] < target_gap:
                    snapped[2] = math.nextafter(snapped[2], math.inf)
            else:
                while snapped[2] - snapped[1] > target_gap:
                    snapped[2] = math.nextafter(snapped[2], -math.inf)
            if snapped[2] < pitch_authority.minimum:
                snapped[2] = pitch_authority.minimum
                snapped[1] = snapped[2] - target_gap
            elif snapped[2] > pitch_authority.maximum:
                snapped[2] = pitch_authority.maximum
                snapped[1] = snapped[2] - target_gap
        return snapped

    def inside_authorities(candidate: np.ndarray) -> bool:
        return (
            width_authority.minimum <= candidate[1] <= width_authority.maximum
            and pitch_authority.contains(float(candidate[2]))
            and gap_authority.contains(float(candidate[2] - candidate[1]))
            and (
                phase_authority is None
                or phase_authority.contains(float(candidate[0]))
            )
        )

    def box_fit(
        design: np.ndarray,
        target: np.ndarray,
        lower: tuple[float, ...],
        upper: tuple[float, ...],
    ) -> np.ndarray:
        fixed = tuple(
            index
            for index, (minimum, maximum) in enumerate(
                zip(lower, upper, strict=True)
            )
            if minimum == maximum
        )
        free = tuple(index for index in range(len(lower)) if index not in fixed)
        candidate = np.empty(len(lower), dtype=np.float64)
        adjusted = target.copy()
        if fixed:
            fixed_values = np.asarray([lower[index] for index in fixed])
            candidate[list(fixed)] = fixed_values
            adjusted = adjusted - design[:, fixed] @ fixed_values
        if free:
            result = lsq_linear(
                design[:, free],
                adjusted,
                bounds=(
                    np.asarray([lower[index] for index in free]),
                    np.asarray([upper[index] for index in free]),
                ),
                method="bvls",
                tol=1.0e-12,
                max_iter=50,
            )
            if not result.success:
                raise RuntimeError("bounded lattice box fit did not converge")
            candidate[list(free)] = result.x
        return candidate

    phase_bounds = (
        (-math.inf, math.inf)
        if phase_authority is None
        else (phase_authority.minimum, phase_authority.maximum)
    )
    unconstrained = snap_numeric_boundary(
        np.linalg.lstsq(matrix, values, rcond=None)[0]
    )
    if inside_authorities(unconstrained):
        return (
            float(unconstrained[0]),
            float(unconstrained[1]),
            float(unconstrained[2]),
            LatticeParameterFitBasis.DIRECT_LEAST_SQUARES,
        )
    selected = snap_numeric_boundary(
        box_fit(
            matrix,
            values,
            (phase_bounds[0], width_authority.minimum, pitch_authority.minimum),
            (phase_bounds[1], width_authority.maximum, pitch_authority.maximum),
        )
    )
    gap = float(selected[2] - selected[1])
    if not gap_authority.contains(gap):
        target_gap = (
            gap_authority.minimum
            if gap < gap_authority.minimum
            else gap_authority.maximum
        )
        width_minimum = max(
            width_authority.minimum,
            pitch_authority.minimum - target_gap,
        )
        width_maximum = min(
            width_authority.maximum,
            pitch_authority.maximum - target_gap,
        )
        if width_minimum > width_maximum:
            raise RuntimeError("compiled lattice authorities have no feasible fit")
        reduced = box_fit(
            np.column_stack((matrix[:, 0], matrix[:, 1] + matrix[:, 2])),
            values - matrix[:, 2] * target_gap,
            (phase_bounds[0], width_minimum),
            (phase_bounds[1], width_maximum),
        )
        selected = snap_numeric_boundary(
            np.asarray((reduced[0], reduced[1], reduced[1] + target_gap))
        )
    if not inside_authorities(selected):
        raise RuntimeError(
            "bounded lattice least-squares fit escaped authority: "
            f"phase={selected[0]}, W={selected[1]}, pitch={selected[2]}, "
            f"gap={selected[2] - selected[1]}"
        )
    return (
        float(selected[0]),
        float(selected[1]),
        float(selected[2]),
        LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES,
    )


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
    fit_basis = LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER
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
        updated_phase, updated_width, updated_pitch, updated_basis = updated
        converged = updated_matches == matches and (
            updated_phase,
            updated_width,
            updated_pitch,
        ) == (phase, width, pitch)
        fit_basis = most_constrained_lattice_parameter_fit_basis(
            fit_basis,
            updated_basis,
        )
        if converged:
            break
        matches = updated_matches
        phase, width, pitch = updated_phase, updated_width, updated_pitch
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
        phase, width, pitch, retained_basis = _linear_fit(
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
        fit_basis = most_constrained_lattice_parameter_fit_basis(
            fit_basis,
            retained_basis,
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
    residual_compatibility_limit = max(2.0, width * 0.015)
    # The physical contract is inclusive at the residual limit.  LAPACK
    # implementations can place the same least-squares result a few ulps on
    # either side of that exact boundary, so absorb only numerically negligible
    # pixel error here; this is not an additional geometry tolerance.
    residual_compatible = (
        residual_mean
        <= residual_compatibility_limit + _NUMERIC_RESIDUAL_EPSILON_PX
    )
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
                    use=SequenceBindingUse.PHASE_ANCHOR,
                    observation_id=observed.observation_id,
                    evidence_group_id=observed.evidence_group_id,
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
    lattice_fit = phase_lattice_fit_from_absolute(
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
        lattice_parameter_fit_basis=fit_basis,
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
