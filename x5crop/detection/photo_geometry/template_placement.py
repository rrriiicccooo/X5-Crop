"""Compose fixed-size source frames from selected template fits."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...formats import FramePhysicalSpec
from ...geometry.convex import ConvexPolygon, signed_area
from ...run_local_identity import run_local_id
from .boundary_geometry import canonical_boundary_line
from .interval_math import (
    add as _interval_sum,
    intersect as _intersect,
    subtract as _interval_difference,
)
from .model import BoundaryAxis, BoundaryRole, PositionSource
from .output_model import FrameBoundaryGeometry, OutputBoundaryUse
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFit
from .template_enclosing_support_aperture import (
    EnclosingSupportApertureAuthority,
    derive_enclosing_support_aperture_authority,
)
from .template_model import (
    OverlapRelation,
    SequenceFit,
    SequenceRoleLineEvidence,
    TemplateSpec,
)


_ROLES = (
    BoundaryRole.TOP,
    BoundaryRole.BOTTOM,
    BoundaryRole.START,
    BoundaryRole.END,
)
_EPSILON = 1.0e-8


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


def _oriented_width(
    start: FiniteInterval,
    end: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    return (
        _interval_difference(end, start)
        if direction > 0
        else _interval_difference(start, end)
    )


def _canonical_width(sequence: SequenceFit, template: TemplateSpec) -> float:
    width = float(sequence.pitch_fit.canonical_frame_width_px)
    if not (
        template.frame_width_px.minimum - _EPSILON
        <= width
        <= template.frame_width_px.maximum + _EPSILON
    ):
        raise ValueError("sequence canonical width contradicts template width")
    return width


def _validate_interval_contains(
    interval: FiniteInterval,
    value: float,
    *,
    name: str,
) -> None:
    if not interval.contains(value, epsilon=_EPSILON):
        raise ValueError(f"{name} canonical position leaves its interval")


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
            or tuple(
                item.role
                for item in (self.top, self.bottom, self.start, self.end)
            )
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
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    enclosing_support_aperture_authority: (
        EnclosingSupportApertureAuthority
    )
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
            or not self.frames
            or tuple(frame.lane_ordinal for frame in self.frames)
            != tuple(range(1, self.output_slot_count + 1))
        ):
            raise ValueError("format placement identity or authority is inconsistent")
        if not isinstance(self.width_authority_px, FiniteInterval) or not isinstance(
            self.height_authority_px, FiniteInterval
        ):
            raise TypeError("format placement lane authority must be intervals")
        if not isinstance(
            self.enclosing_support_aperture_authority,
            EnclosingSupportApertureAuthority,
        ):
            raise TypeError(
                "format placement enclosing-support authority is invalid"
            )
        support_output = (
            self.cross_fit.boundary_use
            == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        )
        if support_output == (
            self.enclosing_support_aperture_authority.state
            == EvidenceState.NOT_APPLICABLE
        ):
            raise ValueError(
                "format placement support and aperture authority disagree"
            )
        for frame in self.frames:
            for boundary in (frame.top, frame.bottom, frame.start, frame.end):
                if boundary.line.source_axis_long != self.width_axis:
                    raise ValueError("frame boundary authority disagrees with placement")


@dataclass(frozen=True)
class _ResolvedBoundary:
    role: BoundaryRole
    canonical: float
    full_interval: FiniteInterval
    observation_ids: tuple[ObservationId, ...]
    source: PositionSource
    inference: str | None
    line_evidence: SequenceRoleLineEvidence | None


def _sequence_boundary(
    sequence: SequenceFit,
    template: TemplateSpec,
    role_index: int,
) -> _ResolvedBoundary:
    role = template.roles[role_index]
    interval = sequence.model_full_role_intervals_px[role_index]
    canonical = float(sequence.model_role_positions_px[role_index])
    binding = sequence.role_bindings[role_index]
    if binding is not None:
        ids = (binding.observation_id,)
        source = PositionSource.OBSERVED_TRANSITION
        inference = None
        canonical = binding.canonical_position_px
        interval = binding.full_position_interval_px
        line_evidence = binding.line_evidence
    else:
        ids = tuple(sequence.bound_observation_ids)
        if not ids:
            raise ValueError("template-inferred sequence edge lacks direct authority")
        source = PositionSource.INFERRED_SEQUENCE
        inference = f"{role.role.value}_from_template_fixed_width"
        line_evidence = None
    return _ResolvedBoundary(
        role=role.role,
        canonical=canonical,
        full_interval=interval,
        observation_ids=ids,
        source=source,
        inference=inference,
        line_evidence=line_evidence,
    )


def _shift_sequence_line_evidence(
    evidence: SequenceRoleLineEvidence | None,
    delta_px: float,
) -> SequenceRoleLineEvidence | None:
    if evidence is None:
        return None
    return SequenceRoleLineEvidence(
        observation_id=evidence.observation_id,
        reference_trace_px=evidence.reference_trace_px,
        fit_position_interval_px=FiniteInterval(
            evidence.fit_position_interval_px.minimum + delta_px,
            evidence.fit_position_interval_px.maximum + delta_px,
        ),
        fit_direction_interval_degrees=(
            evidence.fit_direction_interval_degrees
        ),
    )


def _sequence_pair(
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
    measured_width = sequence.pitch_fit.frame_width_px
    if start_direct and not end_direct:
        inferred_interval = _advance(
            start.full_interval,
            measured_width,
            template.direction,
        )
        inferred_canonical = start.canonical + width * template.direction
        end = _ResolvedBoundary(
            role=end.role,
            canonical=inferred_canonical,
            full_interval=inferred_interval,
            observation_ids=end.observation_ids,
            source=end.source,
            inference="end_from_observed_start_and_correlated_source_frame_width",
            line_evidence=_shift_sequence_line_evidence(
                start.line_evidence,
                width * template.direction,
            ),
        )
    elif end_direct and not start_direct:
        inferred_interval = _retreat(
            end.full_interval,
            measured_width,
            template.direction,
        )
        inferred_canonical = end.canonical - width * template.direction
        start = _ResolvedBoundary(
            role=start.role,
            canonical=inferred_canonical,
            full_interval=inferred_interval,
            observation_ids=start.observation_ids,
            source=start.source,
            inference="start_from_observed_end_and_correlated_source_frame_width",
            line_evidence=_shift_sequence_line_evidence(
                end.line_evidence,
                -width * template.direction,
            ),
        )
    return start, end


def _resolve_sequence_pair(
    sequence: SequenceFit,
    template: TemplateSpec,
    ordinal: int,
    width: float,
) -> tuple[_ResolvedBoundary, _ResolvedBoundary]:
    start, end = _sequence_pair(sequence, template, ordinal, width)
    # When both sides are direct, each keeps its own measured physical
    # interval.  Fixed W is already enforced by the selected placement's
    # joint feasible set; hulling a direct END with START + the independent
    # source-scale extrema would manufacture a state that no observation and
    # no joint solution supports.
    _validate_interval_contains(
        start.full_interval,
        start.canonical,
        name="start",
    )
    _validate_interval_contains(end.full_interval, end.canonical, name="end")
    oriented = _oriented_width(
        start.full_interval,
        end.full_interval,
        template.direction,
    )
    width_value = template.direction * (end.canonical - start.canonical)
    frame_width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    if (
        not template.frame_width_px.minimum - _EPSILON
        <= width_value
        <= template.frame_width_px.maximum + _EPSILON
        or _intersect(oriented, frame_width) is None
    ):
        raise ValueError("sequence frame edges contradict fixed template width")
    return start, end


def _resolved_sequence_pairs(
    sequence: SequenceFit,
    template: TemplateSpec,
) -> tuple[tuple[_ResolvedBoundary, _ResolvedBoundary], ...]:
    width = _canonical_width(sequence, template)
    return tuple(
        _resolve_sequence_pair(sequence, template, ordinal, width)
        for ordinal in range(template.count)
    )


def resolved_sequence_support_domains_px(
    sequence: SequenceFit,
) -> tuple[FiniteInterval, ...]:
    """Return the realized long-axis domain of every fixed-template frame.

    Direct observations own their native coordinates; fixed-W inference fills
    only an unobserved opposite side.  Cross registration and final placement
    must therefore consult this same resolved geometry instead of the model
    lattice that merely organized the observations.
    """

    template = sequence.template
    width = _canonical_width(sequence, template)
    return tuple(
        FiniteInterval(
            min(start.canonical, end.canonical),
            max(start.canonical, end.canonical),
        )
        for start, end in (
            _sequence_pair(sequence, template, ordinal, width)
            for ordinal in range(template.count)
        )
    )


def resolved_cross_support_domains_px(
    sequence: SequenceFit,
) -> tuple[FiniteInterval, ...]:
    """Partition explicit overlap into disjoint short-axis support domains.

    Output geometry keeps both physical Frame domains.  Cross-axis evidence,
    however, must not count one trace in their shared area as two independent
    Frame regions.  A proven overlap is therefore split at its midpoint only
    for support accounting.  Any unmodeled or geometrically inconsistent
    overlap remains a fixed-template mismatch.
    """

    domains = list(resolved_sequence_support_domains_px(sequence))
    overlaps = {
        relation.relation_ordinal: relation
        for relation in sequence.adjacency_relations
        if isinstance(relation, OverlapRelation)
    }
    for ordinal, (left, right) in enumerate(
        zip(domains, domains[1:]),
        start=1,
    ):
        overlap_minimum = max(left.minimum, right.minimum)
        overlap_maximum = min(left.maximum, right.maximum)
        overlap_px = max(0.0, overlap_maximum - overlap_minimum)
        relation = overlaps.get(ordinal)
        if (overlap_px > _EPSILON) != (relation is not None):
            raise ValueError(
                "realized Frame overlap lacks one explicit OverlapRelation"
            )
        if relation is None:
            continue
        if abs(overlap_px + relation.canonical_signed_gap_px) > _EPSILON:
            raise ValueError(
                "realized Frame overlap contradicts its signed gap"
            )
        split = (overlap_minimum + overlap_maximum) / 2.0
        if sequence.template.direction > 0:
            domains[ordinal - 1] = FiniteInterval(left.minimum, split)
            domains[ordinal] = FiniteInterval(split, right.maximum)
        else:
            domains[ordinal - 1] = FiniteInterval(split, left.maximum)
            domains[ordinal] = FiniteInterval(right.minimum, split)
    ordered = tuple(sorted(domains, key=lambda item: item.minimum))
    if any(
        left.maximum > right.minimum + _EPSILON
        for left, right in zip(ordered, ordered[1:])
    ):
        raise ValueError("cross support domains retain an unmodeled overlap")
    return ordered


def _cross_boundaries(
    cross: CrossFit,
) -> tuple[_ResolvedBoundary, _ResolvedBoundary]:
    direct = {item.role: item for item in cross.direct_bindings}
    inferred = {item.role: item for item in cross.inferred_bindings}
    result: list[_ResolvedBoundary] = []
    for role, canonical, full_interval in (
        (BoundaryRole.TOP, cross.top_canonical_px, cross.top_full_interval_px),
        (
            BoundaryRole.BOTTOM,
            cross.bottom_canonical_px,
            cross.bottom_full_interval_px,
        ),
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
        result.append(
            _ResolvedBoundary(
                role=role,
                canonical=canonical,
                full_interval=full_interval,
                observation_ids=ids,
                source=source,
                inference=inference,
                line_evidence=None,
            )
        )
    if cross.bottom_canonical_px <= cross.top_canonical_px:
        raise ValueError("cross top/bottom order contradicts source coordinates")
    if not cross.fixed_height_px.contains(
        cross.bottom_canonical_px - cross.top_canonical_px,
        epsilon=_EPSILON,
    ):
        raise ValueError("cross span contradicts fixed template height")
    return result[0], result[1]


def _boundary_geometry(
    resolved: _ResolvedBoundary,
    *,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    local_outward_departure_px: float = 0.0,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
) -> FrameBoundaryGeometry:
    boundary_axis = (
        width_axis
        if resolved.role in {BoundaryRole.START, BoundaryRole.END}
        else height_axis
    )
    return FrameBoundaryGeometry(
        role=resolved.role,
        line=canonical_boundary_line(
            boundary_axis=boundary_axis,
            source_axis_long=width_axis,
            position_px=resolved.canonical,
            support_projection_px=support_projection_px,
        ),
        reference_trace_px=reference_trace_px,
        canonical_position_px=resolved.canonical,
        full_position_interval_px=resolved.full_interval,
        local_outward_departure_px=local_outward_departure_px,
        position_source=resolved.source,
        position_observation_ids=resolved.observation_ids,
        named_position_inference=resolved.inference,
    )


def _aperture_corner_outward_departure_px(
    cross: CrossFit,
    cross_support_px: FiniteInterval,
) -> float:
    """Contain aperture corners without creating a placement frame axis.

    A resolved direct top/bottom aperture pair proves the local orientation of
    the fixed-H photo region.  Its fit interval may therefore enlarge the two
    source-axis side bounds by the half-height corner departure.  Enclosing
    support and one-sided inference do not prove that relation and contribute
    nothing here.
    """

    if (
        cross.boundary_use != OutputBoundaryUse.APERTURE_PAIR
        or not cross.direct_pair
        or len(cross.direct_bindings) != 2
    ):
        return 0.0
    directions = tuple(
        item.fit_direction_interval_degrees
        for item in cross.direct_bindings
        if item.fit_direction_interval_degrees is not None
    )
    if not directions:
        return 0.0
    maximum_slope = max(
        abs(math.tan(math.radians(angle)))
        for interval in directions
        for angle in (interval.minimum, interval.maximum)
    )
    return maximum_slope * cross_support_px.width / 2.0


def _sequence_line_outward_departure_px(
    boundary: _ResolvedBoundary,
    cross_support_px: FiniteInterval,
    direction: int,
) -> float:
    """Protect only fitted-line extent not already owned by full position."""

    evidence = boundary.line_evidence
    if evidence is None:
        return 0.0
    projected = tuple(
        position
        - math.tan(math.radians(angle))
        * (trace - evidence.reference_trace_px)
        for position in (
            evidence.fit_position_interval_px.minimum,
            evidence.fit_position_interval_px.maximum,
        )
        for angle in (
            evidence.fit_direction_interval_degrees.minimum,
            evidence.fit_direction_interval_degrees.maximum,
        )
        for trace in (
            cross_support_px.minimum,
            cross_support_px.maximum,
        )
    )
    outward_is_positive = (
        boundary.role == BoundaryRole.END
    ) == (direction > 0)
    if outward_is_positive:
        return max(0.0, max(projected) - boundary.full_interval.maximum)
    return max(0.0, boundary.full_interval.minimum - min(projected))


def _aperture_center_shift_px(
    cross: CrossFit,
    target_trace_px: float,
) -> float | None:
    if cross.boundary_use != OutputBoundaryUse.APERTURE_PAIR:
        return None
    shifts: list[float] = []
    for binding in cross.direct_bindings:
        shift = binding.projected_shift_px(
            source_trace_px=cross.lane_reference_trace_px,
            target_trace_px=target_trace_px,
        )
        if shift is not None:
            shifts.append(shift)
    return sum(shifts) / len(shifts) if shifts else None


def _shift_boundary(
    boundary: _ResolvedBoundary,
    shift_px: float,
) -> _ResolvedBoundary:
    return _ResolvedBoundary(
        role=boundary.role,
        canonical=boundary.canonical + shift_px,
        full_interval=FiniteInterval(
            boundary.full_interval.minimum + shift_px,
            boundary.full_interval.maximum + shift_px,
        ),
        observation_ids=boundary.observation_ids,
        source=boundary.source,
        inference=boundary.inference,
        line_evidence=boundary.line_evidence,
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
    placement_id: str | None = None,
) -> FormatPlacement:
    """Compose fixed-size frames once from one sequence/cross fit pair."""
    if not lane_id or not isinstance(frame_spec, FramePhysicalSpec):
        raise TypeError("format placement requires lane and frame spec")
    if not isinstance(source_scan_geometry, SourceScanGeometry):
        raise TypeError("format placement requires source scan geometry")
    if not isinstance(sequence_fit, SequenceFit) or not isinstance(
        cross_fit,
        CrossFit,
    ):
        raise TypeError("format placement requires canonical template fits")
    if template is None:
        template = sequence_fit.template
    if not isinstance(template, TemplateSpec) or sequence_fit.template != template:
        raise ValueError("sequence fit and template disagree")
    if source_scan_geometry.frame_spec != frame_spec:
        raise ValueError("source scan and requested frame specifications disagree")
    if cross_fit.template_id != template.template_id:
        raise ValueError("cross fit and template identities disagree")
    if (
        width_axis == height_axis
        or not isinstance(width_axis, BoundaryAxis)
        or not isinstance(height_axis, BoundaryAxis)
    ):
        raise ValueError("placement source axes must be distinct typed axes")
    if not isinstance(width_authority_px, FiniteInterval) or not isinstance(
        height_authority_px,
        FiniteInterval,
    ):
        raise TypeError("lane authority must use FiniteInterval")
    if not math.isfinite(cross_fit.lane_reference_trace_px):
        raise ValueError("cross lane reference trace is not finite")
    if len(sequence_fit.model_role_intervals_px) != 2 * template.count:
        raise ValueError("sequence fit count contradicts template count")
    if template.frame_height_px is not None and not _intersects(
        template.frame_height_px, cross_fit.fixed_height_px
    ):
        raise ValueError("cross fixed height contradicts template frame height")
    cross_top, cross_bottom = _cross_boundaries(cross_fit)
    frames: list[TemplateFrame] = []
    for ordinal, (start, end) in enumerate(
        _resolved_sequence_pairs(sequence_fit, template)
    ):
        frame_reference = (start.canonical + end.canonical) / 2.0
        projected_cross_shift = _aperture_center_shift_px(
            cross_fit,
            frame_reference,
        )
        cross_shift = 0.0 if projected_cross_shift is None else projected_cross_shift
        frame_top = _shift_boundary(cross_top, cross_shift)
        frame_bottom = _shift_boundary(cross_bottom, cross_shift)
        frame_width_support = FiniteInterval(
            min(start.full_interval.minimum, end.full_interval.minimum),
            max(start.full_interval.maximum, end.full_interval.maximum),
        )
        frame_cross_support = FiniteInterval(
            min(
                frame_top.full_interval.minimum,
                frame_bottom.full_interval.minimum,
            ),
            max(
                frame_top.full_interval.maximum,
                frame_bottom.full_interval.maximum,
            ),
        )
        aperture_side_departure = _aperture_corner_outward_departure_px(
            cross_fit,
            frame_cross_support,
        )
        start_geometry = _boundary_geometry(
            start,
            reference_trace_px=frame_cross_support.center,
            support_projection_px=frame_cross_support,
            local_outward_departure_px=max(
                aperture_side_departure,
                _sequence_line_outward_departure_px(
                    start,
                    frame_cross_support,
                    template.direction,
                ),
            ),
            width_axis=width_axis,
            height_axis=height_axis,
        )
        end_geometry = _boundary_geometry(
            end,
            reference_trace_px=frame_cross_support.center,
            support_projection_px=frame_cross_support,
            local_outward_departure_px=max(
                aperture_side_departure,
                _sequence_line_outward_departure_px(
                    end,
                    frame_cross_support,
                    template.direction,
                ),
            ),
            width_axis=width_axis,
            height_axis=height_axis,
        )
        cross_reference = (
            frame_reference
            if (
                projected_cross_shift is not None
                or cross_fit.boundary_use
                == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
            )
            else cross_fit.lane_reference_trace_px
        )
        top_geometry = _boundary_geometry(
            frame_top,
            reference_trace_px=cross_reference,
            support_projection_px=frame_width_support,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        bottom_geometry = _boundary_geometry(
            frame_bottom,
            reference_trace_px=cross_reference,
            support_projection_px=frame_width_support,
            width_axis=width_axis,
            height_axis=height_axis,
        )
        polygon = (
            top_geometry.line.intersection(start_geometry.line),
            top_geometry.line.intersection(end_geometry.line),
            bottom_geometry.line.intersection(end_geometry.line),
            bottom_geometry.line.intersection(start_geometry.line),
        )
        if (
            any(
                not math.isfinite(value)
                for point in polygon
                for value in point
            )
            or abs(signed_area(polygon)) <= _EPSILON
        ):
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
    realized_geometry_identity = (
        cross_fit.line_projection_basis.value,
        tuple(
            (
                frame.lane_ordinal,
                *tuple(
                    (
                        boundary.canonical_position_px.hex(),
                        boundary.full_position_interval_px.minimum.hex(),
                        boundary.full_position_interval_px.maximum.hex(),
                        tuple(map(str, boundary.position_observation_ids)),
                    )
                    for boundary in (
                        frame.start,
                        frame.end,
                        frame.top,
                        frame.bottom,
                    )
                ),
            )
            for frame in frames
        ),
    )
    identity = placement_id or run_local_id(
        "template-placement",
        lane_id,
        template.template_id,
        source_scan_geometry.geometry_id,
        realized_geometry_identity,
    )
    return FormatPlacement(
        placement_id=identity,
        lane_id=lane_id,
        frame_spec=frame_spec,
        output_slot_count=template.count,
        source_scan_geometry=source_scan_geometry,
        sequence_fit=sequence_fit,
        cross_fit=cross_fit,
        width_axis=width_axis,
        height_axis=height_axis,
        width_authority_px=width_authority_px,
        height_authority_px=height_authority_px,
        enclosing_support_aperture_authority=(
            derive_enclosing_support_aperture_authority(cross_fit)
        ),
        frames=tuple(frames),
    )


def _intersects(left: FiniteInterval, right: FiniteInterval) -> bool:
    return (
        max(left.minimum, right.minimum)
        <= min(left.maximum, right.maximum) + _EPSILON
    )
