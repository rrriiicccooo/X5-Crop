from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...domain import FiniteInterval, PositiveInterval
from .model import (
    BoundaryAxis,
    BoundaryRole,
    BoundarySource,
    FrameBoundaryGeometry,
    PhotoBoundaryObservation,
    PhotoSequenceTranslationAssessment,
    PhotoSequenceTranslationOutcome,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SourceCoordinateLine,
)
from .selection import (
    ObservedAperturePair,
    indexed_observed_aperture_pairs,
    line_coordinate_at_trace,
    line_coordinate_interval_at_trace,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _add(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def _subtract(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


@dataclass(frozen=True)
class SequenceBoundaryRole:
    role_index: int
    lane_ordinal: int
    role: BoundaryRole
    relative_interval_px: FiniteInterval


@dataclass(frozen=True)
class ObservedRoleAssignment:
    role: SequenceBoundaryRole
    observation: PhotoBoundaryObservation
    position_interval_px: FiniteInterval
    translation_interval_px: FiniteInterval
    scalar_residual_px: float


@dataclass(frozen=True)
class LongAxisSequenceHypothesis:
    hypothesis_id: str
    translation_interval_px: FiniteInterval
    roles: tuple[SequenceBoundaryRole, ...]
    position_intervals_px: tuple[FiniteInterval, ...]
    observations_by_role: tuple[
        PhotoBoundaryObservation | None, ...
    ]
    assignment_ids: tuple[str, ...]
    observed_role_count: int
    role_oriented_observed_role_count: int
    observed_frame_count: int
    observed_aperture_pair_count: int
    scalar_residual_px: float
    physical_uncertainty_px: float
    shared_scale_interval_px_per_mm: PositiveInterval
    background_side_support_fraction: float
    role_oriented_background_support_fraction: float
    known_content_contained: bool
    lane_geometry_contained: bool

    def __post_init__(self) -> None:
        size = len(self.roles)
        if (
            not self.hypothesis_id
            or size == 0
            or len(self.position_intervals_px) != size
            or len(self.observations_by_role) != size
            or self.observed_role_count
            != sum(item is not None for item in self.observations_by_role)
            or not 0
            <= self.role_oriented_observed_role_count
            <= self.observed_role_count
            or self.observed_frame_count < 0
            or not 0
            <= self.observed_aperture_pair_count
            <= self.observed_frame_count
            or not math.isfinite(self.scalar_residual_px)
            or self.scalar_residual_px < 0.0
            or not math.isfinite(self.physical_uncertainty_px)
            or self.physical_uncertainty_px < 0.0
            or not isinstance(
                self.shared_scale_interval_px_per_mm,
                PositiveInterval,
            )
            or not 0.0
            <= self.background_side_support_fraction
            <= 1.0
            or not 0.0
            <= self.role_oriented_background_support_fraction
            <= 1.0
            or not isinstance(self.known_content_contained, bool)
            or not isinstance(self.lane_geometry_contained, bool)
        ):
            raise ValueError("long-axis sequence hypothesis is invalid")


@dataclass(frozen=True)
class _ObservedChainState:
    path: tuple[ObservedRoleAssignment, ...]
    translation_interval_px: FiniteInterval
    shared_scale_interval_px_per_mm: PositiveInterval
    observed_width_centers_px: tuple[float, ...]
    observed_gutter_centers_px: tuple[float, ...]


@dataclass(frozen=True)
class _TypedObservedChainState:
    path: tuple[ObservedRoleAssignment, ...]
    translation_interval_px: FiniteInterval
    shared_scale_interval_px_per_mm: PositiveInterval
    observed_frame_mask: int
    preference_sum: float
    weighted_support_sum: float
    physical_interval_residual_sum: float
    residual_sum: float
    uncertainty_sum: float
    identity_key: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class _AutoObservedPairChainState:
    last_pair: ObservedAperturePair
    pair_count: int
    shared_scale_interval_px_per_mm: PositiveInterval
    directional_preference_sum: float
    weighted_support_sum: float
    residual_sum: float
    uncertainty_sum: float
    identity_key: tuple[str, ...]


def _auto_pair_chain_rank(
    state: _AutoObservedPairChainState,
) -> tuple[
    int,
    float,
    float,
    float,
    float,
    tuple[str, ...],
]:
    count = max(1, state.pair_count)
    return (
        state.pair_count,
        state.directional_preference_sum / count,
        state.weighted_support_sum / count,
        -state.residual_sum / count,
        -state.uncertainty_sum / count,
        tuple(reversed(state.identity_key)),
    )


def auto_observed_photo_sequence_length(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    maximum_output_slot_count: int,
    aperture_width_px: PositiveInterval,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
) -> int:
    """Return the bounded length of the observed contiguous photo chain.

    Partial ``auto`` owns a fixed output capacity, not an authoritative photo
    count.  This local interval DP therefore derives only the number of
    physically connected *observed aperture pairs*.  It never changes output
    capacity, consumes Grid phase, or enumerates slot occupancy.
    """

    if maximum_output_slot_count <= 0:
        raise ValueError("auto photo-chain capacity must be positive")
    directional_minimum = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .directional_role_preference_minimum
    )
    pairs = tuple(
        pair
        for pair in indexed_observed_aperture_pairs(
            observations,
            boundary_axis=boundary_axis,
            reference_trace_px=reference_trace_px,
            aperture_width_px=aperture_width_px,
        )
        if (
            pair.start.left_background_preference_fraction
            >= directional_minimum
            and pair.end.right_background_preference_fraction
            >= directional_minimum
        )
    )
    if not pairs:
        return 0

    ordered_pairs = tuple(
        sorted(
            pairs,
            key=lambda item: (
                item.start_position_px.center,
                item.end_position_px.center,
                item.pair_id,
            ),
        )
    )
    states: list[_AutoObservedPairChainState] = []
    for pair in ordered_pairs:
        scale_minimum = max(
            shared_scale_px_per_mm.minimum,
            max(0.0, pair.width_interval_px.minimum)
            / aperture_width_mm.maximum,
        )
        scale_maximum = min(
            shared_scale_px_per_mm.maximum,
            pair.width_interval_px.maximum
            / aperture_width_mm.minimum,
        )
        if scale_maximum < scale_minimum:
            continue
        pair_scale = PositiveInterval(scale_minimum, scale_maximum)
        start_preference = (
            pair.start.left_background_preference_fraction
        )
        end_preference = pair.end.right_background_preference_fraction
        pair_preference = min(start_preference, end_preference)
        pair_support = (
            pair.start.trace_support_count
            * pair.start.continuous_support_fraction
            + pair.end.trace_support_count
            * pair.end.continuous_support_fraction
        )
        pair_uncertainty = (
            pair.start.measurement_uncertainty_px
            + pair.end.measurement_uncertainty_px
        )
        best = _AutoObservedPairChainState(
            last_pair=pair,
            pair_count=1,
            shared_scale_interval_px_per_mm=pair_scale,
            directional_preference_sum=pair_preference,
            weighted_support_sum=pair_support,
            residual_sum=(
                pair.physical_residual_px
                + pair.start.fit_residual_px
                + pair.end.fit_residual_px
            ),
            uncertainty_sum=pair_uncertainty,
            identity_key=(pair.pair_id,),
        )
        for previous in states:
            if previous.pair_count >= maximum_output_slot_count:
                continue
            previous_pair = previous.last_pair
            if (
                pair.start_position_px.center
                <= previous_pair.end_position_px.center
            ):
                continue
            gap = FiniteInterval(
                pair.start_position_px.minimum
                - previous_pair.end_position_px.maximum,
                pair.start_position_px.maximum
                - previous_pair.end_position_px.minimum,
            )
            if _intersection(gap, gutter_px) is None:
                continue
            shared_scale_minimum = max(
                previous.shared_scale_interval_px_per_mm.minimum,
                pair_scale.minimum,
            )
            shared_scale_maximum = min(
                previous.shared_scale_interval_px_per_mm.maximum,
                pair_scale.maximum,
            )
            if shared_scale_maximum < shared_scale_minimum:
                continue
            candidate = _AutoObservedPairChainState(
                last_pair=pair,
                pair_count=previous.pair_count + 1,
                shared_scale_interval_px_per_mm=PositiveInterval(
                    shared_scale_minimum,
                    shared_scale_maximum,
                ),
                directional_preference_sum=(
                    previous.directional_preference_sum
                    + pair_preference
                ),
                weighted_support_sum=(
                    previous.weighted_support_sum + pair_support
                ),
                residual_sum=(
                    previous.residual_sum
                    + pair.physical_residual_px
                    + pair.start.fit_residual_px
                    + pair.end.fit_residual_px
                ),
                uncertainty_sum=(
                    previous.uncertainty_sum + pair_uncertainty
                ),
                identity_key=(*previous.identity_key, pair.pair_id),
            )
            if _auto_pair_chain_rank(candidate) > _auto_pair_chain_rank(best):
                best = candidate
        states.append(best)

    if not states:
        return 0
    return min(
        maximum_output_slot_count,
        max(state.pair_count for state in states),
    )


def auto_observed_aperture_chain(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    maximum_output_slot_count: int,
    aperture_width_px: PositiveInterval,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
) -> tuple[ObservedAperturePair, ...]:
    """Select one deterministic local aperture pair per physical photo region."""

    if maximum_output_slot_count <= 0:
        raise ValueError("auto aperture-chain capacity must be positive")
    directional_minimum = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .directional_role_preference_minimum
    )
    pairs = tuple(
        pair
        for pair in indexed_observed_aperture_pairs(
            observations,
            boundary_axis=boundary_axis,
            reference_trace_px=reference_trace_px,
            aperture_width_px=aperture_width_px,
        )
        if (
            pair.start.left_background_preference_fraction
            >= directional_minimum
            and pair.end.right_background_preference_fraction
            >= directional_minimum
        )
    )
    del aperture_width_mm
    if not pairs:
        return ()

    def pair_rank(
        pair: ObservedAperturePair,
    ) -> tuple[float, float, float, float, float, str]:
        return (
            -pair.physical_residual_px,
            min(
                pair.start.left_background_preference_fraction,
                pair.end.right_background_preference_fraction,
            ),
            min(
                pair.start.continuous_support_fraction,
                pair.end.continuous_support_fraction,
            ),
            float(
                pair.start.trace_support_count
                + pair.end.trace_support_count
            ),
            -(
                pair.start.measurement_uncertainty_px
                + pair.end.measurement_uncertainty_px
            ),
            pair.pair_id,
        )

    midpoint_pairs = tuple(
        sorted(
            (
                (
                    (
                        pair.start_position_px.center
                        + pair.end_position_px.center
                    )
                    / 2.0,
                    pair,
                )
                for pair in pairs
            ),
            key=lambda item: (item[0], item[1].pair_id),
        )
    )
    cluster_radius = 0.35 * aperture_width_px.minimum
    clusters: list[list[tuple[float, ObservedAperturePair]]] = []
    for midpoint, pair in midpoint_pairs:
        if (
            not clusters
            or midpoint - clusters[-1][0][0] > cluster_radius
        ):
            clusters.append([(midpoint, pair)])
        else:
            clusters[-1].append((midpoint, pair))
    representatives = tuple(
        max(
            (pair for _midpoint, pair in cluster),
            key=pair_rank,
        )
        for cluster in clusters
    )

    ordered = tuple(
        sorted(
            representatives,
            key=lambda pair: (
                pair.start_position_px.center,
                pair.end_position_px.center,
                pair.pair_id,
            ),
        )
    )
    retained: list[ObservedAperturePair] = []
    for pair in ordered:
        if retained:
            previous = retained[-1]
            gap = FiniteInterval(
                pair.start_position_px.minimum
                - previous.end_position_px.maximum,
                pair.start_position_px.maximum
                - previous.end_position_px.minimum,
            )
            observed_contact_floor = min(
                gutter_px.minimum,
                -(
                    PHOTO_BOUNDARY_MEASUREMENT_SPEC
                    .maximum_transition_interval_mm
                    * shared_scale_px_per_mm.maximum
                ),
            )
            if gap.maximum < observed_contact_floor:
                if pair_rank(pair) > pair_rank(previous):
                    retained[-1] = pair
                continue
        retained.append(pair)
    if len(retained) <= maximum_output_slot_count:
        return tuple(retained)
    return tuple(
        sorted(
            sorted(
                retained,
                key=pair_rank,
                reverse=True,
            )[:maximum_output_slot_count],
            key=lambda pair: (
                pair.start_position_px.center,
                pair.end_position_px.center,
                pair.pair_id,
            ),
        )
    )


def sequence_boundary_roles(
    authoritative_sequence_length: int,
    aperture_width_px: PositiveInterval,
    gutter_px: FiniteInterval,
) -> tuple[SequenceBoundaryRole, ...]:
    if authoritative_sequence_length <= 0:
        raise ValueError("sequence roles require positive length")
    roles: list[SequenceBoundaryRole] = []
    start = FiniteInterval.exact(0.0)
    for ordinal in range(1, authoritative_sequence_length + 1):
        end = _add(
            start,
            FiniteInterval(
                aperture_width_px.minimum,
                aperture_width_px.maximum,
            ),
        )
        roles.extend(
            (
                SequenceBoundaryRole(
                    role_index=len(roles),
                    lane_ordinal=ordinal,
                    role=BoundaryRole.START,
                    relative_interval_px=start,
                ),
                SequenceBoundaryRole(
                    role_index=len(roles) + 1,
                    lane_ordinal=ordinal,
                    role=BoundaryRole.END,
                    relative_interval_px=end,
                ),
            )
        )
        start = _add(end, gutter_px)
    return tuple(roles)


def _anchor_assignments(
    observations: tuple[PhotoBoundaryObservation, ...],
    roles: tuple[SequenceBoundaryRole, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    lane_long_extent_px: int,
    known_content_interval_px: FiniteInterval | None,
) -> tuple[ObservedRoleAssignment, ...]:
    assignments: list[ObservedRoleAssignment] = []
    last_relative = roles[-1].relative_interval_px
    maximum_translation = (
        float(lane_long_extent_px) - last_relative.minimum
    )
    if maximum_translation < 0.0:
        return ()
    global_translation = FiniteInterval(0.0, maximum_translation)
    # Content participates in containment and ownership after observation
    # formation.  It cannot shrink the complete pixel anchor discovery domain.
    del known_content_interval_px
    for observation in observations:
        position = line_coordinate_interval_at_trace(
            observation,
            boundary_axis=boundary_axis,
            trace_coordinate_px=reference_trace_px,
        )
        for role in roles:
            translation = _subtract(
                position,
                role.relative_interval_px,
            )
            bounded = _intersection(
                translation,
                global_translation,
            )
            if bounded is None:
                continue
            assignments.append(
                ObservedRoleAssignment(
                    role=role,
                    observation=observation,
                    position_interval_px=position,
                    translation_interval_px=bounded,
                    scalar_residual_px=abs(
                        position.center
                        - (
                            bounded.center
                            + role.relative_interval_px.center
                        )
                    ),
                )
            )
    return tuple(assignments)


def _dispersion(values: tuple[float, ...]) -> float:
    if len(values) <= 1:
        return 0.0
    median = float(np.median(np.asarray(values, dtype=np.float64)))
    return sum(abs(value - median) for value in values)


def _observed_chain_rank(
    state: _ObservedChainState,
) -> tuple[
    float,
    float,
    float,
    float,
    float,
    tuple[tuple[int, str], ...],
]:
    return (
        _dispersion(state.observed_width_centers_px),
        _dispersion(state.observed_gutter_centers_px),
        sum(item.scalar_residual_px for item in state.path),
        sum(
            item.observation.fit_residual_px
            + item.observation.measurement_uncertainty_px
            for item in state.path
        ),
        -sum(
            float(item.observation.trace_support_count)
            for item in state.path
        ),
        tuple(
            (
                item.role.role_index,
                str(item.observation.observation_id),
            )
            for item in state.path
        ),
    )


def _interval_contains(
    outer: FiniteInterval | PositiveInterval,
    inner: FiniteInterval | PositiveInterval,
) -> bool:
    return (
        outer.minimum <= inner.minimum + 1.0e-8
        and outer.maximum + 1.0e-8 >= inner.maximum
    )


def _retain_observed_chain_state(
    states: list[_ObservedChainState],
    candidate: _ObservedChainState,
) -> None:
    """Keep complete interval classes; discard only strict dominance."""

    candidate_rank = _observed_chain_rank(candidate)[:-1]
    for existing in states:
        if (
            _interval_contains(
                existing.translation_interval_px,
                candidate.translation_interval_px,
            )
            and _interval_contains(
                existing.shared_scale_interval_px_per_mm,
                candidate.shared_scale_interval_px_per_mm,
            )
            and _observed_chain_rank(existing)[:-1] <= candidate_rank
        ):
            return
    states[:] = [
        existing
        for existing in states
        if not (
            _interval_contains(
                candidate.translation_interval_px,
                existing.translation_interval_px,
            )
            and _interval_contains(
                candidate.shared_scale_interval_px_per_mm,
                existing.shared_scale_interval_px_per_mm,
            )
            and candidate_rank < _observed_chain_rank(existing)[:-1]
        )
    ]
    states.append(candidate)


def _full_observed_chain_paths(
    roles: tuple[SequenceBoundaryRole, ...],
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    translation_probe_px: float,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
) -> tuple[tuple[ObservedRoleAssignment, ...], ...]:
    """Join every compatible observed role as an interval-constrained chain.

    This is the primary full-observation DP.  It performs no score-based
    top-N truncation: states disappear only when another state has a wider
    feasible translation/scale interval and is no worse on every frozen
    sequence measurement criterion.
    """

    by_role: dict[int, tuple[ObservedRoleAssignment, ...]] = {}
    for role in roles:
        by_role[role.role_index] = tuple(
            sorted(
                (
                    assignment
                    for assignment in assignments
                    if (
                        assignment.role.role_index == role.role_index
                        and assignment.translation_interval_px.contains(
                            translation_probe_px,
                            epsilon=1.0e-8,
                        )
                    )
                ),
                key=lambda item: (
                    item.position_interval_px.center,
                    str(item.observation.observation_id),
                ),
            )
        )
    if any(not by_role[role.role_index] for role in roles):
        return ()

    states_by_observation: dict[str, list[_ObservedChainState]] = {}
    for assignment in by_role[0]:
        state = _ObservedChainState(
            path=(assignment,),
            translation_interval_px=assignment.translation_interval_px,
            shared_scale_interval_px_per_mm=shared_scale_px_per_mm,
            observed_width_centers_px=(),
            observed_gutter_centers_px=(),
        )
        states_by_observation.setdefault(
            str(assignment.observation.observation_id),
            [],
        ).append(state)

    for role_index in range(1, len(roles)):
        next_states: dict[str, list[_ObservedChainState]] = {}
        for assignment in by_role[role_index]:
            assignment_id = str(
                assignment.observation.observation_id
            )
            retained = next_states.setdefault(assignment_id, [])
            for prior_states in states_by_observation.values():
                for state in prior_states:
                    previous = state.path[-1]
                    previous_id = str(
                        previous.observation.observation_id
                    )
                    if (
                        assignment.position_interval_px.center
                        < previous.position_interval_px.center
                    ):
                        continue
                    if (
                        assignment_id == previous_id
                        and not (
                            previous.role.role == BoundaryRole.END
                            and assignment.role.role
                            == BoundaryRole.START
                            and gutter_px.contains(0.0)
                        )
                    ):
                        continue
                    translation = _intersection(
                        state.translation_interval_px,
                        assignment.translation_interval_px,
                    )
                    if translation is None:
                        continue
                    scale_minimum = (
                        state.shared_scale_interval_px_per_mm.minimum
                    )
                    scale_maximum = (
                        state.shared_scale_interval_px_per_mm.maximum
                    )
                    widths = state.observed_width_centers_px
                    gutters = state.observed_gutter_centers_px
                    if assignment.role.role == BoundaryRole.END:
                        width_interval = FiniteInterval(
                            assignment.position_interval_px.minimum
                            - previous.position_interval_px.maximum,
                            assignment.position_interval_px.maximum
                            - previous.position_interval_px.minimum,
                        )
                        if width_interval.maximum <= 0.0:
                            continue
                        scale_minimum = max(
                            scale_minimum,
                            max(0.0, width_interval.minimum)
                            / aperture_width_mm.maximum,
                        )
                        scale_maximum = min(
                            scale_maximum,
                            width_interval.maximum
                            / aperture_width_mm.minimum,
                        )
                        if scale_maximum < scale_minimum:
                            continue
                        widths = (
                            *widths,
                            assignment.position_interval_px.center
                            - previous.position_interval_px.center,
                        )
                    else:
                        gutter_interval = FiniteInterval(
                            assignment.position_interval_px.minimum
                            - previous.position_interval_px.maximum,
                            assignment.position_interval_px.maximum
                            - previous.position_interval_px.minimum,
                        )
                        if _intersection(
                            gutter_interval,
                            gutter_px,
                        ) is None:
                            continue
                        gutters = (
                            *gutters,
                            assignment.position_interval_px.center
                            - previous.position_interval_px.center,
                        )
                    candidate = _ObservedChainState(
                        path=(*state.path, assignment),
                        translation_interval_px=translation,
                        shared_scale_interval_px_per_mm=PositiveInterval(
                            scale_minimum,
                            scale_maximum,
                        ),
                        observed_width_centers_px=widths,
                        observed_gutter_centers_px=gutters,
                    )
                    if (
                        _propagate_positions(
                            roles,
                            candidate.path,
                            PositiveInterval(
                                aperture_width_mm.minimum
                                * shared_scale_px_per_mm.minimum,
                                aperture_width_mm.maximum
                                * shared_scale_px_per_mm.maximum,
                            ),
                            gutter_px,
                            aperture_width_mm=aperture_width_mm,
                            shared_scale_px_per_mm=(
                                shared_scale_px_per_mm
                            ),
                        )
                        is None
                    ):
                        continue
                    _retain_observed_chain_state(retained, candidate)
        states_by_observation = next_states
        if not states_by_observation:
            return ()

    complete = tuple(
        state
        for states in states_by_observation.values()
        for state in states
    )
    if not complete:
        return ()
    best_rank = min(_observed_chain_rank(state) for state in complete)
    best_measurements = best_rank[:-1]
    return tuple(
        state.path
        for state in sorted(complete, key=_observed_chain_rank)
        if _observed_chain_rank(state)[:-1] == best_measurements
    )


def _ordered_assignment_dp(
    observations: tuple[PhotoBoundaryObservation, ...],
    roles: tuple[SequenceBoundaryRole, ...],
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    translation_probe_px: float,
    preferred_outer_assignment: tuple[str, int] | None = None,
) -> tuple[ObservedRoleAssignment, ...]:
    by_identity = {
        (
            str(item.observation.observation_id),
            item.role.role_index,
        ): item
        for item in assignments
        if item.translation_interval_px.contains(
            translation_probe_px,
            epsilon=1.0e-8,
        )
    }
    ordered_observations = tuple(
        sorted(
            observations,
            key=lambda item: (
                line_coordinate_at_trace(
                    item,
                    boundary_axis=boundary_axis,
                    trace_coordinate_px=reference_trace_px,
                ),
                str(item.observation_id),
            ),
        )
    )
    # score = observed count, evidence support, negative residual.
    empty_score = (0, 0.0, 0.0)
    scores = [
        [empty_score for _ in range(len(roles) + 1)]
        for _ in range(len(ordered_observations) + 1)
    ]
    paths: list[list[tuple[ObservedRoleAssignment, ...]]] = [
        [() for _ in range(len(roles) + 1)]
        for _ in range(len(ordered_observations) + 1)
    ]

    def better(
        left_score: tuple[int, float, float],
        left_path: tuple[ObservedRoleAssignment, ...],
        right_score: tuple[int, float, float],
        right_path: tuple[ObservedRoleAssignment, ...],
    ) -> tuple[
        tuple[int, float, float],
        tuple[ObservedRoleAssignment, ...],
    ]:
        if left_score != right_score:
            return (
                (left_score, left_path)
                if left_score > right_score
                else (right_score, right_path)
            )
        left_ids = tuple(
            (
                item.role.role_index,
                str(item.observation.observation_id),
            )
            for item in left_path
        )
        right_ids = tuple(
            (
                item.role.role_index,
                str(item.observation.observation_id),
            )
            for item in right_path
        )
        return (
            (left_score, left_path)
            if left_ids <= right_ids
            else (right_score, right_path)
        )

    for observation_index, observation in enumerate(
        ordered_observations,
        1,
    ):
        for role_index, role in enumerate(roles, 1):
            best_score, best_path = better(
                scores[observation_index - 1][role_index],
                paths[observation_index - 1][role_index],
                scores[observation_index][role_index - 1],
                paths[observation_index][role_index - 1],
            )
            assignment = by_identity.get(
                (str(observation.observation_id), role.role_index)
            )
            if assignment is not None:
                previous_score = scores[observation_index - 1][role_index - 1]
                candidate_score = (
                    previous_score[0]
                    + 1
                    + (
                        1_000
                        if preferred_outer_assignment
                        == (
                            str(observation.observation_id),
                            role.role_index,
                        )
                        else 0
                    ),
                    previous_score[1]
                    + float(observation.trace_support_count),
                    previous_score[2] - assignment.scalar_residual_px,
                )
                candidate_path = (
                    *paths[observation_index - 1][role_index - 1],
                    assignment,
                )
                best_score, best_path = better(
                    best_score,
                    best_path,
                    candidate_score,
                    candidate_path,
                )
            scores[observation_index][role_index] = best_score
            paths[observation_index][role_index] = best_path
    return paths[-1][-1]


def _ordered_assignment_dp_paths(
    observations: tuple[PhotoBoundaryObservation, ...],
    roles: tuple[SequenceBoundaryRole, ...],
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    translation_probe_px: float,
    preferred_outer_assignments: tuple[tuple[str, int], ...] = (),
    aperture_width_px: PositiveInterval,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
) -> tuple[tuple[ObservedRoleAssignment, ...], ...]:
    """Return one bounded, physically propagated ordered observation path.

    Raw measurement coverage remains complete in ``assignments``.  This join
    does not build the historical all-observation Cartesian chain: the typed
    interval DP separately evaluates one-sided and contact states, while this
    path contributes the deterministic ordered optimum for the same exact
    translation-membership class.
    """

    del preferred_outer_assignments
    partial = _ordered_assignment_dp(
        observations,
        roles,
        assignments,
        boundary_axis=boundary_axis,
        reference_trace_px=reference_trace_px,
        translation_probe_px=translation_probe_px,
    )
    if partial and _propagate_positions(
        roles,
        partial,
        aperture_width_px,
        gutter_px,
        aperture_width_mm=aperture_width_mm,
        shared_scale_px_per_mm=shared_scale_px_per_mm,
    ) is None:
        partial = ()

    def identity(
        path: tuple[ObservedRoleAssignment, ...],
    ) -> tuple[tuple[int, str], ...]:
        return tuple(
            (
                item.role.role_index,
                str(item.observation.observation_id),
            )
            for item in path
        )

    combined = {
        identity(path): path
        for path in ((partial,) if partial else ())
    }
    return tuple(combined[key] for key in sorted(combined))


def _role_oriented_preference(
    assignment: ObservedRoleAssignment,
) -> float:
    return (
        assignment.observation.left_background_preference_fraction
        if assignment.role.role == BoundaryRole.START
        else assignment.observation.right_background_preference_fraction
    )


def _best_directional_assignment_path(
    assignments: tuple[ObservedRoleAssignment, ...],
    roles: tuple[SequenceBoundaryRole, ...],
    *,
    translation_probe_px: float,
) -> tuple[ObservedRoleAssignment, ...]:
    """Build one typed edge-pair/one-sided path for a translation class.

    Missing roles deliberately remain absent and are propagated from the
    observed opposite edge, aperture interval, shared scale and typed gutter.
    A weak line is therefore not rewarded merely for turning an inferred edge
    into an observed one.
    """

    selected: list[ObservedRoleAssignment] = []
    used_observations: dict[str, SequenceBoundaryRole] = {}
    for role in roles:
        candidates = tuple(
            assignment
            for assignment in assignments
            if (
                assignment.role.role_index == role.role_index
                and assignment.translation_interval_px.contains(
                    translation_probe_px,
                    epsilon=1.0e-8,
                )
            )
        )
        if not candidates:
            continue
        for candidate in sorted(
            candidates,
            key=lambda item: (
                -_role_oriented_preference(item),
                -item.observation.trace_support_count,
                -item.observation.continuous_support_fraction,
                item.observation.measurement_uncertainty_px,
                item.observation.fit_residual_px,
                str(item.observation.observation_id),
            ),
        ):
            observation_id = str(candidate.observation.observation_id)
            previous_role = used_observations.get(observation_id)
            if previous_role is not None:
                contact_reuse = (
                    previous_role.role == BoundaryRole.END
                    and candidate.role.role == BoundaryRole.START
                    and candidate.role.lane_ordinal
                    == previous_role.lane_ordinal + 1
                )
                if not contact_reuse:
                    continue
            selected.append(candidate)
            used_observations[observation_id] = candidate.role
            break
    return tuple(selected)


def _typed_chain_rank(
    state: _TypedObservedChainState,
) -> tuple[
    int,
    int,
    float,
    float,
    float,
    float,
    float,
    tuple[tuple[int, str], ...],
]:
    count = max(1, len(state.path))
    return (
        state.observed_frame_mask.bit_count(),
        len(state.path),
        -state.physical_interval_residual_sum / count,
        state.preference_sum / count,
        state.weighted_support_sum / count,
        -state.residual_sum / count,
        -state.uncertainty_sum / count,
        state.identity_key,
    )


def _typed_interval_constrained_path(
    roles: tuple[SequenceBoundaryRole, ...],
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    translation_probe_px: float,
    aperture_width_px: PositiveInterval,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
    use_directional_preference: bool,
) -> tuple[ObservedRoleAssignment, ...]:
    """Select observed edge-pair/one-sided evidence inside the physical DP.

    Unlike the historical ordered matcher, every state is interval-propagated
    before it can survive.  Missing roles are ordinary one-sided inference
    states; adding a weak line cannot rescue a physically contradictory path.
    One best state is retained per last observed physical line because that
    identity is the only history needed by the next ordered join.
    """

    by_role = {
        role.role_index: tuple(
            assignment
            for assignment in assignments
            if (
                assignment.role.role_index == role.role_index
                and assignment.translation_interval_px.contains(
                    translation_probe_px,
                    epsilon=1.0e-8,
                )
            )
        )
        for role in roles
    }
    states: tuple[_TypedObservedChainState, ...] = (
        _TypedObservedChainState(
            path=(),
            translation_interval_px=FiniteInterval.exact(
                translation_probe_px
            ),
            shared_scale_interval_px_per_mm=shared_scale_px_per_mm,
            observed_frame_mask=0,
            preference_sum=0.0,
            weighted_support_sum=0.0,
            physical_interval_residual_sum=0.0,
            residual_sum=0.0,
            uncertainty_sum=0.0,
            identity_key=(),
        ),
    )
    for role in roles:
        next_by_last_identity: dict[
            str,
            _TypedObservedChainState,
        ] = {}

        def retain(candidate: _TypedObservedChainState) -> None:
            identity = (
                "__no_observed_line__"
                if not candidate.path
                else str(
                    candidate.path[-1].observation.observation_id
                )
            )
            existing = next_by_last_identity.get(identity)
            if (
                existing is None
                or _typed_chain_rank(candidate)
                > _typed_chain_rank(existing)
            ):
                next_by_last_identity[identity] = candidate

        for state in states:
            retain(state)
            previous = state.path[-1] if state.path else None
            for assignment in by_role[role.role_index]:
                if previous is not None:
                    previous_position = (
                        previous.position_interval_px.center
                    )
                    position = assignment.position_interval_px.center
                    if position < previous_position:
                        continue
                    same_observation = (
                        assignment.observation.observation_id
                        == previous.observation.observation_id
                    )
                    if same_observation and not (
                        previous.role.role == BoundaryRole.END
                        and assignment.role.role
                        == BoundaryRole.START
                        and assignment.role.lane_ordinal
                        == previous.role.lane_ordinal + 1
                        and gutter_px.contains(0.0)
                    ):
                        continue
                path = (*state.path, assignment)
                # ``by_role`` contains only assignments whose closed
                # translation interval contains this exact probe.  Every
                # surviving state starts from that same exact interval, so
                # re-intersecting it for every DP transition is redundant.
                translation = state.translation_interval_px
                scale = state.shared_scale_interval_px_per_mm
                physical_interval_residual = 0.0
                if (
                    previous is not None
                    and previous.role.role_index
                    == assignment.role.role_index - 1
                ):
                    separation_minimum = (
                        assignment.position_interval_px.minimum
                        - previous.position_interval_px.maximum
                    )
                    separation_maximum = (
                        assignment.position_interval_px.maximum
                        - previous.position_interval_px.minimum
                    )
                    separation_center = (
                        separation_minimum + separation_maximum
                    ) / 2.0
                    if assignment.role.role == BoundaryRole.END:
                        if separation_maximum <= 0.0:
                            continue
                        scale_minimum = max(
                            scale.minimum,
                            max(0.0, separation_minimum)
                            / aperture_width_mm.maximum,
                        )
                        scale_maximum = min(
                            scale.maximum,
                            separation_maximum
                            / aperture_width_mm.minimum,
                        )
                        if scale_maximum < scale_minimum:
                            continue
                        physical_interval_residual = max(
                            0.0,
                            aperture_width_px.minimum
                            - separation_center,
                            separation_center
                            - aperture_width_px.maximum,
                        )
                        scale = PositiveInterval(
                            scale_minimum,
                            scale_maximum,
                        )
                    else:
                        if (
                            separation_maximum < gutter_px.minimum
                            or gutter_px.maximum < separation_minimum
                        ):
                            continue
                        physical_interval_residual = max(
                            0.0,
                            gutter_px.minimum - separation_center,
                            separation_center - gutter_px.maximum,
                        )
                observation = assignment.observation
                observation_id = str(observation.observation_id)
                retain(
                    _TypedObservedChainState(
                        path=path,
                        translation_interval_px=translation,
                        shared_scale_interval_px_per_mm=scale,
                        observed_frame_mask=(
                            state.observed_frame_mask
                            | (1 << (assignment.role.lane_ordinal - 1))
                        ),
                        preference_sum=(
                            state.preference_sum
                            + (
                                _role_oriented_preference(assignment)
                                if use_directional_preference
                                else 0.0
                            )
                        ),
                        weighted_support_sum=(
                            state.weighted_support_sum
                            + observation.trace_support_count
                            * observation.continuous_support_fraction
                        ),
                        physical_interval_residual_sum=(
                            state.physical_interval_residual_sum
                            + physical_interval_residual
                        ),
                        residual_sum=(
                            state.residual_sum
                            + observation.fit_residual_px
                        ),
                        uncertainty_sum=(
                            state.uncertainty_sum
                            + observation.measurement_uncertainty_px
                        ),
                        identity_key=(
                            *state.identity_key,
                            (
                                assignment.role.role_index,
                                observation_id,
                            ),
                        ),
                    )
                )
        states = tuple(next_by_last_identity.values())
    observed = tuple(
        sorted(
            (state for state in states if state.path),
            key=_typed_chain_rank,
            reverse=True,
        )
    )
    if not observed:
        return ()
    for state in observed:
        if (
            _propagate_positions(
                roles,
                state.path,
                aperture_width_px,
                gutter_px,
                aperture_width_mm=aperture_width_mm,
                shared_scale_px_per_mm=shared_scale_px_per_mm,
            )
            is not None
        ):
            return state.path
    return ()


def _active_assignment_signature(
    assignments: tuple[ObservedRoleAssignment, ...],
    translation_probe_px: float,
) -> tuple[tuple[int, str], ...]:
    """Identify one exact probe-membership class.

    Every sequence solver below depends on a translation probe only through
    the assignments whose closed translation intervals contain that probe.
    Many registered anchor tiles produce the same membership class.  Keeping
    that identity explicit lets the caller reuse the physical DP result
    without dropping any measurement or probe coverage.
    """

    return tuple(
        (
            assignment.role.role_index,
            str(assignment.observation.observation_id),
        )
        for assignment in assignments
        if assignment.translation_interval_px.contains(
            translation_probe_px,
            epsilon=1.0e-8,
        )
    )


def _coverage_component_probes(
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    role_count: int,
    translation_bin_count: int,
) -> tuple[float, ...]:
    """Return one deterministic probe for every best-supported phase class."""

    if not assignments or translation_bin_count <= 0:
        return ()
    quality = np.zeros(
        (role_count, translation_bin_count),
        dtype=np.float32,
    )
    for assignment in assignments:
        lower = max(
            0,
            int(math.ceil(assignment.translation_interval_px.minimum)),
        )
        upper = min(
            translation_bin_count - 1,
            int(math.floor(assignment.translation_interval_px.maximum)),
        )
        if upper < lower:
            continue
        observation = assignment.observation
        value = (
            observation.trace_support_count
            * observation.continuous_support_fraction
            * (0.05 + _role_oriented_preference(assignment) ** 2)
            / (
                1.0
                + observation.fit_residual_px
                + observation.measurement_uncertainty_px
            )
        )
        target = quality[
            assignment.role.role_index,
            lower : upper + 1,
        ]
        np.maximum(target, value, out=target)
    coverage = np.count_nonzero(quality > 0.0, axis=0)
    maximum_coverage = int(coverage.max(initial=0))
    if maximum_coverage <= 0:
        return ()
    summed = np.sum(quality, axis=0)
    eligible = np.flatnonzero(coverage == maximum_coverage)
    probes: list[float] = []
    start = 0
    for index in range(1, eligible.size + 1):
        if (
            index < eligible.size
            and eligible[index] == eligible[index - 1] + 1
        ):
            continue
        component = eligible[start:index]
        probes.append(
            float(component[int(np.argmax(summed[component]))])
        )
        start = index
    return tuple(probes)


def _propagate_positions(
    roles: tuple[SequenceBoundaryRole, ...],
    assignments: tuple[ObservedRoleAssignment, ...],
    aperture_width_px: PositiveInterval,
    gutter_px: FiniteInterval,
    *,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
) -> tuple[FiniteInterval, tuple[FiniteInterval, ...]] | None:
    resolved_scale = _shared_scale_interval(
        assignments,
        aperture_width_mm=aperture_width_mm,
        scale_px_per_mm=shared_scale_px_per_mm,
    )
    if resolved_scale is None:
        return None
    if not assignments:
        return None
    translation_minimum = max(
        assignment.translation_interval_px.minimum
        for assignment in assignments
    )
    translation_maximum = min(
        assignment.translation_interval_px.maximum
        for assignment in assignments
    )
    if translation_maximum < translation_minimum:
        return None
    translation = FiniteInterval(
        translation_minimum,
        translation_maximum,
    )
    position_minima = [
        translation_minimum + role.relative_interval_px.minimum
        for role in roles
    ]
    position_maxima = [
        translation_maximum + role.relative_interval_px.maximum
        for role in roles
    ]
    for assignment in assignments:
        index = assignment.role.role_index
        position_minima[index] = max(
            position_minima[index],
            assignment.position_interval_px.minimum,
        )
        position_maxima[index] = min(
            position_maxima[index],
            assignment.position_interval_px.maximum,
        )
        if position_maxima[index] < position_minima[index]:
            return None
    width_minimum = max(
        aperture_width_px.minimum,
        aperture_width_mm.minimum * resolved_scale.minimum,
    )
    width_maximum = min(
        aperture_width_px.maximum,
        aperture_width_mm.maximum * resolved_scale.maximum,
    )
    for _ in range(len(roles) * 2 + 2):
        changed = False
        for index in range(0, len(roles), 2):
            narrowed_end_minimum = max(
                position_minima[index + 1],
                position_minima[index] + width_minimum,
            )
            narrowed_end_maximum = min(
                position_maxima[index + 1],
                position_maxima[index] + width_maximum,
            )
            if narrowed_end_maximum < narrowed_end_minimum:
                return None
            if (
                narrowed_end_minimum != position_minima[index + 1]
                or narrowed_end_maximum != position_maxima[index + 1]
            ):
                position_minima[index + 1] = narrowed_end_minimum
                position_maxima[index + 1] = narrowed_end_maximum
                changed = True
            narrowed_start_minimum = max(
                position_minima[index],
                position_minima[index + 1] - width_maximum,
            )
            narrowed_start_maximum = min(
                position_maxima[index],
                position_maxima[index + 1] - width_minimum,
            )
            if narrowed_start_maximum < narrowed_start_minimum:
                return None
            if (
                narrowed_start_minimum != position_minima[index]
                or narrowed_start_maximum != position_maxima[index]
            ):
                position_minima[index] = narrowed_start_minimum
                position_maxima[index] = narrowed_start_maximum
                changed = True
        for index in range(1, len(roles) - 1, 2):
            narrowed_start_minimum = max(
                position_minima[index + 1],
                position_minima[index] + gutter_px.minimum,
            )
            narrowed_start_maximum = min(
                position_maxima[index + 1],
                position_maxima[index] + gutter_px.maximum,
            )
            if narrowed_start_maximum < narrowed_start_minimum:
                return None
            if (
                narrowed_start_minimum != position_minima[index + 1]
                or narrowed_start_maximum != position_maxima[index + 1]
            ):
                position_minima[index + 1] = narrowed_start_minimum
                position_maxima[index + 1] = narrowed_start_maximum
                changed = True
            narrowed_end_minimum = max(
                position_minima[index],
                position_minima[index + 1] - gutter_px.maximum,
            )
            narrowed_end_maximum = min(
                position_maxima[index],
                position_maxima[index + 1] - gutter_px.minimum,
            )
            if narrowed_end_maximum < narrowed_end_minimum:
                return None
            if (
                narrowed_end_minimum != position_minima[index]
                or narrowed_end_maximum != position_maxima[index]
            ):
                position_minima[index] = narrowed_end_minimum
                position_maxima[index] = narrowed_end_maximum
                changed = True
        if not changed:
            break
    return translation, tuple(
        FiniteInterval(minimum, maximum)
        for minimum, maximum in zip(
            position_minima,
            position_maxima,
            strict=True,
        )
    )


def _shared_scale_interval(
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    aperture_width_mm: PositiveInterval,
    scale_px_per_mm: PositiveInterval,
) -> PositiveInterval | None:
    """Resolve the single scanner scale shared by every frame in a lane."""

    minimum = scale_px_per_mm.minimum
    maximum = scale_px_per_mm.maximum
    by_role = {
        item.role.role_index: item
        for item in assignments
    }
    for role_index in range(0, max(by_role, default=-1) + 1, 2):
        start = by_role.get(role_index)
        end = by_role.get(role_index + 1)
        if start is None or end is None:
            continue
        width_minimum = (
            end.position_interval_px.minimum
            - start.position_interval_px.maximum
        )
        width_maximum = (
            end.position_interval_px.maximum
            - start.position_interval_px.minimum
        )
        if width_minimum <= 0.0 or width_maximum <= 0.0:
            return None
        minimum = max(
            minimum,
            width_minimum / aperture_width_mm.maximum,
        )
        maximum = min(
            maximum,
            width_maximum / aperture_width_mm.minimum,
        )
        if maximum < minimum:
            return None
    return PositiveInterval(minimum, maximum)


def _fill_contact_reuse(
    assignments: tuple[ObservedRoleAssignment, ...],
    all_assignments: tuple[ObservedRoleAssignment, ...],
    translation: FiniteInterval,
    gutter_px: FiniteInterval,
) -> tuple[ObservedRoleAssignment, ...]:
    """One contact observation may support E_i and S_(i+1)."""

    if not gutter_px.contains(0.0):
        return assignments
    by_role = {item.role.role_index: item for item in assignments}
    by_observation = {
        str(item.observation.observation_id): item
        for item in assignments
    }
    for candidate in all_assignments:
        if candidate.role.role_index in by_role:
            continue
        if not _intersection(
            candidate.translation_interval_px,
            translation,
        ):
            continue
        existing = by_observation.get(
            str(candidate.observation.observation_id)
        )
        if existing is None:
            continue
        if (
            existing.role.role == BoundaryRole.END
            and candidate.role.role == BoundaryRole.START
            and candidate.role.lane_ordinal
            == existing.role.lane_ordinal + 1
        ) or (
            existing.role.role == BoundaryRole.START
            and candidate.role.role == BoundaryRole.END
            and existing.role.lane_ordinal
            == candidate.role.lane_ordinal + 1
        ):
            by_role[candidate.role.role_index] = candidate
    return tuple(by_role[index] for index in sorted(by_role))


def _path_physical_interval_residual(
    assignments: tuple[ObservedRoleAssignment, ...],
    *,
    aperture_width_px: PositiveInterval,
    gutter_px: FiniteInterval,
) -> float:
    by_role = {
        assignment.role.role_index: assignment
        for assignment in assignments
    }
    residuals: list[float] = []
    for role_index in range(0, max(by_role, default=-1) + 1):
        left = by_role.get(role_index)
        right = by_role.get(role_index + 1)
        if left is None or right is None:
            continue
        separation = (
            right.position_interval_px.center
            - left.position_interval_px.center
        )
        expected = (
            aperture_width_px
            if right.role.role == BoundaryRole.END
            else gutter_px
        )
        residuals.append(
            max(
                0.0,
                expected.minimum - separation,
                separation - expected.maximum,
            )
        )
    if not residuals:
        return 0.0
    return sum(residuals) / len(residuals)


def solve_long_axis_sequence_hypotheses(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    authoritative_sequence_length: int,
    aperture_width_px: PositiveInterval,
    aperture_width_mm: PositiveInterval,
    shared_scale_px_per_mm: PositiveInterval,
    gutter_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    lane_long_extent_px: int,
    expected_grid_translation_px: float | None = None,
    known_content_interval_px: FiniteInterval | None = None,
    preferred_outer_assignments: tuple[tuple[str, int], ...] = (),
    allow_blank_slots: bool = False,
) -> tuple[LongAxisSequenceHypothesis, ...]:
    """Resolve complete ordered sequence classes without a first-edge anchor."""

    roles = sequence_boundary_roles(
        authoritative_sequence_length,
        aperture_width_px,
        gutter_px,
    )
    assignments = _anchor_assignments(
        observations,
        roles,
        boundary_axis=boundary_axis,
        reference_trace_px=reference_trace_px,
        lane_long_extent_px=lane_long_extent_px,
        known_content_interval_px=known_content_interval_px,
    )
    if not assignments:
        return ()
    directional_assignments = tuple(
        assignment
        for assignment in assignments
        if (
            (
                assignment.observation
                .left_background_preference_fraction
                if assignment.role.role == BoundaryRole.START
                else assignment.observation
                .right_background_preference_fraction
            )
            >= PHOTO_BOUNDARY_MEASUREMENT_SPEC
            .directional_role_preference_minimum
        )
    )
    directional_observation_ids = {
        str(assignment.observation.observation_id)
        for assignment in directional_assignments
    }
    directional_observations = tuple(
        observation
        for observation in observations
        if str(observation.observation_id)
        in directional_observation_ids
    )
    # Translation proposals are bounded by the complete sequence, not by an
    # individual role.  Deduplicate probe locations at the source-geometry
    # equivalence scale before running the ordered K-state DP.
    equivalence_px = 1.0
    preferred_assignments = (
        tuple(
            item
            for item in assignments
            if (
                str(item.observation.observation_id),
                item.role.role_index,
            )
            in preferred_outer_assignments
        )
    )
    preferred_sparse_paths: list[
        tuple[ObservedRoleAssignment, ...]
    ] = [(item,) for item in preferred_assignments]
    preferred_leading = tuple(
        item
        for item in preferred_assignments
        if item.role.role_index == 0
    )
    preferred_trailing = tuple(
        item
        for item in preferred_assignments
        if item.role.role_index == len(roles) - 1
    )
    for leading in preferred_leading:
        for trailing in preferred_trailing:
            sparse = (leading, trailing)
            if (
                _propagate_positions(
                    roles,
                    sparse,
                    aperture_width_px,
                    gutter_px,
                    aperture_width_mm=aperture_width_mm,
                    shared_scale_px_per_mm=shared_scale_px_per_mm,
                )
                is not None
            ):
                preferred_sparse_paths.append(sparse)
    if allow_blank_slots:
        assignment_by_identity = {
            (
                str(item.observation.observation_id),
                item.role.role_index,
            ): item
            for item in assignments
        }
        directional_pairs = tuple(
            pair
            for pair in indexed_observed_aperture_pairs(
                observations,
                boundary_axis=boundary_axis,
                reference_trace_px=reference_trace_px,
                aperture_width_px=aperture_width_px,
            )
            if (
                pair.start.left_background_preference_fraction
                >= PHOTO_BOUNDARY_MEASUREMENT_SPEC
                .directional_role_preference_minimum
                and pair.end.right_background_preference_fraction
                >= PHOTO_BOUNDARY_MEASUREMENT_SPEC
                .directional_role_preference_minimum
            )
        )
        for pair in directional_pairs:
            mapped_paths: list[
                tuple[
                    float,
                    tuple[ObservedRoleAssignment, ...],
                ]
            ] = []
            for ordinal_index in range(authoritative_sequence_length):
                start = assignment_by_identity.get(
                    (
                        str(pair.start.observation_id),
                        ordinal_index * 2,
                    )
                )
                end = assignment_by_identity.get(
                    (
                        str(pair.end.observation_id),
                        ordinal_index * 2 + 1,
                    )
                )
                if start is None or end is None:
                    continue
                path = (start, end)
                propagated = _propagate_positions(
                    roles,
                    path,
                    aperture_width_px,
                    gutter_px,
                    aperture_width_mm=aperture_width_mm,
                    shared_scale_px_per_mm=shared_scale_px_per_mm,
                )
                if propagated is None:
                    continue
                distance = (
                    0.0
                    if expected_grid_translation_px is None
                    else abs(
                        propagated[0].center
                        - expected_grid_translation_px
                    )
                )
                mapped_paths.append((distance, path))
            if mapped_paths:
                minimum_distance = min(
                    item[0] for item in mapped_paths
                )
                preferred_sparse_paths.extend(
                    path
                    for distance, path in mapped_paths
                    if distance <= minimum_distance + equivalence_px
                )
        preferred_sparse_paths = list(
            {
                tuple(
                    (
                        item.role.role_index,
                        str(item.observation.observation_id),
                    )
                    for item in path
                ): path
                for path in preferred_sparse_paths
            }.values()
        )
    probes = {
        round(item.translation_interval_px.center / equivalence_px)
        * equivalence_px
        for item in preferred_assignments
    }
    for sparse in preferred_sparse_paths:
        sparse_propagation = _propagate_positions(
            roles,
            sparse,
            aperture_width_px,
            gutter_px,
            aperture_width_mm=aperture_width_mm,
            shared_scale_px_per_mm=shared_scale_px_per_mm,
        )
        if sparse_propagation is not None:
            # A narrow observed pair may define a sub-pixel translation
            # interval.  Its exact center must remain inside the registered
            # class; rounding may move the probe outside and silently discard
            # the only observed local anchor.
            probes.add(sparse_propagation[0].center)
    maximum_translation = max(
        item.translation_interval_px.maximum
        for item in assignments
    )
    translation_bin_count = int(math.floor(maximum_translation)) + 1
    probes.update(
        _coverage_component_probes(
            assignments,
            role_count=len(roles),
            translation_bin_count=translation_bin_count,
        )
    )
    probes.update(
        _coverage_component_probes(
            directional_assignments,
            role_count=len(roles),
            translation_bin_count=translation_bin_count,
        )
    )
    if expected_grid_translation_px is not None:
        probes.add(expected_grid_translation_px)
    primary_probes = set(probes)
    outer_role_indices = {0, len(roles) - 1}
    directional_greedy_probes = {
        round(
            item.translation_interval_px.center / equivalence_px
        )
        * equivalence_px
        for item in directional_assignments
        if item.role.role_index in outer_role_indices
    }
    for role in roles[1:-1]:
        role_assignments = tuple(
            item
            for item in directional_assignments
            if item.role.role_index == role.role_index
        )
        if not role_assignments:
            continue
        best = max(
            role_assignments,
            key=lambda item: (
                _role_oriented_preference(item),
                item.observation.trace_support_count,
                item.observation.continuous_support_fraction,
                -item.observation.measurement_uncertainty_px,
                -item.observation.fit_residual_px,
                str(item.observation.observation_id),
            ),
        )
        directional_greedy_probes.add(
            round(
                best.translation_interval_px.center / equivalence_px
            )
            * equivalence_px
        )
    hypotheses_by_assignment: dict[
        tuple[tuple[int, str], ...],
        LongAxisSequenceHypothesis,
    ] = {}
    general_path_cache: dict[
        tuple[tuple[int, str], ...],
        tuple[tuple[ObservedRoleAssignment, ...], ...],
    ] = {}
    directional_general_path_cache: dict[
        tuple[tuple[int, str], ...],
        tuple[tuple[ObservedRoleAssignment, ...], ...],
    ] = {}
    directional_typed_path_cache: dict[
        tuple[tuple[int, str], ...],
        tuple[ObservedRoleAssignment, ...],
    ] = {}
    general_typed_path_cache: dict[
        tuple[tuple[int, str], ...],
        tuple[ObservedRoleAssignment, ...],
    ] = {}
    for probe in sorted(primary_probes | directional_greedy_probes):
        general_typed_path: tuple[ObservedRoleAssignment, ...] = ()
        if probe in primary_probes:
            general_signature = _active_assignment_signature(
                assignments,
                probe,
            )
            general_primary = general_path_cache.get(general_signature)
            if general_primary is None:
                general_primary = _ordered_assignment_dp_paths(
                    observations,
                    roles,
                    assignments,
                    boundary_axis=boundary_axis,
                    reference_trace_px=reference_trace_px,
                    translation_probe_px=probe,
                    preferred_outer_assignments=(
                        preferred_outer_assignments
                    ),
                    aperture_width_px=aperture_width_px,
                    aperture_width_mm=aperture_width_mm,
                    shared_scale_px_per_mm=(
                        shared_scale_px_per_mm
                    ),
                    gutter_px=gutter_px,
                )
                general_path_cache[general_signature] = general_primary
            general_typed_path = general_typed_path_cache.get(
                general_signature,
                (),
            )
            if (
                not general_typed_path
                and general_signature
                not in general_typed_path_cache
            ):
                general_typed_path = _typed_interval_constrained_path(
                    roles,
                    assignments,
                    translation_probe_px=probe,
                    aperture_width_px=aperture_width_px,
                    aperture_width_mm=aperture_width_mm,
                    shared_scale_px_per_mm=shared_scale_px_per_mm,
                    gutter_px=gutter_px,
                    use_directional_preference=False,
                )
                general_typed_path_cache[
                    general_signature
                ] = general_typed_path
            directional_primary: tuple[
                tuple[ObservedRoleAssignment, ...], ...
            ] = ()
            if directional_assignments:
                directional_signature = _active_assignment_signature(
                    directional_assignments,
                    probe,
                )
                directional_primary = (
                    directional_general_path_cache.get(
                        directional_signature
                    )
                )
                if directional_primary is None:
                    directional_primary = _ordered_assignment_dp_paths(
                        directional_observations,
                        roles,
                        directional_assignments,
                        boundary_axis=boundary_axis,
                        reference_trace_px=reference_trace_px,
                        translation_probe_px=probe,
                        preferred_outer_assignments=(),
                        aperture_width_px=aperture_width_px,
                        aperture_width_mm=aperture_width_mm,
                        shared_scale_px_per_mm=(
                            shared_scale_px_per_mm
                        ),
                        gutter_px=gutter_px,
                    )
                    directional_general_path_cache[
                        directional_signature
                    ] = directional_primary
            general_paths = (
                *general_primary,
                *directional_primary,
                *(
                    path
                    for path in preferred_sparse_paths
                    if all(
                        item.translation_interval_px.contains(
                            probe,
                            epsilon=1.0e-8,
                        )
                        for item in path
                    )
                ),
            )
        else:
            general_paths = ()
        if directional_assignments:
            directional_signature = _active_assignment_signature(
                directional_assignments,
                probe,
            )
            directional_path = directional_typed_path_cache.get(
                directional_signature
            )
            if directional_path is None:
                directional_path = _typed_interval_constrained_path(
                    roles,
                    directional_assignments,
                    translation_probe_px=probe,
                    aperture_width_px=aperture_width_px,
                    aperture_width_mm=aperture_width_mm,
                    shared_scale_px_per_mm=shared_scale_px_per_mm,
                    gutter_px=gutter_px,
                    use_directional_preference=True,
                )
                directional_typed_path_cache[
                    directional_signature
                ] = directional_path
        else:
            directional_path = ()
        ordered_paths = tuple(
            {
                tuple(
                    (
                        item.role.role_index,
                        str(item.observation.observation_id),
                    )
                    for item in path
                ): path
                for path in (
                    *general_paths,
                    *(
                        (general_typed_path,)
                        if general_typed_path
                        else ()
                    ),
                    *((directional_path,) if directional_path else ()),
                )
            }.values()
        )
        for ordered in ordered_paths:
            if not ordered:
                continue
            propagated = _propagate_positions(
                roles,
                ordered,
                aperture_width_px,
                gutter_px,
                aperture_width_mm=aperture_width_mm,
                shared_scale_px_per_mm=shared_scale_px_per_mm,
            )
            if propagated is None:
                continue
            translation, positions = propagated
            contact_augmented = _fill_contact_reuse(
                ordered,
                assignments,
                translation,
                gutter_px,
            )
            augmented_propagation = _propagate_positions(
                roles,
                contact_augmented,
                aperture_width_px,
                gutter_px,
                aperture_width_mm=aperture_width_mm,
                shared_scale_px_per_mm=shared_scale_px_per_mm,
            )
            if augmented_propagation is not None:
                ordered = contact_augmented
                translation, positions = augmented_propagation
            observations_by_role: list[
                PhotoBoundaryObservation | None
            ] = [None] * len(roles)
            for assignment in ordered:
                observations_by_role[
                    assignment.role.role_index
                ] = assignment.observation
            assignment_key = tuple(
                (
                    assignment.role.role_index,
                    str(assignment.observation.observation_id),
                )
                for assignment in ordered
            )
            observed_frames = sum(
                any(
                    observations_by_role[index + offset] is not None
                    for offset in (0, 1)
                )
                for index in range(0, len(roles), 2)
            )
            observed_aperture_pairs = sum(
                observations_by_role[index] is not None
                and observations_by_role[index + 1] is not None
                for index in range(0, len(roles), 2)
            )
            # Design aperture and gutter intervals are feasibility contracts,
            # not point-valued pixel evidence.  Ranking by distance to their
            # midpoint would silently turn the format model into a fake edge
            # observation.  Once interval propagation accepts a path, only
            # the fitted pixel-line residual remains a measurement-quality
            # criterion.
            residual = (
                sum(
                    item.observation.fit_residual_px
                    for item in ordered
                )
                / len(ordered)
                + _path_physical_interval_residual(
                    ordered,
                    aperture_width_px=aperture_width_px,
                    gutter_px=gutter_px,
                )
            )
            uncertainty = sum(item.width for item in positions)
            resolved_scale = _shared_scale_interval(
                ordered,
                aperture_width_mm=aperture_width_mm,
                scale_px_per_mm=shared_scale_px_per_mm,
            )
            if resolved_scale is None:
                continue
            hypothesis = LongAxisSequenceHypothesis(
                hypothesis_id=_stable_id(
                    "long-sequence",
                    *(
                        f"{role_index}:{observation_id}"
                        for role_index, observation_id in assignment_key
                    ),
                ),
                translation_interval_px=translation,
                roles=roles,
                position_intervals_px=positions,
                observations_by_role=tuple(observations_by_role),
                assignment_ids=tuple(
                    f"{role_index}:{observation_id}"
                    for role_index, observation_id in assignment_key
                ),
                observed_role_count=len(ordered),
                role_oriented_observed_role_count=sum(
                    _role_oriented_preference(item)
                    >= PHOTO_BOUNDARY_MEASUREMENT_SPEC
                    .directional_role_preference_minimum
                    for item in ordered
                ),
                observed_frame_count=observed_frames,
                observed_aperture_pair_count=(
                    observed_aperture_pairs
                ),
                scalar_residual_px=residual,
                physical_uncertainty_px=uncertainty,
                shared_scale_interval_px_per_mm=resolved_scale,
                background_side_support_fraction=(
                    sum(
                        item.observation
                        .background_side_support_fraction
                        for item in ordered
                    )
                    / len(ordered)
                ),
                role_oriented_background_support_fraction=(
                    sum(
                        (
                            item.observation
                            .left_background_preference_fraction
                            if item.role.role == BoundaryRole.START
                            else item.observation
                            .right_background_preference_fraction
                        )
                        for item in ordered
                    )
                    / len(ordered)
                ),
                known_content_contained=(
                    True
                    if known_content_interval_px is None
                    else (
                        positions[0].minimum
                        <= known_content_interval_px.minimum
                        and positions[-1].maximum
                        >= known_content_interval_px.maximum
                    )
                ),
                lane_geometry_contained=(
                    positions[0].minimum >= 0.0
                    and positions[-1].maximum
                    <= float(lane_long_extent_px)
                ),
            )
            existing = hypotheses_by_assignment.get(assignment_key)
            if (
                existing is None
                or (
                    hypothesis.physical_uncertainty_px,
                    hypothesis.scalar_residual_px,
                    hypothesis.hypothesis_id,
                )
                < (
                    existing.physical_uncertainty_px,
                    existing.scalar_residual_px,
                    existing.hypothesis_id,
                )
            ):
                hypotheses_by_assignment[assignment_key] = hypothesis
    if not hypotheses_by_assignment:
        return ()
    hypotheses = tuple(hypotheses_by_assignment.values())
    hypotheses = tuple(
        item for item in hypotheses if item.lane_geometry_contained
    )
    if not hypotheses:
        return ()
    if not allow_blank_slots:
        maximum_observed_frames = max(
            item.observed_frame_count for item in hypotheses
        )
        hypotheses = tuple(
            item
            for item in hypotheses
            if item.observed_frame_count == maximum_observed_frames
        )
    return tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                -item.observed_aperture_pair_count,
                -item.role_oriented_observed_role_count,
                -(
                    item.background_side_support_fraction
                    * item.role_oriented_observed_role_count
                ),
                -(
                    item.role_oriented_background_support_fraction
                    * item.role_oriented_observed_role_count
                ),
                -item.observed_role_count,
                item.scalar_residual_px,
                item.physical_uncertainty_px,
                item.hypothesis_id,
            ),
        )
    )


def photo_translation_assessment(
    hypotheses: tuple[LongAxisSequenceHypothesis, ...],
) -> PhotoSequenceTranslationAssessment:
    if not hypotheses:
        return PhotoSequenceTranslationAssessment(
            outcome=PhotoSequenceTranslationOutcome.UNRESOLVED,
            interval_px=None,
            observation_ids=(),
            competing_class_ids=("sequence_translation_unresolved",),
        )
    classes = tuple(
        sorted(
            {
                (
                    round(item.translation_interval_px.minimum, 6),
                    round(item.translation_interval_px.maximum, 6),
                )
                for item in hypotheses
            }
        )
    )
    if len(classes) > 1:
        return PhotoSequenceTranslationAssessment(
            outcome=PhotoSequenceTranslationOutcome.UNRESOLVED,
            interval_px=None,
            observation_ids=(),
            competing_class_ids=tuple(
                f"translation:{minimum:.6f}:{maximum:.6f}"
                for minimum, maximum in classes
            ),
        )
    selected = hypotheses[0]
    observation_ids = tuple(
        sorted(
            {
                observation.observation_id
                for observation in selected.observations_by_role
                if observation is not None
            },
            key=str,
        )
    )
    return PhotoSequenceTranslationAssessment(
        outcome=PhotoSequenceTranslationOutcome.OBSERVED_ANCHOR,
        interval_px=selected.translation_interval_px,
        observation_ids=observation_ids,
        competing_class_ids=(),
    )


def _line_with_position_at_trace(
    template: SourceCoordinateLine,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
    position_px: float,
    support_projection_px: FiniteInterval,
) -> SourceCoordinateLine:
    if boundary_axis == BoundaryAxis.X:
        offset = (
            template.normal_x * position_px
            + template.normal_y * trace_coordinate_px
        )
    else:
        offset = (
            template.normal_x * trace_coordinate_px
            + template.normal_y * position_px
        )
    return SourceCoordinateLine(
        normal_x=template.normal_x,
        normal_y=template.normal_y,
        offset_px=offset,
        support_projection_px=support_projection_px,
        source_axis_long=template.source_axis_long,
    )


def frame_long_boundaries(
    hypothesis: LongAxisSequenceHypothesis,
    *,
    lane_ordinal: int,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
) -> tuple[FrameBoundaryGeometry, FrameBoundaryGeometry]:
    if lane_ordinal <= 0 or lane_ordinal * 2 > len(hypothesis.roles):
        raise ValueError("frame ordinal exceeds sequence hypothesis")
    start_index = (lane_ordinal - 1) * 2
    template = next(
        (
            observation.line
            for observation in hypothesis.observations_by_role
            if observation is not None
        ),
        None,
    )
    if template is None:
        raise ValueError("inferred sequence requires observed rotation authority")
    boundaries: list[FrameBoundaryGeometry] = []
    for role, index in (
        (BoundaryRole.START, start_index),
        (BoundaryRole.END, start_index + 1),
    ):
        observation = hypothesis.observations_by_role[index]
        position = hypothesis.position_intervals_px[index]
        if observation is not None:
            boundaries.append(
                FrameBoundaryGeometry(
                    role=role,
                    line=observation.line,
                    offset_interval_px=observation.offset_interval_px,
                    source=BoundarySource.OBSERVED,
                    observation_ids=(observation.observation_id,),
                    named_inference=None,
                )
            )
            continue
        line = _line_with_position_at_trace(
            template,
            boundary_axis=boundary_axis,
            trace_coordinate_px=reference_trace_px,
            position_px=position.center,
            support_projection_px=support_projection_px,
        )
        component = (
            line.normal_x
            if boundary_axis == BoundaryAxis.X
            else line.normal_y
        )
        offset_values = (
            line.offset_px
            + (position.minimum - position.center) * component,
            line.offset_px
            + (position.maximum - position.center) * component,
        )
        dependencies = tuple(
            sorted(
                {
                    item.observation_id
                    for item in hypothesis.observations_by_role
                    if item is not None
                },
                key=str,
            )
        )
        boundaries.append(
            FrameBoundaryGeometry(
                role=role,
                line=line,
                offset_interval_px=FiniteInterval(
                    min(offset_values),
                    max(offset_values),
                ),
                source=BoundarySource.INFERRED_SEQUENCE,
                observation_ids=dependencies,
                named_inference=(
                    f"sequence_{role.value}_from_observed_anchor_"
                    "aperture_and_gutter_intervals"
                ),
            )
        )
    return boundaries[0], boundaries[1]
