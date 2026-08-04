from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from ...domain import Box, EvidenceState
from ...geometry.affine import AffineCoordinateTransform
from ...geometry.convex import (
    ConvexPolygon,
    axis_aligned_minkowski_guard,
    clip_convex_polygon_to_box,
    contains_point,
    convex_hull,
    mapped_half_open_box,
)
from ..source_core import SourceLaneEvidence
from .corridors import source_lane_box
from .boundary_geometry import canonical_boundary_line_at_position
from .model import (
    AuthoritySide,
    BoundaryRole,
    ClippedRequirement,
    DirectUseBudgetAssessment,
    DirectUseBudgetEdgeAssessment,
    FootprintSaturationFact,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SafeCropEnvelope,
)
from .template_model import (
    FormatPlacement,
    FrameFormatPlacement,
)
from .protection import (
    DIRECT_USE_BUDGET_SPEC,
    MinimumGuardSpec,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _boundary_polygon(
    placement: FrameFormatPlacement,
    *,
    top_position_px: float,
    bottom_position_px: float,
    start_position_px: float,
    end_position_px: float,
) -> tuple[tuple[float, float], ...]:
    top = canonical_boundary_line_at_position(
        placement.top,
        top_position_px,
        placement.start.line,
    )
    bottom = canonical_boundary_line_at_position(
        placement.bottom,
        bottom_position_px,
        placement.start.line,
    )
    start = canonical_boundary_line_at_position(
        placement.start,
        start_position_px,
        placement.start.line,
    )
    end = canonical_boundary_line_at_position(
        placement.end,
        end_position_px,
        placement.start.line,
    )
    return (
        top.intersection(start),
        top.intersection(end),
        bottom.intersection(end),
        bottom.intersection(start),
    )


def format_placement_frame_footprint(
    placement: FormatPlacement,
    lane_ordinal: int,
) -> ConvexPolygon:
    index = lane_ordinal - 1
    if index < 0 or index >= placement.output_slot_count:
        raise ValueError("format-placement ordinal is out of range")
    frame = placement.canonical.frames[index]
    return convex_hull(
        _boundary_polygon(
            frame,
            top_position_px=min(
                item.top_full_positions_px[index].minimum
                for item in placement.cross_placements
            ),
            bottom_position_px=max(
                item.bottom_full_positions_px[index].maximum
                for item in placement.cross_placements
            ),
            start_position_px=min(
                item.full_positions_px[index * 2].minimum
                for item in placement.sequence_placements
            ),
            end_position_px=max(
                item.full_positions_px[index * 2 + 1].maximum
                for item in placement.sequence_placements
            ),
        )
    )


def _oriented_outer_footprint(
    points: tuple[tuple[float, float], ...],
    canonical_frame: FrameFormatPlacement,
) -> ConvexPolygon:
    """Form one rectangle from the outermost value of each boundary role."""

    if not points:
        raise ValueError("oriented outer footprint requires source points")
    sequence_normal = (
        canonical_frame.start.line.normal_x,
        canonical_frame.start.line.normal_y,
    )
    cross_normal = (
        canonical_frame.top.line.normal_x,
        canonical_frame.top.line.normal_y,
    )
    sequence_offsets = tuple(
        sequence_normal[0] * x + sequence_normal[1] * y
        for x, y in points
    )
    cross_offsets = tuple(
        cross_normal[0] * x + cross_normal[1] * y
        for x, y in points
    )
    start = replace(
        canonical_frame.start.line,
        offset_px=min(sequence_offsets),
    )
    end = replace(
        canonical_frame.end.line,
        offset_px=max(sequence_offsets),
    )
    top = replace(
        canonical_frame.top.line,
        offset_px=min(cross_offsets),
    )
    bottom = replace(
        canonical_frame.bottom.line,
        offset_px=max(cross_offsets),
    )
    return convex_hull(
        (
            top.intersection(start),
            top.intersection(end),
            bottom.intersection(end),
            bottom.intersection(start),
        )
    )


def _inside_authority(point: tuple[float, float], authority: Box) -> bool:
    return (
        authority.left <= point[0] <= authority.right - 1
        and authority.top <= point[1] <= authority.bottom - 1
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
    minimum_guard_footprint: ConvexPolygon,
    required_footprint: ConvexPolygon,
    authority: Box,
) -> tuple[FootprintSaturationFact, ...]:
    guard_sides = set(
        _outside_authority_sides(minimum_guard_footprint, authority)
    )
    visible_sides = set(
        _outside_authority_sides(required_footprint, authority)
    )
    return tuple(
        FootprintSaturationFact(
            authority_side=side,
            clipped_requirements=tuple(
                requirement
                for requirement, applies in (
                    (ClippedRequirement.MINIMUM_GUARD, side in guard_sides),
                    (
                        ClippedRequirement.VISIBLE_INTERPOLATION_GUARD,
                        side in visible_sides,
                    ),
                )
                if applies
            ),
        )
        for side in AuthoritySide
        if side in guard_sides or side in visible_sides
    )


def safe_crop_envelope_from_placements(
    placements: tuple[FormatPlacement, ...],
    canonical: FormatPlacement,
    *,
    lane: SourceLaneEvidence,
    lane_ordinal: int,
    layout: str,
    minimum_guard: MinimumGuardSpec,
    transform: AffineCoordinateTransform,
) -> SafeCropEnvelope:
    """Build the sole saved footprint and mapped-box owner for one slot."""

    if (
        not placements
        or canonical not in placements
        or lane_ordinal <= 0
        or any(
            placement.lane_id != canonical.lane_id
            or placement.output_slot_count < lane_ordinal
            or placement.direction.direction_id != canonical.direction.direction_id
            for placement in placements
        )
    ):
        raise ValueError("safe envelope requires one coherent placement set")
    authority = source_lane_box(lane, layout)
    canonical_frame = canonical.canonical.frames[lane_ordinal - 1]
    placement_footprints = tuple(
        format_placement_frame_footprint(placement, lane_ordinal)
        for placement in placements
    )
    if any(
        not all(_inside_authority(point, authority) for point in footprint)
        for footprint in placement_footprints
    ):
        raise ValueError("format placement exceeds source/lane authority")
    placement_union = _oriented_outer_footprint(
        tuple(
            point
            for footprint in placement_footprints
            for point in footprint
        ),
        canonical_frame,
    )
    canonical_width = canonical.canonical_sequence
    start_index = (lane_ordinal - 1) * 2
    end_index = start_index + 1
    width_guard_px = (
        minimum_guard.sequence_axis_mm_per_side
        * canonical.source_frame_geometry.width_state.feasible_scale_interval().maximum
    )
    height_guard_px = (
        minimum_guard.cross_axis_mm_per_side
        * canonical.source_frame_geometry.height_state.feasible_scale_interval().maximum
    )
    minimum_guard_footprint = convex_hull(
        _boundary_polygon(
            canonical_frame,
            top_position_px=(
                canonical_frame.top.canonical_position_px - height_guard_px
            ),
            bottom_position_px=(
                canonical_frame.bottom.canonical_position_px + height_guard_px
            ),
            start_position_px=(
                canonical_width.canonical_positions_px[start_index]
                - width_guard_px
            ),
            end_position_px=(
                canonical_width.canonical_positions_px[end_index]
                + width_guard_px
            ),
        )
    )
    geometric_requirement = _oriented_outer_footprint(
        placement_union + minimum_guard_footprint,
        canonical_frame,
    )
    required = axis_aligned_minkowski_guard(
        geometric_requirement,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.interpolation_allowance_source_px,
    )
    canonical_polygon = convex_hull(
        canonical_frame.canonical_source_polygon
    )
    if not all(
        _inside_authority(point, authority)
        for point in canonical_polygon
    ):
        raise ValueError("canonical placement exceeds source/lane authority")
    constrained = clip_convex_polygon_to_box(required, authority)
    if (
        not all(contains_point(constrained, point) for point in placement_union)
        or not all(contains_point(constrained, point) for point in canonical_polygon)
    ):
        raise ValueError("authority clipping removed a valid placement")
    solution_ids = tuple(sorted(item.placement_id for item in placements))
    mapped = mapped_half_open_box(constrained, transform.map_point)
    if (
        mapped.left < 0
        or mapped.top < 0
        or mapped.right > transform.output_extent.width
        or mapped.bottom > transform.output_extent.height
    ):
        raise ValueError("mapped footprint exceeds affine output authority")
    return SafeCropEnvelope(
        geometry_id=_stable_id(
            "safe-format-placement-envelope",
            canonical.lane_id,
            lane_ordinal,
            *solution_ids,
        ),
        lane_id=canonical.lane_id,
        lane_ordinal=lane_ordinal,
        placement_source_footprint=placement_union,
        required_source_footprint=required,
        constrained_source_footprint=constrained,
        saturation_facts=_saturation_facts(
            minimum_guard_footprint,
            required,
            authority,
        ),
        sampling_authority_box=authority,
        authority_profile_id=lane.domain.authority_profile_id,
        mapped_output_box=mapped,
    )


def output_sampling_identity(
    geometry: SafeCropEnvelope,
    transform: AffineCoordinateTransform,
) -> tuple[object, ...]:
    mapped = geometry.mapped_output_box
    if mapped is None:
        raise ValueError("safe crop envelope has not been mapped")
    return (
        mapped,
        transform.matrix,
        transform.inverse_matrix,
        transform.source_extent,
        transform.output_extent,
        geometry.lane_id,
        geometry.authority_profile_id,
        geometry.sampling_authority_box,
    )


def _actual_source_sampling_polygon(
    box: Box,
    transform: AffineCoordinateTransform,
) -> ConvexPolygon:
    return convex_hull(
        tuple(
            transform.inverse_map_point(x, y)
            for x, y in (
                (float(box.left), float(box.top)),
                (float(box.right - 1), float(box.top)),
                (float(box.right - 1), float(box.bottom - 1)),
                (float(box.left), float(box.bottom - 1)),
            )
        )
    )


def _line_offset_at_position(frame_boundary, position: float, side_line) -> float:
    return canonical_boundary_line_at_position(
        frame_boundary,
        position,
        side_line,
    ).offset_px


def direct_use_budget_assessment(
    placements: tuple[FormatPlacement, ...],
    output_geometry: SafeCropEnvelope,
    transform: AffineCoordinateTransform | None,
) -> DirectUseBudgetAssessment:
    """Judge worst per-side expansion against every retained placement."""

    if (
        transform is None
        or output_geometry.mapped_output_box is None
        or not placements
        or any(
            placement.lane_id != output_geometry.lane_id
            or placement.output_slot_count < output_geometry.lane_ordinal
            for placement in placements
        )
    ):
        return DirectUseBudgetAssessment(
            geometry_id=output_geometry.geometry_id,
            placement_solution_ids=(),
            edge_assessments=(),
            state=EvidenceState.UNAVAILABLE,
            named_gap="direct_use_budget_unavailable",
        )
    actual = _actual_source_sampling_polygon(
        output_geometry.mapped_output_box,
        transform,
    )
    worst: dict[
        BoundaryRole,
        tuple[float, float, float, float, float, str, bool],
    ] = {}
    index = output_geometry.lane_ordinal - 1
    for placement in placements:
        frame = placement.canonical.frames[index]
        boundaries = (
            frame.start,
            frame.end,
            frame.top,
            frame.bottom,
        )
        actual_offsets = {
            boundary.role: tuple(
                boundary.line.normal_x * x + boundary.line.normal_y * y
                for x, y in actual
            )
            for boundary in boundaries
        }
        width_limit, height_limit = DIRECT_USE_BUDGET_SPEC.limits_mm(
            placement.component
        )
        width_budget_px = (
            placement.source_frame_geometry.width_state.design_budget_px(
                DIRECT_USE_BUDGET_SPEC.sequence_axis_ratio_per_side
            ).minimum
        )
        height_budget_px = (
            placement.source_frame_geometry.height_state.design_budget_px(
                DIRECT_USE_BUDGET_SPEC.cross_axis_ratio_per_side
            ).minimum
        )
        for width in placement.sequence_placements:
            start_position = width.fit_positions_px[index * 2]
            end_position = width.fit_positions_px[index * 2 + 1]
            for role, position, actual_offset, limit_mm in (
                (
                    BoundaryRole.START,
                    start_position.maximum,
                    min(actual_offsets[BoundaryRole.START]),
                    width_limit,
                ),
                (
                    BoundaryRole.END,
                    end_position.minimum,
                    max(actual_offsets[BoundaryRole.END]),
                    width_limit,
                ),
            ):
                boundary = frame.start if role == BoundaryRole.START else frame.end
                boundary_offset = _line_offset_at_position(
                    boundary,
                    position,
                    frame.start.line,
                )
                expansion_px = max(
                    0.0,
                    boundary_offset - actual_offset
                    if role == BoundaryRole.START
                    else actual_offset - boundary_offset,
                )
                expansion_mm = placement.source_frame_geometry.width_state.worst_case_mm(
                    expansion_px
                )
                candidate = (
                    expansion_mm - limit_mm,
                    expansion_mm,
                    expansion_px,
                    -limit_mm,
                    limit_mm,
                    width.placement_id,
                    expansion_px <= width_budget_px,
                )
                current = worst.get(role)
                if current is None or candidate > current:
                    worst[role] = candidate
        for height in placement.cross_placements:
            for role, position, actual_offset in (
                (
                    BoundaryRole.TOP,
                    height.top_fit_positions_px[index].maximum,
                    min(actual_offsets[BoundaryRole.TOP]),
                ),
                (
                    BoundaryRole.BOTTOM,
                    height.bottom_fit_positions_px[index].minimum,
                    max(actual_offsets[BoundaryRole.BOTTOM]),
                ),
            ):
                boundary = frame.top if role == BoundaryRole.TOP else frame.bottom
                boundary_offset = _line_offset_at_position(
                    boundary,
                    position,
                    frame.start.line,
                )
                expansion_px = max(
                    0.0,
                    boundary_offset - actual_offset
                    if role == BoundaryRole.TOP
                    else actual_offset - boundary_offset,
                )
                expansion_mm = placement.source_frame_geometry.height_state.worst_case_mm(
                    expansion_px
                )
                candidate = (
                    expansion_mm - height_limit,
                    expansion_mm,
                    expansion_px,
                    -height_limit,
                    height_limit,
                    height.placement_id,
                    expansion_px <= height_budget_px,
                )
                current = worst.get(role)
                if current is None or candidate > current:
                    worst[role] = candidate
    edge_assessments = tuple(
        DirectUseBudgetEdgeAssessment(
            role=role,
            expansion_px=worst[role][2],
            expansion_mm=worst[role][1],
            limit_mm=worst[role][4],
            within_limit=worst[role][6],
            worst_placement_solution_id=worst[role][5],
        )
        for role in (
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
        )
    )
    state = (
        EvidenceState.SUPPORTED
        if all(item.within_limit for item in edge_assessments)
        else EvidenceState.CONTRADICTED
    )
    return DirectUseBudgetAssessment(
        geometry_id=output_geometry.geometry_id,
        placement_solution_ids=tuple(
            sorted(item.placement_id for item in placements)
        ),
        edge_assessments=edge_assessments,
        state=state,
        named_gap=None,
    )
