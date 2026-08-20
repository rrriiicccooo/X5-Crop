"""Construct and group bounded short-axis physical fit candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ...domain import FiniteInterval
from .interval_math import (
    add as _add,
    intersect as _intersect,
    midpoint as _midpoint_interval,
    scale as _scale_interval,
    subtract as _subtract,
)
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .output_model import OutputBoundaryUse, SharedStripDirection
from .template_cross_geometry import (
    direction_closure as _direction_closure,
    hull_intervals as _hull_intervals,
    shared_direction_for as _direction_for,
    shared_trace_coordinates as _shared_trace_coordinates,
    single_direction_ready as _single_direction_ready,
)
from .template_cross_model import (
    CrossEvidence,
    CrossFit,
    CrossRoleBinding,
)
from .template_model import TemplateSpec


@dataclass(frozen=True)
class _Candidate:
    top: CrossRoleBinding
    bottom: CrossRoleBinding
    direct_pair: bool
    shared_support: int
    continuous_support: float
    residual: float
    center_compatible: bool
    height_compatibility: FiniteInterval
    canonical_height_px: float
    shift_interval: FiniteInterval
    center_interval: FiniteInterval | None
    direction_interval: FiniteInterval | None
    direction_ready: bool
    support_trace_coordinates_px: tuple[int, ...]
    top_full_override: FiniteInterval | None = None
    bottom_full_override: FiniteInterval | None = None
    source_direction: SharedStripDirection | None = None


def _direct_candidate(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    center: FiniteInterval | None,
    minimum_shared_trace_support: int,
    source_direction: SharedStripDirection | None = None,
) -> _Candidate | None:
    # Aperture coordinates require photo-boundary role authority on both
    # sides. Role-unknown material/holder lines belong to the separate
    # enclosing-support owner even when their span happens to match H.
    if not top.role_authorized or not bottom.role_authorized:
        return None
    expected_bottom = _add(top.full_interval_px, fixed_height)
    if _intersect(bottom.full_interval_px, expected_bottom) is None:
        return None
    height = _intersect(fixed_height, _subtract(bottom.full_interval_px, top.full_interval_px))
    shift = _intersect(top.full_interval_px, _subtract(bottom.full_interval_px, fixed_height))
    if height is None or shift is None:
        return None
    support_traces = _shared_trace_coordinates(top, bottom)
    if len(support_traces) < minimum_shared_trace_support:
        return None
    if source_direction is None:
        direction, direction_ready, contradiction = _direction_closure(
            top,
            bottom,
        )
        if contradiction:
            return None
    else:
        if any(
            item.observed_direction_interval_degrees is None
            or _intersect(
                item.observed_direction_interval_degrees,
                source_direction.observed_angle_interval_degrees,
            )
            is None
            for item in (top, bottom)
        ):
            return None
        # The whole-strip observation validates that both local fragments
        # belong to the same strip.  Their measured direction still owns the
        # final deskew; small local departures remain a straight-model
        # residual rather than being forced into the coarse statistical fit.
        direction = source_direction.observed_angle_interval_degrees
        direction_ready = True
    midpoint = _midpoint_interval(top.full_interval_px, bottom.full_interval_px)
    center_interval = _intersect(midpoint, center) if center is not None else midpoint
    return _Candidate(
        top=top,
        bottom=bottom,
        direct_pair=True,
        shared_support=0,
        continuous_support=min(top.continuous_support_fraction, bottom.continuous_support_fraction),
        residual=top.fit_residual_px + bottom.fit_residual_px,
        center_compatible=center_interval is not None,
        height_compatibility=height,
        canonical_height_px=canonical_height_px,
        shift_interval=shift,
        center_interval=center_interval,
        direction_interval=direction,
        direction_ready=direction_ready,
        support_trace_coordinates_px=support_traces,
        source_direction=None,
    )


def _single_candidate(
    binding: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    center: FiniteInterval | None,
    source_direction: SharedStripDirection | None = None,
) -> _Candidate | None:
    # A single edge needs independent spatial support and direct direction.
    # Without holder-centre authority it must additionally span the complete
    # registered domain before its coordinate can own placement.
    if (
        not binding.role_authorized
        or binding.independent_support_region_count
        < SPATIAL_SUPPORT_REGION_COUNT
        or (
            source_direction is None
            and not _single_direction_ready(binding)
        )
        or (center is None and not binding.source_spanning_continuous)
    ):
        return None
    if center is not None:
        half_height = _scale_interval(fixed_height, 0.5)
        centered_top = _subtract(center, half_height)
        centered_bottom = _add(center, half_height)
        expected_side = (
            centered_top
            if binding.role == BoundaryRole.TOP
            else centered_bottom
        )
        if _intersect(binding.full_interval_px, expected_side) is None:
            return None
        # Holder centre and the complete physical H interval are compatibility
        # facts only.  Once this placement is selected, the fixed canonical H
        # owns the inferred side; propagating the complete search interval into
        # output safety would manufacture placements that were never selected.
        direct_center = binding.full_interval_px.center
        if binding.role == BoundaryRole.TOP:
            canonical_top = direct_center
            canonical_bottom = direct_center + canonical_height_px
            top_full = binding.full_interval_px
            bottom_full = _add(
                binding.full_interval_px,
                FiniteInterval.exact(canonical_height_px),
            )
        else:
            canonical_bottom = direct_center
            canonical_top = direct_center - canonical_height_px
            bottom_full = binding.full_interval_px
            top_full = _subtract(
                binding.full_interval_px,
                FiniteInterval.exact(canonical_height_px),
            )
        return _Candidate(
            top=binding,
            bottom=binding,
            direct_pair=False,
            shared_support=0,
            continuous_support=binding.continuous_support_fraction,
            residual=binding.fit_residual_px,
            center_compatible=True,
            height_compatibility=fixed_height,
            canonical_height_px=canonical_height_px,
            shift_interval=FiniteInterval.exact(canonical_top),
            center_interval=center,
            direction_interval=(
                source_direction.full_angle_interval_degrees
                if source_direction is not None
                else binding.full_direction_interval_degrees
            ),
            direction_ready=True,
            support_trace_coordinates_px=binding.trace_coordinates_px,
            top_full_override=top_full,
            bottom_full_override=bottom_full,
            source_direction=source_direction,
        )
    if binding.role == BoundaryRole.TOP:
        top = binding
        bottom = binding
        top_full = binding.full_interval_px
        bottom_full = _add(
            top_full,
            FiniteInterval.exact(canonical_height_px),
        )
    else:
        top = binding
        bottom = binding
        bottom_full = binding.full_interval_px
        top_full = _subtract(
            bottom_full,
            FiniteInterval.exact(canonical_height_px),
        )
    shift = top_full
    midpoint = _midpoint_interval(top_full, bottom_full)
    center_interval = _intersect(midpoint, center) if center is not None else midpoint
    return _Candidate(
        top=top,
        bottom=bottom,
        direct_pair=False,
        shared_support=0,
        continuous_support=binding.continuous_support_fraction,
        residual=binding.fit_residual_px,
        center_compatible=center_interval is not None,
        height_compatibility=fixed_height,
        canonical_height_px=canonical_height_px,
        shift_interval=shift,
        center_interval=center_interval,
        direction_interval=(
            source_direction.full_angle_interval_degrees
            if source_direction is not None
            else binding.full_direction_interval_degrees
        ),
        direction_ready=True,
        support_trace_coordinates_px=binding.trace_coordinates_px,
        top_full_override=top_full,
        bottom_full_override=bottom_full,
        source_direction=source_direction,
    )


def _template_local_refinement_candidates(
    anchor: CrossRoleBinding,
    opposite_bindings: Sequence[CrossRoleBinding],
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    center: FiniteInterval | None,
    minimum_shared_trace_support: int,
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
    source_direction: SharedStripDirection | None = None,
) -> tuple[_Candidate, ...]:
    """Refine one template-projected opposite side with the nearest raw line.

    The source-wide, role-authorized anchor already owns the cross offset.
    Fixed H only predicts a bounded local corridor; it does not create the
    missing side.  A real opposite observation inside that corridor can refine
    H when its physical position is uniquely nearest.  Equal nearest lines
    remain discrete candidates and therefore unresolved downstream.
    """

    if not anchor.role_authorized or (
        source_direction is None and not _single_direction_ready(anchor)
    ):
        return ()
    if len(longitudinal_support_domains_px) < SPATIAL_SUPPORT_REGION_COUNT:
        return ()
    expected = (
        anchor.full_interval_px.center + canonical_height_px
        if anchor.role == BoundaryRole.TOP
        else anchor.full_interval_px.center - canonical_height_px
    )

    def distance(interval: FiniteInterval) -> float:
        if interval.contains(expected):
            return 0.0
        return min(
            abs(expected - interval.minimum),
            abs(expected - interval.maximum),
        )

    compatible: list[tuple[float, _Candidate]] = []
    for opposite in opposite_bindings:
        if (
            opposite.role == anchor.role
            or opposite.role_authorized
            or opposite.independent_support_region_count
            < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            or (
                source_direction is None
                and not _single_direction_ready(opposite)
            )
            or _longitudinal_domain_count(
                opposite.trace_coordinates_px,
                longitudinal_support_domains_px,
            )
            < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        ):
            continue
        localized = replace(
            opposite,
            evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
            role_authorized=True,
        )
        top, bottom = (
            (anchor, localized)
            if anchor.role == BoundaryRole.TOP
            else (localized, anchor)
        )
        candidate = _direct_candidate(
            top,
            bottom,
            fixed_height=fixed_height,
            canonical_height_px=canonical_height_px,
            center=center,
            minimum_shared_trace_support=minimum_shared_trace_support,
            source_direction=source_direction,
        )
        if candidate is None:
            continue
        # This direct pair is the only authority allowed to narrow the source
        # H state.  It remains one shared height for every frame.
        candidate = replace(
            candidate,
            canonical_height_px=candidate.height_compatibility.center,
        )
        compatible.append((distance(localized.full_interval_px), candidate))
    if not compatible:
        return ()
    nearest = min(item[0] for item in compatible)
    return tuple(
        candidate
        for value, candidate in compatible
        if abs(value - nearest) <= 1.0e-9
    )


def _covers_template_domains(
    binding: CrossRoleBinding,
    domains: tuple[FiniteInterval, ...],
) -> bool:
    """Whether one role-authorized side is observed across every frame domain."""

    return bool(domains) and binding.role_authorized and all(
        any(domain.contains(float(trace), epsilon=0.5) for trace in binding.trace_coordinates_px)
        for domain in domains
    )


def _longitudinal_domain_count(
    traces: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> int:
    return sum(
        any(domain.contains(float(trace), epsilon=0.5) for trace in traces)
        for domain in domains
    )


def _fit_from_candidate(
    candidate: _Candidate,
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    lane_reference_trace_px: float,
) -> CrossFit:
    top = candidate.top
    bottom = candidate.bottom
    if candidate.direct_pair:
        top_fit = top.fit_interval_px
        bottom_fit = bottom.fit_interval_px
        observed_center = _midpoint_interval(
            top.full_interval_px,
            bottom.full_interval_px,
        ).center
        top_canonical = observed_center - candidate.canonical_height_px / 2.0
        bottom_canonical = observed_center + candidate.canonical_height_px / 2.0
        top_full = _hull_intervals(
            (top.full_interval_px, FiniteInterval.exact(top_canonical))
        )
        bottom_full = _hull_intervals(
            (bottom.full_interval_px, FiniteInterval.exact(bottom_canonical))
        )
        direct = (top, bottom)
        inferred: tuple[CrossRoleBinding, ...] = ()
    elif top.role == BoundaryRole.TOP:
        inferred_height = FiniteInterval.exact(candidate.canonical_height_px)
        top_full = candidate.top_full_override or top.full_interval_px
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else _add(top.full_interval_px, inferred_height)
        )
        top_fit = _intersect(top.fit_interval_px, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        bottom_fit = _add(top.fit_interval_px, inferred_height)
        bottom_fit = _intersect(bottom_fit, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        direct = (top,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.BOTTOM,
                run_id=f"inferred:{top.run_id}:bottom",
                observation_id=top.observation_id,
                coordinate_interval_px=_add(top.coordinate_interval_px, inferred_height),
                trace_coordinates_px=top.trace_coordinates_px,
                support_fraction=top.support_fraction,
                continuous_support_fraction=top.continuous_support_fraction,
                fit_residual_px=top.fit_residual_px,
                fit_interval_px=bottom_fit,
                full_interval_px=bottom_full,
                canonical_direction_degrees=top.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    top.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=top.full_direction_interval_degrees,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(top.observation_id,),
                independent_support_region_count=top.independent_support_region_count,
                source_spanning_continuous=top.source_spanning_continuous,
                role_authorized=top.role_authorized,
            ),
        )
    else:
        inferred_height = FiniteInterval.exact(candidate.canonical_height_px)
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else bottom.full_interval_px
        )
        top_full = (
            candidate.top_full_override
            or _subtract(bottom.full_interval_px, inferred_height)
        )
        bottom_fit = _intersect(bottom.fit_interval_px, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        top_fit = _subtract(bottom.fit_interval_px, inferred_height)
        top_fit = _intersect(top_fit, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        direct = (bottom,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.TOP,
                run_id=f"inferred:{bottom.run_id}:top",
                observation_id=bottom.observation_id,
                coordinate_interval_px=_subtract(bottom.coordinate_interval_px, inferred_height),
                trace_coordinates_px=bottom.trace_coordinates_px,
                support_fraction=bottom.support_fraction,
                continuous_support_fraction=bottom.continuous_support_fraction,
                fit_residual_px=bottom.fit_residual_px,
                fit_interval_px=top_fit,
                full_interval_px=top_full,
                canonical_direction_degrees=bottom.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    bottom.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=bottom.full_direction_interval_degrees,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(bottom.observation_id,),
                independent_support_region_count=bottom.independent_support_region_count,
                source_spanning_continuous=bottom.source_spanning_continuous,
                role_authorized=bottom.role_authorized,
            ),
        )
    if not candidate.direct_pair:
        top_canonical = candidate.shift_interval.center
        bottom_canonical = top_canonical + candidate.canonical_height_px
    selected_direction = candidate.source_direction or _direction_for(
        direct,
        parallel_interval=candidate.direction_interval,
    )
    return CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=lane_reference_trace_px,
        fixed_height_px=fixed_height,
        top_canonical_px=top_canonical,
        bottom_canonical_px=bottom_canonical,
        top_fit_interval_px=top_fit,
        bottom_fit_interval_px=bottom_fit,
        top_full_interval_px=top_full,
        bottom_full_interval_px=bottom_full,
        direct_bindings=direct,
        inferred_bindings=inferred,
        selected_direction=selected_direction,
        direct_pair=candidate.direct_pair,
        shared_trace_support_count=candidate.shared_support,
        continuous_support_fraction=candidate.continuous_support,
        residual_sum_px=candidate.residual,
        center_compatible=candidate.center_compatible,
        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        height_compatibility_px=candidate.height_compatibility,
        shift_interval_px=candidate.shift_interval,
        center_interval_px=candidate.center_interval,
        parallel_direction_interval_degrees=candidate.direction_interval,
        direction_provenance_ids=(selected_direction.selected_observation_ids if selected_direction is not None else ()),
        single_side_inferred=not candidate.direct_pair,
        independent_support_region_count=candidate.shared_support,
    )


def _same_physical_group(left: _Candidate, right: _Candidate) -> bool:
    if left.direct_pair != right.direct_pair:
        return False
    left_ids = {left.top.observation_id, left.bottom.observation_id}
    right_ids = {right.top.observation_id, right.bottom.observation_id}
    if left_ids.isdisjoint(right_ids):
        # Nearby local closures are still discrete answers unless the ledger
        # proves that they are connected through the same direct physical
        # anchor.  Spatial region coverage alone cannot create that missing
        # relationship.
        return False
    if _intersect(left.shift_interval, right.shift_interval) is None:
        return False
    if _intersect(
        left.height_compatibility,
        right.height_compatibility,
    ) is None:
        return False
    if left.center_compatible != right.center_compatible:
        return False
    if left.center_interval is None or right.center_interval is None:
        if left.center_interval is not None or right.center_interval is not None:
            return False
    elif _intersect(left.center_interval, right.center_interval) is None:
        return False
    if left.direction_interval is None or right.direction_interval is None:
        return left.direction_interval is None and right.direction_interval is None
    return _intersect(left.direction_interval, right.direction_interval) is not None


def _common_interval(
    intervals: Sequence[FiniteInterval],
) -> FiniteInterval | None:
    if not intervals:
        return None
    common = intervals[0]
    for interval in intervals[1:]:
        common = _intersect(common, interval)
        if common is None:
            return None
    return common


def _merge_group_interval(
    intervals: Sequence[FiniteInterval],
) -> FiniteInterval | None:
    common = _common_interval(intervals)
    if common is not None:
        return common
    if not intervals:
        return None
    minimum = min(item.minimum for item in intervals)
    maximum = max(item.maximum for item in intervals)
    ordered = sorted(intervals, key=lambda item: item.minimum)
    if any(
        right.minimum > left.maximum
        for left, right in zip(ordered, ordered[1:])
    ):
        return None
    return FiniteInterval(minimum, maximum)


def _group_candidates(candidates: Sequence[_Candidate]) -> tuple[tuple[_Candidate, ...], ...]:
    groups: list[list[_Candidate]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.shift_interval.center,
            str(item.top.observation_id),
            str(item.bottom.observation_id),
        ),
    ):
        for group in groups:
            heights = [item.height_compatibility for item in group] + [candidate.height_compatibility]
            directions = [
                item.direction_interval
                for item in group
                if item.direction_interval is not None
            ]
            if candidate.direction_interval is not None:
                directions.append(candidate.direction_interval)
            common_direction = (
                _merge_group_interval(directions)
                if directions
                else None
            )
            direction_shape_matches = (
                all(item.direction_interval is None for item in group)
                and candidate.direction_interval is None
            ) or (
                all(item.direction_interval is not None for item in group)
                and candidate.direction_interval is not None
                and common_direction is not None
            )
            # A shared direct observation is one physical anchor, not another
            # vote.  Candidate pairs connected through that same top or bottom
            # role describe one closure network whose model uncertainty is
            # continuous.  Pairs with no shared identity remain discrete even
            # when their coordinates happen to be nearby.
            if any(
                _same_physical_group(item, candidate) for item in group
            ) and direction_shape_matches:
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return tuple(tuple(group) for group in groups)


def _group_direction(
    group: Sequence[_Candidate],
) -> SharedStripDirection | None:
    source_directions = tuple(
        candidate.source_direction
        for candidate in group
        if candidate.source_direction is not None
    )
    if source_directions:
        identity = source_directions[0].direction_id
        if (
            len(source_directions) != len(group)
            or any(item.direction_id != identity for item in source_directions)
        ):
            return None
        return source_directions[0]
    bindings: list[CrossRoleBinding] = []
    seen: set[ObservationId] = set()
    for candidate in group:
        direct = (candidate.top, candidate.bottom) if candidate.direct_pair else (candidate.top,)
        for binding in direct:
            if binding.observation_id in seen:
                continue
            seen.add(binding.observation_id)
            bindings.append(binding)
    if not bindings or any(
        item.fit_direction_interval_degrees is None
        or item.full_direction_interval_degrees is None
        or item.canonical_direction_degrees is None
        for item in bindings
    ):
        return None
    full_intervals = tuple(item.full_direction_interval_degrees for item in bindings)
    assert all(interval is not None for interval in full_intervals)
    common = _merge_group_interval(
        tuple(
            candidate.direction_interval
            for candidate in group
            if candidate.direction_interval is not None
        )
    )
    if common is None:
        return None
    identities = tuple(item.observation_id for item in bindings)
    spanning_intervals = tuple(
        item.full_direction_interval_degrees
        for item in bindings
        if item.source_spanning_continuous
    )
    safety_intervals = spanning_intervals or full_intervals
    safety = FiniteInterval(
        min(interval.minimum for interval in safety_intervals),
        max(interval.maximum for interval in safety_intervals),
    )
    canonical_interval = _intersect(common, safety)
    if canonical_interval is None:
        return None
    canonical = min(
        canonical_interval.maximum,
        max(
            canonical_interval.minimum,
            sum(float(item.canonical_direction_degrees) for item in bindings)
            / len(bindings),
        ),
    )
    return SharedStripDirection(
        direction_id="template-cross-direction:" + ":".join(map(str, identities)),
        selected_observation_ids=identities,
        full_angle_interval_degrees=safety,
        observed_angle_interval_degrees=FiniteInterval(
            min(interval.minimum for interval in full_intervals),
            max(interval.maximum for interval in full_intervals),
        ),
        canonical_angle_degrees=canonical,
    )


def _fit_from_group(
    group: Sequence[_Candidate],
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    lane_reference_trace_px: float,
    registered_trace_coordinates_px: tuple[int, ...],
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
) -> CrossFit:
    """Collapse one continuous physical group without hulling alternatives."""

    def support_region_count(traces: tuple[int, ...]) -> int:
        count = independent_spatial_support_count(
            registered_trace_coordinates_px,
            traces,
        )
        count = max(count, support_domain_count(traces))
        return min(SPATIAL_SUPPORT_REGION_COUNT, count)

    def support_domain_count(traces: tuple[int, ...]) -> int:
        if not longitudinal_support_domains_px:
            return 0
        return min(
            SPATIAL_SUPPORT_REGION_COUNT,
            sum(
                any(
                    domain.contains(float(trace), epsilon=0.5)
                    for trace in traces
                )
                for domain in longitudinal_support_domains_px
            ),
        )

    def role_authorized_pair_domain_count(
        candidates: Sequence[_Candidate],
    ) -> int:
        return max(
            (
                support_domain_count(candidate.support_trace_coordinates_px)
                for candidate in candidates
                if candidate.direct_pair
                and candidate.top.role_authorized
                and candidate.bottom.role_authorized
            ),
            default=0,
        )

    role_authorized_group = tuple(
        candidate
        for candidate in group
        if candidate.direct_pair
        and candidate.top.role_authorized
        and candidate.bottom.role_authorized
        and support_domain_count(candidate.support_trace_coordinates_px)
        >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, template.count)
    )
    if role_authorized_group:
        group = role_authorized_group

    representative = _fit_from_candidate(
        group[0],
        template=template,
        fixed_height=fixed_height,
        lane_reference_trace_px=lane_reference_trace_px,
    )

    if len(group) == 1:
        candidate = group[0]
        direct = (
            (candidate.top, candidate.bottom)
            if candidate.direct_pair
            else (candidate.top,)
        )
        support_traces = tuple(sorted(set(candidate.support_trace_coordinates_px)))
        return replace(
            representative,
            shared_trace_support_count=len(support_traces),
            direct_provenance_ids=tuple(item.observation_id for item in direct),
            independent_support_region_count=support_region_count(
                support_traces
            ),
            longitudinal_support_domain_count=support_domain_count(
                support_traces
            ),
            role_authorized_pair_support_domain_count=(
                role_authorized_pair_domain_count((candidate,))
            ),
        )
    top_fit = _hull_intervals(
        tuple(
            (item.top_full_override or item.top.fit_interval_px)
            if not item.direct_pair
            else item.top.fit_interval_px
            for item in group
        )
    )
    bottom_fit = _hull_intervals(
        tuple(
            (item.bottom_full_override or item.bottom.fit_interval_px)
            if not item.direct_pair
            else item.bottom.fit_interval_px
            for item in group
        )
    )
    top_full = _hull_intervals(
        tuple(
            item.top_full_override or item.top.full_interval_px
            for item in group
        )
    )
    bottom_full = _hull_intervals(
        tuple(
            item.bottom_full_override or item.bottom.full_interval_px
            for item in group
        )
    )
    shift = _hull_intervals(tuple(item.shift_interval for item in group))
    height_values = tuple(item.height_compatibility for item in group)
    height = _hull_intervals(height_values)
    centers = tuple(
        item.center_interval
        for item in group
        if item.center_interval is not None
    )
    center_interval = (
        _hull_intervals(centers)
        if centers
        else None
    )
    directions = tuple(
        item.direction_interval
        for item in group
        if item.direction_interval is not None
    )
    direction_interval = (
        _common_interval(directions)
        if directions
        else None
    )
    feasible_top = _common_interval(
        (
            shift,
            top_full,
            _subtract(bottom_full, height),
        )
    )
    if feasible_top is None:
        raise AssertionError("physical group has no canonical top closure")
    top_canonical = feasible_top.center
    feasible_height = _intersect(
        height,
        FiniteInterval(
            bottom_full.minimum - top_canonical,
            bottom_full.maximum - top_canonical,
        ),
    )
    if feasible_height is None:
        raise AssertionError("physical group has no canonical height closure")
    bottom_canonical = top_canonical + feasible_height.center
    direct_ids: list[ObservationId] = []
    seen: set[ObservationId] = set()
    for candidate in group:
        direct = (candidate.top, candidate.bottom) if candidate.direct_pair else (candidate.top,)
        for binding in direct:
            if binding.observation_id not in seen:
                seen.add(binding.observation_id)
                direct_ids.append(binding.observation_id)
    inferred = representative.inferred_bindings
    if inferred and direct_ids:
        inferred = tuple(
            replace(item, source_observation_ids=tuple(direct_ids))
            for item in inferred
        )
    selected_direction = _group_direction(group)
    support_traces = tuple(
        sorted(
            {
                trace
                for item in group
                for trace in item.support_trace_coordinates_px
            }
        )
    )
    independent_regions = support_region_count(support_traces)
    return replace(
        representative,
        top_canonical_px=top_canonical,
        bottom_canonical_px=bottom_canonical,
        top_fit_interval_px=top_fit,
        bottom_fit_interval_px=bottom_fit,
        top_full_interval_px=top_full,
        bottom_full_interval_px=bottom_full,
        inferred_bindings=inferred,
        selected_direction=selected_direction,
        shared_trace_support_count=len(support_traces),
        continuous_support_fraction=min(item.continuous_support for item in group),
        residual_sum_px=max(item.residual for item in group),
        center_compatible=all(item.center_compatible for item in group),
        height_compatibility_px=height,
        shift_interval_px=shift,
        center_interval_px=center_interval,
        parallel_direction_interval_degrees=direction_interval,
        direction_provenance_ids=(
            selected_direction.selected_observation_ids
            if selected_direction is not None
            else ()
        ),
        direct_provenance_ids=tuple(direct_ids),
        independent_support_region_count=independent_regions,
        longitudinal_support_domain_count=support_domain_count(support_traces),
        role_authorized_pair_support_domain_count=(
            role_authorized_pair_domain_count(group)
        ),
    )
