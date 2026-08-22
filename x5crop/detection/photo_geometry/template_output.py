"""Selected-placement envelope, deterministic bleed, and output assessment."""

from __future__ import annotations

import math

from ...domain import Box, EvidenceState
from ...formats import OUTPUT_PROTECTION_SPEC
from ...geometry.convex import ConvexPolygon, convex_hull
from ...run_local_identity import run_local_id
from ..source_core import SourceLaneEvidence
from .boundary_geometry import boundary_line_at_state
from .template_feasible_geometry import (
    FeasiblePlacementProjection,
    JointFrameState,
)
from .model import (
    AuthoritySide,
    BoundaryRole,
)
from .output_model import (
    BoundaryProtectionFact,
    DirectUseBudgetAssessment,
    DirectUseBudgetEdgeAssessment,
    FootprintSaturationFact,
    FrameBoundaryGeometry,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
)
from .template_placement import FormatPlacement, TemplateFrame
from .trace_support import PIXEL_CENTER_EXTENT_PX


_ROLES = (
    BoundaryRole.START,
    BoundaryRole.END,
    BoundaryRole.TOP,
    BoundaryRole.BOTTOM,
)


def _frame(placement: FormatPlacement, lane_ordinal: int) -> TemplateFrame:
    if not isinstance(placement, FormatPlacement):
        raise TypeError("template output requires a format placement")
    if lane_ordinal <= 0 or lane_ordinal > placement.output_slot_count:
        raise ValueError("template output ordinal is outside the placement")
    frame = placement.frames[lane_ordinal - 1]
    if frame.lane_ordinal != lane_ordinal:
        raise ValueError("template frame ordinal disagrees with placement")
    return frame


def _footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
    *,
    apply_bleed_and_residual: bool = False,
) -> ConvexPolygon:
    """Materialize only same-state boundary intersections."""

    if projection.placement_id != placement.placement_id:
        raise ValueError("joint projection belongs to another placement")
    states = projection.frame_states[frame.lane_ordinal - 1]
    boundaries = _canonical_boundaries(frame)
    points: list[tuple[float, float]] = []
    for state in states:
        if apply_bleed_and_residual:
            residuals = _state_boundary_residuals(
                placement,
                frame,
                state,
            )
            bleeds = _state_bleed_px(
                placement,
                state,
                placement.cross_fit.boundary_use,
            )
            expansions = {
                role: residuals[role] + bleeds[role]
                for role in _ROLES
            }
        else:
            expansions = {role: 0.0 for role in _ROLES}
        positions = {
            BoundaryRole.START: (
                state.sequence_start_px
                - placement.sequence_fit.template.direction
                * expansions[BoundaryRole.START]
            ),
            BoundaryRole.END: (
                state.sequence_end_px
                + placement.sequence_fit.template.direction
                * expansions[BoundaryRole.END]
            ),
            BoundaryRole.TOP: (
                state.top_at_lane_reference_px
                - expansions[BoundaryRole.TOP]
            ),
            BoundaryRole.BOTTOM: (
                state.bottom_at_lane_reference_px
                + expansions[BoundaryRole.BOTTOM]
            ),
        }
        for cross_role, sequence_role in (
            (BoundaryRole.TOP, BoundaryRole.START),
            (BoundaryRole.TOP, BoundaryRole.END),
            (BoundaryRole.BOTTOM, BoundaryRole.END),
            (BoundaryRole.BOTTOM, BoundaryRole.START),
        ):
            cross_line = boundary_line_at_state(
                boundaries[cross_role],
                position_px=positions[cross_role],
                enclosing_support_slope=state.enclosing_support_slope,
            )
            sequence_line = boundary_line_at_state(
                boundaries[sequence_role],
                position_px=positions[sequence_role],
            )
            points.append(cross_line.intersection(sequence_line))
    return convex_hull(tuple(points))


def _canonical_boundaries(
    frame: TemplateFrame,
) -> dict[BoundaryRole, FrameBoundaryGeometry]:
    return {
        BoundaryRole.START: frame.start,
        BoundaryRole.END: frame.end,
        BoundaryRole.TOP: frame.top,
        BoundaryRole.BOTTOM: frame.bottom,
    }


def _state_boundary_residuals(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
) -> dict[BoundaryRole, float]:
    """Return outward residuals for one joint placement state.

    Aperture slopes can only enlarge local protection. A directly observed
    enclosing pair may retain its own same-state boundary slope, but neither
    case creates a placement angle or selection authority. The complete
    non-zero raster span is retained on every side.
    """

    result: dict[BoundaryRole, float] = {
        BoundaryRole.START: (
            state.sequence_start_model_residual_px
            + frame.start.local_outward_departure_px
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.END: (
            state.sequence_end_model_residual_px
            + frame.end.local_outward_departure_px
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.TOP: (
            _state_cross_outward_departure_px(
                placement,
                frame,
                state,
                BoundaryRole.TOP,
            )
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.BOTTOM: (
            _state_cross_outward_departure_px(
                placement,
                frame,
                state,
                BoundaryRole.BOTTOM,
            )
            + PIXEL_CENTER_EXTENT_PX
        ),
    }
    return result


def _state_cross_outward_departure_px(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
    role: BoundaryRole,
) -> float:
    """Evaluate one aperture residual against the same feasible state.

    A trace interval and the role position come from one observation family.
    Measuring their outward difference at each retained state avoids the false
    Cartesian sum of an extreme position with an independently extreme local
    departure.  Direction uncertainty is used only when raw trace intervals do
    not cover the frame support.
    """

    if placement.cross_fit.boundary_use != OutputBoundaryUse.APERTURE_PAIR:
        return 0.0
    direct = {item.role: item for item in placement.cross_fit.direct_bindings}
    binding = direct.get(role)
    source_role = role
    if binding is None:
        inferred = next(
            (
                item
                for item in placement.cross_fit.inferred_bindings
                if item.role == role
            ),
            None,
        )
        if inferred is None:
            raise ValueError("aperture output role lacks cross provenance")
        source_bindings = tuple(
            item
            for item in placement.cross_fit.direct_bindings
            if item.observation_id in inferred.source_observation_ids
        )
        if len(source_bindings) != 1:
            raise ValueError("inferred aperture role lacks one direct source")
        binding = source_bindings[0]
        source_role = binding.role

    state_source_position = (
        state.top_at_lane_reference_px
        if source_role == BoundaryRole.TOP
        else state.bottom_at_lane_reference_px
    )
    target_trace_px = (
        frame.top.reference_trace_px
        if role == BoundaryRole.TOP
        else frame.bottom.reference_trace_px
    )
    binding_shift = binding.projected_shift_px(
        source_trace_px=placement.cross_fit.lane_reference_trace_px,
        target_trace_px=target_trace_px,
    )
    binding_shift = 0.0 if binding_shift is None else binding_shift
    source_position = min(
        max(
            state_source_position,
            binding.full_interval_px.minimum + binding_shift,
        ),
        binding.full_interval_px.maximum + binding_shift,
    )
    support = (
        frame.top.line.support_projection_px
        if role == BoundaryRole.TOP
        else frame.bottom.line.support_projection_px
    )
    raw_departure = 0.0
    covered_traces: list[float] = []
    trace_coordinates = (
        binding.trace_coordinates_px
        if binding.trace_position_intervals_px
        else ()
    )
    for trace, interval in zip(
        trace_coordinates,
        binding.trace_position_intervals_px,
        strict=True,
    ):
        trace_px = float(trace)
        if not support.contains(trace_px):
            continue
        departure = (
            source_position - interval.minimum
            if role == BoundaryRole.TOP
            else interval.maximum - source_position
        )
        raw_departure = max(raw_departure, departure)
        covered_traces.append(trace_px)

    fit_direction = binding.fit_direction_interval_degrees
    if fit_direction is None:
        return max(0.0, raw_departure)
    if covered_traces:
        lower = min(covered_traces)
        upper = max(covered_traces)
        extrapolation_deltas = tuple(
            endpoint - min(max(endpoint, lower), upper)
            for endpoint in (support.minimum, support.maximum)
        )
    else:
        extrapolation_deltas = tuple(
            endpoint - target_trace_px
            for endpoint in (support.minimum, support.maximum)
        )
    shifts = tuple(
        math.tan(math.radians(angle)) * delta
        for angle in (fit_direction.minimum, fit_direction.maximum)
        for delta in extrapolation_deltas
    )
    direction_departure = (
        max(0.0, -min(shifts, default=0.0))
        if role == BoundaryRole.TOP
        else max(0.0, max(shifts, default=0.0))
    )
    return max(0.0, raw_departure + direction_departure)


def _state_bleed_px(
    placement: FormatPlacement,
    state: JointFrameState,
    use: OutputBoundaryUse,
) -> dict[BoundaryRole, float]:
    """Convert physical bleed with the same W/H state it protects."""

    sequence_scale = (
        abs(state.sequence_end_px - state.sequence_start_px)
        / placement.frame_spec.frame_width_mm
    )
    cross_scale = (
        abs(
            state.bottom_at_lane_reference_px
            - state.top_at_lane_reference_px
        )
        / placement.frame_spec.frame_height_mm
    )
    sequence = OUTPUT_PROTECTION_SPEC.sequence_bleed_mm(
        placement.frame_spec.frame_width_mm
    ) * sequence_scale
    cross = (
        0.0
        if use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        else OUTPUT_PROTECTION_SPEC.cross_bleed_mm * cross_scale
    )
    return {
        BoundaryRole.START: sequence,
        BoundaryRole.END: sequence,
        BoundaryRole.TOP: cross,
        BoundaryRole.BOTTOM: cross,
    }


def _maximum_state_components(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
) -> tuple[dict[BoundaryRole, float], dict[BoundaryRole, float]]:
    residuals = {role: 0.0 for role in _ROLES}
    bleeds = {role: 0.0 for role in _ROLES}
    for state in projection.frame_states[frame.lane_ordinal - 1]:
        state_residuals = _state_boundary_residuals(placement, frame, state)
        state_bleeds = _state_bleed_px(
            placement,
            state,
            placement.cross_fit.boundary_use,
        )
        for role in _ROLES:
            residuals[role] = max(residuals[role], state_residuals[role])
            bleeds[role] = max(bleeds[role], state_bleeds[role])
    return residuals, bleeds


def joint_placement_envelope(
    placement: FormatPlacement,
    projection: FeasiblePlacementProjection,
    lane_ordinal: int,
) -> JointPlacementEnvelope:
    """Retain continuous uncertainty from one selected placement only."""

    frame = _frame(placement, lane_ordinal)
    return JointPlacementEnvelope(
        placement_id=placement.placement_id,
        projection_id=projection.projection_id,
        lane_id=placement.lane_id,
        lane_ordinal=lane_ordinal,
        boundary_use=placement.cross_fit.boundary_use,
        canonical_source_footprint=convex_hull(frame.canonical_source_polygon),
        feasible_source_footprint=_footprint(
            placement,
            frame,
            projection,
        ),
        extreme_evaluation_count=projection.extreme_evaluation_count,
    )


def _outside_authority_sides(
    polygon: ConvexPolygon,
    authority: Box,
) -> tuple[AuthoritySide, ...]:
    sides: list[AuthoritySide] = []
    if min(point[0] for point in polygon) < authority.left:
        sides.append(AuthoritySide.LEFT)
    if min(point[1] for point in polygon) < authority.top:
        sides.append(AuthoritySide.TOP)
    if max(point[0] for point in polygon) > authority.right - 1:
        sides.append(AuthoritySide.RIGHT)
    if max(point[1] for point in polygon) > authority.bottom - 1:
        sides.append(AuthoritySide.BOTTOM)
    return tuple(sides)


def _saturation_facts(
    required: ConvexPolygon,
    authority: Box,
) -> tuple[FootprintSaturationFact, ...]:
    outside = set(_outside_authority_sides(required, authority))
    return tuple(
        FootprintSaturationFact(
            authority_side=side,
        )
        for side in AuthoritySide
        if side in outside
    )


def _source_lane_authority(
    lane: SourceLaneEvidence,
    layout: str,
) -> Box:
    work = lane.domain.work_box
    if layout == "horizontal":
        return work
    if layout == "vertical":
        return Box(work.top, work.left, work.bottom, work.right)
    raise ValueError(f"unsupported source layout: {layout}")


def _expansion_px(
    boundary: FrameBoundaryGeometry,
    footprint: ConvexPolygon,
) -> float:
    projections = tuple(
        boundary.line.normal_x * x + boundary.line.normal_y * y
        for x, y in footprint
    )
    if boundary.role in {BoundaryRole.START, BoundaryRole.TOP}:
        return max(0.0, boundary.line.offset_px - min(projections))
    return max(0.0, max(projections) - boundary.line.offset_px)


def output_footprint_from_template_placement(
    placement: FormatPlacement,
    projection: FeasiblePlacementProjection,
    *,
    lane: SourceLaneEvidence,
    lane_ordinal: int,
    layout: str,
) -> OutputFootprint:
    """Add deterministic bleed to one selected source-coordinate envelope."""

    frame = _frame(placement, lane_ordinal)
    if not isinstance(lane, SourceLaneEvidence):
        raise TypeError("template output requires source-lane authority")
    if lane.domain.lane_id != placement.lane_id:
        raise ValueError("source-lane authority disagrees with placement")
    envelope = joint_placement_envelope(placement, projection, lane_ordinal)
    parameter_footprint = _footprint(placement, frame, projection)
    local_residuals, bleed_by_role = _maximum_state_components(
        placement,
        frame,
        projection,
    )
    required = _footprint(
        placement,
        frame,
        projection,
        apply_bleed_and_residual=True,
    )
    authority = _source_lane_authority(lane, layout)
    saturation = _saturation_facts(required, authority)
    boundaries = _canonical_boundaries(frame)
    protections = tuple(
        BoundaryProtectionFact(
            role=role,
            measurement_expansion_px=_expansion_px(
                boundaries[role],
                parameter_footprint,
            ),
            bleed_px=bleed_by_role[role],
            local_boundary_residual_px=local_residuals[role],
            joint_expansion_px=_expansion_px(boundaries[role], required),
        )
        for role in _ROLES
    )
    return OutputFootprint(
        geometry_id=run_local_id(
            "template-output-footprint",
            placement.placement_id,
            lane_ordinal,
        ),
        envelope=envelope,
        required_source_footprint=required,
        boundary_protections=protections,
        saturation_facts=saturation,
        sampling_authority_box=authority,
        authority_profile_id=lane.domain.authority_profile_id,
    )


def _assert_selected_output(
    placement: FormatPlacement,
    output: OutputFootprint,
) -> None:
    frame = _frame(placement, output.envelope.lane_ordinal)
    if (
        output.envelope.placement_id != placement.placement_id
        or output.envelope.lane_id != placement.lane_id
        or output.envelope.canonical_source_footprint
        != convex_hull(frame.canonical_source_polygon)
    ):
        raise ValueError("output footprint does not belong to selected placement")


def template_direct_use_budget_assessment(
    placement: FormatPlacement,
    output: OutputFootprint,
) -> DirectUseBudgetAssessment:
    """Assess complete uncertainty plus bleed against the output policy."""

    if not isinstance(output, OutputFootprint):
        raise TypeError("direct-use assessment requires an output footprint")
    _assert_selected_output(placement, output)
    protections = {item.role: item for item in output.boundary_protections}
    width_state = placement.source_scan_geometry.width_state
    height_state = placement.source_scan_geometry.height_state
    ratio = OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
    states = {
        BoundaryRole.START: width_state,
        BoundaryRole.END: width_state,
        BoundaryRole.TOP: height_state,
        BoundaryRole.BOTTOM: height_state,
    }
    limit_mm = {
        BoundaryRole.START: placement.frame_spec.frame_width_mm * ratio,
        BoundaryRole.END: placement.frame_spec.frame_width_mm * ratio,
        BoundaryRole.TOP: placement.frame_spec.frame_height_mm * ratio,
        BoundaryRole.BOTTOM: placement.frame_spec.frame_height_mm * ratio,
    }
    support_output = (
        output.envelope.boundary_use
        == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
    )
    edge_assessments = tuple(
        DirectUseBudgetEdgeAssessment(
            role=role,
            expansion_px=protections[role].joint_expansion_px,
            expansion_mm=states[role].worst_case_mm(
                protections[role].joint_expansion_px
            ),
            limit_mm=limit_mm[role],
            limit_applies=(
                not support_output
                or role in {BoundaryRole.START, BoundaryRole.END}
            ),
            within_limit=(
                True
                if support_output
                and role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
                else
                states[role].worst_case_mm(
                    protections[role].joint_expansion_px
                )
                <= limit_mm[role]
            ),
        )
        for role in _ROLES
    )
    support_ratio = None
    support_within_limit = None
    if support_output:
        support = placement.cross_fit.enclosing_support_pair
        if support is None:
            raise ValueError("enclosing output lost its support authority")
        # The enclosing contract belongs to the directly observed support
        # span.  The output footprint is the union of alternative joint states;
        # measuring its hull would combine a translated top from one state with
        # a translated bottom from another and falsely enlarge physical height.
        support_ratio = support.observed_span_px.maximum / (
            placement.cross_fit.bottom_canonical_px
            - placement.cross_fit.top_canonical_px
        )
        support_within_limit = (
            support_ratio
            <= OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        )
    supported = all(item.within_limit for item in edge_assessments) and (
        support_within_limit is not False
    )
    return DirectUseBudgetAssessment(
        geometry_id=output.geometry_id,
        boundary_use=output.envelope.boundary_use,
        edge_assessments=edge_assessments,
        enclosing_support_height_ratio=support_ratio,
        enclosing_support_within_limit=support_within_limit,
        state=(
            EvidenceState.SUPPORTED
            if supported
            else EvidenceState.CONTRADICTED
        ),
    )


__all__ = [
    "joint_placement_envelope",
    "output_footprint_from_template_placement",
    "template_direct_use_budget_assessment",
]
