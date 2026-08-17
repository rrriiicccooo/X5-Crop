"""Selected-placement envelope, deterministic bleed, and output assessment."""

from __future__ import annotations

import math

from ...domain import Box, EvidenceState, FiniteInterval
from ...formats import OUTPUT_PROTECTION_SPEC
from ...geometry.affine import AffineCoordinateTransform
from ...geometry.convex import ConvexPolygon, convex_hull, mapped_half_open_box
from ...run_local_identity import run_local_id
from ..source_core import SourceLaneEvidence
from .boundary_geometry import boundary_line_at_state
from .template_feasible_geometry import FeasiblePlacementProjection
from .model import AuthoritySide, BoundaryRole, ClippedRequirement
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
            or boundary.full_direction_interval_degrees
            != placement.direction.full_angle_interval_degrees
        ):
            raise ValueError("frame does not retain one shared direction authority")


def _angles(placement: FormatPlacement) -> tuple[float, ...]:
    interval = placement.direction.full_angle_interval_degrees
    return tuple(dict.fromkeys((interval.minimum, interval.maximum)))


def _footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
    *,
    sequence_bleed_px: float = 0.0,
    cross_bleed_px: float = 0.0,
) -> ConvexPolygon:
    """Project correlated placement states and shared-angle extremes."""

    _validate_shared_direction(placement, frame)
    if projection.placement_id != placement.placement_id:
        raise ValueError("joint projection belongs to another placement")
    role_index = 2 * (frame.lane_ordinal - 1)
    start = projection.sequence_role_intervals_px[role_index]
    end = projection.sequence_role_intervals_px[role_index + 1]
    points: list[tuple[float, float]] = []
    for angle in _angles(placement):
        cross_shift = math.tan(math.radians(angle)) * (
            frame.top.reference_trace_px
            - placement.cross_fit.lane_reference_trace_px
        )
        top = FiniteInterval(
            projection.top_at_lane_reference_px.minimum
            + cross_shift
            - cross_bleed_px,
            projection.top_at_lane_reference_px.maximum
            + cross_shift
            - cross_bleed_px,
        )
        bottom = FiniteInterval(
            projection.bottom_at_lane_reference_px.minimum
            + cross_shift
            + cross_bleed_px,
            projection.bottom_at_lane_reference_px.maximum
            + cross_shift
            + cross_bleed_px,
        )
        intervals = {
            BoundaryRole.START: FiniteInterval(
                start.minimum - sequence_bleed_px,
                start.maximum - sequence_bleed_px,
            ),
            BoundaryRole.END: FiniteInterval(
                end.minimum + sequence_bleed_px,
                end.maximum + sequence_bleed_px,
            ),
            BoundaryRole.TOP: top,
            BoundaryRole.BOTTOM: bottom,
        }
        boundaries = _canonical_boundaries(frame)
        for cross_role, sequence_role in (
            (BoundaryRole.TOP, BoundaryRole.START),
            (BoundaryRole.TOP, BoundaryRole.END),
            (BoundaryRole.BOTTOM, BoundaryRole.END),
            (BoundaryRole.BOTTOM, BoundaryRole.START),
        ):
            for cross_position in (
                intervals[cross_role].minimum,
                intervals[cross_role].maximum,
            ):
                cross_line = boundary_line_at_state(
                    boundaries[cross_role],
                    position_px=cross_position,
                    angle_degrees=angle,
                )
                for sequence_position in (
                    intervals[sequence_role].minimum,
                    intervals[sequence_role].maximum,
                ):
                    sequence_line = boundary_line_at_state(
                        boundaries[sequence_role],
                        position_px=sequence_position,
                        angle_degrees=angle,
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
        feasible_source_footprint=_footprint(placement, frame, projection),
        extreme_evaluation_count=projection.extreme_evaluation_count,
    )


def _bleed_px(
    placement: FormatPlacement,
    use: OutputBoundaryUse,
) -> tuple[float, float]:
    width_scale = (
        placement.source_scan_geometry.width_state.feasible_scale_interval().maximum
    )
    height_scale = (
        placement.source_scan_geometry.height_state.feasible_scale_interval().maximum
    )
    sequence = OUTPUT_PROTECTION_SPEC.sequence_bleed_mm(
        placement.frame_spec.frame_width_mm
    ) * width_scale
    cross = (
        0.0
        if use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        else OUTPUT_PROTECTION_SPEC.cross_bleed_mm * height_scale
    )
    return sequence, cross


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
            clipped_requirements=(ClippedRequirement.VISIBLE_PLACEMENT,),
        )
        for side in AuthoritySide
        if side in outside
    )


def _mapped_box(
    polygon: ConvexPolygon,
    transform: AffineCoordinateTransform,
) -> Box:
    if not isinstance(transform, AffineCoordinateTransform):
        raise TypeError("template output requires an affine transform")
    mapped = mapped_half_open_box(polygon, transform.map_point)
    if (
        mapped.left < 0
        or mapped.top < 0
        or mapped.right > transform.output_extent.width
        or mapped.bottom > transform.output_extent.height
    ):
        raise ValueError("mapped template footprint exceeds output authority")
    return mapped


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
    transform: AffineCoordinateTransform,
) -> OutputFootprint:
    """Add deterministic bleed to one selected joint placement envelope."""

    frame = _frame(placement, lane_ordinal)
    if not isinstance(lane, SourceLaneEvidence):
        raise TypeError("template output requires source-lane authority")
    if lane.domain.lane_id != placement.lane_id:
        raise ValueError("source-lane authority disagrees with placement")
    envelope = joint_placement_envelope(placement, projection, lane_ordinal)
    sequence_bleed, cross_bleed = _bleed_px(placement, envelope.boundary_use)
    required = _footprint(
        placement,
        frame,
        projection,
        sequence_bleed_px=sequence_bleed,
        cross_bleed_px=cross_bleed,
    )
    authority = _source_lane_authority(lane, layout)
    saturation = _saturation_facts(required, authority)
    boundaries = _canonical_boundaries(frame)
    bleed_by_role = {
        BoundaryRole.START: sequence_bleed,
        BoundaryRole.END: sequence_bleed,
        BoundaryRole.TOP: cross_bleed,
        BoundaryRole.BOTTOM: cross_bleed,
    }
    protections = tuple(
        BoundaryProtectionFact(
            role=role,
            measurement_expansion_px=_expansion_px(
                boundaries[role],
                envelope.feasible_source_footprint,
            ),
            bleed_px=bleed_by_role[role],
            straight_residual_px=0.0,
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
        mapped_output_box=(
            None if saturation else _mapped_box(required, transform)
        ),
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
        support_ratio = (
            support.observed_span_px.maximum
            / placement.cross_fit.fixed_height_px.minimum
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
