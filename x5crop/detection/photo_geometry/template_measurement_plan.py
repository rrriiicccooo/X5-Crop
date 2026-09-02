"""Compile one bounded template measurement plan from physical authority."""

from __future__ import annotations

import hashlib
import math

from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import (
    FORMAT_CATALOG_REVISION,
    FormatSpec,
    FramePhysicalSpec,
    OUTPUT_PROTECTION_SPEC,
)
from ..evidence.scan_canvas import CanvasAxisScaleIntervals
from ..source_core import SourceStripValidationDomain
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .source_geometry import centered_short_axis_authority_px
from .template_measurement_plan_model import (
    MAX_CROSS_FITTED_OBSERVATIONS,
    MAX_CROSS_PAIRS,
    MAX_CROSS_REGISTERED_RUNS_PER_ROLE,
    MAX_PHASE_OBSERVATIONS,
    MAX_PIXEL_COORDINATES,
    MAX_PLACEMENT_CHECKS,
    MAX_REGISTERED_QUERIES,
    MAX_WORK_UNITS,
    MeasurementAxis,
    MeasurementIntentKind,
    MeasurementUnit,
    TemplateCrossBounds,
    TemplateMeasurementPlan,
    TemplatePhaseBounds,
    TemplatePixelBounds,
    TemplatePlacementBounds,
    TemplateProjectedQueryPlan,
    TemplateQueryIntent,
    TemplateRoleBounds,
    TemplateWorkBounds,
)
from .template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
    generic_separator_gap_interval_px,
)
from .template_nominal_grid_authority import (
    compile_calibrated_nominal_grid_prior,
)


def compile_template_measurement_plan(
    *,
    format_spec: FormatSpec,
    frame_spec: FramePhysicalSpec,
    count: int,
    full_count: int,
    holder_full_count: int,
    lane_authority: SourceStripValidationDomain,
    layout: str,
    scale_authority: CanvasAxisScaleIntervals,
) -> TemplateMeasurementPlan:
    """Compile one fixed-format plan without touching pixels."""

    physical_identity = _stable_identity(
        "template-physical",
        FORMAT_CATALOG_REVISION,
        format_spec.format_id,
        frame_spec.identity_fields,
        (
            "nominal-pitch-calibration-unavailable"
            if format_spec.nominal_pitch_calibration is None
            else format_spec.nominal_pitch_calibration.identity_fields
        ),
        count,
        full_count,
        holder_full_count,
        lane_authority.lane_id,
        lane_authority.source_axis_long,
        lane_authority.authority_profile_id,
        layout,
    )
    width_factor_minimum, width_factor_maximum = (
        frame_spec.width_factor_bounds
    )
    height_factor_minimum, height_factor_maximum = (
        frame_spec.height_factor_bounds
    )
    frame_width_px = _scaled_extent(
        frame_spec.frame_width_mm,
        scale_authority.width_axis_px_per_mm,
        width_factor_minimum,
        width_factor_maximum,
    )
    frame_height_px = _scaled_extent(
        frame_spec.frame_height_mm,
        scale_authority.height_axis_px_per_mm,
        height_factor_minimum,
        height_factor_maximum,
    )
    gap_px = _gap_interval_px(
        frame_spec,
        scale_authority.width_axis_px_per_mm,
        frame_width_px,
    )
    pitch_px = FiniteInterval(
        frame_width_px.minimum + gap_px.minimum,
        frame_width_px.maximum + gap_px.maximum,
    )
    # The lane work box is canonical long-x/cross-y for both raw layouts.
    # source_axis_long records the raw TIFF axis and must not rotate the
    # already-canonical authority a second time.
    long_extent_px = lane_authority.work_box.width
    phase_lattice = PhaseLatticeAuthority(
        period_px=pitch_px,
        cycle_origin_px=0.0,
        minimum_slot_offset=-1,
        maximum_slot_offset=max(
            full_count,
            int(math.ceil(long_extent_px / pitch_px.minimum)) + 1,
        ),
    )
    template_spec = TemplateSpec(
        template_id=f"{physical_identity}:spec",
        frame_width_px=frame_width_px,
        frame_height_px=frame_height_px,
        pitch_px=pitch_px,
        nominal_gap_px=gap_px,
        count=count,
        phase_lattice_authority=phase_lattice,
    )
    calibrated_nominal_grid_prior = compile_calibrated_nominal_grid_prior(
        format_spec=format_spec,
        frame_spec=frame_spec,
        template_id=template_spec.template_id,
        scale_px_per_mm=scale_authority.width_axis_px_per_mm,
    )
    query_intents = _query_intents(
        physical_identity=physical_identity,
        frame_spec=frame_spec,
        count=count,
    )
    projected_queries = _project_queries(
        lane_authority.work_box,
        layout,
        frame_spec,
        frame_width_px,
        frame_height_px,
        scale_authority.width_axis_px_per_mm,
        scale_authority.height_axis_px_per_mm,
    )
    phase_bounds = TemplatePhaseBounds(
        max_hypotheses=MAX_PHASE_OBSERVATIONS * max(6, 2 * count),
        max_role_count=2 * count,
        max_direct_observations=MAX_PHASE_OBSERVATIONS,
    )
    role_bounds = TemplateRoleBounds(
        max_role_bindings=2 * count,
        max_inferred_roles=2 * count,
        max_adjacency_relations=max(0, count - 1),
    )
    cross_bounds = TemplateCrossBounds(
        max_registered_runs_per_role=MAX_CROSS_REGISTERED_RUNS_PER_ROLE,
        max_fitted_observations=MAX_CROSS_FITTED_OBSERVATIONS,
        max_compatible_pairs=MAX_CROSS_PAIRS,
        max_evaluated_fits=MAX_CROSS_PAIRS,
        max_inferred_observations=2,
    )
    placement_bounds = TemplatePlacementBounds(
        max_direction_candidates=2,
        max_placement_checks=MAX_PLACEMENT_CHECKS,
        max_safety_checks=count,
    )
    pixel_bounds, work_bounds = _bounds_for_lane(
        lane_authority.work_box,
        len(query_intents),
        count,
    )
    plan_identity = _stable_identity(
        "template-plan",
        physical_identity,
        tuple(
            (
                item.kind.value,
                item.axis.value,
                item.coordinate_unit.value,
                tuple((p.minimum, p.maximum) for p in item.coordinate_positions),
                item.trace_unit.value,
                tuple((p.minimum, p.maximum) for p in item.trace_positions),
                (item.search_margin_mm.minimum, item.search_margin_mm.maximum),
                (item.expected_span_mm.minimum, item.expected_span_mm.maximum),
            )
            for item in query_intents
        ),
        phase_bounds,
        role_bounds,
        cross_bounds,
        placement_bounds,
    )
    return TemplateMeasurementPlan(
        format_spec=format_spec,
        frame_spec=frame_spec,
        count=count,
        full_count=full_count,
        holder_full_count=holder_full_count,
        lane_id=lane_authority.lane_id,
        layout=layout,
        lane_authority=lane_authority,
        scale_authority=scale_authority,
        template_spec=template_spec,
        calibrated_nominal_grid_prior=calibrated_nominal_grid_prior,
        query_intents=query_intents,
        projected_queries=projected_queries,
        phase_bounds=phase_bounds,
        role_bounds=role_bounds,
        cross_bounds=cross_bounds,
        placement_bounds=placement_bounds,
        pixel_bounds=pixel_bounds,
        work_bounds=work_bounds,
        physical_identity=physical_identity,
        plan_identity=plan_identity,
    )


def _scaled_extent(
    design_mm: float,
    scale: PositiveInterval,
    factor_minimum: float,
    factor_maximum: float,
) -> PositiveInterval:
    return PositiveInterval(
        design_mm * factor_minimum * scale.minimum,
        design_mm * factor_maximum * scale.maximum,
    )


def _gap_interval_px(
    frame_spec: FramePhysicalSpec,
    scale: PositiveInterval,
    width_px: PositiveInterval,
) -> FiniteInterval:
    if frame_spec.format_gap_prior_mm is not None:
        return FiniteInterval(
            frame_spec.format_gap_prior_mm * scale.minimum,
            frame_spec.format_gap_prior_mm * scale.maximum,
        )
    # An absent format prior remains a bounded generic physical interval.  It
    # does not identify a format or authorize placement by itself.
    return generic_separator_gap_interval_px(width_px)


def _lattice_positions(
    minimum: int,
    maximum: int,
    spacing_px: float,
) -> tuple[int, ...]:
    if maximum <= minimum:
        raise ValueError("query lattice requires positive extent")
    step = max(1, int(round(spacing_px)))
    first = min(maximum - 1, minimum + step // 2)
    values = list(range(first, maximum, step))
    if values[-1] < maximum - 1 - step // 2:
        values.append(maximum - 1)
    return tuple(sorted(set(values)))


def _clip_interval(
    interval: FiniteInterval,
    minimum: float,
    maximum: float,
) -> FiniteInterval:
    return FiniteInterval(
        max(minimum, interval.minimum),
        min(maximum, interval.maximum),
    )


def _project_queries(
    work_box: Box,
    layout: str,
    frame_spec: FramePhysicalSpec,
    frame_width_px: PositiveInterval,
    frame_height_px: PositiveInterval,
    long_scale: PositiveInterval,
    short_scale: PositiveInterval,
) -> TemplateProjectedQueryPlan:
    if layout not in {"horizontal", "vertical"}:
        raise ValueError("query projection requires a canonical layout")
    # SourceStripValidationDomain.work_box is already expressed in the
    # canonical work image: long coordinates are x and short coordinates are
    # y for both layouts.  Registered measurement later maps those canonical
    # coordinates onto the source X/Y axes.  Rotating the box here a second
    # time swaps the extents for vertical scans and registers every query
    # outside its source authority.
    long_min, long_max = work_box.left, work_box.right
    short_min, short_max = work_box.top, work_box.bottom
    if long_min != 0:
        raise ValueError("compiled sequence authority must begin at long zero")
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    cross_traces = _lattice_positions(
        long_min,
        long_max,
        spec.lattice_spacing_mm(frame_spec.frame_width_mm) * long_scale.maximum,
    )
    short_authority = FiniteInterval(float(short_min), float(short_max - 1))
    center = centered_short_axis_authority_px(short_authority, short_scale)
    halo = spec.measurement_halo_px(short_scale.maximum)
    enclosing_extra = (
        OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio - 1.0
    ) * frame_height_px.maximum / 2.0
    top = _clip_interval(
        FiniteInterval(
            center.minimum - frame_height_px.maximum / 2.0,
            center.maximum - frame_height_px.minimum / 2.0,
        ),
        float(short_min),
        float(short_max - 1),
    )
    bottom = _clip_interval(
        FiniteInterval(
            center.minimum + frame_height_px.minimum / 2.0,
            center.maximum + frame_height_px.maximum / 2.0,
        ),
        float(short_min),
        float(short_max - 1),
    )
    top_measured = _clip_interval(
        FiniteInterval(
            top.minimum - halo - enclosing_extra,
            top.maximum + halo,
        ),
        float(short_min),
        float(short_max - 1),
    )
    bottom_measured = _clip_interval(
        FiniteInterval(
            bottom.minimum - halo,
            bottom.maximum + halo + enclosing_extra,
        ),
        float(short_min),
        float(short_max - 1),
    )
    short_center = (short_min + short_max - 1) / 2.0
    half_height = min(
        (short_max - short_min - 2) / 2.0,
        frame_height_px.minimum / 2.0 - halo,
    )
    sequence_traces = _lattice_positions(
        max(short_min, int(math.ceil(short_center - half_height))),
        min(short_max, int(math.floor(short_center + half_height)) + 1),
        spec.lattice_spacing_mm(frame_spec.frame_height_mm) * short_scale.maximum,
    )
    return TemplateProjectedQueryPlan(
        long_extent_px=long_max - long_min,
        cross_trace_positions_px=cross_traces,
        top_core_intervals_px=tuple(top for _ in cross_traces),
        top_measurement_intervals_px=tuple(top_measured for _ in cross_traces),
        bottom_core_intervals_px=tuple(bottom for _ in cross_traces),
        bottom_measurement_intervals_px=tuple(bottom_measured for _ in cross_traces),
        sequence_trace_positions_px=sequence_traces,
        sequence_measurement_interval_px=FiniteInterval(
            float(long_min),
            float(long_max - 1),
        ),
        sequence_ownership_interval_px=FiniteInterval(
            float(long_min),
            float(long_max - 1),
        ),
        measurement_halo_px=halo,
    )


def _query_intents(
    *,
    physical_identity: str,
    frame_spec: FramePhysicalSpec,
    count: int,
) -> tuple[TemplateQueryIntent, ...]:
    early = 1.0 / float(count + 1)
    sequence_positions = (
        (MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR, (0.0, 1.0)),
        (MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR, (early,)),
        (MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR, (0.5,)),
        (MeasurementIntentKind.LATE_SEQUENCE_ANCHOR, (1.0 - early,)),
    )
    margin = FiniteInterval(
        max(0.05, min(frame_spec.frame_width_mm, frame_spec.frame_height_mm) * 0.005),
        max(0.10, min(frame_spec.frame_width_mm, frame_spec.frame_height_mm) * 0.02),
    )
    intents: list[TemplateQueryIntent] = []
    for kind, axis in (
        (MeasurementIntentKind.COARSE_LONG_SUPPORT, MeasurementAxis.LONG),
        (MeasurementIntentKind.COARSE_SHORT_SUPPORT, MeasurementAxis.SHORT),
    ):
        intents.append(
            TemplateQueryIntent(
                intent_id=f"{physical_identity}:{kind.value}",
                kind=kind,
                axis=axis,
                coordinate_unit=MeasurementUnit.LANE_RATIO,
                coordinate_positions=(FiniteInterval(0.0, 1.0),),
                trace_unit=MeasurementUnit.LANE_RATIO,
                trace_positions=(
                    FiniteInterval.exact(0.1),
                    FiniteInterval.exact(0.3),
                    FiniteInterval.exact(0.5),
                    FiniteInterval.exact(0.7),
                    FiniteInterval.exact(0.9),
                ),
                search_margin_mm=margin,
                expected_span_mm=FiniteInterval.exact(
                    frame_spec.frame_width_mm
                    if axis == MeasurementAxis.LONG
                    else frame_spec.frame_height_mm
                ),
                registration_index=len(intents),
            )
        )
    for kind, positions in sequence_positions:
        intents.append(
            TemplateQueryIntent(
                intent_id=f"{physical_identity}:{kind.value}",
                kind=kind,
                axis=MeasurementAxis.LONG,
                coordinate_unit=MeasurementUnit.LANE_RATIO,
                coordinate_positions=tuple(FiniteInterval.exact(value) for value in positions),
                trace_unit=MeasurementUnit.LANE_RATIO,
                trace_positions=(FiniteInterval.exact(0.5),),
                search_margin_mm=margin,
                expected_span_mm=FiniteInterval.exact(frame_spec.frame_width_mm),
                registration_index=len(intents),
            )
        )
    for kind, position in (
        (MeasurementIntentKind.TOP, -frame_spec.frame_height_mm / 2.0),
        (MeasurementIntentKind.BOTTOM, frame_spec.frame_height_mm / 2.0),
    ):
        intents.append(
            TemplateQueryIntent(
                intent_id=f"{physical_identity}:{kind.value}",
                kind=kind,
                axis=MeasurementAxis.SHORT,
                coordinate_unit=MeasurementUnit.MILLIMETRES,
                coordinate_positions=(FiniteInterval.exact(position),),
                trace_unit=MeasurementUnit.LANE_RATIO,
                trace_positions=(FiniteInterval.exact(0.5),),
                search_margin_mm=margin,
                expected_span_mm=FiniteInterval.exact(frame_spec.frame_height_mm),
                registration_index=len(intents),
            )
        )
    return tuple(intents)


def _bounds_for_lane(
    work_box: Box,
    query_count: int,
    slot_count: int,
) -> tuple[TemplatePixelBounds, TemplateWorkBounds]:
    # Logical intent count and concrete query count are different contracts.
    # Current measurement can use many lattice traces under the eight compiled
    # intents, but it must still remain bounded by source dimensions before
    # any candidate exists.
    source_pixels = work_box.width * work_box.height
    coordinate_upper_bound = source_pixels * 16
    if coordinate_upper_bound <= 0 or coordinate_upper_bound > MAX_PIXEL_COORDINATES:
        raise ValueError("template pixel work bound exceeded")
    work_units = (
        query_count
        + (2 * slot_count)
        * MAX_PHASE_OBSERVATIONS
        * max(6, 2 * slot_count)
        + MAX_CROSS_PAIRS
        + MAX_PLACEMENT_CHECKS
    )
    if work_units > MAX_WORK_UNITS:
        raise ValueError("template work bound exceeded")
    pixel = TemplatePixelBounds(
        max_registered_queries=MAX_REGISTERED_QUERIES,
        max_trace_positions=2 * (work_box.width + work_box.height),
        max_coordinate_samples=coordinate_upper_bound,
        max_pixel_queries=source_pixels * 128,
        max_peak_temporary_bytes=source_pixels * 10 + 32 * 1024 * 1024,
    )
    return pixel, TemplateWorkBounds(
        max_query_intents=query_count,
        max_work_units=work_units,
    )


def _stable_identity(prefix: str, *parts: object) -> str:
    payload = repr(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return f"{prefix}:{digest}"
