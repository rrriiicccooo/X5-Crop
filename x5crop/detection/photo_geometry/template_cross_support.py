"""Bounded direct enclosing-support pairing for fixed-H cross geometry."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from ...domain import FiniteInterval
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .output_model import SharedStripDirection
from .template_cross_candidates import (
    _direction_closure,
    _direction_for,
    _shared_trace_coordinates,
)
from .template_cross_model import (
    CrossRoleBinding,
    EnclosingSupportPair,
    _intersect,
    _midpoint_interval,
    _subtract,
)
from .template_model import TemplateSpec


class SupportFitStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class EnclosingSupportCandidate:
    top_binding: CrossRoleBinding
    bottom_binding: CrossRoleBinding
    selected_direction: SharedStripDirection
    pair: EnclosingSupportPair
    shared_trace_support_count: int
    independent_support_region_count: int
    longitudinal_support_domain_count: int


@dataclass(frozen=True)
class SupportFitCompetition:
    best: EnclosingSupportCandidate | None
    runner_up: EnclosingSupportCandidate | None
    status: SupportFitStatus
    reason: str | None


def _candidate(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    holder_center: FiniteInterval | None,
    registered_traces: tuple[int, ...],
    minimum_shared_trace_support: int,
    parallel_direction_tolerance_degrees: float,
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
) -> EnclosingSupportCandidate | None:
    if top.role != BoundaryRole.TOP or bottom.role != BoundaryRole.BOTTOM:
        return None
    traces = _shared_trace_coordinates(top, bottom)
    if len(traces) < minimum_shared_trace_support:
        return None
    direction_interval, direction_ready, contradiction = _direction_closure(
        top,
        bottom,
        parallel_tolerance_degrees=parallel_direction_tolerance_degrees,
    )
    if contradiction or not direction_ready:
        return None
    direction = _direction_for(
        (top, bottom),
        parallel_interval=direction_interval,
    )
    if direction is None:
        return None
    independent_regions = min(
        SPATIAL_SUPPORT_REGION_COUNT,
        independent_spatial_support_count(registered_traces, traces),
    )
    domains = min(
        SPATIAL_SUPPORT_REGION_COUNT,
        sum(
            any(domain.contains(float(trace), epsilon=0.5) for trace in traces)
            for domain in longitudinal_support_domains_px
        ),
    )
    source_spanning = top.source_spanning_continuous and bottom.source_spanning_continuous
    connected = (
        independent_regions >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        and domains >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, template.count)
    )
    if not source_spanning and not connected:
        return None
    midpoint = _midpoint_interval(top.full_interval_px, bottom.full_interval_px)
    center_interval = (
        _intersect(midpoint, holder_center)
        if holder_center is not None
        else midpoint
    )
    if center_interval is None:
        return None
    span = _subtract(bottom.full_interval_px, top.full_interval_px)
    if span.minimum <= fixed_height.maximum or span.maximum > 1.1 * fixed_height.minimum:
        return None
    aperture_center = center_interval.center
    aperture_top = aperture_center - canonical_height_px / 2.0
    aperture_bottom = aperture_center + canonical_height_px / 2.0
    if (
        top.full_interval_px.minimum > aperture_top + 1.0e-9
        or bottom.full_interval_px.maximum < aperture_bottom - 1.0e-9
    ):
        return None
    pair = EnclosingSupportPair(
        top_canonical_px=top.full_interval_px.center,
        bottom_canonical_px=bottom.full_interval_px.center,
        top_full_interval_px=top.full_interval_px,
        bottom_full_interval_px=bottom.full_interval_px,
        top_provenance_ids=(top.observation_id,),
        bottom_provenance_ids=(bottom.observation_id,),
        observed_span_px=span,
    )
    return EnclosingSupportCandidate(
        top_binding=top,
        bottom_binding=bottom,
        selected_direction=direction,
        pair=pair,
        shared_trace_support_count=len(traces),
        independent_support_region_count=independent_regions,
        longitudinal_support_domain_count=domains,
    )


def fit_enclosing_support(
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    holder_center: FiniteInterval | None,
    top_bindings: Sequence[CrossRoleBinding],
    bottom_bindings: Sequence[CrossRoleBinding],
    registered_trace_coordinates_px: tuple[int, ...],
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
    minimum_shared_trace_support: int,
    parallel_direction_tolerance_degrees: float,
) -> SupportFitCompetition:
    """Run a bounded support-pair sweep and retain discrete alternatives."""

    if not top_bindings or not bottom_bindings:
        return SupportFitCompetition(None, None, SupportFitStatus.UNRESOLVED, "no two-sided support")
    ordered_top = tuple(sorted(top_bindings, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
    ordered_bottom = tuple(sorted(bottom_bindings, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
    starts = tuple(item.full_interval_px.minimum for item in ordered_bottom)
    prefix_max: list[float] = []
    running = -math.inf
    for item in ordered_bottom:
        running = max(running, item.full_interval_px.maximum)
        prefix_max.append(running)
    support_bound = 1.1 * fixed_height.minimum
    candidates: list[EnclosingSupportCandidate] = []
    for top in ordered_top:
        lower = top.full_interval_px.maximum + fixed_height.maximum
        upper = top.full_interval_px.minimum + support_bound
        if lower > upper:
            continue
        index = bisect_left(prefix_max, lower)
        while index < len(ordered_bottom) and starts[index] <= upper:
            candidate = _candidate(
                top,
                ordered_bottom[index],
                template=template,
                fixed_height=fixed_height,
                canonical_height_px=canonical_height_px,
                holder_center=holder_center,
                registered_traces=registered_trace_coordinates_px,
                minimum_shared_trace_support=minimum_shared_trace_support,
                parallel_direction_tolerance_degrees=parallel_direction_tolerance_degrees,
                longitudinal_support_domains_px=longitudinal_support_domains_px,
            )
            if candidate is not None:
                candidates.append(candidate)
            index += 1
    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.pair.top_canonical_px,
                str(item.pair.top_provenance_ids[0]),
                str(item.pair.bottom_provenance_ids[0]),
            ),
        )
    )
    if len(ordered) == 1:
        return SupportFitCompetition(ordered[0], None, SupportFitStatus.RESOLVED, None)
    if ordered:
        return SupportFitCompetition(
            ordered[0],
            ordered[1] if len(ordered) > 1 else None,
            SupportFitStatus.UNRESOLVED,
            "multiple enclosing support pairs remain",
        )
    return SupportFitCompetition(None, None, SupportFitStatus.UNRESOLVED, "no enclosing support pair")


__all__ = [
    "EnclosingSupportCandidate",
    "SupportFitCompetition",
    "SupportFitStatus",
    "fit_enclosing_support",
]
