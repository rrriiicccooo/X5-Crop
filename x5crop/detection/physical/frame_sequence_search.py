from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from functools import lru_cache
from math import ceil, floor

import numpy as np

from ...domain import (
    BoundarySide,
    EvidenceState,
    ObservationId,
    PixelInterval,
)
from ...image.content import ContentRegionObservation
from . import frame_sequence_common_width as width_resolution
from . import frame_sequence_measurements as measurement_facts
from .model import FrameBoundarySource

def _measured_frame_precedes(
    left: measurement_facts.MeasuredFrameConstraint,
    right: measurement_facts.MeasuredFrameConstraint,
) -> bool:
    return bool(
        right.leading.position.minimum > left.leading.position.maximum
        and right.trailing.position.minimum > left.trailing.position.maximum
    )

def measured_frame_option_rank(
    option: measurement_facts.MeasuredFrameConstraint,
) -> tuple[bool, int, int, int, float, float, float, float, float]:
    return (
        option.full_width_hypothesis_admissible,
        sum(
            edge.state == EvidenceState.SUPPORTED
            for edge in (option.leading, option.trailing)
        ),
        sum(
            edge.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            and measurement_facts.separator_edge_path_is_supported(edge)
            for edge in (option.leading, option.trailing)
        ),
        sum(
            edge.basis == FrameBoundarySource.GRAY_PATH_OBSERVATION
            for edge in (option.leading, option.trailing)
        ),
        option.leading.observation_quality + option.trailing.observation_quality,
        -(
            option.leading.position.maximum
            - option.leading.position.minimum
            + option.trailing.position.maximum
            - option.trailing.position.minimum
        ),
        -option.search_order_residual,
        -option.frame_width_hint_residual,
        -option.leading.position.midpoint,
    )

def _option_is_valid_at_frame_index(
    option: measurement_facts.MeasuredFrameConstraint,
    frame_index: int,
    count: int,
) -> bool:
    return bool(
        option.allowed_at(frame_index, count)
        and not (
            option.leading.external_side is not None
            and (
                frame_index != 1
                or option.leading.external_side != BoundarySide.LEADING
            )
        )
        and not (
            option.trailing.external_side is not None
            and (
                frame_index != count
                or option.trailing.external_side != BoundarySide.TRAILING
            )
        )
        and not (
            frame_index == 1
            and option.leading.separator is not None
            and option.leading.external_side != BoundarySide.LEADING
        )
        and not (
            frame_index == count
            and option.trailing.separator is not None
            and option.trailing.external_side != BoundarySide.TRAILING
        )
    )

def _separator_boundary_key(edge: measurement_facts.EdgeConstraint) -> ObservationId | None:
    return (
        None
        if edge.separator is None or edge.external_side is not None
        else edge.separator.provenance.observation_id
    )

def _separator_edges_pair_at_boundary(
    left: measurement_facts.MeasuredFrameConstraint,
    right: measurement_facts.MeasuredFrameConstraint,
) -> bool:
    left_key = _separator_boundary_key(left.trailing)
    right_key = _separator_boundary_key(right.leading)
    if left_key != right_key:
        return False
    if left_key is None:
        return True
    return bool(
        left.trailing.separator == right.leading.separator
        and left.trailing.separator_cross_axis
        == right.leading.separator_cross_axis
    )

def _separator_boundary_keys_are_compatible(
    left: measurement_facts.MeasuredFrameConstraint,
    right: measurement_facts.MeasuredFrameConstraint,
) -> bool:
    left_key = _separator_boundary_key(left.trailing)
    right_key = _separator_boundary_key(right.leading)
    return bool(
        left_key == right_key
        or left_key is None
        or right_key is None
    )

def _common_width_coordinate_span(
    option: measurement_facts.MeasuredFrameConstraint,
    frame_index: int,
    count: int,
    coordinates: tuple[float, ...],
) -> tuple[int, int] | None:
    holder_clipped_endpoint = bool(
        (frame_index == 1 and option.leading_holder_clip_supported)
        or (frame_index == count and option.trailing_holder_clip_supported)
    )
    measurement_uncertainty = (
        option.width_px.maximum - option.width_px.minimum
    )
    start = bisect_left(
        coordinates,
        (
            option.width_px.minimum
            if holder_clipped_endpoint
            else option.width_px.minimum - measurement_uncertainty
        ),
    )
    end = (
        len(coordinates)
        if holder_clipped_endpoint
        else bisect_right(
            coordinates,
            option.width_px.maximum + measurement_uncertainty,
        )
    )
    return None if start >= end else (start, end)

def _options_from_mask(
    mask: int,
    lookup: dict[int, measurement_facts.MeasuredFrameConstraint],
) -> tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...]:
    selected: list[tuple[int, measurement_facts.MeasuredFrameConstraint]] = []
    remaining = mask
    while remaining:
        bit = remaining & -remaining
        option_index = bit.bit_length() - 1
        selected.append((option_index, lookup[option_index]))
        remaining ^= bit
    return tuple(selected)

@dataclass(frozen=True)
class _CommonWidthOptionIndex:
    option_lookups: tuple[dict[int, measurement_facts.MeasuredFrameConstraint], ...]
    group_masks: tuple[tuple[int, ...], ...]

def _maximal_common_width_group_masks(
    groups: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    return tuple(
        group
        for index, group in enumerate(groups)
        if not any(
            index != other_index
            and all(mask & ~other_mask == 0 for mask, other_mask in zip(group, other))
            and any(mask != other_mask for mask, other_mask in zip(group, other))
            for other_index, other in enumerate(groups)
        )
    )

def _separator_pair_option_masks(
    option_lookups: tuple[dict[int, measurement_facts.MeasuredFrameConstraint], ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    pairs: list[tuple[tuple[int, int], ...]] = []
    for left_lookup, right_lookup in zip(
        option_lookups,
        option_lookups[1:],
    ):
        trailing_masks: dict[object, int] = {}
        leading_masks: dict[object, int] = {}
        for option_index, option in left_lookup.items():
            key = _separator_boundary_key(option.trailing)
            if key is not None:
                trailing_masks[key] = trailing_masks.get(key, 0) | (
                    1 << option_index
                )
        for option_index, option in right_lookup.items():
            key = _separator_boundary_key(option.leading)
            if key is not None:
                leading_masks[key] = leading_masks.get(key, 0) | (
                    1 << option_index
                )
        pairs.append(
            tuple(
                (trailing_masks[key], leading_masks[key])
                for key in trailing_masks.keys() & leading_masks.keys()
            )
        )
    return tuple(pairs)

def _separator_assignment_upper_bound(
    group_masks: tuple[int, ...],
    pair_masks: tuple[tuple[tuple[int, int], ...], ...],
) -> int:
    return sum(
        any(
            group_masks[boundary_index] & trailing_mask
            and group_masks[boundary_index + 1] & leading_mask
            for trailing_mask, leading_mask in boundary_pairs
        )
        for boundary_index, boundary_pairs in enumerate(pair_masks)
    )

def _common_width_option_index(
    options_by_frame: tuple[
        tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...],
        ...,
    ],
    count: int,
    width_hypotheses: tuple[PixelInterval, ...],
) -> _CommonWidthOptionIndex:
    option_lookups = tuple(dict(frame_options) for frame_options in options_by_frame)
    if count == 1:
        group_masks = (
            (
                sum(
                    1 << option_index
                    for option_index in option_lookups[0]
                ),
            ),
        ) if option_lookups and option_lookups[0] else ()
        return _CommonWidthOptionIndex(
            option_lookups,
            group_masks,
        )
    ordered_coordinates = tuple(
        dict.fromkeys(
            coordinate
            for width in width_hypotheses
            for coordinate in (
                width.minimum,
                width.midpoint,
                width.maximum,
            )
        )
    )
    if not ordered_coordinates:
        return _CommonWidthOptionIndex(option_lookups, ())
    coordinates = tuple(sorted(ordered_coordinates))
    additions: list[list[tuple[int, int]]] = [
        [] for _ in range(len(coordinates))
    ]
    removals: list[list[tuple[int, int]]] = [
        [] for _ in range(len(coordinates) + 1)
    ]
    for frame_index, frame_options in enumerate(options_by_frame, start=1):
        for option_index, option in frame_options:
            span = _common_width_coordinate_span(
                option,
                frame_index,
                count,
                coordinates,
            )
            if span is None:
                continue
            start, end = span
            additions[start].append((frame_index - 1, option_index))
            removals[end].append((frame_index - 1, option_index))

    active_masks = [0] * count
    membership_by_coordinate: dict[float, tuple[int, ...]] = {}
    for coordinate_index, coordinate in enumerate(coordinates):
        for frame_offset, option_index in removals[coordinate_index]:
            active_masks[frame_offset] &= ~(1 << option_index)
        for frame_offset, option_index in additions[coordinate_index]:
            active_masks[frame_offset] |= 1 << option_index
        membership_by_coordinate[coordinate] = tuple(active_masks)

    group_masks: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for coordinate in ordered_coordinates:
        key = membership_by_coordinate[coordinate]
        if any(mask == 0 for mask in key) or key in seen:
            continue
        seen.add(key)
        group_masks.append(key)
    return _CommonWidthOptionIndex(
        option_lookups,
        _maximal_common_width_group_masks(tuple(group_masks)),
    )

def _materialize_common_width_group(
    index: _CommonWidthOptionIndex,
    masks: tuple[int, ...],
) -> tuple[tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...], ...]:
    return tuple(
        _options_from_mask(mask, lookup)
        for mask, lookup in zip(masks, index.option_lookups, strict=True)
    )

def _content_coverage_interval(
    option: measurement_facts.MeasuredFrameConstraint,
    visible_content: ContentRegionObservation,
) -> tuple[int, int] | None:
    start = max(
        visible_content.region.left,
        int(floor(option.leading.position.minimum)),
    )
    end = min(
        visible_content.region.right,
        int(ceil(option.trailing.position.maximum)),
    )
    return None if end <= start else (start, end)

def _expanded_content_coverage_interval(
    option: measurement_facts.MeasuredFrameConstraint,
    visible_content: ContentRegionObservation,
) -> tuple[int, int] | None:
    interval = _content_coverage_interval(option, visible_content)
    if interval is None:
        return None
    start, end = interval
    uncertainty = visible_content.position_uncertainty_px
    return (
        max(visible_content.region.left, start - uncertainty),
        min(visible_content.region.right, end + uncertainty),
    )

def width_hypothesis_can_cover_reliable_content(
    hypothesis: width_resolution.DimensionPlacementHypothesis,
    count: int,
    visible_content: ContentRegionObservation,
) -> bool:
    if not visible_content.reliable_runs:
        return True
    uncertainty = visible_content.position_uncertainty_px
    required_extent = sum(
        max(
            0,
            end
            - start
            - measurement_facts.INTERVAL_ENDPOINT_COUNT * uncertainty,
        )
        for start, end in visible_content.reliable_runs
    )
    return hypothesis.width_px.maximum * count >= required_extent

@dataclass(frozen=True)
class SequenceGraphContext:
    coverages: tuple[tuple[int, int] | None, ...]
    run_starts: tuple[int, ...]
    run_ends: tuple[int, ...]
    first_mask: int
    last_mask: int
    allow_nominal_slot_sized_gap: bool
    edge_support_cache: dict[tuple[int, int], bool]

def sequence_graph_context(
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    visible_content: ContentRegionObservation,
    *,
    allow_nominal_slot_sized_gap: bool,
) -> SequenceGraphContext:
    coverages = tuple(
        _expanded_content_coverage_interval(option, visible_content)
        for option in ordered
    )
    runs = tuple(sorted(visible_content.reliable_runs))
    first_content_start = min((start for start, _ in runs), default=None)
    last_content_end = max((end for _, end in runs), default=None)
    first_mask = 0
    last_mask = 0
    for option_index, coverage in enumerate(coverages):
        bit = 1 << option_index
        if not runs or (
            coverage is not None
            and first_content_start is not None
            and first_content_start >= coverage[0]
        ):
            first_mask |= bit
        if not runs or (
            coverage is not None
            and last_content_end is not None
            and last_content_end <= coverage[1]
        ):
            last_mask |= bit
    return SequenceGraphContext(
        coverages=coverages,
        run_starts=tuple(start for start, _ in runs),
        run_ends=tuple(end for _, end in runs),
        first_mask=first_mask,
        last_mask=last_mask,
        allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
        edge_support_cache={},
    )

def sequence_graph_edge_is_interval_feasible(
    left_index: int,
    right_index: int,
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> bool:
    left = ordered[left_index]
    right = ordered[right_index]
    if not _separator_boundary_keys_are_compatible(left, right):
        return False
    if not _measured_frame_precedes(left, right):
        return False
    if not context.allow_nominal_slot_sized_gap:
        common_width = left.width_px.intersection(right.width_px)
        if (
            common_width is None
            or right.leading.position.minus(left.trailing.position).maximum
            >= common_width.minimum
        ):
            return False
    left_coverage = context.coverages[left_index]
    right_coverage = context.coverages[right_index]
    if left_coverage is None or right_coverage is None:
        return not context.run_starts
    gap_start = left_coverage[1]
    gap_end = right_coverage[0]
    if gap_end <= gap_start:
        return True
    run_index = bisect_right(context.run_ends, gap_start)
    return bool(
        run_index >= len(context.run_starts)
        or context.run_starts[run_index] >= gap_end
    )

def _cached_sequence_graph_edge_supported(
    left_index: int,
    right_index: int,
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> bool:
    key = (left_index, right_index)
    supported = context.edge_support_cache.get(key)
    if supported is None:
        supported = sequence_graph_edge_is_interval_feasible(
            left_index,
            right_index,
            ordered,
            context,
        )
        context.edge_support_cache[key] = supported
    return supported

def _fenwick_update(
    tree: list[tuple[float, int, int] | None],
    index: int,
    value: tuple[float, int, int],
) -> None:
    current = index + 1
    while current < len(tree):
        existing = tree[current]
        if existing is None or value > existing:
            tree[current] = value
        current += current & -current

def _fenwick_query(
    tree: list[tuple[float, int, int] | None],
    count: int,
) -> tuple[float, int, int] | None:
    best: tuple[float, int, int] | None = None
    current = count
    while current > 0:
        candidate = tree[current]
        if candidate is not None and (best is None or candidate > best):
            best = candidate
        current -= current & -current
    return best

def reachable_predecessors_for_boundary(
    previous_indexes: tuple[int, ...],
    current_indexes: tuple[int, ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> dict[int, int]:
    eligible_previous = tuple(
        index
        for index in previous_indexes
        if not context.run_starts or context.coverages[index] is not None
    )
    if not eligible_previous:
        return {}
    trailing_coordinates = tuple(
        sorted(
            {
                ordered[index].trailing.position.maximum
                for index in eligible_previous
            }
        )
    )
    tree: list[tuple[float, int, int] | None] = [
        None
    ] * (len(trailing_coordinates) + 1)
    sorted_previous = tuple(
        sorted(
            eligible_previous,
            key=lambda index: (
                ordered[index].leading.position.maximum,
                ordered[index].trailing.position.maximum,
                index,
            ),
        )
    )
    cursor = 0
    reachable: dict[int, int] = {}
    for current_index in sorted(
        current_indexes,
        key=lambda index: (
            ordered[index].leading.position.minimum,
            ordered[index].trailing.position.minimum,
            index,
        ),
    ):
        current = ordered[current_index]
        while (
            cursor < len(sorted_previous)
            and ordered[sorted_previous[cursor]].leading.position.maximum
            < current.leading.position.minimum
        ):
            previous_index = sorted_previous[cursor]
            coverage = context.coverages[previous_index]
            coverage_end = (
                float(ordered[previous_index].trailing.position.maximum)
                if coverage is None
                else float(coverage[1])
            )
            trailing_rank = bisect_left(
                trailing_coordinates,
                ordered[previous_index].trailing.position.maximum,
            )
            _fenwick_update(
                tree,
                trailing_rank,
                (coverage_end, -previous_index, previous_index),
            )
            cursor += 1
        candidate = _fenwick_query(
            tree,
            bisect_left(
                trailing_coordinates,
                current.trailing.position.minimum,
            ),
        )
        if candidate is None:
            continue
        previous_index = candidate[2]
        if _cached_sequence_graph_edge_supported(
            previous_index,
            current_index,
            ordered,
            context,
        ):
            reachable[current_index] = previous_index
            continue
        fallback_indexes = sorted(
            (
                index
                for index in eligible_previous
                if index != previous_index
                and ordered[index].leading.position.maximum
                < current.leading.position.minimum
                and ordered[index].trailing.position.maximum
                < current.trailing.position.minimum
            ),
            key=lambda index: (
                (
                    float(ordered[index].trailing.position.maximum)
                    if context.coverages[index] is None
                    else float(context.coverages[index][1])
                ),
                -index,
            ),
            reverse=True,
        )
        fallback_index = next(
            (
                index
                for index in fallback_indexes
                if _cached_sequence_graph_edge_supported(
                    index,
                    current_index,
                    ordered,
                    context,
                )
            ),
            None,
        )
        if fallback_index is not None:
            reachable[current_index] = fallback_index
    return reachable

def _reachable_predecessors(
    previous_indexes: tuple[int, ...],
    current_indexes: tuple[int, ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> dict[int, int]:
    previous_by_separator: dict[ObservationId | None, list[int]] = {}
    current_by_separator: dict[ObservationId | None, list[int]] = {}
    for index in previous_indexes:
        previous_by_separator.setdefault(
            _separator_boundary_key(ordered[index].trailing),
            [],
        ).append(index)
    for index in current_indexes:
        current_by_separator.setdefault(
            _separator_boundary_key(ordered[index].leading),
            [],
        ).append(index)
    reachable: dict[int, int] = {}
    for separator_key in sorted(
        previous_by_separator.keys() & current_by_separator.keys(),
        key=lambda item: "" if item is None else str(item),
    ):
        reachable.update(
            reachable_predecessors_for_boundary(
                tuple(previous_by_separator[separator_key]),
                tuple(current_by_separator[separator_key]),
                ordered,
                context,
            )
        )
    unassigned_previous = tuple(previous_by_separator.get(None, ()))
    if unassigned_previous:
        for separator_key, indexes in current_by_separator.items():
            if separator_key is None:
                continue
            reachable.update(
                reachable_predecessors_for_boundary(
                    unassigned_previous,
                    tuple(indexes),
                    ordered,
                    context,
                )
            )
    unassigned_current = tuple(current_by_separator.get(None, ()))
    assigned_previous = tuple(
        index
        for separator_key, indexes in previous_by_separator.items()
        if separator_key is not None
        for index in indexes
    )
    if assigned_previous and unassigned_current:
        reachable.update(
            reachable_predecessors_for_boundary(
                assigned_previous,
                unassigned_current,
                ordered,
                context,
            )
        )
    return reachable

def _reachable_successors_for_boundary(
    current_indexes: tuple[int, ...],
    following_indexes: tuple[int, ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> dict[int, int]:
    eligible_following = tuple(
        index
        for index in following_indexes
        if not context.run_starts or context.coverages[index] is not None
    )
    if not eligible_following:
        return {}
    reversed_trailing_coordinates = tuple(
        sorted(
            {
                -ordered[index].trailing.position.minimum
                for index in eligible_following
            }
        )
    )
    tree: list[tuple[float, int, int] | None] = [
        None
    ] * (len(reversed_trailing_coordinates) + 1)
    sorted_following = tuple(
        sorted(
            eligible_following,
            key=lambda index: (
                ordered[index].leading.position.minimum,
                ordered[index].trailing.position.minimum,
                -index,
            ),
            reverse=True,
        )
    )
    cursor = 0
    reachable: dict[int, int] = {}
    for current_index in sorted(
        current_indexes,
        key=lambda index: (
            ordered[index].leading.position.maximum,
            ordered[index].trailing.position.maximum,
            -index,
        ),
        reverse=True,
    ):
        current = ordered[current_index]
        while (
            cursor < len(sorted_following)
            and ordered[sorted_following[cursor]].leading.position.minimum
            > current.leading.position.maximum
        ):
            following_index = sorted_following[cursor]
            coverage = context.coverages[following_index]
            coverage_start = (
                float(ordered[following_index].leading.position.minimum)
                if coverage is None
                else float(coverage[0])
            )
            trailing_rank = bisect_left(
                reversed_trailing_coordinates,
                -ordered[following_index].trailing.position.minimum,
            )
            _fenwick_update(
                tree,
                trailing_rank,
                (-coverage_start, -following_index, following_index),
            )
            cursor += 1
        candidate = _fenwick_query(
            tree,
            bisect_left(
                reversed_trailing_coordinates,
                -current.trailing.position.maximum,
            ),
        )
        if candidate is None:
            continue
        following_index = candidate[2]
        if _cached_sequence_graph_edge_supported(
            current_index,
            following_index,
            ordered,
            context,
        ):
            reachable[current_index] = following_index
            continue
        fallback_indexes = sorted(
            (
                index
                for index in eligible_following
                if index != following_index
                and ordered[index].leading.position.minimum
                > current.leading.position.maximum
                and ordered[index].trailing.position.minimum
                > current.trailing.position.maximum
            ),
            key=lambda index: (
                -(
                    float(ordered[index].leading.position.minimum)
                    if context.coverages[index] is None
                    else float(context.coverages[index][0])
                ),
                -index,
            ),
            reverse=True,
        )
        fallback_index = next(
            (
                index
                for index in fallback_indexes
                if _cached_sequence_graph_edge_supported(
                    current_index,
                    index,
                    ordered,
                    context,
                )
            ),
            None,
        )
        if fallback_index is not None:
            reachable[current_index] = fallback_index
    return reachable

def _reachable_successors(
    current_indexes: tuple[int, ...],
    following_indexes: tuple[int, ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> dict[int, int]:
    current_by_separator: dict[ObservationId | None, list[int]] = {}
    following_by_separator: dict[ObservationId | None, list[int]] = {}
    for index in current_indexes:
        current_by_separator.setdefault(
            _separator_boundary_key(ordered[index].trailing),
            [],
        ).append(index)
    for index in following_indexes:
        following_by_separator.setdefault(
            _separator_boundary_key(ordered[index].leading),
            [],
        ).append(index)
    reachable: dict[int, int] = {}
    for separator_key in sorted(
        current_by_separator.keys() & following_by_separator.keys(),
        key=lambda item: "" if item is None else str(item),
    ):
        reachable.update(
            _reachable_successors_for_boundary(
                tuple(current_by_separator[separator_key]),
                tuple(following_by_separator[separator_key]),
                ordered,
                context,
            )
        )
    unassigned_current = tuple(current_by_separator.get(None, ()))
    assigned_following = tuple(
        index
        for separator_key, indexes in following_by_separator.items()
        if separator_key is not None
        for index in indexes
    )
    if unassigned_current and assigned_following:
        reachable.update(
            _reachable_successors_for_boundary(
                unassigned_current,
                assigned_following,
                ordered,
                context,
            )
        )
    unassigned_following = tuple(following_by_separator.get(None, ()))
    if unassigned_following:
        for separator_key, indexes in current_by_separator.items():
            if separator_key is None:
                continue
            reachable.update(
                _reachable_successors_for_boundary(
                    tuple(indexes),
                    unassigned_following,
                    ordered,
                    context,
                )
            )
    return reachable

def _graph_sequence_for_target(
    target_layer: int,
    target_index: int,
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    selected = [target_index]
    current = target_index
    for layer_index in range(target_layer, 0, -1):
        predecessor = forward[layer_index][current]
        if predecessor is None:
            raise ValueError("feasible sequence node lacks a leading path")
        selected.insert(0, predecessor)
        current = predecessor
    current = target_index
    for layer_index in range(target_layer, len(forward) - 1):
        successor = backward[layer_index][current]
        if successor is None:
            raise ValueError("feasible sequence node lacks a trailing path")
        selected.append(successor)
        current = successor
    return tuple(ordered[index] for index in selected)

@dataclass(frozen=True)
class GraphPathState:
    observation_candidate_count: int
    supported_separator_count: int
    internal_measurement_quality: float
    uncorroborated_overlap_extent_px: float
    frame_sized_unexplained_gap_count: int
    unexplained_spacing_extent_px: float
    uncorroborated_contact_count: int
    frame_width_hint_residual: float
    boundary_uncertainty_px: float
    external_leading_quality: float
    coordinate_key: tuple[float, ...]
    predecessor: int | None

@dataclass(frozen=True)
class GraphLayerStateIndex:
    option_indexes: tuple[int, ...]
    leading_maxima: np.ndarray
    trailing_minima: np.ndarray
    trailing_maxima: np.ndarray
    frame_width_minima: np.ndarray
    frame_width_maxima: np.ndarray
    separator_offsets: dict[ObservationId | None, np.ndarray]
    coverage_ends: np.ndarray
    observation_candidate_counts: np.ndarray
    supported_separator_counts: np.ndarray
    internal_measurement_qualities: np.ndarray
    uncorroborated_overlap_extents: np.ndarray
    frame_sized_unexplained_gap_counts: np.ndarray
    unexplained_spacing_extents: np.ndarray
    uncorroborated_contact_counts: np.ndarray
    frame_width_hint_residuals: np.ndarray
    boundary_uncertainties: np.ndarray
    external_leading_qualities: np.ndarray
    coordinate_keys: tuple[tuple[float, ...], ...]

def graph_layer_state_index(
    states: dict[int, GraphPathState],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> GraphLayerStateIndex:
    option_indexes = tuple(states)
    separator_offsets: dict[ObservationId | None, list[int]] = {}
    for offset, option_index in enumerate(option_indexes):
        separator_offsets.setdefault(
            _separator_boundary_key(ordered[option_index].trailing),
            [],
        ).append(offset)

    def state_array(name: str, dtype: np.dtype) -> np.ndarray:
        return np.fromiter(
            (getattr(states[index], name) for index in option_indexes),
            dtype=dtype,
            count=len(option_indexes),
        )

    return GraphLayerStateIndex(
        option_indexes=option_indexes,
        leading_maxima=np.fromiter(
            (ordered[index].leading.position.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        trailing_minima=np.fromiter(
            (ordered[index].trailing.position.minimum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        trailing_maxima=np.fromiter(
            (ordered[index].trailing.position.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        frame_width_minima=np.fromiter(
            (ordered[index].width_px.minimum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        frame_width_maxima=np.fromiter(
            (ordered[index].width_px.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        separator_offsets={
            key: np.asarray(offsets, dtype=np.int64)
            for key, offsets in separator_offsets.items()
        },
        coverage_ends=np.asarray(
            [
                (
                    np.nan
                    if context.coverages[index] is None
                    else context.coverages[index][1]
                )
                for index in option_indexes
            ],
            dtype=np.float64,
        ),
        observation_candidate_counts=state_array(
            "observation_candidate_count",
            np.int64,
        ),
        supported_separator_counts=state_array(
            "supported_separator_count",
            np.int64,
        ),
        internal_measurement_qualities=state_array(
            "internal_measurement_quality",
            np.float64,
        ),
        uncorroborated_overlap_extents=state_array(
            "uncorroborated_overlap_extent_px",
            np.float64,
        ),
        frame_sized_unexplained_gap_counts=state_array(
            "frame_sized_unexplained_gap_count",
            np.int64,
        ),
        unexplained_spacing_extents=state_array(
            "unexplained_spacing_extent_px",
            np.float64,
        ),
        uncorroborated_contact_counts=state_array(
            "uncorroborated_contact_count",
            np.int64,
        ),
        frame_width_hint_residuals=state_array(
            "frame_width_hint_residual",
            np.float64,
        ),
        boundary_uncertainties=state_array(
            "boundary_uncertainty_px",
            np.float64,
        ),
        external_leading_qualities=state_array(
            "external_leading_quality",
            np.float64,
        ),
        coordinate_keys=tuple(states[index].coordinate_key for index in option_indexes),
    )

@dataclass(frozen=True)
class SequenceGraphEvaluations:
    states: frozenset[tuple[int, int]]
    edge_queries: frozenset[tuple[int, int]]
    witness_transitions: frozenset[tuple[int, int, int]]
    independent_edge_witnesses: frozenset[
        tuple[int, ObservationId]
    ] = frozenset()

    def incremental_cost(self, previous: "SequenceGraphEvaluations") -> int:
        return (
            len(self.states - previous.states)
            + len(self.edge_queries - previous.edge_queries)
            + len(
                self.witness_transitions
                - previous.witness_transitions
            )
            + len(
                self.independent_edge_witnesses
                - previous.independent_edge_witnesses
            )
        )

    def merged(
        self,
        other: "SequenceGraphEvaluations",
    ) -> "SequenceGraphEvaluations":
        return SequenceGraphEvaluations(
            self.states | other.states,
            self.edge_queries | other.edge_queries,
            self.witness_transitions | other.witness_transitions,
            self.independent_edge_witnesses
            | other.independent_edge_witnesses,
        )

def _one_sided_supported_separator_edge_ids(
    edges: tuple[measurement_facts.EdgeConstraint, ...],
) -> tuple[ObservationId, ...]:
    return tuple(
        dict.fromkeys(
            edge.provenance.observation_id
            for edge in edges
            if measurement_facts.separator_edge_path_is_supported(edge)
            and edge.separator_cross_axis is not None
            and sum(
                edge.separator_cross_axis.edge_path(side).state
                == EvidenceState.SUPPORTED
                for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
            )
            == 1
        )
    )

def _sequence_graph_evaluations(
    feasible: tuple[tuple[int, ...], ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> SequenceGraphEvaluations:
    witness_transitions = (
        frozenset(
            (layer_index, left_index, right_index)
            for layer_index, (left_indexes, right_indexes) in enumerate(
                zip(feasible, feasible[1:])
            )
            for left_index in left_indexes
            for right_index in right_indexes
            if _cached_sequence_graph_edge_supported(
                left_index,
                right_index,
                ordered,
                context,
            )
        )
        if context.allow_nominal_slot_sized_gap
        else frozenset()
    )
    last_layer = len(feasible) - 1
    independent_edge_witnesses = (
        frozenset(
            (layer_index, edge_id)
            for layer_index, option_indexes in enumerate(feasible)
            for option_index in option_indexes
            for edge_id in _one_sided_supported_separator_edge_ids(
                tuple(
                    edge
                    for edge in (
                        (
                            ordered[option_index].leading
                            if layer_index > 0
                            else None
                        ),
                        (
                            ordered[option_index].trailing
                            if layer_index < last_layer
                            else None
                        ),
                    )
                    if edge is not None
                )
            )
        )
        if ordered
        else frozenset()
    )
    return SequenceGraphEvaluations(
        states=frozenset(
            (layer_index, option_index)
            for layer_index, indexes in enumerate(feasible)
            for option_index in indexes
        ),
        edge_queries=frozenset(
            key
            for key, supported in context.edge_support_cache.items()
            if supported
        ),
        witness_transitions=witness_transitions,
        independent_edge_witnesses=independent_edge_witnesses,
    )


def _constraint_uncertainty(option: measurement_facts.MeasuredFrameConstraint) -> float:
    return sum(
        edge.position.maximum - edge.position.minimum
        for edge in (option.leading, option.trailing)
    )

def _observation_candidate_count(option: measurement_facts.MeasuredFrameConstraint) -> int:
    return len(
        {
            edge.provenance.observation_id
            for edge in (option.leading, option.trailing)
            if edge.basis
            in {
                FrameBoundarySource.GRAY_PATH_OBSERVATION,
                FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            }
        }
    )

def best_graph_predecessor(
    current_index: int,
    previous: GraphLayerStateIndex,
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> tuple[int, int, int, float, float, int, float, int] | None:
    current = ordered[current_index]
    separator_key = _separator_boundary_key(current.leading)
    previous_indexes = previous.option_indexes
    if not previous_indexes:
        return None
    valid = np.logical_and(
        previous.leading_maxima < current.leading.position.minimum,
        previous.trailing_maxima < current.trailing.position.minimum,
    )
    common_width_minima = np.maximum(
        previous.frame_width_minima,
        current.width_px.minimum,
    )
    common_width_maxima = np.minimum(
        previous.frame_width_maxima,
        current.width_px.maximum,
    )
    common_width_available = common_width_maxima >= common_width_minima
    if separator_key is not None:
        separator_compatible = np.zeros(len(previous_indexes), dtype=bool)
        for key in (None, separator_key):
            offsets = previous.separator_offsets.get(key)
            if offsets is not None:
                separator_compatible[offsets] = True
        valid &= separator_compatible
    if not context.allow_nominal_slot_sized_gap:
        valid &= common_width_available
        valid &= (
            current.leading.position.maximum - previous.trailing_minima
            < common_width_minima
        )
    if context.run_starts:
        current_coverage = context.coverages[current_index]
        if current_coverage is None:
            return None
        previous_coverage_end = previous.coverage_ends
        valid &= np.isfinite(previous_coverage_end)
        gap_end = float(current_coverage[0])
        uncovered = gap_end > previous_coverage_end
        if np.any(uncovered):
            run_ends = np.asarray(context.run_ends, dtype=np.float64)
            run_starts = np.asarray(context.run_starts, dtype=np.float64)
            run_indexes = np.searchsorted(
                run_ends,
                previous_coverage_end,
                side="right",
            )
            next_run_start = np.full(len(previous_indexes), np.inf, dtype=np.float64)
            has_following_run = run_indexes < len(run_starts)
            next_run_start[has_following_run] = run_starts[
                run_indexes[has_following_run]
            ]
            valid &= np.logical_or(~uncovered, next_run_start >= gap_end)
    candidate_offsets = np.flatnonzero(valid)
    if not len(candidate_offsets):
        return None

    separator_supported = np.zeros(len(previous_indexes), dtype=np.int64)
    observation_increment = _observation_candidate_count(current)
    internal_quality = np.zeros(len(previous_indexes), dtype=np.float64)
    unexplained_spacing = np.maximum(
        0.0,
        current.leading.position.minimum - previous.trailing_maxima,
    )
    frame_sized_unexplained_gap = np.zeros(len(previous_indexes), dtype=np.int64)
    uncorroborated_overlap = np.maximum(
        0.0,
        previous.trailing_minima - current.leading.position.maximum,
    )
    uncorroborated_contact = np.logical_and(
        previous.trailing_minima == current.leading.position.minimum,
        previous.trailing_maxima == current.leading.position.maximum,
    ).astype(np.int64)
    if separator_key is not None:
        for offset in candidate_offsets:
            previous_option = ordered[previous_indexes[int(offset)]]
            if (
                common_width_available[offset]
                and _separator_edges_pair_at_boundary(previous_option, current)
                and previous_option.trailing.separator is not None
                and previous_option.trailing.separator_cross_axis is not None
                and previous_option.trailing.separator_cross_axis
                .complete_separator_supported
                and previous_option.trailing.separator.width_px.minimum > 0.0
                and previous_option.trailing.separator.width_px.maximum
                < common_width_minima[offset]
            ):
                separator_supported[offset] = 1
                internal_quality[offset] = (
                    previous_option.trailing.observation_quality
                    + current.leading.observation_quality
                )
                unexplained_spacing[offset] = 0.0
                uncorroborated_overlap[offset] = 0.0
                uncorroborated_contact[offset] = 0
    frame_sized_unexplained_gap = np.logical_and(
        common_width_available,
        unexplained_spacing >= common_width_minima,
    ).astype(np.int64)
    frame_sized_unexplained_gap[separator_supported.astype(bool)] = 0
    observation_counts = (
        previous.observation_candidate_counts + observation_increment
    )
    supported_counts = previous.supported_separator_counts + separator_supported
    qualities = previous.internal_measurement_qualities + internal_quality
    overlaps = previous.uncorroborated_overlap_extents + uncorroborated_overlap
    frame_sized_gaps = (
        previous.frame_sized_unexplained_gap_counts
        + frame_sized_unexplained_gap
    )
    unexplained = previous.unexplained_spacing_extents + unexplained_spacing
    contacts = previous.uncorroborated_contact_counts + uncorroborated_contact
    width_hint_residuals = previous.frame_width_hint_residuals
    uncertainties = previous.boundary_uncertainties
    leading_qualities = previous.external_leading_qualities

    remaining = candidate_offsets
    minimum_overlap = np.min(overlaps[remaining])
    remaining = remaining[overlaps[remaining] == minimum_overlap]
    minimum_frame_sized_gaps = np.min(frame_sized_gaps[remaining])
    remaining = remaining[
        frame_sized_gaps[remaining] == minimum_frame_sized_gaps
    ]
    maximum_count = np.max(supported_counts[remaining])
    remaining = remaining[supported_counts[remaining] == maximum_count]
    maximum_quality = np.max(qualities[remaining])
    remaining = remaining[qualities[remaining] == maximum_quality]
    minimum_contacts = np.min(contacts[remaining])
    remaining = remaining[contacts[remaining] == minimum_contacts]
    minimum_unexplained = np.min(unexplained[remaining])
    remaining = remaining[unexplained[remaining] == minimum_unexplained]
    maximum_leading_quality = np.max(leading_qualities[remaining])
    remaining = remaining[
        leading_qualities[remaining] == maximum_leading_quality
    ]
    maximum_observation_count = np.max(observation_counts[remaining])
    remaining = remaining[
        observation_counts[remaining] == maximum_observation_count
    ]
    minimum_uncertainty = np.min(uncertainties[remaining])
    remaining = remaining[uncertainties[remaining] == minimum_uncertainty]
    minimum_width_hint_residual = np.min(width_hint_residuals[remaining])
    remaining = remaining[
        width_hint_residuals[remaining] == minimum_width_hint_residual
    ]
    best_offset = max(
        (int(offset) for offset in remaining),
        key=lambda offset: previous.coordinate_keys[offset],
    )
    return (
        previous_indexes[best_offset],
        observation_increment,
        int(separator_supported[best_offset]),
        float(internal_quality[best_offset]),
        float(uncorroborated_overlap[best_offset]),
        int(frame_sized_unexplained_gap[best_offset]),
        float(unexplained_spacing[best_offset]),
        int(uncorroborated_contact[best_offset]),
    )

def sequence_graph_best_path(
    grouped_options: tuple[
        tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...] | None:
    states: list[dict[int, GraphPathState]] = [
        {
            option_index: GraphPathState(
                observation_candidate_count=_observation_candidate_count(option),
                supported_separator_count=0,
                internal_measurement_quality=0.0,
                uncorroborated_overlap_extent_px=0.0,
                frame_sized_unexplained_gap_count=0,
                unexplained_spacing_extent_px=0.0,
                uncorroborated_contact_count=0,
                frame_width_hint_residual=option.frame_width_hint_residual,
                boundary_uncertainty_px=_constraint_uncertainty(option),
                external_leading_quality=option.leading.measurement_quality,
                coordinate_key=(
                    -option.leading.position.midpoint,
                    -option.trailing.position.midpoint,
                ),
                predecessor=None,
            )
            for option_index, option in grouped_options[0]
            if context.first_mask & (1 << option_index)
        }
    ]
    for frame_options in grouped_options[1:]:
        previous_index = graph_layer_state_index(
            states[-1],
            ordered,
            context,
        )
        current_states: dict[int, GraphPathState] = {}
        for option_index, option in frame_options:
            predecessor = best_graph_predecessor(
                option_index,
                previous_index,
                ordered,
                context,
            )
            if predecessor is None:
                continue
            (
                predecessor_index,
                observation_increment,
                separator_increment,
                quality_increment,
                overlap_increment,
                frame_sized_gap_increment,
                unexplained_increment,
                contact_increment,
            ) = predecessor
            previous = states[-1][predecessor_index]
            current_states[option_index] = GraphPathState(
                observation_candidate_count=(
                    previous.observation_candidate_count
                    + observation_increment
                ),
                supported_separator_count=(
                    previous.supported_separator_count + separator_increment
                ),
                internal_measurement_quality=(
                    previous.internal_measurement_quality + quality_increment
                ),
                uncorroborated_overlap_extent_px=(
                    previous.uncorroborated_overlap_extent_px
                    + overlap_increment
                ),
                frame_sized_unexplained_gap_count=(
                    previous.frame_sized_unexplained_gap_count
                    + frame_sized_gap_increment
                ),
                unexplained_spacing_extent_px=(
                    previous.unexplained_spacing_extent_px
                    + unexplained_increment
                ),
                uncorroborated_contact_count=(
                    previous.uncorroborated_contact_count + contact_increment
                ),
                frame_width_hint_residual=(
                    previous.frame_width_hint_residual
                    + option.frame_width_hint_residual
                ),
                boundary_uncertainty_px=(
                    previous.boundary_uncertainty_px
                    + _constraint_uncertainty(option)
                ),
                external_leading_quality=previous.external_leading_quality,
                coordinate_key=(
                    *previous.coordinate_key,
                    -option.leading.position.midpoint,
                    -option.trailing.position.midpoint,
                ),
                predecessor=predecessor_index,
            )
        if not current_states:
            return None
        states.append(current_states)
    terminal_indexes = tuple(
        option_index
        for option_index in states[-1]
        if context.last_mask & (1 << option_index)
    )
    if not terminal_indexes:
        return None
    terminal_index = max(
        terminal_indexes,
        key=lambda option_index: (
            -states[-1][option_index].uncorroborated_overlap_extent_px,
            -states[-1][option_index].frame_sized_unexplained_gap_count,
            states[-1][option_index].supported_separator_count,
            states[-1][option_index].internal_measurement_quality,
            -states[-1][option_index].uncorroborated_contact_count,
            -states[-1][option_index].unexplained_spacing_extent_px,
            states[-1][option_index].external_leading_quality
            + ordered[option_index].trailing.measurement_quality,
            states[-1][option_index].observation_candidate_count,
            -states[-1][option_index].boundary_uncertainty_px,
            -states[-1][option_index].frame_width_hint_residual,
            states[-1][option_index].coordinate_key,
        ),
    )
    selected = [terminal_index]
    for layer_index in reversed(range(1, len(states))):
        predecessor = states[layer_index][selected[-1]].predecessor
        if predecessor is None:
            raise ValueError("graph path state lacks its predecessor")
        selected.append(predecessor)
    selected.reverse()
    sequence = tuple(ordered[index] for index in selected)
    return (
        sequence
        if width_resolution.measured_constraint_common_width(sequence, len(sequence)) is not None
        else None
    )

def _sequence_boundary_has_supported_separator(
    left: measurement_facts.MeasuredFrameConstraint,
    right: measurement_facts.MeasuredFrameConstraint,
) -> bool:
    common_width = left.width_px.intersection(right.width_px)
    return bool(
        common_width is not None
        and _separator_edges_pair_at_boundary(left, right)
        and left.trailing.separator is not None
        and left.trailing.separator_cross_axis is not None
        and left.trailing.separator_cross_axis.complete_separator_supported
        and left.trailing.separator.width_px.minimum > 0.0
        and left.trailing.separator.width_px.maximum < common_width.minimum
    )

def _sequence_supported_separator_count(
    sequence: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> int:
    return sum(
        _sequence_boundary_has_supported_separator(left, right)
        for left, right in zip(sequence, sequence[1:])
    )

def _graph_sequence_rank(
    sequence: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[object, ...]:
    supported_separator_count = 0
    internal_measurement_quality = 0.0
    uncorroborated_overlap_extent_px = 0.0
    frame_sized_unexplained_gap_count = 0
    unexplained_spacing_extent_px = 0.0
    uncorroborated_contact_count = 0
    for left, right in zip(sequence, sequence[1:]):
        common_width = left.width_px.intersection(right.width_px)
        separator_supported = _sequence_boundary_has_supported_separator(
            left,
            right,
        )
        if separator_supported:
            supported_separator_count += 1
            internal_measurement_quality += (
                left.trailing.observation_quality
                + right.leading.observation_quality
            )
            continue
        uncorroborated_overlap_extent_px += max(
            0.0,
            left.trailing.position.minimum - right.leading.position.maximum,
        )
        unexplained_spacing_extent_px += max(
            0.0,
            right.leading.position.minimum - left.trailing.position.maximum,
        )
        if (
            common_width is not None
            and right.leading.position.minimum - left.trailing.position.maximum
            >= common_width.minimum
        ):
            frame_sized_unexplained_gap_count += 1
        uncorroborated_contact_count += int(
            left.trailing.position == right.leading.position
        )
    return (
        -uncorroborated_overlap_extent_px,
        -frame_sized_unexplained_gap_count,
        supported_separator_count,
        internal_measurement_quality,
        -uncorroborated_contact_count,
        -unexplained_spacing_extent_px,
        sequence[0].leading.measurement_quality
        + sequence[-1].trailing.measurement_quality,
        sum(_observation_candidate_count(option) for option in sequence),
        -sum(_constraint_uncertainty(option) for option in sequence),
        -sum(option.frame_width_hint_residual for option in sequence),
        tuple(
            coordinate
            for option in sequence
            for coordinate in (
                -option.leading.position.midpoint,
                -option.trailing.position.midpoint,
            )
        ),
    )

def _contact_neutral_sequence_rank(
    sequence: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[object, ...]:
    rank = _graph_sequence_rank(sequence)
    return (*rank[:4], *rank[5:])

@dataclass(frozen=True)
class SequenceGraphFeasibility:
    forward: tuple[dict[int, int | None], ...]
    backward: tuple[dict[int, int | None], ...]
    feasible: tuple[tuple[int, ...], ...]
    evaluations: SequenceGraphEvaluations

def _sequence_graph_feasibility(
    grouped_options: tuple[
        tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> SequenceGraphFeasibility | None:
    forward: list[dict[int, int | None]] = [
        {
            option_index: None
            for option_index, _ in grouped_options[0]
            if context.first_mask & (1 << option_index)
        }
    ]
    for frame_options in grouped_options[1:]:
        forward.append(
            _reachable_predecessors(
                tuple(forward[-1]),
                tuple(option_index for option_index, _ in frame_options),
                ordered,
                context,
            )
        )

    backward: list[dict[int, int | None]] = [
        {} for _ in grouped_options
    ]
    backward[-1] = {
        option_index: None
        for option_index, _ in grouped_options[-1]
        if context.last_mask & (1 << option_index)
    }
    for layer_index in reversed(range(len(grouped_options) - 1)):
        backward[layer_index] = _reachable_successors(
            tuple(option_index for option_index, _ in grouped_options[layer_index]),
            tuple(backward[layer_index + 1]),
            ordered,
            context,
        )

    feasible = tuple(
        tuple(
            option_index
            for option_index, _ in frame_options
            if option_index in forward[layer_index]
            and option_index in backward[layer_index]
        )
        for layer_index, frame_options in enumerate(grouped_options)
    )
    if any(not indexes for indexes in feasible):
        return None
    return SequenceGraphFeasibility(
        tuple(forward),
        tuple(backward),
        feasible,
        _sequence_graph_evaluations(
            feasible,
            ordered,
            context,
        ),
    )

def _graph_sequence_for_transition(
    layer_index: int,
    left_index: int,
    right_index: int,
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    selected = [left_index]
    current = left_index
    for prefix_layer in range(layer_index, 0, -1):
        predecessor = forward[prefix_layer][current]
        if predecessor is None:
            raise ValueError("feasible contact transition lacks a leading path")
        selected.insert(0, predecessor)
        current = predecessor
    selected.append(right_index)
    current = right_index
    for suffix_layer in range(layer_index + 1, len(backward) - 1):
        successor = backward[suffix_layer][current]
        if successor is None:
            raise ValueError("feasible contact transition lacks a trailing path")
        selected.append(successor)
        current = successor
    return tuple(ordered[index] for index in selected)

def _contact_transition_witnesses(
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[tuple[measurement_facts.MeasuredFrameConstraint, ...], ...]:
    best: tuple[measurement_facts.MeasuredFrameConstraint, ...] | None = None
    transitions = tuple(
        dict.fromkeys(
            (
                layer_index,
                left_index,
                right_index,
            )
            for layer_index in range(len(forward) - 1)
            for left_index, right_index in backward[layer_index].items()
            if right_index is not None
            and left_index in forward[layer_index]
            and right_index in forward[layer_index + 1]
            and right_index in backward[layer_index + 1]
            and ordered[left_index].trailing.position
            == ordered[right_index].leading.position
        )
    )
    for layer_index, left_index, right_index in transitions:
        sequence = _graph_sequence_for_transition(
            layer_index,
            left_index,
            right_index,
            forward,
            backward,
            ordered,
        )
        if (
            best is None
            or _contact_neutral_sequence_rank(sequence)
            > _contact_neutral_sequence_rank(best)
        ):
            best = sequence
    return () if best is None else (best,)

def _physical_sequences_through_transitions(
    transitions: frozenset[tuple[int, int, int]],
    feasible: tuple[tuple[int, ...], ...],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> dict[
    tuple[int, int, int],
    tuple[measurement_facts.MeasuredFrameConstraint, ...],
]:
    @lru_cache(maxsize=None)
    def best_prefix(
        layer_index: int,
        option_index: int,
    ) -> tuple[measurement_facts.MeasuredFrameConstraint, ...] | None:
        option = ordered[option_index]
        if layer_index == 0:
            return (option,)
        candidates = tuple(
            (*prefix, option)
            for previous_index in feasible[layer_index - 1]
            if context.edge_support_cache.get(
                (previous_index, option_index),
                False,
            )
            and (
                prefix := best_prefix(layer_index - 1, previous_index)
            )
            is not None
        )
        return max(candidates, key=_graph_sequence_rank, default=None)

    @lru_cache(maxsize=None)
    def best_suffix(
        layer_index: int,
        option_index: int,
    ) -> tuple[measurement_facts.MeasuredFrameConstraint, ...] | None:
        option = ordered[option_index]
        if layer_index == len(feasible) - 1:
            return (option,)
        candidates = tuple(
            (option, *suffix)
            for next_index in feasible[layer_index + 1]
            if context.edge_support_cache.get(
                (option_index, next_index),
                False,
            )
            and (
                suffix := best_suffix(layer_index + 1, next_index)
            )
            is not None
        )
        return max(candidates, key=_graph_sequence_rank, default=None)

    sequences: dict[
        tuple[int, int, int],
        tuple[measurement_facts.MeasuredFrameConstraint, ...],
    ] = {}
    for layer_index, left_index, right_index in sorted(transitions):
        prefix = best_prefix(layer_index, left_index)
        suffix = best_suffix(layer_index + 1, right_index)
        if prefix is not None and suffix is not None:
            sequences[(layer_index, left_index, right_index)] = (
                *prefix,
                *suffix,
            )
    return sequences

def _independent_separator_edge_witnesses(
    witnesses: frozenset[tuple[int, ObservationId]],
    grouped_options: tuple[
        tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
) -> tuple[tuple[measurement_facts.MeasuredFrameConstraint, ...], ...]:
    best_by_edge: dict[
        ObservationId,
        tuple[measurement_facts.MeasuredFrameConstraint, ...],
    ] = {}
    last_layer = len(grouped_options) - 1
    for layer_index, edge_id in sorted(
        witnesses,
        key=lambda item: (str(item[1]), item[0]),
    ):
        constrained = tuple(
            (
                tuple(
                    (option_index, option)
                    for option_index, option in frame_options
                    if edge_id
                    in _one_sided_supported_separator_edge_ids(
                        tuple(
                            edge
                            for edge in (
                                (
                                    option.leading
                                    if offset > 0
                                    else None
                                ),
                                (
                                    option.trailing
                                    if offset < last_layer
                                    else None
                                ),
                            )
                            if edge is not None
                        )
                    )
                )
                if offset == layer_index
                else frame_options
            )
            for offset, frame_options in enumerate(grouped_options)
        )
        sequence = sequence_graph_best_path(
            constrained,
            ordered,
            context,
        )
        if sequence is None:
            continue
        existing = best_by_edge.get(edge_id)
        if (
            existing is None
            or _graph_sequence_rank(sequence)
            > _graph_sequence_rank(existing)
        ):
            best_by_edge[edge_id] = sequence
    return tuple(
        best_by_edge[edge_id]
        for edge_id in sorted(best_by_edge, key=str)
    )

def sequence_graph_witnesses(
    grouped_options: tuple[
        tuple[tuple[int, measurement_facts.MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    context: SequenceGraphContext,
    *,
    feasibility: SequenceGraphFeasibility | None = None,
) -> tuple[tuple[measurement_facts.MeasuredFrameConstraint, ...], ...]:
    resolved = feasibility or _sequence_graph_feasibility(
        grouped_options,
        ordered,
        context,
    )
    if resolved is None:
        return ()
    forward = list(resolved.forward)
    backward = list(resolved.backward)
    feasible = resolved.feasible
    feasible_sets = tuple(set(indexes) for indexes in feasible)
    feasible_grouped_options = tuple(
        tuple(
            (option_index, option)
            for option_index, option in frame_options
            if option_index in feasible_sets[layer_index]
        )
        for layer_index, frame_options in enumerate(grouped_options)
    )
    physical_witness = sequence_graph_best_path(
        feasible_grouped_options,
        ordered,
        context,
    )
    contact_witnesses = _contact_transition_witnesses(
        forward,
        backward,
        ordered,
    )
    transition_sequences = _physical_sequences_through_transitions(
        resolved.evaluations.witness_transitions,
        feasible,
        ordered,
        context,
    )
    targets: list[tuple[int, int]] = []
    targets.append((0, feasible[0][0]))
    if context.allow_nominal_slot_sized_gap:
        targets.extend(
            (layer_index, option_index)
            for layer_index, indexes in enumerate(feasible)
            for option_index in indexes
        )
    else:
        for layer_index, indexes in enumerate(feasible):
            for key in (
                lambda index: ordered[index].leading.position.minimum,
                lambda index: -ordered[index].leading.position.maximum,
                lambda index: ordered[index].trailing.position.minimum,
                lambda index: -ordered[index].trailing.position.maximum,
            ):
                targets.append((layer_index, max(indexes, key=key)))
    sequences: list[tuple[measurement_facts.MeasuredFrameConstraint, ...]] = []
    if physical_witness is not None:
        sequences.append(physical_witness)
    sequences.extend(contact_witnesses)
    for target_layer, target_index in dict.fromkeys(targets):
        sequences.append(
            _graph_sequence_for_target(
                target_layer,
                target_index,
                forward,
                backward,
                ordered,
            )
        )
    if context.allow_nominal_slot_sized_gap:
        for (
            _layer_index,
            left_index,
            right_index,
        ), sequence in transition_sequences.items():
            left = ordered[left_index]
            right = ordered[right_index]
            common_width = left.width_px.intersection(right.width_px)
            if common_width is None:
                continue
            spacing = right.leading.position.minus(left.trailing.position)
            if spacing.minimum >= common_width.minimum:
                sequences.append(sequence)
    sequences.extend(
        _independent_separator_edge_witnesses(
            resolved.evaluations.independent_edge_witnesses,
            feasible_grouped_options,
            ordered,
            context,
        )
    )
    return tuple(
        sequence
        for sequence in dict.fromkeys(sequences)
        if (
            len(sequence) == 1
            or width_resolution.measured_constraint_common_width(sequence, len(sequence)) is not None
        )
    )

@dataclass(frozen=True)
class MeasuredFrameSequenceSearchResult:
    sequences: tuple[
        tuple[measurement_facts.MeasuredFrameConstraint, ...], ...
    ]
    assignment_evaluations: int
    budget_exhausted: bool

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("sequence search evaluations cannot be negative")

def measured_frame_sequences(
    options: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    count: int,
    visible_content: ContentRegionObservation,
    evaluation_budget: int,
    width_hypotheses: tuple[PixelInterval, ...],
    *,
    allow_nominal_slot_sized_gap: bool,
    minimum_supported_separator_count: int = 0,
) -> MeasuredFrameSequenceSearchResult:
    if minimum_supported_separator_count < 0:
        raise ValueError("separator support lower bound cannot be negative")
    ordered = tuple(
        sorted(
            options,
            key=measured_frame_option_rank,
            reverse=True,
        )
    )
    evaluations = 0
    graph_evaluations = SequenceGraphEvaluations(
        frozenset(),
        frozenset(),
        frozenset(),
    )
    sequences: list[tuple[measurement_facts.MeasuredFrameConstraint, ...]] = []
    truncated = False
    graph_context = sequence_graph_context(
        ordered,
        visible_content,
        allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
    )
    options_by_frame = tuple(
        tuple(
            (option_index, option)
            for option_index, option in enumerate(ordered)
            if _option_is_valid_at_frame_index(option, frame_index, count)
        )
        for frame_index in range(1, count + 1)
    )
    if any(not frame_options for frame_options in options_by_frame):
        return MeasuredFrameSequenceSearchResult((), evaluations, False)
    width_index = _common_width_option_index(
        options_by_frame,
        count,
        width_hypotheses,
    )
    separator_pair_masks = _separator_pair_option_masks(
        width_index.option_lookups
    )
    for group_masks in width_index.group_masks:
        if (
            minimum_supported_separator_count
            and _separator_assignment_upper_bound(
                group_masks,
                separator_pair_masks,
            )
            < minimum_supported_separator_count
        ):
            continue
        grouped_options = _materialize_common_width_group(
            width_index,
            group_masks,
        )
        feasibility = _sequence_graph_feasibility(
            grouped_options,
            ordered,
            graph_context,
        )
        if feasibility is None:
            continue
        group_evaluations = feasibility.evaluations.incremental_cost(
            graph_evaluations
        )
        if evaluations + group_evaluations > evaluation_budget:
            truncated = True
            break
        evaluations += group_evaluations
        graph_evaluations = graph_evaluations.merged(feasibility.evaluations)
        sequences.extend(
            sequence
            for sequence in sequence_graph_witnesses(
                grouped_options,
                ordered,
                graph_context,
                feasibility=feasibility,
            )
            if _sequence_supported_separator_count(sequence)
            >= minimum_supported_separator_count
        )
    return MeasuredFrameSequenceSearchResult(
        tuple(dict.fromkeys(sequences)),
        evaluations,
        truncated,
    )
