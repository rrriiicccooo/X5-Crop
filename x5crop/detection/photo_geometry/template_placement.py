"""Compose fixed-size source frames from selected template fits."""
from __future__ import annotations
from dataclasses import dataclass
import math
from ...domain import FiniteInterval, ObservationId
from ...formats import FramePhysicalSpec
from ...geometry.convex import ConvexPolygon, signed_area
from .boundary_geometry import canonical_boundary_line
from .model import BoundaryAxis, BoundaryRole, DirectionAuthority, PositionSource
from .output_model import FrameBoundaryGeometry, SharedStripDirection
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFit
from .template_model import SequenceFit, TemplateSpec
_ROLES = (BoundaryRole.TOP, BoundaryRole.BOTTOM, BoundaryRole.START, BoundaryRole.END)
_EPSILON = 1.0e-8
def _interval_difference(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum - right.maximum, left.maximum - right.minimum)
def _interval_sum(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum + right.minimum, left.maximum + right.maximum)
def _intersect(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if minimum > maximum:
        raise ValueError("inferred boundary contradicts its template edge")
    return FiniteInterval(minimum, maximum)


def _advance(
    position: FiniteInterval,
    extent: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    return (
        _interval_sum(position, extent)
        if direction > 0
        else _interval_difference(position, extent)
    )


def _retreat(
    position: FiniteInterval,
    extent: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    return (
        _interval_difference(position, extent)
        if direction > 0
        else _interval_sum(position, extent)
    )
def _oriented_width(start: FiniteInterval, end: FiniteInterval, direction: int) -> FiniteInterval:
    return _interval_difference(end, start) if direction > 0 else _interval_difference(start, end)
def _canonical_width(sequence: SequenceFit, template: TemplateSpec) -> float:
    width = float(sequence.pitch_fit.canonical_frame_width_px)
    if not template.frame_width_px.minimum - _EPSILON <= width <= template.frame_width_px.maximum + _EPSILON:
        raise ValueError("sequence canonical width contradicts template width")
    return width
def _validate_interval_contains(interval: FiniteInterval, value: float, *, name: str) -> None:
    if not interval.contains(value, epsilon=_EPSILON):
        raise ValueError(f"{name} canonical position leaves its interval")


def _cross_direction_compatible(
    cross: CrossFit,
    direction: SharedStripDirection,
) -> bool:
    selected = cross.selected_direction
    if selected is None:
        return True
    compatibility = (
        cross.parallel_direction_interval_degrees
        or selected.full_angle_interval_degrees
    )
    return (
        compatibility.contains(
            direction.canonical_angle_degrees,
            epsilon=_EPSILON,
        )
        and set(selected.selected_observation_ids).issubset(
            direction.selected_observation_ids
        )
    )
@dataclass(frozen=True)
class TemplateFrame:
    """One fixed W/H frame and its four source-coordinate boundaries."""
    lane_ordinal: int
    top: FrameBoundaryGeometry
    bottom: FrameBoundaryGeometry
    start: FrameBoundaryGeometry
    end: FrameBoundaryGeometry
    canonical_source_polygon: ConvexPolygon
    def __post_init__(self) -> None:
        if (
            self.lane_ordinal <= 0
            or tuple(item.role for item in (self.top, self.bottom, self.start, self.end))
            != _ROLES
            or len(self.canonical_source_polygon) != 4
            or any(
                not math.isfinite(value)
                for point in self.canonical_source_polygon
                for value in point
            )
            or abs(signed_area(self.canonical_source_polygon)) <= _EPSILON
        ):
            raise ValueError("template frame is degenerate or has invalid roles")
@dataclass(frozen=True)
class FormatPlacement:
    """One lane's fixed-count placement from selected template fits."""
    placement_id: str
    lane_id: str
    frame_spec: FramePhysicalSpec
    output_slot_count: int
    source_scan_geometry: SourceScanGeometry
    sequence_fit: SequenceFit
    cross_fit: CrossFit
    direction: SharedStripDirection
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    frames: tuple[TemplateFrame, ...]
    def __post_init__(self) -> None:
        template = self.sequence_fit.template
        if (
            not self.placement_id
            or not self.lane_id
            or self.output_slot_count != template.count
            or self.source_scan_geometry.frame_spec != self.frame_spec
            or self.cross_fit.template_id != template.template_id
            or self.width_axis == self.height_axis
            or not isinstance(self.direction, SharedStripDirection)
            or not self.frames
            or tuple(frame.lane_ordinal for frame in self.frames)
            != tuple(range(1, self.output_slot_count + 1))
            or not _cross_direction_compatible(self.cross_fit, self.direction)
        ):
            raise ValueError("format placement identity or authority is inconsistent")
        if not isinstance(self.width_authority_px, FiniteInterval) or not isinstance(
            self.height_authority_px, FiniteInterval
        ):
            raise TypeError("format placement lane authority must be intervals")
        for frame in self.frames:
            for boundary in (frame.top, frame.bottom, frame.start, frame.end):
                if boundary.line.source_axis_long != self.width_axis or boundary.direction_reference_id != self.direction.direction_id:
                    raise ValueError("frame boundary authority disagrees with placement")
@dataclass(frozen=True)
class _ResolvedBoundary:
    role: BoundaryRole
    canonical: float
    full_interval: FiniteInterval
    observation_ids: tuple[ObservationId, ...]
    source: PositionSource
    inference: str | None
def _sequence_boundary(
    sequence: SequenceFit,
    template: TemplateSpec,
    role_index: int,
) -> _ResolvedBoundary:
    role = template.roles[role_index]
    interval = sequence.role_positions_px[role_index]
    canonical = float(sequence.canonical_role_positions_px[role_index])
    identity = sequence.role_observation_ids[role_index]
    direct = role_index in sequence.matched_role_indices
    inferred = role_index in sequence.inferred_role_indices
    if direct != (identity is not None) or inferred != (identity is None):
        raise ValueError("sequence role ledger and observation identity disagree")
    if direct:
        ids = (identity,)
        assert identity is not None
        source = PositionSource.OBSERVED_TRANSITION
        inference = None
    else:
        ids = tuple(sequence.direct_observation_ids)
        if not ids:
            raise ValueError("template-inferred sequence edge lacks direct authority")
        source = PositionSource.INFERRED_SEQUENCE
        inference = f"{role.role.value}_from_template_fixed_width"
    return _ResolvedBoundary(role.role, canonical, interval, ids, source, inference)
def _resolve_sequence_pair(
    sequence: SequenceFit,
    template: TemplateSpec,
    ordinal: int,
    width: float,
) -> tuple[_ResolvedBoundary, _ResolvedBoundary]:
    start_index = 2 * ordinal
    end_index = start_index + 1
    start = _sequence_boundary(sequence, template, start_index)
    end = _sequence_boundary(sequence, template, end_index)
    start_direct = start.source == PositionSource.OBSERVED_TRANSITION
    end_direct = end.source == PositionSource.OBSERVED_TRANSITION
    if start_direct and not end_direct:
        inferred_interval = _advance(
            start.full_interval,
            template.frame_width_px,
            template.direction,
        )
        inferred_canonical = start.canonical + width * template.direction
        end = _ResolvedBoundary(
            end.role,
            inferred_canonical,
            inferred_interval,
            end.observation_ids,
            end.source,
            "end_from_observed_start_and_fixed_template_width",
        )
    elif end_direct and not start_direct:
        inferred_interval = _retreat(
            end.full_interval,
            template.frame_width_px,
            template.direction,
        )
        inferred_canonical = end.canonical - width * template.direction
        start = _ResolvedBoundary(
            start.role,
            inferred_canonical,
            inferred_interval,
            start.observation_ids,
            start.source,
            "start_from_observed_end_and_fixed_template_width",
        )
    elif start_direct and end_direct:
        # Both observations bind one discrete placement, while fixed W carries
        # the continuous model uncertainty between them.  Retain both direct
        # identities, but propagate the same-placement W interval in both
        # directions so SafeCrop can protect a weak transition that landed on
        # the photo-side edge of a border.  This never mixes a runner-up phase
        # or another role assignment into the selected envelope.
        end_from_start = _advance(
            start.full_interval,
            template.frame_width_px,
            template.direction,
        )
        start_from_end = _retreat(
            end.full_interval,
            template.frame_width_px,
            template.direction,
        )
        model_budget = (
            template.frame_width_px.maximum
            - template.frame_width_px.minimum
        ) / 2.0
        start = _ResolvedBoundary(
            start.role,
            start.canonical,
            FiniteInterval(
                min(start.full_interval.minimum, start_from_end.minimum),
                max(
                    start.full_interval.maximum,
                    start_from_end.maximum + model_budget,
                ),
            ),
            start.observation_ids,
            start.source,
            start.inference,
        )
        end = _ResolvedBoundary(
            end.role,
            end.canonical,
            FiniteInterval(
                min(end.full_interval.minimum, end_from_start.minimum),
                max(
                    end.full_interval.maximum,
                    end_from_start.maximum + model_budget,
                ),
            ),
            end.observation_ids,
            end.source,
            end.inference,
        )
    _validate_interval_contains(start.full_interval, start.canonical, name="start")
    _validate_interval_contains(end.full_interval, end.canonical, name="end")
    oriented = _oriented_width(start.full_interval, end.full_interval, template.direction)
    width_value = template.direction * (end.canonical - start.canonical)
    frame_width = FiniteInterval(template.frame_width_px.minimum, template.frame_width_px.maximum)
    if not template.frame_width_px.minimum - _EPSILON <= width_value <= template.frame_width_px.maximum + _EPSILON or _intersect(oriented, frame_width) is None:
        raise ValueError("sequence frame edges contradict fixed template width")
    return start, end
def _cross_boundaries(
    cross: CrossFit,
    direction: SharedStripDirection,
) -> tuple[_ResolvedBoundary, _ResolvedBoundary]:
    direct = {item.role: item for item in cross.direct_bindings}
    inferred = {item.role: item for item in cross.inferred_bindings}
    result: list[_ResolvedBoundary] = []
    for role, canonical, full_interval in (
        (BoundaryRole.TOP, cross.top_canonical_px, cross.top_full_interval_px),
        (BoundaryRole.BOTTOM, cross.bottom_canonical_px, cross.bottom_full_interval_px),
    ):
        binding = direct.get(role)
        if binding is not None:
            ids = (binding.observation_id,)
            source = PositionSource.OBSERVED_TRANSITION
            inference = None
        else:
            binding = inferred.get(role)
            if binding is None:
                raise ValueError("cross fit does not provide both short-axis roles")
            ids = tuple(binding.source_observation_ids)
            if not ids:
                raise ValueError("inferred cross edge lacks direct source IDs")
            source = PositionSource.INFERRED_OPPOSITE_EDGE
            opposite = "top" if role == BoundaryRole.BOTTOM else "bottom"
            inference = f"{role.value}_from_observed_{opposite}_and_fixed_template_height"
        _validate_interval_contains(full_interval, canonical, name=role.value)
        result.append(_ResolvedBoundary(role, canonical, full_interval, ids, source, inference))
    if cross.bottom_canonical_px <= cross.top_canonical_px:
        raise ValueError("cross top/bottom order contradicts source coordinates")
    if not cross.fixed_height_px.contains(
        cross.bottom_canonical_px - cross.top_canonical_px,
        epsilon=_EPSILON,
    ):
        raise ValueError("cross span contradicts fixed template height")
    if not _cross_direction_compatible(cross, direction):
        raise ValueError("cross-selected direction contradicts placement direction")
    return result[0], result[1]
def _boundary_geometry(
    resolved: _ResolvedBoundary,
    *,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    direction: SharedStripDirection,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
) -> FrameBoundaryGeometry:
    boundary_axis = width_axis if resolved.role in {BoundaryRole.START, BoundaryRole.END} else height_axis
    return FrameBoundaryGeometry(
        role=resolved.role,
        line=canonical_boundary_line(
            direction,
            boundary_axis=boundary_axis,
            source_axis_long=width_axis,
            trace_coordinate_px=reference_trace_px,
            position_px=resolved.canonical,
            support_projection_px=support_projection_px,
        ),
        reference_trace_px=reference_trace_px,
        canonical_position_px=resolved.canonical,
        full_position_interval_px=resolved.full_interval,
        full_direction_interval_degrees=direction.full_angle_interval_degrees,
        position_source=resolved.source,
        position_observation_ids=resolved.observation_ids,
        named_position_inference=resolved.inference,
        direction_authority=(
            DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            if resolved.role in {BoundaryRole.START, BoundaryRole.END}
            else DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ),
        direction_reference_id=direction.direction_id,
    )
def _reanchor_cross_boundary(
    resolved: _ResolvedBoundary,
    *,
    source_trace_px: float,
    target_trace_px: float,
    support_projection_px: FiniteInterval,
    direction: SharedStripDirection,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
) -> _ResolvedBoundary:
    """Move a cross edge coordinate to a frame trace on its line."""
    del support_projection_px, width_axis, height_axis

    def at_trace(position_px: float, angle_degrees: float) -> float:
        return position_px + math.tan(math.radians(angle_degrees)) * (
            target_trace_px - source_trace_px
        )

    canonical = at_trace(
        resolved.canonical,
        direction.canonical_angle_degrees,
    )
    endpoints = tuple(
        at_trace(value, angle)
        for value in (resolved.full_interval.minimum, resolved.full_interval.maximum)
        for angle in (
            direction.full_angle_interval_degrees.minimum,
            direction.full_angle_interval_degrees.maximum,
        )
    )
    return _ResolvedBoundary(
        resolved.role,
        canonical,
        FiniteInterval(min(endpoints), max(endpoints)),
        resolved.observation_ids,
        resolved.source,
        resolved.inference,
    )
def compose_format_placement(
    *,
    lane_id: str,
    frame_spec: FramePhysicalSpec,
    source_scan_geometry: SourceScanGeometry,
    sequence_fit: SequenceFit,
    cross_fit: CrossFit,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    width_authority_px: FiniteInterval,
    height_authority_px: FiniteInterval,
    template: TemplateSpec | None = None,
    direction: SharedStripDirection | None = None,
    placement_id: str | None = None,
) -> FormatPlacement:
    """Compose fixed-size frames once from one sequence/cross fit pair."""
    if not lane_id or not isinstance(frame_spec, FramePhysicalSpec):
        raise TypeError("format placement requires lane and frame spec")
    if not isinstance(source_scan_geometry, SourceScanGeometry):
        raise TypeError("format placement requires source scan geometry")
    if not isinstance(sequence_fit, SequenceFit) or not isinstance(cross_fit, CrossFit):
        raise TypeError("format placement requires canonical template fits")
    if template is None:
        template = sequence_fit.template
    if not isinstance(template, TemplateSpec) or sequence_fit.template != template:
        raise ValueError("sequence fit and template disagree")
    if source_scan_geometry.frame_spec != frame_spec:
        raise ValueError("source scan and requested frame specifications disagree")
    if cross_fit.template_id != template.template_id:
        raise ValueError("cross fit and template identities disagree")
    if width_axis == height_axis or not isinstance(width_axis, BoundaryAxis) or not isinstance(height_axis, BoundaryAxis):
        raise ValueError("placement source axes must be distinct typed axes")
    if not isinstance(width_authority_px, FiniteInterval) or not isinstance(height_authority_px, FiniteInterval):
        raise TypeError("lane authority must use FiniteInterval")
    selected_direction = cross_fit.selected_direction
    if selected_direction is not None:
        if direction is None:
            direction = selected_direction
        elif not _cross_direction_compatible(cross_fit, direction):
            raise ValueError("explicit direction contradicts cross-selected direction")
    if direction is None:
        raise ValueError("format placement requires cross-selected or explicit direction")
    if not isinstance(direction, SharedStripDirection):
        raise TypeError("placement direction must be SharedStripDirection")
    if not math.isfinite(cross_fit.lane_reference_trace_px):
        raise ValueError("cross lane reference trace is not finite")
    if len(sequence_fit.role_positions_px) != 2 * template.count:
        raise ValueError("sequence fit count contradicts template count")
    width = _canonical_width(sequence_fit, template)
    if template.frame_height_px is not None and not _intersects(
        template.frame_height_px, cross_fit.fixed_height_px
    ):
        raise ValueError("cross fixed height contradicts template frame height")
    cross_top, cross_bottom = _cross_boundaries(cross_fit, direction)
    frames: list[TemplateFrame] = []
    for ordinal in range(template.count):
        start, end = _resolve_sequence_pair(sequence_fit, template, ordinal, width)
        frame_reference = (start.canonical + end.canonical) / 2.0
        frame_width_support = FiniteInterval(
            min(start.full_interval.minimum, end.full_interval.minimum),
            max(start.full_interval.maximum, end.full_interval.maximum),
        )
        start_geometry = _boundary_geometry(
            start,
            reference_trace_px=height_authority_px.center,
            support_projection_px=height_authority_px,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        end_geometry = _boundary_geometry(
            end,
            reference_trace_px=height_authority_px.center,
            support_projection_px=height_authority_px,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        frame_top = _reanchor_cross_boundary(
            cross_top,
            source_trace_px=cross_fit.lane_reference_trace_px,
            target_trace_px=frame_reference,
            support_projection_px=frame_width_support,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        frame_bottom = _reanchor_cross_boundary(
            cross_bottom,
            source_trace_px=cross_fit.lane_reference_trace_px,
            target_trace_px=frame_reference,
            support_projection_px=frame_width_support,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        top_geometry = _boundary_geometry(
            frame_top,
            reference_trace_px=frame_reference,
            support_projection_px=frame_width_support,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        bottom_geometry = _boundary_geometry(
            frame_bottom,
            reference_trace_px=frame_reference,
            support_projection_px=frame_width_support,
            direction=direction,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        polygon = (
            top_geometry.line.intersection(start_geometry.line),
            top_geometry.line.intersection(end_geometry.line),
            bottom_geometry.line.intersection(end_geometry.line),
            bottom_geometry.line.intersection(start_geometry.line),
        )
        if any(not math.isfinite(value) for point in polygon for value in point) or abs(signed_area(polygon)) <= _EPSILON:
            raise ValueError("fixed template frame polygon is degenerate")
        frames.append(
            TemplateFrame(
                lane_ordinal=ordinal + 1,
                top=top_geometry,
                bottom=bottom_geometry,
                start=start_geometry,
                end=end_geometry,
                canonical_source_polygon=polygon,
            )
        )
    phase = sequence_fit.phase_lattice_fit.canonical_absolute_phase_px.hex()
    identity = placement_id or (
        f"template-placement:{lane_id}:{template.template_id}:"
        f"{source_scan_geometry.geometry_id}:{direction.direction_id}:{phase}:"
        f"{cross_fit.top_canonical_px.hex()}:{cross_fit.bottom_canonical_px.hex()}"
    )
    return FormatPlacement(
        placement_id=identity,
        lane_id=lane_id,
        frame_spec=frame_spec,
        output_slot_count=template.count,
        source_scan_geometry=source_scan_geometry,
        sequence_fit=sequence_fit,
        cross_fit=cross_fit,
        direction=direction,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority_px,
        height_authority_px=height_authority_px,
        frames=tuple(frames),
    )
def _intersects(left: FiniteInterval, right: FiniteInterval) -> bool:
    return max(left.minimum, right.minimum) <= min(left.maximum, right.maximum) + _EPSILON
