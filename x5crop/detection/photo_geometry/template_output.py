"""Selected-placement envelope, deterministic bleed, and output assessment."""

from __future__ import annotations

import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId, WorkspaceExtent
from ...formats import OUTPUT_PROTECTION_SPEC
from ...geometry.convex import (
    ConvexPolygon,
    clip_convex_polygon_to_bounds,
    convex_hull,
)
from ...run_local_identity import run_local_id
from ..source_core import SourceLaneEvidence
from .boundary_geometry import boundary_line_at_state
from .line_observations import SourceCoordinateLine
from .template_feasible_geometry import (
    FeasiblePlacementProjection,
    JointFrameState,
)
from .template_model import ContactRelation, OverlapRelation
from .model import (
    AuthoritySide,
    BoundaryRole,
)
from .output_model import (
    BoundaryProtectionFact,
    DirectUseBudgetAssessment,
    DirectUseBudgetEdgeAssessment,
    EnclosingSupportApertureRisk,
    FootprintSaturationFact,
    FootprintSaturationKind,
    FrameBoundaryGeometry,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
    footprint_outside_authority_sides,
    footprint_overflow_px,
    sampling_authority_bounds,
    source_boundary_sides,
)
from .template_placement import FormatPlacement, TemplateFrame
from .template_cross_model import (
    CrossLineProjectionBasis,
    CrossRoleBinding,
)
from .trace_support import PIXEL_CENTER_EXTENT_PX
from .robust_line_fit import physical_line_region_at_positions


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


def _state_footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
    *,
    apply_residual: bool = False,
    apply_bleed: bool = False,
    residuals: dict[BoundaryRole, float] | None = None,
) -> ConvexPolygon:
    """Materialize one feasible state's four boundary intersections."""

    if apply_bleed and not apply_residual:
        raise ValueError("product bleed cannot omit mandatory residual protection")
    boundaries = _canonical_boundaries(frame)
    points: list[tuple[float, float]] = []
    if apply_residual:
        if residuals is None:
            if placement.cross_fit.boundary_use == OutputBoundaryUse.APERTURE_PAIR:
                raise ValueError("aperture protection requires the complete frame reference set")
            residuals = _support_state_residuals(placement, frame, state)
        bleeds = (
            _state_bleed_px(
                placement,
                state,
                placement.cross_fit.boundary_use,
            )
            if apply_bleed
            else {role: 0.0 for role in _ROLES}
        )
        topology_protections = (
            _state_topology_protection_px(
                placement,
                frame,
                state,
            )[0]
            if apply_bleed
            else {role: 0.0 for role in _ROLES}
        )
        expansions = {
            role: (
                residuals[role]
                + bleeds[role]
                + topology_protections[role]
            )
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


def _footprint(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
    *,
    apply_residual: bool = False,
    apply_bleed: bool = False,
    protected_states: tuple[dict[BoundaryRole, float], ...] | None = None,
) -> ConvexPolygon:
    """Materialize only same-state boundary intersections."""

    if projection.placement_id != placement.placement_id:
        raise ValueError("joint projection belongs to another placement")
    states = projection.frame_states[frame.lane_ordinal - 1]
    if protected_states is not None and not apply_residual:
        raise ValueError("prepared protection requires a protected footprint")
    residuals = protected_states if protected_states is not None else (
        _frame_boundary_residuals(placement, frame, states, apply_bleed=apply_bleed)
        if apply_residual else (None,) * len(states)
    )
    return convex_hull(
        tuple(
            point
            for state, state_residuals in zip(states, residuals, strict=True)
            for point in _state_footprint(
                placement,
                frame,
                state,
                apply_residual=apply_residual,
                apply_bleed=apply_bleed,
                residuals=state_residuals,
            )
        )
    )


def _maximum_same_state_cross_alignment_padding_px(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
) -> float | None:
    """Bound added top+bottom line padding in one feasible support state."""

    if (
        placement.cross_fit.boundary_use
        != OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
    ):
        return None
    return max(
        residuals[BoundaryRole.TOP] + residuals[BoundaryRole.BOTTOM]
        for state in projection.frame_states[frame.lane_ordinal - 1]
        for residuals in (
            _support_state_residuals(placement, frame, state),
        )
    )


def _line_outward_expansion_px(
    line: SourceCoordinateLine,
    role: BoundaryRole,
    footprint: ConvexPolygon,
) -> float:
    projections = tuple(
        line.normal_x * x + line.normal_y * y for x, y in footprint
    )
    if role == BoundaryRole.TOP:
        return max(0.0, line.offset_px - min(projections))
    if role == BoundaryRole.BOTTOM:
        return max(0.0, max(projections) - line.offset_px)
    raise ValueError("aperture risk requires one cross role")


def _enclosing_support_aperture_risk(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
) -> EnclosingSupportApertureRisk | None:
    """Bound output against every authorized same-state aperture center."""

    if (
        placement.cross_fit.boundary_use
        != OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
    ):
        return None
    states = projection.frame_states[frame.lane_ordinal - 1]
    canonical_height = (
        placement.cross_fit.bottom_canonical_px
        - placement.cross_fit.top_canonical_px
    )
    authority = placement.enclosing_support_aperture_authority
    calibrated_offset = (
        authority.effective_center_offset_px
        if authority.state == EvidenceState.SUPPORTED
        else None
    )
    boundaries = _canonical_boundaries(frame)
    top_expansion = 0.0
    bottom_expansion = 0.0
    offset_minimum = math.inf
    offset_maximum = -math.inf
    for state in states:
        span = (
            state.bottom_at_lane_reference_px
            - state.top_at_lane_reference_px
        )
        if span < canonical_height - 1.0e-8:
            raise ValueError("enclosing support state does not contain H")
        slack = 0.5 * max(0.0, span - canonical_height)
        offset = calibrated_offset or FiniteInterval(-slack, slack)
        if offset.minimum < -slack - 1.0e-8 or offset.maximum > slack + 1.0e-8:
            raise ValueError(
                "calibrated aperture center leaves enclosing support state"
            )
        offset_minimum = min(offset_minimum, offset.minimum)
        offset_maximum = max(offset_maximum, offset.maximum)
        support_midpoint = 0.5 * (
            state.top_at_lane_reference_px
            + state.bottom_at_lane_reference_px
        )
        requested = _state_footprint(
            placement,
            frame,
            state,
            apply_residual=True,
            apply_bleed=True,
        )
        slope = state.enclosing_support_slope
        if slope is None:
            raise ValueError("enclosing support state lost its shared slope")
        top_line = boundary_line_at_state(
            boundaries[BoundaryRole.TOP],
            position_px=(
                support_midpoint
                + offset.maximum
                - 0.5 * canonical_height
            ),
            enclosing_support_slope=slope,
        )
        bottom_line = boundary_line_at_state(
            boundaries[BoundaryRole.BOTTOM],
            position_px=(
                support_midpoint
                + offset.minimum
                + 0.5 * canonical_height
            ),
            enclosing_support_slope=slope,
        )
        top_expansion = max(
            top_expansion,
            _line_outward_expansion_px(
                top_line,
                BoundaryRole.TOP,
                requested,
            ),
        )
        bottom_expansion = max(
            bottom_expansion,
            _line_outward_expansion_px(
                bottom_line,
                BoundaryRole.BOTTOM,
                requested,
            ),
        )
    center_offset = FiniteInterval(offset_minimum, offset_maximum)
    return EnclosingSupportApertureRisk(
        aperture_authority_id=authority.authority_id,
        aperture_authority_state=authority.state,
        canonical_height_px=canonical_height,
        center_offset_interval_px=center_offset,
        maximum_center_shift_px=max(
            abs(center_offset.minimum),
            abs(center_offset.maximum),
        ),
        top_expansion_px=top_expansion,
        bottom_expansion_px=bottom_expansion,
        feasible_state_count=len(states),
    )


def _canonical_boundaries(
    frame: TemplateFrame,
) -> dict[BoundaryRole, FrameBoundaryGeometry]:
    return {
        BoundaryRole.START: frame.start,
        BoundaryRole.END: frame.end,
        BoundaryRole.TOP: frame.top,
        BoundaryRole.BOTTOM: frame.bottom,
    }


def _support_state_residuals(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
) -> dict[BoundaryRole, float]:
    """Protect one enclosing state without counting its shared slope twice."""

    cross_span = FiniteInterval(
        frame.top.full_position_interval_px.minimum,
        frame.bottom.full_position_interval_px.maximum,
    )
    result: dict[BoundaryRole, float] = {
        BoundaryRole.START: (
            max(0.0, _sequence_line_protection(frame.start, state.sequence_start_px,
                                      cross_span, placement.sequence_fit.template.direction)[0])
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.END: (
            max(0.0, _sequence_line_protection(frame.end, state.sequence_end_px,
                                      cross_span, placement.sequence_fit.template.direction)[0])
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.TOP: (
            _support_cross_outward_departure_px(
                placement,
                frame,
                state,
                BoundaryRole.TOP,
            )
            + PIXEL_CENTER_EXTENT_PX
        ),
        BoundaryRole.BOTTOM: (
            _support_cross_outward_departure_px(
                placement,
                frame,
                state,
                BoundaryRole.BOTTOM,
            )
            + PIXEL_CENTER_EXTENT_PX
        ),
    }
    return result


def _maximum_abs_slope(direction: FiniteInterval | None) -> float:
    return 0.0 if direction is None else max(
        abs(math.tan(math.radians(angle)))
        for angle in (direction.minimum, direction.maximum)
    )


def _sequence_line_protection(
    boundary: FrameBoundaryGeometry,
    state_position: float,
    cross_span: FiniteInterval,
    direction: int,
    reachable_positions: FiniteInterval | None = None,
) -> tuple[float, float]:
    positions, slope = _sequence_line_extent(boundary, cross_span, reachable_positions)
    if positions is None:
        return 0.0, 0.0
    return _sequence_outward_departure(boundary.role, positions, state_position, direction), slope


def _sequence_outward_departure(
    role: BoundaryRole,
    positions: FiniteInterval,
    state_position: float,
    direction: int,
) -> float:
    outward_positive = (role == BoundaryRole.END) == (direction > 0)
    return (
        positions.maximum - state_position if outward_positive
        else state_position - positions.minimum
    )


def _sequence_line_extent(
    boundary: FrameBoundaryGeometry,
    cross_span: FiniteInterval,
    reachable_positions: FiniteInterval | None,
) -> tuple[FiniteInterval | None, float]:
    """Prepare one frame's correlated line-family bounds once for all states."""
    evidence = boundary.line_evidence
    if evidence is None:
        return None, 0.0
    fit = evidence.fit_position_interval_px
    fit_minimum = max(fit.minimum, reachable_positions.minimum) if reachable_positions else fit.minimum
    fit_maximum = min(fit.maximum, reachable_positions.maximum) if reachable_positions else fit.maximum
    positions = [
        position - math.tan(math.radians(angle)) * (trace - evidence.reference_trace_px)
        for position in ((fit_minimum, fit_maximum) if fit_minimum <= fit_maximum else ())
        for angle in (evidence.fit_direction_interval_degrees.minimum, evidence.fit_direction_interval_degrees.maximum)
        for trace in (cross_span.minimum, cross_span.maximum)
    ]
    slope = _maximum_abs_slope(evidence.fit_direction_interval_degrees) if positions else 0.0
    region = evidence.physical_line_region
    offset = evidence.physical_position_offset_px
    if region is not None and reachable_positions is not None:
        region = physical_line_region_at_positions(region, offset, reachable_positions)
        if region is None:
            raise ValueError("sequence physical line contradicts native reachable positions")
        offset = FiniteInterval.exact(0.0)
    if region is not None:
        for trace in (cross_span.minimum, cross_span.maximum):
            interval = region.project(trace)
            positions.extend((
                interval.minimum + offset.minimum,
                interval.maximum + offset.maximum,
            ))
        slope = max(slope, *(abs(value) for _, value in region.vertices))
    if not positions:
        return None, 0.0
    return FiniteInterval(min(positions), max(positions)), slope


def _cross_binding_for_role(
    placement: FormatPlacement, role: BoundaryRole,
) -> CrossRoleBinding:
    cross = placement.cross_fit
    direct = {item.role: item for item in cross.direct_bindings}
    if role in direct:
        return direct[role]
    inferred = next((item for item in cross.inferred_bindings if item.role == role), None)
    sources = () if inferred is None else tuple(
        item for item in cross.direct_bindings
        if item.observation_id in inferred.source_observation_ids
    )
    if len(sources) != 1:
        raise ValueError("inferred aperture role lacks one direct source")
    return sources[0]


def _frame_boundary_residuals(
    placement: FormatPlacement,
    frame: TemplateFrame,
    states: tuple[JointFrameState, ...],
    *,
    apply_bleed: bool,
) -> tuple[dict[BoundaryRole, float], ...]:
    """Close an aperture's protective spans without another geometry solver.

    The line-family support is Lipschitz in the other axis's expansion.
    Solve that two-variable outer bound analytically. Raw trace admission is
    shared by all reference states, including their convex interior. Every
    further pass must admit a new registered endpoint; no numerical fixed-point
    iteration or pixel query is involved.
    """
    if placement.cross_fit.boundary_use != OutputBoundaryUse.APERTURE_PAIR:
        return tuple(_support_state_residuals(placement, frame, state) for state in states)
    cross = placement.cross_fit
    direction = placement.sequence_fit.template.direction
    sequence_span = FiniteInterval(
        min(frame.start.full_position_interval_px.minimum, frame.end.full_position_interval_px.minimum),
        max(frame.start.full_position_interval_px.maximum, frame.end.full_position_interval_px.maximum),
    )
    cross_span = FiniteInterval(frame.top.full_position_interval_px.minimum,
                              frame.bottom.full_position_interval_px.maximum)
    reachable_positions = {
        BoundaryRole.START: FiniteInterval(min(state.sequence_start_px for state in states),
                                          max(state.sequence_start_px for state in states)),
        BoundaryRole.END: FiniteInterval(min(state.sequence_end_px for state in states),
                                        max(state.sequence_end_px for state in states)),
    }
    bindings = {role: _cross_binding_for_role(placement, role)
                for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM)}
    statistical = cross.line_projection_basis == CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT
    cross_slopes = {role: _maximum_abs_slope(
        binding.fit_direction_interval_degrees if statistical else binding.full_direction_interval_degrees
    ) for role, binding in bindings.items()}
    orientation_slope = (
        max((_maximum_abs_slope(binding.fit_direction_interval_degrees)
             for binding in cross.direct_bindings), default=0.0)
        if cross.direct_pair and len(cross.direct_bindings) == 2 else 0.0
    )
    sequence_extents = {
        boundary.role: _sequence_line_extent(
            boundary, cross_span, reachable_positions[boundary.role],
        )
        for boundary in (frame.start, frame.end)
    }
    cross_positions = {
        role: _aperture_binding_positions(
            binding, lane_reference_trace_px=cross.lane_reference_trace_px,
            support=sequence_span, line_projection_basis=cross.line_projection_basis,
        )
        for role, binding in bindings.items()
    }
    bases: list[dict[BoundaryRole, float]] = []
    departures: list[dict[BoundaryRole, float]] = []
    slopes: list[dict[BoundaryRole, float]] = []
    optional: list[dict[BoundaryRole, float]] = []
    source_positions: list[dict[BoundaryRole, float]] = []
    for state in states:
        extras = {role: 0.0 for role in _ROLES}
        if apply_bleed:
            bleed = _state_bleed_px(placement, state, cross.boundary_use)
            topology = _state_topology_protection_px(placement, frame, state)[0]
            extras = {role: bleed[role] + topology[role] for role in _ROLES}
        base = {role: PIXEL_CENTER_EXTENT_PX + extras[role] for role in _ROLES}
        signed_departures = {role: 0.0 for role in _ROLES}
        state_slopes = dict(cross_slopes)
        for boundary, position in ((frame.start, state.sequence_start_px), (frame.end, state.sequence_end_px)):
            extent, slope = sequence_extents[boundary.role]
            departure = (
                0.0 if extent is None else _sequence_outward_departure(
                    boundary.role, extent, position, direction,
                )
            )
            if orientation_slope > 0.0:
                departure = max(departure, orientation_slope * cross_span.width / 2.0)
            signed_departures[boundary.role] = departure
            base[boundary.role] += max(0.0, departure)
            state_slopes[boundary.role] = max(slope, orientation_slope)
        sources = {}
        for role, binding in bindings.items():
            source_position = (state.top_at_lane_reference_px if binding.role == BoundaryRole.TOP
                               else state.bottom_at_lane_reference_px)
            sources[role] = source_position
            positions = cross_positions[role]
            if positions:
                departure = (source_position - min(positions) if role == BoundaryRole.TOP
                             else max(positions) - source_position)
                signed_departures[role] = departure
                base[role] += max(0.0, departure)
        bases.append(base)
        departures.append(signed_departures)
        slopes.append(state_slopes)
        optional.append(extras)
        source_positions.append(sources)

    # One shared trace ledger is essential: an interior reference frame can
    # cover a trace that neither of the two extreme reference frames covers.
    admitted = {role: {i for i, trace in enumerate(binding.trace_coordinates_px)
                       if sequence_span.contains(float(trace))}
                for role, binding in bindings.items()}
    endpoint_count = sum(len(binding.trace_position_intervals_px) for binding in bindings.values())
    for _ in range(endpoint_count + 1):
        expansions = []
        for base, slope, signed, extras in zip(bases, slopes, departures, optional, strict=True):
            rx = max(base[BoundaryRole.START], base[BoundaryRole.END])
            ry = max(base[BoundaryRole.TOP], base[BoundaryRole.BOTTOM])
            m = max(slope[BoundaryRole.START], slope[BoundaryRole.END])
            n = max(slope[BoundaryRole.TOP], slope[BoundaryRole.BOTTOM])
            denominator = 1.0 - m * n
            if denominator <= 0.0:
                raise ValueError("aperture protection has no bounded two-axis closure")
            dx = (rx + m * ry) / denominator
            dy = (ry + n * rx) / denominator
            expansions.append({role: PIXEL_CENTER_EXTENT_PX + extras[role] + max(
                0.0, signed[role] + slope[role] * (
                    dy if role in {BoundaryRole.START, BoundaryRole.END} else dx
                ),
            ) for role in _ROLES})
        endpoints = tuple(
            value for state, expansion in zip(states, expansions, strict=True)
            for value in (state.sequence_start_px - direction * expansion[BoundaryRole.START],
                          state.sequence_end_px + direction * expansion[BoundaryRole.END])
        )
        expanded_span = FiniteInterval(min(sequence_span.minimum, min(endpoints)),
                                       max(sequence_span.maximum, max(endpoints)))
        added = False
        for role, binding in bindings.items():
            traces = binding.trace_coordinates_px if binding.trace_position_intervals_px else ()
            for index, (trace, interval) in enumerate(zip(traces, binding.trace_position_intervals_px, strict=True)):
                if index in admitted[role] or not expanded_span.contains(float(trace)):
                    continue
                admitted[role].add(index)
                added = True
                for base, signed, extras, sources in zip(bases, departures, optional, source_positions, strict=True):
                    departure = (sources[role] - interval.minimum if role == BoundaryRole.TOP
                                 else interval.maximum - sources[role])
                    signed[role] = max(signed[role], departure)
                    base[role] = PIXEL_CENTER_EXTENT_PX + extras[role] + max(0.0, signed[role])
        if not added:
            return tuple({role: expansion[role] - extras[role] for role in _ROLES}
                         for expansion, extras in zip(expansions, optional, strict=True))
    raise ValueError("aperture protection exceeded its registered endpoint bound")


def _support_cross_outward_departure_px(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
    role: BoundaryRole,
) -> float:
    """Retain measured support residuals relative to its same-state slope."""

    binding = next(item for item in placement.cross_fit.direct_bindings if item.role == role)

    state_source_position = (
        state.top_at_lane_reference_px
        if role == BoundaryRole.TOP
        else state.bottom_at_lane_reference_px
    )
    support = (
        frame.top.line.support_projection_px
        if role == BoundaryRole.TOP
        else frame.bottom.line.support_projection_px
    )
    target_trace_px = (
        frame.top.reference_trace_px
        if role == BoundaryRole.TOP
        else frame.bottom.reference_trace_px
    )
    state_slope = state.enclosing_support_slope
    if state_slope is None:
        raise ValueError("enclosing support state lost its shared slope")
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
        state_position_at_trace = state_source_position + state_slope * (
            trace_px - target_trace_px
        )
        departure = (
            state_position_at_trace - interval.minimum
            if role == BoundaryRole.TOP
            else interval.maximum - state_position_at_trace
        )
        raw_departure = max(raw_departure, departure)
        covered_traces.append(trace_px)

    direction_uncertainty = binding.observed_direction_interval_degrees
    if direction_uncertainty is None:
        return max(0.0, raw_departure)
    if binding.trace_coordinates_px:
        lower = float(binding.trace_coordinates_px[0])
        upper = float(binding.trace_coordinates_px[-1])
        extrapolation_deltas = tuple(
            endpoint - min(max(endpoint, lower), upper)
            for endpoint in (support.minimum, support.maximum)
        )
    elif covered_traces:
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
    # The selected support line already carries one feasible shared slope.
    # Only the observed direction's departure from that same state remains as
    # extrapolation protection.  Adding the absolute slope here would count it
    # once in the joint footprint and again as a local residual.
    shifts = tuple(
        (math.tan(math.radians(angle)) - state_slope) * delta
        for angle in (
            direction_uncertainty.minimum,
            direction_uncertainty.maximum,
        )
        for delta in extrapolation_deltas
    )
    direction_departure = (
        max(0.0, -min(shifts, default=0.0))
        if role == BoundaryRole.TOP
        else max(0.0, max(shifts, default=0.0))
    )
    return max(0.0, raw_departure + direction_departure)


def _aperture_binding_positions(
    binding: CrossRoleBinding,
    *,
    lane_reference_trace_px: float,
    support: FiniteInterval,
    line_projection_basis: CrossLineProjectionBasis,
) -> tuple[float, ...]:
    """Project one direct aperture edge with its explicit typed basis."""

    positions: list[float] = []
    if not isinstance(line_projection_basis, CrossLineProjectionBasis):
        raise TypeError("aperture line projection basis must be typed")
    use_statistical_fit = (
        line_projection_basis
        == CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT
    )
    direction = (
        binding.fit_direction_interval_degrees
        if use_statistical_fit
        else binding.full_direction_interval_degrees
    )
    if direction is not None:
        positions.extend(
            value
            + math.tan(math.radians(angle))
            * (trace - lane_reference_trace_px)
            for value in (
                binding.full_interval_px.minimum,
                binding.full_interval_px.maximum,
            )
            for angle in (direction.minimum, direction.maximum)
            for trace in (support.minimum, support.maximum)
        )
    if binding.trace_position_intervals_px:
        positions.extend(
            value
            for trace, interval in zip(
                binding.trace_coordinates_px,
                binding.trace_position_intervals_px,
                strict=True,
            )
            if support.contains(float(trace))
            for value in (interval.minimum, interval.maximum)
        )
    return tuple(positions)


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


def _topology_relations_by_role(
    placement: FormatPlacement,
    frame: TemplateFrame,
) -> dict[BoundaryRole, ContactRelation | OverlapRelation]:
    """Map only boundaries owned by proven contact or overlap topology."""

    values: dict[BoundaryRole, ContactRelation | OverlapRelation] = {}
    for relation in placement.sequence_fit.adjacency_relations:
        if not isinstance(relation, (ContactRelation, OverlapRelation)):
            continue
        role = (
            BoundaryRole.END
            if frame.lane_ordinal == relation.relation_ordinal
            else BoundaryRole.START
            if frame.lane_ordinal == relation.relation_ordinal + 1
            else None
        )
        if role is None:
            continue
        if role in values:
            raise ValueError(
                "one output boundary cannot belong to multiple topologies"
            )
        values[role] = relation
    return values


def _state_topology_protection_px(
    placement: FormatPlacement,
    frame: TemplateFrame,
    state: JointFrameState,
) -> tuple[
    dict[BoundaryRole, float],
    dict[BoundaryRole, ObservationId | None],
]:
    """Use one extra base bleed only on proven contact/overlap sides."""

    sequence_scale = (
        abs(state.sequence_end_px - state.sequence_start_px)
        / placement.frame_spec.frame_width_mm
    )
    sequence = OUTPUT_PROTECTION_SPEC.sequence_bleed_mm(
        placement.frame_spec.frame_width_mm
    ) * sequence_scale
    relations = _topology_relations_by_role(placement, frame)
    protections = {role: 0.0 for role in _ROLES}
    relation_ids: dict[BoundaryRole, ObservationId | None] = {
        role: None for role in _ROLES
    }
    for role, relation in relations.items():
        protections[role] = sequence
        relation_ids[role] = (
            relation.contact_observation_id
            if isinstance(relation, ContactRelation)
            else relation.overlap_observation_id
        )
    return protections, relation_ids


def _maximum_state_components(
    placement: FormatPlacement,
    frame: TemplateFrame,
    projection: FeasiblePlacementProjection,
    protected: tuple[dict[BoundaryRole, float], ...],
) -> tuple[
    dict[BoundaryRole, float],
    dict[BoundaryRole, float],
    dict[BoundaryRole, float],
    dict[BoundaryRole, ObservationId | None],
]:
    residuals = {role: 0.0 for role in _ROLES}
    bleeds = {role: 0.0 for role in _ROLES}
    topology_protections = {role: 0.0 for role in _ROLES}
    topology_relation_ids: dict[BoundaryRole, ObservationId | None] = {
        role: None for role in _ROLES
    }
    states = projection.frame_states[frame.lane_ordinal - 1]
    for state, state_residuals in zip(states, protected, strict=True):
        state_bleeds = _state_bleed_px(
            placement,
            state,
            placement.cross_fit.boundary_use,
        )
        state_topology, state_relation_ids = _state_topology_protection_px(
            placement,
            frame,
            state,
        )
        for role in _ROLES:
            residuals[role] = max(residuals[role], state_residuals[role])
            bleeds[role] = max(bleeds[role], state_bleeds[role])
            topology_protections[role] = max(
                topology_protections[role],
                state_topology[role],
            )
            relation_id = state_relation_ids[role]
            if (
                relation_id is not None
                and topology_relation_ids[role] not in {None, relation_id}
            ):
                raise ValueError(
                    "one output boundary cannot change topology relation"
                )
            if relation_id is not None:
                topology_relation_ids[role] = relation_id
    return (
        residuals,
        bleeds,
        topology_protections,
        topology_relation_ids,
    )


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
        sequence_constraint_basis=projection.sequence_constraint_basis,
        global_lattice_constraint_ids=(
            projection.global_lattice_constraint_ids
        ),
    )


def _saturation_facts(
    requested: ConvexPolygon,
    mandatory: ConvexPolygon,
    authority: Box,
    source: WorkspaceExtent,
) -> tuple[FootprintSaturationFact, ...]:
    source_sides = source_boundary_sides(authority, source)
    return tuple(
        FootprintSaturationFact(
            authority_side=side,
            kind=(
                FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION
                if side in source_sides
                and footprint_overflow_px(mandatory, authority, side, source) > 0.0
                else FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED
                if side in source_sides
                else FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION
                if footprint_overflow_px(mandatory, authority, side, source) > 0.0
                else FootprintSaturationKind.LANE_BOUNDARY_OPTIONAL_BLEED
            ),
            requested_overflow_px=footprint_overflow_px(
                requested,
                authority,
                side,
                source,
            ),
            mandatory_overflow_px=footprint_overflow_px(
                mandatory,
                authority,
                side,
                source,
            ),
        )
        for side in footprint_outside_authority_sides(requested, authority, source)
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


def _source_canvas_extent(
    lane: SourceLaneEvidence,
    layout: str,
) -> WorkspaceExtent:
    long_axis = lane.scan_canvas.observed_long_axis_px
    short_axis = lane.scan_canvas.observed_short_axis_px
    if layout == "horizontal":
        return WorkspaceExtent(long_axis, short_axis)
    if layout == "vertical":
        return WorkspaceExtent(short_axis, long_axis)
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
    requested_protection = _frame_boundary_residuals(
        placement, frame, projection.frame_states[lane_ordinal - 1], apply_bleed=True,
    )
    (
        local_residuals,
        bleed_by_role,
        topology_protection_by_role,
        topology_relation_by_role,
    ) = _maximum_state_components(
        placement,
        frame,
        projection,
        requested_protection,
    )
    mandatory = _footprint(
        placement,
        frame,
        projection,
        apply_residual=True,
    )
    requested = _footprint(
        placement,
        frame,
        projection,
        apply_residual=True,
        apply_bleed=True,
        protected_states=requested_protection,
    )
    authority = _source_lane_authority(lane, layout)
    source_extent = _source_canvas_extent(lane, layout)
    authority_bounds = sampling_authority_bounds(authority, source_extent)
    saturation = _saturation_facts(
        requested,
        mandatory,
        authority,
        source_extent,
    )
    source_boundary_only = all(fact.source_boundary for fact in saturation)
    required = (
        clip_convex_polygon_to_bounds(requested, authority_bounds)
        if saturation and source_boundary_only
        else requested
    )
    boundaries = _canonical_boundaries(frame)
    protections = tuple(
        BoundaryProtectionFact(
            role=role,
            measurement_expansion_px=_expansion_px(
                boundaries[role],
                parameter_footprint,
            ),
            base_bleed_px=bleed_by_role[role],
            topology_protection_px=topology_protection_by_role[role],
            topology_relation_id=topology_relation_by_role[role],
            local_boundary_residual_px=local_residuals[role],
            joint_expansion_px=_expansion_px(boundaries[role], requested),
        )
        for role in _ROLES
    )
    maximum_same_state_cross_alignment_padding_px = (
        _maximum_same_state_cross_alignment_padding_px(
            placement,
            frame,
            projection,
        )
    )
    enclosing_support_aperture_risk = _enclosing_support_aperture_risk(
        placement,
        frame,
        projection,
    )
    return OutputFootprint(
        geometry_id=run_local_id(
            "template-output-footprint",
            placement.placement_id,
            lane_ordinal,
        ),
        envelope=envelope,
        mandatory_source_footprint=mandatory,
        requested_source_footprint=requested,
        required_source_footprint=required,
        boundary_protections=protections,
        maximum_same_state_cross_alignment_padding_px=(
            maximum_same_state_cross_alignment_padding_px
        ),
        enclosing_support_aperture_risk=(
            enclosing_support_aperture_risk
        ),
        saturation_facts=saturation,
        sampling_authority_box=authority,
        source_extent=source_extent,
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
    support_risk = output.enclosing_support_aperture_risk
    if support_output != (support_risk is not None):
        raise ValueError("output lost its enclosing-aperture risk")
    expansion_px = {
        role: (
            support_risk.top_expansion_px
            if support_risk is not None and role == BoundaryRole.TOP
            else support_risk.bottom_expansion_px
            if support_risk is not None and role == BoundaryRole.BOTTOM
            else protections[role].joint_expansion_px
        )
        for role in _ROLES
    }
    expansion_mm = {
        role: states[role].worst_case_mm(
            expansion_px[role]
        )
        for role in _ROLES
    }
    maximum_same_state_cross_alignment_padding_mm = (
        height_state.worst_case_mm(
            float(output.maximum_same_state_cross_alignment_padding_px)
        )
        if support_output
        else None
    )
    edge_assessments = tuple(
        DirectUseBudgetEdgeAssessment(
            role=role,
            expansion_px=expansion_px[role],
            expansion_mm=expansion_mm[role],
            limit_mm=limit_mm[role],
            limit_applies=True,
            within_limit=expansion_mm[role] <= limit_mm[role],
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
    maximum_same_state_cross_alignment_padding_within_limit = (
        None
        if maximum_same_state_cross_alignment_padding_mm is None
        else maximum_same_state_cross_alignment_padding_mm
        <= limit_mm[BoundaryRole.TOP]
    )
    supported = (
        all(item.within_limit for item in edge_assessments)
        and support_within_limit is not False
        and maximum_same_state_cross_alignment_padding_within_limit is not False
    )
    return DirectUseBudgetAssessment(
        geometry_id=output.geometry_id,
        boundary_use=output.envelope.boundary_use,
        edge_assessments=edge_assessments,
        enclosing_support_height_ratio=support_ratio,
        enclosing_support_within_limit=support_within_limit,
        maximum_same_state_cross_alignment_padding_mm=(
            maximum_same_state_cross_alignment_padding_mm
        ),
        maximum_same_state_cross_alignment_padding_within_limit=(
            maximum_same_state_cross_alignment_padding_within_limit
        ),
        state=(
            EvidenceState.SUPPORTED
            if supported
            else EvidenceState.CONTRADICTED
        ),
    )
