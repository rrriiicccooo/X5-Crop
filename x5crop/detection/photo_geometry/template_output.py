"""Selected-template output safety and direct-use assessment."""

from __future__ import annotations

from ...domain import Box, EvidenceState
from ...formats import DIRECT_USE_BUDGET_SPEC
from ...geometry.affine import AffineCoordinateTransform
from ...geometry.convex import (
    ConvexPolygon,
    clip_convex_polygon_to_box,
    convex_hull,
    mapped_half_open_box,
)
from ...run_local_identity import run_local_id
from ..source_core import SourceLaneEvidence
from .boundary_geometry import boundary_line_at_state
from .model import AuthoritySide, BoundaryRole, ClippedRequirement
from .output_model import (
    DirectUseBudgetAssessment,
    DirectUseBudgetEdgeAssessment,
    FrameBoundaryGeometry,
    FootprintSaturationFact,
    SafeCropEnvelope,
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


def _retained_safety_footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
) -> ConvexPolygon:
    """Envelope complete frame states without independently rotating edges."""

    _validate_shared_direction(placement, frame)
    points: list[tuple[float, float]] = []
    angles = tuple(
        dict.fromkeys(
            (
                placement.direction.full_angle_interval_degrees.minimum,
                placement.direction.full_angle_interval_degrees.maximum,
            )
        )
    )
    for angle in angles:
        top = boundary_line_at_state(
            frame.top,
            position_px=frame.top.full_position_interval_px.minimum,
            angle_degrees=angle,
        )
        bottom = boundary_line_at_state(
            frame.bottom,
            position_px=frame.bottom.full_position_interval_px.maximum,
            angle_degrees=angle,
        )
        start = boundary_line_at_state(
            frame.start,
            position_px=frame.start.full_position_interval_px.minimum,
            angle_degrees=angle,
        )
        end = boundary_line_at_state(
            frame.end,
            position_px=frame.end.full_position_interval_px.maximum,
            angle_degrees=angle,
        )
        points.extend(
            (
                top.intersection(start),
                top.intersection(end),
                bottom.intersection(end),
                bottom.intersection(start),
            )
        )
    return convex_hull(tuple(points))


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


def safe_crop_envelope_from_template_placement(
    placement: FormatPlacement,
    *,
    lane: SourceLaneEvidence,
    lane_ordinal: int,
    layout: str,
    transform: AffineCoordinateTransform,
) -> SafeCropEnvelope:
    """Build one saved footprint from the selected placement only."""

    frame = _frame(placement, lane_ordinal)
    if not isinstance(lane, SourceLaneEvidence):
        raise TypeError("template output requires source-lane authority")
    if lane.domain.lane_id != placement.lane_id:
        raise ValueError("source-lane authority disagrees with placement")
    authority = _source_lane_authority(lane, layout)
    placement_footprint = convex_hull(frame.canonical_source_polygon)
    required = _retained_safety_footprint(placement, frame)
    constrained = clip_convex_polygon_to_box(required, authority)
    return SafeCropEnvelope(
        geometry_id=run_local_id(
            "template-safe-crop-envelope",
            placement.placement_id,
            lane_ordinal,
        ),
        lane_id=placement.lane_id,
        lane_ordinal=lane_ordinal,
        placement_source_footprint=placement_footprint,
        required_source_footprint=required,
        constrained_source_footprint=constrained,
        saturation_facts=_saturation_facts(required, authority),
        sampling_authority_box=authority,
        authority_profile_id=lane.domain.authority_profile_id,
        mapped_output_box=_mapped_box(constrained, transform),
    )


def _assert_selected_envelope(
    placement: FormatPlacement,
    frame: TemplateFrame,
    envelope: SafeCropEnvelope,
    transform: AffineCoordinateTransform,
) -> None:
    if (
        envelope.lane_id != placement.lane_id
        or envelope.lane_ordinal != frame.lane_ordinal
        or envelope.mapped_output_box is None
    ):
        raise ValueError("safe envelope does not belong to the placement frame")
    canonical = convex_hull(frame.canonical_source_polygon)
    required = _retained_safety_footprint(placement, frame)
    constrained = clip_convex_polygon_to_box(
        required,
        envelope.sampling_authority_box,
    )
    if (
        envelope.placement_source_footprint != canonical
        or envelope.required_source_footprint != required
        or envelope.constrained_source_footprint != constrained
        or envelope.mapped_output_box != _mapped_box(constrained, transform)
    ):
        raise ValueError("safe envelope contains non-selected placement geometry")


def _expansion_px(
    boundary: FrameBoundaryGeometry,
    required: ConvexPolygon,
) -> float:
    projections = tuple(
        boundary.line.normal_x * x + boundary.line.normal_y * y
        for x, y in required
    )
    if boundary.role in {BoundaryRole.START, BoundaryRole.TOP}:
        return max(0.0, boundary.line.offset_px - min(projections))
    return max(0.0, max(projections) - boundary.line.offset_px)


def template_direct_use_budget_assessment(
    placement: FormatPlacement,
    envelope: SafeCropEnvelope,
    transform: AffineCoordinateTransform,
) -> DirectUseBudgetAssessment:
    """Assess the selected frame against fixed 5%/3% per-side budgets."""

    if not isinstance(envelope, SafeCropEnvelope):
        raise TypeError("direct-use assessment requires a safe crop envelope")
    frame = _frame(placement, envelope.lane_ordinal)
    _assert_selected_envelope(placement, frame, envelope, transform)
    width_state = placement.source_scan_geometry.width_state
    height_state = placement.source_scan_geometry.height_state
    limits = {
        BoundaryRole.START: (
            width_state,
            DIRECT_USE_BUDGET_SPEC.sequence_ratio_per_side,
        ),
        BoundaryRole.END: (
            width_state,
            DIRECT_USE_BUDGET_SPEC.sequence_ratio_per_side,
        ),
        BoundaryRole.TOP: (
            height_state,
            DIRECT_USE_BUDGET_SPEC.cross_ratio_per_side,
        ),
        BoundaryRole.BOTTOM: (
            height_state,
            DIRECT_USE_BUDGET_SPEC.cross_ratio_per_side,
        ),
    }
    boundaries = {
        BoundaryRole.START: frame.start,
        BoundaryRole.END: frame.end,
        BoundaryRole.TOP: frame.top,
        BoundaryRole.BOTTOM: frame.bottom,
    }
    assessments: list[DirectUseBudgetEdgeAssessment] = []
    for role in _ROLES:
        state, ratio = limits[role]
        expansion = _expansion_px(
            boundaries[role],
            envelope.required_source_footprint,
        )
        expansion_mm = state.worst_case_mm(expansion)
        limit_mm = state.worst_case_mm(
            state.retained_extent_budget_px(ratio).minimum
        )
        assessments.append(
            DirectUseBudgetEdgeAssessment(
                role=role,
                expansion_px=expansion,
                expansion_mm=expansion_mm,
                limit_mm=limit_mm,
                within_limit=expansion_mm <= limit_mm,
                worst_placement_solution_id=placement.placement_id,
            )
        )
    edge_assessments = tuple(assessments)
    state = (
        EvidenceState.SUPPORTED
        if all(item.within_limit for item in edge_assessments)
        else EvidenceState.CONTRADICTED
    )
    return DirectUseBudgetAssessment(
        geometry_id=envelope.geometry_id,
        placement_solution_ids=(placement.placement_id,),
        edge_assessments=edge_assessments,
        state=state,
        named_gap=None,
    )
