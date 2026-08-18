from __future__ import annotations

from dataclasses import replace
import math
from typing import TYPE_CHECKING

from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import OUTPUT_PROTECTION_SPEC
from ..source_core import SourceLaneEvidence
from .model import BoundaryAxis, BoundaryRole, QueryPurpose
from .measurement_model import PhotoBoundaryMeasurementQuery
from .search_model import (
    PhotoEdgeSearchCorridor,
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorWindow,
)
from .template_model import template_role_refinement_radius_px
from .template_measurement_plan_model import (
    MeasurementIntentKind,
    TemplateMeasurementPlan,
)
from .axis_layout import source_axes
from ...run_local_identity import run_local_id

if TYPE_CHECKING:
    from .coarse_strip_support import CoarseStripSupport


def source_lane_box(
    lane: SourceLaneEvidence,
    layout: str,
) -> Box:
    work = lane.domain.work_box
    if layout == "horizontal":
        return work
    if layout == "vertical":
        return Box(
            left=work.top,
            top=work.left,
            right=work.bottom,
            bottom=work.right,
        )
    raise ValueError(f"unsupported source layout: {layout}")


def _stable_id(prefix: str, *parts: object) -> str:
    return run_local_id(prefix, *parts)


def build_top_bottom_search_corridors(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
    coarse_support: "CoarseStripSupport",
) -> tuple[PhotoEdgeSearchCorridor, PhotoEdgeSearchCorridor]:
    """Project the compiler-owned short-axis query plan."""

    if (
        measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
        or coarse_support.lane_id != lane.domain.lane_id
    ):
        raise ValueError("corridors require the compiled lane plan")
    _long_axis, short_axis = source_axes(layout)
    projected = measurement_plan.projected_queries
    long_support = coarse_support.long_axis.interval_px
    retained_indices = tuple(
        index
        for index, trace in enumerate(projected.cross_trace_positions_px)
        if long_support.contains(float(trace), epsilon=0.5)
    )
    if not retained_indices:
        raise ValueError("coarse strip support contains no cross trace")
    traces = tuple(projected.cross_trace_positions_px[index] for index in retained_indices)
    short_direct = coarse_support.short_axis.direct_interval_px
    if short_direct is None:
        top_core = tuple(projected.top_core_intervals_px[index] for index in retained_indices)
        top_measured = tuple(
            projected.top_measurement_intervals_px[index]
            for index in retained_indices
        )
        bottom_core = tuple(
            projected.bottom_core_intervals_px[index]
            for index in retained_indices
        )
        bottom_measured = tuple(
            projected.bottom_measurement_intervals_px[index]
            for index in retained_indices
        )
    else:
        authority = coarse_support.short_axis.interval_px
        allowance = max(
            float(projected.measurement_halo_px),
            (
                OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
                - 1.0
            )
            * measurement_plan.template_spec.frame_height_px.maximum,
        )
        top_value = short_direct.minimum
        bottom_value = short_direct.maximum

        def local(value: float, extra: float = 0.0) -> FiniteInterval:
            return FiniteInterval(
                max(authority.minimum, value - allowance - extra),
                min(authority.maximum, value + allowance + extra),
            )

        top_one = local(top_value)
        bottom_one = local(bottom_value)
        top_core = tuple(FiniteInterval.exact(top_value) for _ in traces)
        top_measured = tuple(top_one for _ in traces)
        bottom_core = tuple(FiniteInterval.exact(bottom_value) for _ in traces)
        bottom_measured = tuple(bottom_one for _ in traces)
    return (
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                measurement_plan.plan_identity,
                BoundaryRole.TOP.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.TOP,
            boundary_axis=short_axis,
            trace_positions_px=traces,
            core_intervals_px=top_core,
            measurement_intervals_px=top_measured,
            measurement_halo_px=projected.measurement_halo_px,
        ),
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                measurement_plan.plan_identity,
                BoundaryRole.BOTTOM.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.BOTTOM,
            boundary_axis=short_axis,
            trace_positions_px=traces,
            core_intervals_px=bottom_core,
            measurement_intervals_px=bottom_measured,
            measurement_halo_px=projected.measurement_halo_px,
        ),
    )


def _merged_anchor_cores(
    intervals: tuple[FiniteInterval, ...],
) -> tuple[FiniteInterval, ...]:
    ordered = sorted(intervals, key=lambda item: item.minimum)
    merged: list[FiniteInterval] = []
    for item in ordered:
        if not merged or item.minimum > merged[-1].maximum + 1.0:
            merged.append(item)
            continue
        merged[-1] = FiniteInterval(
            merged[-1].minimum,
            max(merged[-1].maximum, item.maximum),
        )
    return tuple(merged)


def _anchor_windows(
    lane_id: str,
    support_interval_px: FiniteInterval,
    direct_interval_px: FiniteInterval | None,
    measurement_plan: TemplateMeasurementPlan,
) -> tuple[SequenceAnchorWindow, ...]:
    if support_interval_px.width <= 0.0:
        raise ValueError("anchor domain requires positive coarse support")

    def conservative_window() -> tuple[SequenceAnchorWindow, ...]:
        return (
            SequenceAnchorWindow(
                window_id=f"anchor-window:{lane_id}:conservative",
                core_px=FiniteInterval(
                    support_interval_px.minimum,
                    support_interval_px.maximum + 1.0,
                ),
                measurement_px=support_interval_px,
            ),
        )

    if direct_interval_px is None:
        return conservative_window()

    template = measurement_plan.template_spec
    width_px = (
        template.frame_width_px.minimum + template.frame_width_px.maximum
    ) / 2.0
    pitch_px = (template.pitch_px.minimum + template.pitch_px.maximum) / 2.0
    holder_span_px = width_px + (measurement_plan.full_count - 1) * pitch_px
    origins = tuple(
        sorted(
            {
                direct_interval_px.minimum,
                direct_interval_px.maximum - holder_span_px,
            }
        )
    )
    radius_px = template_role_refinement_radius_px(template.pitch_px.maximum)
    cores: list[FiniteInterval] = []
    for origin_px in origins:
        for slot_index in range(measurement_plan.full_count):
            frame_start_px = origin_px + slot_index * pitch_px
            for role_px in (frame_start_px, frame_start_px + width_px):
                minimum = max(support_interval_px.minimum, role_px - radius_px)
                maximum = min(support_interval_px.maximum, role_px + radius_px)
                if maximum > minimum:
                    cores.append(FiniteInterval(minimum, maximum))
    if not cores:
        return conservative_window()

    halo_px = float(measurement_plan.projected_queries.measurement_halo_px)
    return tuple(
        SequenceAnchorWindow(
            window_id=f"anchor-window:{lane_id}:{index}",
            core_px=FiniteInterval(
                core.minimum,
                core.maximum + 1.0,
            ),
            measurement_px=FiniteInterval(
                max(support_interval_px.minimum, core.minimum - halo_px),
                min(support_interval_px.maximum, core.maximum + halo_px),
            ),
        )
        for index, core in enumerate(_merged_anchor_cores(tuple(cores)))
    )


def build_sequence_anchor_discovery_domain(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
    coarse_support: "CoarseStripSupport",
) -> SequenceAnchorDiscoveryDomain:
    if (
        measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
        or coarse_support.lane_id != lane.domain.lane_id
    ):
        raise ValueError("anchor domain requires the compiled lane plan")
    projected = measurement_plan.projected_queries
    windows = _anchor_windows(
        lane.domain.lane_id,
        coarse_support.long_axis.interval_px,
        coarse_support.long_axis.direct_interval_px,
        measurement_plan,
    )
    query_order = tuple(window.window_id for window in windows)
    return SequenceAnchorDiscoveryDomain(
        domain_id=_stable_id(
            "sequence-anchor-domain",
            lane.domain.lane_id,
            measurement_plan.plan_identity,
        ),
        lane_id=lane.domain.lane_id,
        long_axis_extent_px=projected.long_extent_px,
        support_interval_px=coarse_support.long_axis.interval_px,
        authoritative_sequence_length=measurement_plan.full_count,
        windows=windows,
        query_execution_order=query_order,
    )


def registered_lane_measurement_queries(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    top_corridor: PhotoEdgeSearchCorridor,
    bottom_corridor: PhotoEdgeSearchCorridor,
    anchor_domain: SequenceAnchorDiscoveryDomain,
    measurement_plan: TemplateMeasurementPlan,
    registration_start: int = 0,
) -> tuple[PhotoBoundaryMeasurementQuery, ...]:
    """Pre-register top/bottom and finite theory-local anchor windows."""

    if (
        not isinstance(measurement_plan, TemplateMeasurementPlan)
        or measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
    ):
        raise ValueError("measurement queries require the compiled lane plan")
    intent_ids = {item.kind: item.intent_id for item in measurement_plan.query_intents}

    scales = lane.scan_canvas.axis_scales
    source_long_axis, source_short_axis = source_axes(layout)
    queries: list[PhotoBoundaryMeasurementQuery] = []
    for corridor, purpose in (
        (top_corridor, QueryPurpose.TOP_CORRIDOR),
        (bottom_corridor, QueryPurpose.BOTTOM_CORRIDOR),
    ):
        queries.append(
            PhotoBoundaryMeasurementQuery(
                query_id=f"query:{measurement_plan.plan_identity}:{corridor.corridor_id}",
                registration_index=0,
                lane_id=lane.domain.lane_id,
                purpose=purpose,
                boundary_axis=source_short_axis,
                trace_positions_px=corridor.trace_positions_px,
                search_intervals_px=corridor.measurement_intervals_px,
                transition_ownership_intervals_px=(
                    corridor.measurement_intervals_px
                ),
                expected_support_px=measurement_plan.template_spec.frame_width_px.maximum,
                boundary_axis_scale_px_per_mm=(
                    scales.height_axis_px_per_mm
                ),
                trace_axis_scale_px_per_mm=(
                    scales.width_axis_px_per_mm
                ),
                measurement_halo_px=corridor.measurement_halo_px,
                registration_provenance_ids=(
                    corridor.corridor_id,
                    intent_ids[
                        MeasurementIntentKind.TOP
                        if purpose == QueryPurpose.TOP_CORRIDOR
                        else MeasurementIntentKind.BOTTOM
                    ],
                ),
            )
        )
    short_traces = measurement_plan.projected_queries.sequence_trace_positions_px
    baseline_interval = anchor_domain.support_interval_px
    queries.append(
        PhotoBoundaryMeasurementQuery(
            query_id=f"query:{measurement_plan.plan_identity}:{anchor_domain.domain_id}:baseline",
            registration_index=0,
            lane_id=lane.domain.lane_id,
            purpose=QueryPurpose.SEQUENCE_BASELINE,
            boundary_axis=source_long_axis,
            trace_positions_px=short_traces,
            search_intervals_px=tuple(
                baseline_interval for _trace in short_traces
            ),
            transition_ownership_intervals_px=tuple(
                baseline_interval for _trace in short_traces
            ),
            expected_support_px=measurement_plan.template_spec.frame_height_px.maximum,
            boundary_axis_scale_px_per_mm=scales.width_axis_px_per_mm,
            trace_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
            measurement_halo_px=measurement_plan.projected_queries.measurement_halo_px,
            registration_provenance_ids=(
                anchor_domain.domain_id,
                intent_ids[MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR],
                intent_ids[MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR],
                intent_ids[MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR],
                intent_ids[MeasurementIntentKind.LATE_SEQUENCE_ANCHOR],
            ),
        )
    )
    windows_by_id = {
        window.window_id: window for window in anchor_domain.windows
    }
    # Every window is pre-registered before template placement begins.
    for window_id in anchor_domain.query_execution_order:
        window = windows_by_id[window_id]
        source_long_extent = (
            source_lane_box(lane, layout).right
            if source_long_axis == BoundaryAxis.X
            else source_lane_box(lane, layout).bottom
        )
        measured_interval = FiniteInterval(
            window.measurement_px.minimum,
            min(
                float(source_long_extent - 1),
                window.measurement_px.maximum,
            ),
        )
        owned_interval = FiniteInterval(
            window.core_px.minimum,
            min(
                float(source_long_extent - 1),
                max(window.core_px.minimum, window.core_px.maximum - 1.0),
            ),
        )
        queries.append(
            PhotoBoundaryMeasurementQuery(
                query_id=f"query:{measurement_plan.plan_identity}:{anchor_domain.domain_id}:{window.window_id}",
                registration_index=0,
                lane_id=lane.domain.lane_id,
                purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
                boundary_axis=source_long_axis,
                trace_positions_px=short_traces,
                search_intervals_px=tuple(
                    measured_interval for _trace in short_traces
                ),
                transition_ownership_intervals_px=tuple(
                    owned_interval for _trace in short_traces
                ),
                expected_support_px=measurement_plan.template_spec.frame_height_px.maximum,
                boundary_axis_scale_px_per_mm=(
                    scales.width_axis_px_per_mm
                ),
                trace_axis_scale_px_per_mm=(
                    scales.height_axis_px_per_mm
                ),
                measurement_halo_px=int(
                    max(
                        1.0,
                        math.ceil(
                            window.measurement_px.width
                            - window.core_px.width
                        ),
                    )
                ),
                registration_provenance_ids=(
                    anchor_domain.domain_id,
                    window.window_id,
                    intent_ids[MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.LATE_SEQUENCE_ANCHOR],
                ),
            )
        )
    return tuple(
        replace(
            query,
            registration_index=registration_start + index,
        )
        for index, query in enumerate(queries)
    )
