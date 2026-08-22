"""Bounded direct enclosing-support pairing for fixed-H cross geometry."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from ...domain import FiniteInterval
from ...formats import OUTPUT_PROTECTION_SPEC
from .interval_math import (
    intersect as _intersect,
    midpoint as _midpoint_interval,
    subtract as _subtract,
)
from .model import (
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .output_model import SharedStripDirection
from .template_cross_geometry import (
    direction_closure as _direction_closure,
    shared_direction_for as _direction_for,
)
from .template_cross_model import (
    CrossRoleBinding,
    EnclosingSupportPair,
)
from .template_model import TemplateSpec


class SupportFitStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    BOUND_EXCEEDED = "bound_exceeded"


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
    evaluated_candidate_count: int

    def __post_init__(self) -> None:
        if (
            self.evaluated_candidate_count < 0
            or (
                self.status == SupportFitStatus.RESOLVED
                and (self.best is None or self.runner_up is not None)
            )
            or (
                self.status == SupportFitStatus.BOUND_EXCEEDED
                and (self.best is not None or self.runner_up is not None)
            )
            or (self.reason is not None and not self.reason)
        ):
            raise ValueError("enclosing-support competition is invalid")


def _candidate(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    reference_trace_px: float,
    holder_center: FiniteInterval | None,
    registered_traces: tuple[int, ...],
    minimum_shared_trace_support: int,
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
) -> EnclosingSupportCandidate | None:
    if top.role != BoundaryRole.TOP or bottom.role != BoundaryRole.BOTTOM:
        return None
    # A pre-closed coarse pair cannot be detached.  Otherwise both sides must
    # remain role-unknown support observations; photo-aperture roles are never
    # reinterpreted after fitting.
    if (top.enclosing_pair_id is None) != (bottom.enclosing_pair_id is None):
        return None
    if (
        top.enclosing_pair_id is not None
        and top.enclosing_pair_id != bottom.enclosing_pair_id
    ):
        return None
    if (
        top.enclosing_pair_id is None
        and (top.role_authorized or bottom.role_authorized)
    ):
        return None
    if not top.trace_position_intervals_px or not bottom.trace_position_intervals_px:
        return None
    # Boundary use belongs to the selected pair, not permanently to either
    # raw line.  A line that can authorize an aperture may also serve as one
    # side of a directly observed enclosing rectangle.  When this path wins,
    # both sides are uniformly ENCLOSING_SUPPORT_PAIR (zero aperture bleed);
    # no output ever mixes aperture and support semantics edge by edge.
    top_by_trace = dict(
        zip(
            top.trace_coordinates_px,
            top.trace_position_intervals_px,
            strict=True,
        )
    )
    bottom_by_trace = dict(
        zip(
            bottom.trace_coordinates_px,
            bottom.trace_position_intervals_px,
            strict=True,
        )
    )
    traces = tuple(sorted(set(top_by_trace).intersection(bottom_by_trace)))
    if len(traces) < minimum_shared_trace_support:
        return None
    direction_interval, direction_ready, contradiction = _direction_closure(
        top,
        bottom,
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
    # A material/holder support may become the output boundary itself, so a
    # two-region local fragment cannot be extrapolated across the strip merely
    # because its trace coordinates happen to touch three template domains.
    directly_continuous = (
        top.independent_support_region_count >= SPATIAL_SUPPORT_REGION_COUNT
        and bottom.independent_support_region_count
        >= SPATIAL_SUPPORT_REGION_COUNT
    )
    connected = (
        directly_continuous
        and independent_regions >= SPATIAL_SUPPORT_REGION_COUNT
        and domains >= min(SPATIAL_SUPPORT_REGION_COUNT, template.count)
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
    # The broad physical-H interval is search compatibility, not the
    # aperture/support classifier. A role-unknown pair is usable only when it
    # directly contains canonical H and stays within the explicit 1.1H limit.
    if (
        span.minimum <= canonical_height_px
        or span.maximum
        > OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        * canonical_height_px
    ):
        return None
    aperture_center = center_interval.center
    aperture_top = aperture_center - canonical_height_px / 2.0
    aperture_bottom = aperture_center + canonical_height_px / 2.0
    if (
        top.full_interval_px.minimum > aperture_top + 1.0e-9
        or bottom.full_interval_px.maximum < aperture_bottom - 1.0e-9
    ):
        return None

    def straight_residual(
        binding: CrossRoleBinding,
        intervals: dict[int, FiniteInterval],
    ) -> float:
        slope = math.tan(
            math.radians(direction.canonical_angle_degrees)
        )
        reference = binding.full_interval_px.center
        return max(
            (
                max(
                    interval.minimum
                    - (
                        reference
                        + slope * (float(trace) - reference_trace_px)
                    ),
                    0.0,
                    (
                        reference
                        + slope * (float(trace) - reference_trace_px)
                    )
                    - interval.maximum,
                )
                for trace, interval in intervals.items()
            ),
            default=0.0,
        )

    pair = EnclosingSupportPair(
        top_canonical_px=top.full_interval_px.center,
        bottom_canonical_px=bottom.full_interval_px.center,
        top_full_interval_px=top.full_interval_px,
        bottom_full_interval_px=bottom.full_interval_px,
        top_provenance_ids=(top.observation_id,),
        bottom_provenance_ids=(bottom.observation_id,),
        observed_span_px=span,
        reference_trace_px=reference_trace_px,
        trace_coordinates_px=traces,
        top_trace_intervals_px=tuple(top_by_trace[trace] for trace in traces),
        bottom_trace_intervals_px=tuple(
            bottom_by_trace[trace] for trace in traces
        ),
        top_straight_model_residual_px=straight_residual(
            top,
            {trace: top_by_trace[trace] for trace in traces},
        ),
        bottom_straight_model_residual_px=straight_residual(
            bottom,
            {trace: bottom_by_trace[trace] for trace in traces},
        ),
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
    reference_trace_px: float,
    holder_center: FiniteInterval | None,
    top_bindings: Sequence[CrossRoleBinding],
    bottom_bindings: Sequence[CrossRoleBinding],
    registered_trace_coordinates_px: tuple[int, ...],
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
    minimum_shared_trace_support: int,
    maximum_evaluated_candidates: int,
) -> SupportFitCompetition:
    """Run a bounded support-pair sweep and retain discrete alternatives."""

    if maximum_evaluated_candidates < 0:
        raise ValueError("enclosing-support evaluation bound cannot be negative")
    if not top_bindings or not bottom_bindings:
        return SupportFitCompetition(
            None,
            None,
            SupportFitStatus.UNRESOLVED,
            "no two-sided support",
            0,
        )
    ordered_top = tuple(sorted(top_bindings, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
    ordered_bottom = tuple(sorted(bottom_bindings, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
    starts = tuple(item.full_interval_px.minimum for item in ordered_bottom)
    prefix_max: list[float] = []
    running = -math.inf
    for item in ordered_bottom:
        running = max(running, item.full_interval_px.maximum)
        prefix_max.append(running)
    support_bound = (
        OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        * canonical_height_px
    )
    candidates: list[EnclosingSupportCandidate] = []
    for top in ordered_top:
        lower = top.full_interval_px.maximum + canonical_height_px
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
                reference_trace_px=reference_trace_px,
                holder_center=holder_center,
                registered_traces=registered_trace_coordinates_px,
                minimum_shared_trace_support=minimum_shared_trace_support,
                longitudinal_support_domains_px=longitudinal_support_domains_px,
            )
            if candidate is not None:
                candidates.append(candidate)
                if len(candidates) > maximum_evaluated_candidates:
                    return SupportFitCompetition(
                        None,
                        None,
                        SupportFitStatus.BOUND_EXCEEDED,
                        "enclosing-support evaluated-fit bound exceeded",
                        len(candidates),
                    )
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
        return SupportFitCompetition(
            ordered[0],
            None,
            SupportFitStatus.RESOLVED,
            None,
            len(ordered),
        )
    if ordered:
        return SupportFitCompetition(
            ordered[0],
            ordered[1] if len(ordered) > 1 else None,
            SupportFitStatus.UNRESOLVED,
            "multiple enclosing support pairs remain",
            len(ordered),
        )
    return SupportFitCompetition(
        None,
        None,
        SupportFitStatus.UNRESOLVED,
        "no enclosing support pair",
        0,
    )
