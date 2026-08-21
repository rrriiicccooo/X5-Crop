"""Selected-placement envelope, deterministic bleed, and output assessment."""

from __future__ import annotations

import math

from ...domain import Box, EvidenceState
from ...formats import OUTPUT_PROTECTION_SPEC
from ...geometry.convex import ConvexPolygon, convex_hull
from ...run_local_identity import run_local_id
from ..source_core import SourceLaneEvidence
from .boundary_geometry import boundary_line_at_state
from .template_feasible_geometry import FeasiblePlacementProjection
from .model import (
    AuthoritySide,
    BoundaryRole,
    ClippedRequirement,
    PositionSource,
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


def _validate_shared_direction(
    placement: FormatPlacement,
    frame: TemplateFrame,
) -> None:
    for boundary in (frame.top, frame.bottom, frame.start, frame.end):
        if (
            boundary.direction_reference_id != placement.direction.direction_id
            or not placement.direction.observed_angle_interval_degrees.contains(
                boundary.full_direction_interval_degrees.minimum,
                epsilon=1.0e-9,
            )
            or not placement.direction.observed_angle_interval_degrees.contains(
                boundary.full_direction_interval_degrees.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("frame direction residual lacks shared provenance")


def _footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
    *,
    apply_bleed_and_residual: bool = False,
) -> ConvexPolygon:
    """Materialize only same-state boundary intersections."""

    _validate_shared_direction(placement, frame)
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
        cross_shift = math.tan(math.radians(state.angle_degrees)) * (
            frame.top.reference_trace_px
            - placement.cross_fit.lane_reference_trace_px
        )
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
                + cross_shift
                - expansions[BoundaryRole.TOP]
            ),
            BoundaryRole.BOTTOM: (
                state.bottom_at_lane_reference_px
                + cross_shift
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
                angle_degrees=state.angle_degrees,
            )
            sequence_line = boundary_line_at_state(
                boundaries[sequence_role],
                position_px=positions[sequence_role],
                angle_degrees=state.angle_degrees,
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
    state,
) -> dict[BoundaryRole, float]:
    """Return outward residuals for one joint placement state.

    A local top/bottom fragment may prove the aperture offset without owning
    the complete placement frame axis. Its measured slope is therefore evaluated
    only on the traces where that fragment was directly observed.  Extending
    a short fragment's direction interval to every frame corner would invent
    an unobserved curved strip and can make protection grow with distance.
    """

    result: dict[BoundaryRole, float] = {
        BoundaryRole.START: state.sequence_start_model_residual_px,
        BoundaryRole.END: state.sequence_end_model_residual_px,
        BoundaryRole.TOP: 0.0,
        BoundaryRole.BOTTOM: 0.0,
    }
    if (
        placement.cross_fit.boundary_use
        == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
    ):
        # The support pair's trace intervals and common slope are already one
        # joint feasible system.  Adding the same per-side line uncertainty a
        # second time would manufacture an outer boundary wider than any
        # directly observed support state.
        return result
    cross_bindings = {
        item.observation_id: item
        for item in placement.cross_fit.direct_bindings
    }
    for role, boundary in (
        (BoundaryRole.TOP, frame.top),
        (BoundaryRole.BOTTOM, frame.bottom),
    ):
        if boundary.position_source != PositionSource.OBSERVED_TRANSITION:
            continue
        binding = cross_bindings.get(boundary.position_observation_ids[0])
        if (
            binding is None
            or binding.full_direction_interval_degrees is None
            or not binding.trace_coordinates_px
        ):
            raise ValueError(
                "observed cross boundary lacks direct residual authority"
            )
        outward = 0.0
        global_slope = math.tan(math.radians(state.angle_degrees))
        for trace in (
            float(binding.trace_coordinates_px[0]),
            float(binding.trace_coordinates_px[-1]),
        ):
            distance = trace - placement.cross_fit.lane_reference_trace_px
            global_at_trace = (
                (
                    state.top_at_lane_reference_px
                    if role == BoundaryRole.TOP
                    else state.bottom_at_lane_reference_px
                )
                + global_slope * distance
            )
            for observed_position in (
                binding.full_interval_px.minimum,
                binding.full_interval_px.maximum,
            ):
                for observed_angle in (
                    binding.full_direction_interval_degrees.minimum,
                    binding.full_direction_interval_degrees.maximum,
                ):
                    observed_at_trace = (
                        observed_position
                        + math.tan(math.radians(observed_angle)) * distance
                    )
                    delta = (
                        global_at_trace - observed_at_trace
                        if role == BoundaryRole.TOP
                        else observed_at_trace - global_at_trace
                    )
                    outward = max(outward, delta)
        result[role] = max(0.0, outward)
    return result


def _state_bleed_px(
    placement: FormatPlacement,
    state,
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
    *,
    requirement: ClippedRequirement = ClippedRequirement.VISIBLE_PLACEMENT,
) -> tuple[FootprintSaturationFact, ...]:
    outside = set(_outside_authority_sides(required, authority))
    return tuple(
        FootprintSaturationFact(
            authority_side=side,
            clipped_requirements=(requirement,),
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
            worst_placement_solution_id=placement.placement_id,
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
        placement_solution_ids=(placement.placement_id,),
        boundary_use=output.envelope.boundary_use,
        edge_assessments=edge_assessments,
        enclosing_support_height_ratio=support_ratio,
        enclosing_support_within_limit=support_within_limit,
        state=(EvidenceState.SUPPORTED if supported else EvidenceState.CONTRADICTED),
        named_gap=None,
    )


__all__ = [
    "joint_placement_envelope",
    "output_footprint_from_template_placement",
    "template_direct_use_budget_assessment",
]
