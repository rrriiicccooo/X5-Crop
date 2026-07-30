from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import math
import numpy as np

from ...configuration.grid import FrameGridSearchPrior
from ...domain import Box, EvidenceState, FiniteInterval
from ...formats import FrameDesignApertureMm
from ..evidence.separator import (
    LongAxisSeparatorMeasurementField,
    SeparatorCorridorObservation,
    separator_corridor_observations,
)
from ..source_core import SourceLaneEvidence
from .model import (
    K_MAX,
    O_MAX,
    P_MAX,
    FrameGridEquivalenceClass,
    FrameGridProposal,
    FrameGridWorkStatistics,
    FrameSlot,
    GridAnchorClass,
    GridCandidateKind,
    GridCorridorCandidate,
    GridOmissionScope,
    GridOmissionSummary,
    GridOmittedAlternative,
    LaneGridSelection,
    PlacementSeed,
    PlacementSeedKind,
    SafeCropEnvelope,
    SlotInteraction,
)


BOUNDARY_MATCH_TOLERANCE_MM = 1.5


@dataclass(frozen=True)
class _SeedDescriptor:
    descriptor_id: str
    kind: PlacementSeedKind
    interval: FiniteInterval
    ordering_score: float
    provenance: str


@dataclass(frozen=True)
class _PathState:
    state_id: str
    path: tuple[GridCorridorCandidate, ...]
    ordering_cost: float


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:20]}"


def _interval_union(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    if not values:
        raise ValueError("interval union requires values")
    return FiniteInterval(
        min(item.minimum for item in values),
        max(item.maximum for item in values),
    )


def _aggregate_state(values: tuple[EvidenceState, ...]) -> EvidenceState:
    if not values:
        return EvidenceState.UNAVAILABLE
    if any(value == EvidenceState.CONTRADICTED for value in values):
        return EvidenceState.CONTRADICTED
    if all(value == EvidenceState.SUPPORTED for value in values):
        return EvidenceState.SUPPORTED
    if all(value == EvidenceState.NOT_APPLICABLE for value in values):
        return EvidenceState.NOT_APPLICABLE
    return EvidenceState.UNAVAILABLE


def _bounded_interval(
    center: float,
    radius: float,
    lower: float,
    upper: float,
) -> FiniteInterval | None:
    minimum = max(lower, center - radius)
    maximum = min(upper, center + radius)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


def _expanded_observed_interval(
    interval: FiniteInterval,
    uncertainty_px: float,
    upper_px: float,
) -> FiniteInterval:
    bounded = _bounded_interval(
        interval.center,
        uncertainty_px + interval.width / 2.0,
        0.0,
        upper_px,
    )
    if bounded is None:
        raise ValueError("observed interval lies outside lane authority")
    return bounded


def _clipped_interval(
    interval: FiniteInterval,
    lower: float,
    upper: float,
) -> FiniteInterval | None:
    minimum = max(lower, interval.minimum)
    maximum = min(upper, interval.maximum)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


def _nearest_line(
    field: LongAxisSeparatorMeasurementField,
    expected_px: float,
    tolerance_px: float,
):
    eligible = tuple(
        line
        for line in field.lines
        if abs(line.boundary_px - expected_px) <= tolerance_px
    )
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda line: (
            abs(line.boundary_px - expected_px),
            -line.support_fraction,
            str(line.observation_id),
        ),
    )


def _seed_descriptors_are_equivalent(
    descriptors: tuple[_SeedDescriptor, ...],
    pitch_px: float,
    equality_px: float,
) -> bool:
    if not descriptors:
        return False
    centers = tuple(item.interval.center for item in descriptors)
    return max(centers) - min(centers) + equality_px < pitch_px


def _positive_content_support_interval(
    lane: SourceLaneEvidence,
    aperture_px: float,
) -> FiniteInterval | None:
    table = lane.content.row_run_table
    domain = lane.domain.work_box
    if table.run_count == 0:
        return None
    difference = np.zeros(domain.width + 1, dtype=np.int64)
    lefts = table.lefts - domain.left
    rights = table.rights - domain.left
    np.add.at(difference, lefts, 1)
    np.add.at(difference, rights, -1)
    support = np.cumsum(difference[:-1], dtype=np.int64).astype(
        np.float64,
        copy=False,
    )
    support /= float(domain.height)
    window = max(1, min(domain.width, round(aperture_px / 4.0)))
    cumulative = np.empty(support.size + 1, dtype=np.float64)
    cumulative[0] = 0.0
    np.cumsum(support, out=cumulative[1:])
    smoothed = (
        cumulative[window:] - cumulative[:-window]
    ) / float(window)
    if not smoothed.size:
        return None
    maximum = float(smoothed.max())
    if maximum <= 0.0:
        return None
    active = np.flatnonzero(smoothed >= maximum * 0.5)
    if not active.size:
        return None
    center_offset = window // 2
    return FiniteInterval(
        float(domain.left + int(active[0]) + center_offset),
        float(domain.left + int(active[-1]) + center_offset),
    )


def _placement_seeds(
    lane: SourceLaneEvidence,
    component_id: str,
    output_slot_count: int,
    prior: FrameGridSearchPrior,
    field: LongAxisSeparatorMeasurementField,
    px_per_mm: float,
) -> tuple[tuple[PlacementSeed, ...], tuple[GridOmissionSummary, ...]]:
    lane_id = lane.domain.lane_id
    aperture_px = prior.aperture_long_axis_mm * px_per_mm
    pitch_px = prior.pitch_mm.center * px_per_mm
    uncertainty_px = prior.boundary_uncertainty_mm * px_per_mm
    equality_px = prior.equality_interval_mm * px_per_mm
    total_span = (
        (output_slot_count - 1) * pitch_px + aperture_px
    )
    maximum_origin = field.long_extent_px - total_span
    if maximum_origin < 0.0:
        return (), ()

    raw: list[_SeedDescriptor] = []
    if prior.strip_mode == "full":
        leading_center = prior.full_leading_margin_mm.center * px_per_mm
        trailing_center = (
            field.long_extent_px
            - prior.full_trailing_margin_mm.center * px_per_mm
            - total_span
        )
        model_values = (
            (
                PlacementSeedKind.FULL_LEADING,
                leading_center,
                "full_margin_model",
            ),
            (
                PlacementSeedKind.FULL_TRAILING,
                trailing_center,
                "full_margin_model",
            ),
            (
                PlacementSeedKind.CENTERED,
                (field.long_extent_px - total_span) / 2.0,
                "full_margin_model",
            ),
        )
    else:
        support = _positive_content_support_interval(lane, aperture_px)
        if support is None:
            model_values = (
                (
                    PlacementSeedKind.CENTERED,
                    maximum_origin / 2.0,
                    "blank_center_model",
                ),
            )
        else:
            leading_gap = support.minimum
            trailing_gap = field.long_extent_px - support.maximum
            intervals: list[FiniteInterval] = []
            if leading_gap <= trailing_gap + pitch_px:
                minimum = max(0.0, support.minimum - aperture_px)
                maximum = min(maximum_origin, support.minimum)
                if maximum >= minimum:
                    intervals.append(FiniteInterval(minimum, maximum))
            if trailing_gap <= leading_gap + pitch_px:
                minimum = max(0.0, support.maximum - total_span)
                maximum = min(
                    maximum_origin,
                    support.maximum - total_span + aperture_px,
                )
                if maximum >= minimum:
                    intervals.append(FiniteInterval(minimum, maximum))
            model_values = ()
            for interval in intervals:
                raw.append(
                    _SeedDescriptor(
                        descriptor_id=_stable_id(
                            "seed-descriptor",
                            lane_id,
                            component_id,
                            PlacementSeedKind.POSITIVE_CONTENT.value,
                            f"{interval.minimum:.6f}",
                            f"{interval.maximum:.6f}",
                        ),
                        kind=PlacementSeedKind.POSITIVE_CONTENT,
                        interval=interval,
                        ordering_score=0.0,
                        provenance="positive_content_placement",
                    )
                )
    for kind, origin, provenance in model_values:
        interval = _bounded_interval(
            origin,
            uncertainty_px,
            0.0,
            maximum_origin,
        )
        if interval is None:
            continue
        raw.append(
            _SeedDescriptor(
                descriptor_id=_stable_id(
                    "seed-descriptor",
                    lane_id,
                    component_id,
                    kind.value,
                    f"{interval.center:.6f}",
                    provenance,
                ),
                kind=kind,
                interval=interval,
                ordering_score=0.0,
                provenance=provenance,
            )
        )

    unique_by_id = {
        item.descriptor_id: item for item in raw
    }
    ordered = sorted(
        unique_by_id.values(),
        key=lambda item: (item.interval.center, item.descriptor_id),
    )
    groups: list[list[_SeedDescriptor]] = []
    for descriptor in ordered:
        matching = next(
            (
                group
                for group in groups
                if _seed_descriptors_are_equivalent(
                    tuple((*group, descriptor)),
                    pitch_px,
                    equality_px,
                )
            ),
            None,
        )
        if matching is None:
            groups.append([descriptor])
        else:
            matching.append(descriptor)

    group_records: list[
        tuple[PlacementSeed, str, tuple[_SeedDescriptor, ...]]
    ] = []
    for group in groups:
        members = tuple(sorted(group, key=lambda item: item.descriptor_id))
        representative = min(
            members,
            key=lambda item: (-item.ordering_score, item.descriptor_id),
        )
        class_id = _stable_id(
            "seed-equivalence",
            *(item.descriptor_id for item in members),
        )
        group_records.append(
            (
                PlacementSeed(
                    seed_id=class_id,
                    kind=representative.kind,
                    origin_px=_interval_union(
                        tuple(item.interval for item in members)
                    ),
                    scalar_ordering_score=representative.ordering_score,
                    provenance=representative.provenance,
                ),
                representative.descriptor_id,
                members,
            )
        )
    group_records.sort(
        key=lambda item: (
            -item[0].scalar_ordering_score,
            item[0].origin_px.center,
            item[0].seed_id,
        )
    )
    retained = tuple(group_records[:P_MAX])
    retained_ids = {item[0].seed_id for item in retained}
    omitted: list[GridOmittedAlternative] = []
    for seed, representative_id, members in group_records:
        retained_class = seed.seed_id in retained_ids
        for member in members:
            if retained_class and member.descriptor_id == representative_id:
                continue
            omitted.append(
                GridOmittedAlternative(
                    alternative_id=member.descriptor_id,
                    absorbing_equivalence_class_id=(
                        seed.seed_id if retained_class else None
                    ),
                )
            )
    summaries = (
        (
            GridOmissionSummary(
                scope_id=_stable_id(
                    "omission-scope",
                    lane_id,
                    component_id,
                    GridOmissionScope.PLACEMENT_SEED.value,
                ),
                scope=GridOmissionScope.PLACEMENT_SEED,
                lane_id=lane_id,
                component_id=component_id,
                seed_id=None,
                corridor_ordinal=None,
                discovered_count=len(ordered),
                retained_count=len(retained),
                omitted_alternatives=tuple(
                    sorted(omitted, key=lambda item: item.alternative_id)
                ),
            ),
        )
        if omitted
        else ()
    )
    return tuple(item[0] for item in retained), summaries


def _candidate_geometry_equivalent(
    candidates: tuple[GridCorridorCandidate, ...],
    pitch_px: float,
    equality_px: float,
) -> bool:
    if not candidates:
        return False
    previous = tuple(
        item.previous_photo_end_px.center for item in candidates
    )
    following = tuple(
        item.next_photo_start_px.center for item in candidates
    )
    shared_minimum = min(
        min(
            item.previous_photo_end_px.minimum,
            item.next_photo_start_px.minimum,
        )
        for item in candidates
    )
    shared_maximum = max(
        max(
            item.previous_photo_end_px.maximum,
            item.next_photo_start_px.maximum,
        )
        for item in candidates
    )
    return (
        max(previous) - min(previous) + equality_px < pitch_px
        and max(following) - min(following) + equality_px < pitch_px
        and shared_maximum - shared_minimum + equality_px < pitch_px
    )


def _corridor_shared_interval(
    candidate: GridCorridorCandidate,
) -> FiniteInterval:
    return FiniteInterval(
        min(
            candidate.previous_photo_end_px.minimum,
            candidate.next_photo_start_px.minimum,
        ),
        max(
            candidate.previous_photo_end_px.maximum,
            candidate.next_photo_start_px.maximum,
        ),
    )


def _merge_corridor_candidates(
    candidates: tuple[GridCorridorCandidate, ...],
) -> GridCorridorCandidate:
    if not candidates:
        raise ValueError("corridor union requires candidates")
    corridor_index = candidates[0].corridor_index
    if any(item.corridor_index != corridor_index for item in candidates):
        raise ValueError("corridor union requires one ordinal")
    source_ids = tuple(
        sorted(
            {
                source_id
                for item in candidates
                for source_id in item.source_candidate_ids
            }
        )
    )
    observed = tuple(
        item for item in candidates if item.observation is not None
    )
    representative = min(
        observed or candidates,
        key=lambda item: (
            item.residual_mm,
            item.candidate_id,
        ),
    )
    return GridCorridorCandidate(
        candidate_id=_stable_id(
            "corridor-equivalence",
            corridor_index,
            *source_ids,
        ),
        source_candidate_ids=source_ids,
        corridor_index=corridor_index,
        kind=representative.kind,
        previous_photo_end_px=_interval_union(
            tuple(item.previous_photo_end_px for item in candidates)
        ),
        next_photo_start_px=_interval_union(
            tuple(item.next_photo_start_px for item in candidates)
        ),
        observation=representative.observation,
        residual_mm=max(item.residual_mm for item in candidates),
    )


def _local_corridor_candidates(
    lane_id: str,
    component_id: str,
    seed: PlacementSeed,
    corridor_index: int,
    expected_end_px: float,
    expected_start_px: float,
    observations: tuple[SeparatorCorridorObservation, ...],
    prior: FrameGridSearchPrior,
    px_per_mm: float,
    upper_px: float,
) -> tuple[
    tuple[GridCorridorCandidate, ...],
    tuple[GridOmissionSummary, ...],
]:
    boundary_uncertainty_px = (
        prior.boundary_uncertainty_mm * px_per_mm
    )
    tolerance_px = (
        BOUNDARY_MATCH_TOLERANCE_MM * px_per_mm
        + seed.origin_px.width / 2.0
    )
    equality_px = prior.equality_interval_mm * px_per_mm
    pitch_px = prior.pitch_mm.center * px_per_mm
    observed: list[GridCorridorCandidate] = []
    for observation in observations:
        previous = observation.previous_photo_end_px
        following = observation.next_photo_start_px
        if observation.kind == "edge_pair":
            previous_residual = abs(previous.center - expected_end_px)
            next_residual = abs(following.center - expected_start_px)
            if max(previous_residual, next_residual) > tolerance_px:
                continue
            kind = GridCandidateKind.OBSERVED_EDGE_PAIR
        else:
            learned_gutter = observation.learned_gutter_px
            if learned_gutter is None:
                raise ValueError(
                    "one-sided candidate requires learned gutter authority"
                )
            previous_residual = abs(previous.center - expected_end_px)
            next_residual = abs(previous.center - expected_start_px)
            if min(previous_residual, next_residual) > tolerance_px:
                continue
            if previous_residual <= next_residual:
                following = _clipped_interval(
                    FiniteInterval(
                        previous.minimum + learned_gutter.minimum,
                        previous.maximum + learned_gutter.maximum,
                    ),
                    0.0,
                    upper_px,
                )
                if following is None:
                    continue
            else:
                previous = _clipped_interval(
                    FiniteInterval(
                        following.minimum - learned_gutter.maximum,
                        following.maximum - learned_gutter.minimum,
                    ),
                    0.0,
                    upper_px,
                )
                if previous is None:
                    continue
            kind = GridCandidateKind.OBSERVED_ONE_SIDED
        raw_id = _stable_id(
            "corridor-candidate",
            lane_id,
            component_id,
            seed.seed_id,
            corridor_index,
            observation.observation_id,
            kind.value,
        )
        candidate = GridCorridorCandidate(
                candidate_id=raw_id,
                source_candidate_ids=(raw_id,),
                corridor_index=corridor_index,
                kind=kind,
                previous_photo_end_px=_expanded_observed_interval(
                    previous,
                    boundary_uncertainty_px,
                    upper_px,
                ),
                next_photo_start_px=_expanded_observed_interval(
                    following,
                    boundary_uncertainty_px,
                    upper_px,
                ),
                observation=observation,
                residual_mm=(
                    previous_residual + next_residual
                )
                / px_per_mm,
            )
        if (
            _corridor_shared_interval(candidate).width + equality_px
            >= pitch_px
        ):
            continue
        observed.append(candidate)
    observed.sort(
        key=lambda item: (
            item.residual_mm
            - (
                0.0
                if item.observation is None
                else item.observation.support
            ),
            item.kind.value,
            item.candidate_id,
        )
    )
    geometry_order = sorted(
        observed,
        key=lambda item: (
            item.previous_photo_end_px.center,
            item.next_photo_start_px.center,
            item.candidate_id,
        ),
    )
    groups: list[list[GridCorridorCandidate]] = []
    for candidate in geometry_order:
        matching = next(
            (
                group
                for group in groups
                if _candidate_geometry_equivalent(
                    tuple((*group, candidate)),
                    pitch_px,
                    equality_px,
                )
            ),
            None,
        )
        if matching is None:
            groups.append([candidate])
        else:
            matching.append(candidate)

    group_records: list[
        tuple[
            GridCorridorCandidate,
            str,
            tuple[GridCorridorCandidate, ...],
        ]
    ] = []
    for group in groups:
        members = tuple(sorted(group, key=lambda item: item.candidate_id))
        representative = min(
            members,
            key=lambda item: (
                item.residual_mm
                - (
                    0.0
                    if item.observation is None
                    else item.observation.support
                ),
                item.candidate_id,
            ),
        )
        group_records.append(
            (
                _merge_corridor_candidates(members),
                representative.candidate_id,
                members,
            )
        )
    group_records.sort(
        key=lambda item: (
            item[0].residual_mm
            - (
                0.0
                if item[0].observation is None
                else item[0].observation.support
            ),
            item[0].candidate_id,
        )
    )
    retained = tuple(group_records[:O_MAX])
    retained_ids = {item[0].candidate_id for item in retained}
    omitted: list[GridOmittedAlternative] = []
    for candidate, representative_id, members in group_records:
        retained_class = candidate.candidate_id in retained_ids
        for member in members:
            if retained_class and member.candidate_id == representative_id:
                continue
            omitted.append(
                GridOmittedAlternative(
                    alternative_id=member.candidate_id,
                    absorbing_equivalence_class_id=(
                        candidate.candidate_id if retained_class else None
                    ),
                )
            )
    summaries = (
        (
            GridOmissionSummary(
                scope_id=_stable_id(
                    "omission-scope",
                    lane_id,
                    component_id,
                    seed.seed_id,
                    GridOmissionScope.OBSERVED_CORRIDOR.value,
                    corridor_index,
                ),
                scope=GridOmissionScope.OBSERVED_CORRIDOR,
                lane_id=lane_id,
                component_id=component_id,
                seed_id=seed.seed_id,
                corridor_ordinal=corridor_index,
                discovered_count=len(observed),
                retained_count=len(retained),
                omitted_alternatives=tuple(
                    sorted(omitted, key=lambda item: item.alternative_id)
                ),
            ),
        )
        if omitted
        else ()
    )

    end_offset = expected_end_px - seed.origin_px.center
    start_offset = expected_start_px - seed.origin_px.center
    model_end = _clipped_interval(
        FiniteInterval(
            seed.origin_px.minimum + end_offset,
            seed.origin_px.maximum + end_offset,
        ),
        0.0,
        upper_px,
    )
    model_start = _clipped_interval(
        FiniteInterval(
            seed.origin_px.minimum + start_offset,
            seed.origin_px.maximum + start_offset,
        ),
        0.0,
        upper_px,
    )
    candidates = [item[0] for item in retained]
    if model_end is not None and model_start is not None:
        model_id = _stable_id(
            "corridor-model",
            lane_id,
            component_id,
            seed.seed_id,
            corridor_index,
        )
        candidates.append(
            GridCorridorCandidate(
                candidate_id=model_id,
                source_candidate_ids=(model_id,),
                corridor_index=corridor_index,
                kind=GridCandidateKind.MODEL_ONLY,
                previous_photo_end_px=model_end,
                next_photo_start_px=model_start,
                observation=None,
                residual_mm=0.0,
            )
        )
    return tuple(candidates[:K_MAX]), summaries


def _path_geometry_equivalent(
    states: tuple[_PathState, ...],
    pitch_px: float,
    equality_px: float,
) -> bool:
    if not states:
        return False
    length = len(states[0].path)
    if any(len(state.path) != length for state in states):
        return False
    return all(
        _candidate_geometry_equivalent(
            tuple(state.path[index] for state in states),
            pitch_px,
            equality_px,
        )
        for index in range(length)
    )


def _merge_path_states(states: tuple[_PathState, ...]) -> _PathState:
    if not states:
        raise ValueError("path-state union requires values")
    member_ids = tuple(sorted(state.state_id for state in states))
    return _PathState(
        state_id=_stable_id("dp-equivalence", *member_ids),
        path=tuple(
            _merge_corridor_candidates(
                tuple(state.path[index] for state in states)
            )
            for index in range(len(states[0].path))
        ),
        ordering_cost=min(state.ordering_cost for state in states),
    )


def _normalize_frontier(
    raw_states: tuple[_PathState, ...],
    *,
    lane_id: str,
    component_id: str,
    seed_id: str,
    frontier_ordinal: int,
    pitch_px: float,
    equality_px: float,
) -> tuple[tuple[_PathState, ...], tuple[GridOmissionSummary, ...]]:
    ordered = tuple(sorted(raw_states, key=lambda item: item.state_id))
    groups: list[list[_PathState]] = []
    for state in ordered:
        matching = next(
            (
                group
                for group in groups
                if _path_geometry_equivalent(
                    tuple((*group, state)),
                    pitch_px,
                    equality_px,
                )
            ),
            None,
        )
        if matching is None:
            groups.append([state])
        else:
            matching.append(state)
    records: list[tuple[_PathState, str, tuple[_PathState, ...]]] = []
    for group in groups:
        members = tuple(sorted(group, key=lambda item: item.state_id))
        representative = min(
            members,
            key=lambda item: (item.ordering_cost, item.state_id),
        )
        records.append(
            (_merge_path_states(members), representative.state_id, members)
        )
    records.sort(
        key=lambda item: (
            item[0].ordering_cost,
            item[0].state_id,
        )
    )
    retained = tuple(records[:K_MAX])
    retained_ids = {item[0].state_id for item in retained}
    omitted: list[GridOmittedAlternative] = []
    for state, representative_id, members in records:
        retained_class = state.state_id in retained_ids
        for member in members:
            if retained_class and member.state_id == representative_id:
                continue
            omitted.append(
                GridOmittedAlternative(
                    alternative_id=member.state_id,
                    absorbing_equivalence_class_id=(
                        state.state_id if retained_class else None
                    ),
                )
            )
    summaries = (
        (
            GridOmissionSummary(
                scope_id=_stable_id(
                    "omission-scope",
                    lane_id,
                    component_id,
                    seed_id,
                    GridOmissionScope.DP_FRONTIER.value,
                    frontier_ordinal,
                ),
                scope=GridOmissionScope.DP_FRONTIER,
                lane_id=lane_id,
                component_id=component_id,
                seed_id=seed_id,
                corridor_ordinal=frontier_ordinal,
                discovered_count=len(raw_states),
                retained_count=len(retained),
                omitted_alternatives=tuple(
                    sorted(omitted, key=lambda item: item.alternative_id)
                ),
            ),
        )
        if omitted
        else ()
    )
    return tuple(item[0] for item in retained), summaries


def _candidate_ordering_cost(candidate: GridCorridorCandidate) -> float:
    return candidate.residual_mm - (
        0.0
        if candidate.observation is None
        else candidate.observation.support
    )


def _ordered_corridor_paths(
    candidates: tuple[tuple[GridCorridorCandidate, ...], ...],
    *,
    lane_id: str,
    component_id: str,
    seed_id: str,
    pitch_px: float,
    equality_px: float,
) -> tuple[
    tuple[_PathState, ...],
    int,
    int,
    tuple[GridOmissionSummary, ...],
]:
    if not candidates:
        return (
            (_PathState(_stable_id("dp-empty", seed_id), (), 0.0),),
            0,
            0,
            (),
        )
    transition_count = len(candidates[0])
    raw = tuple(
        _PathState(
            state_id=_stable_id("dp-state", candidate.candidate_id),
            path=(candidate,),
            ordering_cost=_candidate_ordering_cost(candidate),
        )
        for candidate in candidates[0]
    )
    states, first_summaries = _normalize_frontier(
        raw,
        lane_id=lane_id,
        component_id=component_id,
        seed_id=seed_id,
        frontier_ordinal=1,
        pitch_px=pitch_px,
        equality_px=equality_px,
    )
    state_count = len(states)
    summaries = list(first_summaries)
    for frontier_ordinal, corridor_candidates in enumerate(
        candidates[1:],
        start=2,
    ):
        following: list[_PathState] = []
        for state in states:
            prior_shared = _corridor_shared_interval(state.path[-1])
            for candidate in corridor_candidates:
                transition_count += 1
                if (
                    _corridor_shared_interval(candidate).minimum
                    <= prior_shared.maximum
                ):
                    continue
                following.append(
                    _PathState(
                        state_id=_stable_id(
                            "dp-state",
                            state.state_id,
                            candidate.candidate_id,
                        ),
                        path=(*state.path, candidate),
                        ordering_cost=(
                            state.ordering_cost
                            + _candidate_ordering_cost(candidate)
                        ),
                    )
                )
        if not following:
            return (), state_count, transition_count, tuple(summaries)
        states, frontier_summaries = _normalize_frontier(
            tuple(following),
            lane_id=lane_id,
            component_id=component_id,
            seed_id=seed_id,
            frontier_ordinal=frontier_ordinal,
            pitch_px=pitch_px,
            equality_px=equality_px,
        )
        summaries.extend(frontier_summaries)
        state_count += len(states)
    return states, state_count, transition_count, tuple(summaries)


def _interaction(
    previous_end: FiniteInterval,
    next_start: FiniteInterval,
    equality_px: float,
) -> SlotInteraction:
    delta = next_start.center - previous_end.center
    if abs(delta) <= equality_px:
        return SlotInteraction.CONTACT
    if delta < 0.0:
        return SlotInteraction.OVERLAP
    return SlotInteraction.SEPARATED


def _proposal_from_path(
    lane: SourceLaneEvidence,
    field: LongAxisSeparatorMeasurementField,
    prior: FrameGridSearchPrior,
    component_id: str,
    output_slot_count: int,
    seed: PlacementSeed,
    path_state: _PathState,
    px_per_mm: float,
) -> FrameGridProposal | None:
    aperture_px = prior.aperture_long_axis_mm * px_per_mm
    pitch_px = prior.pitch_mm.center * px_per_mm
    boundary_uncertainty_px = (
        prior.boundary_uncertainty_mm * px_per_mm
    )
    equality_px = prior.equality_interval_mm * px_per_mm
    upper_px = float(field.long_extent_px)
    origin = seed.origin_px.center
    path = path_state.path
    if output_slot_count > 1 and len(path) != output_slot_count - 1:
        return None

    tolerance_px = BOUNDARY_MATCH_TOLERANCE_MM * px_per_mm
    first_line = _nearest_line(field, origin, tolerance_px)
    first_start = seed.origin_px
    if first_line is not None:
        first_start = _interval_union(
            (
                first_start,
                _expanded_observed_interval(
                    first_line.interval_px,
                    boundary_uncertainty_px,
                    upper_px,
                ),
            )
        )
    last_start_center = origin + (output_slot_count - 1) * pitch_px
    last_end_center = last_start_center + aperture_px
    last_line = _nearest_line(field, last_end_center, tolerance_px)
    last_end = _clipped_interval(
        FiniteInterval(
            seed.origin_px.minimum
            + (output_slot_count - 1) * pitch_px
            + aperture_px,
            seed.origin_px.maximum
            + (output_slot_count - 1) * pitch_px
            + aperture_px,
        ),
        0.0,
        upper_px,
    )
    if last_end is None:
        return None
    if last_line is not None:
        last_end = _interval_union(
            (
                last_end,
                _expanded_observed_interval(
                    last_line.interval_px,
                    boundary_uncertainty_px,
                    upper_px,
                ),
            )
        )

    starts: list[FiniteInterval] = [first_start]
    ends: list[FiniteInterval] = []
    interactions: list[SlotInteraction] = []
    for candidate in path:
        shared = FiniteInterval(
            min(
                candidate.previous_photo_end_px.minimum,
                candidate.next_photo_start_px.minimum,
            ),
            max(
                candidate.previous_photo_end_px.maximum,
                candidate.next_photo_start_px.maximum,
            ),
        )
        ends.append(shared)
        starts.append(shared)
        interactions.append(
            _interaction(
                candidate.previous_photo_end_px,
                candidate.next_photo_start_px,
                equality_px,
            )
        )
    ends.append(last_end)
    if any(
        end.minimum <= start.maximum
        for start, end in zip(starts, ends, strict=True)
    ):
        return None

    domain = lane.domain.work_box
    lane_id = lane.domain.lane_id
    slots: list[FrameSlot] = []
    envelopes: list[SafeCropEnvelope] = []
    observed_boundary_count = 0
    two_sided_slot_count = 0
    for ordinal, (start, end) in enumerate(
        zip(starts, ends, strict=True),
        start=1,
    ):
        expected_start = origin + (ordinal - 1) * pitch_px
        expected_end = expected_start + aperture_px
        start_observed = _nearest_line(
            field,
            expected_start,
            tolerance_px,
        ) is not None
        end_observed = _nearest_line(
            field,
            expected_end,
            tolerance_px,
        ) is not None
        observed_boundary_count += int(start_observed) + int(end_observed)
        two_sided_slot_count += int(start_observed and end_observed)
        work_box = Box(
            domain.left + math.floor(start.minimum),
            domain.top,
            domain.left + math.ceil(end.maximum),
            domain.bottom,
        )
        if (
            not work_box.valid()
            or work_box.left < domain.left
            or work_box.right > domain.right
        ):
            return None
        content_support = any(
            component.footprint.right > work_box.left
            and component.footprint.left < work_box.right
            for component in lane.content.components
        )
        slots.append(
            FrameSlot(
                lane_id=lane_id,
                lane_ordinal=ordinal,
                start_px=start,
                end_px=end,
                appearance_state=(
                    EvidenceState.SUPPORTED
                    if content_support
                    else EvidenceState.UNAVAILABLE
                ),
                previous_interaction=(
                    SlotInteraction.NOT_APPLICABLE
                    if ordinal == 1
                    else interactions[ordinal - 2]
                ),
                next_interaction=(
                    SlotInteraction.NOT_APPLICABLE
                    if ordinal == output_slot_count
                    else interactions[ordinal - 1]
                ),
            )
        )
        envelopes.append(
            SafeCropEnvelope(
                lane_id=lane_id,
                lane_ordinal=ordinal,
                work_box=work_box,
                provenance=(
                    "observed_and_model_outward_union"
                    if start_observed or end_observed
                    else "model_outward_union"
                ),
            )
        )

    endpoint_support_count = int(first_line is not None) + int(
        last_line is not None
    )
    model_only_boundary_count = (
        2 * output_slot_count - observed_boundary_count
    )
    residual_mm = sum(item.residual_mm for item in path)
    scalar = (
        endpoint_support_count * 1000.0
        + two_sided_slot_count * 100.0
        + observed_boundary_count * 10.0
        - model_only_boundary_count
        - residual_mm
    )
    anchor_count = sum(
        item.kind != GridCandidateKind.MODEL_ONLY for item in path
    )
    anchor_class = (
        GridAnchorClass.ZERO
        if anchor_count == 0
        else GridAnchorClass.ONE
        if anchor_count == 1
        else GridAnchorClass.TWO_PLUS
    )
    return FrameGridProposal(
        proposal_id=_stable_id(
            "grid-proposal",
            lane_id,
            component_id,
            output_slot_count,
            seed.seed_id,
            path_state.state_id,
        ),
        lane_id=lane_id,
        component_id=component_id,
        output_slot_count=output_slot_count,
        seed=seed,
        corridor_candidates=path,
        anchor_class=anchor_class,
        slots=tuple(slots),
        safe_envelopes=tuple(envelopes),
        content_assignment_signature=(),
        observed_boundary_count=observed_boundary_count,
        two_sided_slot_count=two_sided_slot_count,
        endpoint_support_count=endpoint_support_count,
        model_only_boundary_count=model_only_boundary_count,
        residual_mm=residual_mm,
        scalar_ordering_score=scalar,
        geometry_state=EvidenceState.SUPPORTED,
        ordinal_state=EvidenceState.SUPPORTED,
        ownership_state=EvidenceState.SUPPORTED,
        containment_state=(
            EvidenceState.UNAVAILABLE
            if lane.content.state != EvidenceState.CONTRADICTED
            else EvidenceState.CONTRADICTED
        ),
    )


def _component_proposals(
    lane: SourceLaneEvidence,
    field: LongAxisSeparatorMeasurementField,
    prior: FrameGridSearchPrior,
    component_id: str,
    output_slot_count: int,
    px_per_mm: float,
    observations: tuple[SeparatorCorridorObservation, ...],
) -> tuple[tuple[FrameGridProposal, ...], FrameGridWorkStatistics]:
    seeds, seed_summaries = _placement_seeds(
        lane,
        component_id,
        output_slot_count,
        prior,
        field,
        px_per_mm,
    )
    proposals: list[FrameGridProposal] = []
    omissions = list(seed_summaries)
    total_states = 0
    total_transitions = 0
    observed_candidates = 0
    model_candidates = 0
    pitch_px = prior.pitch_mm.center * px_per_mm
    equality_px = prior.equality_interval_mm * px_per_mm
    aperture_px = prior.aperture_long_axis_mm * px_per_mm
    upper_px = float(field.long_extent_px)
    for seed in seeds:
        origin = seed.origin_px.center
        candidates_by_corridor: list[
            tuple[GridCorridorCandidate, ...]
        ] = []
        for corridor_index in range(1, output_slot_count):
            candidates, summaries = _local_corridor_candidates(
                lane.domain.lane_id,
                component_id,
                seed,
                corridor_index,
                origin + (corridor_index - 1) * pitch_px + aperture_px,
                origin + corridor_index * pitch_px,
                observations,
                prior,
                px_per_mm,
                upper_px,
            )
            candidates_by_corridor.append(candidates)
            omissions.extend(summaries)
        if any(not values for values in candidates_by_corridor):
            continue
        path_states, states, transitions, path_summaries = (
            _ordered_corridor_paths(
                tuple(candidates_by_corridor),
                lane_id=lane.domain.lane_id,
                component_id=component_id,
                seed_id=seed.seed_id,
                pitch_px=pitch_px,
                equality_px=equality_px,
            )
        )
        omissions.extend(path_summaries)
        total_states += states
        total_transitions += transitions
        observed_candidates += sum(
            candidate.kind != GridCandidateKind.MODEL_ONLY
            for values in candidates_by_corridor
            for candidate in values
        )
        model_candidates += sum(
            candidate.kind == GridCandidateKind.MODEL_ONLY
            for values in candidates_by_corridor
            for candidate in values
        )
        for path_state in path_states:
            proposal = _proposal_from_path(
                lane,
                field,
                prior,
                component_id,
                output_slot_count,
                seed,
                path_state,
                px_per_mm,
            )
            if proposal is not None:
                proposals.append(proposal)
    work = FrameGridWorkStatistics(
        lane_id=lane.domain.lane_id,
        component_id=component_id,
        output_slot_count=output_slot_count,
        seed_count=len(seeds),
        observed_candidate_count=observed_candidates,
        model_candidate_count=model_candidates,
        candidate_builds=len(seeds),
        dp_states=total_states,
        dp_transitions=total_transitions,
        state_upper=FrameGridWorkStatistics.state_limit(output_slot_count),
        transition_upper=FrameGridWorkStatistics.transition_limit(
            output_slot_count
        ),
        retained_proposal_count=len(proposals),
        omission_summaries=tuple(omissions),
        budget_exhausted=False,
    )
    return tuple(proposals), work


def _proposals_are_output_equivalent(
    proposals: tuple[FrameGridProposal, ...],
    *,
    equality_interval_px: float,
) -> bool:
    if not proposals:
        raise ValueError("output equivalence requires proposals")
    base = proposals[0]
    if any(
        proposal.lane_id != base.lane_id
        or proposal.output_slot_count != base.output_slot_count
        or proposal.content_assignment_signature
        != base.content_assignment_signature
        for proposal in proposals
    ):
        return False
    if base.output_slot_count > 1:
        pitch_floor = min(
            following.start_px.center - previous.start_px.center
            for proposal in proposals
            for previous, following in zip(
                proposal.slots,
                proposal.slots[1:],
            )
        )
        if pitch_floor <= 0.0:
            return False
        maximum_ordinal_shift = max(
            max(
                proposal.slots[ordinal].start_px.center
                for proposal in proposals
            )
            - min(
                proposal.slots[ordinal].start_px.center
                for proposal in proposals
            )
            for ordinal in range(base.output_slot_count)
        )
        if maximum_ordinal_shift + equality_interval_px >= pitch_floor:
            return False
        for ordinal in range(base.output_slot_count):
            earliest_start = min(
                proposal.slots[ordinal].start_px.minimum
                for proposal in proposals
            )
            latest_end = max(
                proposal.slots[ordinal].end_px.maximum
                for proposal in proposals
            )
            if latest_end <= earliest_start:
                return False
    return True


def _merged_interaction(
    values: tuple[SlotInteraction, ...],
    *,
    endpoint: bool,
) -> SlotInteraction:
    if endpoint:
        return SlotInteraction.NOT_APPLICABLE
    if len(set(values)) == 1:
        return values[0]
    if SlotInteraction.OVERLAP in values:
        return SlotInteraction.OVERLAP
    if SlotInteraction.CONTACT in values:
        return SlotInteraction.CONTACT
    return SlotInteraction.SEPARATED


def _outward_union_proposals(
    proposals: tuple[FrameGridProposal, ...],
    class_id: str,
) -> FrameGridProposal:
    if not _proposals_are_output_equivalent(
        proposals,
        equality_interval_px=0.0,
    ):
        raise ValueError("only output-equivalent proposals can be unioned")
    base = min(proposals, key=lambda item: item.proposal_id)
    count = base.output_slot_count
    slots = tuple(
        FrameSlot(
            lane_id=base.lane_id,
            lane_ordinal=ordinal + 1,
            start_px=FiniteInterval.exact(
                min(
                    item.slots[ordinal].start_px.minimum
                    for item in proposals
                )
            ),
            end_px=FiniteInterval.exact(
                max(
                    item.slots[ordinal].end_px.maximum
                    for item in proposals
                )
            ),
            appearance_state=(
                EvidenceState.SUPPORTED
                if any(
                    item.slots[ordinal].appearance_state
                    == EvidenceState.SUPPORTED
                    for item in proposals
                )
                else _aggregate_state(
                    tuple(
                        item.slots[ordinal].appearance_state
                        for item in proposals
                    )
                )
            ),
            previous_interaction=_merged_interaction(
                tuple(
                    item.slots[ordinal].previous_interaction
                    for item in proposals
                ),
                endpoint=ordinal == 0,
            ),
            next_interaction=_merged_interaction(
                tuple(
                    item.slots[ordinal].next_interaction
                    for item in proposals
                ),
                endpoint=ordinal == count - 1,
            ),
        )
        for ordinal in range(count)
    )
    envelopes = tuple(
        SafeCropEnvelope(
            lane_id=base.lane_id,
            lane_ordinal=ordinal + 1,
            work_box=Box(
                min(
                    item.safe_envelopes[ordinal].work_box.left
                    for item in proposals
                ),
                min(
                    item.safe_envelopes[ordinal].work_box.top
                    for item in proposals
                ),
                max(
                    item.safe_envelopes[ordinal].work_box.right
                    for item in proposals
                ),
                max(
                    item.safe_envelopes[ordinal].work_box.bottom
                    for item in proposals
                ),
            ),
            provenance=(
                "observed_and_model_outward_union"
                if any(
                    item.safe_envelopes[ordinal].provenance
                    == "observed_and_model_outward_union"
                    for item in proposals
                )
                else "model_outward_union"
            ),
        )
        for ordinal in range(count)
    )
    corridor_candidates = tuple(
        _merge_corridor_candidates(
            tuple(
                item.corridor_candidates[index]
                for item in proposals
            )
        )
        for index in range(max(0, count - 1))
    )
    anchor_count = sum(
        item.kind != GridCandidateKind.MODEL_ONLY
        for item in corridor_candidates
    )
    anchor_class = (
        GridAnchorClass.ZERO
        if anchor_count == 0
        else GridAnchorClass.ONE
        if anchor_count == 1
        else GridAnchorClass.TWO_PLUS
    )
    representative_seed = min(
        (item.seed for item in proposals),
        key=lambda item: item.seed_id,
    )
    return replace(
        base,
        proposal_id=class_id,
        component_id=(
            base.component_id
            if len({item.component_id for item in proposals}) == 1
            else "equivalence_union"
        ),
        seed=replace(
            representative_seed,
            seed_id=_stable_id(
                "seed-union",
                *(sorted(item.seed.seed_id for item in proposals)),
            ),
            origin_px=_interval_union(
                tuple(item.seed.origin_px for item in proposals)
            ),
            scalar_ordering_score=max(
                item.seed.scalar_ordering_score for item in proposals
            ),
        ),
        corridor_candidates=corridor_candidates,
        anchor_class=anchor_class,
        slots=slots,
        safe_envelopes=envelopes,
        observed_boundary_count=max(
            item.observed_boundary_count for item in proposals
        ),
        two_sided_slot_count=max(
            item.two_sided_slot_count for item in proposals
        ),
        endpoint_support_count=max(
            item.endpoint_support_count for item in proposals
        ),
        model_only_boundary_count=min(
            item.model_only_boundary_count for item in proposals
        ),
        residual_mm=max(item.residual_mm for item in proposals),
        scalar_ordering_score=max(
            item.scalar_ordering_score for item in proposals
        ),
        geometry_state=_aggregate_state(
            tuple(item.geometry_state for item in proposals)
        ),
        ordinal_state=_aggregate_state(
            tuple(item.ordinal_state for item in proposals)
        ),
        ownership_state=_aggregate_state(
            tuple(item.ownership_state for item in proposals)
        ),
        containment_state=_aggregate_state(
            tuple(item.containment_state for item in proposals)
        ),
    )


def _proposal_equivalence_classes(
    proposals: tuple[FrameGridProposal, ...],
    equality_interval_px: float,
) -> tuple[FrameGridEquivalenceClass, ...]:
    groups: list[list[FrameGridProposal]] = []
    for proposal in sorted(proposals, key=lambda item: item.proposal_id):
        matching = next(
            (
                group
                for group in groups
                if _proposals_are_output_equivalent(
                    tuple((*group, proposal)),
                    equality_interval_px=equality_interval_px,
                )
            ),
            None,
        )
        if matching is None:
            groups.append([proposal])
        else:
            matching.append(proposal)
    classes = []
    for group in groups:
        members = tuple(sorted(group, key=lambda item: item.proposal_id))
        member_ids = tuple(item.proposal_id for item in members)
        class_id = _stable_id("grid-equivalence", *member_ids)
        classes.append(
            FrameGridEquivalenceClass(
                equivalence_class_id=class_id,
                member_proposal_ids=member_ids,
                merged_proposal=(
                    replace(members[0], proposal_id=class_id)
                    if len(members) == 1
                    else _outward_union_proposals(members, class_id)
                ),
            )
        )
    return tuple(
        sorted(classes, key=lambda item: item.equivalence_class_id)
    )


def search_lane_grid(
    lane: SourceLaneEvidence,
    separator_field: LongAxisSeparatorMeasurementField,
    output_slot_count: int,
    aperture_components: tuple[FrameDesignApertureMm, ...],
    priors: tuple[FrameGridSearchPrior, ...],
) -> LaneGridSelection:
    if (
        len(aperture_components) != len(priors)
        or output_slot_count <= 0
        or separator_field.lane_id != lane.domain.lane_id
    ):
        raise ValueError("lane Grid search inputs are inconsistent")
    scale_authority = lane.scan_canvas.axis_scales
    if scale_authority is None:
        raise ValueError("lane Grid search requires scan-canvas scale authority")
    px_per_mm = scale_authority.long_axis_px_per_mm.maximum
    proposals: list[FrameGridProposal] = []
    work: list[FrameGridWorkStatistics] = []
    separator_work = []
    equality_intervals = []
    for component_index, (component, prior) in enumerate(
        zip(aperture_components, priors, strict=True)
    ):
        component_id = (
            f"component:{component_index}:"
            f"{component.long_axis_mm:g}x{component.short_axis_mm:g}"
        )
        equality_intervals.append(
            prior.equality_interval_mm * px_per_mm
        )
        observation_set = separator_corridor_observations(
            separator_field,
            FiniteInterval(
                prior.gutter_mm.minimum * px_per_mm,
                prior.gutter_mm.maximum * px_per_mm,
            ),
            equality_interval_px=(
                prior.equality_interval_mm * px_per_mm
            ),
        )
        separator_work.append(observation_set.work)
        component_values, statistics = _component_proposals(
            lane,
            separator_field,
            prior,
            component_id,
            output_slot_count,
            px_per_mm,
            observation_set.corridors,
        )
        proposals.extend(component_values)
        work.append(statistics)

    classes = _proposal_equivalence_classes(
        tuple(proposals),
        min(equality_intervals),
    )
    omission_risk = any(item.omitted_outcome_risk for item in work)
    if omission_risk:
        selected = None
        reason = "omitted_outcome_unresolved"
        ordinal_state = EvidenceState.UNAVAILABLE
        ownership_state = EvidenceState.UNAVAILABLE
    elif len(classes) == 1:
        selected = classes[0].merged_proposal
        reason = "unique_output_equivalence_class"
        ordinal_state = selected.ordinal_state
        ownership_state = selected.ownership_state
    elif classes:
        selected = None
        reason = "non_equivalent_alternatives"
        ordinal_state = EvidenceState.CONTRADICTED
        signatures = {
            item.merged_proposal.content_assignment_signature
            for item in classes
        }
        ownership_state = (
            EvidenceState.CONTRADICTED
            if len(signatures) > 1
            else EvidenceState.SUPPORTED
        )
    else:
        selected = None
        reason = "no_valid_proposal"
        ordinal_state = EvidenceState.UNAVAILABLE
        ownership_state = EvidenceState.UNAVAILABLE
    return LaneGridSelection(
        lane_id=lane.domain.lane_id,
        proposal_classes=classes,
        selected_proposal=selected,
        work_by_component=tuple(work),
        separator_work_by_component=tuple(separator_work),
        grid_search_coverage_state=(
            EvidenceState.CONTRADICTED
            if omission_risk
            else EvidenceState.SUPPORTED
        ),
        ordinal_state=ordinal_state,
        ownership_state=ownership_state,
        selection_reason=reason,
    )
