"""Bounded sequence phase fitting."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Sequence

import numpy as np
from scipy.optimize import lsq_linear

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .model import BoundaryRole
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    LatticeParameterFitBasis,
    PitchFit,
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleBinding,
    TemplateRole,
    TemplateSpec,
    adjacency_prefix_coefficients,
    adjacency_prefix_positions,
    adjacency_prefix_intervals,
    template_role_position,
    template_role_interval,
    most_constrained_lattice_parameter_fit_basis,
    phase_lattice_fit_from_absolute,
    realize_adjacency_relations,
    realize_adjacency_relations_at_role_positions,
    template_role_refinement_radius_px,
)
from .template_pitch import refine_placement_pitch_interval
from . import (
    template_phase_candidate_model as _candidate_model,
    template_phase_observations as _observations,
)


_LINEAR_CONSTRAINT_EPSILON_PX = 1.0e-7


@dataclass(frozen=True, slots=True)
class _PhaseMatchingIndex:
    """Read-only O(N + R + P) indices for one exact phase-fitting input."""

    direct: tuple[_candidate_model._AnchorFact, ...]
    roles: tuple[TemplateRole, ...]
    separator_pairs: tuple[
        tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...
    ]
    centers: tuple[float, ...] = field(init=False)
    optional_separator_pairs: tuple[
        tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...
    ] = field(init=False)
    separator_ids: frozenset[ObservationId] = field(init=False)
    has_both_polarities: bool = field(init=False)
    role_by_index: Mapping[int, TemplateRole] = field(init=False)
    direct_by_id: Mapping[ObservationId, _candidate_model._AnchorFact] = field(init=False)
    separator_pair_ids: frozenset[
        tuple[ObservationId, ObservationId]
    ] = field(init=False)

    def __post_init__(self) -> None:
        optional_pairs = tuple(
            (left, right)
            for left, right in self.separator_pairs
            if BoundaryRole.END in left.qualified_anchor_roles
            and BoundaryRole.START in right.qualified_anchor_roles
        )
        object.__setattr__(self, "centers", tuple(item.coordinate_px for item in self.direct))
        object.__setattr__(self, "optional_separator_pairs", optional_pairs)
        object.__setattr__(self, "separator_ids", frozenset(
            item.observation_id for pair in optional_pairs for item in pair
        ))
        object.__setattr__(self, "has_both_polarities", {
            item.polarity for item in self.direct
        } >= {-1, 1})
        object.__setattr__(self, "role_by_index", MappingProxyType({
            item.role_index: item for item in self.roles
        }))
        object.__setattr__(self, "direct_by_id", MappingProxyType({
            item.observation_id: item for item in self.direct
        }))
        object.__setattr__(self, "separator_pair_ids", frozenset(
            (left.observation_id, right.observation_id)
            for left, right in self.separator_pairs
        ))

    def validate_input(
        self,
        direct: tuple[_candidate_model._AnchorFact, ...],
        roles: tuple[TemplateRole, ...],
        separator_pairs: tuple[
            tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...
        ],
    ) -> None:
        if (
            self.direct is not direct
            or self.separator_pairs is not separator_pairs
            or self.roles != roles
        ):
            raise ValueError("phase matching index belongs to a different input")


def _match_roles(
    direct: tuple[_candidate_model._AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    separator_pairs: tuple[tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...],
    *,
    phase: float,
    width: float,
    pitch: float,
    direction: int,
    prefixes: tuple[float, ...],
    frame_width: PositiveInterval,
    fit_residual_limit_px: float | None,
    required_bindings: tuple[tuple[int, ObservationId], ...] = (),
    adjacency_relations: tuple[AdjacencyRelation, ...] = (),
    matching_index: _PhaseMatchingIndex | None = None,
) -> tuple[tuple[TemplateRole, _candidate_model._AnchorFact], ...]:
    index = matching_index or _PhaseMatchingIndex(direct, roles, separator_pairs)
    index.validate_input(direct, roles, separator_pairs)
    centers = index.centers
    used: set[ObservationId] = set()
    used_supports: set[ObservationId] = set()
    used_roles: set[int] = set()
    optional_separator_pairs = index.optional_separator_pairs
    separator_ids = index.separator_ids
    selected: list[tuple[TemplateRole, _candidate_model._AnchorFact]] = []
    corridor = template_role_refinement_radius_px(pitch)
    has_both_polarities = index.has_both_polarities
    role_by_index = index.role_by_index
    direct_by_id = index.direct_by_id
    contact_roles = {
        item.shared_edge_observation_id: (
            2 * item.relation_ordinal - 1,
            2 * item.relation_ordinal,
        )
        for item in adjacency_relations
        if isinstance(item, ContactRelation)
    }
    separator_pair_ids = index.separator_pair_ids
    required_by_role = dict(required_bindings)
    material_seed_roles = {
        (index, identity)
        for end_index, end_id in required_bindings
        if end_index % 2 == 1
        for start_id in (required_by_role.get(end_index + 1),)
        if (end_id, start_id) in separator_pair_ids
        for index, identity in (
            (end_index, end_id), (end_index + 1, start_id)
        )
    }

    def seed_line_fit_compatible(item: _candidate_model._AnchorFact) -> bool:
        # A complete direct family can test its own seed from the raw physical
        # proof. Optional matching keeps the statistical connection contract:
        # a rough line must not silently rewrite another anchor's hypothesis.
        return (
            fit_residual_limit_px is None
            or item.fit_residual_px <= fit_residual_limit_px
            or (
                item.source_spanning_direct_line
                and item.line_evidence is not None
                and item.line_evidence.physical_line_region is not None
            )
        )

    def candidates(
        role: TemplateRole,
        expected: float,
    ) -> tuple[_candidate_model._AnchorFact, ...]:
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
            and (
                not item.qualified_anchor_roles
                or role.role in item.qualified_anchor_roles
            )
        )

    def compatibility_axes(
        role: TemplateRole,
        expected: float,
        item: _candidate_model._AnchorFact,
    ) -> tuple[int, float]:
        return (
            int(
                not item.qualified_anchor_roles
                and has_both_polarities
                and item.polarity not in {0, _observations._expected_polarity(role)}
            ),
            abs(item.coordinate_px - expected),
        )

    def unique_dominant(
        values: Sequence[object],
        axes,
    ) -> object | None:
        """Return one physically dominant value, never an ID/strength tie-break."""

        measured = tuple((value, axes(value)) for value in values)
        frontier = []
        for candidate, candidate_axes in measured:
            dominated = any(
                all(left <= right + 1.0e-9 for left, right in zip(other_axes, candidate_axes, strict=True))
                and any(left < right - 1.0e-9 for left, right in zip(other_axes, candidate_axes, strict=True))
                for other, other_axes in measured
                if other is not candidate
            )
            if not dominated:
                frontier.append(candidate)
        return frontier[0] if len(frontier) == 1 else None

    def width_compatible(start: _candidate_model._AnchorFact, end: _candidate_model._AnchorFact) -> bool:
        low = direction * (end.interval_px.minimum - start.interval_px.maximum)
        high = direction * (end.interval_px.maximum - start.interval_px.minimum)
        if direction < 0:
            low, high = high, low
        return max(low, frame_width.minimum) <= min(
            high,
            frame_width.maximum,
        )

    required: list[tuple[TemplateRole, _candidate_model._AnchorFact]] = []
    for role_index, observation_id in required_bindings:
        role = role_by_index.get(role_index)
        anchor = direct_by_id.get(observation_id)
        if role is None or anchor is None:
            return ()
        expected = template_role_position(
            role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        if (
            abs(anchor.coordinate_px - expected) > corridor
            or not seed_line_fit_compatible(anchor)
            or (
                anchor.qualified_anchor_roles
                and role.role not in anchor.qualified_anchor_roles
                and role_index
                not in contact_roles.get(anchor.observation_id, ())
                and (role_index, anchor.observation_id)
                not in material_seed_roles
            )
        ):
            return ()
        required.append((role, anchor))
    required_by_support: dict[
        ObservationId,
        list[tuple[TemplateRole, _candidate_model._AnchorFact]],
    ] = {}
    for item in required:
        required_by_support.setdefault(item[1].evidence_group_id, []).append(
            item
        )
    for group in required_by_support.values():
        if len(group) == 1:
            continue
        if len(group) != 2:
            return ()
        ordered_group = tuple(sorted(group, key=lambda item: item[0].role_index))
        (left_role, left), (right_role, right) = ordered_group
        is_contact = (
            left.observation_id == right.observation_id
            and contact_roles.get(left.observation_id)
            == (left_role.role_index, right_role.role_index)
        )
        is_separator = (
            (left.observation_id, right.observation_id) in separator_pair_ids
            and left_role.role == BoundaryRole.END
            and right_role.role == BoundaryRole.START
            and right_role.slot_index == left_role.slot_index + 1
        )
        if not (is_contact or is_separator):
            return ()
    for role, anchor in required:
        used.add(anchor.observation_id)
        used_roles.add(role.role_index)
        selected.append((role, anchor))
    used_supports.update(required_by_support)

    expected_positions = {
        role.role_index: template_role_position(
            role,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=direction,
            prefixes=prefixes,
        )
        for role in roles
    }
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
        end_expected = expected_positions[end_role.role_index]
        start_expected = expected_positions[start_role.role_index]
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
            for left, right in optional_separator_pairs
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
    frame_width_center = (frame_width.minimum + frame_width.maximum) / 2.0
    for start_role, end_role in slot_roles:
        start_expected = expected_positions[start_role.role_index]
        end_expected = expected_positions[end_role.role_index]
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
        pairs: list[tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact]] = []
        for start in starts:
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
                and chosen.polarity not in {0, _observations._expected_polarity(role)}
                and abs(chosen.coordinate_px - expected) > corridor * 0.35
            ):
                continue
            used.add(chosen.observation_id)
            used_supports.add(chosen.evidence_group_id)
            used_roles.add(role.role_index)
            selected.append((role, chosen))
    return tuple(sorted(selected, key=lambda item: item[0].role_index))


def _linear_fit(
    matches: tuple[tuple[TemplateRole, _candidate_model._AnchorFact], ...],
    *,
    width: float,
    pitch: float,
    direction: int,
    relations: tuple[AdjacencyRelation, ...],
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

    # Relations stay fixed during this fit; START/END reuse the same slot prefix.
    prefix_by_slot = {}
    for role, _anchor in matches:
        if role.slot_index not in prefix_by_slot:
            prefix_by_slot[role.slot_index] = adjacency_prefix_coefficients(
                relations, role.slot_index
            )

    def coefficients(role: TemplateRole) -> tuple[float, float, float]:
        width_count, pitch_count, _fixed_delta = prefix_by_slot[role.slot_index]
        return (
            1.0,
            float(
                direction
                * (width_count + int(role.role == BoundaryRole.END))
            ),
            float(direction * pitch_count),
        )

    def fixed_delta(role: TemplateRole) -> float:
        return prefix_by_slot[role.slot_index][2]

    for fit_matches in (straight, matches):
        matrix = np.asarray(
            [coefficients(role) for role, _anchor in fit_matches],
            dtype=np.float64,
        )
        values = np.asarray(
            [
                anchor.coordinate_px - direction * fixed_delta(role)
                for role, anchor in fit_matches
            ],
            dtype=np.float64,
        )
        unconstrained = None
        full_rank = False
        if len(fit_matches) >= 3:
            unconstrained, _residuals, rank, _singular_values = np.linalg.lstsq(
                matrix, values, rcond=None
            )
            full_rank = rank == 3
        if full_rank or len(straight) == len(matches):
            break
    fit_basis = LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER
    if full_rank:
        solution = _bounded_lattice_least_squares(
            matrix,
            values,
            width_authority=width_authority,
            pitch_authority=pitch_authority,
            gap_authority=gap_authority,
            phase_authority=phase_authority,
            unconstrained=unconstrained,
        )
        phase, width, pitch, fit_basis = solution
        return float(phase), width, pitch, fit_basis
    offsets = tuple(
        coefficients(role)[1] * width
        + coefficients(role)[2] * pitch
        + direction * fixed_delta(role)
        for role, _anchor in fit_matches
    )
    phase_values = sorted(
        anchor.coordinate_px - offset
        for offset, (_role, anchor) in zip(offsets, fit_matches, strict=True)
    )
    phase = float(phase_values[len(phase_values) // 2])
    if phase_authority is not None:
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
    unconstrained: np.ndarray | None = None,
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

    def inside_box(candidate: np.ndarray) -> bool:
        return (
            width_authority.minimum <= candidate[1] <= width_authority.maximum
            and pitch_authority.contains(float(candidate[2]))
            and (
                phase_authority is None
                or phase_authority.contains(float(candidate[0]))
            )
        )

    def inside_authorities(candidate: np.ndarray) -> bool:
        return inside_box(candidate) and gap_authority.contains(
            float(candidate[2] - candidate[1])
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
    if unconstrained is None:
        unconstrained = np.linalg.lstsq(matrix, values, rcond=None)[0]
    box_fit_required = not inside_box(unconstrained)
    unconstrained = snap_numeric_boundary(unconstrained)
    if inside_authorities(unconstrained):
        return (
            float(unconstrained[0]),
            float(unconstrained[1]),
            float(unconstrained[2]),
            LatticeParameterFitBasis.DIRECT_LEAST_SQUARES,
        )
    selected = unconstrained
    if box_fit_required or not inside_box(selected):
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
    seed: _candidate_model._PhaseSeed,
    direct: tuple[_candidate_model._AnchorFact, ...],
    separator_pairs: tuple[tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    relations: tuple[AdjacencyRelation, ...],
    pitch_authority: FiniteInterval,
    phase_authority: FiniteInterval | None,
    fit_residual_limit_px: float | None,
    phase_anchor_authority_ceiling: (
        frozenset[tuple[int, ObservationId]] | None
    ) = None,
    *,
    matching_index: _PhaseMatchingIndex | None = None,
) -> _candidate_model._BoundFit | None:
    matching_roles = template.roles
    index = matching_index or _PhaseMatchingIndex(direct, matching_roles, separator_pairs)
    index.validate_input(direct, matching_roles, separator_pairs)
    width = (
        template.frame_width_px.minimum
        + template.frame_width_px.maximum
    ) / 2.0
    seed_width = width
    pitch = seed.pitch_px
    phase = seed.phase_px
    fit_basis = LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER
    relations = seed.adjacency_relations or relations
    relations = realize_adjacency_relations(
        relations,
        frame_width_interval_px=template.frame_width_px,
        pitch_interval_px=pitch_authority,
        frame_width_px=width,
        pitch_px=pitch,
    )
    prefixes = adjacency_prefix_positions(relations, template.count)
    matches: tuple[tuple[TemplateRole, _candidate_model._AnchorFact], ...] = ()
    required = set(seed.required_bindings)

    def retains_seed_identity(
        values: tuple[tuple[TemplateRole, _candidate_model._AnchorFact], ...],
    ) -> bool:
        return required.issubset(
            {
                (role.role_index, anchor.observation_id)
                for role, anchor in values
            }
        )

    def compatible_subset() -> tuple[tuple[TemplateRole, _candidate_model._AnchorFact], ...]:
        residual_limit = max(3.0, width * 0.035)
        return tuple(
            (role, anchor)
            for role, anchor in matches
            if abs(
                anchor.coordinate_px
                - template_role_position(
                    role,
                    phase=phase,
                    width=width,
                    pitch=pitch,
                    direction=template.direction,
                    prefixes=prefixes,
                )
            ) <= residual_limit
        )

    for _iteration in range(4):
        updated_matches = _match_roles(
            direct,
            index.roles,
            separator_pairs,
            phase=phase,
            width=width,
            pitch=pitch,
            direction=template.direction,
            prefixes=prefixes,
            frame_width=template.frame_width_px,
            fit_residual_limit_px=fit_residual_limit_px,
            required_bindings=seed.required_bindings,
            adjacency_relations=relations,
            matching_index=index,
        )
        if phase_anchor_authority_ceiling is not None:
            updated_matches = tuple(
                (role, anchor)
                for role, anchor in updated_matches
                if (role.role_index, anchor.observation_id)
                in phase_anchor_authority_ceiling
            )
        if not updated_matches or not retains_seed_identity(updated_matches):
            return None
        # Realizing relations changes their positions, not their fit coefficients.
        # The same direct rows therefore already have their final bounded fit.
        if updated_matches == matches:
            break
        updated = _linear_fit(
            updated_matches,
            width=width,
            pitch=pitch,
            direction=template.direction,
            relations=relations,
            width_authority=template.frame_width_px,
            pitch_authority=pitch_authority,
            gap_authority=template.gap_prior_px,
            phase_authority=phase_authority,
        )
        updated_phase, updated_width, updated_pitch, updated_basis = updated
        fit_basis = most_constrained_lattice_parameter_fit_basis(
            fit_basis,
            updated_basis,
        )
        matches = updated_matches
        phase, width, pitch = updated_phase, updated_width, updated_pitch
        relations = realize_adjacency_relations(
            relations,
            frame_width_interval_px=template.frame_width_px,
            pitch_interval_px=pitch_authority,
            frame_width_px=width,
            pitch_px=pitch,
        )
        prefixes = adjacency_prefix_positions(relations, template.count)
    # Refitting a retained subset can expose another outlier. Close that
    # subset monotonically. Each refit deletes at least one optional binding;
    # at most R - 1 subset solves follow the four matching solves. If optional
    # matches would erase the required identity, its original bounded model
    # gets one independent check before deleting incompatible optional rows.
    # No role rematch, new seed, native coordinate, or authority is introduced.
    seed_identity_replayed = False
    for _trim_iteration in range(len(matches)):
        retained = compatible_subset()
        if retained == matches:
            break
        if not retained or not retains_seed_identity(retained):
            if seed_identity_replayed or not required:
                return None
            defining_matches = tuple(
                (role, anchor)
                for role, anchor in matches
                if (role.role_index, anchor.observation_id) in required
            )
            phase, width, pitch, fit_basis = _linear_fit(
                defining_matches,
                width=seed_width,
                pitch=seed.pitch_px,
                direction=template.direction,
                relations=relations,
                width_authority=template.frame_width_px,
                pitch_authority=pitch_authority,
                gap_authority=template.gap_prior_px,
                phase_authority=phase_authority,
            )
            relations = realize_adjacency_relations(
                relations,
                frame_width_interval_px=template.frame_width_px,
                pitch_interval_px=pitch_authority,
                frame_width_px=width,
                pitch_px=pitch,
            )
            prefixes = adjacency_prefix_positions(relations, template.count)
            retained = compatible_subset()
            if (
                retained == matches
                or not retained
                or not retains_seed_identity(retained)
            ):
                return None
            seed_identity_replayed = True
        phase, width, pitch, retained_basis = _linear_fit(
            retained,
            width=width,
            pitch=pitch,
            direction=template.direction,
            relations=relations,
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
        relations = realize_adjacency_relations(
            relations,
            frame_width_interval_px=template.frame_width_px,
            pitch_interval_px=pitch_authority,
            frame_width_px=width,
            pitch_px=pitch,
        )
        prefixes = adjacency_prefix_positions(relations, template.count)
    if not matches:
        return None
    if not template.gap_prior_px.contains(pitch - width):
        return None
    canonical_positions = tuple(
        template_role_position(
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
    direct_by_id = index.direct_by_id
    local_relation_by_role: dict[int, _candidate_model._AnchorFact] = {}
    global_role_by_observation = {
        anchor.observation_id: role.role_index for role, anchor in matches
    }
    for relation in relations:
        if not (
            isinstance(relation, SeparatorRelation)
            and relation.kind != SeparatorRelationKind.NOMINAL
        ):
            continue
        required = (
            (
                2 * relation.relation_ordinal - 1,
                relation.end_edge_observation_id,
            ),
            (
                2 * relation.relation_ordinal,
                relation.next_start_edge_observation_id,
            ),
        )
        for role_index, observation_id in required:
            assert observation_id is not None
            global_anchor = by_role.get(role_index)
            if global_anchor is not None:
                if global_anchor.observation_id != observation_id:
                    return None
                continue
            anchor = direct_by_id.get(observation_id)
            role = roles[role_index]
            if (
                anchor is None
                or observation_id in global_role_by_observation
                or anchor.qualified_anchor_roles
                and role.role not in anchor.qualified_anchor_roles
                or abs(
                    anchor.coordinate_px
                    - canonical_positions[role_index]
                )
                > template_role_refinement_radius_px(pitch)
            ):
                return None
            current = local_relation_by_role.get(role_index)
            if current is not None and current.observation_id != observation_id:
                return None
            if any(
                item.observation_id == observation_id
                and other_role != role_index
                for other_role, item in local_relation_by_role.items()
            ):
                return None
            local_relation_by_role[role_index] = anchor
    residuals = tuple(
        abs(anchor.coordinate_px - canonical_positions[role.role_index])
        for role, anchor in matches
    )
    residual_sum = sum(residuals)
    residual_mean = residual_sum / len(residuals)
    # One role's residual belongs to that role.  Smearing the largest residual
    # over every boundary turns one local observation into source-wide
    # uncertainty and can exceed the direct-use budget even when the template
    # placement is unique.  The global phase interval below carries the common
    # fit uncertainty; every directly bound role keeps only its own observed
    # interval plus its fitted coordinate.  Missing roles propagate the full
    # continuous template authority: pitch uncertainty grows with the slot
    # ordinal and a directly authorized adjacency relation changes the suffix
    # once.
    uncertainty = max(1.0, min(width * 0.04, residual_mean + 1.0))
    phase_interval = FiniteInterval(phase - uncertainty, phase + uncertainty)
    prefix_intervals = adjacency_prefix_intervals(relations, template.count)
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
        binding_use = SequenceBindingUse.PHASE_ANCHOR
        if observed is None:
            observed = local_relation_by_role.get(role.role_index)
            binding_use = SequenceBindingUse.LOCAL_REFINEMENT
        if observed is None:
            inferred_interval = template_role_interval(
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
                    use=binding_use,
                    observation_id=observed.observation_id,
                    evidence_group_id=observed.evidence_group_id,
                    canonical_position_px=observed.coordinate_px,
                    fit_position_interval_px=observed.interval_px,
                    full_position_interval_px=observed.full_interval_px,
                    line_evidence=observed.line_evidence,
                )
            )
    bound_direct_ids = tuple(
        dict.fromkeys(
            binding.observation_id
            for binding in role_bindings
            if binding is not None
        )
    )
    phase_direct_ids = tuple(
        dict.fromkeys(anchor.observation_id for _role, anchor in matches)
    )
    support_groups: dict[int, list[tuple[TemplateRole, _candidate_model._AnchorFact]]] = {}
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
    relations = realize_adjacency_relations_at_role_positions(
        relations,
        model_role_positions_px=canonical_positions,
        direction=template.direction,
        frame_width_px=width,
        pitch_px=pitch,
    )
    fit = SequenceFit(
        template=template,
        phase_lattice_fit=lattice_fit,
        pitch_fit=PitchFit(
            frame_width_px=template.frame_width_px,
            gap_interval_px=template.gap_prior_px,
            pitch_interval_px=measured_pitch,
            canonical_frame_width_px=width,
            canonical_pitch_px=pitch,
            observation_ids=phase_direct_ids,
        ),
        lattice_parameter_fit_basis=fit_basis,
        model_role_positions_px=canonical_positions,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(role_full_intervals),
        role_bindings=tuple(role_bindings),
        adjacency_relations=relations,
        contradicted_observation_count=max(
            0,
            len(direct) - len(bound_direct_ids),
        ),
        residual_sum_px=residual_sum,
        phase_support_coverage=phase_support_coverage,
    )
    return _candidate_model._BoundFit(fit, _candidate_model._phase_residual_compatible(fit))
