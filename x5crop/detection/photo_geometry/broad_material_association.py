"""Exact, bounded raw-peak association on a registered broad trace lattice."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
import math
import sys

from ...domain import ObservationId
from .cross_height_transition_measurement import spatial_region_trace_ordinals
from .measurement_model import BroadMaterialTraceObservation, PhotoBoundaryMeasurementQuery
from .measurement_points import TransitionPoint
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC, PhotoBoundaryMeasurementSpec, spatial_support_region_index
from .robust_line_fit import LINE_REGION_ARITHMETIC_EPSILON_PX, _clip_line_region


class BroadAssociationState(str, Enum):
    COMPLETE = "complete"
    BOUND_EXCEEDED = "bound_exceeded"


@dataclass(frozen=True)
class BroadAssociationWork:
    point_pair_check_count: int = 0
    seed_count: int = 0
    extension_attempt_count: int = 0
    polygon_clip_count: int = 0
    polygon_vertex_evaluation_count: int = 0
    dominance_member_check_count: int = 0
    quota_region_check_count: int = 0
    created_path_count: int = 0
    peak_search_depth: int = 0
    peak_completed_path_count: int = 0
    peak_point_reference_count: int = 0
    peak_polygon_vertex_count: int = 0

    def __post_init__(self) -> None:
        if any(type(getattr(self, field.name)) is not int or getattr(self, field.name) < 0
               for field in fields(self)):
            raise ValueError("broad association work must be nonnegative integers")
        if (self.created_path_count > self.seed_count + self.extension_attempt_count
                or self.peak_search_depth > self.created_path_count):
            raise ValueError("broad association work contains unattempted paths")

    @property
    def charged_work(self) -> int:
        return (self.point_pair_check_count + self.polygon_vertex_evaluation_count
                + self.dominance_member_check_count)


@dataclass(frozen=True)
class BroadAssociationResult:
    state: BroadAssociationState
    input_transition_ids: tuple[ObservationId, ...]
    queried_traces: tuple[int, ...]
    reference_trace_px: float
    paths: tuple[tuple[ObservationId, ...], ...]
    work: BroadAssociationWork
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, BroadAssociationState) or not isinstance(self.work, BroadAssociationWork):
            raise TypeError("broad association requires typed state and work")
        if (not isinstance(self.input_transition_ids, tuple)
                or any(not isinstance(identity, ObservationId) for identity in self.input_transition_ids)
                or tuple(sorted(set(self.input_transition_ids), key=str)) != self.input_transition_ids
                or not isinstance(self.queried_traces, tuple) or not self.queried_traces
                or any(type(trace) is not int for trace in self.queried_traces)
                or tuple(sorted(set(self.queried_traces))) != self.queried_traces
                or not math.isfinite(self.reference_trace_px)):
            raise ValueError("broad association input identity is invalid")
        inputs = set(self.input_transition_ids)
        if (not isinstance(self.paths, tuple)
                or any(not isinstance(path, tuple) or not path
                       or any(not isinstance(identity, ObservationId) for identity in path)
                       or len(set(path)) != len(path) or not set(path).issubset(inputs)
                       for path in self.paths)
                or tuple(sorted(set(self.paths), key=lambda path: tuple(map(str, path)))) != self.paths):
            raise ValueError("broad association paths changed input identities")
        if self.state == BroadAssociationState.BOUND_EXCEEDED:
            if self.paths or not isinstance(self.failure_reason, str) or not self.failure_reason:
                raise ValueError("bounded broad association cannot retain partial paths")
        elif self.failure_reason is not None:
            raise ValueError("complete broad association cannot retain a failure")
        p, t = len(inputs), len(self.queried_traces)
        work = self.work
        if (work.charged_work > 5 * p * p
                or work.seed_count > p
                or work.peak_search_depth > min(p, t)
                or work.peak_completed_path_count > p
                or len(self.paths) > work.peak_completed_path_count
                or work.peak_point_reference_count > 2 * p * t + 2 * t
                or work.peak_polygon_vertex_count > min(p, t) * (2 * t + 4) + 4 * t + 10
                or work.quota_region_check_count > 3 * (
                    work.seed_count + work.extension_attempt_count + work.created_path_count
                )):
            raise ValueError("broad association work exceeds its input bounds")

    @property
    def temporary_numeric_bytes(self) -> int:
        """Bound solver numeric/index storage, not Python heap or process RSS."""
        return (16 * self.work.peak_polygon_vertex_count
                + 8 * self.work.peak_point_reference_count
                + 64 * len(self.input_transition_ids) + 80 * len(self.queried_traces))

    def validate_query(
        self, query: PhotoBoundaryMeasurementQuery,
        observations: tuple[BroadMaterialTraceObservation, ...],
    ) -> None:
        if (self.input_transition_ids != tuple(sorted((raw.transition_id for raw in observations), key=str))
                or self.queried_traces != query.trace_positions_px
                or self.reference_trace_px != (query.trace_positions_px[0] + query.trace_positions_px[-1]) / 2):
            raise ValueError("broad association changed registered input identity")
        by_id = {raw.transition_id: raw for raw in observations}
        regions = spatial_region_trace_ordinals(self.queried_traces)
        for path in self.paths:
            raw = tuple(by_id[identity] for identity in path)
            ordinals = tuple(item.trace_ordinal for item in raw)
            if (tuple(sorted(set(ordinals))) != ordinals
                    or len({(item.polarity, item.background_side) for item in raw}) != 1
                    or not regions
                    or any(sum(ordinal in region for ordinal in ordinals) <= len(region) // 2
                           for region in regions)):
                raise ValueError("broad association path lost registered material support")


def associate_registered_broad_material(
    query: PhotoBoundaryMeasurementQuery,
    observations: tuple[BroadMaterialTraceObservation, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> BroadAssociationResult | None:
    if not observations:
        return None
    return associate_broad_material(
        tuple(TransitionPoint(raw, float(raw.trace_coordinate_px), raw.coordinate_px) for raw in observations),
        query.trace_positions_px,
        reference_trace_px=(query.trace_positions_px[0] + query.trace_positions_px[-1]) / 2,
        connection_px=spec.line_connection_allowance_px(query.boundary_axis_scale_px_per_mm.maximum),
        maximum_slope=math.tan(math.radians(spec.maximum_measurable_line_angle_degrees)),
        maximum_missing_lattice_steps=spec.maximum_missing_lattice_steps,
    )


class _BoundExceeded(Exception):
    pass


def _mask_numeric_slots(raw_count: int) -> int:
    """Reserve actual Python numeric limbs in eight-byte accounting slots."""
    digits = (raw_count + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
    return (digits * sys.int_info.sizeof_digit + 7) // 8


def broad_family_sources_supported(
    identities, association_paths, source_regions,
) -> bool:
    """Certify a native path subset or the complete existing region union.

    Geometry, one peak per trace and regional support remain caller-owned.
    A family cannot splice arbitrary pieces of mutually exclusive paths.
    """
    wanted = frozenset(identities)
    paths = tuple(frozenset(path) for path in association_paths)
    if not wanted:
        return False
    if any(wanted.issubset(path) for path in paths):
        return True
    parents = tuple(frozenset(region) for region in source_regions
                    if region and frozenset(region).issubset(wanted))
    return (len(parents) >= 2 and frozenset().union(*parents) == wanted
            and all(any(parent.issubset(path) for path in paths) for parent in parents))


def associate_broad_material(
    points: tuple[TransitionPoint, ...],
    queried_traces: tuple[int, ...],
    *,
    reference_trace_px: float,
    connection_px: float,
    maximum_slope: float,
    maximum_missing_lattice_steps: int,
) -> BroadAssociationResult:
    """Enumerate maximal feasible paths, or return a typed incomplete search.

    Search order never resolves a competition. A branch is discarded only
    when its complete possible raw-ID universe is contained in an already
    feasible qualified path. Connected components use the original local
    link rule; raw physical intervals independently constrain each path.
    All pair, clipping and membership operations share a 5 P² cap.
    """
    if (not isinstance(points, tuple) or not isinstance(queried_traces, tuple)
            or not queried_traces or any(type(trace) is not int for trace in queried_traces)
            or tuple(sorted(set(queried_traces))) != queried_traces
            or not math.isfinite(reference_trace_px)
            or not math.isfinite(connection_px) or connection_px < 0.0
            or not math.isfinite(maximum_slope) or maximum_slope < 0.0
            or type(maximum_missing_lattice_steps) is not int
            or maximum_missing_lattice_steps < 0):
        raise ValueError("broad association requires a registered lattice and finite bounds")
    for point in points:
        if (not isinstance(point, TransitionPoint)
                or not isinstance(point.transition, BroadMaterialTraceObservation)):
            raise TypeError("broad association requires actual typed broad peaks")
        raw = point.transition
        raw.__post_init__()
        if (not isinstance(raw.transition_id, ObservationId)
                or not math.isfinite(point.trace) or not math.isfinite(point.coordinate)
                or point.trace != raw.trace_coordinate_px or point.coordinate != raw.coordinate_px
                or type(raw.trace_ordinal) is not int
                or not 0 <= raw.trace_ordinal < len(queried_traces)
                or queried_traces[raw.trace_ordinal] != point.trace
                or raw.spatial_region_index != spatial_support_region_index(queried_traces, point.trace)):
            raise ValueError("broad peak leaves its registered trace identity")
    identities = tuple(sorted((point.transition.transition_id for point in points), key=str))
    if len(set(identities)) != len(points) or len({point.transition.query_id for point in points}) > 1:
        raise ValueError("broad association requires unique peaks from one query")
    trace_peak_counts = [0] * len(queried_traces)
    for point in points:
        trace_peak_counts[point.transition.trace_ordinal] += 1
    # Visit the less populated lattice end first. This only schedules the
    # exhaustive search; it cannot choose among completed interpretations.
    reverse_search = tuple(reversed(trace_peak_counts)) < tuple(trace_peak_counts)

    def trace_order(point):
        ordinal = point.transition.trace_ordinal
        return len(queried_traces) - 1 - ordinal if reverse_search else ordinal

    ordered = tuple(sorted(points, key=lambda point: (
        trace_order(point), point.coordinate, str(point.transition.transition_id),
    )))
    p, t = len(ordered), len(queried_traces)
    counters = {field.name: 0 for field in fields(BroadAssociationWork)}
    charged = 0

    def charge(field: str, count: int = 1) -> None:
        nonlocal charged
        if charged + count > 5 * p * p:
            raise _BoundExceeded("charged_work_bound")
        charged += count
        counters[field] += count

    def finish(paths=(), reason=None):
        return BroadAssociationResult(
            BroadAssociationState.COMPLETE if reason is None else BroadAssociationState.BOUND_EXCEEDED,
            identities, queried_traces, reference_trace_px, paths,
            BroadAssociationWork(**counters), reason,
        )

    regions = spatial_region_trace_ordinals(queried_traces)
    if not points or not regions:
        return finish()
    quotas = tuple(len(region) // 2 + 1 for region in regions)
    orders = tuple(trace_order(point) for point in ordered)
    raw_regions = tuple(point.transition.spatial_region_index for point in ordered)
    completed: list[tuple[list[int], int]] = []
    completed_references = 0
    frame_references = 0
    # This expands arithmetic only for an impossibility certificate. Final
    # feasibility still uses the unchanged closed-set polygon clipper.
    magnitude = max(1.0, abs(reference_trace_px) * maximum_slope,
                    *(abs(value) for point in ordered for value in (
                        point.transition.physical_position_interval_px.minimum,
                        point.transition.physical_position_interval_px.maximum,
                        point.trace * maximum_slope)))
    guard = LINE_REGION_ARITHMETIC_EPSILON_PX + 16 * (p + 2) * math.ulp(magnitude)
    slope_guard = 16 * (p + 2) * math.ulp(maximum_slope)
    base_bounds = (-maximum_slope - slope_guard, maximum_slope + slope_guard, (), ())
    # A finite FIFO of at most P physical pairs, never a chain/adjacency cache.
    physical_cache: dict[int, tuple[float, float]] = {}

    def reference_peak(extra=0):
        value = completed_references + frame_references + 3 * len(physical_cache) + extra
        if value > 2 * p * t + 2 * t:
            raise _BoundExceeded("point_reference_bound")
        counters['peak_point_reference_count'] = max(counters['peak_point_reference_count'], value)

    def linked(first: int, second: int) -> bool:
        charge('point_pair_check_count')
        a, b = ordered[first], ordered[second]
        return (0 < orders[second] - orders[first] <= maximum_missing_lattice_steps + 1
                and a.transition.polarity == b.transition.polarity
                and a.transition.background_side == b.transition.background_side
                and abs(a.coordinate - b.coordinate)
                <= abs(a.trace - b.trace) * maximum_slope + connection_px + 1.0e-12)

    def pair_bounds(first, second):
        charge('dominance_member_check_count')
        key = min(first, second) * p + max(first, second)
        if key in physical_cache:
            return physical_cache[key]
        charge('point_pair_check_count', 2)
        a, b = ordered[first], ordered[second]
        if a.trace > b.trace:
            a, b = b, a
        delta = b.trace - a.trace
        if delta <= 0.0:
            raise ValueError("physical certificate requires distinct traces")
        left, right = a.transition.physical_position_interval_px, b.transition.physical_position_interval_px
        al = math.nextafter(left.minimum - guard, -math.inf)
        ah = math.nextafter(left.maximum + guard, math.inf)
        bl = math.nextafter(right.minimum - guard, -math.inf)
        bh = math.nextafter(right.maximum + guard, math.inf)
        dlo, dhi = math.nextafter(delta, -math.inf), math.nextafter(delta, math.inf)
        nl, nh = math.nextafter(bl - ah, -math.inf), math.nextafter(bh - al, math.inf)
        bounds = (math.nextafter(nl / (dhi if nl >= 0 else dlo), -math.inf),
                  math.nextafter(nh / (dlo if nh >= 0 else dhi), math.inf))
        if len(physical_cache) == p:
            del physical_cache[next(iter(physical_cache))]
        reference_peak(3)
        physical_cache[key] = bounds
        return bounds

    def add_required(required, bounds, additions, ranges=None):
        lower, upper, lower_owners, upper_owners = bounds
        charge('dominance_member_check_count', len(required))
        changed = list(required)
        changed_set = set(required)
        for index in additions:
            charge('dominance_member_check_count')
            if index in changed_set:
                continue
            cached = ranges.get(index) if ranges is not None else None
            if cached is not None:
                lower, upper = max(lower, cached[0]), min(upper, cached[1])
                if lower > upper:
                    return None
            for prior in changed[len(required):] if cached is not None else changed:
                if orders[prior] == orders[index]:
                    return None
                lo, hi = pair_bounds(prior, index)
                if lo > lower:
                    lower, lower_owners = lo, (prior, index)
                if hi < upper:
                    upper, upper_owners = hi, (prior, index)
                if lower > upper:
                    return None
            changed.append(index)
            charge('dominance_member_check_count')
            changed_set.add(index)
        return tuple(sorted(changed)), (lower, upper, lower_owners, upper_owners)

    def physical_conflict(pool):
        first = ordered[pool[0]]
        interval = first.transition.physical_position_interval_px
        allowance = maximum_slope * abs(first.trace - reference_trace_px)
        lower, upper = interval.minimum - allowance, interval.maximum + allowance
        vertices = ((lower, -maximum_slope), (upper, -maximum_slope),
                    (upper, maximum_slope), (lower, maximum_slope))
        for index in pool:
            point = ordered[index]
            interval = point.transition.physical_position_interval_px
            delta = point.trace - reference_trace_px
            for a, b, limit in ((1.0, delta, interval.maximum), (-1.0, -delta, -interval.minimum)):
                charge('polygon_vertex_evaluation_count', len(vertices) + 1)
                counters['polygon_clip_count'] += 1
                counters['peak_polygon_vertex_count'] = max(
                    counters['peak_polygon_vertex_count'], 2 * len(vertices) + 1,
                )
                vertices = _clip_line_region(vertices, a, b, limit)
                if not vertices:
                    # Pairwise intercept intervals characterize the slope
                    # interval. Only after actual clipping failed do we seek
                    # a smaller outward-certified conflict (at most 4 raw).
                    lo_bound, hi_bound, lo_owners, hi_owners = base_bounds
                    for rank, current in enumerate(pool):
                        for previous_rank in range(rank):
                            prior = pool[previous_rank]
                            lo, hi = pair_bounds(prior, current)
                            if lo > lo_bound:
                                lo_bound, lo_owners = lo, (prior, current)
                            if hi < hi_bound:
                                hi_bound, hi_owners = hi, (prior, current)
                            if lo_bound > hi_bound:
                                charge('dominance_member_check_count', len(lo_owners) + len(hi_owners))
                                conflict = tuple(sorted(set(lo_owners + hi_owners)))
                                if len(conflict) == 4:
                                    # Four endpoint owners can describe a
                                    # smaller strip contradiction. Certify a
                                    # three-raw subset with the same outward
                                    # arithmetic before creating its branches.
                                    for omitted in range(4):
                                        lo_subset, hi_subset = base_bounds[:2]
                                        for right in range(4):
                                            if right == omitted:
                                                continue
                                            for left in range(right):
                                                if left == omitted:
                                                    continue
                                                lo, hi = pair_bounds(conflict[left], conflict[right])
                                                lo_subset, hi_subset = max(lo_subset, lo), min(hi_subset, hi)
                                        if lo_subset > hi_subset:
                                            charge('dominance_member_check_count', 4)
                                            return tuple(index for rank, index in enumerate(conflict)
                                                         if rank != omitted)
                                return conflict
                    # At arithmetic boundaries use the entire actually
                    # clipped union, rather than infer a smaller conflict.
                    return tuple(pool)
        if any(not math.isfinite(value) for vertex in vertices for value in vertex):
            raise ValueError("broad association produced nonfinite geometry")
        return None

    try:
        parent = list(range(p))

        def root(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for first in range(p):
            for second in range(first + 1, p):
                if orders[second] - orders[first] > maximum_missing_lattice_steps + 1:
                    break
                if linked(first, second):
                    parent[root(second)] = root(first)
        components: dict[int, list[int]] = {}
        for index in range(p):
            charge('dominance_member_check_count')
            components.setdefault(root(index), []).append(index)

        for component in components.values():
            q = len(component)
            if q < sum(quotas):
                # Distinct trace support cannot exceed the raw cardinality.
                # This rejects only components too small for the unchanged
                # three regional quotas, before materializing search scratch.
                counters['seed_count'] += 1
                counters['quota_region_check_count'] += 3
                continue
            limbs = (q + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit
            mask_references = _mask_numeric_slots(q)
            component_start = len(completed)
            ranks = {index: rank for rank, index in enumerate(component)}

            def words(operations=1):
                charge('dominance_member_check_count', operations * limbs)

            def bit(index):
                words()
                return 1 << ranks[index]

            def members(mask):
                # Materialize one bounded byte view, rather than repeatedly
                # copy a full Python integer for each extracted low bit.
                # Conversion visits all limbs; each byte-bit membership is
                # one actual single-limb intersection. No P masks are kept.
                words()
                data = mask.to_bytes((q + 7) // 8, 'little')
                result = []
                byte_bits = (1, 2, 4, 8, 16, 32, 64, 128)
                for rank, index in enumerate(component):
                    charge('dominance_member_check_count')
                    if data[rank // 8] & byte_bits[rank % 8]:
                        result.append(index)
                return result

            def contained(mask, other):
                words(2)
                return mask & other == mask

            def viability(pool):
                """Retain every raw that can belong to a quota-qualified DAG path.

                Registered regions are consecutive along the ordered lattice.
                A prefix entering the next region must already satisfy the
                previous region's quota. For a fixed endpoint only the largest
                count in its current region matters. The suffix is symmetric;
                concatenating them proves local-link support, not a physical
                straight line. Physical feasibility remains search-owned.
                """
                forward = [0] * len(pool)
                backward = [0] * len(pool)
                first_region, last_region = (2, 0) if reverse_search else (0, 2)
                for rank, index in enumerate(pool):
                    region = raw_regions[index]
                    best = 1 if region == first_region else 0
                    for previous in range(rank - 1, -1, -1):
                        prior = pool[previous]
                        if orders[index] - orders[prior] > maximum_missing_lattice_steps + 1:
                            break
                        count = forward[previous]
                        if count and linked(prior, index):
                            previous_region = raw_regions[prior]
                            if previous_region == region:
                                best = max(best, count + 1)
                            elif abs(previous_region - region) == 1 and count >= quotas[previous_region]:
                                best = max(best, 1)
                    forward[rank] = best
                for rank in range(len(pool) - 1, -1, -1):
                    index = pool[rank]
                    region = raw_regions[index]
                    best = 1 if region == last_region else 0
                    for following in range(rank + 1, len(pool)):
                        later = pool[following]
                        if orders[later] - orders[index] > maximum_missing_lattice_steps + 1:
                            break
                        count = backward[following]
                        if count and linked(index, later):
                            following_region = raw_regions[later]
                            if following_region == region:
                                best = max(best, count + 1)
                            elif abs(following_region - region) == 1 and count >= quotas[following_region]:
                                best = max(best, 1)
                    backward[rank] = best
                result = []
                for rank, index in enumerate(pool):
                    charge('dominance_member_check_count')
                    before, after = forward[rank], backward[rank]
                    if before and after and before + after - 1 >= quotas[raw_regions[index]]:
                        result.append(index)
                return result

            def propagate(pool, ranges, required, bounds, additions):
                # The branch already supplies every requested addition to
                # add_required. Repeating an existing required raw is harmless:
                # its pair bounds are already present in ranges. No difference
                # of two required sets is needed to discover those additions.
                charge('dominance_member_check_count', len(required))
                required_set = set(required)
                result = {}
                for index in pool:
                    charge('dominance_member_check_count')
                    if index in required_set:
                        result[index] = bounds[:2]
                        continue
                    old = ranges.get(index) if ranges is not None else base_bounds[:2]
                    if old is None:
                        continue
                    lo, hi = max(old[0], bounds[0]), min(old[1], bounds[1])
                    for prior in additions:
                        if prior == index:
                            continue
                        if orders[prior] == orders[index]:
                            lo, hi = 1.0, 0.0
                            break
                        pair_lo, pair_hi = pair_bounds(prior, index)
                        lo, hi = max(lo, pair_lo), min(hi, pair_hi)
                        if lo > hi:
                            break
                    if lo <= hi:
                        result[index] = (lo, hi)
                return result

            def visit(mask, required, bounds, depth, ranges=None):
                nonlocal completed_references, frame_references
                # Every suspended frame retains its own scratch reservation.
                scratch_references = 8 * q + 2 * t
                references = scratch_references + 2 * mask_references + len(required) + 3 * len(ranges or ())
                frame_references += references

                def descend(child_mask, child_required, child_bounds, child_ranges, schedule_count):
                    nonlocal frame_references, references
                    active_references = references
                    # Grouping has been released. Only the pool, schedule and
                    # six numeric bound/owner slots survive beside durable
                    # mask/required/range state. Child arguments alias entry
                    # state; stale entry buffers after child tail updates
                    # remain covered by its active scratch reservation.
                    references = (len(pool) + schedule_count + 6 + 2 * mask_references
                                  + len(required) + 3 * len(ranges or ()))
                    frame_references += references - active_references
                    try:
                        visit(child_mask, child_required, child_bounds, depth + 1, child_ranges)
                    finally:
                        frame_references += active_references - references
                        references = active_references
                    reference_peak()

                try:
                    while True:
                        if depth > min(p, t):
                            raise _BoundExceeded("search_depth_bound")
                        counters['created_path_count'] += 1
                        counters['peak_search_depth'] = max(counters['peak_search_depth'], depth)
                        reference_peak()
                        charge('dominance_member_check_count', len(required))
                        required_set = set(required)
                        dominance_forced = None
                        new_mask = 0
                        for rank in range(component_start, len(completed)):
                            old = completed[rank][1]
                            difference = 0
                            # Original mask plus both transient positive
                            # operands can coexist while XOR is evaluated.
                            reference_peak(mask_references)
                            words(2)
                            difference = mask ^ (mask & old)
                            if not difference:
                                return
                            words()
                            if difference.bit_count() == 1:
                                words()
                                charge('dominance_member_check_count')
                                index = component[difference.bit_length() - 1]
                                charge('dominance_member_check_count')
                                if index not in required_set:
                                    dominance_forced = index
                                    break
                        difference = 0
                        pool = members(mask)
                        filtered = []
                        if dominance_forced is not None:
                            # Every explanation omitting this sole raw is
                            # already contained in a qualified completed path.
                            # Require it only in the remaining search branch;
                            # the completed path itself stays represented.
                            updated = add_required(required, bounds, (dominance_forced,), ranges)
                            if updated is None:
                                return
                            ranges = propagate(pool, ranges, *updated, (dominance_forced,))
                            frame_references -= references
                            required, bounds = updated
                            references = scratch_references + 2 * mask_references + len(required) + 3 * len(ranges)
                            frame_references += references
                            counters['extension_attempt_count'] += 1
                            continue
                        new_mask = mask
                        mask_filtered = False
                        by_trace: dict[int, list[int]] = {}
                        for index in pool:
                            charge('dominance_member_check_count')
                            available = ranges.get(index) if ranges is not None else base_bounds[:2]
                            if available is not None and max(available[0], bounds[0]) <= min(available[1], bounds[1]):
                                filtered.append(index)
                                charge('dominance_member_check_count')
                                by_trace.setdefault(orders[index], []).append(index)
                            else:
                                charge('dominance_member_check_count')
                                if index in required_set:
                                    return
                                words()
                                new_mask ^= bit(index)
                                mask_filtered = True
                        pool = filtered
                        region_counts = [0, 0, 0]
                        for indices in by_trace.values():
                            region_counts[raw_regions[indices[0]]] += 1
                        counters['quota_region_check_count'] += 3
                        if any(count < quota for count, quota in zip(region_counts, quotas)):
                            return
                        duplicates = next((tuple(indices) for indices in by_trace.values()
                                           if len(indices) > 1), None)
                        forced = []
                        if duplicates:
                            for indices in by_trace.values():
                                if (len(indices) == 1 and region_counts[raw_regions[indices[0]]]
                                        == quotas[raw_regions[indices[0]]]):
                                    charge('dominance_member_check_count')
                                    if indices[0] not in required_set:
                                        forced.append(indices[0])
                        mask = new_mask
                        if forced:
                            updated = add_required(required, bounds, forced, ranges)
                            if updated is None:
                                return
                            ranges = propagate(pool, ranges, *updated, forced)
                            frame_references -= references
                            required, bounds = updated
                            references = scratch_references + 2 * mask_references + len(required) + 3 * len(ranges)
                            frame_references += references
                            counters['extension_attempt_count'] += 1
                            continue
                        if mask_filtered and any(contained(mask, old) for _, old in completed[component_start:]):
                            return
                        if duplicates:
                            removed = 0
                            for index in duplicates:
                                words()
                                removed |= bit(index)
                            words()
                            base = mask ^ removed
                            removed = 0
                            by_trace.clear()
                            required_set.clear()
                            filtered = ()
                            forced = ()
                            optional = conflict = ()
                            indices = ()
                            region_counts = ()
                            for rank in range(len(duplicates) - 1):
                                index = duplicates[rank]
                                updated = add_required(required, bounds, (index,), ranges)
                                if updated is None:
                                    continue
                                words()
                                counters['extension_attempt_count'] += 1
                                descend(base | bit(index), *updated,
                                        propagate(pool, ranges, *updated, (index,)), len(duplicates))
                                updated = None
                            # The final choice also contains the zero-peak
                            # case. Its frame is reused, so only branches that
                            # require a new trace increase the search depth.
                            words()
                            mask = base | bit(duplicates[-1])
                            counters['extension_attempt_count'] += 1
                            continue
                        conflict = next(((first, second) for first, second in zip(pool, pool[1:])
                                         if not linked(first, second)), None)
                        if conflict is None:
                            conflict = physical_conflict(pool)
                        if conflict is None:
                            remove = []
                            for rank in range(component_start, len(completed)):
                                old = completed[rank][1]
                                if contained(old, mask):
                                    remove.append(rank)
                            for rank in reversed(remove):
                                old_component, _ = completed.pop(rank)
                                completed_references -= _mask_numeric_slots(len(old_component))
                            if len(completed) == p:
                                raise _BoundExceeded("completed_path_bound")
                            completed.append((component, mask))
                            completed_references += mask_references
                            counters['peak_completed_path_count'] = max(
                                counters['peak_completed_path_count'], len(completed),
                            )
                            reference_peak()
                            return
                        # Partition by the last omitted conflict owner. Each
                        # recursive branch requires at least one new trace;
                        # the optional final branch reuses the current frame.
                        charge('dominance_member_check_count', len(conflict))
                        optional = tuple(index for index in conflict if index not in required_set)
                        if not optional:
                            return
                        charge('dominance_member_check_count', len(optional))
                        optional = tuple(sorted(optional, key=lambda index: (
                            -(ordered[index].transition.physical_position_interval_px.maximum
                              - ordered[index].transition.physical_position_interval_px.minimum),
                            orders[index], index,
                        )))
                        by_trace.clear()
                        required_set.clear()
                        filtered = ()
                        forced = ()
                        conflict = ()
                        indices = ()
                        region_counts = ()
                        base = removed = 0
                        for rank in range(len(optional) - 1):
                            index = optional[rank]
                            updated = add_required(required, bounds, optional[rank + 1:], ranges)
                            if updated is None:
                                continue
                            words()
                            counters['extension_attempt_count'] += 1
                            descend(mask ^ bit(index), *updated,
                                    propagate(pool, ranges, *updated, optional[rank + 1:]), len(optional))
                            updated = None
                        words()
                        mask ^= bit(optional[-1])
                        counters['extension_attempt_count'] += 1
                finally:
                    frame_references -= references

            # DAG viability is an initial conservative upper set. Later
            # exclusions use exact conflict branching and fixed trace quotas;
            # recomputing this upper set cannot add a valid interpretation.
            region_counts = [0, 0, 0]
            unique_traces = True
            last_order = None
            for index in component:
                charge('dominance_member_check_count')
                if orders[index] != last_order:
                    region_counts[raw_regions[index]] += 1
                else:
                    unique_traces = False
                last_order = orders[index]
            counters['seed_count'] += 1
            counters['quota_region_check_count'] += 3
            if any(count < quota for count, quota in zip(region_counts, quotas)):
                continue
            reference_peak(8 * q + 2 * t)
            viable = component if unique_traces and all(
                linked(first, second) for first, second in zip(component, component[1:])
            ) else viability(component)
            if not viable:
                continue
            if len(viable) == q:
                # 1 << Q needs one extra limb at an exact limb boundary.
                charge('dominance_member_check_count',
                       2 * ((q + sys.int_info.bits_per_digit) // sys.int_info.bits_per_digit))
                initial_mask = (1 << q) - 1
            else:
                initial_mask = 0
                for index in viable:
                    words()
                    initial_mask |= bit(index)
            visit(initial_mask, (), base_bounds, 1)
        output_references = 0
        for component, mask in completed:
            charge('dominance_member_check_count', (
                len(component) + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit)
            output_references += mask.bit_count()
        reference_peak(output_references + t)
        paths = []
        for component, mask in completed:
            charge('dominance_member_check_count', (
                len(component) + sys.int_info.bits_per_digit - 1) // sys.int_info.bits_per_digit)
            data = mask.to_bytes((len(component) + 7) // 8, 'little')
            selected = []
            byte_bits = (1, 2, 4, 8, 16, 32, 64, 128)
            for rank, index in enumerate(component):
                charge('dominance_member_check_count')
                if data[rank // 8] & byte_bits[rank % 8]:
                    selected.append(index)
            paths.append(tuple(ordered[index].transition.transition_id
                               for index in sorted(selected, key=lambda index: ordered[index].trace)))
        return finish(tuple(sorted(paths, key=lambda path: tuple(map(str, path)))))
    except _BoundExceeded as error:
        return finish(reason=str(error))
