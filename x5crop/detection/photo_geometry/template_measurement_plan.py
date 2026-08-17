"""Compile one bounded template measurement plan from physical authority."""

from __future__ import annotations

import hashlib
import math

from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import (
    FORMAT_CATALOG_REVISION,
    FRAME_DIMENSION_TOLERANCE_SPEC,
    FormatSpec,
    FramePhysicalSpec,
)
from ..evidence.scan_canvas import CanvasAxisScaleIntervals
from ..source_core import SourceStripValidationDomain
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .source_geometry import centered_short_axis_authority_px
from .template_measurement_plan_model import (
    MAX_CROSS_PAIRS,
    MAX_PHASE_OBSERVATIONS,
    MAX_PIXEL_COORDINATES,
    MAX_PLACEMENT_CHECKS,
    MAX_QUERY_INTENTS,
    MAX_REGISTERED_QUERIES,
    MAX_WORK_UNITS,
    MeasurementAxis,
    MeasurementIntentKind,
    MeasurementUnit,
    TemplateCompileReceipt,
    TemplateCrossBounds,
    TemplateMeasurementInputs,
    TemplateMeasurementPlan,
    TemplateNormalPathStopFacts,
    TemplatePhaseBounds,
    TemplatePixelBounds,
    TemplatePlacementBounds,
    TemplateProjectedQueryPlan,
    TemplateQueryIntent,
    TemplateRoleBounds,
    TemplateStopFact,
    TemplateWorkBounds,
)
from .template_model import PhaseLatticeAuthority, TemplateSpec

def compile_template_measurement_plan(
    *,
    format_spec: FormatSpec,
    frame_spec: FramePhysicalSpec,
    count: int,
    full_count: int,
    holder_full_count: int | None = None,
    lane_authority: SourceStripValidationDomain,
    layout: str,
    scale_authority: CanvasAxisScaleIntervals,
) -> TemplateMeasurementPlan:
    """Compile one fixed-format plan without touching pixels."""

    if holder_full_count is None:
        holder_full_count = full_count
    inputs = TemplateMeasurementInputs(
        format_spec=format_spec,
        frame_spec=frame_spec,
        count=count,
        full_count=full_count,
        holder_full_count=holder_full_count,
        lane_authority=lane_authority,
        layout=layout,
        scale_authority=scale_authority,
    )
    physical_identity = _stable_identity(
        "template-physical",
        FORMAT_CATALOG_REVISION,
        inputs.format_spec.format_id,
        inputs.frame_spec.identity_fields,
        inputs.count,
        inputs.full_count,
        inputs.holder_full_count,
        inputs.lane_authority.lane_id,
        inputs.lane_authority.source_axis_long,
        inputs.lane_authority.authority_profile_id,
        inputs.layout,
    )
    frame_width_px = _scaled_extent(
        inputs.frame_spec.frame_width_mm,
        inputs.scale_authority.width_axis_px_per_mm,
        FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
    )
    frame_height_px = _scaled_extent(
        inputs.frame_spec.frame_height_mm,
        inputs.scale_authority.height_axis_px_per_mm,
        FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
    )
    gap_px = _gap_interval_px(
        inputs.frame_spec,
        inputs.scale_authority.width_axis_px_per_mm,
        frame_width_px,
    )
    pitch_px = FiniteInterval(
        frame_width_px.minimum + gap_px.minimum,
        frame_width_px.maximum + gap_px.maximum,
    )
    long_extent_px = (
        inputs.lane_authority.work_box.width
        if inputs.lane_authority.source_axis_long == "x"
        else inputs.lane_authority.work_box.height
    )
    phase_lattice = PhaseLatticeAuthority(
        period_px=pitch_px,
        cycle_origin_px=0.0,
        minimum_slot_offset=-1,
        maximum_slot_offset=max(
            inputs.full_count,
            int(math.ceil(long_extent_px / pitch_px.minimum)) + 1,
        ),
    )
    template_spec = TemplateSpec(
        template_id=f"{physical_identity}:spec",
        frame_width_px=frame_width_px,
        frame_height_px=frame_height_px,
        pitch_px=pitch_px,
        nominal_gap_px=gap_px,
        count=inputs.count,
        phase_lattice_authority=phase_lattice,
    )
    query_intents = _query_intents(
        physical_identity=physical_identity,
        frame_spec=inputs.frame_spec,
        count=inputs.count,
    )
    projected_queries = _project_queries(
        inputs.lane_authority.work_box,
        inputs.layout,
        inputs.frame_spec,
        frame_width_px,
        frame_height_px,
        inputs.scale_authority.width_axis_px_per_mm,
        inputs.scale_authority.height_axis_px_per_mm,
    )
    phase_bounds = TemplatePhaseBounds(
        max_hypotheses=MAX_PHASE_OBSERVATIONS * max(6, 2 * inputs.count),
        max_role_count=2 * inputs.count,
        max_direct_observations=MAX_PHASE_OBSERVATIONS,
    )
    role_bounds = TemplateRoleBounds(
        max_role_bindings=2 * inputs.count,
        max_inferred_roles=2 * inputs.count,
        max_local_relations=max(0, inputs.count - 1),
    )
    cross_bounds = TemplateCrossBounds(
        max_registered_runs=MAX_PHASE_OBSERVATIONS,
        max_fitted_observations=MAX_PHASE_OBSERVATIONS,
        max_compatible_pairs=MAX_CROSS_PAIRS,
        max_evaluated_fits=MAX_CROSS_PAIRS,
        max_inferred_observations=2,
    )
    placement_bounds = TemplatePlacementBounds(
        max_direction_candidates=2,
        max_placement_checks=MAX_PLACEMENT_CHECKS,
        max_safety_checks=inputs.count,
    )
    pixel_bounds, work_bounds = _bounds_for_lane(
        inputs.lane_authority.work_box,
        len(query_intents),
        inputs.count,
    )
    if 2 * inputs.count > phase_bounds.max_role_count:
        raise ValueError("template phase role bound overflow")
    facts = (
        TemplateStopFact.FIXED_FORMAT_TEMPLATE,
        TemplateStopFact.DIRECT_PHASE_EVIDENCE_REQUIRED,
        TemplateStopFact.REGISTERED_QUERY_SET_COMPLETE,
        TemplateStopFact.NO_PIXEL_ACCESS_DURING_COMPILE,
    )
    stop_facts = TemplateNormalPathStopFacts(
        requires_direct_phase_evidence=True,
        facts=facts,
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
    receipt = TemplateCompileReceipt(
        physical_identity=physical_identity,
        plan_identity=plan_identity,
        query_count=len(query_intents),
        role_count=2 * inputs.count,
        cross_fit_upper_bound=cross_bounds.max_evaluated_fits,
        placement_check_count=MAX_PLACEMENT_CHECKS,
        pixel_coordinate_upper_bound=pixel_bounds.max_coordinate_samples,
        work_unit_upper_bound=work_bounds.max_work_units,
        pixel_read_count=0,
        prevalidated=True,
    )
    return TemplateMeasurementPlan(
        format_spec=inputs.format_spec,
        frame_spec=inputs.frame_spec,
        count=inputs.count,
        full_count=inputs.full_count,
        holder_full_count=inputs.holder_full_count,
        lane_id=inputs.lane_authority.lane_id,
        layout=inputs.layout,
        lane_authority=inputs.lane_authority,
        scale_authority=inputs.scale_authority,
        template_spec=template_spec,
        query_intents=query_intents,
        projected_queries=projected_queries,
        phase_bounds=phase_bounds,
        role_bounds=role_bounds,
        cross_bounds=cross_bounds,
        placement_bounds=placement_bounds,
        pixel_bounds=pixel_bounds,
        work_bounds=work_bounds,
        normal_path_stop_facts=stop_facts,
        physical_identity=physical_identity,
        plan_identity=plan_identity,
        compile_receipt=receipt,
    )


def _scaled_extent(
    design_mm: float,
    scale: PositiveInterval,
    tolerance_ratio: float,
) -> PositiveInterval:
    return PositiveInterval(
        design_mm * (1.0 - tolerance_ratio) * scale.minimum,
        design_mm * (1.0 + tolerance_ratio) * scale.maximum,
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
    return FiniteInterval(width_px.minimum * 0.02, width_px.maximum * 0.20)


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
        FiniteInterval(top.minimum - halo, top.maximum + halo),
        float(short_min),
        float(short_max - 1),
    )
    bottom_measured = _clip_interval(
        FiniteInterval(bottom.minimum - halo, bottom.maximum + halo),
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
    # Current measurement can use many lattice traces under the six compiled
    # intents, but it must still remain bounded by source dimensions before
    # any candidate exists.
    coordinate_upper_bound = work_box.width * work_box.height * 16
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
        max_peak_temporary_bytes=coordinate_upper_bound * 10 + 32 * 1024 * 1024,
    )
    return pixel, TemplateWorkBounds(
        max_query_intents=query_count,
        max_work_units=work_units,
    )


def _stable_identity(prefix: str, *parts: object) -> str:
    payload = repr(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return f"{prefix}:{digest}"


__all__ = ["compile_template_measurement_plan"]
