from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256
import math

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import FRAME_DIMENSION_TOLERANCE_SPEC, FramePhysicalSpec
from ..output_geometry import (
    observed_strip_angle_estimate_degrees,
    resolve_shared_strip_direction,
)
from .boundary_geometry import (
    canonical_boundary_line,
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
    source_cross_axis_slope_interval,
    source_sequence_axis_slope_interval,
)
from .bounds import MAX_COMPLETE_CHAINS_PER_LANE
from .measurement import (
    continuous_trace_support_fraction,
    fit_template_bound_boundary_observation,
    robust_scalar_location,
    track_side_transition_regions,
)
from .model import (
    BoundaryAxis,
    BoundaryRole,
    DirectionAuthority,
    FrameBoundaryGeometry,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    PositionSource,
    SharedStripDirection,
)
from .source_geometry import (
    JointAxisGeometry,
    LaneGapModel,
    SourceFrameGeometry,
)
from .template_model import (
    BoundRoleEvidence,
    CanonicalFormatPlacement,
    ComponentTemplateProposal,
    CrossPlacement,
    CrossRoleEvidence,
    EnhancedPhaseQuery,
    EnhancedQueryRegistry,
    FormatPlacement,
    FrameFormatPlacement,
    LocalAdvanceKind,
    LocalAdvanceRelation,
    ProvisionalHeightTemplate,
    RegisteredSequenceRoleQuery,
    SequencePlacement,
    SourcePlacementMaterialization,
    TemplateLaneInput,
    TemplateLaneProposal,
    TemplateSequenceSeed,
)
from .template_profiles import (
    BasicAxisProfile,
    PhaseVote,
    ProfileRun,
    TemplatePhaseGroup,
    TemplateRole,
    build_phase_groups,
    cross_profile_from_regions,
    group_support_exclusion_authorized,
    ordered_template_roles,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _gap_seed_mm(component: FramePhysicalSpec) -> float:
    """Return a search origin, never a source-gap authority."""

    return (
        component.format_gap_prior_mm
        if component.format_gap_prior_mm is not None
        else 0.0
    )


def _gap_observation_domain_mm(component: FramePhysicalSpec) -> FiniteInterval:
    if component.format_gap_prior_mm is None:
        return FiniteInterval(-component.frame_width_mm, component.frame_width_mm)
    prior = component.format_gap_prior_mm
    return FiniteInterval(max(-component.frame_width_mm, prior - 2.0), prior + 2.0)


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
    *,
    epsilon: float = 0.0,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        if minimum - maximum > epsilon:
            return None
        return FiniteInterval.exact((minimum + maximum) / 2.0)
    return FiniteInterval(minimum, maximum)


def _hull(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    if not values:
        raise ValueError("interval hull requires values")
    return FiniteInterval(
        min(value.minimum for value in values),
        max(value.maximum for value in values),
    )


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def _subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


def _conditional_fit_and_full(
    fit_values: tuple[FiniteInterval, ...],
    full_values: tuple[FiniteInterval, ...],
) -> tuple[FiniteInterval, FiniteInterval] | None:
    """Keep the robust center as preference inside the full safety domain."""

    full = _common(full_values)
    if full is None:
        return None
    fit = _common(fit_values)
    if fit is not None:
        fit = _intersection(fit, full)
    return (full if fit is None else fit), full


def direction_class_key(direction: SharedStripDirection) -> tuple[object, ...]:
    return (
        round(direction.canonical_angle_degrees, 12),
        round(direction.full_angle_interval_degrees.minimum, 12),
        round(direction.full_angle_interval_degrees.maximum, 12),
        tuple(map(str, direction.selected_observation_ids)),
    )


def merge_sampling_equivalent_direction_classes(
    directions: tuple[SharedStripDirection, ...],
) -> tuple[SharedStripDirection, ...]:
    """Merge only direction classes that produce the exact same transform.

    The interval hull preserves every template-bound direction interpretation;
    ordinary support or residual scores never collapse a distinct transform.
    """

    grouped: dict[float, list[SharedStripDirection]] = {}
    for direction in directions:
        grouped.setdefault(direction.canonical_angle_degrees, []).append(direction)
    merged: list[SharedStripDirection] = []
    for canonical_angle, members in grouped.items():
        observation_ids = tuple(
            sorted(
                {
                    observation_id
                    for member in members
                    for observation_id in member.selected_observation_ids
                },
                key=str,
            )
        )
        full_angle_interval = FiniteInterval(
            min(
                member.full_angle_interval_degrees.minimum
                for member in members
            ),
            max(
                member.full_angle_interval_degrees.maximum
                for member in members
            ),
        )
        merged.append(
            SharedStripDirection(
                direction_id=_stable_id(
                    "template-direction-class",
                    canonical_angle,
                    full_angle_interval.minimum,
                    full_angle_interval.maximum,
                    *(str(identity) for identity in observation_ids),
                ),
                selected_observation_ids=observation_ids,
                full_angle_interval_degrees=full_angle_interval,
                canonical_angle_degrees=canonical_angle,
            )
        )
    return tuple(sorted(merged, key=direction_class_key))


def _template_bound_direction_classes(
    templates: tuple[ProvisionalHeightTemplate, ...],
) -> tuple[SharedStripDirection, ...]:
    directions: list[SharedStripDirection] = []
    for template in templates:
        fit_intervals = tuple(
            item.fit_angle_interval_degrees
            for item in template.raw_observations
            if item.fit_angle_interval_degrees is not None
        )
        if len(fit_intervals) != len(template.raw_observations):
            raise ValueError("template direction lacks fit intervals")
        resolution = resolve_shared_strip_direction(template.raw_observations)
        if resolution.direction is not None:
            hull = _hull(
                tuple(
                    item.angle_interval_degrees
                    for item in template.raw_observations
                )
            )
            if _hull(fit_intervals).width > (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
            ):
                continue
            directions.append(
                SharedStripDirection(
                    direction_id=_stable_id(
                        "template-direction-safety-hull",
                        resolution.direction.direction_id,
                        hull.minimum,
                        hull.maximum,
                    ),
                    selected_observation_ids=(
                        resolution.direction.selected_observation_ids
                    ),
                    full_angle_interval_degrees=hull,
                    canonical_angle_degrees=(
                        resolution.direction.canonical_angle_degrees
                    ),
                )
            )
            continue
        full_intervals = tuple(
            item.angle_interval_degrees
            for item in template.raw_observations
        )
        if len(fit_intervals) < 2:
            continue
        fit_hull = _hull(fit_intervals)
        if fit_hull.width > (
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
        ):
            continue
        hull = _hull(full_intervals)
        canonical = observed_strip_angle_estimate_degrees(
            template.raw_observations
        )
        canonical = min(
            fit_hull.maximum,
            max(fit_hull.minimum, canonical),
        )
        identities = tuple(
            sorted(
                (
                    item.observation_id
                    for item in template.raw_observations
                ),
                key=str,
            )
        )
        directions.append(
            SharedStripDirection(
                direction_id=_stable_id(
                    "bounded-template-direction",
                    hull.minimum,
                    hull.maximum,
                    canonical,
                    *(str(identity) for identity in identities),
                ),
                selected_observation_ids=identities,
                full_angle_interval_degrees=hull,
                canonical_angle_degrees=canonical,
            )
        )
    return merge_sampling_equivalent_direction_classes(tuple(directions))


def _role_relative_projection(
    role: TemplateRole,
    component: FramePhysicalSpec,
    width_state: JointAxisGeometry,
) -> FiniteInterval:
    index = role.lane_ordinal - 1
    width_count = index + (1 if role.role == BoundaryRole.END else 0)
    return width_state.project_affine(
        q_coefficient=width_count * component.frame_width_mm,
        scale_coefficient=index * _gap_seed_mm(component),
    )


def _role_canonical_relative(
    role: TemplateRole,
    component: FramePhysicalSpec,
    width_state: JointAxisGeometry,
) -> float:
    scale, normalized, _factor = width_state.canonical_state()
    index = role.lane_ordinal - 1
    return (
        (index + (1 if role.role == BoundaryRole.END else 0))
        * component.frame_width_mm
        * normalized
        + index * _gap_seed_mm(component) * scale
    )


def _role_affine_coefficients(
    role: TemplateRole,
    component: FramePhysicalSpec,
) -> tuple[float, float]:
    index = role.lane_ordinal - 1
    return (
        (
            index
            + (1 if role.role == BoundaryRole.END else 0)
        )
        * component.frame_width_mm,
        index * _gap_seed_mm(component),
    )


def _sequence_phase_votes(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    roles: tuple[TemplateRole, ...],
) -> tuple[PhaseVote, ...]:
    runs = {run.run_id: run for run in lane.sequence_profile.runs}
    values: list[PhaseVote] = []
    for region in lane.sequence_profile.runs:
        run = runs[region.run_id]
        for role in roles:
            if not run.anchor_qualified_for(role.role):
                continue
            relative = _role_relative_projection(
                role,
                geometry.component,
                geometry.width_state,
            )
            values.append(
                PhaseVote(
                    vote_id=_stable_id(
                        "phase-vote",
                        geometry.component.component_id,
                        run.run_id,
                        role.role_index,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=_subtract(
                        run.coordinate_interval_px,
                        relative,
                    ),
                    transition_ids=run.transition_ids,
                    template_coordinate_px=_role_canonical_relative(
                        role,
                        geometry.component,
                        geometry.width_state,
                    ),
                )
            )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.vote_id))
    )


def _line_boundary_coordinate(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> float:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        if abs(line.normal_y) <= 1.0e-12:
            raise ValueError("cross-boundary line cannot project y")
        return (
            line.offset_px - line.normal_x * trace_coordinate_px
        ) / line.normal_y
    if abs(line.normal_x) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project x")
    return (
        line.offset_px - line.normal_y * trace_coordinate_px
    ) / line.normal_x


def reference_role_transition_ids(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    target_coordinate_px: float,
    equivalence_px: float,
) -> tuple[ObservationId, ...]:
    """Bind one unambiguous measured transition per registered trace.

    The physical template reference proposes where to look inside the already
    completed query.  It does not create evidence: a trace is omitted whenever
    its two nearest transitions are indistinguishable at the frozen geometry
    equivalence scale.
    """

    if not math.isfinite(target_coordinate_px) or equivalence_px <= 0.0:
        raise ValueError("reference transition proposal is invalid")
    by_trace: dict[int, list[PhotoBoundaryTransition]] = {}
    for transition in measurement_set.transitions:
        by_trace.setdefault(transition.trace_coordinate_px, []).append(
            transition
        )
    selected: list[ObservationId] = []
    for trace in measurement_set.query.trace_positions_px:
        ordered = sorted(
            by_trace.get(trace, ()),
            key=lambda item: (
                abs(item.coordinate_px - target_coordinate_px),
                str(item.transition_id),
            ),
        )
        if not ordered:
            continue
        if (
            len(ordered) > 1
            and abs(
                abs(ordered[1].coordinate_px - target_coordinate_px)
                - abs(ordered[0].coordinate_px - target_coordinate_px)
            )
            <= equivalence_px
        ):
            continue
        selected.append(ordered[0].transition_id)
    return tuple(selected)


def _observation_coordinate_interval(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> FiniteInterval:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        normal = line.normal_y
        other = line.normal_x
    else:
        normal = line.normal_x
        other = line.normal_y
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project coordinate")
    values = tuple(
        (offset - other * trace_coordinate_px) / normal
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def _reference_role_run(
    lane: TemplateLaneInput,
    *,
    role: BoundaryRole,
    measurement_set: PhotoBoundaryMeasurementSet,
    target_coordinate_px: float,
    equivalence_px: float,
    support_interval_px: FiniteInterval | None = None,
) -> tuple[ProfileRun, PhotoBoundaryObservation] | None:
    transition_ids = reference_role_transition_ids(
        measurement_set,
        target_coordinate_px=target_coordinate_px,
        equivalence_px=equivalence_px,
    )
    observation = fit_template_bound_boundary_observation(
        measurement_set,
        transition_ids=transition_ids,
        role=role,
        source_axis_long=lane.width_axis,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        minimum_trace_fraction=(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
        ),
        support_interval_px=support_interval_px,
    )
    if observation is None:
        return None
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    role_preference = (
        observation.left_background_preference_fraction
        if role == BoundaryRole.TOP
        else observation.right_background_preference_fraction
    )
    if (
        observation.background_side_support_fraction
        < spec.directional_background_support_minimum
        or role_preference < spec.directional_role_preference_minimum
    ):
        return None
    selected = tuple(
        transition
        for transition in measurement_set.transitions
        if transition.transition_id in set(observation.transition_ids)
    )
    traces = tuple(
        sorted({transition.trace_coordinate_px for transition in selected})
    )
    queried = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    return (
        ProfileRun(
            run_id=_stable_id(
                "reference-role-run",
                role.value,
                *(str(identity) for identity in observation.transition_ids),
            ),
            coordinate_interval_px=_observation_coordinate_interval(
                observation,
                boundary_axis=lane.height_axis,
                trace_coordinate_px=lane.width_authority_px.center,
            ),
            transition_ids=observation.transition_ids,
            trace_coordinates_px=traces,
            role_hint=role,
            qualified_anchor_roles=(),
            support_fraction=len(traces) / len(queried),
            continuous_support_fraction=(
                observation.continuous_support_fraction
            ),
            fit_residual_px=observation.fit_residual_px,
            evidence_strength=sum(
                transition.gradient_z
                + max(transition.tone_z, transition.texture_z)
                for transition in selected
            )
            / len(selected),
            pair_qualified=True,
        ),
        observation,
    )


def _inlier_profile_run(
    lane: TemplateLaneInput,
    run: ProfileRun,
    observation: PhotoBoundaryObservation,
    measurement_set: PhotoBoundaryMeasurementSet,
    support_interval_px: FiniteInterval | None = None,
) -> ProfileRun:
    selected = tuple(
        transition
        for transition in measurement_set.transitions
        if transition.transition_id in set(observation.transition_ids)
    )
    traces = tuple(
        sorted({transition.trace_coordinate_px for transition in selected})
    )
    queried = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    return ProfileRun(
        run_id=_stable_id(
            "inlier-profile-run",
            run.run_id,
            observation.observation_id,
        ),
        coordinate_interval_px=_observation_coordinate_interval(
            observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=lane.width_authority_px.center,
        ),
        transition_ids=observation.transition_ids,
        trace_coordinates_px=traces,
        role_hint=run.role_hint,
        qualified_anchor_roles=run.qualified_anchor_roles,
        support_fraction=(
            observation.trace_support_count / len(queried)
        ),
        continuous_support_fraction=(
            observation.continuous_support_fraction
        ),
        fit_residual_px=observation.fit_residual_px,
        evidence_strength=sum(
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z)
            for transition in selected
        )
        / len(selected),
        pair_qualified=run.pair_qualified,
    )


def _reference_pair_height_template(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    broad_height: FiniteInterval,
    *,
    support_interval_px: FiniteInterval | None = None,
) -> ProvisionalHeightTemplate | None:
    height = geometry.height_state.extent_projection_px()
    center = lane.height_authority_px.center
    equivalence_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
        * lane.height_scale_px_per_mm.maximum
    )
    top = _reference_role_run(
        lane,
        role=BoundaryRole.TOP,
        measurement_set=lane.top_measurement_set,
        target_coordinate_px=center - height.center / 2.0,
        equivalence_px=equivalence_px,
        support_interval_px=support_interval_px,
    )
    bottom = _reference_role_run(
        lane,
        role=BoundaryRole.BOTTOM,
        measurement_set=lane.bottom_measurement_set,
        target_coordinate_px=center + height.center / 2.0,
        equivalence_px=equivalence_px,
        support_interval_px=support_interval_px,
    )
    if top is None or bottom is None:
        return None
    polarities = tuple(
        (
            1
            if sum(value > 0 for value in values)
            > sum(value < 0 for value in values)
            else -1
        )
        for run in (top[0], bottom[0])
        for values in (
            tuple(
                lane.transition_by_id[str(identity)].polarity
                for identity in run.transition_ids
                if lane.transition_by_id[str(identity)].polarity != 0
            ),
        )
        if values
    )
    if len(polarities) != 2 or polarities[0] != -polarities[1]:
        return None
    origin = _intersection(
        top[0].coordinate_interval_px,
        _subtract(bottom[0].coordinate_interval_px, broad_height),
    )
    if origin is None:
        return None
    angle_hull = _hull(
        (top[1].angle_interval_degrees, bottom[1].angle_interval_degrees)
    )
    if (
        angle_hull.width
        > PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
    ):
        return None
    return ProvisionalHeightTemplate(
        template_id=_stable_id(
            "reference-pair-height-template",
            geometry.component.component_id,
            top[0].run_id,
            bottom[0].run_id,
        ),
        component_id=geometry.component.component_id,
        origin_interval_px=origin,
        observed_runs=(top[0], bottom[0]),
        raw_observations=(top[1], bottom[1]),
    )


def _template_bound_opposite_run(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    top_run: ProfileRun,
    top_observation: PhotoBoundaryObservation,
    support_interval_px: FiniteInterval | None = None,
) -> ProfileRun | None:
    """Bind bottom transitions through the top edge and height template.

    The bottom query is registered and executed before this function.  This
    stage only groups its existing transitions against one fixed physical
    height; it does not widen coverage or create another query authority.
    """

    height = geometry.height_state.extent_projection_px()
    by_trace: dict[int, list[PhotoBoundaryTransition]] = {}
    top_transitions = tuple(
        transition
        for identity in top_run.transition_ids
        if (
            transition := lane.transition_by_id.get(str(identity))
        )
        is not None
    )
    top_polarities = tuple(
        transition.polarity
        for transition in top_transitions
        if transition.polarity != 0
    )
    if not top_polarities:
        return None
    top_polarity = (
        1
        if sum(value > 0 for value in top_polarities)
        > sum(value < 0 for value in top_polarities)
        else -1
    )
    for transition in lane.bottom_measurement_set.transitions:
        if (
            support_interval_px is not None
            and not support_interval_px.contains(
                float(transition.trace_coordinate_px),
                epsilon=0.5,
            )
        ):
            continue
        if transition.polarity != -top_polarity:
            continue
        top_coordinate = _line_boundary_coordinate(
            top_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        implied = _subtract(
            transition.coordinate_interval_px,
            FiniteInterval.exact(top_coordinate),
        )
        if _intersection(implied, height) is not None:
            by_trace.setdefault(
                transition.trace_coordinate_px,
                [],
            ).append(transition)

    selected: list[PhotoBoundaryTransition] = []
    for trace in lane.bottom_measurement_set.query.trace_positions_px:
        values = by_trace.get(trace, ())
        if not values:
            continue
        ordered = sorted(
            values,
            key=lambda item: (
                -item.coordinate_px,
                str(item.transition_id),
            ),
        )
        if (
            len(ordered) > 1
            and math.isclose(
                ordered[0].coordinate_px,
                ordered[1].coordinate_px,
                abs_tol=1.0e-9,
            )
        ):
            continue
        selected.append(ordered[0])

    queried = tuple(
        trace
        for trace in lane.bottom_measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(float(trace), epsilon=0.5)
    )
    minimum = max(
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_count,
        math.ceil(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            * len(queried)
        ),
    )
    if len(selected) < minimum:
        return None
    reference = lane.width_authority_px.center
    top_reference = _line_boundary_coordinate(
        top_observation,
        boundary_axis=lane.height_axis,
        trace_coordinate_px=reference,
    )
    projected: list[FiniteInterval] = []
    for transition in selected:
        top_at_trace = _line_boundary_coordinate(
            top_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        projected.append(
            _add(
                transition.coordinate_interval_px,
                FiniteInterval.exact(top_reference - top_at_trace),
            )
        )
    centers = sorted(value.center for value in projected)
    center = centers[len(centers) // 2]
    deviations = sorted(abs(value - center) for value in centers)
    mad = deviations[len(deviations) // 2]
    half_width = max(value.width / 2.0 for value in projected)
    interval = FiniteInterval(
        center - 3.0 * mad - half_width,
        center + 3.0 * mad + half_width,
    )
    traces = tuple(sorted(item.trace_coordinate_px for item in selected))
    continuity = continuous_trace_support_fraction(queried, traces)
    return ProfileRun(
        run_id=_stable_id(
            "template-bound-opposite-run",
            geometry.component.component_id,
            top_observation.observation_id,
            *(str(item.transition_id) for item in selected),
        ),
        coordinate_interval_px=interval,
        transition_ids=tuple(
            sorted(
                (item.transition_id for item in selected),
                key=str,
            )
        ),
        trace_coordinates_px=traces,
        role_hint=BoundaryRole.BOTTOM,
        qualified_anchor_roles=(),
        support_fraction=len(selected) / len(queried),
        continuous_support_fraction=continuity,
        fit_residual_px=mad,
        evidence_strength=sum(
            item.gradient_z + max(item.tone_z, item.texture_z)
            for item in selected
        )
        / len(selected),
        pair_qualified=True,
    )


def _cross_pair_seed_qualified(run: ProfileRun) -> bool:
    """Admit a measured edge only as one half of a complete physical pair."""

    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    return (
        run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        and run.support_fraction >= spec.minimum_cross_trace_fraction
        and run.continuous_support_fraction
        >= spec.minimum_continuous_support_fraction
    )


def provisional_height_templates(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    *,
    support_interval_px: FiniteInterval | None = None,
) -> tuple[ProvisionalHeightTemplate, ...]:
    allowance_mm = PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm
    scale = geometry.height_state.scale_authority
    broad_height = FiniteInterval(
        max(0.0, geometry.component.frame_height_mm - allowance_mm)
        * scale.minimum,
        (geometry.component.frame_height_mm + allowance_mm) * scale.maximum,
    )
    fit_cache: dict[tuple[BoundaryRole, str], PhotoBoundaryObservation | None] = {}
    fitted: dict[
        BoundaryRole,
        list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]],
    ] = {BoundaryRole.TOP: [], BoundaryRole.BOTTOM: []}
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        for run in lane.cross_profile.runs:
            if (
                run.role_hint != role
                or not (
                    run.pair_qualified
                    or run.anchor_qualified_for(role)
                    or _cross_pair_seed_qualified(run)
                )
            ):
                continue
            key = (role, run.run_id)
            if key not in fit_cache:
                fit_cache[key] = fit_template_bound_boundary_observation(
                    measurement_set,
                    transition_ids=run.transition_ids,
                    role=role,
                    source_axis_long=lane.width_axis,
                    boundary_axis_scale_px_per_mm=(
                        lane.height_scale_px_per_mm
                    ),
                    minimum_trace_fraction=(
                        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
                    ),
                    support_interval_px=support_interval_px,
                )
            observation = fit_cache[key]
            if observation is None:
                continue
            run = _inlier_profile_run(
                lane,
                run,
                observation,
                measurement_set,
                support_interval_px,
            )
            origin = (
                run.coordinate_interval_px
                if role == BoundaryRole.TOP
                else _subtract(run.coordinate_interval_px, broad_height)
            )
            fitted[role].append((run, observation, origin))
    for top_run, top_observation, _top_origin in tuple(
        fitted[BoundaryRole.TOP]
    ):
        bottom_run = _template_bound_opposite_run(
            lane,
            geometry,
            top_run,
            top_observation,
            support_interval_px,
        )
        if bottom_run is None:
            continue
        bottom_observation = fit_template_bound_boundary_observation(
            lane.bottom_measurement_set,
            transition_ids=bottom_run.transition_ids,
            role=BoundaryRole.BOTTOM,
            source_axis_long=lane.width_axis,
            boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
            minimum_trace_fraction=(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            ),
            support_interval_px=support_interval_px,
        )
        if bottom_observation is None:
            continue
        if bottom_observation.background_side_support_fraction < (
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.directional_background_support_minimum
        ):
            continue
        bottom_run = _inlier_profile_run(
            lane,
            bottom_run,
            bottom_observation,
            lane.bottom_measurement_set,
            support_interval_px,
        )
        fitted[BoundaryRole.BOTTOM].append(
            (
                bottom_run,
                bottom_observation,
                _subtract(bottom_run.coordinate_interval_px, broad_height),
            )
        )
    for role in fitted:
        fitted[role].sort(
            key=lambda item: (item[2].center, item[0].run_id)
        )

    templates: list[ProvisionalHeightTemplate] = []
    bottom_values = fitted[BoundaryRole.BOTTOM]
    bottom_centers = tuple(item[2].center for item in bottom_values)
    maximum_bottom_half_width = max(
        (item[2].width / 2.0 for item in bottom_values),
        default=0.0,
    )
    for top in fitted[BoundaryRole.TOP]:
        top_origin = top[2]
        start = bisect_left(
            bottom_centers,
            top_origin.minimum - maximum_bottom_half_width,
        )
        stop = bisect_right(
            bottom_centers,
            top_origin.maximum + maximum_bottom_half_width,
        )
        for bottom in bottom_values[start:stop]:
            origin = _intersection(top_origin, bottom[2])
            if origin is None:
                continue
            templates.append(
                ProvisionalHeightTemplate(
                    template_id=_stable_id(
                        "provisional-height-template",
                        geometry.component.component_id,
                        top[0].run_id,
                        bottom[0].run_id,
                    ),
                    component_id=geometry.component.component_id,
                    origin_interval_px=origin,
                    observed_runs=(top[0], bottom[0]),
                    raw_observations=(top[1], bottom[1]),
                )
            )
    for values in fitted.values():
        for run, observation, origin in values:
            if not run.anchor_qualified_for(run.role_hint):
                continue
            templates.append(
                ProvisionalHeightTemplate(
                    template_id=_stable_id(
                        "provisional-height-template",
                        geometry.component.component_id,
                        run.run_id,
                    ),
                    component_id=geometry.component.component_id,
                    origin_interval_px=origin,
                    observed_runs=(run,),
                    raw_observations=(observation,),
                )
            )
    if not templates:
        reference_pair = _reference_pair_height_template(
            lane,
            geometry,
            broad_height,
            support_interval_px=support_interval_px,
        )
        if reference_pair is not None:
            templates.append(reference_pair)
    unique = {item.template_id: item for item in templates}
    return tuple(unique[key] for key in sorted(unique))


def build_lane_template_proposal(
    lane: TemplateLaneInput,
    components: tuple[FramePhysicalSpec, ...],
) -> TemplateLaneProposal:
    component_proposals: list[ComponentTemplateProposal] = []
    all_height_templates: list[ProvisionalHeightTemplate] = []
    for component in components:
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=lane.width_scale_px_per_mm,
            height_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        roles = ordered_template_roles(lane.output_slot_count)
        votes = _sequence_phase_votes(lane, geometry, roles)
        groups, work = build_phase_groups(
            votes,
            roles,
            frame_width_lower_px=(
                geometry.width_state.extent_projection_px().minimum
            ),
        )
        if not groups:
            continue
        ambiguous_vote_ids = tuple(
            sorted(
                {
                    vote_id
                    for group in groups
                    for vote_id in group.ambiguous_vote_ids
                }
            )
        )
        heights = provisional_height_templates(lane, geometry)
        all_height_templates.extend(heights)
        component_proposal = ComponentTemplateProposal(
            component=component,
            initial_source_geometry=geometry,
            roles=roles,
            phase_votes=votes,
            phase_groups=groups,
            enhanced_phase_queries=tuple(
                EnhancedPhaseQuery(
                    query_id=_stable_id(
                        "enhanced-phase-query",
                        component.component_id,
                        vote_id,
                    ),
                    vote_id=vote_id,
                )
                for vote_id in ambiguous_vote_ids
            ),
            registered_sequence_role_queries=(),
            height_templates=heights,
            grouping_work=work,
        )
        component_proposals.append(component_proposal)
    observations = tuple(
        {
            str(observation.observation_id): observation
            for template in all_height_templates
            for observation in template.raw_observations
        }.values()
    )
    directions = _template_bound_direction_classes(
        tuple(all_height_templates)
    )
    return TemplateLaneProposal(
        lane=lane,
        components=tuple(component_proposals),
        raw_top_bottom_observations=tuple(
            sorted(observations, key=lambda item: str(item.observation_id))
        ),
        direction_classes=tuple(
            sorted(directions, key=direction_class_key)
        ),
    )


def shared_source_direction_classes(
    lane_proposals: tuple[TemplateLaneProposal, ...],
) -> tuple[SharedStripDirection, ...]:
    if not lane_proposals:
        return ()
    if any(not lane.direction_classes for lane in lane_proposals):
        return ()
    if (
        len(lane_proposals) == 1
        and len(lane_proposals[0].direction_classes) == 1
    ):
        return lane_proposals[0].direction_classes
    selected_ids = {
        str(identity)
        for lane in lane_proposals
        for direction in lane.direction_classes
        for identity in direction.selected_observation_ids
    }
    observations = tuple(
        observation
        for lane in lane_proposals
        for observation in lane.raw_top_bottom_observations
        if str(observation.observation_id) in selected_ids
    )
    directions = tuple(
        direction
        for lane in lane_proposals
        for direction in lane.direction_classes
    )
    if any(len(lane.direction_classes) > 1 for lane in lane_proposals):
        hull = FiniteInterval(
            min(
                direction.full_angle_interval_degrees.minimum
                for direction in directions
            ),
            max(
                direction.full_angle_interval_degrees.maximum
                for direction in directions
            ),
        )
        if (
            max(
                direction.canonical_angle_degrees
                for direction in directions
            )
            - min(
                direction.canonical_angle_degrees
                for direction in directions
            )
            > PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_shared_direction_hull_degrees
        ):
            return tuple(sorted(directions, key=direction_class_key))
        canonical = observed_strip_angle_estimate_degrees(observations)
        canonical = min(hull.maximum, max(hull.minimum, canonical))
        observation_ids = tuple(
            sorted(
                (observation.observation_id for observation in observations),
                key=str,
            )
        )
        return (
            SharedStripDirection(
                direction_id=_stable_id(
                    "bounded-shared-direction",
                    hull.minimum,
                    hull.maximum,
                    canonical,
                    *(str(identity) for identity in observation_ids),
                ),
                selected_observation_ids=observation_ids,
                full_angle_interval_degrees=hull,
                canonical_angle_degrees=canonical,
            ),
        )
    resolution = resolve_shared_strip_direction(observations)
    return () if resolution.direction is None else (resolution.direction,)


@dataclass(frozen=True)
class _BoundRunProjection:
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("bound run projection is invalid")


def _project_profile_run(
    run: ProfileRun,
    *,
    transitions: dict[str, PhotoBoundaryTransition],
    direction: SharedStripDirection,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    reference_trace_px: float,
    boundary_scale_px_per_mm: PositiveInterval,
) -> _BoundRunProjection:
    try:
        bound = tuple(transitions[str(identity)] for identity in run.transition_ids)
    except KeyError as exc:
        raise ValueError("profile run transition is unavailable") from exc
    if not bound:
        raise ValueError("profile run has no transition evidence")
    if boundary_axis == source_width_axis:
        canonical_slope = canonical_source_sequence_axis_slope(
            direction,
            source_width_axis,
        )
        slope_interval = source_sequence_axis_slope_interval(
            direction,
            source_width_axis,
        )
    else:
        canonical_slope = canonical_source_cross_axis_slope(
            direction,
            boundary_axis,
        )
        slope_interval = source_cross_axis_slope_interval(
            direction,
            boundary_axis,
        )
    centers = tuple(
        transition.coordinate_px
        + canonical_slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
    )
    weights = tuple(
        max(
            1.0,
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z),
        )
        for transition in bound
    )
    canonical = robust_scalar_location(
        centers,
        weights,
        boundary_scale_px_per_mm,
    )
    residuals = tuple(value - canonical for value in centers)
    center = sorted(residuals)[len(residuals) // 2]
    absolute = sorted(abs(value - center) for value in residuals)
    mad = absolute[len(absolute) // 2]
    numeric = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.transition_coordinate_sampling_uncertainty_px
    )
    fit_uncertainty = mad / math.sqrt(len(bound)) + numeric
    fit = FiniteInterval(
        canonical - fit_uncertainty,
        canonical + fit_uncertainty,
    )
    projected = tuple(
        coordinate
        + slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
        for coordinate in (
            transition.coordinate_interval_px.minimum,
            transition.coordinate_interval_px.maximum,
        )
        for slope in (slope_interval.minimum, slope_interval.maximum)
    )
    full = FiniteInterval(
        min(projected) - numeric,
        max(projected) + numeric,
    )
    if not full.contains(canonical, epsilon=1.0e-8):
        raise ValueError("canonical run position escaped exact projection")
    full = _hull((full, fit))
    return _BoundRunProjection(canonical, fit, full)


def _background_preference(run: ProfileRun, role: BoundaryRole) -> float:
    del role
    # Directional role preference already belongs to anchor qualification.
    # Canonical ranking uses only the format-neutral strength retained here.
    return min(1.0, run.evidence_strength / 12.0)


def _registered_sequence_transition_index(
    lane: TemplateLaneInput,
    direction: SharedStripDirection,
) -> dict[int, tuple[tuple[float, PhotoBoundaryTransition], ...]]:
    sequence_query_ids = {
        item.query.query_id for item in lane.sequence_measurement_sets
    }
    canonical_slope = canonical_source_sequence_axis_slope(
        direction,
        lane.width_axis,
    )
    reference = lane.height_authority_px.center
    values: dict[int, list[tuple[float, PhotoBoundaryTransition]]] = {}
    for transition in lane.transition_by_id.values():
        if transition.query_id not in sequence_query_ids:
            continue
        projected = transition.coordinate_px + canonical_slope * (
            reference - float(transition.trace_coordinate_px)
        )
        values.setdefault(transition.trace_coordinate_px, []).append(
            (projected, transition)
        )
    return {
        trace: tuple(
            sorted(items, key=lambda item: (item[0], str(item[1].transition_id)))
        )
        for trace, items in values.items()
    }


def _register_sequence_role_queries(
    proposal: TemplateLaneProposal,
) -> TemplateLaneProposal:
    components: list[ComponentTemplateProposal] = []
    search_allowance_px = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.center_offset_allowance_mm
        * proposal.lane.width_scale_px_per_mm.maximum
    )
    for component in proposal.components:
        queries = tuple(
            RegisteredSequenceRoleQuery(
                query_id=_stable_id(
                    "registered-sequence-role-query",
                    seed.seed_id,
                    role.role_index,
                ),
                seed_id=seed.seed_id,
                role=role,
                target_interval_px=_add(
                    _add(
                        _add(
                            seed.base_phase_interval_px,
                            _role_relative_projection(
                                role,
                                component.component,
                                component.initial_source_geometry.width_state,
                            ),
                        ),
                        local_advance_prefix(
                            seed.local_advance_relations,
                            lane_ordinal=role.lane_ordinal,
                        )[0],
                    ),
                    FiniteInterval(
                        -search_allowance_px,
                        search_allowance_px,
                    ),
                ),
            )
            for seed in build_template_sequence_seeds(component)
            for role in component.roles
        )
        components.append(
            replace(
                component,
                registered_sequence_role_queries=queries,
            )
        )
    return replace(proposal, components=tuple(components))


def _registered_sequence_role_run(
    lane: TemplateLaneInput,
    query: RegisteredSequenceRoleQuery,
    direction: SharedStripDirection,
    transition_index: dict[
        int,
        tuple[tuple[float, PhotoBoundaryTransition], ...],
    ],
) -> ProfileRun | None:
    """Bind an existing registered transition field to one template role."""

    slope_interval = source_sequence_axis_slope_interval(
        direction,
        lane.width_axis,
    )
    reference = lane.height_authority_px.center
    by_trace: dict[int, list[tuple[float, PhotoBoundaryTransition]]] = {}
    for trace, indexed in transition_index.items():
        coordinates = tuple(item[0] for item in indexed)
        start = bisect_left(coordinates, query.target_interval_px.minimum)
        stop = bisect_right(coordinates, query.target_interval_px.maximum)
        if start < stop:
            by_trace[trace] = list(indexed[start:stop])
    equivalence = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
        * lane.width_scale_px_per_mm.maximum
    )
    target = query.target_interval_px.center
    selected: list[tuple[float, PhotoBoundaryTransition]] = []
    for trace in sorted(by_trace):
        ordered = sorted(
            by_trace[trace],
            key=lambda item: (abs(item[0] - target), str(item[1].transition_id)),
        )
        if (
            len(ordered) > 1
            and abs(
                abs(ordered[1][0] - target)
                - abs(ordered[0][0] - target)
            )
            <= equivalence
        ):
            continue
        selected.append(ordered[0])
    if not selected:
        return None
    centers = sorted(item[0] for item in selected)
    center = centers[len(centers) // 2]
    connection = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_mm
        * lane.width_scale_px_per_mm.maximum
    )
    selected = tuple(
        item for item in selected if abs(item[0] - center) <= connection
    )
    queried_traces = tuple(
        sorted(
            {
                trace
                for item in lane.sequence_measurement_sets
                for trace in item.query.trace_positions_px
            }
        )
    )
    minimum = max(
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_count,
        math.ceil(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_cross_fit_trace_fraction
            * len(queried_traces)
        ),
    )
    if len(selected) < minimum:
        return None
    traces = tuple(sorted(item[1].trace_coordinate_px for item in selected))
    continuity = continuous_trace_support_fraction(queried_traces, traces)
    mean_gradient = sum(item[1].gradient_z for item in selected) / len(selected)
    mean_tone_or_texture = sum(
        max(item[1].tone_z, item[1].texture_z) for item in selected
    ) / len(selected)
    if (
        mean_gradient < PHOTO_BOUNDARY_MEASUREMENT_SPEC.gradient_z_minimum
        or mean_tone_or_texture
        < PHOTO_BOUNDARY_MEASUREMENT_SPEC.tone_or_texture_z_minimum
    ):
        return None
    projected_interval_values = tuple(
        coordinate
        + slope * (reference - float(transition.trace_coordinate_px))
        for _projected, transition in selected
        for coordinate in (
            transition.coordinate_interval_px.minimum,
            transition.coordinate_interval_px.maximum,
        )
        for slope in (slope_interval.minimum, slope_interval.maximum)
    )
    selected_centers = tuple(item[0] for item in selected)
    median = sorted(selected_centers)[len(selected_centers) // 2]
    residual = sorted(abs(value - median) for value in selected_centers)[
        len(selected_centers) // 2
    ]
    identities = tuple(
        sorted((item[1].transition_id for item in selected), key=str)
    )
    return ProfileRun(
        run_id=_stable_id(
            "registered-sequence-role-run",
            query.query_id,
            *(str(identity) for identity in identities),
        ),
        coordinate_interval_px=FiniteInterval(
            min(projected_interval_values),
            max(projected_interval_values),
        ),
        transition_ids=identities,
        trace_coordinates_px=traces,
        role_hint=None,
        qualified_anchor_roles=(query.role.role,),
        support_fraction=len(traces) / len(queried_traces),
        continuous_support_fraction=continuity,
        fit_residual_px=residual,
        evidence_strength=mean_gradient + mean_tone_or_texture,
        pair_qualified=True,
    )


def _bind_registered_sequence_roles(
    proposal: TemplateLaneProposal,
    direction: SharedStripDirection,
) -> tuple[TemplateLaneProposal, dict[str, ProfileRun], int]:
    queries = tuple(
        query
        for component in proposal.components
        for query in component.registered_sequence_role_queries
    )
    if not queries:
        return proposal, {}, 0
    registry = EnhancedQueryRegistry(tuple(query.query_id for query in queries))
    transition_index = _registered_sequence_transition_index(
        proposal.lane,
        direction,
    )
    runs: dict[str, ProfileRun] = {}
    for query in queries:
        if not registry.consume(query.query_id):
            raise ValueError("registered sequence role query executed twice")
        run = _registered_sequence_role_run(
            proposal.lane,
            query,
            direction,
            transition_index,
        )
        if run is not None:
            runs[query.query_id] = run
    merged = {
        run.run_id: run
        for run in (
            *proposal.lane.sequence_profile.runs,
            *runs.values(),
        )
    }
    profile = BasicAxisProfile(
        "sequence",
        proposal.lane.sequence_profile.coordinate_count,
        tuple(
            sorted(
                {
                    trace
                    for run in merged.values()
                    for trace in run.trace_coordinates_px
                }
            )
        ),
        tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    item.coordinate_interval_px.center,
                    item.run_id,
                ),
            )
        ),
    )
    return (
        replace(proposal, lane=replace(proposal.lane, sequence_profile=profile)),
        runs,
        registry.consumed_count,
    )


def _registered_pair_seeds(
    lane: TemplateLaneInput,
    component: ComponentTemplateProposal,
    seed: TemplateSequenceSeed,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[TemplateSequenceSeed, ...]:
    query_by_role = {
        query.role.role_index: query
        for query in component.registered_sequence_role_queries
        if query.seed_id == seed.seed_id and query.query_id in registered_runs
    }
    values: list[TemplateSequenceSeed] = []
    for ordinal in range(1, len(component.roles) // 2 + 1):
        roles = (
            component.roles[(ordinal - 1) * 2],
            component.roles[(ordinal - 1) * 2 + 1],
        )
        queries = tuple(query_by_role.get(role.role_index) for role in roles)
        if any(query is None for query in queries):
            continue
        runs = tuple(registered_runs[query.query_id] for query in queries)
        projections = tuple(
            _project_profile_run(
                run,
                transitions=lane.transition_by_id,
                direction=direction,
                boundary_axis=lane.width_axis,
                source_width_axis=lane.width_axis,
                reference_trace_px=lane.height_authority_px.center,
                boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
            )
            for run in runs
        )
        observed_width = _subtract(
            projections[1].fit_position_interval_px,
            projections[0].fit_position_interval_px,
        )
        if (
            _intersection(
                observed_width,
                component.initial_source_geometry.width_state.extent_projection_px(),
            )
            is None
        ):
            continue
        votes: list[PhaseVote] = []
        phase_intervals: list[FiniteInterval] = [seed.base_phase_interval_px]
        for role, run in zip(roles, runs, strict=True):
            prefix, _canonical_prefix = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=role.lane_ordinal,
            )
            phase = _subtract(
                _subtract(
                    run.coordinate_interval_px,
                    _role_relative_projection(
                        role,
                        component.component,
                        component.initial_source_geometry.width_state,
                    ),
                ),
                prefix,
            )
            phase_intervals.append(phase)
            votes.append(
                PhaseVote(
                    vote_id=_stable_id(
                        "registered-sequence-role-vote",
                        seed.seed_id,
                        role.role_index,
                        run.run_id,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=phase,
                    transition_ids=run.transition_ids,
                    template_coordinate_px=_role_canonical_relative(
                        role,
                        component.component,
                        component.initial_source_geometry.width_state,
                    ),
                )
            )
        phase = _common(tuple(phase_intervals))
        if phase is None:
            continue
        relation_candidates: list[LocalAdvanceRelation] = []
        original_evidence = _materialized_vote_evidence(
            lane,
            seed.votes,
            direction,
        )
        for observation in original_evidence:
            if (
                observation.role.role != BoundaryRole.START
                or abs(observation.role.lane_ordinal - ordinal) != 1
            ):
                continue
            if observation.role.lane_ordinal < ordinal:
                advance = _subtract(
                    projections[0].fit_position_interval_px,
                    observation.fit_position_interval_px,
                )
                relation_ordinal = observation.role.lane_ordinal
            else:
                advance = _subtract(
                    observation.fit_position_interval_px,
                    projections[0].fit_position_interval_px,
                )
                relation_ordinal = ordinal
            observed_gap = _subtract(advance, observed_width)
            delta = local_advance_delta_from_observed_gap(
                observed_gap,
                component.initial_source_geometry,
            )
            if delta is None:
                continue
            relation_candidates.append(
                LocalAdvanceRelation(
                    relation_ordinal=relation_ordinal,
                    kind=(
                        LocalAdvanceKind.NOMINAL
                        if delta == FiniteInterval.exact(0.0)
                        else LocalAdvanceKind.WIDE
                        if delta.center > 0.0
                        else LocalAdvanceKind.NARROW
                    ),
                    delta_interval_px=delta,
                    canonical_delta_px=delta.center,
                    observation_ids=tuple(
                        ObservationId(value)
                        for value in sorted(
                            {
                                *(
                                    str(identity)
                                    for identity in observation.transition_ids
                                ),
                                *(
                                    str(identity)
                                    for run in runs
                                    for identity in run.transition_ids
                                ),
                            }
                        )
                    ),
                )
            )
        relations = list(seed.local_advance_relations)
        for relation in relation_candidates:
            index = relation.relation_ordinal - 1
            relations[index] = _merge_local_advance_relations(
                (relations[index],),
                (relation,),
            )[0]
        combined = {
            vote.vote_id: vote for vote in (*seed.votes, *votes)
        }
        local = {
            vote.vote_id: vote
            for vote in (*seed.local_advance_votes, *votes)
        }
        values.append(
            replace(
                seed,
                seed_id=_stable_id(
                    "registered-pair-seed",
                    seed.seed_id,
                    ordinal,
                    *(vote.vote_id for vote in votes),
                ),
                base_phase_interval_px=phase,
                votes=tuple(combined[key] for key in sorted(combined)),
                local_advance_votes=tuple(
                    local[key] for key in sorted(local)
                ),
                local_advance_relations=tuple(relations),
                exclusion_authorized=True,
            )
        )
    return tuple(values) if values else (seed,)


def _component_materialization_seeds(
    proposal: TemplateLaneProposal,
    component: ComponentTemplateProposal,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[TemplateSequenceSeed, ...]:
    values = tuple(
        enhanced
        for seed in build_template_sequence_seeds(component)
        for enhanced in _registered_pair_seeds(
            proposal.lane,
            component,
            seed,
            direction,
            registered_runs,
        )
    )
    unique = {item.seed_id: item for item in values}
    return tuple(unique[key] for key in sorted(unique))


def _ambiguous_singleton_group(
    group: TemplatePhaseGroup,
    vote_id: str,
) -> bool:
    return (
        len(group.votes) == 1
        and group.votes[0].vote_id == vote_id
        and vote_id in group.ambiguous_vote_ids
    )


def _refine_component_phase_groups(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
) -> tuple[ComponentTemplateProposal, int]:
    """Resolve pre-registered ambiguous votes against existing groups only."""

    queries = proposal.enhanced_phase_queries
    if not queries:
        return proposal, 0
    registry = EnhancedQueryRegistry(tuple(item.query_id for item in queries))
    vote_by_id = {item.vote_id: item for item in proposal.phase_votes}
    run_by_id = {item.run_id: item for item in lane.sequence_profile.runs}
    assignments: dict[str, list[PhaseVote]] = {}
    for query in queries:
        if not registry.consume(query.query_id):
            raise ValueError("enhanced phase query executed more than once")
        vote = vote_by_id[query.vote_id]
        run = run_by_id[vote.run_id]
        projection = _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
        )
        relative = _role_relative_projection(
            vote.role,
            proposal.component,
            proposal.initial_source_geometry.width_state,
        )
        refined_vote = replace(
            vote,
            phase_interval_px=_subtract(
                projection.fit_position_interval_px,
                relative,
            ),
        )
        targets = tuple(
            group
            for group in proposal.phase_groups
            if not _ambiguous_singleton_group(group, vote.vote_id)
            and all(
                existing.run_id != vote.run_id
                and existing.role.role_index != vote.role.role_index
                and set(map(str, existing.transition_ids)).isdisjoint(
                    map(str, vote.transition_ids)
                )
                for existing in group.votes
            )
            and _intersection(
                group.phase_interval_px,
                refined_vote.phase_interval_px,
            )
            is not None
        )
        if len(targets) == 1:
            assignments.setdefault(targets[0].group_id, []).append(
                refined_vote
            )

    accepted: dict[str, tuple[PhaseVote, ...]] = {}
    for group in proposal.phase_groups:
        additions = tuple(assignments.get(group.group_id, ()))
        if not additions:
            continue
        combined = tuple((*group.votes, *additions))
        if _common(tuple(item.phase_interval_px for item in combined)) is not None:
            accepted[group.group_id] = additions
    accepted_vote_ids = {
        vote.vote_id for additions in accepted.values() for vote in additions
    }
    refined_groups: list[TemplatePhaseGroup] = []
    frame_width_lower = (
        proposal.initial_source_geometry.width_state.extent_projection_px().minimum
    )
    for group in proposal.phase_groups:
        if any(
            _ambiguous_singleton_group(group, vote_id)
            for vote_id in accepted_vote_ids
        ):
            continue
        additions = accepted.get(group.group_id, ())
        if not additions:
            refined_groups.append(group)
            continue
        combined = tuple(
            sorted(
                (*group.votes, *additions),
                key=lambda item: (item.role.role_index, item.vote_id),
            )
        )
        phase = _common(tuple(item.phase_interval_px for item in combined))
        if phase is None:
            raise ValueError("accepted enhanced phase evidence lost intersection")
        refined_groups.append(
            TemplatePhaseGroup(
                group_id=_stable_id(
                    "enhanced-template-phase-group",
                    group.group_id,
                    *(item.vote_id for item in additions),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                votes=combined,
                ambiguous_vote_ids=tuple(
                    vote_id
                    for vote_id in group.ambiguous_vote_ids
                    if vote_id not in accepted_vote_ids
                ),
                exclusion_authorized=group_support_exclusion_authorized(
                    role_coordinates_px=tuple(
                        item.template_coordinate_px for item in combined
                    ),
                    role_identities=tuple(
                        (item.role.lane_ordinal, item.role.role)
                        for item in combined
                    ),
                    transition_id_sets=tuple(
                        item.transition_ids for item in combined
                    ),
                    frame_width_lower_px=frame_width_lower,
                ),
            )
        )
    unique = {item.group_id: item for item in refined_groups}
    return (
        replace(
            proposal,
            phase_groups=tuple(unique[key] for key in sorted(unique)),
        ),
        registry.consumed_count,
    )


def _materialized_vote_evidence(
    lane: TemplateLaneInput,
    votes: tuple[PhaseVote, ...],
    direction: SharedStripDirection,
) -> tuple[BoundRoleEvidence, ...]:
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    values: list[BoundRoleEvidence] = []
    for vote in votes:
        run = run_by_id[vote.run_id]
        projection = _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
        )
        values.append(
            BoundRoleEvidence(
                role=vote.role,
                run_id=run.run_id,
                canonical_position_px=projection.canonical_position_px,
                fit_position_interval_px=projection.fit_position_interval_px,
                full_position_interval_px=projection.full_position_interval_px,
                transition_ids=run.transition_ids,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
                background_preference=_background_preference(
                    run,
                    vote.role.role,
                ),
            )
        )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.run_id))
    )


def _role_evidence_intervals(
    observations: tuple[BoundRoleEvidence, ...],
) -> dict[int, tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]]:
    by_role: dict[int, list[BoundRoleEvidence]] = {}
    for observation in observations:
        by_role.setdefault(observation.role.role_index, []).append(observation)
    result = {}
    for role_index, values in by_role.items():
        fit = _common(tuple(item.fit_position_interval_px for item in values))
        full = _common(tuple(item.full_position_interval_px for item in values))
        if fit is None or full is None:
            continue
        result[role_index] = (
            fit,
            _hull((fit, full)),
            tuple(
                ObservationId(identity)
                for identity in sorted(
                    {
                        str(transition_id)
                        for item in values
                        for transition_id in item.transition_ids
                    }
                )
            ),
        )
    return result


def _common_extent_constraint(
    constraints: tuple[tuple[FiniteInterval, tuple[ObservationId, ...]], ...],
) -> tuple[FiniteInterval, tuple[ObservationId, ...]] | None:
    if not constraints:
        return None
    common = _common(tuple(item[0] for item in constraints))
    if common is None:
        return None
    identities = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for _interval, values in constraints
                for identity in values
            }
        )
    )
    return common, identities


def _refine_source_geometry(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
    compatible_heights: tuple[ProvisionalHeightTemplate, ...],
    *,
    sequence_seeds: tuple[TemplateSequenceSeed, ...] | None = None,
) -> SourceFrameGeometry:
    geometry = proposal.initial_source_geometry
    width_state = geometry.width_state
    for seed in (
        build_template_sequence_seeds(proposal)
        if sequence_seeds is None
        else sequence_seeds
    ):
        if not seed.exclusion_authorized:
            continue
        evidence = _materialized_vote_evidence(
            lane,
            seed.votes,
            direction,
        )
        ordered = tuple(
            sorted(evidence, key=lambda item: item.role.role_index)
        )
        frame_width_lower = width_state.extent_projection_px().minimum
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                if not set(map(str, left.transition_ids)).isdisjoint(
                    map(str, right.transition_ids)
                ):
                    continue
                left_template = _role_canonical_relative(
                    left.role,
                    proposal.component,
                    width_state,
                )
                right_template = _role_canonical_relative(
                    right.role,
                    proposal.component,
                    width_state,
                )
                if right_template - left_template + 1.0e-9 < frame_width_lower:
                    continue
                left_prefix, _ = local_advance_prefix(
                    seed.local_advance_relations,
                    lane_ordinal=left.role.lane_ordinal,
                )
                right_prefix, _ = local_advance_prefix(
                    seed.local_advance_relations,
                    lane_ordinal=right.role.lane_ordinal,
                )
                observed = _subtract(
                    _subtract(
                        right.fit_position_interval_px,
                        left.fit_position_interval_px,
                    ),
                    _subtract(right_prefix, left_prefix),
                )
                left_q, left_scale = _role_affine_coefficients(
                    left.role,
                    proposal.component,
                )
                right_q, right_scale = _role_affine_coefficients(
                    right.role,
                    proposal.component,
                )
                observation_ids = tuple(
                    ObservationId(value)
                    for value in sorted(
                        {
                            *(str(identity) for identity in left.transition_ids),
                            *(str(identity) for identity in right.transition_ids),
                        }
                    )
                )
                width_state = width_state.intersect_affine_observation(
                    observed,
                    q_coefficient=right_q - left_q,
                    scale_coefficient=right_scale - left_scale,
                    observation_ids=observation_ids,
                )

        phase_intervals: list[FiniteInterval] = []
        for observation in evidence:
            prefix, _ = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=observation.role.lane_ordinal,
            )
            phase_intervals.append(
                _subtract(
                    _subtract(
                        observation.fit_position_interval_px,
                        _role_relative_projection(
                            observation.role,
                            proposal.component,
                            width_state,
                        ),
                    ),
                    prefix,
                )
            )
        phase = _common(tuple(phase_intervals))
        if phase is None:
            continue
        indexed_runs = tuple(
            sorted(
                lane.sequence_profile.runs,
                key=lambda item: (
                    item.coordinate_interval_px.center,
                    item.run_id,
                ),
            )
        )
        centers = tuple(
            item.coordinate_interval_px.center for item in indexed_runs
        )
        maximum_half_width = max(
            (
                item.coordinate_interval_px.width / 2.0
                for item in indexed_runs
            ),
            default=0.0,
        )

        def unique_registered_run(
            role: TemplateRole,
        ) -> tuple[ProfileRun, _BoundRunProjection] | None:
            prefix, _ = local_advance_prefix(
                seed.local_advance_relations,
                lane_ordinal=role.lane_ordinal,
            )
            predicted = _add(
                _add(
                    phase,
                    _role_relative_projection(
                        role,
                        proposal.component,
                        width_state,
                    ),
                ),
                prefix,
            )
            binding_allowance = (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm
                * lane.width_scale_px_per_mm.maximum
            )
            binding_domain = FiniteInterval(
                predicted.minimum - binding_allowance,
                predicted.maximum + binding_allowance,
            )
            start = bisect_left(
                centers,
                binding_domain.minimum - maximum_half_width,
            )
            stop = bisect_right(
                centers,
                binding_domain.maximum + maximum_half_width,
            )
            candidates: list[tuple[ProfileRun, _BoundRunProjection]] = []
            gap_domain = _gap_observation_domain_mm(proposal.component)
            allowed_gap_values = tuple(
                gap * scale
                for gap in (
                    gap_domain.minimum,
                    gap_domain.maximum,
                )
                for scale in (
                    width_state.feasible_scale_interval().minimum,
                    width_state.feasible_scale_interval().maximum,
                )
            )
            allowed_gap = FiniteInterval(
                min(allowed_gap_values),
                max(allowed_gap_values),
            )
            for run_index in range(start, stop):
                run = indexed_runs[run_index]
                if _intersection(
                    binding_domain,
                    run.coordinate_interval_px,
                ) is None:
                    continue
                projected = _project_profile_run(
                    run,
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.width_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=lane.height_authority_px.center,
                    boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
                )
                if _intersection(
                    binding_domain,
                    projected.fit_position_interval_px,
                ) is not None:
                    neighbor_index = (
                        run_index - 1
                        if role.role == BoundaryRole.START
                        else run_index + 1
                    )
                    if not 0 <= neighbor_index < len(indexed_runs):
                        continue
                    neighbor = indexed_runs[neighbor_index]
                    observed_gap = (
                        _subtract(
                            run.coordinate_interval_px,
                            neighbor.coordinate_interval_px,
                        )
                        if role.role == BoundaryRole.START
                        else _subtract(
                            neighbor.coordinate_interval_px,
                            run.coordinate_interval_px,
                        )
                    )
                    if _intersection(observed_gap, allowed_gap) is not None:
                        candidates.append((run, projected))
            return candidates[0] if len(candidates) == 1 else None

        for ordinal in range(2, lane.output_slot_count):
            start_role = proposal.roles[(ordinal - 1) * 2]
            end_role = proposal.roles[(ordinal - 1) * 2 + 1]
            start_projection = unique_registered_run(start_role)
            end_projection = unique_registered_run(end_role)
            if start_projection is None or end_projection is None:
                continue
            observed_width = _subtract(
                end_projection[1].fit_position_interval_px,
                start_projection[1].fit_position_interval_px,
            )
            matching_ids = tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        str(identity)
                        for run in (start_projection[0], end_projection[0])
                        for identity in run.transition_ids
                    }
                )
            )
            if not matching_ids:
                continue
            try:
                width_tolerance = (
                    FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio
                )
                width_state = width_state.intersect_affine_observation(
                    FiniteInterval(
                        observed_width.minimum
                        / (
                            proposal.component.frame_width_mm
                            * (1.0 + width_tolerance)
                        ),
                        observed_width.maximum
                        / (
                            proposal.component.frame_width_mm
                            * (1.0 - width_tolerance)
                        ),
                    ),
                    q_coefficient=0.0,
                    scale_coefficient=1.0,
                    observation_ids=matching_ids,
                )
            except ValueError:
                continue

    height_constraints: list[
        tuple[FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    for template in compatible_heights:
        template_runs = {
            run.role_hint: run
            for run in template.observed_runs
        }
        if set(template_runs) != {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            continue
        top = _project_profile_run(
            template_runs[BoundaryRole.TOP],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        bottom = _project_profile_run(
            template_runs[BoundaryRole.BOTTOM],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        observed_height = _subtract(
            bottom.full_position_interval_px,
            top.full_position_interval_px,
        )
        if (
            _intersection(
                observed_height,
                geometry.height_state.extent_projection_px(),
            )
            is not None
        ):
            height_constraints.append(
                (
                    observed_height,
                    tuple(
                        sorted(
                            (
                                *template_runs[
                                    BoundaryRole.TOP
                                ].transition_ids,
                                *template_runs[
                                    BoundaryRole.BOTTOM
                                ].transition_ids,
                            ),
                            key=str,
                        )
                    ),
                )
            )
    height_state = geometry.height_state
    if width_state.observation_ids:
        width_scale = lane.width_scale_px_per_mm
        height_scale = lane.height_scale_px_per_mm
        scale_ratio = (
            (height_scale.minimum + height_scale.maximum)
            / (width_scale.minimum + width_scale.maximum)
        )
        coupled_scale = width_state.feasible_scale_interval()
        try:
            height_state = height_state.intersect_affine_observation(
                FiniteInterval(
                    coupled_scale.minimum * scale_ratio,
                    coupled_scale.maximum * scale_ratio,
                ),
                q_coefficient=0.0,
                scale_coefficient=1.0,
                observation_ids=width_state.observation_ids,
            )
        except ValueError:
            pass
    height_constraints = [
        constraint
        for constraint in height_constraints
        if _intersection(
            constraint[0],
            height_state.extent_projection_px(),
        )
        is not None
    ]
    height_common = _common_extent_constraint(tuple(height_constraints))
    if height_common is not None:
        height_state = height_state.intersect_observed_extent(
            height_common[0],
            observation_ids=height_common[1],
        )
    return SourceFrameGeometry(
        geometry_id=_stable_id(
            "source-frame-geometry",
            proposal.component.component_id,
            width_state.vertices,
            height_state.vertices,
            width_state.observation_ids,
            height_state.observation_ids,
        ),
        component=proposal.component,
        width_state=width_state,
        height_state=height_state,
    )


def _interval_sum(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    result = FiniteInterval.exact(0.0)
    for value in values:
        result = _add(result, value)
    return result


def local_advance_delta_from_observed_gap(
    observed_gap_px: FiniteInterval,
    geometry: SourceFrameGeometry,
) -> FiniteInterval | None:
    """Constrain one observed gap by physical ordering, not a fixed gap."""

    scale = geometry.width_state.feasible_scale_interval()
    gap_mm = _gap_observation_domain_mm(geometry.component)
    allowed_products = tuple(
        gap * pixels_per_mm
        for gap in (gap_mm.minimum, gap_mm.maximum)
        for pixels_per_mm in (scale.minimum, scale.maximum)
    )
    allowed_gap_px = FiniteInterval(
        min(allowed_products),
        max(allowed_products),
    )
    constrained_gap = _intersection(observed_gap_px, allowed_gap_px)
    if constrained_gap is None:
        return None
    nominal_gap_px = geometry.width_state.project_affine(
        q_coefficient=0.0,
        scale_coefficient=_gap_seed_mm(geometry.component),
    )
    if _intersection(constrained_gap, nominal_gap_px) is not None:
        return FiniteInterval.exact(0.0)
    return _subtract(constrained_gap, nominal_gap_px)


def local_advance_prefix(
    relations: tuple[LocalAdvanceRelation, ...],
    *,
    lane_ordinal: int,
) -> tuple[FiniteInterval, float]:
    """Return the one-time phase step accumulated before one frame."""

    if lane_ordinal <= 0 or tuple(
        item.relation_ordinal for item in relations
    ) != tuple(range(1, len(relations) + 1)):
        raise ValueError("local advance relations must be ordered")
    prefix = relations[: lane_ordinal - 1]
    return (
        _interval_sum(tuple(item.delta_interval_px for item in prefix)),
        sum(item.canonical_delta_px for item in prefix),
    )


def _local_advance_relations(
    proposal: ComponentTemplateProposal,
    geometry: SourceFrameGeometry,
    observations: tuple[BoundRoleEvidence, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    by_role = _role_evidence_intervals(observations)
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, len(proposal.roles) // 2):
        end_index = ordinal * 2 - 1
        next_start_index = ordinal * 2
        end = by_role.get(end_index)
        start = by_role.get(next_start_index)
        if end is None or start is None:
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            )
            continue
        observed_gap = _subtract(start[0], end[0])
        observation_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(identity) for identity in end[2]),
                    *(str(identity) for identity in start[2]),
                }
            )
        )
        delta = local_advance_delta_from_observed_gap(
            observed_gap,
            geometry,
        )
        if delta is None:
            raise ValueError("observed gap exceeds format local advance authority")
        if delta == FiniteInterval.exact(0.0):
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=observation_ids,
                )
            )
            continue
        canonical_delta = delta.center
        gap_center = observed_gap.center
        if gap_center < 0.0:
            kind = LocalAdvanceKind.OVERLAP
        elif observed_gap.contains(0.0):
            kind = LocalAdvanceKind.CONTACT
        elif canonical_delta > 0.0:
            kind = LocalAdvanceKind.WIDE
        else:
            kind = LocalAdvanceKind.NARROW
        relations.append(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=canonical_delta,
                observation_ids=observation_ids,
            )
        )
    return tuple(relations)


def _supported_role_subset(
    group: TemplatePhaseGroup,
    *,
    first_ordinal: int,
    last_ordinal: int,
    frame_width_lower_px: float,
) -> tuple[PhaseVote, ...]:
    votes = tuple(
        item
        for item in group.votes
        if first_ordinal <= item.role.lane_ordinal <= last_ordinal
    )
    if not votes or not group_support_exclusion_authorized(
        role_coordinates_px=tuple(item.template_coordinate_px for item in votes),
        role_identities=tuple(
            (item.role.lane_ordinal, item.role.role) for item in votes
        ),
        transition_id_sets=tuple(item.transition_ids for item in votes),
        frame_width_lower_px=frame_width_lower_px,
    ):
        return ()
    return votes


def _structural_authority_votes(
    votes: tuple[PhaseVote, ...],
    *,
    frame_width_lower_px: float,
) -> tuple[PhaseVote, ...]:
    """Return the widest independent role pair that owns absolute phase.

    Other transitions in the same phase group remain query evidence, but an
    adjacent separator side cannot become another absolute-phase authority.
    Local adjacency is consumed by ``LocalAdvanceRelation`` instead.
    """

    pairs: list[tuple[float, str, str, PhaseVote, PhaseVote]] = []
    for left_index, left in enumerate(votes):
        left_ids = set(map(str, left.transition_ids))
        for right in votes[left_index + 1 :]:
            if not left_ids.isdisjoint(map(str, right.transition_ids)):
                continue
            opposite = (
                left.role.lane_ordinal == right.role.lane_ordinal
                and {left.role.role, right.role.role}
                == {BoundaryRole.START, BoundaryRole.END}
            )
            separation = abs(
                left.template_coordinate_px - right.template_coordinate_px
            )
            if not opposite and separation + 1.0e-9 < frame_width_lower_px:
                continue
            pairs.append(
                (
                    separation,
                    left.vote_id,
                    right.vote_id,
                    left,
                    right,
                )
            )
    if not pairs:
        return votes
    _distance, _left_id, _right_id, left, right = min(
        pairs,
        key=lambda item: (-item[0], item[1], item[2]),
    )
    return tuple(
        sorted((left, right), key=lambda item: item.role.role_index)
    )


def _phase_step_relation(
    upstream: TemplatePhaseGroup,
    downstream: TemplatePhaseGroup,
    *,
    relation_ordinal: int,
    upstream_votes: tuple[PhaseVote, ...],
    downstream_votes: tuple[PhaseVote, ...],
) -> LocalAdvanceRelation | None:
    upstream_ids = {
        str(identity)
        for vote in upstream_votes
        for identity in vote.transition_ids
    }
    downstream_ids = {
        str(identity)
        for vote in downstream_votes
        for identity in vote.transition_ids
    }
    if (
        upstream is downstream
        or not upstream_ids.isdisjoint(downstream_ids)
        or _intersection(
            upstream.phase_interval_px,
            downstream.phase_interval_px,
        )
        is not None
    ):
        return None
    delta = _subtract(
        downstream.phase_interval_px,
        upstream.phase_interval_px,
    )
    if delta.contains(0.0):
        return None
    return LocalAdvanceRelation(
        relation_ordinal=relation_ordinal,
        kind=(
            LocalAdvanceKind.WIDE
            if delta.center > 0.0
            else LocalAdvanceKind.NARROW
        ),
        delta_interval_px=delta,
        canonical_delta_px=delta.center,
        observation_ids=tuple(
            ObservationId(value)
            for value in sorted(upstream_ids | downstream_ids)
        ),
    )


def build_template_sequence_seeds(
    proposal: ComponentTemplateProposal,
) -> tuple[TemplateSequenceSeed, ...]:
    groups = proposal.phase_groups
    slot_count = len(proposal.roles) // 2
    frame_width_lower = (
        proposal.initial_source_geometry.width_state.extent_projection_px().minimum
    )
    downstream_by_split: dict[
        int,
        tuple[TemplatePhaseGroup, tuple[PhaseVote, ...]] | None,
    ] = {}
    upstream_support: dict[tuple[str, int], tuple[PhaseVote, ...]] = {}
    for split in range(1, slot_count):
        downstream: list[
            tuple[TemplatePhaseGroup, tuple[PhaseVote, ...]]
        ] = []
        for group in groups:
            upstream_support[(group.group_id, split)] = _supported_role_subset(
                group,
                first_ordinal=1,
                last_ordinal=split,
                frame_width_lower_px=frame_width_lower,
            )
            votes = _supported_role_subset(
                group,
                first_ordinal=split + 1,
                last_ordinal=slot_count,
                frame_width_lower_px=frame_width_lower,
            )
            if votes:
                downstream.append((group, votes))
        downstream_by_split[split] = (
            downstream[0] if len(downstream) == 1 else None
        )

    seeds: list[TemplateSequenceSeed] = []
    for initial in groups:
        current = initial
        group_for_ordinal: list[TemplatePhaseGroup] = []
        relations: list[LocalAdvanceRelation] = []
        group_ids = [initial.group_id]
        for split in range(1, slot_count):
            group_for_ordinal.append(current)
            downstream = downstream_by_split[split]
            relation = None
            if downstream is not None:
                upstream_votes = upstream_support[(current.group_id, split)]
                if upstream_votes:
                    relation = _phase_step_relation(
                        current,
                        downstream[0],
                        relation_ordinal=split,
                        upstream_votes=upstream_votes,
                        downstream_votes=downstream[1],
                    )
            if relation is None:
                relation = LocalAdvanceRelation(
                    relation_ordinal=split,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            else:
                current = downstream[0]
                if current.group_id not in group_ids:
                    group_ids.append(current.group_id)
            relations.append(relation)
        group_for_ordinal.append(current)
        votes = tuple(
            sorted(
                {
                    vote.vote_id: vote
                    for ordinal, group in enumerate(group_for_ordinal, start=1)
                    for vote in group.votes
                    if vote.role.lane_ordinal == ordinal
                }.values(),
                key=lambda item: (item.role.role_index, item.vote_id),
            )
        )
        if not votes:
            continue
        local_advance_votes = votes
        if initial.exclusion_authorized:
            votes = _structural_authority_votes(
                votes,
                frame_width_lower_px=frame_width_lower,
            )
        seeds.append(
            TemplateSequenceSeed(
                seed_id=_stable_id(
                    "template-sequence-seed",
                    *(group_ids),
                    *(item.kind.value for item in relations),
                    *(item.delta_interval_px for item in relations),
                ),
                phase_group_ids=tuple(group_ids),
                base_phase_interval_px=initial.phase_interval_px,
                votes=votes,
                local_advance_votes=local_advance_votes,
                local_advance_relations=tuple(relations),
                exclusion_authorized=(
                    initial.exclusion_authorized
                    and all(
                        item.kind == LocalAdvanceKind.NOMINAL
                        or bool(item.observation_ids)
                        for item in relations
                    )
                ),
            )
        )
    unique = {item.seed_id: item for item in seeds}
    return tuple(unique[key] for key in sorted(unique))


def _merge_local_advance_relations(
    declared: tuple[LocalAdvanceRelation, ...],
    observed: tuple[LocalAdvanceRelation, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    if len(declared) != len(observed):
        raise ValueError("local advance relation sets disagree")
    merged: list[LocalAdvanceRelation] = []
    for left, right in zip(declared, observed, strict=True):
        if left.relation_ordinal != right.relation_ordinal:
            raise ValueError("local advance relation ordinals disagree")
        left_is_nominal = left.kind == LocalAdvanceKind.NOMINAL
        right_is_nominal = right.kind == LocalAdvanceKind.NOMINAL
        if not left_is_nominal and right_is_nominal and right.observation_ids:
            raise ValueError("observed nominal gap contradicts phase step")
        if left_is_nominal:
            merged.append(right)
            continue
        if right_is_nominal:
            merged.append(left)
            continue
        common = _intersection(left.delta_interval_px, right.delta_interval_px)
        if common is None:
            raise ValueError("local phase-step evidence conflicts")
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in left.observation_ids),
                    *(str(item) for item in right.observation_ids),
                }
            )
        )
        merged.append(
            LocalAdvanceRelation(
                relation_ordinal=left.relation_ordinal,
                kind=(
                    left.kind
                    if left.kind == right.kind
                    else LocalAdvanceKind.WIDE
                    if common.center > 0.0
                    else LocalAdvanceKind.NARROW
                ),
                delta_interval_px=common,
                canonical_delta_px=common.center,
                observation_ids=identities,
            )
        )
    return tuple(merged)


def _registered_sequence_run_direction_interval(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
) -> FiniteInterval | None:
    """Bound one already measured short-edge slope without making it phase."""

    values = tuple(
        transitions[str(identity)]
        for identity in run.transition_ids
        if str(identity) in transitions
    )
    traces = np.asarray(
        [item.trace_coordinate_px for item in values],
        dtype=np.float64,
    )
    coordinates = np.asarray(
        [item.coordinate_px for item in values],
        dtype=np.float64,
    )
    if len(values) < 2 or float(np.ptp(traces)) <= 0.0:
        return None
    design = np.column_stack((traces, np.ones_like(traces)))
    slope, intercept = np.linalg.lstsq(
        design,
        coordinates,
        rcond=None,
    )[0]
    residual = np.abs(coordinates - (slope * traces + intercept))
    interval_half_width = np.asarray(
        [item.coordinate_interval_px.width / 2.0 for item in values],
        dtype=np.float64,
    )
    slope_allowance = 2.0 * float(
        np.max(residual + interval_half_width)
    ) / float(np.ptp(traces))
    return FiniteInterval(
        math.degrees(math.atan(float(slope) - slope_allowance)),
        math.degrees(math.atan(float(slope) + slope_allowance)),
    )


def _materialize_sequence_placement(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    seed: TemplateSequenceSeed,
    direction: SharedStripDirection,
    geometry: SourceFrameGeometry,
) -> SequencePlacement:
    observations = _materialized_vote_evidence(
        lane,
        seed.votes,
        direction,
    )
    if not observations:
        raise ValueError("sequence placement has no absolute pixel anchor")
    relations = _merge_local_advance_relations(
        seed.local_advance_relations,
        _local_advance_relations(
            proposal,
            geometry,
            _materialized_vote_evidence(
                lane,
                seed.local_advance_votes,
                direction,
            ),
        ),
    )
    fit_phases: list[FiniteInterval] = []
    full_phases: list[FiniteInterval] = []
    implied_canonical: list[float] = []
    weights: list[float] = []
    for observation in observations:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=observation.role.lane_ordinal,
        )
        relative = _role_relative_projection(
            observation.role,
            proposal.component,
            geometry.width_state,
        )
        fit_phases.append(
            _subtract(
                _subtract(observation.fit_position_interval_px, relative),
                prefix_interval,
            )
        )
        full_phases.append(
            _subtract(
                _subtract(observation.full_position_interval_px, relative),
                prefix_interval,
            )
        )
        implied_canonical.append(
            observation.canonical_position_px
            - _role_canonical_relative(
                observation.role,
                proposal.component,
                geometry.width_state,
            )
            - prefix_canonical
        )
        weights.append(
            max(
                1.0,
                observation.support_fraction
                + observation.continuous_support_fraction,
            )
        )
    phase_fit = _common(tuple(fit_phases))
    phase_full = _common(tuple(full_phases))
    if phase_fit is None or phase_full is None:
        raise ValueError("template-bound observations disagree on phase")
    phase_full = _hull((phase_full, phase_fit))
    canonical_phase = robust_scalar_location(
        tuple(implied_canonical),
        tuple(weights),
        geometry.width_state.feasible_scale_interval(),
    )
    if not phase_fit.contains(canonical_phase, epsilon=1.0e-9):
        canonical_phase = phase_fit.center
    by_role = _role_evidence_intervals(observations)
    registered_safety_projections = tuple(
        sorted(
            (
                (
                    projection.full_position_interval_px.center,
                    run,
                    projection,
                )
                for run in lane.sequence_profile.runs
                if run.pair_qualified
                for projection in (
                    _project_profile_run(
                        run,
                        transitions=lane.transition_by_id,
                        direction=direction,
                        boundary_axis=lane.width_axis,
                        source_width_axis=lane.width_axis,
                        reference_trace_px=lane.height_authority_px.center,
                        boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
                    ),
                )
            ),
            key=lambda item: (item[0], item[1].run_id),
        )
    )
    safety_projection_centers = tuple(
        item[0] for item in registered_safety_projections
    )
    maximum_safety_half_width = max(
        (
            item[2].full_position_interval_px.width / 2.0
            for item in registered_safety_projections
        ),
        default=0.0,
    )
    safety_lookup_allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.center_offset_allowance_mm
        * lane.width_scale_px_per_mm.maximum
    )
    canonical_positions: list[float] = []
    fit_positions: list[FiniteInterval] = []
    full_positions: list[FiniteInterval] = []
    sequence_edge_direction_intervals: list[FiniteInterval] = []
    safety_support_transition_ids: list[tuple[ObservationId, ...]] = []
    for role in proposal.roles:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=role.lane_ordinal,
        )
        relative = _role_relative_projection(
            role,
            proposal.component,
            geometry.width_state,
        )
        relative_canonical = _role_canonical_relative(
            role,
            proposal.component,
            geometry.width_state,
        )
        fit = _add(_add(phase_fit, relative), prefix_interval)
        full = _add(_add(phase_full, relative), prefix_interval)
        observed = by_role.get(role.role_index)
        if observed is not None:
            fit_intersection = _intersection(fit, observed[0])
            full_intersection = _intersection(full, observed[1])
            if fit_intersection is None or full_intersection is None:
                raise ValueError("observed role contradicts propagated template")
            fit = fit_intersection
            full = _hull((fit, full_intersection))
        corridor = FiniteInterval(
            fit.minimum - safety_lookup_allowance,
            fit.maximum + safety_lookup_allowance,
        )
        start = bisect_left(
            safety_projection_centers,
            corridor.minimum - maximum_safety_half_width,
        )
        stop = bisect_right(
            safety_projection_centers,
            corridor.maximum + maximum_safety_half_width,
        )
        registered_support = tuple(
            (run, projection)
            for _center, run, projection in registered_safety_projections[
                start:stop
            ]
            if _intersection(
                corridor,
                projection.full_position_interval_px,
            )
            is not None
        )
        if registered_support:
            nearest_distance = min(
                abs(
                    projection.full_position_interval_px.center
                    - fit.center
                )
                for _run, projection in registered_support
            )
            equivalence = (
                PHOTO_BOUNDARY_MEASUREMENT_SPEC.geometry_equivalence_mm
                * lane.width_scale_px_per_mm.maximum
            )
            registered_support = tuple(
                (run, projection)
                for run, projection in registered_support
                if abs(
                    projection.full_position_interval_px.center
                    - fit.center
                )
                <= nearest_distance + equivalence
            )
        if registered_support:
            full = _hull(
                (
                    full,
                    *(
                        projection.full_position_interval_px
                        for _run, projection in registered_support
                    ),
                )
            )
        canonical_sequence_slope = canonical_source_sequence_axis_slope(
            direction,
            lane.width_axis,
        )
        direction_intervals = tuple(
            interval
            for run, _projection in registered_support
            if (
                interval := _registered_sequence_run_direction_interval(
                    run,
                    lane.transition_by_id,
                )
            )
            is not None
        )
        direction_interval = (
            _hull(direction_intervals)
            if direction_intervals
            else FiniteInterval.exact(
                math.degrees(math.atan(canonical_sequence_slope))
            )
        )
        direction_slopes = (
            math.tan(math.radians(direction_interval.minimum)),
            math.tan(math.radians(direction_interval.maximum)),
        )
        direction_displacement = max(
            abs(value - canonical_sequence_slope)
            for value in direction_slopes
        ) * max(
            abs(
                lane.height_authority_px.minimum
                - lane.height_authority_px.center
            ),
            abs(
                lane.height_authority_px.maximum
                - lane.height_authority_px.center
            ),
        )
        full = FiniteInterval(
            full.minimum - direction_displacement,
            full.maximum + direction_displacement,
        )
        canonical = canonical_phase + relative_canonical + prefix_canonical
        if not fit.contains(canonical, epsilon=1.0e-8):
            # Canonical preference has no authority outside the conditional
            # feasible interval.  The midpoint is the deterministic fallback,
            # never a clamp of the invalid preference.
            canonical = fit.center
        canonical_positions.append(canonical)
        fit_positions.append(fit)
        full_positions.append(_hull((full, fit)))
        sequence_edge_direction_intervals.append(direction_interval)
        safety_support_transition_ids.append(
            tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        str(identity)
                        for run, _projection in registered_support
                        for identity in run.transition_ids
                    }
                )
            )
        )
    return SequencePlacement(
        placement_id=_stable_id(
            "sequence-placement",
            proposal.component.component_id,
            seed.seed_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        template_seed_id=seed.seed_id,
        phase_group_ids=seed.phase_group_ids,
        source_geometry_id=geometry.geometry_id,
        roles=proposal.roles,
        phase_fit_interval_px=phase_fit,
        phase_full_interval_px=phase_full,
        lane_gap_model=LaneGapModel.from_edge_families(
            geometry.width_state,
            lane_id=lane.lane_id,
            edge_families=tuple(
                tuple(
                    (
                        run.coordinate_interval_px,
                        run.transition_ids,
                    )
                    for run in lane.sequence_profile.runs
                    if run.anchor_qualified_for(role)
                )
                for role in (BoundaryRole.START, BoundaryRole.END)
            ),
            format_gap_prior_mm=proposal.component.format_gap_prior_mm,
        ),
        local_advance_relations=relations,
        canonical_positions_px=tuple(canonical_positions),
        fit_positions_px=tuple(fit_positions),
        full_positions_px=tuple(full_positions),
        sequence_edge_direction_intervals_degrees=tuple(
            sequence_edge_direction_intervals
        ),
        safety_support_transition_ids=tuple(
            safety_support_transition_ids
        ),
        observations=observations,
        exclusion_authorized=seed.exclusion_authorized,
    )


def _slope_displacement_interval(
    slope: FiniteInterval,
    trace_delta_px: float,
) -> FiniteInterval:
    values = (
        slope.minimum * trace_delta_px,
        slope.maximum * trace_delta_px,
    )
    return FiniteInterval(min(values), max(values))


def _materialize_cross_placement(
    lane: TemplateLaneInput,
    template: ProvisionalHeightTemplate,
    direction: SharedStripDirection,
    geometry: SourceFrameGeometry,
    frame_reference_traces_px: tuple[float, ...],
    frame_reference_intervals_px: tuple[FiniteInterval, ...],
) -> CrossPlacement:
    lane_reference = lane.width_authority_px.center
    observed_runs = {
        run.role_hint: run
        for run in template.observed_runs
    }
    lane_projections = {
        role: _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane_reference,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        for role, run in observed_runs.items()
    }
    extent = geometry.height_state.extent_projection_px()
    phase = _conditional_fit_and_full(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.fit_position_interval_px, extent)
            for role, projection in lane_projections.items()
        ),
        tuple(
            projection.full_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.full_position_interval_px, extent)
            for role, projection in lane_projections.items()
        ),
    )
    if phase is None:
        raise ValueError("template-bound height roles disagree on source height")
    phase_fit, phase_full = phase
    canonical_slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    slope_interval = source_cross_axis_slope_interval(
        direction,
        lane.height_axis,
    )
    if len(frame_reference_traces_px) != len(frame_reference_intervals_px):
        raise ValueError("cross placement frame references are incomplete")
    frame_states: list[
        tuple[
            dict[BoundaryRole, FiniteInterval],
            dict[BoundaryRole, FiniteInterval],
            float,
        ]
    ] = []
    for reference, reference_interval in zip(
        frame_reference_traces_px,
        frame_reference_intervals_px,
        strict=True,
    ):
        delta = reference - lane_reference
        canonical_shift = canonical_slope * delta
        shift = _slope_displacement_interval(slope_interval, delta)
        model_top_fit = _add(phase_fit, shift)
        model_bottom_fit = _add(model_top_fit, extent)
        full_shifts = tuple(
            _slope_displacement_interval(
                slope_interval,
                endpoint - lane_reference,
            )
            for endpoint in (
                reference_interval.minimum,
                reference_interval.maximum,
            )
        )
        model_top_full = _add(phase_full, _hull(full_shifts))
        model_bottom_full = _add(model_top_full, extent)
        frame_fit = {
            BoundaryRole.TOP: model_top_fit,
            BoundaryRole.BOTTOM: model_bottom_fit,
        }
        frame_full = {
            BoundaryRole.TOP: model_top_full,
            BoundaryRole.BOTTOM: model_bottom_full,
        }
        for role, run in observed_runs.items():
            direct_values = tuple(
                _project_profile_run(
                    run,
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.height_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=endpoint,
                    boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                )
                for endpoint in (
                    reference,
                    reference_interval.minimum,
                    reference_interval.maximum,
                )
            )
            conditioned = _conditional_fit_and_full(
                (
                    frame_fit[role],
                    direct_values[0].fit_position_interval_px,
                ),
                (
                    frame_full[role],
                    _hull(
                        tuple(
                            item.full_position_interval_px
                            for item in direct_values
                        )
                    ),
                ),
            )
            if conditioned is None:
                raise ValueError("exact height projection contradicts template")
            frame_fit[role], frame_full[role] = conditioned
        frame_states.append((frame_fit, frame_full, canonical_shift))

    extent_constraints = tuple(
        intersection
        for _frame_fit, frame_full, _canonical_shift in frame_states
        if (
            intersection := _intersection(
                extent,
                _subtract(
                    frame_full[BoundaryRole.BOTTOM],
                    frame_full[BoundaryRole.TOP],
                ),
            )
        )
        is not None
    )
    if len(extent_constraints) != len(frame_states):
        raise ValueError("frame height is outside joint source geometry")
    shared_extent = _common(extent_constraints)
    if shared_extent is None:
        raise ValueError("frame heights have no shared physical extent")
    _scale, normalized, _factor = geometry.height_state.canonical_state()
    canonical_extent_preference = (
        geometry.height_state.design_extent_mm * normalized
    )
    canonical_extent = (
        canonical_extent_preference
        if shared_extent.contains(canonical_extent_preference)
        else shared_extent.center
    )
    canonical_extent_interval = FiniteInterval.exact(canonical_extent)
    canonical_phase_condition = _conditional_fit_and_full(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(
                projection.fit_position_interval_px,
                canonical_extent_interval,
            )
            for role, projection in lane_projections.items()
        ),
        tuple(
            projection.full_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(
                projection.full_position_interval_px,
                canonical_extent_interval,
            )
            for role, projection in lane_projections.items()
        ),
    )
    if canonical_phase_condition is None:
        raise ValueError("canonical source height is outside observed roles")
    canonical_phase_interval = canonical_phase_condition[0]
    canonical_phase_preference = sum(
        projection.canonical_position_px
        - (canonical_extent if role == BoundaryRole.BOTTOM else 0.0)
        for role, projection in lane_projections.items()
    ) / len(lane_projections)
    canonical_phase = (
        canonical_phase_preference
        if canonical_phase_interval.contains(canonical_phase_preference)
        else canonical_phase_interval.center
    )

    top_canonical: list[float] = []
    bottom_canonical: list[float] = []
    top_fit: list[FiniteInterval] = []
    bottom_fit: list[FiniteInterval] = []
    top_full: list[FiniteInterval] = []
    bottom_full: list[FiniteInterval] = []
    for frame_fit, frame_full, canonical_shift in frame_states:
        frame_phase = _conditional_fit_and_full(
            (
                frame_fit[BoundaryRole.TOP],
                _subtract(
                    frame_fit[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
            (
                frame_full[BoundaryRole.TOP],
                _subtract(
                    frame_full[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
        )
        if frame_phase is None:
            raise ValueError("canonical source height is infeasible at frame")
        frame_phase_interval = frame_phase[0]
        predicted_phase = canonical_phase + canonical_shift
        frame_phase = (
            predicted_phase
            if frame_phase_interval.contains(predicted_phase)
            else frame_phase_interval.center
        )
        canonical_top = frame_phase
        canonical_bottom = frame_phase + canonical_extent
        if canonical_top >= canonical_bottom:
            raise ValueError("canonical height placement is unordered")
        conditional_top_fit = (
            frame_fit[BoundaryRole.TOP]
            if frame_fit[BoundaryRole.TOP].contains(
                canonical_top,
                epsilon=1.0e-8,
            )
            else FiniteInterval.exact(canonical_top)
        )
        conditional_bottom_fit = (
            frame_fit[BoundaryRole.BOTTOM]
            if frame_fit[BoundaryRole.BOTTOM].contains(
                canonical_bottom,
                epsilon=1.0e-8,
            )
            else FiniteInterval.exact(canonical_bottom)
        )
        top_canonical.append(canonical_top)
        bottom_canonical.append(canonical_bottom)
        top_fit.append(conditional_top_fit)
        bottom_fit.append(conditional_bottom_fit)
        top_full.append(
            _hull((conditional_top_fit, frame_full[BoundaryRole.TOP]))
        )
        bottom_full.append(
            _hull(
                (
                    conditional_bottom_fit,
                    frame_full[BoundaryRole.BOTTOM],
                )
            )
        )
    observation_by_role = {
        observation.role: observation for observation in template.raw_observations
    }
    return CrossPlacement(
        placement_id=_stable_id(
            "cross-placement",
            template.template_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        provisional_template_id=template.template_id,
        source_geometry_id=geometry.geometry_id,
        lane_reference_trace_px=lane_reference,
        frame_reference_traces_px=frame_reference_traces_px,
        top_canonical_positions_px=tuple(top_canonical),
        bottom_canonical_positions_px=tuple(bottom_canonical),
        top_fit_positions_px=tuple(top_fit),
        bottom_fit_positions_px=tuple(bottom_fit),
        top_full_positions_px=tuple(top_full),
        bottom_full_positions_px=tuple(bottom_full),
        evidence=tuple(
            CrossRoleEvidence(
                role=role,
                run_id=run.run_id,
                observation=observation_by_role[role],
                canonical_position_at_lane_reference_px=(
                    lane_projections[role].canonical_position_px
                ),
                fit_position_at_lane_reference_px=(
                    lane_projections[role].fit_position_interval_px
                ),
                full_position_at_lane_reference_px=(
                    lane_projections[role].full_position_interval_px
                ),
            )
            for role, run in observed_runs.items()
        ),
    )


def _boundary_geometry(
    *,
    role: BoundaryRole,
    canonical_position_px: float,
    full_position_interval_px: FiniteInterval,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    direction: SharedStripDirection,
    observation_ids: tuple[ObservationId, ...],
    position_source: PositionSource,
    named_position_inference: str | None,
    sequence_direction_interval_degrees: FiniteInterval | None = None,
    sequence_direction_reference_id: str | None = None,
) -> FrameBoundaryGeometry:
    if not observation_ids:
        raise ValueError("frame boundary requires position evidence")
    return FrameBoundaryGeometry(
        role=role,
        line=canonical_boundary_line(
            direction,
            boundary_axis=boundary_axis,
            source_axis_long=source_width_axis,
            trace_coordinate_px=reference_trace_px,
            position_px=canonical_position_px,
            support_projection_px=support_projection_px,
        ),
        reference_trace_px=reference_trace_px,
        canonical_position_px=canonical_position_px,
        full_position_interval_px=full_position_interval_px,
        full_direction_interval_degrees=(
            sequence_direction_interval_degrees
            if role in {BoundaryRole.START, BoundaryRole.END}
            else direction.full_angle_interval_degrees
        ),
        position_source=position_source,
        position_observation_ids=observation_ids,
        named_position_inference=named_position_inference,
        direction_authority=(
            DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            if role in {BoundaryRole.START, BoundaryRole.END}
            else DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ),
        direction_reference_id=(
            sequence_direction_reference_id
            if role in {BoundaryRole.START, BoundaryRole.END}
            else direction.direction_id
        ),
    )


def _canonical_frames(
    lane: TemplateLaneInput,
    direction: SharedStripDirection,
    sequence: SequencePlacement,
    cross: CrossPlacement,
) -> tuple[FrameFormatPlacement, ...]:
    sequence_observations: dict[int, tuple[ObservationId, ...]] = {}
    for role_index in range(len(sequence.roles)):
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for item in sequence.observations
                    if item.role.role_index == role_index
                    for identity in item.transition_ids
                }
            )
        )
        if identities:
            sequence_observations[role_index] = identities
    all_sequence_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in sequence.observations
                for identity in item.transition_ids
            }
        )
    )
    cross_by_role = {
        item.role: tuple(item.observation.transition_ids)
        for item in cross.evidence
    }
    all_cross_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in cross.evidence
                for identity in item.observation.transition_ids
            }
        )
    )
    frames: list[FrameFormatPlacement] = []
    for ordinal in range(1, len(sequence.roles) // 2 + 1):
        start_index = (ordinal - 1) * 2
        end_index = start_index + 1
        frame_reference = (
            sequence.canonical_positions_px[start_index]
            + sequence.canonical_positions_px[end_index]
        ) / 2.0
        width_support = FiniteInterval(
            sequence.full_positions_px[start_index].minimum,
            sequence.full_positions_px[end_index].maximum,
        )
        start_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in sequence_observations.get(start_index, ())),
                    *(
                        str(item)
                        for item in sequence.safety_support_transition_ids[
                            start_index
                        ]
                    ),
                }
            )
        ) or all_sequence_ids
        end_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in sequence_observations.get(end_index, ())),
                    *(
                        str(item)
                        for item in sequence.safety_support_transition_ids[
                            end_index
                        ]
                    ),
                }
            )
        ) or all_sequence_ids
        top_ids = cross_by_role.get(BoundaryRole.TOP, all_cross_ids)
        bottom_ids = cross_by_role.get(BoundaryRole.BOTTOM, all_cross_ids)
        start = _boundary_geometry(
            role=BoundaryRole.START,
            canonical_position_px=sequence.canonical_positions_px[start_index],
            full_position_interval_px=sequence.full_positions_px[start_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=start_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if start_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if start_index in sequence_observations
                else "start_from_template_phase_and_lane_gap"
            ),
            sequence_direction_interval_degrees=(
                sequence.sequence_edge_direction_intervals_degrees[
                    start_index
                ]
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        end = _boundary_geometry(
            role=BoundaryRole.END,
            canonical_position_px=sequence.canonical_positions_px[end_index],
            full_position_interval_px=sequence.full_positions_px[end_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=end_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if end_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if end_index in sequence_observations
                else "end_from_template_phase_and_lane_gap"
            ),
            sequence_direction_interval_degrees=(
                sequence.sequence_edge_direction_intervals_degrees[
                    end_index
                ]
            ),
            sequence_direction_reference_id=sequence.placement_id,
        )
        top = _boundary_geometry(
            role=BoundaryRole.TOP,
            canonical_position_px=cross.top_canonical_positions_px[ordinal - 1],
            full_position_interval_px=cross.top_full_positions_px[ordinal - 1],
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=top_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.TOP in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.TOP in cross_by_role
                else "top_from_observed_bottom_and_source_height"
            ),
        )
        bottom = _boundary_geometry(
            role=BoundaryRole.BOTTOM,
            canonical_position_px=(
                cross.bottom_canonical_positions_px[ordinal - 1]
            ),
            full_position_interval_px=(
                cross.bottom_full_positions_px[ordinal - 1]
            ),
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=bottom_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.BOTTOM in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.BOTTOM in cross_by_role
                else "bottom_from_observed_top_and_source_height"
            ),
        )
        polygon = (
            top.line.intersection(start.line),
            top.line.intersection(end.line),
            bottom.line.intersection(end.line),
            bottom.line.intersection(start.line),
        )
        frames.append(
            FrameFormatPlacement(
                placement_geometry_id=_stable_id(
                    "frame-format-placement",
                    sequence.placement_id,
                    cross.placement_id,
                    ordinal,
                ),
                lane_id=lane.lane_id,
                lane_ordinal=ordinal,
                top=top,
                bottom=bottom,
                start=start,
                end=end,
                canonical_source_polygon=polygon,
            )
        )
    return tuple(frames)


def _sequence_within_authority(
    placement: SequencePlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in placement.full_positions_px
    )


def _cross_within_authority(
    placement: CrossPlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in (
            *placement.top_full_positions_px,
            *placement.bottom_full_positions_px,
        )
    )


def _compatible_height_templates(
    lane_proposal: TemplateLaneProposal,
    component_proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
) -> tuple[ProvisionalHeightTemplate, ...]:
    selected_ids = {str(identity) for identity in direction.selected_observation_ids}
    return tuple(
        template
        for template in component_proposal.height_templates
        if {
            str(observation.observation_id)
            for observation in template.raw_observations
        }.issubset(selected_ids)
    )


def _direction_bound_cross_profile_runs(
    lane: TemplateLaneInput,
    direction: SharedStripDirection,
    sequence_support_px: FiniteInterval,
) -> tuple[ProfileRun, ...]:
    """Aggregate registered transitions like a bounded multi-trace profile.

    V4.2.8's useful separator producer combined many scan lines before it
    localized an edge.  V5 keeps the stronger authority model: pixels have
    already been queried, the shared direction is template-bound, and every
    aggregate run still consists solely of auditable transition identities.
    Two half-bin lattices prevent a real line from disappearing on one bin
    boundary; all structurally supported bins survive, so this is not top-K
    selection or a candidate score competition.
    """

    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    reference = lane.width_authority_px.center
    slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    bin_width = max(
        1.0,
        spec.local_window_mm * lane.height_scale_px_per_mm.maximum,
    )
    values: list[ProfileRun] = []
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        queried = tuple(
            trace
            for trace in measurement_set.query.trace_positions_px
            if sequence_support_px.contains(float(trace), epsilon=0.5)
        )
        if not queried:
            continue
        queried_set = set(queried)
        minimum_support = max(
            spec.minimum_trace_count,
            math.ceil(spec.minimum_cross_fit_trace_fraction * len(queried)),
        )
        projected = tuple(
            (
                transition,
                transition.coordinate_px
                + slope * (reference - transition.trace_coordinate_px),
            )
            for transition in measurement_set.transitions
            if transition.trace_coordinate_px in queried_set
            and transition.polarity != 0
        )
        for polarity in (-1, 1):
            polarity_values = tuple(
                item for item in projected if item[0].polarity == polarity
            )
            for offset in (0.0, bin_width / 2.0):
                buckets: dict[int, dict[int, list[tuple[PhotoBoundaryTransition, float]]]] = {}
                for transition, coordinate in polarity_values:
                    bucket = math.floor((coordinate - offset) / bin_width)
                    buckets.setdefault(bucket, {}).setdefault(
                        transition.trace_coordinate_px,
                        [],
                    ).append((transition, coordinate))
                for bucket, by_trace in buckets.items():
                    center = offset + (bucket + 0.5) * bin_width
                    selected: list[tuple[PhotoBoundaryTransition, float]] = []
                    ambiguous = False
                    for trace in queried:
                        candidates = by_trace.get(trace, ())
                        if not candidates:
                            continue
                        ordered = sorted(
                            candidates,
                            key=lambda item: (
                                abs(item[1] - center),
                                str(item[0].transition_id),
                            ),
                        )
                        if (
                            len(ordered) > 1
                            and math.isclose(
                                abs(ordered[0][1] - center),
                                abs(ordered[1][1] - center),
                                abs_tol=1.0e-9,
                            )
                        ):
                            ambiguous = True
                            continue
                        selected.append(ordered[0])
                    traces = tuple(
                        sorted(item[0].trace_coordinate_px for item in selected)
                    )
                    continuity = continuous_trace_support_fraction(
                        queried,
                        traces,
                    )
                    if (
                        len(traces) < minimum_support
                        or continuity < spec.minimum_continuous_support_fraction
                        or not selected
                    ):
                        continue
                    transitions = tuple(item[0] for item in selected)
                    mean_gradient = sum(
                        item.gradient_z for item in transitions
                    ) / len(transitions)
                    mean_tone_or_texture = sum(
                        max(item.tone_z, item.texture_z)
                        for item in transitions
                    ) / len(transitions)
                    if (
                        mean_gradient < spec.gradient_z_minimum
                        or mean_tone_or_texture
                        < spec.tone_or_texture_z_minimum
                    ):
                        continue
                    coordinates = tuple(item[1] for item in selected)
                    coordinate_center = float(np.median(coordinates))
                    residual = float(
                        np.median(
                            np.abs(
                                np.asarray(coordinates, dtype=np.float64)
                                - coordinate_center
                            )
                        )
                    )
                    half_width = max(
                        item.coordinate_interval_px.width / 2.0
                        for item in transitions
                    )
                    identities = tuple(
                        sorted(
                            (item.transition_id for item in transitions),
                            key=str,
                        )
                    )
                    values.append(
                        ProfileRun(
                            run_id=_stable_id(
                                "direction-bound-cross-profile-run",
                                role.value,
                                polarity,
                                *(str(identity) for identity in identities),
                            ),
                            coordinate_interval_px=FiniteInterval(
                                coordinate_center - residual - half_width,
                                coordinate_center + residual + half_width,
                            ),
                            transition_ids=identities,
                            trace_coordinates_px=traces,
                            role_hint=role,
                            qualified_anchor_roles=(),
                            support_fraction=len(traces) / len(queried),
                            continuous_support_fraction=continuity,
                            fit_residual_px=residual,
                            evidence_strength=(
                                mean_gradient + mean_tone_or_texture
                            ),
                            pair_qualified=not ambiguous,
                        )
                    )
    unique = {
        (
            item.role_hint,
            tuple(map(str, item.transition_ids)),
        ): item
        for item in values
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.coordinate_interval_px.center,
                item.run_id,
            ),
        )
    )


def _staged_height_templates(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    direction: SharedStripDirection,
    sequence_support_px: FiniteInterval,
) -> tuple[ProvisionalHeightTemplate, ...]:
    """Rebind registered cross evidence inside one complete sequence span.

    The source-wide top/bottom lattice establishes possible shared directions.
    A partial strip, however, must not lose its actual photo edge merely because
    the rest of the scan canvas contains no frames.  This stage performs no new
    pixel query: it groups the already registered transition records again with
    support restricted to the full uncertain span of this sequence template.
    """

    top_regions = track_side_transition_regions(
        (lane.top_measurement_set,),
        reference_trace_px=lane.width_authority_px.center,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        support_interval_px=sequence_support_px,
    )
    bottom_regions = track_side_transition_regions(
        (lane.bottom_measurement_set,),
        reference_trace_px=lane.width_authority_px.center,
        boundary_axis_scale_px_per_mm=lane.height_scale_px_per_mm,
        support_interval_px=sequence_support_px,
    )
    tracked_profile = cross_profile_from_regions(
        top_regions,
        bottom_regions,
        coordinate_count=(
            int(math.floor(lane.height_authority_px.maximum))
            - int(math.ceil(lane.height_authority_px.minimum))
            + 1
        ),
        transition_by_id=lane.transition_by_id,
    )
    aggregate_runs = _direction_bound_cross_profile_runs(
        lane,
        direction,
        sequence_support_px,
    )
    scoped_lane = replace(
        lane,
        cross_profile=BasicAxisProfile(
            "cross",
            tracked_profile.coordinate_count,
            tuple(
                sorted(
                    {
                        *tracked_profile.trace_coordinates_px,
                        *(
                            trace
                            for run in aggregate_runs
                            for trace in run.trace_coordinates_px
                        ),
                    }
                )
            ),
            tuple(
                sorted(
                    {
                        run.run_id: run
                        for run in (*tracked_profile.runs, *aggregate_runs)
                    }.values(),
                    key=lambda item: (
                        item.coordinate_interval_px.center,
                        item.run_id,
                    ),
                )
            ),
        ),
    )

    return tuple(
        template
        for template in provisional_height_templates(
            scoped_lane,
            geometry,
            support_interval_px=sequence_support_px,
        )
        if all(
            _intersection(
                observation.angle_interval_degrees,
                direction.full_angle_interval_degrees,
            )
            is not None
            for observation in template.raw_observations
        )
    )


def _materialize_component_seed(
    lane_proposal: TemplateLaneProposal,
    component_proposal: ComponentTemplateProposal,
    seed: TemplateSequenceSeed,
    direction: SharedStripDirection,
    source_geometry: SourceFrameGeometry | None = None,
) -> tuple[FormatPlacement, ...]:
    """Materialize one complete template interpretation.

    A seed owns one correlated source-geometry and local-advance hypothesis.
    Conflicting interpretations remain separate physical placements.
    """

    lane = lane_proposal.lane
    compatible_heights = _compatible_height_templates(
        lane_proposal,
        component_proposal,
        direction,
    )
    if not compatible_heights:
        return ()
    if source_geometry is None:
        try:
            geometry = _refine_source_geometry(
                lane,
                component_proposal,
                direction,
                compatible_heights,
                sequence_seeds=(seed,),
            )
            observed_relations = _local_advance_relations(
                component_proposal,
                geometry,
                _materialized_vote_evidence(
                    lane,
                    seed.local_advance_votes,
                    direction,
                ),
            )
            joint_relations = _merge_local_advance_relations(
                seed.local_advance_relations,
                observed_relations,
            )
            if joint_relations != seed.local_advance_relations:
                seed = replace(
                    seed,
                    local_advance_relations=joint_relations,
                )
                geometry = _refine_source_geometry(
                    lane,
                    component_proposal,
                    direction,
                    compatible_heights,
                    sequence_seeds=(seed,),
                )
        except ValueError:
            return ()
    else:
        if source_geometry.component != component_proposal.component:
            raise ValueError("source geometry component disagrees")
        geometry = source_geometry
    try:
        sequence = _materialize_sequence_placement(
            lane,
            component_proposal,
            seed,
            direction,
            geometry,
        )
    except ValueError:
        return ()
    if not _sequence_within_authority(sequence, lane.width_authority_px):
        return ()
    sequence_support_px = FiniteInterval(
        min(item.minimum for item in sequence.full_positions_px),
        max(item.maximum for item in sequence.full_positions_px),
    )
    staged_heights = _staged_height_templates(
        lane,
        geometry,
        direction,
        sequence_support_px,
    )
    if staged_heights:
        compatible_heights = tuple(
            {
                item.template_id: item
                for item in (*compatible_heights, *staged_heights)
            }.values()
        )
        if source_geometry is None:
            try:
                geometry = _refine_source_geometry(
                    lane,
                    component_proposal,
                    direction,
                    compatible_heights,
                    sequence_seeds=(seed,),
                )
                sequence = _materialize_sequence_placement(
                    lane,
                    component_proposal,
                    seed,
                    direction,
                    geometry,
                )
            except ValueError:
                return ()
    if not _sequence_within_authority(sequence, lane.width_authority_px):
        return ()
    frame_references = tuple(
        (
            sequence.canonical_positions_px[index * 2]
            + sequence.canonical_positions_px[index * 2 + 1]
        )
        / 2.0
        for index in range(lane.output_slot_count)
    )
    frame_reference_intervals = tuple(
        FiniteInterval(
            (
                sequence.full_positions_px[index * 2].minimum
                + sequence.full_positions_px[index * 2 + 1].minimum
            )
            / 2.0,
            (
                sequence.full_positions_px[index * 2].maximum
                + sequence.full_positions_px[index * 2 + 1].maximum
            )
            / 2.0,
        )
        for index in range(lane.output_slot_count)
    )
    crosses: list[CrossPlacement] = []
    for template in compatible_heights:
        try:
            crosses.append(
                _materialize_cross_placement(
                    lane,
                    template,
                    direction,
                    geometry,
                    frame_references,
                    frame_reference_intervals,
                )
            )
        except ValueError:
            continue
    if not crosses:
        return ()
    unique_crosses = {item.placement_id: item for item in crosses}
    retained_crosses = tuple(
        unique_crosses[key]
        for key in sorted(unique_crosses)
        if _cross_within_authority(
            unique_crosses[key],
            lane.height_authority_px,
        )
    )
    if not retained_crosses:
        return ()
    return tuple(
        FormatPlacement(
            placement_id=_stable_id(
                "format-placement",
                lane.lane_id,
                component_proposal.component.component_id,
                direction.direction_id,
                geometry.geometry_id,
                sequence.placement_id,
                cross.placement_id,
            ),
            lane_id=lane.lane_id,
            component=component_proposal.component,
            output_slot_count=lane.output_slot_count,
            direction=direction,
            source_frame_geometry=geometry,
            sequence=sequence,
            cross=cross,
            canonical=CanonicalFormatPlacement(
                canonical_id=_stable_id(
                    "canonical-format-placement",
                    sequence.placement_id,
                    cross.placement_id,
                ),
                sequence_placement_id=sequence.placement_id,
                cross_placement_id=cross.placement_id,
                frames=_canonical_frames(
                    lane,
                    direction,
                    sequence,
                    cross,
                ),
            ),
        )
        for cross in retained_crosses
    )


def materialize_lane_placements(
    proposal: TemplateLaneProposal,
    direction: SharedStripDirection,
    registered_runs: dict[str, ProfileRun],
) -> tuple[tuple[FormatPlacement, ...], int, bool]:
    proposed_unsorted = tuple(
        (component, seed)
        for component in sorted(
            proposal.components,
            key=lambda item: item.component.component_id,
        )
        for seed in _component_materialization_seeds(
            proposal,
            component,
            direction,
            registered_runs,
        )
    )
    proposed = tuple(
        sorted(
            proposed_unsorted,
            key=lambda item: (
                -sum(
                    {
                        vote.role.role
                        for vote in item[1].votes
                        if vote.role.lane_ordinal == ordinal
                    }
                    == {BoundaryRole.START, BoundaryRole.END}
                    for ordinal in {
                        vote.role.lane_ordinal for vote in item[1].votes
                    }
                ),
                -len({vote.role.role_index for vote in item[1].votes}),
                min(vote.role.lane_ordinal for vote in item[1].votes),
                tuple(
                    value
                    for vote in item[1].votes
                    for value in (
                        vote.phase_interval_px.minimum.hex(),
                        vote.phase_interval_px.maximum.hex(),
                    )
                ),
                tuple(
                    sorted(
                        str(identity)
                        for vote in item[1].votes
                        for identity in vote.transition_ids
                    )
                ),
                item[0].component.component_id,
                item[1].seed_id,
            ),
        )
    )
    seed_materializations = tuple(
        placements
        for component, seed in proposed[:MAX_COMPLETE_CHAINS_PER_LANE]
        if (placements := _materialize_component_seed(
            proposal,
            component,
            seed,
            direction,
        ))
    )
    values = tuple(
        placement
        for placements in seed_materializations
        for placement in placements
    )
    unique = {item.placement_id: item for item in values}
    ordered = tuple(unique[key] for key in sorted(unique))
    proposed_count = max(len(proposed), len(ordered))
    bound_exceeded = proposed_count > MAX_COMPLETE_CHAINS_PER_LANE
    return (
        ordered[:MAX_COMPLETE_CHAINS_PER_LANE],
        proposed_count,
        bound_exceeded,
    )


def _basic_lane_structurally_closed(
    placements: tuple[FormatPlacement, ...],
) -> bool:
    return bool(placements) and all(
        placement.sequence.exclusion_authorized
        for placement in placements
    )


def materialize_source_placements(
    lane_proposals: tuple[TemplateLaneProposal, ...],
    direction: SharedStripDirection,
) -> SourcePlacementMaterialization:
    """Materialize every lane from one source-wide component geometry."""

    if not lane_proposals:
        return SourcePlacementMaterialization((), (), (), (), ())
    phase_lanes: list[TemplateLaneProposal] = []
    phase_counts: list[int] = []
    for lane in lane_proposals:
        components: list[ComponentTemplateProposal] = []
        count = 0
        for component in lane.components:
            refined, consumed = _refine_component_phase_groups(
                lane.lane,
                component,
                direction,
            )
            components.append(refined)
            count += consumed
        phase_lanes.append(replace(lane, components=tuple(components)))
        phase_counts.append(count)
    phase_lane_proposals = tuple(phase_lanes)
    basic_independent = tuple(
        materialize_lane_placements(lane, direction, {})
        for lane in phase_lane_proposals
    )
    basic_closed = tuple(
        _basic_lane_structurally_closed(materialization[0])
        for materialization in basic_independent
    )
    if all(basic_closed):
        refined_lane_proposals = phase_lane_proposals
        enhanced_counts = phase_counts
        registered_runs_by_lane = [
            {} for _lane in refined_lane_proposals
        ]
        independent = basic_independent
    else:
        bound = tuple(
            (
                (lane, {}, 0)
                if closed
                else _bind_registered_sequence_roles(
                    _register_sequence_role_queries(lane),
                    direction,
                )
            )
            for lane, closed in zip(
                phase_lane_proposals,
                basic_closed,
                strict=True,
            )
        )
        refined_lane_proposals = tuple(item[0] for item in bound)
        registered_runs_by_lane = [item[1] for item in bound]
        enhanced_counts = [
            phase_count + item[2]
            for phase_count, item in zip(
                phase_counts,
                bound,
                strict=True,
            )
        ]
        independent = tuple(
            (
                basic
                if closed
                else materialize_lane_placements(
                    lane,
                    direction,
                    registered_runs,
                )
            )
            for lane, registered_runs, basic, closed in zip(
                refined_lane_proposals,
                registered_runs_by_lane,
                basic_independent,
                basic_closed,
                strict=True,
            )
        )
    if len(refined_lane_proposals) > 2:
        raise ValueError("template-first source supports at most two lanes")
    return SourcePlacementMaterialization(
        placements_by_lane=tuple(item[0] for item in independent),
        proposed_complete_chain_counts_by_lane=tuple(
            item[1] for item in independent
        ),
        chain_bound_exceeded_by_lane=tuple(item[2] for item in independent),
        enhanced_query_counts_by_lane=tuple(enhanced_counts),
        lane_proposals=refined_lane_proposals,
    )
